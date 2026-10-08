"""Runs build/test_bike.sfc in Mesen and checks every frame against
test/bikefix.py: the sprites written (OAM 32-127) must be the same, and
the tiles of the bike and the objects in the VRAM must be the pictures the
sprites use. Also measures bike_draw and objects_draw (master clocks) and
the bytes queued for the VRAM.

  bike_test.py [--frames N] [--out DIR]

Run from console/snes after `make build/test_bike.sfc`.
"""

import argparse
import os
import pickle
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))

import numpy as np

import bikefix
import bike_poses
import mesen

ROM = 'build/test_bike.sfc'
GEN = 'build/gen'

LUA = r'''
local A = { __SYMS__ }
local function rd(addr, n)
  local t = {}
  for i = 0, n - 1 do t[#t + 1] = string.format("%02x", emu.read(addr + i, emu.memType.snesMemory)) end
  return table.concat(t)
end
local t0, t1, o0 = 0, 0, 0
local bike, objs = {}, {}
emu.addMemoryCallback(function() t0 = emu.getMasterClock() end, emu.callbackType.exec, A.bike_draw)
emu.addMemoryCallback(function() t1 = emu.getMasterClock() - t0 end, emu.callbackType.exec, A.bike_draw_end)
emu.addMemoryCallback(function() o0 = emu.getMasterClock() end, emu.callbackType.exec, A.objects_draw)
emu.addMemoryCallback(function()
  local o1 = emu.getMasterClock() - o0
  print(string.format("FRAME %s %d %d %s %s %s", rd(A.test_time, 2), t1, o1, rd(A.core_dmaq_n, 2),
    rd(A.core_oam, 544), rd(A.core_dmaq, 8 * 12)))
end, emu.callbackType.exec, A.objects_draw_end)
local vf = { __VFRAMES__ }
local f = 0
emu.addEventCallback(function()
  f = f + 1
  for _, v in ipairs(vf) do
    if f == v then
      local t = {}
      for i = 0x6000 * 2, 0x7000 * 2 - 1 do t[#t + 1] = string.format("%02x", emu.read(i, emu.memType.snesVideoRam)) end
      print(string.format("VRAM %d %s %s", f, rd(A.test_time, 2), table.concat(t)))
    end
  end
end, emu.eventType.endFrame)
'''


def tiles_of(img_idx):
    from gen_bike import tiles16
    return tiles16(img_idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames', type=int, default=0)
    ap.add_argument('--out', default=os.path.join('build', 'bike_test'))
    a = ap.parse_args()
    data = bikefix.Data(GEN)
    syms = mesen.read_symbols(ROM)
    org = bike_poses.origin(os.environ.get('ELMA_RES', '../../elma.res'))
    poses = bike_poses.fixed_poses(org)
    nframes = a.frames or len(poses) * bike_poses.HOLD + 20
    names = ['bike_draw', 'bike_draw_end', 'objects_draw', 'objects_draw_end', 'test_time',
             'core_dmaq_n', 'core_oam', 'core_dmaq']
    lua = LUA.replace('__SYMS__', ', '.join('%s = 0x%06X' % (n, syms[n]) for n in names))
    vframes = list(range(30, nframes, 37))
    lua = lua.replace('__VFRAMES__', ', '.join(str(v) for v in vframes))
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, 'bike_test.lua')
    with open(path, 'w') as f:
        f.write(lua)
    lines = []
    import subprocess
    p = subprocess.run([mesen.find_mesen(), '--testrunner', os.path.abspath(ROM),
                        os.path.abspath(_script(a.out, nframes, path))],
                       capture_output=True, text=True, timeout=900)
    lines = p.stdout.splitlines()
    # The model, frame by frame:
    bike = bikefix.Bike(data)
    objs_def = bike_poses.objects(org, os.environ.get("ELMA_RES", "../../elma.res"))
    objs = bikefix.Objects(data, objs_def, org)
    active = [o[3] for o in objs_def]
    expect = {}
    accs = {}
    t = 0
    for n, pose in enumerate(poses):
        for h in range(bike_poses.HOLD):
            oam, acc, dma = bike.frame(pose)
            ooam, kinds = objs.frame(pose.cam, t, active)
            expect[t] = (oam, ooam, dma, list(bike.cur), list(bike.cur_flip), list(objs.curf))
            accs[t] = acc
            t += 1
    bad = 0
    clocks, oclocks, dmas, kinds, frames_csv = [], [], [], [], []
    states = {}
    for line in lines:
        if not line.startswith('FRAME '):
            continue
        _, tt, c1, c2, qn, oamhex, qhex = line.split()
        tt = int.from_bytes(bytes.fromhex(tt), 'little')
        if tt not in expect:
            continue
        clocks.append(int(c1))
        oclocks.append(int(c2))
        oam = bytes.fromhex(oamhex)
        q = bytes.fromhex(qhex)
        nq = int.from_bytes(bytes.fromhex(qn), 'little') // 8
        qbytes = sum(int.from_bytes(q[i * 8 + 4:i * 8 + 6], 'little') for i in range(min(nq, 12)))
        dmas.append(qbytes)
        ex_oam, ex_ooam, ex_dma, cur, curf, ocur = expect[tt]
        frames_csv.append('%d,%d,%d,%d,%s' % (tt, int(c1), int(c2), ex_dma, ' '.join(str(a) for a in accs[tt])))
        kinds.append(('turn' if poses[tt // bike_poses.HOLD].turn < bikefix.TURN_DONE else
                      'load' if ex_dma else 'calm', int(c1), ex_dma))
        states[tt] = (cur, curf, ocur)
        got = decode(oam, 32, 64)
        want = [(x & 0x1FF, y & 0xFF, tile, attr) for x, y, tile, attr, _, _ in ex_oam]
        want += [(0, 224, None, None)] * (32 - len(want))
        gotb = decode(oam, 64, 128)
        wantb = [(x & 0x1FF, y & 0xFF, tile, attr) for x, y, tile, attr, _, _ in ex_ooam]
        wantb += [(0, 224, None, None)] * (64 - len(wantb))
        for name, g, w in (('bike', got, want), ('objects', gotb, wantb)):
            if not same(g, w):
                bad += 1
                if bad <= 10:
                    print('frame %d (pose %d) %s differ:' % (tt, tt // bike_poses.HOLD, name))
                    for i, (gg, ww) in enumerate(zip(g, w)):
                        if not same([gg], [ww]):
                            print('  sprite %d: got %s want %s' % (i, gg, ww))
    # The VRAM: the tiles the sprites use.
    imgs = data.images
    vbad = 0
    for line in lines:
        if not line.startswith('VRAM '):
            continue
        _, f, tt, vhex = line.split()
        tt = int.from_bytes(bytes.fromhex(tt), 'little') - 1
        if tt not in states:
            continue
        vram = bytes.fromhex(vhex)
        cur, curf, ocur = states[tt]
        for err in check_vram(data, vram, cur, ocur):
            vbad += 1
            if vbad <= 10:
                print('VRAM at frame %d: %s' % (tt, err))
    with open(os.path.join(a.out, 'frames.csv'), 'w') as f:
        f.write('frame,bike_clocks,objects_clocks,bike_bytes,parts_loaded\n' + '\n'.join(frames_csv) + '\n')
    print('frames checked: %d, OAM differences: %d, VRAM differences: %d' % (len(clocks), bad, vbad))
    if clocks:
        print('bike_draw: master clocks typical (median) %d, worst %d' % (sorted(clocks)[len(clocks) // 2], max(clocks)))
        for k in ('calm', 'load', 'turn'):
            c = sorted(x[1] for x in kinds if x[0] == k)
            b = [x[2] for x in kinds if x[0] == k]
            if c:
                print('  %s frames (%d): median %d, worst %d; bike tiles %d..%d bytes' % (
                    k, len(c), c[len(c) // 2], c[-1], min(b), max(b)))
        print('objects_draw: typical %d, worst %d' % (sorted(oclocks)[len(oclocks) // 2], max(oclocks)))
        print('bytes queued a frame: typical %d, worst %d' % (sorted(dmas)[len(dmas) // 2], max(dmas)))
    return 1 if bad or vbad else 0


def _script(out, nframes, lua_path):
    """The Lua of the run: the checks above, stopped after nframes."""
    full = open(lua_path).read() + '\nlocal ff = 0\nemu.addEventCallback(function() ff = ff + 1; if ff >= %d then emu.stop(0) end end, emu.eventType.endFrame)\n' % nframes
    p = os.path.join(out, 'bike_test_run.lua')
    with open(p, 'w') as f:
        f.write(full)
    return p


def decode(oam, first, end):
    out = []
    for n in range(first, end):
        x, y, tile, attr = oam[4 * n:4 * n + 4]
        hi = oam[512 + n // 4] >> (2 * (n % 4)) & 3
        x |= (hi & 1) << 8
        out.append((x, y, tile | (attr & 1) << 8, attr & 0xFE, hi >> 1))
    return out


def same(got, want):
    for g, w in zip(got, want):
        if w[1] == 224 and w[2] is None:
            if g[1] != 224:
                return False
            continue
        if (g[0], g[1], g[2], g[3], g[4]) != (w[0], w[1], w[2], w[3], 0):
            return False
    return True


def check_vram(data, vram, cur, ocur):
    """The tiles of the parts and the objects in the VRAM ($6000-$6FFF)."""
    from gen_bike import tiles16
    errs = []

    def tile_at(n):
        return vram[n * 32:n * 32 + 32]

    def sprite_at(t):
        return tile_at(t) + tile_at(t + 1) + tile_at(t + 16) + tile_at(t + 17)
    imgs = data.images
    for p in range(11):
        if cur[p] is None:
            continue
        if p == 10:
            base = sum(len(x) for x in data.frame[:cur[p]])
            for i in range(len(data.frame[cur[p]])):
                if sprite_at(164 + 2 * i) != tiles16(imgs['frame'][base + i]):
                    errs.append('the body, sprite %d' % i)
        else:
            t = (128 + 2 * p) if p < 8 else (160 + 2 * (p - 8))
            if sprite_at(t) != tiles16(imgs['single'][cur[p]]):
                errs.append('part %d' % p)
    for k, f in enumerate(ocur):
        if f is None:
            continue
        if sprite_at(192 + 2 * k) != tiles16(imgs['obj'][k][f]):
            errs.append('object kind %d' % k)
    return errs


if __name__ == '__main__':
    sys.exit(main())
