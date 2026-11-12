"""Native exact spring/lever coordinate vectors, guards and bank checks."""
from pathlib import Path
import random,struct,json,re,subprocess,argparse
from pyboy import PyBoy
BASE=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=BASE/'build/anchor-check');parser.add_argument('--assembly',type=Path,default=BASE/'src/physics_anchor_fast.s');args=parser.parse_args();P=args.out.resolve();P.mkdir(parents=True,exist_ok=True);r=random.Random(532256)
def s32(x):return((x+2**31)&0xffffffff)-2**31
def sat(x):return max(-32768,min(32767,x))
cases=[]
vals=[0,1,-1,0x7fffffff,-0x80000000,32767,-32768,32768,-32769,524288,-524288,8388607,-8388608]
for i,x in enumerate(vals):
 for j,y in enumerate(vals):
  for a in(0,1,-1,32767,-32768,8192,-8192):cases.append((x,y,vals[(i+2)%len(vals)],vals[(j+4)%len(vals)],a,-a if a!=-32768 else 32767))
for _ in range(1024):cases.append(tuple(r.randint(-2**31,2**31-1)for _ in range(4))+tuple(r.randint(-32768,32767)for _ in range(2)))
rows=[]
for bx,by,wx,wy,ax,ay in cases:
 dx,dy=s32(bx-wx),s32(by-wy)
 want=(sat((dx>>4)+(ax<<4)),sat((dy>>4)+(ay<<4)),sat(s32(-dx)>>8),sat(s32(-dy)>>8))
 rows.append((struct.pack('<iiiihh',bx,by,wx,wy,ax,ay),struct.pack('<hhhh',*want)))
header='#include <stdint.h>\ntypedef struct{uint8_t input[20],output[8];}vec_t;\n'
sources=[];banks=[1,2,3,5,6,7,10,11,12,13,14]
for bank,start in zip(banks,range(0,len(rows),500)):
 block=rows[start:start+500];name=f'vecs{bank}';header+=f'extern const vec_t {name}[];\n#define N{bank} {len(block)}\n';source=P/f'{name}.c';source.write_text(f'#pragma bank {bank}\n#include "vectors.h"\nconst vec_t {name}[]={{\n'+',\n'.join('{{'+','.join(map(str,a))+'},{'+','.join(map(str,b))+'}}'for a,b in block)+'\n};\n');sources.append((bank,source))
(P/'vectors.h').write_text(header)
driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
#include <string.h>
#include "vectors.h"
uint8_t Bike[109],wheel[22],arena[24];vec_t copy;
volatile uint8_t done;volatile uint16_t failures,guards,count,banks_bad;
void riding_anchor32(uint8_t *wheel,int16_t ax,int16_t ay,int16_t *out)__sdcccall(0);
void check(void){uint8_t i;int16_t ax,ay;memcpy(Bike,copy.input,8);memcpy(wheel,copy.input+8,8);memcpy(&ax,copy.input+16,2);memcpy(&ay,copy.input+18,2);memset(arena,0xa5,24);SWITCH_ROM(8);riding_anchor32(wheel,ax,ay,(int16_t *)(arena+7));if(CURRENT_BANK!=8)++banks_bad;for(i=0;i<8;++i)if(arena[7+i]!=copy.output[i])++failures;for(i=0;i<24;++i)if((i<7||i>=15)&&arena[i]!=0xa5)++guards;++count;}
void main(void){uint16_t i;disable_interrupts();DISPLAY_OFF;cpu_fast();
'''
for bank,source in sources:driver+=f'for(i=0;i<N{bank};++i){{SWITCH_ROM({bank});memcpy(&copy,&vecs{bank}[i],sizeof(copy));check();}}\n'
driver+='done=1;while(1){}}\n';(P/'driver.c').write_text(driver)
cmd=[str(BASE/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(P),'-o',str(P/'check.gbc'),str(P/'driver.c'),str(args.assembly)]+[str(v)for _,v in sources]
subprocess.run(cmd,check=True,capture_output=True,text=True)
s={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(P/'check.noi').read_text())};p=PyBoy(str(P/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0);starts=[];cycles=[];retset=set()
def ret(key):
 if starts and starts[-1][0]==p.register_file.SP-2:cycles.append(p._cycles()-starts.pop()[1])
def enter(_):
 sp=p.register_file.SP;retpc=p.memory[sp]+256*p.memory[sp+1]
 if retpc not in retset:p.hook_register(0,retpc,ret,retpc);retset.add(retpc)
 starts.append((sp,p._cycles()))
p.hook_register(8,s['_riding_anchor32']&65535,enter,None)
for _ in range(300):
 p.tick(100,False)
 if p.memory[s['_done']]:break
def n(name,n=2):return int.from_bytes(bytes(p.memory[s['_'+name]:s['_'+name]+n]),'little')
report={name:n(name)for name in('failures','guards','count','banks_bad')};report.update(done=n('done',1),expected_cases=len(cases),cycles={'min':min(cycles),'max':max(cycles),'mean':sum(cycles)/len(cycles)})
(P/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));p.stop(save=False);assert report['done']and report['count']==len(cases)and not(report['failures']or report['guards']or report['banks_bad'])
