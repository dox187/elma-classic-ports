#!/usr/bin/env python3
"""Private raw64 arithmetic ROM: independent integer oracle and unchanged ASM/C physics."""
import argparse
import json
import math
import os
from pathlib import Path
import random
import subprocess

import mesen
import physrom
from m7_latch_check import sites as latch_sites
from wide_force_check import ROOT, toolchain


def build(args):
    out=args.out
    out.mkdir(parents=True,exist_ok=True)
    include=getattr(args,'source_include','wide_native_math.asm')
    src=Path('src/phys.asm').read_text().replace('.include "phys.inc"', '.include "phys.inc"\n.include "'+include+'"',1)
    src=src.replace('phys_step:\n','phys_step:\n jsl wide_math_probe\n',1)
    src+='''
.BASE $00
.RAMSECTION ".wide_math_probe_buffers" BANK $7E SLOT 2
wide_math_buffers dsb 32
.ENDS
.RAMSECTION ".wide_math_probe_args" BANK 0 SLOT 1
wide_math_fraction dsb 2
.ENDS
.BASE $80
.SECTION ".wide_math_probe_text" SUPERFREE
wide_math_probe:
 php
 rep #$30
 pha
 phx
 phy
 phb
 phd
wide_math_call_begin:
 jsl wide_math_c_call
wide_math_call_end:
 pld
 plb
 ply
 plx
 pla
 plp
 rtl
.ENDS
'''
    (out/'probe.asm').write_text(src)
    bins=toolchain(args.pvs);dev=bins.parent
    subprocess.run([str(bins/'wla-65816'),'-h','-s','-x','-I'+str(args.gen),'-Isrc','-Itest','-o',str(out/'probe.obj'),str(out/'probe.asm')],check=True)
    call='''typedef unsigned short u16;
extern u16 wide_math_buffers[];
extern u16 wide_math_fraction;
void wide_mul64(const u16*,const u16*,u16,u16*,u16*);
void wide_math_c_call(void) {
 wide_mul64(wide_math_buffers,wide_math_buffers+4,wide_math_fraction,
            wide_math_buffers+8,wide_math_buffers+12);
}
'''
    if args.operation == 'div':
        call=call.replace('wide_mul64','wide_div64')
    elif args.operation == 'sqrt':
        call=call.replace('void wide_mul64(const u16*,const u16*,u16,u16*,u16*);',
                          'void wide_sqrt64(const u16*,u16,u16*,u16*);')
        call=call.replace('wide_mul64(wide_math_buffers,wide_math_buffers+4,wide_math_fraction,',
                          'wide_sqrt64(wide_math_buffers,wide_math_fraction,')
    call=call.replace('wide_mul64',getattr(args,'function_name','wide_mul64'))
    (out/'call.c').write_text(call)
    subprocess.run([str(bins/'816-tcc'),'-Wall','-F','-Isrc','-I'+str(args.gen),'-I'+str(dev.parent/'pvsneslib/include'),'-I'+str(dev/'include'),'-c',str(out/'call.c'),'-o',str(out/'call.ps')],check=True)
    subprocess.run([str(dev/'tools/816-opt'),'-i',str(out/'call.ps'),'-o',str(out/'call.s')],check=True)
    subprocess.run([str(bins/'wla-65816'),'-d','-s','-x','-I'+str(args.gen),'-Isrc','-o',str(out/'call.obj'),str(out/'call.s')],check=True)
    manifest=args.link.read_text().splitlines()
    assert manifest.count('build/obj/phys.obj')==1
    manifest[manifest.index('build/obj/phys.obj')]=str(out/'probe.obj')
    manifest.append(str(out/'call.obj'))
    (out/'probe.link').write_text('\n'.join(manifest)+'\n')
    with (out/'link.log').open('w') as log:
        subprocess.run([str(bins/'wlalink'),'-d','-S','-A','-c',str(out/'probe.link'),str(out/'probe.sfc')],stdout=log,stderr=log,check=True)
    return out/'probe.sfc'


def vectors(operation):
    edge=[-(1<<63),(1<<63)-1,-1,0,1,-(1<<40),1<<40,-(1<<44),1<<44,(1<<32)-1,-(1<<32)+1]
    cases=[(a,b,f) for a in edge for b in edge for f in (0,40,44,48)]
    rng=random.Random(9135)
    for _ in range(1200):
        cases.append((rng.randrange(-(1<<rng.randrange(1,64)),1<<rng.randrange(1,64)),rng.randrange(-(1<<rng.randrange(1,64)),1<<rng.randrange(1,64)),rng.choice((0,40,44,48))))
    cases += [(a,b,3) for a,b,_ in cases[:30]]
    rows=[]
    for a,b,f in cases:
        domain=f not in (0,40,44,48)
        q=0
        if operation == 'mul':
            n=a*b
            q=((abs(n)+(1<<(f-1)))>>f)*(-1 if n<0 else 1) if f else n
        elif operation == 'div':
            domain=domain or b==0
            if not domain:
                n=abs(a)<<f
                q,r=divmod(n,abs(b))
                q += int(2*r >= abs(b))
                if (a<0)!=(b<0): q=-q
        else:
            domain=domain or a<0
            if not domain:
                n=a<<f
                q=math.isqrt(n)
                if n-q*q>q: q+=1
        status=2 if domain else int(not -(1<<63)<=q<(1<<63))
        rows.append((a,b,f,status,q))
    return rows


def instrument(sym,steps,operation,addresses=(),restore=True):
    mask=(1<<64)-1
    cases=','.join('{0x%x,0x%x,%d,%d,0x%x}'%(a&mask,b&mask,f,s,q&mask) for a,b,f,s,q in vectors(operation))
    return '''
local m=emu.memType.snesMemory
local buf=%d
local fraction=%d
local cases={%s}
local idx=0
local bad=0
local injections=0
local start=0
local current=nil
local times={q0={},q40={},q44={},q48={},overflow={},domain={}}
local function wr(a,v,n) for i=0,n-1 do emu.write(a+i,(v>>(8*i))&255,m) end end
local function rd(a,n) local v=0 for i=0,n-1 do v=v|(emu.read(a+i,m)<<(8*i)) end return v end
local function check(name,a,b)
 if a~=b then bad=bad+1 if bad<10 then print("MATHFAIL "..name.." "..idx.." "..a.." "..b) end end
end
emu.addMemoryCallback(function()
 idx=idx+1 current=cases[(idx-1)%%#cases+1]
 wr(buf,current[1],8) wr(buf+8,current[2],8) wr(fraction,current[3],2)
 wr(buf+16,0x123456789abcdef,8) wr(buf+24,0x7777,2)
 wr(buf+26,0xa55a,2) wr(buf+28,0x3cc3,2)
 start=emu.getMasterClock()
end,emu.callbackType.exec,%d,%d)
emu.addMemoryCallback(function()
 local c=current
 check("a",rd(buf,8),c[1]) check("b",rd(buf+8,8),c[2])
 check("status",rd(buf+24,2),c[4])
 check("result",rd(buf+16,8),c[4]==0 and c[5] or 0x123456789abcdef)
 check("status_canary",rd(buf+26,2),0xa55a) check("after",rd(buf+28,2),0x3cc3)
 local k=c[4]==2 and "domain" or (c[4]==1 and "overflow" or "q"..c[3])
 local t=times[k] t[#t+1]=emu.getMasterClock()-start
 if idx==%d then
  local fields={string.format('"cases":%%d,"failures":%%d,"latch_injections":%%d',idx,bad,injections)}
  for name,t in pairs(times) do table.sort(t) local sum=0 for _,v in ipairs(t) do sum=sum+v end
   fields[#fields+1]=string.format('"%%s":{"count":%%d,"median":%%d,"max":%%d,"total":%%d}',name,#t,t[math.floor((#t+1)/2)] or 0,t[#t] or 0,sum)
  end
  out("MATH","math-results.json","{"..table.concat(fields,",").."}")
 end
end,emu.callbackType.exec,%d,%d)
'''%(sym['wide_math_buffers'],sym['wide_math_fraction'],cases,sym['wide_math_call_begin'],sym['wide_math_call_begin'],steps,sym['wide_math_call_end'],sym['wide_math_call_end']) + ''.join('''
emu.addMemoryCallback(function()
 injections=injections+1
 emu.write(0x80210d,0x5a,m) emu.write(0x80210d,0xc3,m)
 emu.write(0x80210e,0x39,m) emu.write(0x80210e,0xa6,m)
 %s
end,emu.callbackType.exec,%d,%d)
'''%('emu.write(0x80211f,emu.read(%d,m),m)'%(sym['core_m7_latch']+1) if restore else '',a,a) for a in addresses)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=Path('build/wide-native-math'))
    p.add_argument('--gen',type=Path,default=Path('build/gen'))
    p.add_argument('--link',type=Path,default=Path('build/test_phys.sfc.link'))
    p.add_argument('--pvs')
    p.add_argument('--physdump',default='build/host/physdump')
    p.add_argument('--cases',default='test/physcases.txt')
    p.add_argument('--operation', choices=('mul','div','sqrt'), default='mul')
    p.add_argument('--latch-stress', action='store_true')
    p.add_argument('--negative-control', action='store_true',
                   help='inject scroll writes without restoration; arithmetic must fail')
    args=p.parse_args();os.chdir(ROOT)
    rom=build(args);symbols=mesen.read_symbols(str(rom));original=mesen.run
    addresses=[a for a in latch_sites(rom,symbols['core_m7_latch'])
               if symbols['wide_mul64']<=a<symbols['wide_div64']] if args.latch_stress or args.negative_control else []
    def run(r,s,o,*a,**kw):
        steps=(Path(o)/'host_log.bin').stat().st_size//6
        lua=Path(kw['lua']);lua.write_text(lua.read_text()+instrument(symbols,steps,args.operation,addresses,not args.negative_control))
        return original(r,s,o,*a,**kw)
    mesen.run=run
    try:
        ok=physrom.run(argparse.Namespace(rom=str(rom),physdump=args.physdump,gen=str(args.gen),cases=args.cases,full=12,full_from=0,out=str(args.out/'check')))
    finally:mesen.run=original
    report=json.loads((args.out/'check/math-results.json').read_text())
    report.update(physics_unchanged=bool(ok),operation=args.operation,
                  latch_sites=len(addresses),negative_control=args.negative_control,
                  clock_scope='Complete compiled C forwarding call, including arguments/copies/save/restore/cleanup')
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    expected=report['failures']>0 if args.negative_control else report['failures']==0
    return 0 if ok and expected and (not addresses or report['latch_injections']>0) else 1
if __name__=='__main__':raise SystemExit(main())
