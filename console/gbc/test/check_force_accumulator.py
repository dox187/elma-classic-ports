#!/usr/bin/env python3
"""Verify native split force sums against complete Python integer arithmetic."""
import argparse,json,random,re,struct,subprocess
from pathlib import Path
from pyboy import PyBoy
BASE=Path(__file__).resolve().parents[1]
Q=1<<24

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--out',type=Path,default=BASE/'build/force-accumulator-check')
 a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 (out/'driver.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
int64_t force_residual[2];
int32_t q24_fraction;
volatile int32_t units[6],fractions[6],answer;
volatile uint8_t ready,request,axis;
void service(void) BANKED;
void main(void){cpu_fast();ready=1;while(1){if(request)service();vsync();}}
''')
 (out/'caller.c').write_text('''#include <gb/gb.h>
#include "physics_force.h"
#pragma bank 8
extern volatile int32_t units[6],fractions[6],answer;
extern volatile uint8_t request,axis;
void service(void) BANKED {
 riding_force_begin();
 for(uint8_t i=0;i<6;++i)riding_force_sub(axis,units[i],fractions[i]);
 answer=riding_force_finish(axis);request=0;
}
''')
 rom=out/'check.gbc';cmd=[BASE/'.toolchain/gbdk/bin/lcc','-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(BASE/'src'),'-o',rom,out/'driver.c',out/'caller.c',BASE/'src/physics_force.c',BASE/'src/physics_div20.s']
 proc=subprocess.run(list(map(str,cmd)),capture_output=True,text=True);(out/'compile.log').write_text(proc.stdout+proc.stderr)
 if proc.returncode:raise RuntimeError(proc.stderr)
 syms={k:int(v,16) for k,v in re.findall(r'DEF (_\w+) 0x([\dA-Fa-f]+)',rom.with_suffix('.noi').read_text())}
 e=PyBoy(str(rom),window='null',sound_emulated=False,cgb=True);e.set_emulation_speed(0)
 def put(n,fmt,*v):
  data=struct.pack(fmt,*v);e.memory[syms['_'+n]:syms['_'+n]+len(data)]=data
 def get(n,fmt):
  size=struct.calcsize(fmt);return struct.unpack(fmt,bytes(e.memory[syms['_'+n]:syms['_'+n]+size]))
 rng=random.Random(933);count=0;failures=[]
 try:
  for _ in range(120):
   e.tick(1,False)
   if get('ready','B')[0]:break
  assert get('ready','B')[0]
  for i in range(8192):
   axis=i&1;prior=rng.randrange(-10*Q,10*Q)
   terms=[(rng.randrange(-(1<<31),1<<31),rng.randrange(-Q//2,Q//2) if j<4 else 0) for j in range(6)]
   if i<1024:terms=[(rng.choice((-2147483648,-1,0,1,2147483647)),rng.choice((-Q//2,-1,0,1,Q//2-1)) if j<4 else 0) for j in range(6)]
   if i>=6144:terms=[(rng.randrange(-1000000,1000000),f) for _,f in terms]
   initial=[3456,7890];initial[axis]=prior
   put('force_residual','2q',*initial);put('units','6i',*[q for q,f in terms]);put('fractions','6i',*[f for q,f in terms]);put('axis','B',axis);put('request','B',1)
   for _ in range(10):
    e.tick(1,False)
    if not get('request','B')[0]:break
   assert not get('request','B')[0], 'native force fixture timed out'
   total=prior-sum(q*Q+f for q,f in terms);expected=(total+10*Q)//(20*Q)
   wanted=list(initial);wanted[axis]=total-expected*20*Q
   got=get('answer','i')[0];res=get('force_residual','2q')
   count+=1
   if got!=expected or list(res)!=wanted:
    failures.append(dict(case=i,axis=axis,terms=terms,prior=prior,result=got,expected=expected,residual=list(res),wanted=wanted));break
 finally:e.stop(save=False)
 report=dict(cases=count,failures=failures,oracle='Complete Python integers; nearest positive ties, exact residual')
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
 assert count==8192 and not failures
if __name__=='__main__':main()
