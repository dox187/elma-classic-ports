"""Paired native wheel torque reaction and frozen C, with integer oracle."""
import argparse,json,random,re,struct,subprocess
from pathlib import Path
from pyboy import PyBoy
B=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gen',type=Path,default=B/'build/gen-8m');p.add_argument('--out',type=Path,default=B/'build/physics-torque-reaction-check');p.add_argument('--captures',type=Path);args=p.parse_args()
G=args.gen.resolve();O=args.out.resolve();O.mkdir(parents=True,exist_ok=True)
rng=random.Random(0x916181);rows=[];coverage={"accumulator_wraps":0,"zero_torque_wheels":0,"int16_min_torque_wheels":0,"int16_max_torque_wheels":0}
C={k:int(v)for k,v in re.findall(r'^#define (C_REACT_[ME]) (\d+)$',(G/'riding_constants.h').read_text(),re.M)}
rec=[int(v)for v in re.findall(r'-?\d+',(B.parent/'nes/src/recip.inc').read_text().split('\n',1)[1])]
def signed(x,n):return(x+(1<<(n-1)))%(1<<n)-(1<<(n-1))
def s32(x):return signed(x,32)
def sat32(x):return max(-2**31,min(2**31-1,x))
def oracle(state):
 out=bytearray(state);tq=struct.unpack_from('<hh',state);kx=struct.unpack_from('<hh',state,20);ky=struct.unpack_from('<hh',state,24)
 for k in range(2):
  if not tq[k]:coverage["zero_torque_wheels"]+=1;continue
  if tq[k]==-32768:coverage["int16_min_torque_wheels"]+=1
  if tq[k]==32767:coverage["int16_max_torque_wheels"]+=1
  x=max(-127,min(127,kx[k]>>4));y=max(-127,min(127,ky[k]>>4));r=rec[min(255,(x*x+y*y)>>5)]
  tr=(tq[k]*r)>>8;tr=sat32((tr*C['C_REACT_M']+(1<<(C['C_REACT_E']-1)))>>C['C_REACT_E'])
  vx=struct.unpack_from('<i',state,28+k*4)[0];vy=struct.unpack_from('<i',state,36+k*4)[0]
  rx=vx+sat32((tr*ky[k]+8192)>>14);ry=vy-sat32((tr*kx[k]+8192)>>14)
  coverage['accumulator_wraps']+=sum(not(-2**31<=v<2**31)for v in [rx,ry])
  struct.pack_into('<i',out,28+k*4,s32(rx));struct.pack_into('<i',out,36+k*4,s32(ry))
 return bytes(out)
def add(state):rows.append((bytes(state),oracle(state)))
limits=[-2147483648,-2147483647,-1073741824,-65536,-32768,-1,0,1,32767,65535,1073741823,2147483646,2147483647]
coords=[-32768,-32767,-2033,-2032,-2031,-16,-1,0,1,15,16,2031,2032,2033,32766,32767]
for tq in [-32768,-32767,-1,0,1,32766,32767]:
 for x in coords:
  for y in coords:
   state=bytearray(rng.randbytes(44));struct.pack_into('<hh',state,0,tq,signed(-tq,16));struct.pack_into('<hhhh',state,20,x,y,y,x)
   struct.pack_into('<iiii',state,28,*[limits[rng.randrange(len(limits))]for _ in range(4)]);add(state)
for _ in range(600):add(rng.randbytes(44))
captured=json.loads(args.captures.read_text())if args.captures else[]
for r in captured:add(bytes.fromhex(r['state']))
header='#include <stdint.h>\ntypedef struct{uint8_t input[44],output[44];}vec_t;\n';sources=[]
for bank,start in enumerate(range(0,len(rows),64),60):
 block=rows[start:start+64];header+=f'extern const vec_t vecs{bank}[];\n#define N{bank} {len(block)}\n';source=O/f'vecs{bank}.c';source.write_text(f'#pragma bank {bank}\n#include "vectors.h"\nconst vec_t vecs{bank}[]={{\n'+',\n'.join('{'+','.join('{'+','.join(map(str,v))+'}'for v in row)+'}'for row in block)+'\n};\n');sources.append((bank,source))
(O/'vectors.h').write_text(header)
(O/'reference.c').write_text('''#pragma bank 8
#include "physics_math.h"
#include "physics_math32.h"
uint8_t riding_recip_index(int16_t,int16_t)__sdcccall(0);
const int16_t Recip_d2[]={
#include "../../nes/src/recip.inc"
};
void riding_torque_reaction_reference(const int16_t*tq,const riding_torque32_t*damping,int32_t*dvx,int32_t*dvy)__sdcccall(0){
 for(uint8_t k=0;k<2;++k){int16_t kx=damping->kx[k],ky=damping->ky[k];
  if(tq[k]){uint8_t d2=riding_recip_index(kx,ky);int16_t rec=Recip_d2[d2];
   int32_t tr=KMUL32(riding_mulshift32((int32_t)tq[k],rec,8),C_REACT);
   dvx[k]+=riding_mulq32(tr,ky,14);dvy[k]-=riding_mulq32(tr,kx,14);
  }
 }
}
'''.replace('#include "../../nes/src/recip.inc"','#include "'+str(B.parent/'nes/src/recip.inc')+'"'))
driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "physics_math32.h"
#include "vectors.h"
uint8_t before_guard[8],state[44],after_guard[8];vec_t copy;
volatile uint8_t done;volatile uint16_t failures,reference_failures,guards,count,banks_bad;
void riding_torque_reaction32(const int16_t*,const riding_torque32_t*,int32_t*,int32_t*)__sdcccall(0);
void riding_torque_reaction_reference(const int16_t*,const riding_torque32_t*,int32_t*,int32_t*)__sdcccall(0);
void check(void){uint8_t i;memcpy(state,copy.input,44);memset(before_guard,0xa5,8);memset(after_guard,0xa5,8);SWITCH_ROM(8);
 riding_torque_reaction32((int16_t*)state,(riding_torque32_t*)(state+4),(int32_t*)(state+28),(int32_t*)(state+36));
 if(CURRENT_BANK!=8)++banks_bad;for(i=0;i<44;++i)if(state[i]!=copy.output[i])++failures;for(i=0;i<8;++i)if(before_guard[i]!=0xa5||after_guard[i]!=0xa5)++guards;
 memcpy(state,copy.input,44);riding_torque_reaction_reference((int16_t*)state,(riding_torque32_t*)(state+4),(int32_t*)(state+28),(int32_t*)(state+36));
 for(i=0;i<44;++i)if(state[i]!=copy.output[i])++reference_failures;++count;}
void main(void){uint16_t i;disable_interrupts();DISPLAY_OFF;cpu_fast();
'''
for bank,_ in sources:driver+=f'for(i=0;i<N{bank};++i){{SWITCH_ROM({bank});memcpy(&copy,&vecs{bank}[i],sizeof(copy));check();}}\n'
driver+='done=1;while(1){}}\n';(O/'driver.c').write_text(driver)
tables=sum((sorted(G.glob(glob))for glob in('physics_coefficient_*.c','physics_quarter_*.c','physics_scale_*.c')),[])
common=[B/'src'/f for f in('physics_math32.c','physics_math32.s','physics_mul_fast.s','physics_kmul_fast.s','physics_math.s','physics_shift_fast.s','physics_recip_fast.s')]
cmd=[B/'.toolchain/gbdk/bin/lcc','-msm83:gb','-Wf--opt-code-size','-Wf--max-allocs-per-node','-Wf100000','-DRIDING_COEFFICIENT_LOOKUP','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(O),'-I'+str(G),'-I'+str(B/'src'),'-o',O/'check.gbc',O/'driver.c',O/'reference.c',B/'src/physics_torque_reaction.s',*common,*[v for _,v in sources],*tables,G/'physics_coefficient_calls.s']
r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True);(O/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,(O/'compile.log').read_text()
symbols={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(O/'check.noi').read_text())};emu=PyBoy(str(O/'check.gbc'),window='null',sound_emulated=False,cgb=True);emu.set_emulation_speed(0);started=[];cycles={'assembly':[],'reference':[]};returns=set()
def returned(_):
 if started and started[-1][0]==emu.register_file.SP-2:
  sp,when,name=started.pop();cycles[name].append(emu._cycles()-when)
def entered(name):
 sp=emu.register_file.SP;pc=emu.memory[sp]+256*emu.memory[sp+1]
 if pc not in returns:emu.hook_register(0,pc,returned,None);returns.add(pc)
 started.append((sp,emu._cycles(),name))
for name,sym in [('assembly','_riding_torque_reaction32'),('reference','_riding_torque_reaction_reference')]:emu.hook_register(8,symbols[sym]&65535,entered,name)
try:
 for _ in range(300):
  emu.tick(100,False)
  if emu.memory[symbols['_done']]:break
 def n(name,size=2):return int.from_bytes(bytes(emu.memory[symbols['_'+name]:symbols['_'+name]+size]),'little')
 report={name:n(name)for name in('failures','reference_failures','guards','count','banks_bad')};report.update(coverage=coverage,done=n('done',1),captured=len(captured),expected_cases=len(rows),cycles={name:dict(min=min(v),max=max(v),mean=sum(v)/len(v),count=len(v))for name,v in cycles.items()})
 if len(cycles['assembly'])==len(cycles['reference']):
  savings=[a-b for a,b in zip(cycles['reference'],cycles['assembly'])];report['savings']=dict(min=min(savings),max=max(savings),mean=sum(savings)/len(savings))
 (O/'cycles.json').write_text(json.dumps(cycles)+'\n');(O/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));assert report['done']and report['count']==len(rows)and not any(report[x]for x in('failures','reference_failures','guards','banks_bad'))
finally:emu.stop(save=False)
