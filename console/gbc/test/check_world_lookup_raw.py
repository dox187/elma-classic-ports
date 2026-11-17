"""Native direct-ID SRAM lookup versus the linked oracle, including fallback.

Checks every direct ID, allocator slot and bank/count boundary; no game state is injected.
"""
from pathlib import Path
import argparse,json,re,subprocess,hashlib,time
from pyboy import PyBoy
B=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,default=B/'build/world-lookup-raw-check');args=parser.parse_args();O=args.out.resolve();O.mkdir(parents=True,exist_ok=True)
reference=(B/'src/world_lookup_linked.s').read_text().replace('_world_','_reference_world_');(O/'reference.s').write_text(reference)
(O/'driver.c').write_text(r'''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
void world_lookup_clear(uint16_t)__sdcccall(0);
void world_lookup_raw_clear(uint16_t)__sdcccall(0);
uint16_t world_lookup_get(uint16_t)__sdcccall(0);
void world_lookup_set(uint16_t,uint16_t)__sdcccall(0);
void world_lookup_insert_absent(uint16_t,uint16_t)__sdcccall(0);
void reference_world_lookup_clear(uint16_t)__sdcccall(0);
uint16_t reference_world_lookup_get(uint16_t)__sdcccall(0);
void reference_world_lookup_set(uint16_t,uint16_t)__sdcccall(0);
void reference_world_lookup_insert_absent(uint16_t,uint16_t)__sdcccall(0);
extern uint8_t world_lookup_direct;
volatile uint8_t done,phase;
volatile uint16_t failures,bank_failures,guard_failures,mode_failures,first_bad=65535;
volatile uint32_t checks;
static const uint16_t counts[]={0,1,4095,4096,4097,8191,8192,8193,12287,12288,12289,12300,27639,28410,65535};
static const uint16_t ids[]={0,1,4094,4095,4096,4097,8190,8191,8192,8193,12286,12287};
static void bad(uint16_t id){if(!failures)first_bad=id;++failures;}
static void bank(void){if(*(volatile uint8_t*)0xb800!=0xa5)++bank_failures;}
static void compare(uint16_t id){uint16_t a,b;*(volatile uint8_t*)0x4000=3;a=world_lookup_get(id);bank();b=reference_world_lookup_get(id);if(a!=b)bad(id);++checks;}
static void init(void){reference_world_lookup_clear(65535);world_lookup_raw_clear(12288);}
static void guards(void){uint16_t i;*(volatile uint8_t*)0x4000=0;for(i=0xaef0;i!=0xc000;++i)if(*(volatile uint8_t*)i!=0xa5)++guard_failures;}
void main(void){uint16_t id,i,j,slot,old;uint8_t full=0;disable_interrupts();DISPLAY_OFF;cpu_fast();*(volatile uint8_t*)0x0000=10;*(volatile uint8_t*)0x4000=0;for(i=0xaef0;i!=0xc000;++i)*(volatile uint8_t*)i=0xa5;
 init();phase=1;
 for(id=0;id<12300;++id){
  if(id>=12288){world_lookup_set(id,id%444);if(world_lookup_get(id)!=65535)bad(id);bank();++checks;continue;}
  slot=id%444;if(id>=444){old=id-444;world_lookup_set(old,65535);bank();reference_world_lookup_set(old,65535);compare(old);}
  compare(id);*(volatile uint8_t*)0x4000=2;world_lookup_insert_absent(id,slot);bank();reference_world_lookup_insert_absent(id,slot);compare(id);
 }
 for(id=0;id<12300;++id){if(id<12288)compare(id);else{if(world_lookup_get(id)!=65535)bad(id);++checks;}}
 guards();phase=2;
 for(i=0;i<sizeof(counts)/sizeof(counts[0]);++i){world_lookup_raw_clear(counts[i]);bank();if(world_lookup_direct!=(counts[i]<=12288))++mode_failures;
  for(j=0;j<sizeof(ids)/sizeof(ids[0]);++j){id=ids[j];if(world_lookup_get(id)!=65535)bad(id);world_lookup_set(id,j);if(world_lookup_get(id)!=j)bad(id);++checks;}
  if(counts[i]>12288){world_lookup_set(65535,443);if(world_lookup_get(65535)!=443)bad(65535);world_lookup_set(65535,65535);if(world_lookup_get(65535)!=65535)bad(65535);++checks;}
  guards();
 }
 phase=3;init();
 for(i=0;i<12;++i){id=1023+(i<<10);world_lookup_insert_absent(id,i);reference_world_lookup_insert_absent(id,i);}
 for(i=0;i<12;i+=2){id=1023+(i<<10);world_lookup_set(id,65535);reference_world_lookup_set(id,65535);}
 for(i=1;i<12;i+=2){id=1023+(i<<10);world_lookup_set(id,i+128);reference_world_lookup_set(id,i+128);}
 for(i=0;i<12;++i){id=1023+(i<<10);compare(id);world_lookup_set(id,i+256);reference_world_lookup_set(id,i+256);compare(id);}
 for(i=0;i<12;++i){id=1023+(i<<10);world_lookup_set(id,65535);reference_world_lookup_set(id,65535);}
 for(i=0;i<444;++i){id=i;world_lookup_set(id,i);reference_world_lookup_set(id,i);compare(id);world_lookup_set(id,65535);reference_world_lookup_set(id,65535);compare(id);}
 guards();phase=4;world_lookup_clear(0);if(world_lookup_direct)++mode_failures;
 /* Compressed clear never touches the three scratch banks. */
 for(i=1;i<4;++i){*(volatile uint8_t*)0x4000=i;for(id=0xa000;id!=0xc000;++id)*(volatile uint8_t*)id=0x90+i;}
 world_lookup_clear(12288);bank();for(i=1;i<4;++i){*(volatile uint8_t*)0x4000=i;for(id=0xa000;id!=0xc000;++id)if(*(volatile uint8_t*)id!=0x90+i)++guard_failures;}
 *(volatile uint8_t*)0x4000=0;guards();done=1;while(1){}
}''')
cmd=[str(B/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x1a','-Wm-ya4','-Wm-yoA','-Wl-m','-Wl-j','-Wa-l','-o',str(O/'check.gbc'),str(O/'driver.c'),str(O/'reference.s'),str(B/'src/world_lookup_raw.s')]
r=subprocess.run(cmd,capture_output=True,text=True);(O/'compile.log').write_text(r.stdout+r.stderr);assert not r.returncode,r.stdout+r.stderr
sy={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(O/'check.noi').read_text())};p=PyBoy(str(O/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0);pending=[];returns=set();timing={}
def returned(key):
 if pending and pending[-1]['sp']+2==p.register_file.SP and pending[-1]['key']==key:
  call=pending.pop();timing.setdefault(call['name'],[]).append(p._cycles()-call['start'])
def entered(name):
 if p.memory[sy['_phase']]!=1 and not name.endswith('clear'):return
 sp=p.register_file.SP;key=(0,p.memory[sp]+256*p.memory[sp+1]);
 if key not in returns:p.hook_register(*key,returned,key);returns.add(key)
 pending.append({'sp':sp,'key':key,'name':name,'start':p._cycles()})
for n in ['world_lookup_get','world_lookup_set','world_lookup_insert_absent','reference_world_lookup_get','reference_world_lookup_set','reference_world_lookup_insert_absent','world_lookup_raw_clear','reference_world_lookup_clear']:p.hook_register(0,sy['_'+n],entered,n)
t=time.monotonic()
for _ in range(1000):
 p.tick(100,False)
 if p.memory[sy['_done']]:break
def n(k,size=2):return int.from_bytes(bytes(p.memory[sy['_'+k]:sy['_'+k]+size]),'little')
report={k:n(k)for k in ['failures','bank_failures','guard_failures','mode_failures','first_bad']};report.update(done=n('done',1),phase=n('phase',1),checks=n('checks',4),seconds=time.monotonic()-t,timing={k:{'calls':len(v),'min':min(v),'max':max(v),'mean':sum(v)/len(v)}for k,v in timing.items()});(O/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True);p.stop(save=False);assert report['done']and not any(report[k]for k in ['failures','bank_failures','guard_failures','mode_failures'])
