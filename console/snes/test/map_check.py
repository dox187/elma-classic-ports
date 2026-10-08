"""Checks the level background of the SNES (build/test_map.sfc, map.asm)
in Mesen 2: moves the camera along paths, and where it stops compares
what VRAM and CGRAM hold for the screen with the converted data
(map_ref.py), and the screenshot with the expected picture. Measures the
master clocks of map_set_camera and the bytes it queues, every frame.

  map_check.py [--levels 0,19,33,45,47] [--path sweep,fast] [--out DIR]

Paths: "sweep" goes over the whole level row by row at 8 pixels a frame;
"fast" makes diagonal moves of 10-16 pixels a frame (falls) between random
places; "start" only looks at the start of the level. Every check holds the
camera still for a few frames first.
"""

import argparse
import binascii
import io
import os
import random
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, HERE)
import elmadata  # noqa: E402
import levgeom  # noqa: E402
import map_ref  # noqa: E402
import mesen  # noqa: E402

HOLD = 20           # frames still before a check
LOAD_WAIT = 60      # frames after a load before the path
SCREEN_W, SCREEN_H = 256, 224


def clamp_cam(x, y, w, h):
    return max(0, min(x, w - SCREEN_W)), max(0, min(y, h - SCREEN_H))


def path_sweep(w, h, every=90):
    """Row by row at 8 pixels a frame; checks every `every` frames."""
    cams, checks = [], []
    y = 0
    x = 0
    right = True
    while True:
        xe = w - SCREEN_W if right else 0
        while x != xe:
            x += 8 if xe > x else -8
            if (x > xe) == right:
                x = xe
            cams.append((x, y))
            if len(cams) % every == 0:
                cams += [(x, y)] * HOLD
                checks.append(len(cams))
        cams += [(x, y)] * HOLD
        checks.append(len(cams))
        if y >= h - SCREEN_H:
            break
        ye = min(y + 192, h - SCREEN_H)
        while y < ye:
            y = min(y + 8, ye)
            cams.append((x, y))
        right = not right
    return cams, checks


def path_fast(w, h, n=12, seed=1):
    """Moves of 10-16 pixels a frame in both directions between random
    places."""
    rnd = random.Random(seed)
    cams, checks = [], []
    x, y = clamp_cam(w // 2, h // 2, w, h)
    for _ in range(n):
        tx, ty = clamp_cam(rnd.randrange(0, max(1, w)), rnd.randrange(0, max(1, h)), w, h)
        sp = rnd.choice((10, 12, 16))
        while (x, y) != (tx, ty):
            dx, dy = tx - x, ty - y
            x += max(-sp, min(sp, dx))
            y += max(-sp, min(sp, dy))
            cams.append((x, y))
        cams += [(x, y)] * HOLD
        checks.append(len(cams))
    return cams, checks


def make_lua(syms, plan, last):
    """plan: list of (level, cams, checks) one after the other."""
    L = []
    a = lambda n: syms[n]
    L.append('local mem = emu.memType.snesMemory')
    L.append('local vram = emu.memType.snesVideoRam')
    L.append('local cgram = emu.memType.snesCgRam')
    L.append('local function w16(ad, v) emu.write(ad, v & 255, mem) emu.write(ad + 1, (v >> 8) & 255, mem) end')
    L.append('local function r16(ad) return emu.read(ad, mem) | (emu.read(ad + 1, mem) << 8) end')
    L.append('local function hex(t) return (t:gsub(".", function(c) return string.format("%02x", string.byte(c)) end)) end')
    L.append('local function dumpv(name, from, n) local t = {} for i = 0, n - 1 do t[#t + 1] = string.char(emu.read(from + i, vram)) end print("OUT VRAM " .. name .. " " .. hex(table.concat(t))) end')
    L.append('local function dumpc(name) local t = {} for i = 0, 255 do t[#t + 1] = string.char(emu.read(i, cgram)) end print("OUT CGRAM " .. name .. " " .. hex(table.concat(t))) end')
    L.append('local cams = {}')
    L.append('local loads = {}')
    L.append('local checks = {}')
    f = 1
    for n, (level, cams, checks) in enumerate(plan):
        L.append('loads[%d] = %d' % (f, level))
        for i, (x, y) in enumerate(cams):
            L.append('cams[%d] = {%d, %d}' % (f + i, x & 0xFFFF, y & 0xFFFF))
        for c in checks:
            L.append('checks[%d] = "%d_%d_%d"' % (f + c - 1, level, n, c))
        f += len(cams) + 2
    L.append('local frame = 0')
    L.append('local pf = 0')       # frame of the plan: stops while a check waits for the jobs
    L.append('local waited = 0')
    L.append('local lastjobs = 0')
    L.append('local t0 = 0')
    L.append('local cpu = 0')
    L.append('emu.addMemoryCallback(function() t0 = emu.getMasterClock() end, emu.callbackType.exec, %d, %d)' % (a('map_set_camera'), a('map_set_camera')))
    L.append('emu.addMemoryCallback(function() cpu = emu.getMasterClock() - t0 end, emu.callbackType.exec, %d, %d)' % (a('map_set_camera_end'), a('map_set_camera_end')))
    # The parts of map_set_camera (sums over all frames):
    L.append('local prof = {region = 0, work = 0, flush = 0, dec = 0, make = 0, ndec = 0, nmake = 0}')
    L.append('local tp, td, tm = 0, 0, 0')
    def cb(label, code):
        if label in syms:
            L.append('emu.addMemoryCallback(function() %s end, emu.callbackType.exec, %d, %d)' % (code, syms[label], syms[label]))
    cb('map_p_region', 'local c = emu.getMasterClock() prof.region = prof.region + c - t0 tp = c')
    cb('map_p_work', 'local c = emu.getMasterClock() prof.work = prof.work + c - tp tp = c')
    cb('map_set_camera_end', 'prof.flush = prof.flush + emu.getMasterClock() - tp')
    cb('map_decode_job@p_dec0', 'td = emu.getMasterClock()')
    cb('map_decode_job@p_dec1', 'prof.dec = prof.dec + emu.getMasterClock() - td prof.ndec = prof.ndec + 1')
    cb('map_work@p_make0', 'tm = emu.getMasterClock()')
    cb('map_work@p_make1', 'prof.make = prof.make + emu.getMasterClock() - tm prof.nmake = prof.nmake + 1')
    L.append('''emu.addEventCallback(function()
  frame = frame + 1
  -- A check waits (the camera still) until all jobs are done:
  -- (two frames without jobs: the last transfers are done by the NMI)
  local ck0 = checks[pf + 1]
  local busy = r16(%(jobs)d) > 0 or lastjobs > 0
  lastjobs = r16(%(jobs)d)
  if ck0 and busy and waited < 600 then
    waited = waited + 1
  else
    pf = pf + 1
    waited = 0
  end
  local l = loads[pf]
  if l and waited == 0 then w16(%(level)d, l) w16(%(load)d, 1) end
  local c = cams[pf]
  if c then w16(%(cx)d, c[1]) w16(%(cy)d, c[2]) end
  if frame == 1 then w16(%(ready)d, 0x5A5A) end
  print(string.format("STAT %%d %%d %%d %%d %%d %%d %%d %%d %%d %%d %%d", frame, cpu, r16(%(bytes)d), r16(%(tiles)d), r16(%(comp)d), r16(%(jobs)d), r16(%(short)d), r16(%(minfree)d), r16(%(mcx)d), r16(%(mcy)d), pf))
  cpu = 0
  local ck = checks[pf]
  if ck and waited == 0 then
    dumpv("chr_" .. ck, 0, 704 * 32)
    dumpv("map_" .. ck, 0x5800 * 2, 4096)
    dumpv("sky_" .. ck, 0x2C00 * 2, 0x2400 * 2)
    dumpc("cg_" .. ck)
    local t = {} for i = 0, 4095 do t[#t + 1] = string.char(emu.read(%(shadow)d + i, mem)) end
    print("OUT WRAM shadow_" .. ck .. " " .. hex(table.concat(t)))
    print("OUT SHOT shot_" .. ck .. " " .. hex(emu.takeScreenshot()))
    local st = emu.getState()
    print(string.format("CHECK %%s %%d %%d %%d %%d %%d %%d %%d %%d %%d", ck, r16(%(mcx)d), r16(%(mcy)d), r16(%(jobs)d), r16(%(s0)d), r16(%(s1)d), r16(%(resets)d),
      st["ppu.layers[0].hscroll"], st["ppu.layers[0].vscroll"], st["ppu.layers[1].hscroll"]))
  end
  if pf >= %(last)d then
    print(string.format("PROF %%d %%d %%d %%d %%d %%d %%d", prof.region, prof.work, prof.flush, prof.dec, prof.ndec, prof.make, prof.nmake))
    emu.stop(0)
  end
end, emu.eventType.endFrame)''' % {
        'level': a('test_level'), 'load': a('test_load'), 'cx': a('test_cam_x'), 'cy': a('test_cam_y'),
        'ready': a('test_ready'), 'bytes': a('map_stat_bytes'), 'tiles': a('map_stat_tiles'),
        'comp': a('map_stat_comp'), 'jobs': a('map_stat_jobs'), 'short': a('map_stat_short'),
        'minfree': a('map_stat_minfree'), 'mcx': a('map_cam_x'), 'mcy': a('map_cam_y'),
        'shadow': a('map_shadow'), 's0': a('core_scroll'), 's1': a('core_scroll') + 2, 'nofree': a('map_stat_nofree'), 'resets': a('map_stat_resets'),
        'last': last})
    return '\n'.join(L)


def words(b):
    return np.frombuffer(b, dtype='<u2')


def check(md, level, cam, dumps, shot):
    """Errors of a check: VRAM of BG1 for the screen, BG2, CGRAM, picture."""
    errs = []
    chr_, bmap, sky, cg = dumps
    mapw = words(bmap)
    cam_x, cam_y = cam
    lv = md.level(level)
    for cy in range(cam_y >> 3, ((cam_y + SCREEN_H - 1) >> 3) + 1):
        for cx in range(cam_x >> 3, ((cam_x + SCREEN_W - 1) >> 3) + 1):
            cs, rs = cx & 63, cy & 31
            e = int(mapw[(1024 if cs >= 32 else 0) + rs * 32 + (cs & 31)])
            t, p, pr = e & 0x3FF, (e >> 10) & 7, (e >> 13) & 1
            data = chr_[t * 32:t * 32 + 32]
            want, wp, wpr = md.cell_tile(level, cx, cy)
            ok = data == want and (p == wp or not any(want)) and pr == wpr and not e & 0xC000
            if not ok:
                errs.append('cell (%d,%d) entry %04x: tile %s pal %d/%d prio %d/%d' % (
                    cx, cy, e, 'ok' if data == want else 'differs', p, wp, pr, wpr))
    # BG2: map and tiles.
    skyw = words(sky)
    ncol = lv['sky_cols'].shape[0]
    for c in range(32):
        for r in range(28):
            e = int(skyw[r * 32 + c])
            if e != int(lv['sky_cols'][c % ncol][r]):
                errs.append('BG2 map (%d,%d) %04x' % (c, r, e))
                break
    nt = len(lv['sky_raw']) // 32
    tiles = sky[0x400 * 2:0x400 * 2 + nt * 32]
    if tiles != lv['sky_raw']:
        errs.append('BG2 tiles differ')
    # CGRAM 16..127:
    pal = md.palettes(level)
    cgw = words(cg)
    for i in range(16, 128):
        if i % 16 == 0:
            continue
        want = pal[i // 16][i % 16]
        got = cgw[i]
        g = np.array([got & 31, (got >> 5) & 31, (got >> 10) & 31]) * 255.0 / 31.0
        if np.abs(g - want).max() > 1:
            errs.append('CGRAM %d %04x' % (i, got))
            break
    # The picture:
    from PIL import Image
    img = np.array(Image.open(io.BytesIO(shot)).convert('RGB')).astype(np.float64)
    if img.shape[0] != SCREEN_H:
        img = img[::img.shape[0] // SCREEN_H, ::img.shape[1] // SCREEN_W]
    exp, _, _ = md.screen(level, cam_x, cam_y)
    d = np.abs(np.round(img * 31 / 255) - np.round(exp * 31 / 255)).max(axis=2)
    bad = int((d > 0).sum())
    return errs, bad, img, exp


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rom', default=os.path.join(ROOT, 'build', 'test_map.sfc'))
    ap.add_argument('--gen', default=os.path.join(ROOT, 'build', 'gen'))
    ap.add_argument('--res', default=os.environ.get('ELMA_RES', os.path.join(ROOT, '..', '..', 'elma.res')))
    ap.add_argument('--levels', default='0,19,33,45,47')
    ap.add_argument('--path', default='sweep;fast')
    ap.add_argument('--every', type=int, default=90)
    ap.add_argument('--out', default=None)
    ap.add_argument('--keep', action='store_true', help='save the pictures of failed checks')
    a = ap.parse_args()
    md = map_ref.MapData(a.gen)
    levs = elmadata.internal_levels(elmadata.Resource(a.res))
    syms = mesen.read_symbols(a.rom)
    plan = []
    for li in [int(x) for x in a.levels.split(',')]:
        w, h = levgeom.size_px(levs[li])
        sx, sy = levs[li].start()
        px, py = levgeom.to_px(levs[li], sx, sy)
        start = clamp_cam(int(px) - 128, int(py) - 112, w, h)
        for p in a.path.split(';'):
            if p == 'sweep':
                cams, checks = path_sweep(w, h, a.every)
            elif p == 'fast':
                cams, checks = path_fast(w, h, seed=li + 1)
            elif p.startswith('ride:'):
                # A ride of the PC game (pcref DUMP): the camera of the game
                # (KIRAJ320.CPP: 2 m + baljobb * 9.33 m left of the bike,
                # the bike in the middle vertically), a check every 120 frames.
                cams, checks = [], []
                for line in open(p[5:]):
                    if line.startswith('#'):
                        continue
                    v = line.split()
                    bx, by, bj = float(v[4]), float(v[5]), float(v[23])
                    px, py = levgeom.to_px(levs[li], bx, by)
                    cams.append(clamp_cam(int(round(px - (2.0 + bj * 28.0 / 3.0) * levgeom.PX_PER_M)),
                                          int(round(py)) - 112, w, h))
                    if len(cams) % 120 == 0:
                        cams += [cams[-1]] * HOLD
                        checks.append(len(cams))
                cams += [cams[-1]] * HOLD
                checks.append(len(cams))
            elif p.startswith('moves:'):
                # moves:dx,dy,n/dx,dy,n... from the start, a check after each
                cams, checks = [], []
                x, y = start
                for m in p[6:].split('/'):
                    dx, dy, k = [int(v) for v in m.split(',')]
                    for _ in range(k):
                        x, y = clamp_cam(x + dx, y + dy, w, h)
                        cams.append((x, y))
                    cams += [(x, y)] * HOLD
                    checks.append(len(cams))
            else:
                cams, checks = [start] * HOLD, [HOLD]
            if p.startswith('ride:') or p in ('sweep', 'fast'):
                start = cams[0]      # loaded where the path starts
            cams = [start] * (LOAD_WAIT + HOLD) + cams
            checks = [LOAD_WAIT + HOLD] + [c + LOAD_WAIT + HOLD for c in checks]
            plan.append((li, cams, checks))
    last = sum(len(c) + 2 for _, c, _ in plan) + 2
    out = a.out or os.path.join(ROOT, 'build', 'map_check')
    os.makedirs(out, exist_ok=True)
    lua = os.path.join(out, 'map_check.lua')
    with open(lua, 'w') as f:
        f.write(make_lua(syms, plan, last))
    p = subprocess.run([mesen.find_mesen(), '--testrunner', os.path.abspath(a.rom), lua],
                       capture_output=True, text=True, timeout=7200)
    stats = []
    dumps = {}
    checks = []
    for line in p.stdout.splitlines():
        if line.startswith('STAT '):
            stats.append([int(v) for v in line.split()[1:]])
        elif line.startswith('OUT '):
            _, kind, name, data = line.split(' ', 3)
            dumps[name] = binascii.unhexlify(data.strip())
            if a.keep:
                with open(os.path.join(out, name), 'wb') as f:
                    f.write(dumps[name])
        elif line.startswith('PROF '):
            pr = [int(v) for v in line.split()[1:]]
            print('parts (master clocks in all): region %d, work %d (decode %d in %d lines, '
                  '%d a line; make %d in %d calls), flush %d' % (
                      pr[0], pr[1], pr[3], pr[4], pr[3] // max(pr[4], 1), pr[5], pr[6], pr[2]))
        elif line.startswith('CHECK '):
            checks.append(line.split()[1:])
        elif line.strip() and 'Uninitialized memory' not in line:
            print(line)
    if p.returncode != 0:
        print(p.stderr[-2000:])
    # The frames of each level (skipping the load frames):
    st = np.array(stats) if stats else np.zeros((0, 11), dtype=np.int64)
    # The frames of the paths (a load takes the frames after it):
    moving = st
    if len(st):
        keep = np.ones(len(st), dtype=bool)
        f = 1
        for _, cams, _ in plan:
            keep &= ~((st[:, 10] >= f) & (st[:, 10] < f + LOAD_WAIT))
            f += len(cams) + 2
        moving = st[keep & (st[:, 1] > 0)]
    nfail = 0
    nbad = 0
    for ck in checks:
        name, mcx, mcy, jobs, s0, s1, resets, h1, v1, h2 = ck[0], *[int(v) for v in ck[1:]]
        if resets:
            print('check %s: %d resets of the map since the load' % (name, resets))
        level = int(name.split('_')[0])
        try:
            d = (dumps['chr_' + name], dumps['map_' + name], dumps['sky_' + name], dumps['cg_' + name])
        except KeyError:
            print('check %s: no dump' % name)
            nfail += 1
            continue
        errs, bad, img, exp = check(md, level, (mcx, mcy), d, dumps['shot_' + name])
        if jobs:
            errs.append('%d jobs left' % jobs)
        if s0 != mcx or ((s1 + 1) & 0xFFFF) != mcy:
            errs.append('scroll %d,%d for camera %d,%d' % (s0, s1, mcx, mcy))
        if h1 != (mcx & 0x3FF) or v1 != ((mcy - 1) & 0x3FF):
            errs.append('PPU scroll %d,%d for camera %d,%d' % (h1, v1, mcx, mcy))
        nbad += bad
        if errs or bad:
            nfail += 1 if errs else 0
            print('check %s at %d,%d: %d errors, %d pixels differ%s' % (
                name, mcx, mcy, len(errs), bad, (': ' + '; '.join(errs[:4])) if errs else ''))
            if a.keep or errs:
                from PIL import Image
                both = np.concatenate([img, exp], axis=1)
                Image.fromarray(np.clip(both, 0, 255).astype(np.uint8)).save(
                    os.path.join(out, 'fail_%s.png' % name))
    print('%d checks, %d failed, %d pixels differed in all' % (len(checks), nfail, nbad))
    if len(moving):
        cpu = moving[:, 1]
        print('map_set_camera: %d frames, master clocks median %d, mean %d, 99%% %d, max %d' % (
            len(cpu), np.median(cpu), cpu.mean(), np.percentile(cpu, 99), cpu.max()))
        print('DMA bytes a frame: mean %.0f, max %d; tiles a frame max %d (edges %d); '
              'jobs left max %d; frames short of budget %d; fewest free tiles %d' % (
                  moving[:, 2].mean(), moving[:, 2].max(), moving[:, 3].max(), moving[:, 4].max(),
                  moving[:, 5].max(), moving[:, 6].max(), moving[:, 7].min() // 2))
    np.save(os.path.join(out, 'stats.npy'), st)
    return 1 if nfail else 0


if __name__ == '__main__':
    sys.exit(main())
