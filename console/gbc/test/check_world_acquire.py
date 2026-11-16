"""Native complete cache-metadata equivalence against an independent C scan.

The upload stub records arguments; the full world-cache fixture separately checks
actual VRAM bytes, old/new visible views, cancellation and display deadlines.
"""
from pathlib import Path
import random,re,subprocess,json,argparse
from pyboy import PyBoy
B=Path(__file__).resolve().parents[1];parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=B/'build/world-acquire-check');parser.add_argument('--assembly',type=Path,default=B/'src/world_acquire_fast.s');args=parser.parse_args();P=args.out.resolve();P.mkdir(parents=True,exist_ok=True);r=random.Random(441443)
cases=[]
for mode in range(4):cases += [(mode,i,(i+443)%444,r.randrange(65536))for i in range(444)]
cases += [(4,i,0,r.randrange(65536))for i in(0,1,7,8,255,256,439,440,443)]
cases += [(r.choice((5,6)),r.randrange(444),r.randrange(444),r.randrange(65536))for _ in range(1024)]
sources=[];header='#include <stdint.h>\ntypedef struct{uint8_t mode;uint16_t next,sel,seed;}v_t;\n'
for bank,start in enumerate(range(0,len(cases),1000),1):
 block=cases[start:start+1000];header+=f'extern const v_t vectors{bank}[];\n#define N{bank} {len(block)}\n';path=P/f'vectors{bank}.c';path.write_text(f'#pragma bank {bank}\n#include "vectors.h"\nconst v_t vectors{bank}[]={{'+','.join('{'+','.join(map(str,row))+'}'for row in block)+'};\n');sources.append(path)
(P/'vectors.h').write_text(header)
(P/'case.c').write_text(r'''#include <gb/gb.h>
#include <stdint.h>
#include <string.h>
#include "vectors.h"
#pragma bank 6
uint8_t guard0[8];uint16_t world_cache_ids[444];uint8_t guard1[8];
uint16_t world_cache_references[444];uint8_t guard2[8];uint8_t world_cache_free_bits[56];uint8_t guard3[8];
uint16_t world_cache_next,world_cache_failures,world_uploads,uploaded_slot,uploaded_id;
static uint16_t want_ids[444],want_refs[444],want_lookup[444],want_next,want_fail,want_uploads,want_uploaded_slot,want_uploaded_id,want_return,want_high[2];
static uint8_t want_bits[56];
volatile uint16_t cases_done,case_id,failures,bank_failures,guard_failures,first_bad_case,first_bad_kind,first_bad_index;
extern v_t row;
const uint8_t marker=0x5a;
uint16_t world_lookup_get(uint16_t)__sdcccall(0);
void world_lookup_set(uint16_t,uint16_t)__sdcccall(0);
void world_lookup_clear(uint16_t)__sdcccall(0);
uint16_t world_acquire_fast(uint16_t)__sdcccall(0);
void world_cache_upload(uint16_t slot,uint16_t id)__sdcccall(0){++world_uploads;uploaded_slot=slot;uploaded_id=id;}
static const uint8_t masks[8]={1,2,4,8,16,32,64,128};
uint16_t reference_acquire(uint16_t id)__sdcccall(0){
 uint16_t slot=world_lookup_get(id),old,n;
 if(slot<444){if(!world_cache_references[slot])world_cache_free_bits[slot>>3]&=~masks[slot&7];++world_cache_references[slot];return slot;}
 slot=world_cache_next;
 if(world_cache_references[slot]){
  for(n=0;n<444;++n){if(world_cache_free_bits[slot>>3]&masks[slot&7])break;if(++slot==444)slot=0;}
  if(n==444){++world_cache_failures;return 0;}
 }
 world_cache_free_bits[slot>>3]&=~masks[slot&7];world_cache_next=slot+1;if(world_cache_next==444)world_cache_next=0;
 old=world_cache_ids[slot];if(old!=65535)world_lookup_set(old,65535);
 world_cache_upload(slot,id);world_cache_ids[slot]=id;world_cache_references[slot]=1;world_lookup_set(id,slot);return slot;
}
static uint16_t setup(void){
 uint16_t i,random=row.seed,free=(row.next+row.sel)%444,input;
 if(free==row.next)free=(free+1)%444;
 /* Reset fixed-capacity mapping before recreating this independent fixture. */
 world_lookup_clear(0);
 memset(world_cache_free_bits,0,56);
 for(i=0;i<444;++i){
  uint16_t ref=1+(i&255),id=1024+i;
  if(row.mode==1&&i==row.sel)ref=0;
  if(row.mode==2&&i==row.next)ref=0;
  if(row.mode==3&&i==free)ref=0;
  if(row.mode==5){random=random*109U+89U;ref=(random&7)?1+(random&255):0;}
  if(row.mode==6){ref=0;if((i+row.seed)&3)id=65535;}
  if(row.mode==0&&i==row.sel&&row.seed&1)ref=65535;
  world_cache_references[i]=ref;world_cache_ids[i]=id;
  world_lookup_set(1024+i,id==65535?65535:i);
  if(!ref)world_cache_free_bits[i>>3]|=masks[i&7];
 }
 world_lookup_set(60000,65535);world_lookup_set(60001,65535);
 world_cache_next=row.next;world_cache_failures=row.seed;world_uploads=row.seed;uploaded_slot=65535;uploaded_id=65535;
 memset(guard0,0xa5,8);memset(guard1,0xa5,8);memset(guard2,0xa5,8);memset(guard3,0xa5,8);
 input=row.mode<2?1024+row.sel:60000+(row.seed&1);return input;
}
static void bad(uint8_t kind,uint16_t i){if(!failures){first_bad_case=case_id;first_bad_kind=kind;first_bad_index=i;}++failures;}
void unit_case(void) BANKED {
 uint16_t input,i,got;
 input=setup();want_return=reference_acquire(input);
 memcpy(want_ids,world_cache_ids,888);memcpy(want_refs,world_cache_references,888);memcpy(want_bits,world_cache_free_bits,56);
 for(i=0;i<444;++i)want_lookup[i]=world_lookup_get(1024+i);
 want_high[0]=world_lookup_get(60000);want_high[1]=world_lookup_get(60001);
 want_next=world_cache_next;want_fail=world_cache_failures;want_uploads=world_uploads;want_uploaded_slot=uploaded_slot;want_uploaded_id=uploaded_id;
 input=setup();got=world_acquire_fast(input);
 if(got!=want_return)bad(1,got);
 for(i=0;i<444;++i){if(world_cache_ids[i]!=want_ids[i])bad(2,i);if(world_cache_references[i]!=want_refs[i])bad(3,i);if(world_lookup_get(1024+i)!=want_lookup[i])bad(4,i);}
 for(i=0;i<56;++i)if(world_cache_free_bits[i]!=want_bits[i])bad(5,i);
 if(world_lookup_get(60000)!=want_high[0]||world_lookup_get(60001)!=want_high[1])bad(6,0);
 if(world_cache_next!=want_next||world_cache_failures!=want_fail||world_uploads!=want_uploads||uploaded_slot!=want_uploaded_slot||uploaded_id!=want_uploaded_id)bad(7,0);
 for(i=0;i<8;++i)if(guard0[i]!=0xa5||guard1[i]!=0xa5||guard2[i]!=0xa5||guard3[i]!=0xa5)++guard_failures;
 if(CURRENT_BANK!=6||*(volatile const uint8_t *)&marker!=0x5a)++bank_failures;
 ++cases_done;
}
''')
s='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "vectors.h"
v_t row;volatile uint8_t done;extern volatile uint16_t case_id;void unit_case(void)BANKED;void world_lookup_clear(uint16_t)__sdcccall(0);
void main(void){uint16_t i;disable_interrupts();DISPLAY_OFF;cpu_fast();world_lookup_clear(65535);
'''
for bank,start in enumerate(range(0,len(cases),1000),1):s+=f'for(i=0;i<N{bank};++i){{SWITCH_ROM({bank});memcpy(&row,&vectors{bank}[i],sizeof(row));case_id={start}+i;unit_case();}}\n'
s+='done=1;while(1){}}\n';(P/'driver.c').write_text(s)
cmd=[str(B/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size','-Wf--max-allocs-per-node','-Wf100000','-Wm-yC','-Wm-yt0x1a','-Wm-ya4','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(P),'-o',str(P/'check.gbc'),str(P/'driver.c'),str(P/'case.c'),str(args.assembly),str(B/'src/world_memory.s'),str(B/'src/world_alloc_fast.s')]+list(map(str,sources))
r=subprocess.run(cmd,capture_output=True,text=True);(P/'compile.log').write_text(r.stdout+r.stderr);assert not r.returncode,r.stdout+r.stderr
rom=(P/'check.gbc').read_bytes();assert rom[0x149]==3
sy={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(P/'check.noi').read_text())};p=PyBoy(str(P/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0);pending=[];registered=set();timing={'asm':{},'reference':{}}
def returned(key):
 if pending and pending[-1][0]==p.register_file.SP-2:
  sp,t,name,mode=pending.pop();timing[name].setdefault(mode,[]).append(p._cycles()-t)
def entered(name):
 sp=p.register_file.SP;ret=p.memory[sp]+256*p.memory[sp+1];bank=p.memory[sy['__current_bank']]if ret>=0x4000 else 0;key=(bank,ret)
 if key not in registered:p.hook_register(bank,ret,returned,key);registered.add(key)
 mode=p.memory[sy['_row']];pending.append((sp,p._cycles(),name,mode))
for key,name in(('asm','_world_acquire_fast'),('reference','_reference_acquire')):
 address=sy[name];p.hook_register(address>>16,address&65535,entered,key)
for _ in range(3000):
 p.tick(100,False)
 if p.memory[sy['_done']]:break
def n(key,size=2):return int.from_bytes(bytes(p.memory[sy['_'+key]:sy['_'+key]+size]),'little')
report={k:n(k)for k in('cases_done','failures','bank_failures','guard_failures','first_bad_case','first_bad_kind','first_bad_index')};report.update(done=n('done',1),expected=len(cases),timing={name:{mode:{'calls':len(v),'min':min(v),'max':max(v),'mean':sum(v)/len(v)}for mode,v in modes.items()}for name,modes in timing.items()});(P/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));p.stop(save=False);assert report['done']and report['cases_done']==len(cases)and not any(report[k]for k in('failures','bank_failures','guard_failures'))
