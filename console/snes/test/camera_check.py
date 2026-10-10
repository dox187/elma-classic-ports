"""Verify the real SNES centered camera against independent integer math.

Uses test_render.sfc command 5. Checks all level origins, fixed-point pixel
boundaries, full 24-bit conversion range and legacy truncation outside it.
"""
import argparse
import contextlib
import io
import os
from pathlib import Path
import struct
import sys

import mesen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
import elmadata
import levgeom


VIEW_SUFFIX = bytes((i * 19 + 7) & 255 for i in range(44))


def camera(level, body):
    ox, oy = levgeom.origin(level)

    def px(distance):
        return (((distance & 0xFFFFFF) >> 8) * 4915) >> 16
    return ((px(body[0] - ox) - 128) & 0xFFFF,
            (px(oy - body[1]) - 112) & 0xFFFF)


def cases(levels):
    out = []
    for i, level in enumerate(levels):
        ox, oy = levgeom.origin(level)
        out += [('origin_%02d' % i, i, (ox, oy)),
                ('offset_%02d' % i, i, (ox + 0x123456, oy - 0x234567))]
    ox, oy = levgeom.origin(levels[0])
    # Tiny distances, byte/word carries, sign/high-byte limits and ignored
    # high bits reproduce the previous game_px ABI, rather than clamping.
    ds = (-16777217, -16777216, -65537, -65536, -257, -256, -1,
          0, 1, 255, 256, 257, 65535, 65536, 65537,
          8388607, 8388608, 16777214, 16777215, 16777216, 16777217)
    for n, d in enumerate(ds):
        out.append(('boundary_%02d' % n, 0, (ox + d, oy - ds[-n - 1])))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rom', default='build/test_render.sfc')
    ap.add_argument('--res', default=os.environ.get('ELMA_RES', '../../elma.res'))
    ap.add_argument('--out', default='build/camera-check')
    a = ap.parse_args()
    levels = elmadata.internal_levels(elmadata.Resource(a.res))
    tests = cases(levels)
    s = mesen.read_symbols(a.rom)
    lua = [r'''
local memory = emu.memType.snesMemory
local function write_bytes(addr, hex)
 for i=1,#hex,2 do emu.write(addr+(i-1)/2,tonumber(hex:sub(i,i+1),16),memory) end
end
local tests, clocks = {}, {}
local index, waiting, t0, dt = 1, false, 0, 0
''']
    for name, level, body in tests:
        lua.append('tests[#tests+1]={%r,%d,%r}' %
                   (name, level, (struct.pack('<ii', *body) + VIEW_SUFFIX).hex()))
    lua.append('''
emu.addMemoryCallback(function() t0=emu.getMasterClock() end,emu.callbackType.exec,%(camera)d)
emu.addMemoryCallback(function() dt=emu.getMasterClock()-t0 end,emu.callbackType.exec,%(end)d)
local f=0
emu.addEventCallback(function()
 f=f+1
 if f<120 then return end
 if waiting then
  if emu.read16(%(done)d,memory)==0 then return end
  local name=tests[index][1]
  dump("PEEK",name.."_camera",memory,%(x)d,4)
  dump("PEEK",name.."_view",memory,%(view)d,52)
  clocks[#clocks+1]=tostring(dt)
  index=index+1 waiting=false
 end
 if index>#tests then
  out("STAT","camera_clocks.txt",table.concat(clocks,"\\n"))
  return
 end
 local t=tests[index]
 write_bytes(%(view)d,t[3])
 emu.write16(%(alpha)d,t[2],memory)
 emu.write16(%(done)d,0,memory)
 emu.write16(%(go)d,5,memory)
 waiting=true
end,emu.eventType.endFrame)
''' % {'camera': s['game_camera'], 'end': s['game_camera_end'],
       'done': s['render_test_done'], 'x': s['game_cam_x'], 'view': s['phys_view'],
       'alpha': s['render_test_alpha'], 'go': s['render_test_go']})
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / 'camera_check.lua'
    path.write_text('\n'.join(lua))
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        results = mesen.run(a.rom, 'W%d' % (125 + len(tests) * 3), str(out), lua=str(path))
    (out / 'raw.txt').write_text(log.getvalue())
    got = {name: data for kind, name, data in results if kind == 'PEEK'}
    failures = []
    for name, level, body in tests:
        want = struct.pack('<HH', *camera(levels[level], body))
        if got.get(name + '_camera') != want:
            failures.append(name + ': camera differs')
        if got.get(name + '_view') != struct.pack('<ii', *body) + VIEW_SUFFIX:
            failures.append(name + ': view was changed')
    for failure in failures:
        print(failure)
    print('%d camera cases, %d differences' % (len(tests), len(failures)))
    stats = [data for kind, _, data in results if kind == 'STAT']
    if stats:
        clocks = list(map(int, stats[-1].decode().split()))
        print('game_camera: median %d, worst %d master clocks' %
              (sorted(clocks)[len(clocks) // 2], max(clocks)))
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
