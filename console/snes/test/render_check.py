"""Check real SNES interpolation against independent integer mathematics.

  python test/render_check.py --rom build/test_render.sfc --out build/render

Exercises every packed view field, signed position rounding, shortest wrapped
angle arcs, alpha endpoints/high-bit correction, teleports and discrete flags.
Also verifies view restoration, reset/capture and untouched solver state.
"""
import argparse
import contextlib
import io
import json
from pathlib import Path
import struct
import sys

import mesen

POSITIONS = [0, 4, 12, 16, 20, 24, 32, 36, 40, 44]
ANGLES = [8, 28, 30]
SIZE = 52


def view(positions, angles, turned=0, gravity=1):
    data = bytearray(SIZE)
    for offset, value in zip(POSITIONS, positions):
        struct.pack_into('<i', data, offset, value)
    for offset, value in zip(ANGLES, angles):
        struct.pack_into('<H', data, offset, value)
    data[48:50] = bytes([turned, gravity])
    return bytes(data)


def reference(prev, current, alpha):
    out = bytearray(current)
    if alpha >= 256 or prev[48:50] != current[48:50]:
        return bytes(out)
    for offset in POSITIONS:
        p = struct.unpack_from('<i', prev, offset)[0]
        c = struct.unpack_from('<i', current, offset)[0]
        delta = c - p
        # Positions that cannot fit delta>>8 in a signed multiplier bypass
        # interpolation. Arithmetic shifts round negative values down.
        if -(1 << 23) <= delta < (1 << 23):
            base = p if alpha < 128 else c
            weight = alpha if alpha < 128 else alpha - 256
            struct.pack_into('<i', out, offset, base + (delta // 256) * weight)
    for offset in ANGLES:
        p = struct.unpack_from('<H', prev, offset)[0]
        c = struct.unpack_from('<H', current, offset)[0]
        delta = ((c - p + 32768) % 65536) - 32768
        struct.pack_into('<H', out, offset, (p + delta * alpha // 256) % 65536)
    return bytes(out)


def cases():
    previous = view([100000, -100000, 0, -1, 65536, -65536, 222222, -333333, 777777, -999999],
                    [65000, 400, 40000])
    current = view([165791, -165791, -257, 256, -65536, 65536, 222478, -333077, 777522, -999999],
                   [200, 65000, 10000])
    out = [(f'alpha_{alpha}', 1, previous, current, alpha) for alpha in (0, 64, 128, 255, 256)]
    # Both signed multiplier boundaries, immediately inside/outside, plus
    # exact and neighboring half-turns (tie chooses the signed negative arc).
    p = view([0] * 10, [0, 32768, 65535])
    c = view([8388607, 8388608, -8388608, -8388609, 1, -1, 255, -255, 256, -256],
             [32768, 0, 32766])
    out += [(f'boundaries_{alpha}', 1, p, c, alpha) for alpha in (0, 64, 128, 255, 256)]
    out += [(f'turn_{alpha}', 1, previous,
             view([500000] * 10, [30000] * 3, 1, 1), alpha) for alpha in (0, 128, 255)]
    out += [(f'gravity_{alpha}', 1, previous,
             view([-500000] * 10, [30000] * 3, 0, 3), alpha) for alpha in (0, 128, 255)]
    out += [('reset', 2, previous, current, 0), ('capture', 3, previous, current, 0),
            ('previous', 4, previous, current, 0)]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rom', default='build/test_render.sfc')
    ap.add_argument('--out', default='build/render')
    a = ap.parse_args()
    s = mesen.read_symbols(a.rom)
    tests = cases()
    solver = bytes((i * 37 + 19) % 256 for i in range(142))
    lua = [r'''
local memory = emu.memType.snesMemory
local function write_bytes(addr, hex)
 for i=1,#hex,2 do emu.write(addr+(i-1)/2,tonumber(hex:sub(i,i+1),16),memory) end
end
local tests = {}
local index, waiting = 1, false
''']
    for name, command, prev, current, alpha in tests:
        lua.append('tests[#tests+1]={%r,%d,%r,%r,%d}' % (name, command, prev.hex(), current.hex(), alpha))
    lua.append('''
emu.addEventCallback(function()
 if frame_count == nil then frame_count=0 end
 frame_count=frame_count+1
 if frame_count<120 then return end
 if waiting then
  if emu.read16(%(done)d,memory)==0 then return end
  local name=tests[index][1]
  dump("PEEK",name.."_view",memory,%(view)d,52)
  dump("PEEK",name.."_restored",memory,%(restored)d,52)
  dump("PEEK",name.."_solver",memory,%(solver)d,142)
  dump("PEEK",name.."_prev",memory,%(prev)d,52)
  dump("PEEK",name.."_current",memory,%(current)d,52)
  index=index+1 waiting=false
 end
 if index>#tests then return end
 local t=tests[index]
 write_bytes(%(prev)d,t[3])
 write_bytes(%(current)d,t[3])
 write_bytes(%(physical_view)d,t[4])
 write_bytes(%(solver)d,%(solver_hex)r)
 emu.write16(%(alpha)d,t[5],memory)
 emu.write16(%(done)d,0,memory)
 emu.write16(%(go)d,t[2],memory)
 waiting=true
end,emu.eventType.endFrame)
''' % {'done': s['render_test_done'], 'view': s['render_test_view'],
       'restored': s['render_test_restored'], 'solver': s['phys_dpa'],
       'prev': s['render_prev'], 'current': s['render_current'],
       'physical_view': s['phys_view'], 'solver_hex': solver.hex(),
       'alpha': s['render_test_alpha'], 'go': s['render_test_go']})
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    source = '\n'.join(lua)
    (out / 'check.lua').write_text(source)
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        rows = mesen.run(a.rom, 'W240', str(out), lua=str(out / 'check.lua'))
    (out / 'raw.txt').write_text(log.getvalue())
    data = {name: value for kind, name, value in rows if kind == 'PEEK'}
    failures = []
    for name, command, prev, current, alpha in tests:
        actual = data.get(name + '_view')
        checks = {'complete': actual is not None,
                  'solver_unchanged': data.get(name + '_solver') == solver}
        if command == 1:
            expected = reference(prev, current, alpha)
            checks.update(interpolation=actual == expected,
                          restored=data.get(name + '_restored') == current,
                          previous_unchanged=data.get(name + '_prev') == prev,
                          current_snapshot=data.get(name + '_current') == current)
        elif command == 2:
            checks.update(view_unchanged=actual == current,
                          reset_previous=data.get(name + '_prev') == current,
                          reset_current=data.get(name + '_current') == current)
        elif command == 4:
            checks.update(previous_snapshot=data.get(name + '_prev') == current,
                          current_unchanged=data.get(name + '_current') == prev,
                          view_unchanged=actual == current,
                          restored=data.get(name + '_restored') == current)
        else:
            checks.update(capture_previous=data.get(name + '_prev') == actual,
                          capture_restored=data.get(name + '_restored') == actual)
        bad = [k for k, ok in checks.items() if not ok]
        if bad:
            failures.append({'case': name, 'failed': bad,
                             'actual': actual.hex() if actual else None,
                             'expected': expected.hex() if command == 1 else None})
        print(name + ': ' + ('FAIL ' + ', '.join(bad) if bad else 'OK'))
    report = {'cases': len(tests), 'ok': not failures, 'failures': failures}
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
