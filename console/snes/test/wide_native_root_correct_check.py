#!/usr/bin/env python3
"""Native residual-correction cost and exact independent integer oracle."""
import argparse
import json
import math
import os
from pathlib import Path
import random

import mesen
import physrom
import wide_native_math_check as common
from wide_normalize_probe import estimate, rounded_shift


def vectors():
    cases=[(0,0,256,2,0),(1,0,256,2,0),(255,0,256,2,0),
           (256,-65536,256,2,0),(1<<48,0,256,2,0),
           (1<<40,0,257,2,0),(1<<40,0,65535,2,0)]
    for q in (1<<38,(1<<40)+1,(1<<44)-1,(1<<47)-257):
        for rem in (0,q//2,q,2*q):
            target=q*q+rem
            for delta in (-257,-256,-64,-8,-2,-1,0,1,2,8,64,256,257):
                guess=q+delta
                for budget in (0,1,8,256):
                    status=0 if abs(delta)<=budget else 2
                    nearest=q+int(rem>q)
                    residue=target-nearest*nearest
                    nearest+=int(residue>=0 and 2*residue>=nearest)
                    cases.append((guess,target-guess*guess,budget,status,nearest))
    rng=random.Random(135313)
    for _ in range(1500):
        unit=1<<44
        x=rng.randrange(-unit//2,unit//2);y=rng.randrange(-unit//2,unit//2)
        if x*x+y*y<(unit//64)**2:continue
        target=(rounded_shift(x*x,44)+rounded_shift(y*y,44))<<44
        guess,_,_=estimate(target,{},40)
        nearest=math.isqrt(target)
        nearest+=int(target-nearest*nearest>nearest)
        residue=target-nearest*nearest
        nearest+=int(residue>=0 and 2*residue>=nearest)
        cases.append((guess,target-guess*guess,256,0,nearest))
    return cases


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=Path('build/wide-native-root-correct'))
    p.add_argument('--gen',type=Path,default=Path('build/gen'))
    p.add_argument('--link',type=Path,default=Path('build/test_phys.sfc.link'))
    p.add_argument('--pvs')
    p.add_argument('--physdump',default='build/host/physdump')
    p.add_argument('--cases',default='test/physcases.txt')
    args=p.parse_args();os.chdir(common.ROOT)
    args.operation='mul';args.source_include='wide_native_root_correct.asm'
    args.function_name='wide_root_correct'
    rom=common.build(args);s=mesen.read_symbols(str(rom));original=mesen.run
    original_vectors=common.vectors;common.vectors=lambda _:vectors()
    def run(r,script,o,*call_args,**kw):
        steps=(Path(o)/'host_log.bin').stat().st_size//6
        text=common.instrument(s,steps,'mul')
        text=text.replace('local times={q0={},q40={},q44={},q48={},overflow={},domain={}}',
                          'local times={q0={},q40={},q44={},q48={},overflow={},domain={},core={},entry={},exit={}}')
        text=text.replace('local bad=0','local core_start=0\nlocal core_end_clock=0\nlocal bad=0')
        text=text.replace('local t=times[k] t[#t+1]=emu.getMasterClock()-start',
                          'local t=times[k] t[#t+1]=emu.getMasterClock()-start\n'
                          ' times.exit[#times.exit+1]=emu.getMasterClock()-core_end_clock')
        text=text.replace('local k=c[4]==2 and "domain" or (c[4]==1 and "overflow" or "q"..c[3])',
                          'local k=c[4]==2 and "fallback" or "delta"..math.abs(c[5]-c[1])\n times[k]=times[k] or {}')
        text+='''
emu.addMemoryCallback(function()
 core_start=emu.getMasterClock()
 times.entry[#times.entry+1]=core_start-start
end,emu.callbackType.exec,%d,%d)
emu.addMemoryCallback(function()
 core_end_clock=emu.getMasterClock()
 times.core[#times.core+1]=core_end_clock-core_start
end,emu.callbackType.exec,%d,%d)
'''%(s['wide_root_correct_core_begin'],s['wide_root_correct_core_begin'],
     s['wide_root_correct_core_end'],s['wide_root_correct_core_end'])
        lua=Path(kw['lua']);lua.write_text(lua.read_text()+text)
        return original(r,script,o,*call_args,**kw)
    mesen.run=run
    try:ok=physrom.run(argparse.Namespace(rom=str(rom),physdump=args.physdump,gen=str(args.gen),cases=args.cases,full=12,full_from=0,out=str(args.out/'check')))
    finally:mesen.run=original;common.vectors=original_vectors
    report=json.loads((args.out/'check/math-results.json').read_text())
    report.update(physics_unchanged=bool(ok),clock_scope='Full compiled C call including input/output copies and save/restore',
                  ppu_products=0,contract='Exact N-estimate^2 residual; 256<=estimate<2^48, limit<=256; unchanged output on fallback')
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return int(not ok or bool(report['failures']))
if __name__=='__main__':raise SystemExit(main())
