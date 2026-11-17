"""Pair native raw strip reads against frozen C and individual plane reads."""
from pathlib import Path
import json,re,subprocess,hashlib
from pyboy import PyBoy
import argparse
parser=argparse.ArgumentParser(description='Check native raw strip clipping and three-plane ROM gathering.')
parser.add_argument('--gen',type=Path)
parser.add_argument('--out',type=Path)
a=parser.parse_args()
B=Path(__file__).resolve().parents[1]
G=(a.gen or B/'build/gen-8m').resolve()
F=(a.out or B/'build/raw-fetch-check').resolve();F.mkdir(parents=True,exist_ok=True)
source_hashes={n:hashlib.sha256((B/'src'/n).read_bytes()).hexdigest()for n in ('world.c','world_memory.s')}
def function(src,new):
 s=src[src.index('static uint8_t fetch_strip('):].split('\nstatic void load_strip(',1)[0];return s.replace('static uint8_t fetch_strip(','uint8_t '+new+'(')
pre='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
#include <string.h>
#include "world.h"
#include "world_memory.h"
#pragma bank 6
world_level_t game_world;
static world_far_t chunk;
static uint16_t last_chunk;
static uint8_t data[3][23],expected[3][23];
#define strip_low (data[0]+1)
#define strip_high (data[1]+1)
#define strip_attrs (data[2]+1)
void world_far_gather3(uint16_t bank,const uint8_t *source,uint8_t *low,uint8_t *high,uint8_t *attrs,uint8_t count,uint8_t stride) __sdcccall(0);
volatile uint16_t failures,first_bad,done_cases,irq_count;
volatile uint8_t done,phase;
'''
case=pre+function((B/'test/fixtures/world_fetch_c.c').read_text(),'reference_fetch')+'\n'+function((B/'src/world.c').read_text(),'candidate_fetch')
case+='''
static void check_one(uint16_t x,uint16_t y,uint8_t vertical,uint8_t count,uint8_t offset,uint8_t partial,uint16_t last,uint16_t bank,uint16_t address) {
 uint8_t a,b;uint16_t reference_last;world_far_t reference_chunk;
 memset(data,0xa5,sizeof(data));last_chunk=last;chunk.bank=bank;chunk.address=address;
 a=reference_fetch(x,y,vertical,count,offset,partial);
 reference_last=last_chunk;reference_chunk=chunk;memcpy(expected,data,sizeof(data));
 memset(data,0xa5,sizeof(data));last_chunk=last;chunk.bank=bank;chunk.address=address;
 b=candidate_fetch(x,y,vertical,count,offset,partial);
 if(a!=b||memcmp(data,expected,sizeof(data))||last_chunk!=reference_last||memcmp(&chunk,&reference_chunk,sizeof(chunk))||CURRENT_BANK!=6){if(!failures)first_bad=done_cases;++failures;}
 ++done_cases;
}
void run_cases(void) BANKED {
 uint16_t i,j,x,y,source,bank;uint8_t n,offset,v,k;
 static const uint16_t banks[]={255,256,500,511};
 static const uint16_t coords[]={0,1,14,15,16,17,30,31,32,33,47,48,63,64,65,95,96,97,65520,65535};
 phase=2;memset(&game_world,0,sizeof(game_world));game_world.width=768;game_world.height=512;game_world.chunks_x=3;game_world.chunks_y=4;game_world.chunks.bank=14;game_world.chunks.address=0x4000;
 for(i=0;i<8000;++i){x=coords[i%20];y=coords[(i/20)%20];v=(i/400)&1;offset=(i/800)%7;n=(i*13)%(22-offset);check_one(x,y,v,n,offset,(i/1600)&1,65535,0,0);}
 phase=3;
 for(k=0;k<8;++k)for(v=0;v<2;++v)for(n=0;n<=21;++n)for(offset=0;offset+n<=21;++offset){
  bank=banks[k&3];source=k<4?0x4003:(v?0x797f:0x7beb);
  memset(data,0xa5,sizeof(data));memset(expected,0xa5,sizeof(expected));
  for(j=0;j<3;++j)world_far_gather(bank,(const uint8_t *)(source+j*512),expected[j]+1+offset,n,v?32:1);
  world_far_gather3(bank,(const uint8_t *)source,strip_low+offset,strip_high+offset,strip_attrs+offset,n,v?32:1);
  if(memcmp(data,expected,sizeof(data))||CURRENT_BANK!=6){if(!failures)first_bad=done_cases;++failures;}++done_cases;
 }
 done=1;
}
'''
(F/'case.c').write_text(case)
(F/'driver.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
extern volatile uint16_t irq_count;
void isr(void){++irq_count;}
void run_cases(void) BANKED;
void main(void){disable_interrupts();DISPLAY_OFF;cpu_fast();
#ifdef STRESS_IRQ
add_VBL(isr);DISPLAY_ON;set_interrupts(VBL_IFLAG);enable_interrupts();
#endif
run_cases();while(1){}}
''')
# Distinct synthetic planes exercise both sides of the ninth ROM bank bit.
banks={}
for b in [255,256,500,501,511]:banks[b]=bytes((i*37+(i>>8)*19+b*13+(b>>8)*91)&255 for i in range(16384))
files=[]
for bank,raw in banks.items():
 path=F/f'data{bank}.c';path.write_text('#include <stdint.h>\n#pragma bank %d\nconst uint8_t data%d[]={\n'%(bank,bank)+','.join(map(str,raw))+'\n};\n');files.append(str(path))
(F/'catalogue.c').write_text('#include "world.h"\n#pragma bank 14\nconst world_far_t directory[]={'+','.join('{%d,%d}'%(500+i//10,0x4000+(i%10)*1536)for i in range(12))+'};\n');files.append(str(F/'catalogue.c'))
flags=[str(B/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size','-Wf--max-allocs-per-node','-Wf100000','-Wm-yC','-Wm-yt0x19','-Wm-yo512','-Wl-m','-Wl-j','-I'+str(G),'-I'+str(B/'src')]
reports=[]
for stress in [False,True]:
 target=F/('irq.gbc'if stress else 'check.gbc');cmd=flags+(['-DSTRESS_IRQ=1']if stress else [])+['-Wa-l','-o',str(target),str(F/'driver.c'),str(F/'case.c'),str(B/'src/world_memory.s')]+files
 r=subprocess.run(cmd,capture_output=True,text=True);(F/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
 sy={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',target.with_suffix('.noi').read_text())};p=PyBoy(str(target),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0);timing={'reference':[],'candidate':[]};pending=[];retset=set()
 def returned(key):
  if pending and pending[-1][0]==p.register_file.SP-6:
   sp,start,name,phase=pending.pop();timing[name].append([phase,p._cycles()-start])
 def entered(name):
  sp=p.register_file.SP
  if pending and pending[-1][0]==sp and pending[-1][2]==name:return
  ret=p.memory[sp]+256*p.memory[sp+1];key=(6,ret)
  if key not in retset:p.hook_register(*key,returned,key);retset.add(key)
  pending.append((sp,p._cycles(),name,p.memory[sy['_phase']]))
 if not stress:
  for name in ['reference','candidate']:
   a=sy['_'+name+'_fetch'];p.hook_register(a>>16,a&65535,entered,name)
 for i in range(2000):
  p.tick(100,False)
  if p.memory[sy['_done']]:break
 def num(n,size=2):return int.from_bytes(bytes(p.memory[sy['_'+n]:sy['_'+n]+size]),'little')
 report={k:num(k)for k in ['failures','first_bad','done_cases','irq_count']};report['done']=num('done',1);report['irq']=stress;report['sha256']=hashlib.sha256(target.read_bytes()).hexdigest();report['source_sha256']=source_hashes
 if not stress:
  report['timing']=timing
 reports.append(report);p.stop(save=False);print({k:v for k,v in report.items()if k!='timing'},flush=True);assert report['done']and report['done_cases']==12048 and not report['failures']and(not stress or report['irq_count']),report
(F/'report.json').write_text(json.dumps(reports,indent=2)+'\n')
assert all(hashlib.sha256((B/'src'/n).read_bytes()).hexdigest()==h for n,h in source_hashes.items())
