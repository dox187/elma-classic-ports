"""Native exact reaction-table index across signed lever boundaries."""
from pathlib import Path
import random,struct,subprocess,re,json,argparse
from pyboy import PyBoy
B=Path(__file__).resolve().parents[1];parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=B/'build/recip-check');parser.add_argument('--assembly',type=Path,default=B/'src/physics_recip_fast.s');args=parser.parse_args();P=args.out.resolve();P.mkdir(parents=True,exist_ok=True);r=random.Random(78941)
cases=[(x,0)for x in range(-32768,32768,16)]+[(r.randint(-32768,32767),r.randint(-32768,32767))for _ in range(4096)]
want=lambda x,y:min(255,(min(127,max(-127,x>>4))**2+min(127,max(-127,y>>4))**2)>>5)
header='#include <stdint.h>\ntypedef struct{int16_t x,y;uint8_t want;}v_t;\n';sources=[]
for bank,start in zip([1,2,3,5,6,7,10,11,12],range(0,len(cases),1024)):
 block=cases[start:start+1024];name=f'vecs{bank}';header+=f'extern const v_t {name}[];\n#define N{bank} {len(block)}\n';path=P/(name+'.c');path.write_text(f'#pragma bank {bank}\n#include "vectors.h"\nconst v_t {name}[]={{'+','.join('{'+f'{x},{y},{want(x,y)}'+'}'for x,y in block)+'};\n');sources.append((bank,path))
(P/'vectors.h').write_text(header)
s='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "vectors.h"
uint8_t riding_recip_index(int16_t x,int16_t y)__sdcccall(0);
volatile uint8_t done;volatile uint16_t count,failures,banks_bad;v_t c;
void check(void){uint8_t n;SWITCH_ROM(8);n=riding_recip_index(c.x,c.y);if(n!=c.want)++failures;if(CURRENT_BANK!=8)++banks_bad;++count;}
void main(void){uint16_t i;disable_interrupts();DISPLAY_OFF;cpu_fast();
'''
for bank,path in sources:s+=f'for(i=0;i<N{bank};++i){{SWITCH_ROM({bank});memcpy(&c,&vecs{bank}[i],5);check();}}\n'
s+='done=1;while(1){}}\n';(P/'driver.c').write_text(s)
subprocess.run([str(B/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(P),'-o',str(P/'check.gbc'),str(P/'driver.c'),str(args.assembly)]+[str(v)for _,v in sources],check=True,capture_output=True,text=True)
sy={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(P/'check.noi').read_text())};p=PyBoy(str(P/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0);starts=[];retset=set();cycles=[]
def returned(_):
 if starts and starts[-1][0]==p.register_file.SP-2:cycles.append(p._cycles()-starts.pop()[1])
def entered(_):
 sp=p.register_file.SP;ret=p.memory[sp]+256*p.memory[sp+1]
 if ret not in retset:p.hook_register(0,ret,returned,None);retset.add(ret)
 starts.append((sp,p._cycles()))
p.hook_register(8,sy['_riding_recip_index']&65535,entered,None)
for _ in range(300):
 p.tick(100,False)
 if p.memory[sy['_done']]:break
def n(key,size=2):return int.from_bytes(bytes(p.memory[sy['_'+key]:sy['_'+key]+size]),'little')
report={k:n(k)for k in('count','failures','banks_bad')};report.update(done=n('done',1),expected=len(cases),cycles={'min':min(cycles),'max':max(cycles),'mean':sum(cycles)/len(cycles)});(P/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(report);p.stop(save=False);assert report['done']and report['count']==len(cases)and not(report['failures']or report['banks_bad'])
