"""Native paired check: frozen generic SM83 oracle, fixed helper, Python model.

Fixture-only state injection covers the fixed cache; gameplay inputs are captured
separately from an unchanged full ROM using controller-only play.
"""
import collections,hashlib,json,random,re,struct,subprocess,time
from pathlib import Path
from pyboy import PyBoy
B=Path(__file__).resolve().parents[1]
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out',type=Path,default=B/'build/retire-check')
parser.add_argument('--captured',type=Path)
args=parser.parse_args();P=args.out.resolve();P.mkdir(parents=True,exist_ok=True)
(P/'oracle.s').write_bytes((B/'test/fixtures/world_retire_generic.s').read_bytes())
(P/'world_refs_retire_fixed.s').write_bytes((B/'src/world_retire_fast.s').read_bytes())
(P/'driver.c').write_text('#include <gb/gb.h>\n#include <gb/cgb.h>\nvoid run(void) BANKED;\nvolatile uint16_t irq_count;\nvolatile uint8_t finished;\nstatic void irq(void){++irq_count;}\nvoid main(void){\n disable_interrupts();DISPLAY_OFF;cpu_fast();ENABLE_RAM;SWITCH_RAM(2);\n add_TIM(irq);TMA_REG=0;TAC_REG=4;set_interrupts(TIM_IFLAG);disable_interrupts();\n run();finished=1;while(1){}\n}\n')
(P/'check.c').write_text('#include <gb/gb.h>\n#include <stdint.h>\n#pragma bank 6\nuint8_t guard0[8];uint16_t world_cache_references[444];uint8_t guard1[8];\nuint8_t world_cache_free_bits[56];uint8_t guard2[8];\nuint16_t retired[255];uint8_t count;\nuint8_t irq_mode;\nvolatile uint8_t done;\nconst uint8_t marker=0x5a;\nvoid world_refs_retire(uint16_t *,const uint16_t *,uint8_t,uint8_t *) __sdcccall(0);\nvoid world_refs_retire_fixed(const uint16_t *,uint8_t) __sdcccall(0);\nvoid fixture_ready(void) __sdcccall(0){}\nvoid fixture_oracle_done(void) __sdcccall(0){}\nvoid fixture_candidate_done(void) __sdcccall(0){}\nvoid run(void) BANKED {\n for(;;){\n  fixture_ready();\n  if(done)return;\n  if(irq_mode)enable_interrupts();else disable_interrupts();\n  world_refs_retire(world_cache_references,retired,count,world_cache_free_bits);\n  fixture_oracle_done();\n  world_refs_retire_fixed(retired,count);\n  fixture_candidate_done();\n }\n}\n')
captured_rows=json.loads(args.captured.read_text())['rows']if args.captured else []
cmd=[str((B/'.toolchain/gbdk/bin/lcc').resolve()),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x1a','-Wm-ya4','-Wm-yoA','-Wl-m','-Wl-j','-Wa-l','-o',str(P/'check.gbc')]+[str(P/x)for x in ['driver.c','check.c','oracle.s','world_refs_retire_fixed.s']]
r=subprocess.run(cmd,capture_output=True,text=True);(P/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
for stem,source in [('candidate','world_refs_retire_fixed.s'),('oracle','oracle.s')]:
 r=subprocess.run([str((B/'.toolchain/gbdk/bin/lcc').resolve()),'-msm83:gb','-c','-o',str(P/(stem+'.o')),str(P/source)],capture_output=True,text=True);assert r.returncode==0,r.stdout+r.stderr
sy={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(P/'check.noi').read_text())}
p=PyBoy(str(P/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0)
rng=random.Random(0x9444)
def vectors():
 for value in range(65536):
  refs=[0]*444;slot=value%444;refs[slot]=value
  yield 'exhaustive16',refs,[slot],bytes([0xa4]*56),0
 for slot in range(444):
  for value in [0,1,2,255,256,257,511,512,65280,65535]:
   refs=[1]*444;refs[slot]=value
   yield 'every_slot',refs,[slot],bytes(rng.randrange(256)for _ in range(56)),0
 for count in [0,1,2,19,21,39,40,255]:
  for value in [0,1,2,255,256,257,65535]:
   for duplicate in [False,True]:
    slots=[(443 if duplicate else (i*53)%444)for i in range(count)]
    yield f'count{count}/ref{value}/dup{int(duplicate)}',[value]*444,slots,bytes([0x80]*56),0
 for i in range(1024):
  refs=[rng.choice([0,1,2,255,256,257,65535,rng.randrange(65536)])for _ in range(444)]
  slots=[rng.randrange(444)for _ in range(i%41)]
  yield 'random',refs,slots,bytes(rng.randrange(256)for _ in range(56)),0
 for row in captured_rows:
  yield 'captured_update'+str(row['update']),row['refs'],row['slots'],bytes(row['bits']),0
 for i in range(256):
  yield 'irq_enabled',[1+(i&1)]*444,[(i+j)%444 for j in range(40)],bytes([0x40]*56),1
it=iter(vectors());current={};counts=collections.Counter();timing=collections.defaultdict(lambda:collections.defaultdict(list));errors=[];pending=[];registered=set();n=0
guard=bytes([0xa5]*8);sram=[bytes((i*37+bank*13+91)&255 for i in range(8192))for bank in range(4)];sram_initialized=False
def addr(name):return sy['_'+name]&65535
def read(name,length):a=addr(name);return bytes(p.memory[a:a+length])if length else b''
def write(name,data):
 if data:a=addr(name);p.memory[a:a+len(data)]=data
def words(v):return struct.pack('<'+'H'*len(v),*v)
def fail(kind,detail=None):
 if len(errors)<10:errors.append({'case':n,'kind':kind,'label':current.get('label'),'detail':detail})
def put_input():
 write('world_cache_references',current['before']);write('world_cache_free_bits',current['bits'])
def ready(_):
 global current,n,sram_initialized
 if not sram_initialized:
  for bank,data in enumerate(sram):p.memory[bank,0xa000:0xbfff]=data[:-1];p.memory[bank,0xbfff]=data[-1]
  sram_initialized=True
 try:label,refs,slots,bits,irq=next(it)
 except StopIteration:p.memory[addr('done')]=1;return
 expected=refs.copy();expected_bits=bytearray(bits)
 for slot in slots:
  if expected[slot]:
   expected[slot]-=1
   if not expected[slot]:expected_bits[slot>>3]|=1<<(slot&7)
 current={'label':label,'before':words(refs),'bits':bits,'expected':words(expected),'expected_bits':bytes(expected_bits),'slots':words(slots),'irq':irq}
 put_input();write('retired',current['slots']);p.memory[addr('count')]=len(slots);p.memory[addr('irq_mode')]=irq
 for g in ['guard0','guard1','guard2']:write(g,guard)
 n+=1;counts[label]+=1
def compare(kind):
 if read('world_cache_references',888)!=current['expected']:fail(kind+'_refs')
 if read('world_cache_free_bits',56)!=current['expected_bits']:fail(kind+'_bits')
 if any(read(g,8)!=guard for g in ['guard0','guard1','guard2']):fail(kind+'_guards')
 if read('retired',len(current['slots']))!=current['slots']:fail(kind+'_list')
 if p.memory[sy['__current_bank']]!=6 or p.memory[addr('marker')]!=0x5a:fail(kind+'_rom_bank')
 if p.memory[0xa000]!=sram[2][0] or p.memory[0xffff]!=4:fail(kind+'_ram_or_IE')
def oracle_done(_):compare('oracle');put_input()
def candidate_done(_):compare('candidate')
def returned(key):
 if pending and pending[-1][0]==p.register_file.SP-2:
  sp,t,kind,label=pending.pop();timing[label][kind].append(p._cycles()-t)
def entered(kind):
 sp=p.register_file.SP;ret=p.memory[sp]+256*p.memory[sp+1];bank=6 if ret>=0x4000 else 0;key=(bank,ret)
 if key not in registered:p.hook_register(bank,ret,returned,key);registered.add(key)
 pending.append((sp,p._cycles(),kind,current['label']))
for name,fn in [('fixture_ready',ready),('fixture_oracle_done',oracle_done),('fixture_candidate_done',candidate_done)]:
 a=sy['_'+name];p.hook_register(a>>16,a&65535,fn,None)
for name,kind in [('world_refs_retire','oracle'),('world_refs_retire_fixed','fixed')]:
 a=sy['_'+name];p.hook_register(a>>16,a&65535,entered,kind)
t=time.monotonic()
for k in range(50000):
 p.tick(100,False)
 if p.memory[addr('finished')]:break
for bank,data in enumerate(sram):
 actual=bytes(p.memory[bank,0xa000:0xbfff])+bytes([p.memory[bank,0xbfff]])
 if actual!=data:fail('protected_sram',bank)
summary={label:{kind:{'calls':len(v),'min':min(v),'max':max(v),'mean':sum(v)/len(v)}for kind,v in kinds.items()}for label,kinds in timing.items()}
for kinds in summary.values():kinds['mean_saved']=kinds['oracle']['mean']-kinds['fixed']['mean']
report={'cases':n,'done':p.memory[addr('finished')],'errors':errors,'counts':dict(counts),'timing':summary,'irq_count':int.from_bytes(read('irq_count',2),'little'),'seconds':time.monotonic()-t,'oracle_sha256':hashlib.sha256((P/'oracle.s').read_bytes()).hexdigest(),'oracle_still_current':(P/'oracle.s').read_bytes()==(B/'test/fixtures/world_retire_generic.s').read_bytes(),'candidate_sha256':hashlib.sha256((P/'world_refs_retire_fixed.s').read_bytes()).hexdigest(),'candidate_bytes':88,'added_RAM':0}
report['candidate_bytes']=int(re.search(r'A _CODE_6 size ([0-9A-F]+)',(P/'candidate.o').read_text()).group(1),16)
report['oracle_bytes']=int(re.search(r'A _CODE size ([0-9A-F]+)',(P/'oracle.o').read_text()).group(1),16)
report['source_still_current']=(P/'world_refs_retire_fixed.s').read_bytes()==(B/'src/world_retire_fast.s').read_bytes()
(P/'report.json').write_text(json.dumps(report,indent=2)+'\n');p.stop(save=False)
print(json.dumps({k:v for k,v in report.items()if k not in ['counts','timing']},indent=2));print(json.dumps({k:v for k,v in summary.items()if k.startswith('captured')or k in ['count0/ref1/dup0','count40/ref1/dup0','count40/ref0/dup0','count40/ref256/dup0','count40/ref65535/dup0']},indent=2))
assert report['cases']==71368+len(captured_rows)and report['done']and not errors and report['oracle_still_current']and report['source_still_current']and report['irq_count']
