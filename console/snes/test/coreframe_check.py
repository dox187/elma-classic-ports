"""Regress shared raster deadlines across missed NMIs and DMA caller ABI.

The real NMI/frame loop advances between work_begin and work_over. Only the
PPU raster read is controlled, so boundary checks are deterministic in either
TV region. DMA checks call the production routine with a nonzero direct page.
"""
import argparse
import contextlib
import io
import json
from pathlib import Path
import struct

import mesen


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rom', default='build/test_render.sfc')
    ap.add_argument('--out', default='build/coreframe')
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    s = mesen.read_symbols(a.rom)
    tests = [('early_after_missed_nmi', 7, 10, 42, 1, 0, 0, 0),
             ('reserve_inside', 7, 182, 42, 1, 0, 0, 0),
             ('reserve_boundary', 7, 183, 42, 1, 0, 0, 1),
             ('near_deadline', 7, 224, 1, 1, 0, 0, 1),
             ('vblank_225', 7, 225, 42, 1, 0, 0, 0),
             ('vblank_pal', 7, 300, 42, 1, 0, 0, 0),
             ('disabled', 7, 224, 42, 0, 0, 0, 0)]
    for name, entries, payload in [('empty', 0, 0), ('partial', 3, 1234),
                                    ('exact_budget', 5, 4520), ('over_budget', 8, 4999)]:
        tests.append(('dma_' + name, 8, 10, 0x1000, 1, entries, payload,
                      max(0, 5000 - entries * 96 - payload)))
    lua = [r'''
local m=emu.memType.snesMemory
local tests={}
local frame,index,phase,wait,vcounter=0,1,0,0,0
local raster=10
''']
    for t in tests:
        lua.append('tests[#tests+1]={%r,%s}' % (t[0], ','.join(str(v) for v in t[1:])))
    lua.append(r'''
emu.addMemoryCallback(function()
 vcounter=1-vcounter
 if vcounter==1 then return raster%%256 else return math.floor(raster/256) end
end,emu.callbackType.read,0x213d,0x213d)
emu.addMemoryCallback(function()
 local t=tests[index]
 if not t then return end
 emu.write(%(active)d,t[5],m)
 local stale=emu.read16(%(work_frame)d,m)
 local now=emu.read16(%(frame_count)d,m)
 out("PEEK",t[1].."_before",string.char(stale%%256,math.floor(stale/256),now%%256,math.floor(now/256)))
end,emu.callbackType.exec,%(over)d,%(over)d)
emu.addMemoryCallback(function()
 local t=tests[index]
 if not t then return end
 emu.write16(%(queue_n)d,t[6]*8,m)
 emu.write16(%(queue_bytes)d,t[7],m)
 local stale=emu.read16(%(work_frame)d,m)
 local now=emu.read16(%(frame_count)d,m)
 out("PEEK",t[1].."_before",string.char(stale%%256,math.floor(stale/256),now%%256,math.floor(now/256)))
end,emu.callbackType.exec,%(dma_wrapper)d,%(dma_wrapper)d)
emu.addEventCallback(function()
 frame=frame+1
 if frame<120 or index>#tests then return end
 local t=tests[index]
 if phase==0 then
  emu.write16(%(done)d,0,m)
  emu.write16(%(go)d,6,m)
  phase=1 return
 end
 if phase==1 then
  if emu.read16(%(done)d,m)==0 then return end
  wait=frame+3 phase=2 return
 end
 if phase==2 then
  if frame<wait then return end
  raster=t[3] vcounter=0
  emu.write16(%(alpha)d,t[4],m)
  emu.write16(%(done)d,0,m)
  emu.write16(%(go)d,t[2],m)
  phase=3 return
 end
 if phase==3 then
  if emu.read16(%(done)d,m)==0 then return end
  dump("PEEK",t[1].."_result",m,%(result)d,2)
  dump("PEEK",t[1].."_value",m,%(value)d,2)
  dump("PEEK",t[1].."_d",m,%(direct_page)d,2)
  dump("PEEK",t[1].."_frame",m,%(work_frame)d,2)
  emu.write16(%(queue_n)d,0,m)
  emu.write16(%(queue_bytes)d,0,m)
  index=index+1 phase=0
 end
end,emu.eventType.endFrame)
''' % {'done': s['render_test_done'], 'go': s['render_test_go'],
       'work_frame': s['core_work_frame'], 'frame_count': s['core_frame_count'],
       'active': s['core_work_active'], 'queue_n': s['core_dmaq_n'],
       'queue_bytes': s['core_dmaq_bytes'], 'alpha': s['render_test_alpha'],
       'result': s['render_test_result'], 'value': s['render_test_value'],
       'direct_page': s['render_test_d'], 'over': s['core_work_over'],
       'dma_wrapper': s['render_test_dma_left']})
    path = out / 'check.lua'
    path.write_text('\n'.join(lua))
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        rows = mesen.run(a.rom, 'W260', str(out), lua=str(path))
    (out / 'raw.txt').write_text(log.getvalue())
    data = {name: value for kind, name, value in rows if kind == 'PEEK'}
    results = []
    for name, command, raster, alpha, active, entries, payload, expected in tests:
        def word(suffix):
            b = data.get(name + suffix)
            return struct.unpack('<H', b)[0] if b is not None else None
        before = data.get(name + '_before')
        previous, current = struct.unpack('<HH', before) if before is not None else (None, None)
        checks = {'returned': word('_result') == expected,
                  'actual_nmi_advanced': previous is not None and previous != current}
        if command == 7 and active:
            checks['deadline_resynchronized'] = word('_frame') == current
        if command == 8:
            checks['accumulator_return'] = word('_value') == expected
            checks['direct_page_preserved'] = word('_d') == alpha
        bad = [n for n, ok in checks.items() if not ok]
        results.append({'case': name, 'ok': not bad, 'failures': bad,
                        'returned': word('_result'), 'expected': expected,
                        'work_frame_before': previous, 'current_frame': current,
                        'work_frame_after': word('_frame')})
        print(name + ': ' + ('FAIL ' + ', '.join(bad) if bad else 'OK'))
    report = {'ok': all(r['ok'] for r in results), 'cases': results}
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
