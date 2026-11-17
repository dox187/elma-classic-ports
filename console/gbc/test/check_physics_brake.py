"""Paired native C/assembly brake torque vectors with Python exact oracle."""
import argparse,json,random,re,struct,subprocess
from pathlib import Path
from pyboy import PyBoy
BASE=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--gen',type=Path,default=BASE/'build/gen-8m');parser.add_argument('--out',type=Path,default=BASE/'build/physics-brake-check');args=parser.parse_args()
GEN=args.gen.resolve();OUT=args.out.resolve();OUT.mkdir(parents=True,exist_ok=True)
constants={k:int(v) for k,v in re.findall(r'^#define (C_BRAKE_[AW]_[ME]) (\d+)$',(GEN/'riding_constants.h').read_text(),re.M)}
ma,ea,mw,ew=[constants[k] for k in ('C_BRAKE_A_M','C_BRAKE_A_E','C_BRAKE_W_M','C_BRAKE_W_E')]
rng=random.Random(0x916272);rows=[]
def s32(x):return (x+2**31)%2**32-2**31
def sat16(x):return max(-32768,min(32767,x))
def row(alfa,wa,db,omega,wo):
 state=bytearray(rng.randbytes(109))
 struct.pack_into('<Ih',state,16,alfa,omega)
 for k in range(2):struct.pack_into('<Ih',state,38+22*k,wa[k],wo[k])
 struct.pack_into('<II',state,95,*db)
 want=[]
 for k in range(2):
  da=s32(wa[k]-alfa-db[k])>>8; spring=(da*ma+(1<<(ea-1)))>>ea
  dw=max(-16383,min(16383,wo[k]-omega)); friction=sat16((dw*mw+(1<<(ew-1)))>>ew)
  want.append(sat16(-spring-friction))
 rows.append((bytes(state),struct.pack('<hh',*want)))
values=[-32768,-32767,-16385,-16384,-16383,-16382,-1,0,1,16382,16383,16384,16385,32766,32767]
angles=[0,1,127,128,255,256,257,0x7fffffff,0x80000000,0xffffff00,0xffffff80,0xffffffff]
for i,v in enumerate(values):
 for j,u in enumerate(values):
  row(angles[(i+j)%len(angles)],[angles[i%len(angles)],angles[j%len(angles)]],[angles[(i+5)%len(angles)],angles[(j+6)%len(angles)]],v,[u,-1-u])
for spring in [-32769,-32768,-32767,-1,0,1,32766,32767,32768]:
 for low in [0,1,127,128,129,254,255]:
  for diff in [-1,0,1]:
   da=(spring*(1<<ea)//ma)+diff; angle=(da*256+low)&0xffffffff
   row(0,[angle,(-angle)&0xffffffff],[0,0],0,[0,0])
for _ in range(1200):row(rng.getrandbits(32),[rng.getrandbits(32)for _ in range(2)],[rng.getrandbits(32)for _ in range(2)],rng.randint(-32768,32767),[rng.randint(-32768,32767)for _ in range(2)])
header='#include <stdint.h>\ntypedef struct{uint8_t input[109],output[4];}vec_t;\n';sources=[]
for bank,start in enumerate(range(0,len(rows),128),60):
 block=rows[start:start+128];header+=f'extern const vec_t vecs{bank}[];\n#define N{bank} {len(block)}\n';source=OUT/f'vecs{bank}.c';source.write_text(f'#pragma bank {bank}\n#include "vectors.h"\nconst vec_t vecs{bank}[]={{\n'+',\n'.join('{{'+','.join(map(str,x))+'},{'+','.join(map(str,y))+'}}'for x,y in block)+'\n};\n');sources.append((bank,source))
(OUT/'vectors.h').write_text(header)
(OUT/'reference.c').write_text('''#pragma bank 8
#include "physics_core.h"
#include "physics_math.h"
#include "physics_math32.h"
static int16_t clamp_w(int32_t w){if(w>16383)return 16383;if(w< -16383)return -16383;return (int16_t)w;}
void riding_brake_reference(int16_t*tq)__sdcccall(0){
 for(uint8_t k=0;k<2;++k){
 int32_t da=riding_sra8((int32_t)(Bike.wheel[k].alfa-(Bike.body.alfa+Bike.dbrake[k])));
 int32_t spring=KMUL32(da,C_BRAKE_A);
 int16_t dw=clamp_w((int32_t)Bike.wheel[k].omega-Bike.body.omega);
 tq[k]=sat16(-spring-KMUL(dw,C_BRAKE_W));
 }
}
''')
driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "vectors.h"
uint8_t Bike[109],arena[12];vec_t copy;
volatile uint8_t done;volatile uint16_t failures,reference_failures,guards,count,banks_bad,state_bad;
void riding_brake32(int16_t*)__sdcccall(0);void riding_brake_reference(int16_t*)__sdcccall(0);
void check(void){uint8_t i;memcpy(Bike,copy.input,109);memset(arena,0xa5,12);SWITCH_ROM(8);riding_brake32((int16_t*)(arena+4));if(CURRENT_BANK!=8)++banks_bad;for(i=0;i<4;++i)if(arena[4+i]!=copy.output[i])++failures;for(i=0;i<12;++i)if((i<4||i>=8)&&arena[i]!=0xa5)++guards;for(i=0;i<109;++i)if(Bike[i]!=copy.input[i])++state_bad;riding_brake_reference((int16_t*)(arena+4));for(i=0;i<4;++i)if(arena[4+i]!=copy.output[i])++reference_failures;++count;}
void main(void){uint16_t i;disable_interrupts();DISPLAY_OFF;cpu_fast();
'''
for bank,_ in sources:driver+=f'for(i=0;i<N{bank};++i){{SWITCH_ROM({bank});memcpy(&copy,&vecs{bank}[i],sizeof(copy));check();}}\n'
driver+='done=1;while(1){}}\n';(OUT/'driver.c').write_text(driver)
tables=sum((sorted(GEN.glob(glob))for glob in('physics_coefficient_*.c','physics_quarter_*.c','physics_scale_*.c')),[])
common=[BASE/'src'/f for f in('physics_math32.c','physics_math32.s','physics_mul_fast.s','physics_kmul_fast.s','physics_math.s','physics_shift_fast.s')]
cmd=[BASE/'.toolchain/gbdk/bin/lcc','-msm83:gb','-Wf--opt-code-size','-Wf--max-allocs-per-node','-Wf100000','-DRIDING_COEFFICIENT_LOOKUP','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(OUT),'-I'+str(GEN),'-I'+str(BASE/'src'),'-o',OUT/'check.gbc',OUT/'driver.c',OUT/'reference.c',BASE/'src/physics_brake_fast.s',*common,*[v for _,v in sources],*tables,GEN/'physics_coefficient_calls.s']
r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True);(OUT/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,(OUT/'compile.log').read_text()
symbols={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(OUT/'check.noi').read_text())};emu=PyBoy(str(OUT/'check.gbc'),window='null',sound_emulated=False,cgb=True);emu.set_emulation_speed(0);started=[];cycles={'assembly':[],'reference':[]};returns=set()
def returned(_):
 if started and started[-1][0]==emu.register_file.SP-2:
  sp,when,name=started.pop();cycles[name].append(emu._cycles()-when)
def entered(name):
 sp=emu.register_file.SP;pc=emu.memory[sp]+256*emu.memory[sp+1]
 if pc not in returns:emu.hook_register(0,pc,returned,None);returns.add(pc)
 started.append((sp,emu._cycles(),name))
for name,sym in [('assembly','_riding_brake32'),('reference','_riding_brake_reference')]:emu.hook_register(8,symbols[sym]&65535,entered,name)
try:
 for _ in range(300):
  emu.tick(100,False)
  if emu.memory[symbols['_done']]:break
 def n(name,size=2):return int.from_bytes(bytes(emu.memory[symbols['_'+name]:symbols['_'+name]+size]),'little')
 report={name:n(name)for name in('failures','reference_failures','guards','count','banks_bad','state_bad')};report.update(done=n('done',1),expected_cases=len(rows),cycles={name:dict(min=min(v),max=max(v),mean=sum(v)/len(v),count=len(v))for name,v in cycles.items()})
 if len(cycles['assembly'])==len(cycles['reference']):
  savings=[a-b for a,b in zip(cycles['reference'],cycles['assembly'])];report['savings']=dict(min=min(savings),max=max(savings),mean=sum(savings)/len(savings))
 (OUT/'cycles.json').write_text(json.dumps(cycles)+'\n');(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));assert report['done']and report['count']==len(rows)and not any(report[x]for x in('failures','reference_failures','guards','banks_bad','state_bad'))
finally:emu.stop(save=False)
