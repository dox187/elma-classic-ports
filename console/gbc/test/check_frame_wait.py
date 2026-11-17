"""Exercise conditional VBlank waiting on the native SM83."""
from pathlib import Path
import json,re,subprocess,hashlib
from pyboy import PyBoy
import argparse
parser=argparse.ArgumentParser(description='Check the first-frame wait across LCD phases, IRQs and counter wrap.')
parser.add_argument('--out',type=Path)
a=parser.parse_args();B=Path(__file__).resolve().parents[1]
O=(a.out or B/'build/frame-wait-check').resolve();O.mkdir(parents=True,exist_ok=True)
source=(B/'src/play.c').read_text()
helper=source[source.index('void game_wait_first_frame('):source.index('void main(void)')]
(O/'wait-helper.c').write_text('#include <gb/gb.h>\n#include <stdint.h>\n'+helper)
(O/'driver.c').write_text(r'''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
void game_wait_first_frame(uint16_t start) NONBANKED;
volatile uint16_t cases,failures,timer_count,wait_start,wait_end;
volatile uint8_t done,irq_mode,epoch,age,phase,first_bad;
static void timer(void){++timer_count;}
void main(void){uint16_t now;uint8_t pending;
 cpu_fast();DISPLAY_ON;add_TIM(timer);TMA_REG=240;TIMA_REG=240;TAC_REG=4;
 for(irq_mode=0;irq_mode<2;++irq_mode){set_interrupts(VBL_IFLAG|(irq_mode?TIM_IFLAG:0));enable_interrupts();
 for(epoch=0;epoch<3;++epoch)for(age=0;age<3;++age)for(phase=0;phase<154;++phase){
  __critical {sys_time=epoch==0?400:epoch==1?65535:0;}
  while(LY_REG!=phase);
  __critical {now=sys_time;if(IF_REG&VBL_IFLAG)++now;}
  wait_start=now-age;
  game_wait_first_frame(wait_start);
  __critical {wait_end=sys_time;pending=IF_REG&VBL_IFLAG;}
  if(pending)++wait_end;
  if(!age && (uint16_t)(wait_end-wait_start)!=1){if(!failures)first_bad=1;++failures;}
  if(age && (uint16_t)(wait_end-wait_start)>age+1){if(!failures)first_bad=2;++failures;}
  ++cases;
 }}done=1;while(1)vsync();}
''')
cmd=[str(B/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size','-Wf--max-allocs-per-node','-Wf100000','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-o',str(O/'check.gbc'),str(O/'driver.c'),str(O/'wait-helper.c')];r=subprocess.run(cmd,capture_output=True,text=True);(O/'compile.log').write_text(r.stdout+r.stderr);assert not r.returncode,r.stdout+r.stderr
sy={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(O/'check.noi').read_text())};p=PyBoy(str(O/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0);calls=[];pending=[];returns=set()
def word(n):a=sy['_'+n];return p.memory[a]+256*p.memory[a+1]
def returned(key):
 if pending and pending[-1]['sp']==p.register_file.SP-2:
  c=pending.pop();c['cycles']=p._cycles()-c.pop('cycle');calls.append(c)
def entered(_):
 sp=p.register_file.SP
 if pending and pending[-1]['sp']==sp:return
 ret=p.memory[sp]+256*p.memory[sp+1]
 if ret not in returns:p.hook_register(0,ret,returned,ret);returns.add(ret)
 pending.append(dict(sp=sp,cycle=p._cycles(),age=p.memory[sy['_age']],irq_mode=p.memory[sy['_irq_mode']],phase=p.memory[sy['_phase']],epoch=p.memory[sy['_epoch']]))
p.hook_register(0,sy['_game_wait_first_frame'],entered,None)
for n in range(1000):
 p.tick(100,False)
 if p.memory[sy['_done']]:break
report={k:word(k)for k in ['cases','failures','timer_count']};report.update(done=p.memory[sy['_done']],expected=2*3*3*154,first_bad=p.memory[sy['_first_bad']],calls=len(calls),immediate_max=max(c['cycles']for c in calls if c['age']),wait_max=max(c['cycles']for c in calls if not c['age']),immediate_over_3000=[c for c in calls if c['age']and c['cycles']>3000],rom_sha256=hashlib.sha256((O/'check.gbc').read_bytes()).hexdigest());(O/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));p.stop(save=False);assert report['done']and report['cases']==report['expected']and not report['failures']and not report['immediate_over_3000']

assert helper in (B/"src/play.c").read_text()
