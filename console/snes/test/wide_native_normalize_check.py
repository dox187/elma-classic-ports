#!/usr/bin/env python3
"""Check exact rounded/floor unsigned32 middle products for normalization."""
import argparse
import json
import os
from pathlib import Path
import random
import re

import mesen
import physrom
import wide_native_math_check as common
from wide_normalize_probe import SEEDS, rounded_shift


def vectors():
    edge=[0,1,0x7fff,0x8000,0xffff,0x10000,0x7fffffff,0x80000000,0xffffffff]
    pairs=[(a,b) for a in edge for b in edge]
    rng=random.Random(6812)
    pairs += [(rng.getrandbits(32),rng.getrandbits(32)) for _ in range(1200)]
    cases=[]
    for a,b in pairs:
        product=a*b
        guard=(product>>31)&1
        for nearest in (0,1):
            output=(product>>32)+(guard if nearest else 0)
            cases.append((a,b,nearest,guard,output | (0x1234567<<32)))
    return cases


def nr_vectors():
    unit=1<<32
    pairs=[(m,r) for m in (0,unit,unit+1,2*unit,3*unit,4*unit-1,4*unit)
                    for r in (0,unit//2,unit//2+1,unit-1,unit,unit+1)]
    rng=random.Random(913883)
    for _ in range(1500):
        m=rng.randrange(unit,4*unit)
        index=min(255,((m-unit)*256)//(3*unit))
        r=SEEDS[index]<<8
        square=rounded_shift(r*r,16)
        term=(3<<16)-rounded_shift(rounded_shift(m,16)*square,16)
        r=rounded_shift(r*term,17)<<16
        pairs.append((m,r))
    cases=[]
    for m,r in pairs:
        square=rounded_shift(r*r,32)
        term=3*unit-rounded_shift(m*square,32)
        status=0 if unit<=m<4*unit and unit//2<=r<=unit and term>=0 else 2
        output=rounded_shift(r*term,33) if status==0 else 0
        cases.append((m,r,0,status,output))
    return cases


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=Path('build/wide-native-normalize-mul32'))
    p.add_argument('--gen',type=Path,default=Path('build/gen'))
    p.add_argument('--link',type=Path,default=Path('build/test_phys.sfc.link'))
    p.add_argument('--pvs')
    p.add_argument('--physdump',default='build/host/physdump')
    p.add_argument('--cases',default='test/physcases.txt')
    p.add_argument('--latch-stress',action='store_true')
    p.add_argument('--negative-control',action='store_true')
    p.add_argument('--kernel',choices=('mul32','nr32'),default='mul32')
    args=p.parse_args();os.chdir(common.ROOT)
    args.operation='mul';args.source_include='wide_native_normalize.asm'
    args.function_name='wide_mul32_shift32' if args.kernel=='mul32' else 'wide_nr32'
    rom=common.build(args);s=mesen.read_symbols(str(rom));original=mesen.run
    start=s[args.function_name]
    end=s['wide_mul32_core_end'] if args.kernel=='mul32' else s['wide_nr32_core_end']
    addresses=[a for a in common.latch_sites(rom,s['core_m7_latch'])
               if start<=a<end] if args.latch_stress or args.negative_control else []
    original_vectors=common.vectors
    common.vectors=lambda _: vectors() if args.kernel=='mul32' else nr_vectors()
    def run(r,script,o,*a,**kw):
        steps=(Path(o)/'host_log.bin').stat().st_size//6
        text=common.instrument(s,steps,'mul',addresses,not args.negative_control)
        core_begin=s['wide_mul32_core_begin' if args.kernel=='mul32' else 'wide_nr32_core_begin']
        core_end=s['wide_mul32_core_end' if args.kernel=='mul32' else 'wide_nr32_core_end']
        text=text.replace('local times={q0={},q40={},q44={},q48={},overflow={},domain={}}',
                          'local times={q0={},q40={},q44={},q48={},overflow={},domain={},core={},entry={},exit={}}')
        text=text.replace('start=emu.getMasterClock()', 'start=emu.getMasterClock()')
        # Insert before the final reporting callback so its core/entry/exit totals
        # include the last arithmetic operation too.
        text=text.replace('local bad=0','local core_start=0\nlocal core_end_clock=0\nlocal bad=0')
        text=text.replace('local t=times[k] t[#t+1]=emu.getMasterClock()-start',
                          'local t=times[k] t[#t+1]=emu.getMasterClock()-start\n'
                          ' times.exit[#times.exit+1]=emu.getMasterClock()-core_end_clock')
        text+='''
emu.addMemoryCallback(function()
 core_start=emu.getMasterClock()
 times.entry[#times.entry+1]=core_start-start
end,emu.callbackType.exec,%d,%d)
emu.addMemoryCallback(function()
 core_end_clock=emu.getMasterClock()
 times.core[#times.core+1]=core_end_clock-core_start
end,emu.callbackType.exec,%d,%d)
'''%(core_begin,core_begin,core_end,core_end)
        if args.kernel=='mul32':
            text=text.replace('local times={q0={},q40={},q44={},q48={},overflow={},domain={},core={},entry={},exit={}}',
                              'local times={floor={},nearest={},overflow={},domain={},core={},entry={},exit={}}')
            text=text.replace('c[4]==0 and c[5] or 0x123456789abcdef','c[5]')
            text=text.replace('local k=c[4]==2 and "domain" or (c[4]==1 and "overflow" or "q"..c[3])',
                              'local k=c[3]==0 and "floor" or "nearest"')
        groups={}
        for name,address in s.items():
            match=re.fullmatch(r'wnm_(product_ll|product_lh|product_hl|product_hh|matrix_sum|matrix_end)(.*)',name)
            if match:groups.setdefault(match[2],{})[match[1]]=address
        text+='\nlocal phase_start={}\n'
        order=('product_ll','product_lh','product_hl','product_hh','matrix_sum','matrix_end')
        for group in groups.values():
            for first,last in zip(order,order[1:]):
                if first not in group or last not in group:continue
                phase_begin,phase_end=group[first],group[last]
                key='phase_'+first
                text+='''
times["%s"]=times["%s"] or {}
emu.addMemoryCallback(function() phase_start[%d]=emu.getMasterClock() end,emu.callbackType.exec,%d,%d)
emu.addMemoryCallback(function()
 if phase_start[%d] then
  local t=times["%s"] t[#t+1]=emu.getMasterClock()-phase_start[%d]
  phase_start[%d]=nil
 end
end,emu.callbackType.exec,%d,%d)
'''%(key,key,phase_begin,phase_begin,phase_begin,phase_begin,key,phase_begin,phase_begin,phase_end,phase_end)
        lua=Path(kw['lua']);lua.write_text(lua.read_text()+text)
        return original(r,script,o,*a,**kw)
    mesen.run=run
    try:ok=physrom.run(argparse.Namespace(rom=str(rom),physdump=args.physdump,gen=str(args.gen),cases=args.cases,full=12,full_from=0,out=str(args.out/'check')))
    finally:mesen.run=original;common.vectors=original_vectors
    report=json.loads((args.out/'check/math-results.json').read_text())
    report.update(physics_unchanged=bool(ok),latch_sites=len(addresses),negative_control=args.negative_control,
                  clock_scope='Full compiled C forwarding call including copies/save/restore/args/cleanup',
                  ppu_partial_products=8 if args.kernel=='mul32' else '14 for Q16-expanded input;24 general',kernel=args.kernel)
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    good=report['failures']>0 if args.negative_control else report['failures']==0
    return 0 if ok and good and (not addresses or report['latch_injections']>0) else 1
if __name__=='__main__':raise SystemExit(main())
