"""Native exact two-wheel suspension orchestration, wide velocities and guards."""
import argparse,json,random,re,struct,subprocess
from pathlib import Path
from pyboy import PyBoy
BASE=Path(__file__).resolve().parents[1]

def s32(x):return (x+2**31)%2**32-2**31
def sat(x,bits):return max(-(1<<(bits-1)),min((1<<(bits-1))-1,x))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',type=Path,default=BASE);p.add_argument('--out',type=Path,default=BASE/'build/suspension-check');p.add_argument('--gen',type=Path,default=BASE/'build/gen');p.add_argument('--assembly',type=Path,default=BASE/'src/physics_suspension_fast.s');a=p.parse_args();base=a.base.resolve();out=a.out.resolve();gen=a.gen.resolve();out.mkdir(parents=True,exist_ok=True)
 constants=(gen/'riding_constants.h').read_text()
 def coeff(x,c):
  m=int(re.search(r'#define '+c+r'_M (\d+)',constants)[1]);e=int(re.search(r'#define '+c+r'_E (\d+)',constants)[1]);return sat((x*m+(1<<(e-1)))>>e,32)
 rng=random.Random(0x9191);rows=[]
 def row(circles,gsx,gsy,oms):
  dvx=[];dvy=[];relx=[];rely=[];kx=[];ky=[];ts=0;b=circles[0]
  for k,w in enumerate(circles[1:]):
   gx=sat((s32(b[0]-w[0])>>4)+(gsx[k]<<4),16);gy=sat((s32(b[1]-w[1])>>4)+(gsy[k]<<4),16)
   x=sat(s32(w[0]-b[0])>>8,16);y=sat(s32(w[1]-b[1])>>8,16)
   rx=s32(b[2]-w[2]-sat((oms*y+512)>>10,32));ry=s32(b[3]-w[3]+sat((oms*x+512)>>10,32))
   dvx.append(s32(coeff(gx,'C_SPRING_W')+coeff(rx,'C_FRIC_W')));dvy.append(s32(coeff(gy,'C_SPRING_W')+coeff(ry,'C_FRIC_W')))
   ts=s32(ts+gsx[k]*gy-gsy[k]*gx);relx.append(rx);rely.append(ry);kx.append(x);ky.append(y)
  inp=b''.join(struct.pack('<iiiiIh',*v,0,0)for v in circles)+struct.pack('<hhhhi',*gsx,*gsy,oms)
  want=struct.pack('<iiiiiiiihhhhi',*dvx,*dvy,*relx,*rely,*kx,*ky,ts)
  assert len(inp)==78 and len(want)==44
  rows.append((inp,want))
 vals=[0,1,-1,32767,-32768,32768,-32769,65536,-65536,0x7fffffff,-0x80000000]
 for i,v in enumerate(vals):
  for j,u in enumerate(vals):
   row([(v,u,vals[(i+3)%len(vals)],vals[(j+5)%len(vals)]),(u,v,-32768,32767),(s32(-v),s32(-u),v,u)],[32767,-32768],[-32768,32767],vals[(i+j)%len(vals)])
 for _ in range(384):
  row([tuple(rng.randint(-2**31,2**31-1)for _ in range(4))for _ in range(3)],[rng.randint(-32768,32767)for _ in range(2)],[rng.randint(-32768,32767)for _ in range(2)],rng.randint(-2**31,2**31-1))
 for _ in range(256):
  row([tuple(rng.randint(-500000,500000)for _ in range(4))for _ in range(3)],[rng.randint(-2048,2048)for _ in range(2)],[rng.randint(-2048,2048)for _ in range(2)],rng.randint(-100000,100000))
 header='#include <stdint.h>\ntypedef struct{uint8_t input[78],output[44];}vec_t;\n';sources=[]
 for bank,start in zip([1,2,3,4,5,6,7,9,10],range(0,len(rows),100)):
  block=rows[start:start+100];header+=f'extern const vec_t vecs{bank}[];\n#define N{bank} {len(block)}\n';source=out/f'vecs{bank}.c';source.write_text(f'#pragma bank {bank}\n#include "vectors.h"\nconst vec_t vecs{bank}[]={{\n'+',\n'.join('{{'+','.join(map(str,x))+'},{'+','.join(map(str,y))+'}}'for x,y in block)+'\n};\n');sources.append((bank,source))
 (out/'vectors.h').write_text(header)
 driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "vectors.h"
uint8_t Bike[109],arena[64];vec_t copy;
volatile uint8_t done;volatile uint16_t failures,guards,count,banks_bad;
int32_t riding_suspension32(const int16_t*,const int16_t*,int32_t,int32_t*,int32_t*,void*)__sdcccall(0);
void check(void){uint8_t i;int32_t oms,ts;memcpy(Bike,copy.input,66);memcpy(&oms,copy.input+74,4);memset(arena,0xa5,64);SWITCH_ROM(8);ts=riding_suspension32((const int16_t*)(copy.input+66),(const int16_t*)(copy.input+70),oms,(int32_t*)(arena+7),(int32_t*)(arena+15),arena+23);memcpy(arena+47,&ts,4);if(CURRENT_BANK!=8)++banks_bad;for(i=0;i<44;++i)if(arena[7+i]!=copy.output[i])++failures;for(i=0;i<64;++i)if((i<7||i>=51)&&arena[i]!=0xa5)++guards;++count;}
void main(void){uint16_t i;disable_interrupts();DISPLAY_OFF;cpu_fast();
'''
 for bank,_ in sources:driver+=f'for(i=0;i<N{bank};++i){{SWITCH_ROM({bank});memcpy(&copy,&vecs{bank}[i],sizeof(copy));check();}}\n'
 driver+='done=1;while(1){}}\n';(out/'driver.c').write_text(driver)
 tables=sum((sorted(gen.glob(glob))for glob in('physics_coefficient_*.c','physics_quarter_*.c','physics_scale_*.c')),[])
 common=[base/'src'/f for f in('physics_math32.c','physics_math32.s','physics_mul_fast.s','physics_kmul_fast.s','physics_anchor_fast.s')]
 cmd=[base/'.toolchain/gbdk/bin/lcc','-msm83:gb','-Wf--opt-code-size','-DRIDING_COEFFICIENT_LOOKUP','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(out),'-I'+str(gen),'-I'+str(base/'src'),'-o',out/'check.gbc',out/'driver.c',a.assembly,*common,*[v for _,v in sources],*tables,gen/'physics_coefficient_calls.s']
 result=subprocess.run(list(map(str,cmd)),capture_output=True,text=True);(out/'compile.log').write_text(result.stdout+result.stderr);assert result.returncode==0,(out/'compile.log').read_text()
 symbols={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(out/'check.noi').read_text())};emu=PyBoy(str(out/'check.gbc'),window='null',sound_emulated=False,cgb=True);emu.set_emulation_speed(0);started=[];cycles=[];returns=set()
 def returned(_):
  if started and started[-1][0]==emu.register_file.SP-2:cycles.append(emu._cycles()-started.pop()[1])
 def entered(_):
  sp=emu.register_file.SP;pc=emu.memory[sp]+256*emu.memory[sp+1]
  if pc not in returns:emu.hook_register(0,pc,returned,None);returns.add(pc)
  started.append((sp,emu._cycles()))
 emu.hook_register(8,symbols['_riding_suspension32']&65535,entered,None)
 try:
  for _ in range(300):
   emu.tick(100,False)
   if emu.memory[symbols['_done']]:break
  def n(name,size=2):return int.from_bytes(bytes(emu.memory[symbols['_'+name]:symbols['_'+name]+size]),'little')
  report={name:n(name)for name in('failures','guards','count','banks_bad')};report.update(done=n('done',1),expected_cases=len(rows),cycles={'min':min(cycles),'max':max(cycles),'mean':sum(cycles)/len(cycles)})
  (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));assert report['done']and report['count']==len(rows)and not(report['failures']or report['guards']or report['banks_bad'])
 finally:emu.stop(save=False)
if __name__=='__main__':main()
