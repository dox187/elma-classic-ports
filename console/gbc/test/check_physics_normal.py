"""Compare native normalization against independent signed integer formulas."""
from pathlib import Path
import argparse,hashlib,json,math,random,re,struct,subprocess,sys
from pyboy import PyBoy
B=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--quick',action='store_true');p.add_argument('--out',type=Path,default=B/'build/normal-check');p.add_argument('--gen',type=Path,default=B/'build/gen');p.add_argument('--assembly',type=Path,default=B/'src/physics_normal_fast.s');p.add_argument('--contacts',type=Path,default=B/'src/physics_contacts.c');a=p.parse_args();P=a.out.resolve();P.mkdir(parents=True,exist_ok=True);r=random.Random(41016384)
rs=[int(v)for v in re.findall(r'-?\d+',(B/'../nes/src/rsqrt.inc').read_text().split('\n',1)[1])]
sat=lambda v:max(-32768,min(32767,v));s16=lambda v:((v+32768)&65535)-32768;s32=lambda v:((v+2**31)&0xffffffff)-2**31
def expected(x,y,d2):
 if d2<16384:
  l=math.isqrt(d2)
  if not l:return(0,16384,0)
  trunc=lambda n:(abs(n)//l)*(-1 if n<0 else 1)
  return(s16(trunc(x<<14)),s16(trunc(y<<14)),l)
 index=((d2-16384)>>9)&65535;rr=rs[min(len(rs)-1,index)];nx,ny=sat((x*rr)>>4),sat((y*rr)>>4)
 return(nx,ny,sat(s32(nx*x+ny*y+8192)>>14))
step=13 if a.quick else 1
keys=[(x,y,x*x+y*y)for x in range(0,411,step)for y in range(0,411,step)]
keys += [(x,y,x*x+y*y)for x,y in ((r.randint(-410,410),r.randint(-410,410))for _ in range(4096 if a.quick else 8192))]
for index in range(297):
 d2=16384+index*512+255
 for x in(-32768,-32767,-410,-1,0,1,410,32767):keys.append((x,-x if x!=-32768 else 32767,d2))
for d2 in(0,1,16383,16384,16895,16896,168100,334562,33570816,33570817,0x40004000,0x7fffffff):
 for x,y in((0,0),(1,-1),(410,-410),(-32768,-32768),(32767,32767),(-32768,32767)):
  keys.append((x,y,d2))
rows=[(key,struct.pack('<hhh',*expected(*key)))for key in keys]
header='#include <stdint.h>\ntypedef struct{int16_t x,y;int32_t d;uint8_t want[6];}v_t;\n';sources=[]
for bank,start in enumerate(range(0,len(rows),1000),44):
 block=rows[start:start+1000];header+=f'extern const v_t vectors{bank}[];\n#define N{bank} {len(block)}\n';path=P/f'normal_vectors{bank}.c';path.write_text(f'#pragma bank {bank}\n#include "normal_vectors.h"\nconst v_t vectors{bank}[]={{'+','.join('{'+f'{key[0]},{key[1]},{key[2]}L,'+'{'+','.join(map(str,want))+'}}'for key,want in block)+'};\n');sources.append((bank,path))
(P/'normal_vectors.h').write_text(header)
(P/'normal_case.c').write_text('''#include <gb/gb.h>
#include <stdint.h>
#include <string.h>
#include "normal_vectors.h"
#include "physics_core.h"
#pragma bank9
void seg_query(uint8_t a,uint8_t b,uint8_t c){}const seg_t *seg_next(void){return 0;}
void riding_normal_fast(int16_t,int16_t,int32_t,uint8_t*)__sdcccall(0);
extern v_t copy;uint8_t arena[288];
volatile uint32_t normal_cases,failures,guard_failures;volatile uint16_t bank_failures;volatile uint32_t first_bad_case;volatile uint8_t first_bad_byte;
void normal_case(void) BANKED {
 uint8_t j,pos8=(uint8_t)(normal_cases*37u);uint16_t pos=8u+pos8;
 for(j=0;j<24;++j)arena[pos-8+j]=(uint8_t)(j^normal_cases^0xa5);
 riding_normal_fast(copy.x,copy.y,copy.d,arena+pos);
 for(j=0;j<6;++j)if(arena[pos+j]!=copy.want[j]){if(!failures){first_bad_case=normal_cases;first_bad_byte=j;}++failures;}
 for(j=0;j<24;++j)if(j<8||j>=14){if(arena[pos-8+j]!=(uint8_t)(j^normal_cases^0xa5))++guard_failures;}
 if(CURRENT_BANK!=9)++bank_failures;++normal_cases;
}
'''.replace('#pragma bank9','#pragma bank 9'))
s='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "normal_vectors.h"
v_t copy;volatile uint8_t done;void normal_case(void) BANKED;
void main(void){uint16_t i;disable_interrupts();DISPLAY_OFF;cpu_fast();
'''
last_bank=sources[-1][0];last_count=len(rows)%1000 or 1000
s+=f'for(uint16_t bank=44;bank<={last_bank};++bank){{uint16_t count=bank=={last_bank}?{last_count}:1000;const v_t *v=(const v_t *)0x4000;SWITCH_ROM(bank);for(i=0;i<count;++i,++v){{memcpy(&copy,v,sizeof(copy));normal_case();}}}}\n'
s+='done=1;while(1){}}\n';(P/'normal_driver.c').write_text(s)
asm=[B/'src'/('physics_'+name+'.s')for name in('mul_fast','kmul_fast','math','div_fast','sqrt_fast','math32','move_fast','shift_fast')]+[a.assembly]
for marker,tool in (('physics_quarter_20.c','mul_table.py'),('physics_scale_36.c','scale_table.py')):
 if not (a.gen/marker).is_file():subprocess.run([sys.executable,str(B/'tools'/tool),'--out',str(a.gen)],check=True)
data=sorted(a.gen.glob('physics_quarter_*.c'))+sorted(a.gen.glob('physics_scale_*.c'))
cmd=[str(B/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-DPHYSICS_ASM','-Wf--opt-code-size','-Wf--max-allocs-per-node','-Wf100000','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-Wl-g_riding_coefficient_bank_lo=252','-Wl-g_riding_coefficient_bank_hi=0','-I'+str(P),'-I'+str(B/'src'),'-I'+str(a.gen),'-o',str(P/'normal_check.gbc'),str(P/'normal_driver.c'),str(P/'normal_case.c'),str(a.contacts),str(B/'src/physics_math.c'),str(B/'src/physics_math32.c')]+list(map(str,asm+data))+[str(v)for _,v in sources]
r=subprocess.run(cmd,capture_output=True,text=True);(P/'compile.log').write_text(r.stdout+r.stderr);assert not r.returncode,r.stdout+r.stderr
layout=(P/'normal_check.map').read_text()
for area in ('_CODE','_HOME'):
 for begin,size in re.findall(r'^'+area+r'\s+([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)',layout,re.M):
  assert int(begin,16)+int(size,16)<=0x4000,('ROM0 fixture overflow',area)
sy={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(P/'normal_check.noi').read_text())}
for bank,_ in sources:assert sy['_vectors%d'%bank]==(bank<<16)|0x4000
p=PyBoy(str(P/'normal_check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0);pending=[];retset=set();timings={name:{'calls':0,'min':2**63,'max':0,'total':0}for name in('deep','table')}
def returned(_):
 if pending and pending[-1][0]==p.register_file.SP-2:
  sp,start,name=pending.pop();v=p._cycles()-start;t=timings[name];t['calls']+=1;t['min']=min(t['min'],v);t['max']=max(t['max'],v);t['total']+=v

def entered(_):
 sp=p.register_file.SP;ret=p.memory[sp]+256*p.memory[sp+1];key=(9,ret)
 if key not in retset:p.hook_register(*key,returned,None);retset.add(key)
 adr=sy['_copy']+4;d2=int.from_bytes(bytes(p.memory[adr:adr+4]),'little',signed=True);pending.append((sp,p._cycles(),'deep'if d2<16384 else'table'))
address=sy['_riding_normal_fast'];p.hook_register(address>>16,address&65535,entered,None)
for _ in range(10000):
 p.tick(100,False)
 if p.memory[sy['_done']]:break
def n(key,size=4):return int.from_bytes(bytes(p.memory[sy['_'+key]:sy['_'+key]+size]),'little')
for t in timings.values():t['mean']=t['total']/t['calls']if t['calls']else None
report={k:n(k)for k in('normal_cases','failures','guard_failures','first_bad_case')};report.update(bank_failures=n('bank_failures',2),first_bad_byte=n('first_bad_byte',1),done=n('done',1),expected=len(rows),timings=timings,exhaustive_nonnegative=not a.quick)
(P/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));p.stop(save=False);assert report['done']and report['normal_cases']==len(rows)and not any(report[k]for k in('failures','guard_failures','bank_failures'))
