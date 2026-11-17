"""Paired native rider response and frozen C, with independent integer oracle."""
import argparse,json,random,re,struct,subprocess
from pathlib import Path
from pyboy import PyBoy
B=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gen',type=Path,default=B/'build/gen-8m');p.add_argument('--out',type=Path,default=B/'build/physics-rider-response-check');p.add_argument('--captures',type=Path);args=p.parse_args()
G=args.gen.resolve();O=args.out.resolve();O.mkdir(parents=True,exist_ok=True)
rng=random.Random(0x916181);rows=[]
C={k:int(v)for k,v in re.findall(r'^#define (C_RIDER_[SF]_[ME]) (\d+)$',(G/'riding_constants.h').read_text(),re.M)}
def signed(x,n):return(x+(1<<(n-1)))%(1<<n)-(1<<(n-1))
def s32(x):return signed(x,32)
def sat(x,n):return max(-(1<<(n-1)),min((1<<(n-1))-1,x))
def coeff(x,c):return sat((x*C[c+'_M']+(1<<(C[c+'_E']-1)))>>C[c+'_E'],32)
def oracle(state,args):
 bx,by,bvx,bvy=struct.unpack_from('<iiii',state);x,y,vx,vy=struct.unpack_from('<iiii',state,66);rx,ry,oms,gx,gy=struct.unpack('<hhiii',args)
 dx=sat(s32(x-bx)>>4,16);dy=sat(s32(y-by)>>4,16)
 dirx=sat((s32(bx-x)>>4)+rx,16);diry=sat((s32(by-y)>>4)+ry,16)
 relx=s32(vx-s32(bvx+sat((oms*signed(-dy,16)+8192)>>14,32)));rely=s32(vy-s32(bvy+sat((oms*dx+8192)>>14,32)))
 ax=s32(coeff(dirx,'C_RIDER_S')-coeff(relx,'C_RIDER_F')+gx);ay=s32(coeff(diry,'C_RIDER_S')-coeff(rely,'C_RIDER_F')+gy)
 vx=s32(vx+ax);vy=s32(vy+ay);out=bytearray(state);struct.pack_into('<iiii',out,66,s32(x+vx*4),s32(y+vy*4),vx,vy);return bytes(out)
def add(state,args):rows.append((bytes(state),args,oracle(state,args)))
limits=[-2147483648,-2147483647,-1073741824,-65536,-32768,-1,0,1,32767,65535,1073741823,2147483646,2147483647]
for i,q in enumerate([-65537,-65536,-32769,-32768,-32767,-1,0,1,32766,32767,32768,65535,65536]):
 for low in range(16):
  for rest in [-32768,-1,0,1,32767]:
   state=bytearray(rng.randbytes(109));bx=limits[i%len(limits)];by=limits[(i+1)%len(limits)];struct.pack_into('<iiii',state,0,bx,by,limits[(i+2)%len(limits)],limits[(i+3)%len(limits)])
   struct.pack_into('<iiii',state,66,s32(bx+q*16+low),s32(by-q*16-low),limits[(i+4)%len(limits)],limits[(i+5)%len(limits)])
   add(state,struct.pack('<hhiii',rest,signed(-rest,16),limits[(i+6)%len(limits)],limits[(i+7)%len(limits)],limits[(i+8)%len(limits)]))
for _ in range(600):
 state=rng.randbytes(109);add(state,struct.pack('<hhiii',rng.randint(-32768,32767),rng.randint(-32768,32767),*(rng.randint(-2**31,2**31-1)for _ in range(3))))
captured=json.loads(args.captures.read_text())if args.captures else[]
for r in captured:add(bytes.fromhex(r['state']),bytes.fromhex(r['args']))
header='#include <stdint.h>\ntypedef struct{uint8_t input[109],args[16],output[109];}vec_t;\n';sources=[]
for bank,start in enumerate(range(0,len(rows),64),60):
 block=rows[start:start+64];header+=f'extern const vec_t vecs{bank}[];\n#define N{bank} {len(block)}\n';source=O/f'vecs{bank}.c';source.write_text(f'#pragma bank {bank}\n#include "vectors.h"\nconst vec_t vecs{bank}[]={{\n'+',\n'.join('{'+','.join('{'+','.join(map(str,v))+'}'for v in row)+'}'for row in block)+'\n};\n');sources.append((bank,source))
(O/'vectors.h').write_text(header)
(O/'reference.c').write_text('''#pragma bank 8
#include "physics_core.h"
#include "physics_math.h"
#include "physics_math32.h"
void riding_rider_vectors32(int16_t,int16_t,int16_t*)__sdcccall(0);
void riding_rider_move32(int32_t,int32_t)__sdcccall(0);
void riding_rider_response_reference(int16_t restx,int16_t resty,int32_t Oms,int32_t gx,int32_t gy)__sdcccall(0){
 int16_t v[4];riding_rider_vectors32(restx,resty,v);
 int16_t dirx=v[0],diry=v[1],dx=v[2],dy=v[3];
 int32_t relx=Bike.rider_vx-(Bike.body.vx+riding_mulq32(Oms,-dy,14));
 int32_t rely=Bike.rider_vy-(Bike.body.vy+riding_mulq32(Oms,dx,14));
 int32_t ax=KMUL32(dirx,C_RIDER_S)-KMUL32(relx,C_RIDER_F)+gx;
 int32_t ay=KMUL32(diry,C_RIDER_S)-KMUL32(rely,C_RIDER_F)+gy;
 riding_rider_move32(ax,ay);
}
''')
driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "vectors.h"
uint8_t before_guard[8],Bike[109],after_guard[8];vec_t copy;
volatile uint8_t done;volatile uint16_t failures,reference_failures,guards,count,banks_bad;
void riding_rider_response32(int16_t,int16_t,int32_t,int32_t,int32_t)__sdcccall(0);void riding_rider_response_reference(int16_t,int16_t,int32_t,int32_t,int32_t)__sdcccall(0);
void check(void){uint8_t i;int16_t *a=(int16_t*)copy.args;int32_t *g=(int32_t*)(copy.args+4);memcpy(Bike,copy.input,109);memset(before_guard,0xa5,8);memset(after_guard,0xa5,8);SWITCH_ROM(8);riding_rider_response32(a[0],a[1],g[0],g[1],g[2]);if(CURRENT_BANK!=8)++banks_bad;for(i=0;i<109;++i)if(Bike[i]!=copy.output[i])++failures;for(i=0;i<8;++i)if(before_guard[i]!=0xa5||after_guard[i]!=0xa5)++guards;memcpy(Bike,copy.input,109);riding_rider_response_reference(a[0],a[1],g[0],g[1],g[2]);for(i=0;i<109;++i)if(Bike[i]!=copy.output[i])++reference_failures;++count;}
void main(void){uint16_t i;disable_interrupts();DISPLAY_OFF;cpu_fast();
'''
for bank,_ in sources:driver+=f'for(i=0;i<N{bank};++i){{SWITCH_ROM({bank});memcpy(&copy,&vecs{bank}[i],sizeof(copy));check();}}\n'
driver+='done=1;while(1){}}\n';(O/'driver.c').write_text(driver)
tables=sum((sorted(G.glob(glob))for glob in('physics_coefficient_*.c','physics_quarter_*.c','physics_scale_*.c')),[])
common=[B/'src'/f for f in('physics_math32.c','physics_math32.s','physics_mul_fast.s','physics_kmul_fast.s','physics_math.s','physics_shift_fast.s','physics_rider_fast.s')]
cmd=[B/'.toolchain/gbdk/bin/lcc','-msm83:gb','-Wf--opt-code-size','-Wf--max-allocs-per-node','-Wf100000','-DRIDING_COEFFICIENT_LOOKUP','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(O),'-I'+str(G),'-I'+str(B/'src'),'-o',O/'check.gbc',O/'driver.c',O/'reference.c',B/'src/physics_rider_response.s',*common,*[v for _,v in sources],*tables,G/'physics_coefficient_calls.s']
r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True);(O/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,(O/'compile.log').read_text()
symbols={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(O/'check.noi').read_text())};emu=PyBoy(str(O/'check.gbc'),window='null',sound_emulated=False,cgb=True);emu.set_emulation_speed(0);started=[];cycles={'assembly':[],'reference':[]};returns=set()
def returned(_):
 if started and started[-1][0]==emu.register_file.SP-2:
  sp,when,name=started.pop();cycles[name].append(emu._cycles()-when)
def entered(name):
 sp=emu.register_file.SP;pc=emu.memory[sp]+256*emu.memory[sp+1]
 if pc not in returns:emu.hook_register(0,pc,returned,None);returns.add(pc)
 started.append((sp,emu._cycles(),name))
for name,sym in [('assembly','_riding_rider_response32'),('reference','_riding_rider_response_reference')]:emu.hook_register(8,symbols[sym]&65535,entered,name)
try:
 for _ in range(300):
  emu.tick(100,False)
  if emu.memory[symbols['_done']]:break
 def n(name,size=2):return int.from_bytes(bytes(emu.memory[symbols['_'+name]:symbols['_'+name]+size]),'little')
 report={name:n(name)for name in('failures','reference_failures','guards','count','banks_bad')};report.update(done=n('done',1),captured=len(captured),expected_cases=len(rows),cycles={name:dict(min=min(v),max=max(v),mean=sum(v)/len(v),count=len(v))for name,v in cycles.items()})
 if len(cycles['assembly'])==len(cycles['reference']):
  savings=[a-b for a,b in zip(cycles['reference'],cycles['assembly'])];report['savings']=dict(min=min(savings),max=max(savings),mean=sum(savings)/len(savings))
 (O/'cycles.json').write_text(json.dumps(cycles)+'\n');(O/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));assert report['done']and report['count']==len(rows)and not any(report[x]for x in('failures','reference_failures','guards','banks_bad'))
finally:emu.stop(save=False)
