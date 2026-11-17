"""Exact wide signed32 x signed16 Q14: independent integer / frozen native C."""
from pathlib import Path
import argparse,hashlib,json,random,re,subprocess
from pyboy import PyBoy
B=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--captures',type=Path,help='JSON list of captured [x,y,shift] calls')
p.add_argument('--gen',type=Path,default=B/'build/gen-8m')
p.add_argument('--out',type=Path,default=B/'build/physics-mulq-wide-check')
p.add_argument('--assembly',type=Path,default=B/'src/physics_math32.s')
p.add_argument('--implementation',type=Path,default=B/'src/physics_math32.c')
p.add_argument('--lcc',type=Path,default=B/'.toolchain/gbdk/bin/lcc')
a=p.parse_args();F=B;G=a.gen.resolve();O=a.out.resolve();O.mkdir(parents=True,exist_ok=True)
r=random.Random(0x914814);rows=[]
def add(x,y,s=14):
 if -2**31<=x<2**31 and -32768<=y<32768:rows.append((x,y,s,max(-2**31,min(2**31-1,(x*y+(1<<(s-1)))>>s))))
xs=[-2**31,-2**31+1,-2**30,-65537,-65536,-65535,-32769,-32768,-32767,-1,0,1,32767,32768,32769,65535,65536,65537,2**30-1,2**30,2**31-2,2**31-1]
ys=[-32768,-32767,-16385,-16384,-8192,-257,-256,-1,0,1,255,256,257,8192,16384,16385,32766,32767]
for x in xs:
 for y in ys:add(x,y)
for y in ys:
 if not y:continue
 for target in [-2**45-8192,-2**45,2**45-8193,2**45-8192,2**45]:
  x=target//y
  for d in range(-3,4):add(x+d,y)
for hi in [-32768,-16384,-1,0,1,16384,32767]:
 for lo in [0,1,8191,8192,8193,16383,16384,32767,32768,49152,57343,57344,57345,65535]:
  for y in [-32768,-16384,-1,0,1,16384,32767]:add((hi<<16)+lo,y)
for _ in range(2400):add(r.randint(-2**31,2**31-1),r.randint(-32768,32767))
for x in xs:
 for y in [-32768,-1,0,1,32767]:
  for s in [1,10,13,15,16]:add(x,y,s)
captures=json.loads(a.captures.read_text())if a.captures else[]
for v in captures:add(*v)
header='#include <stdint.h>\ntypedef struct{int32_t x;int16_t y;uint8_t shift;int32_t expected;}vec_t;\n';sources=[]
for bank,start in enumerate(range(0,len(rows),512),60):
 block=rows[start:start+512];header+=f'extern const vec_t vecs{bank}[];\n#define N{bank} {len(block)}\n';path=O/f'vecs{bank}.c';path.write_text(f'#pragma bank {bank}\n#include "vectors.h"\nconst vec_t vecs{bank}[]={{\n'+',\n'.join('{'+f'{x}L,{y},{s},{w}L'+'}'for x,y,s,w in block)+'\n};\n');sources.append((bank,path))
(O/'vectors.h').write_text(header)
(O/'frozen_dispatch.s').write_text('.module mulq32_frozen_dispatch\n.area _CODE\n_riding_mulq32_frozen::\n ldhl sp,#8\n ld a,(hl)\n cp a,#10\n jr z,mulq_frozen_mulq_check_x\n cp a,#14\n jr nz,mulq_frozen_mulq_wide\nmulq_frozen_mulq_check_x:\n ldhl sp,#3\n bit 7,(hl)\n jr nz,mulq_frozen_mulq_negative\n inc hl\n ld a,(hl+)\n or a,(hl)\n jr nz,mulq_frozen_mulq_wide\n jr mulq_frozen_mulq_product\nmulq_frozen_mulq_negative:\n inc hl\n ld a,(hl+)\n and a,(hl)\n inc a\n jr nz,mulq_frozen_mulq_wide\nmulq_frozen_mulq_product:\n ldhl sp,#6\n ld c,(hl)\n inc hl\n ld b,(hl)\n ldhl sp,#2\n ld e,(hl)\n inc hl\n ld d,(hl)\n call _riding_mul16_regs\n push hl\n ldhl sp,#10\n ld a,(hl)\n pop hl\n cp a,#10\n jp z,mulq_frozen_round10\n jp mulq_frozen_round14\nmulq_frozen_mulq_wide:\n jp _riding_mulq32_reference\n\nmulq_frozen_round10:\n ld a,d\n add a,#2\n ld d,a\n jr nc,mulq_frozen_shift10\n inc hl\nmulq_frozen_shift10:\n ld b,h\n sla d\n rl l\n rl h\n sla d\n rl l\n rl h\n sla d\n rl l\n rl h\n sla d\n rl l\n rl h\n sla d\n rl l\n rl h\n sla d\n rl l\n rl h\n ld e,l\n ld d,h\n ld a,b\n sra a\n sra a\n ld l,a\n add a,a\n sbc a,a\n ld h,a\n ret\nmulq_frozen_round14:\n ld a,d\n add a,#32\n ld d,a\n jr nc,mulq_frozen_shift14\n inc hl\nmulq_frozen_shift14:\n ld b,h\n sla d\n rl l\n rl h\n sla d\n rl l\n rl h\n ld e,l\n ld d,h\n ld a,b\n sra a\n sra a\n sra a\n sra a\n sra a\n sra a\n ld l,a\n add a,a\n sbc a,a\n ld h,a\n ret\n\n')
# Frozen native C from f975994; Python uses unbounded integers independently.
(O/'reference.c').write_text('#include "physics_math32.h"\ntypedef struct { uint16_t lo;uint32_t mid;int8_t top; } wide_t;\nextern const uint32_t riding_math32_positive_limit[17];\nint32_t riding_mul16(int16_t a,int16_t b) __sdcccall(0);\nint16_t kmul(int16_t x,uint8_t m,uint8_t e) __sdcccall(0);\n\nstatic void product(wide_t *out,int32_t x,int16_t y) {\n    int16_t lower=(int16_t)x,upper=(int16_t)(x>>16);\n    int32_t p=riding_mul16(lower,y),hi;\n    out->lo=(uint16_t)p;\n    /* The common signed16 input still retains the complete signed32 product. */\n    if((upper==0 && lower>=0)||(upper==-1 && lower<0))hi=p>>16;\n    else {\n        hi=p>>16;\n        if(lower<0)hi+=y; /* unsigned low-half correction */\n        if(upper)hi+=riding_mul16(upper,y);\n    }\n    out->mid=(uint32_t)hi;\n    out->top=hi<0 ? -1 : 0;\n}\n\nstatic int32_t finish(wide_t *v,uint8_t shift,uint8_t rounded) {\n    uint16_t previous;\n    uint32_t limit;\n    if(rounded) {\n        previous=v->lo;\n        v->lo+=(uint16_t)1U<<(shift-1);\n        if(v->lo<previous) {\n            if(++v->mid==0)++v->top;\n        }\n    }\n    limit=riding_math32_positive_limit[shift];\n    if(v->top>=0) {\n        if(v->top || v->mid>limit)return 2147483647L;\n    } else if(v->top!=-1 || v->mid<~limit)return (-2147483647L-1L);\n    if(shift==16)return (int32_t)v->mid;\n    return (int32_t)(((uint32_t)v->lo>>shift)|(v->mid<<(16-shift)));\n}\n\nint32_t riding_mulq32_reference(int32_t x,int16_t y,uint8_t shift) __sdcccall(0) {\n    wide_t value;\n    if(x==(int32_t)(int16_t)x)\n        return (riding_mul16((int16_t)x,y)+(1L<<(shift-1)))>>shift;\n    product(&value,x,y);\n    return finish(&value,shift,1);\n}\n\n')
driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "physics_math32.h"
#include "vectors.h"
int32_t riding_mulq32_frozen(int32_t,int16_t,uint8_t)__sdcccall(0);
uint8_t before_guard[8],after_guard[8];vec_t copy;
volatile uint8_t done,phase;volatile uint16_t failures,reference_failures,guards,count,banks_bad,irqs;
volatile uint16_t first_bad=65535;volatile int32_t first_actual;
void timer(void){++irqs;}
void check(void){int32_t actual;uint8_t i,bank=CURRENT_BANK;memset(before_guard,0xa5,8);memset(after_guard,0xa5,8);
 actual=riding_mulq32(copy.x,copy.y,copy.shift);if(actual!=copy.expected){++failures;if(first_bad==65535){first_bad=count;first_actual=actual;}}
 if(CURRENT_BANK!=bank||SVBK_REG!=0xff)++banks_bad;
 actual=riding_mulq32_frozen(copy.x,copy.y,copy.shift);if(actual!=copy.expected)++reference_failures;
 for(i=0;i<8;++i)if(before_guard[i]!=0xa5||after_guard[i]!=0xa5)++guards;++count;}
void main(void){uint16_t i;disable_interrupts();DISPLAY_OFF;cpu_fast();SVBK_REG=7;
'''
for bank,_ in sources:driver+=f'for(i=0;i<N{bank};++i){{SWITCH_ROM({bank});memcpy(&copy,&vecs{bank}[i],sizeof(copy));check();if(vecs{bank}[i].x!=copy.x)++banks_bad;}}\n'
driver+='phase=1;add_TIM(timer);TMA_REG=240;TIMA_REG=240;TAC_REG=4;set_interrupts(TIM_IFLAG);enable_interrupts();\n'
bank=sources[0][0];driver+=f'for(i=0;i<256;++i){{SWITCH_ROM({bank});memcpy(&copy,&vecs{bank}[i],sizeof(copy));check();if(vecs{bank}[i].x!=copy.x)++banks_bad;}}\n'
driver+='disable_interrupts();done=1;while(1){}}\n';(O/'driver.c').write_text(driver)
common=[a.implementation.resolve(),a.assembly.resolve(),F/'src/physics_mul_fast.s',F/'src/physics_kmul_fast.s']
source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in common}
tables=sorted(G.glob('physics_quarter_*.c'))+sorted(G.glob('physics_scale_*.c'))
cmd=[a.lcc.resolve(),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-Wl-g_riding_coefficient_bank_lo=221','-Wl-g_riding_coefficient_bank_hi=1','-I'+str(F/'src'),'-I'+str(O),'-o',O/'check.gbc',O/'driver.c',O/'reference.c',O/'frozen_dispatch.s',*common,*[v for _,v in sources],*tables]
rn=subprocess.run(list(map(str,cmd)),capture_output=True,text=True);(O/'compile.log').write_text(rn.stdout+rn.stderr);assert not rn.returncode,(O/'compile.log').read_text()
sym={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9a-fA-F]+)',(O/'check.noi').read_text())}
e=PyBoy(str(O/'check.gbc'),window='null',sound_emulated=False,cgb=True);e.set_emulation_speed(0);active=[];returns=set();records=[]
def returned(_):
 if not active or active[-1]['sp']!=e.register_file.SP-2:return
 v=active.pop();v['cycles']=e._cycles()-v.pop('start');sp=v.pop('sp');v['stack']=next((sp-i for i in range(sp-384,sp)if e.memory[i]!=0xa5),0);records.append(v)
def entered(name):
 sp=e.register_file.SP
 if active:return
 pc=e.memory[sp]+256*e.memory[sp+1]
 if pc not in returns:e.hook_register(0,pc,returned,None);returns.add(pc)
 x=int.from_bytes(bytes(e.memory[sp+2:sp+6]),'little',signed=True);y=int.from_bytes(bytes(e.memory[sp+6:sp+8]),'little',signed=True)
 for i in range(sp-384,sp):e.memory[i]=0xa5
 active.append(dict(name=name,sp=sp,start=e._cycles(),row=int.from_bytes(bytes(e.memory[sym['_count']:sym['_count']+2]),'little'),x=x,y=y,shift=e.memory[sp+8],phase=e.memory[sym['_phase']]))
for name,k in [('assembly','_riding_mulq32'),('reference','_riding_mulq32_frozen')]:e.hook_register(0,sym[k],entered,name)
try:
 for _ in range(300):
  e.tick(100,False)
  if e.memory[sym['_done']]:break
 def n(name,size=2,signed=False):return int.from_bytes(bytes(e.memory[sym['_'+name]:sym['_'+name]+size]),'little',signed=signed)
 report={k:n(k)for k in ['failures','reference_failures','guards','count','banks_bad','irqs','first_bad']};report.update(done=n('done',1),first_actual=n('first_actual',4,True),vectors=len(rows),captures=len(captures),cycles={})
 for label,pred in [('wide14',lambda v:v['shift']==14 and not -32768<=v['x']<=32767),('narrow14',lambda v:v['shift']==14 and -32768<=v['x']<=32767),('other',lambda v:v['shift']!=14),('captured',lambda v:len(rows)-len(captures)<=v['row']<len(rows)),('irq',lambda v:v['phase']==1)]:
  pairs=[(a,b)for a,b in zip(records[::2],records[1::2])if pred(a)and(label=='irq'or a['phase']==0)];savings=[b['cycles']-a['cycles']for a,b in pairs]
  if pairs:report['cycles'][label]={'calls':len(pairs),'assembly_mean':sum(a['cycles']for a,b in pairs)/len(pairs),'reference_mean':sum(b['cycles']for a,b in pairs)/len(pairs),'saving_min':min(savings),'saving_max':max(savings),'saving_mean':sum(savings)/len(pairs),'assembly_stack':max(a['stack']for a,b in pairs),'reference_stack':max(b['stack']for a,b in pairs)}
 assert source_hashes=={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in common},'sources changed during test'
 report['source_sha256']=source_hashes
 report['reference_source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [O/'reference.c',O/'frozen_dispatch.s']}
 assert report['cycles']['narrow14']['saving_min']==report['cycles']['narrow14']['saving_max']==0,'narrow dispatch changed'
 report['coverage']={'positive_saturation':sum(x*y+8192>=2**45 for x,y,s,w in rows if s==14),'negative_saturation':sum(x*y+8192<-(2**45)for x,y,s,w in rows if s==14),'negative_half_round':sum(x*y<0 and x*y%16384==8192 for x,y,s,w in rows if s==14),'zero_product':sum(x*y==0 for x,y,s,w in rows),'x_int32_min':sum(x==-2**31 for x,y,s,w in rows),'x_int32_max':sum(x==2**31-1 for x,y,s,w in rows),'y_int16_min':sum(y==-32768 for x,y,s,w in rows),'y_int16_max':sum(y==32767 for x,y,s,w in rows)}
 (O/'records.json').write_text(json.dumps(records));(O/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));assert report['done']and report['count']==len(rows)+256 and len(records)==2*report['count']and not any(report[k]for k in ['failures','reference_failures','guards','banks_bad'])and report['irqs']>0
finally:e.stop(save=False)
