#!/usr/bin/env python3
"""Verify Q24 quotient, fraction, saturation and restored physical ROM banks."""
from pathlib import Path
import argparse,hashlib,importlib.util,random,json,re,subprocess,collections,sys
from pyboy import PyBoy
B=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--gen',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--source',type=Path,default=B/'src')
p.add_argument('--signed-edges',action='store_true',help='Generate synthetic negative, zero and signed32 endpoint coefficients')
a=p.parse_args();O=a.out.resolve();O.mkdir(parents=True,exist_ok=False);G=a.gen.resolve();S=a.source.resolve()
if a.signed_edges:
 spec=importlib.util.spec_from_file_location('q24_tables',B/'tools/math_q24_coefficients.py')
 generator=importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)
 raw=(G/'riding_constants.h').read_text()
 def signed_pair(m):
  pair=(-int(m[2]),-int(m[3]))
  if 'q24_C_SPRING_T[' in m[1]:pair=(-2147483648,2147483647)
  elif 'q24_C_FRIC_W[' in m[1]:pair=(0,pair[1])
  return m[1]+str(pair[0])+','+str(pair[1])+'}'
 raw=re.sub(r'(q24_C_\w+\[2\]=\{)(-?\d+),(-?\d+)\}',signed_pair,raw)
 constants=O/'signed_constants.h';constants.write_text(raw)
 G=O/'signed-gen';generator.generate(constants,G,481)
coeff=json.loads((G/'physics_q24_manifest.json').read_text())['coefficient_values']
if a.signed_edges:assert {-2147483648,0,2147483647}<=set(coeff)
rng=random.Random(924283)
base=[0,1,-1,127,128,-128,-129,255,-255,256,-256,32767,32768,-32768,-32769,65535,65536,-65536,-65537,16777215,16777216,-16777216,-16777217,2147483647,-2147483648]
base += list(range(-256,257))
base +=[rng.randint(-2**31,2**31-1)for _ in range(384)]+[rng.randint(-65536,65535)for _ in range(128)]
base +=[sign*((1<<k)+delta)for k in range(31)for sign in (-1,1)for delta in (-1,0,1)if -2**31<=sign*((1<<k)+delta)<2**31]
rows=[]
for i,m in enumerate(coeff):
 vals=list(base)
 low=-(1<<31)*(1<<24)-(1<<23);high=(1<<31)*(1<<24)-1-(1<<23)
 ceildiv=lambda a,b:-((-a)//b)
 lo,hi=(ceildiv(low,m),high//m)if m>0 else(ceildiv(high,m),low//m)if m<0 else(-2**31,2**31-1)
 for power in range(8,32,8):
  for sign in (-1,1):
   vals.extend(x for x in range(sign*(1<<power)-4,sign*(1<<power)+5) if -2**31<=x<2**31)
 for bound in (lo,hi):vals.extend(x for x in range(bound-3,bound+4)if -(1<<31)<=x<(1<<31))
 rows.extend(dict(x=x,index=i,group='oracle')for x in dict.fromkeys(vals))
assert len(rows)<65536,'Fixture counter overflow'
(O/'vectors.json').write_text(json.dumps(rows))
(O/'driver.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include "physics_q24.h"
volatile uint16_t fixture_i;volatile uint8_t fixture_done,fixture_index;volatile int32_t fixture_input,fixture_result;
void fixture_before(void){} void fixture_mark(void){}
void main(void){cpu_fast();disable_interrupts();SWITCH_ROM(7);for(fixture_i=0;fixture_i<'''+str(len(rows))+''';++fixture_i){fixture_before();fixture_result=q24_apply(fixture_input,fixture_index);fixture_mark();}fixture_done=1;while(1)vsync();}
''')
# Bank 7 marker catches both a wrong low bank and a stale high mapper bit.
(O/'marker.c').write_text('#include <stdint.h>\n#pragma bank 7\nconst uint8_t bank_marker[]={7,42,91,170,29,255,3,11};\n')
reports={}
for variant in ['candidate']:
 D=O/variant;D.mkdir(exist_ok=True)
 TG=G
 dispatch=TG/'physics_q24_dispatch.c'
 cmd=[B/'.toolchain/gbdk/bin/lcc','-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(S),'-I'+str(TG),'-o',D/'check.gbc',O/'driver.c',O/'marker.c',dispatch,S/'physics_q24.s',*sorted(TG.glob('physics_q24_table_*.c'))]
 p=subprocess.run(list(map(str,cmd)),capture_output=True,text=True);(D/'compile.log').write_text(p.stdout+p.stderr)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 rom=D/'check.gbc';sym={n:int(v,16)for n,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',rom.with_suffix('.noi').read_text())}
 e=PyBoy(str(rom),window='null',sound_emulated=False,cgb=True);e.set_emulation_speed(0);timing=collections.defaultdict(list);fail=[];seen=set();start=[0];marks=[];returns=set();api_cycles=[0];call_sp=[0]
 def read(name,n=4,signed=False):a=sym[name];return int.from_bytes(bytes(e.memory[a:a+n]),'little',signed=signed)
 def before(_):
  i=read('_fixture_i',2);row=rows[i];e.memory[sym['_fixture_input']:sym['_fixture_input']+4]=row['x'].to_bytes(4,'little',signed=True);e.memory[sym['_fixture_index']]=row['index']
 def returned(_):
  if e.register_file.SP==call_sp[0]+3:api_cycles[0]=e._cycles()-start[0]
 def enter(_):
  start[0]=e._cycles();sp=e.register_file.SP;call_sp[0]=sp;addr=e.memory[sp]+256*e.memory[sp+1]
  if addr not in returns:e.hook_register(0,addr,returned,None);returns.add(addr)
 def mark(_):
  i=read('_fixture_i',2)
  if i in seen:return
  seen.add(i);row=rows[i];x=row['x'];m=coeff[row['index']];q=(x*m+2**23)//2**24;want=max(-2**31,min(2**31-1,q));sat=int(want!=q);frac=0 if sat else x*m-q*2**24
  actual=read('_fixture_result',4,True);af=read('_q24_fraction',4,True);ast=read('_q24_saturated',1)
  ok=bytes(e.memory[0x4000:0x4008])==bytes([7,42,91,170,29,255,3,11])and read('__current_bank',1)==7
  if(actual,af,ast,ok)!=(want,frac,sat,True):fail.append(dict(i=i,**row,got=[actual,af,ast,ok],expected=[want,frac,sat,True]))
  cycles=api_cycles[0];timing[row['group']].append(cycles);timing[row['group']+('_zero'if x==0 else'_nonzero')].append(cycles);marks.append(cycles)
 e.hook_register(0,sym['_fixture_before'],before,None);e.hook_register(0,sym['_q24_apply'],enter,None);e.hook_register(0,sym['_fixture_mark'],mark,None)
 for _ in range(100):
  e.tick(100,False)
  if read('_fixture_done',1):break
 assert read('_fixture_done',1),'timeout'
 e.stop(save=False)
 report=dict(cases=len(seen),failure_count=len(fail),failures=fail[:20],cycles={k:dict(count=len(v),min=min(v),mean=sum(v)/len(v),max=max(v),total=sum(v))for k,v in timing.items()},rom0_kernel_bytes=sym['_q24_end']-sym['_q24_apply'],source_sha256={str(f):hashlib.sha256(f.read_bytes()).hexdigest()for f in [S/'physics_q24.s',B/'tools/math_q24_coefficients.py',Path(__file__)]},signed_edges=a.signed_edges)
 (D/'report.json').write_text(json.dumps(report,indent=2));(D/'timings.json').write_text(json.dumps(marks));print(variant,json.dumps(report));reports[variant]=report
 assert len(seen)==len(rows)and not fail
(O/'report.json').write_text(json.dumps(reports,indent=2))
