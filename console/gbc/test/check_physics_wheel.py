"""Validate exact rolling, support and free-wheel kernels at full width."""
import json,random,re,struct,subprocess
from pathlib import Path
from pyboy import PyBoy
import argparse,hashlib
parser=argparse.ArgumentParser(description='Compare native wheel response with C and wide-integer models.')
parser.add_argument('--gen',type=Path)
parser.add_argument('--out',type=Path)
parser.add_argument('--captured',type=Path)
a=parser.parse_args();BASE=Path(__file__).resolve().parents[1];SRC=BASE/'src'
GEN=(a.gen or BASE/'build/gen-8m').resolve()
OUT=(a.out or BASE/'build/wheel-response-check').resolve();OUT.mkdir(parents=True,exist_ok=True)
captured=json.loads(a.captured.read_text())if a.captured else []
source_hashes={n:hashlib.sha256((SRC/n).read_bytes()).hexdigest()for n in ('physics_roll_fast.s','physics_supports_fast.s','physics_free_fast.s')}
def signed(x,n):return (x+(1<<(n-1)))%(1<<n)-(1<<(n-1))
def s32(x):return signed(x,32)
def sat32(x):return max(-2**31,min(2**31-1,x))
def sat16(x):return max(-32768,min(32767,x))
def dot(a,b,c,d):return sat32((a*c+b*d+8192)>>14)
def mul(a,b):return sat32((a*b+8192)>>14)
co={k:int(v)for k,v in re.findall(r'^#define (C_ROLL_\w+) (\d+)$',(GEN/'riding_constants.h').read_text(),re.M)}
def km(x,c):return sat32((x*co['C_ROLL_'+c+'_M']+(1<<(co['C_ROLL_'+c+'_E']-1)))>>co['C_ROLL_'+c+'_E'])
rng=random.Random(0x910177);rows=[]
def add(circle,contact,args):
 x,y,vx,vy,alfa,omega=struct.unpack('<iiiiIh',circle);nx,ny,*_=struct.unpack('<hhhhh',contact);dvx,dvy,tq=struct.unpack('<iih',args);tx=signed(-ny,16);ty=nx
 vn=dot(vx,vy,tx,ty);dvn=dot(dvx,dvy,tx,ty);t=s32(tq+km(dvn,'T'));w=s32(km(vn,'W')+km(t,'DW'));om=sat16(w);sp=km(om,'V');vxx=mul(sp,tx);vyy=mul(sp,ty)
 want=struct.pack('<iiiiIh',s32(x+vxx*4),s32(y+vyy*4),vxx,vyy,(alfa+om*128)%2**32,om)
 nv=dot(vx,vy,nx,ny);supported=not(nv> -10 and dot(dvx,dvy,nx,ny)>0);svx=vx;svy=vy
 if supported and (tq&1):svx=s32(vx-mul(nv,nx));svy=s32(vy-mul(nv,ny))
 support=struct.pack('<iiiiIhB',x,y,svx,svy,alfa,omega,int(supported))
 fc={k:int(v)for k,v in re.findall(r'^#define (C_FREE_[ME]) (\d+)$',(GEN/'riding_constants.h').read_text(),re.M)}
 omfree=sat16(omega+sat16((tq*fc['C_FREE_M']+(1<<(fc['C_FREE_E']-1)))>>fc['C_FREE_E']));fvx=s32(vx+dvx);fvy=s32(vy+dvy)
 free=struct.pack('<iiiiIh',s32(x+fvx*4),s32(y+fvy*4),fvx,fvy,(alfa+omfree*128)%2**32,omfree)
 rows.append((circle+contact+args,want+support+free))
for r in captured:add(bytes.fromhex(r['circle']),bytes.fromhex(r['contact']),bytes.fromhex(r['args']))
values=[-2**31,-2**31+1,-65537,-32769,-32768,-11,-10,-9,-1,0,1,9,10,11,32767,32768,65535,2**31-2,2**31-1]
normals=[(-32768,-32768),(-32768,32767),(32767,-32768),(32767,32767),(-16384,0),(0,-16384),(16384,0),(0,16384),(0,0),(1,-1),(-1,1),(11585,11585)]
for a in values:
 for n in normals:
  for remove in [0,1]:
   circle=struct.pack('<iiiiIh',rng.randint(-2**31,2**31-1),rng.randint(-2**31,2**31-1),a,-1-a,rng.getrandbits(32),rng.randint(-32768,32767));contact=struct.pack('<hhhhh',*n,405,0,0);args=struct.pack('<iih',rng.choice(values),rng.choice(values),rng.choice([-32768,-2,0,2,32766])+remove);add(circle,contact,args)
for i in range(900):
 circle=struct.pack('<iiiiIh',*[rng.randint(-2**31,2**31-1)for _ in range(4)],rng.getrandbits(32),rng.randint(-32768,32767));contact=struct.pack('<hhhhh',*[rng.randint(-32768,32767)for _ in range(5)]);args=struct.pack('<iih',rng.randint(-2**31,2**31-1),rng.randint(-2**31,2**31-1),rng.randint(-32768,32767));add(circle,contact,args)
header='#include <stdint.h>\ntypedef struct{uint8_t input[42],output[67];}vec_t;\n';sources=[]
for bank,start in enumerate(range(0,len(rows),100),60):
 block=rows[start:start+100];header+=f'extern const vec_t vecs{bank}[];\n#define N{bank} {len(block)}\n';p=OUT/f'vecs{bank}.c';p.write_text(f'#pragma bank {bank}\n#include "vectors.h"\nconst vec_t vecs{bank}[]={{\n'+',\n'.join('{{'+','.join(map(str,x))+'},{'+','.join(map(str,y))+'}}'for x,y in block)+'\n};\n');sources.append((bank,p))
(OUT/'vectors.h').write_text(header)
reference='''#pragma bank 9
#include "physics_core.h"
#include "physics_math.h"
#include "physics_math32.h"
typedef struct {int16_t nx,ny,l,tx,ty;}contact_t;
void riding_roll_reference(circle_t*k,const contact_t*c,int32_t dvx,int32_t dvy,int16_t tq)__sdcccall(0){
 int16_t n90x=-c->ny,n90y=c->nx;
 int32_t vn=riding_dotq32(k->vx,k->vy,n90x,n90y,14),dvn=riding_dotq32(dvx,dvy,n90x,n90y,14);
 int32_t t=(int32_t)tq+KMUL32(dvn,C_ROLL_T),w=KMUL32(vn,C_ROLL_W)+KMUL32(t,C_ROLL_DW);
 k->omega=sat16(w);int32_t sp=KMUL32((int32_t)k->omega,C_ROLL_V);
 k->vx=riding_mulq32(sp,n90x,14);k->vy=riding_mulq32(sp,n90y,14);riding_move32(k);
}
void riding_free_reference(circle_t*k,int32_t dvx,int32_t dvy,int16_t tq)__sdcccall(0){k->omega=sat16((int32_t)k->omega+KMUL(tq,C_FREE));k->vx+=dvx;k->vy+=dvy;riding_move32(k);}
uint8_t riding_supports_reference(circle_t*k,const contact_t*c,int32_t dvx,int32_t dvy,uint8_t remove){
 int32_t nv=riding_dotq32(k->vx,k->vy,c->nx,c->ny,14);
 if(nv> -ELSZ && riding_dotq32(dvx,dvy,c->nx,c->ny,14)>0)return 0;
 if(remove){k->vx-=riding_mulq32(nv,c->nx,14);k->vy-=riding_mulq32(nv,c->ny,14);}return 1;
}
''';(OUT/'reference.c').write_text(reference)
driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "vectors.h"
#include "physics_core.h"
typedef struct {int16_t nx,ny,l,tx,ty;}contact_t;
uint8_t arena[30];contact_t contact;vec_t copy;volatile uint8_t done;volatile uint16_t failures,reference_failures,free_failures,free_reference_failures,support_failures,support_reference_failures,guards,count,banks_bad,contact_bad;
void riding_free32(circle_t*,int32_t,int32_t,int16_t)__sdcccall(0);
void riding_free_reference(circle_t*,int32_t,int32_t,int16_t)__sdcccall(0);
void riding_roll32(circle_t*,const contact_t*,int32_t,int32_t,int16_t)__sdcccall(0);
void riding_roll_reference(circle_t*,const contact_t*,int32_t,int32_t,int16_t)__sdcccall(0);
uint8_t riding_supports32(circle_t*,const contact_t*,int32_t,int32_t,uint8_t);
uint8_t riding_supports_reference(circle_t*,const contact_t*,int32_t,int32_t,uint8_t);
void check(void){uint8_t i,r;int32_t dvx=*(int32_t*)(copy.input+32),dvy=*(int32_t*)(copy.input+36);int16_t tq=*(int16_t*)(copy.input+40);memset(arena,0xa5,30);memcpy(&contact,copy.input+22,10);SWITCH_ROM(9);
 memcpy(arena+4,copy.input,22);riding_roll32((circle_t*)(arena+4),&contact,dvx,dvy,tq);for(i=0;i<22;++i)if(arena[4+i]!=copy.output[i])++failures;
 memcpy(arena+4,copy.input,22);riding_roll_reference((circle_t*)(arena+4),&contact,dvx,dvy,tq);for(i=0;i<22;++i)if(arena[4+i]!=copy.output[i])++reference_failures;
 memcpy(arena+4,copy.input,22);r=riding_supports32((circle_t*)(arena+4),&contact,dvx,dvy,tq&1);for(i=0;i<22;++i)if(arena[4+i]!=copy.output[22+i])++support_failures;if(r!=copy.output[44])++support_failures;
 memcpy(arena+4,copy.input,22);r=riding_supports_reference((circle_t*)(arena+4),&contact,dvx,dvy,tq&1);for(i=0;i<22;++i)if(arena[4+i]!=copy.output[22+i])++support_reference_failures;if(r!=copy.output[44])++support_reference_failures;
 memcpy(arena+4,copy.input,22);riding_free32((circle_t*)(arena+4),dvx,dvy,tq);for(i=0;i<22;++i)if(arena[4+i]!=copy.output[45+i])++free_failures;
 memcpy(arena+4,copy.input,22);riding_free_reference((circle_t*)(arena+4),dvx,dvy,tq);for(i=0;i<22;++i)if(arena[4+i]!=copy.output[45+i])++free_reference_failures;
 if(CURRENT_BANK!=9)++banks_bad;for(i=0;i<30;++i)if((i<4||i>=26)&&arena[i]!=0xa5)++guards;for(i=0;i<10;++i)if(((uint8_t*)&contact)[i]!=copy.input[22+i])++contact_bad;++count;}
void main(void){uint16_t i;disable_interrupts();DISPLAY_OFF;cpu_fast();
'''
for bank,_ in sources:driver+=f'for(i=0;i<N{bank};++i){{SWITCH_ROM({bank});memcpy(&copy,&vecs{bank}[i],sizeof(copy));check();}}\n'
driver+='done=1;while(1){}}\n';(OUT/'driver.c').write_text(driver)
tables=sum((sorted(GEN.glob(g))for g in('physics_coefficient_*.c','physics_quarter_*.c','physics_scale_*.c')),[])
common=[SRC/f for f in('physics_math32.c','physics_math32.s','physics_mul_fast.s','physics_kmul_fast.s','physics_math.s','physics_shift_fast.s','physics_move_fast.s','physics_roll_fast.s','physics_supports_fast.s','physics_free_fast.s')]
cmd=[BASE/'.toolchain/gbdk/bin/lcc','-msm83:gb','-Wf--opt-code-size','-Wf--max-allocs-per-node','-Wf100000','-DRIDING_COEFFICIENT_LOOKUP','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(OUT),'-I'+str(GEN),'-I'+str(SRC),'-o',OUT/'check.gbc',OUT/'driver.c',OUT/'reference.c',*common,*[v for _,v in sources],*tables,GEN/'physics_coefficient_calls.s']
r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True);(OUT/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,(OUT/'compile.log').read_text()
S={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(OUT/'check.noi').read_text())};e=PyBoy(str(OUT/'check.gbc'),window='null',sound_emulated=False,cgb=True);e.set_emulation_speed(0);started=[];cycles={name:[]for name in('roll32','roll_reference','supports32','supports_reference','free32','free_reference')};returns=set()
def returned(_):
 if started and e.register_file.SP-started[-1][0] in (2,11):
  sp,when,name=started.pop();cycles[name].append(e._cycles()-when)
def entered(name):
 sp=e.register_file.SP;pc=e.memory[sp]+256*e.memory[sp+1]
 if pc not in returns:e.hook_register(0,pc,returned,None);returns.add(pc)
 started.append((sp,e._cycles(),name))
for name in cycles:e.hook_register(9,S['_riding_'+name]&65535,entered,name)
try:
 for _ in range(300):
  e.tick(100,False)
  if e.memory[S['_done']]:break
 def n(name,size=2):return int.from_bytes(bytes(e.memory[S['_'+name]:S['_'+name]+size]),'little')
 report={name:n(name)for name in('failures','reference_failures','support_failures','support_reference_failures','free_failures','free_reference_failures','guards','count','banks_bad','contact_bad')};report.update(done=n('done',1),captured=len(captured),expected_cases=len(rows),cycles={name:dict(min=min(v),max=max(v),mean=sum(v)/len(v),count=len(v))for name,v in cycles.items()})
 for name in('roll','supports','free'):
  delta=[a-b for a,b in zip(cycles[name+'_reference'],cycles[name+'32'])];report[name+'_savings']=dict(min=min(delta),max=max(delta),mean=sum(delta)/len(delta))
 (OUT/'cycles.json').write_text(json.dumps(cycles));(OUT/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));assert report['done']and report['count']==len(rows)and not any(report[x]for x in('failures','reference_failures','support_failures','support_reference_failures','free_failures','free_reference_failures','guards','banks_bad','contact_bad'))
finally:e.stop(save=False)

assert all(hashlib.sha256((SRC/n).read_bytes()).hexdigest()==h for n,h in source_hashes.items())
