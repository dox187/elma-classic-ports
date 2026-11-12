"""Exact arithmetic byte-drop vectors across signed32 bit patterns."""
from pathlib import Path
import subprocess,random,re,json,argparse
from pyboy import PyBoy
B=Path(__file__).resolve().parents[1];parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=B/'build/shift-check');parser.add_argument('--assembly',type=Path,default=B/'src/physics_shift_fast.s');args=parser.parse_args();P=args.out.resolve();P.mkdir(parents=True,exist_ok=True);r=random.Random(845487)
values=[0,1,-1,2**31-1,-2**31]+[v for i in range(31)for v in(1<<i,-(1<<i),(1<<i)-1,-(1<<i)+1)]+[r.randint(-2**31,2**31-1)for _ in range(4096)]
h='#include <stdint.h>\ntypedef struct{int32_t x,y;}v_t;\n';sources=[]
for bank,start in enumerate(range(0,len(values),1800),1):
 rows=values[start:start+1800];h+=f'extern const v_t vectors{bank}[];\n#define N{bank} {len(rows)}\n';p=P/f'vecs{bank}.c';p.write_text(f'#pragma bank {bank}\n#include "vectors.h"\nconst v_t vectors{bank}[]={{'+','.join('{'+str(v)+','+str(v>>8)+'}'for v in rows)+'};\n');sources.append((bank,p))
(P/'vectors.h').write_text(h)
s='''#include <gb/gb.h>
#include <gb/cgb.h>
#include "vectors.h"
int32_t riding_sra8(int32_t x);
volatile uint8_t done;volatile uint16_t failures,cases,bank_failures;
void check(const v_t *v){uint8_t b=CURRENT_BANK;int32_t got=riding_sra8(v->x);if(got!=v->y)++failures;if(CURRENT_BANK!=b)++bank_failures;++cases;}
void main(void){uint16_t i;disable_interrupts();DISPLAY_OFF;cpu_fast();
'''
for bank,p in sources:s+=f'SWITCH_ROM({bank});for(i=0;i<N{bank};++i)check(&vectors{bank}[i]);\n'
s+='done=1;while(1){}}\n';(P/'driver.c').write_text(s)
subprocess.run([str(B/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(P),'-o',str(P/'check.gbc'),str(P/'driver.c'),str(args.assembly)]+[str(p)for _,p in sources],check=True,capture_output=True,text=True)
sy={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(P/'check.noi').read_text())};p=PyBoy(str(P/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0);pending=[];cycles=[];retset=set()
def returned(_):
 if pending and pending[-1][0]==p.register_file.SP-2:cycles.append(p._cycles()-pending.pop()[1])
def entered(_):
 sp=p.register_file.SP;ret=p.memory[sp]+256*p.memory[sp+1]
 if ret not in retset:p.hook_register(0,ret,returned,None);retset.add(ret)
 pending.append((sp,p._cycles()))
p.hook_register(0,sy['_riding_sra8'],entered,None)
for _ in range(300):
 p.tick(100,False)
 if p.memory[sy['_done']]:break
def n(key,size=2):return int.from_bytes(bytes(p.memory[sy['_'+key]:sy['_'+key]+size]),'little')
report={k:n(k)for k in('cases','failures','bank_failures')};report.update(done=n('done',1),expected=len(values),cycles={'min':min(cycles),'max':max(cycles),'mean':sum(cycles)/len(cycles)});(P/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(report);p.stop(save=False);assert report['done']and report['cases']==len(values)and not(report['failures']or report['bank_failures'])
