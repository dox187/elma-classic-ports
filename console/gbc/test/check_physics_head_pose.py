"""Exhaustive native head pose with frozen C and independent integer oracle."""
import argparse,json,re,struct,subprocess
from pathlib import Path
from pyboy import PyBoy
B=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gen',type=Path,default=B/'build/gen-8m');p.add_argument('--out',type=Path,default=B/'build/physics-head-pose-check');args=p.parse_args()
G=args.gen.resolve();O=args.out.resolve();O.mkdir(parents=True,exist_ok=True)
ref='#pragma bank 8\n#include "physics_core.h"\n#include "physics_math.h"\nint16_t Cs,Sn;\nstatic void angle( void ) {\n\tuint16_t a = (uint16_t)((Bike.body.alfa + 64u) >> RIDING_ANGLE_SHIFT);\n\tCs = fcos( a );\n\tSn = fsin( a );\n}\n\n/* Rider, renderer and head collision all observe the same completed step. */\nvoid head_reference(void) {\n int32_t x=Bike.rider_x,y=Bike.rider_y;\n int16_t hc,hs;\n angle();hc=KMUL(Cs,C_H_X);hs=KMUL(Sn,C_H_X);\n if(!Bike.turned){hc=-hc;hs=-hs;}\n Bike.head_x=x+(int32_t)(hc-KMUL(Sn,C_H_Y))*256L;\n Bike.head_y=y+(int32_t)(hs+KMUL(Cs,C_H_Y))*256L;\n}\n'
(O/'reference.c').write_text(ref)
(O/'driver.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "physics_core.h"
uint8_t riding_subphase;uint8_t before_guard[8];bike_t Bike;uint8_t after_guard[8];uint8_t original[sizeof(Bike)],want[sizeof(Bike)];
int16_t got_cs,got_sn;extern int16_t Cs,Sn;
const int32_t boundaries[16]={(-2147483647L-1L),-2147483647L,2147483647L,2147483646L,-16777216L,-65536L,-256L,-1L,0L,1L,255L,256L,65535L,65536L,16777215L,16777216L};
volatile uint8_t done,ready;volatile uint32_t count,failures,cache_failures,guards,banks_bad;volatile uint16_t phase;
void riding_head_pose32(int16_t*,int16_t*)__sdcccall(0);void head_reference(void);
void marker(void) {++ready;}
void main(void){uint16_t i;uint8_t t,k;uint32_t seed=0x9179cba1ul;disable_interrupts();DISPLAY_OFF;cpu_fast();
for(i=0;i<sizeof(Bike);++i)((uint8_t*)&Bike)[i]=(uint8_t)(i*79+23);
memset(before_guard,0xa5,8);memset(after_guard,0xa5,8);SWITCH_ROM(8);
phase=0;do { for(t=0;t<2;++t){
 Bike.body.alfa=((uint32_t)phase<<7)|(((uint32_t)phase*0x59d5b76dul)&0xff80003ful)|(t?64ul:0ul);
 seed=seed*1664525ul+1013904223ul;Bike.rider_x=(phase&31)==31?(int32_t)seed:boundaries[phase&15];
 seed=seed*1664525ul+1013904223ul;Bike.rider_y=(phase&31)==31?(int32_t)seed:boundaries[(phase>>4)&15];
 Bike.turned=t?255:0;memcpy(original,&Bike,sizeof(Bike));
 head_reference();memcpy(want,&Bike,sizeof(Bike));memcpy(&Bike,original,sizeof(Bike));
 riding_head_pose32(&got_cs,&got_sn);
 for(k=0;k<sizeof(Bike);++k)if(((uint8_t*)&Bike)[k]!=want[k])++failures;
 if(got_cs!=Cs||got_sn!=Sn)++cache_failures;
 if(CURRENT_BANK!=8)++banks_bad;
 for(k=0;k<8;++k)if(before_guard[k]!=0xa5||after_guard[k]!=0xa5)++guards;
 ++count;marker();
 }}while(++phase);
 done=1;while(1){} }
''')
tables = [path for pattern in ('physics_quarter_*.c', 'physics_scale_*.c', 'physics_sine_*.c', 'physics_q24_table_*.c')
          for path in sorted(G.glob(pattern))]
common = [B/'src'/name for name in ('physics_math.c', 'physics_math.s', 'physics_mul_fast.s',
          'physics_mul16u8.s', 'physics_sin_fast.s', 'physics_q24.c', 'physics_q24.s')]
cmd = [B/'.toolchain/gbdk/bin/lcc', '-msm83:gb', '-Wf--opt-code-size', '-Wm-yC',
       '-Wm-yt0x19', '-Wm-yoA', '-Wl-m', '-Wl-j', '-I'+str(G), '-I'+str(B/'src'),
       '-o', O/'check.gbc', O/'driver.c', O/'reference.c', B/'src/physics_geometry.c', B/'src/physics_pose_lookup.s', B/'src/physics_head_pose.s',
       *common, *tables, G/'physics_q24_dispatch.c']
r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True);(O/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,(O/'compile.log').read_text()
symbols={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(O/'check.noi').read_text())};emu=PyBoy(str(O/'check.gbc'),window='null',sound_emulated=False,cgb=True);emu.set_emulation_speed(0);started=[];cycles={'geometry':[],'reference':[]};returns=set();oracle_failures=[];oracle_seen=[0]
def returned(_):
 if started and started[-1][0]==emu.register_file.SP-2:
  sp,when,name=started.pop();cycles[name].append(emu._cycles()-when)
def entered(name):
 sp=emu.register_file.SP;pc=emu.memory[sp]+256*emu.memory[sp+1]
 if pc not in returns:emu.hook_register(0,pc,returned,None);returns.add(pc)
 started.append((sp,emu._cycles(),name))
for name,sym in [('geometry','_riding_head_pose32'),('reference','_head_reference')]:emu.hook_register(symbols[sym]>>16,symbols[sym]&65535,entered,name)
sintab=[int(x)for x in re.search(r'Sintab\[257\] = \{(.*?)\};',(B/'src/physics_math.c').read_text(),re.S)[1].replace('\n','').split(',')if x.strip()]
def s32(v):return (v+2**31)%2**32-2**31
def phase_sin(a):a&=65535;i=a>>8;return sintab[i]+((sintab[i+1]-sintab[i])*(a&255)>>8)
def marker(_):
 a=symbols['_Bike'];state=bytes(emu.memory[a:a+119]);phase=(int.from_bytes(state[16:20],'little')+64)>>7&65535;sn=phase_sin(phase);cs=phase_sin(phase+16384)
 hx=(cs*94372+(1<<23))>>24;hy=(sn*94372+(1<<23))>>24
 if not state[96]:hx=-hx;hy=-hy
 hx-=((sn*660603+(1<<23))>>24);hy+=((cs*660603+(1<<23))>>24)
 x=int.from_bytes(state[72:76],'little',signed=True);y=int.from_bytes(state[76:80],'little',signed=True)
 want=(s32(x+hx*256),s32(y+hy*256),cs,sn)
 got=(int.from_bytes(state[88:92],'little',signed=True),int.from_bytes(state[92:96],'little',signed=True),n('got_cs',2,True),n('got_sn',2,True))
 def scaled(v, factor): return (v*factor+(1<<23))>>24
 ax,ay,bx,by=scaled(cs,228170138),scaled(sn,161061274),scaled(sn,228170138),scaled(cs,161061274)
 want+=(-scaled(sn,7381975),scaled(cs,7381975),ay-ax,ay+ax,-bx-by,bx-by)
 for symbol,fmt in [('_riding_pose_rest','<2h'),('_riding_pose_anchor','<4i')]:
  at=symbols[symbol]; got+=struct.unpack(fmt,bytes(emu.memory[at:at+struct.calcsize(fmt)]))
 if want!=got and len(oracle_failures)<10:oracle_failures.append(dict(phase=phase,want=want,got=got))
 oracle_seen[0]+=1
def n(name,size=4,signed=False):return int.from_bytes(bytes(emu.memory[symbols['_'+name]:symbols['_'+name]+size]),'little',signed=signed)
emu.hook_register(0,symbols['_marker'],marker,None)
try:
 for _ in range(1600):
  emu.tick(100,False)
  if emu.memory[symbols['_done']]:break
 report={name:n(name)for name in('failures','cache_failures','guards','count','banks_bad')};report.update(boundary_coordinates=16,all_phase_values=65536,turn_values=[0,255],discarded_angle_bits='varied high9 and low7',done=n('done',1),oracle_seen=oracle_seen[0],oracle_failures=oracle_failures,cycles={name:dict(min=min(v),max=max(v),mean=sum(v)/len(v),count=len(v))for name,v in cycles.items()})
 if len(cycles['geometry'])==len(cycles['reference']):
  savings=[a-b for a,b in zip(cycles['reference'],cycles['geometry'])];report['savings']=dict(min=min(savings),max=max(savings),mean=sum(savings)/len(savings))
 (O/'cycles.json').write_text(json.dumps(cycles)+'\n');(O/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));assert report['done']and report['count']==131072 and not oracle_failures and not any(report[x]for x in('failures','cache_failures','guards','banks_bad'))
finally:emu.stop(save=False)
