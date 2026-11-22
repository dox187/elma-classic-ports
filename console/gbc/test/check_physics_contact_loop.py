"""Check exact native contact order, boundaries, records and cursor state."""
from pathlib import Path
import json,re,struct,subprocess
from pyboy import PyBoy
import argparse,hashlib,random
parser=argparse.ArgumentParser(description='Pair the native contact loop with its frozen C reference.')
parser.add_argument('--gen',type=Path)
parser.add_argument('--out',type=Path)
args=parser.parse_args()
B=Path(__file__).resolve().parents[1];S=B/'src'
G=(args.gen or B/'build/gen-8m').resolve()
O=(args.out or B/'build/contact-loop-check').resolve();O.mkdir(parents=True,exist_ok=True)
r=random.Random(0x910c)
s16=lambda n:((n+32768)&65535)-32768
def seg(px,py,dx,dy,ex,ey,length,box=(0,255,0,255)):
 return list(struct.pack('<7h4B',*(s16(n)for n in (px,py,dx,dy,ex,ey,length)),*box))
g=[]
def group(qx,qy,ss):g.append({'qx':qx,'qy':qy,'segments':ss})
# Exact radius, signed projection, endpoint and zero/deep-distance boundaries.
for qx,qy in ((0,0),(63,64),(2048,2048),(4095,4095)):
 for length in (-32768,-1,0,1,102,410,1024,32767):
  for pos in (-411,-410,-409,-1,0,1,101,102,409,410,411,length-1,length,length+1):
   for d in (-411,-410,-409,-128,-1,0,1,127,128,409,410,411):
    group(qx,qy,[seg(qx-pos,qy-d,length,0,16384,0,length)])
# Merge radius boundaries, ordering, reversed normals and rejected boxes.
for delta in (-103,-102,-101,-1,0,1,101,102,103):
 for y in (-410,-409,-128,-1,0,1,128,409,410):
  for rev in (False,True):
   a=seg(1024,2048-y,2048,0,16384,0,2048)
   b=seg(2048-delta,1024,0,2048,0,16384,2048)
   ss=[a,b]if not rev else[b,a]
   group(2048,2048,[seg(1,2,3,4,5,6,7,(0,0,0,0)),*ss,ss[0]])
# Adversarial full-width records retain exact16-bit wrap and flagged length checks.
for i in range(1500):
 qx=r.randrange(4096);qy=r.randrange(4096);ss=[]
 for j in range(r.randrange(0,7)):
  values=[r.randint(-32768,32767)for _ in range(7)]
  if i%3==0:values[:2]=[s16(qx+r.randint(-411,411)),s16(qy+r.randint(-411,411))]
  if i%5==0:values[4:6]=r.choice([(16384,0),(-16384,0),(0,16384),(0,-16384),(11585,11585),(-11585,11585)])
  box=(0,255,0,255)if j%3 else tuple(r.randrange(256)for _ in range(4))
  ss.append(seg(*values,box=box))
 group(qx,qy,ss)
groups=g;maximum=max(len(row['segments'])for row in groups)
source_hashes={p:hashlib.sha256((S/p).read_bytes()).hexdigest() for p in ('physics_contacts.c','physics_contact_loop.s')}
baseline=(B/'test/fixtures/physics_contacts_loop_c.c').read_text().split('// helyigazitas:',1)[0]
# The scalar reference retains its original arithmetic, with the current
# packed length/endpoint protocol decoded before geometric operations.
baseline=baseline.replace('pos <= s->len','pos <= SEG_LENGTH(s)')
baseline=baseline.replace('if( pos >= 0 && pos <= SEG_LENGTH(s) ) {',
    'if( pos >= 0 && pos <= SEG_LENGTH(s) ) {\n            if(pos==SEG_LENGTH(s) && ((uint16_t)s->len & SEG_INTERNAL_END))continue;')
baseline=baseline.replace('// Near an end point:',
    '// Near an original endpoint:\n            if((uint16_t)s->len & (pos<0?SEG_INTERNAL_START:SEG_INTERNAL_END))continue;')
baseline=baseline.replace('\t\tif( pos > 0 ) {\n\t\t\tx -= s->dx;',
    '\t\tif((uint16_t)s->len & (pos<0?SEG_INTERNAL_START:SEG_INTERNAL_END))continue;\n\t\tif( pos > 0 ) {\n\t\t\tx -= s->dx;')
candidate=(S/'physics_contacts.c').read_text().split('// helyigazitas:',1)[0]
typepart=baseline[:baseline.index('static contact_t Ct[2];')]
candidate=typepart+'''contact_t Ct[2];
void riding_normal_fast(int16_t,int16_t,int32_t,contact_t*) __sdcccall(0);
#define normalize riding_normal_fast
'''+candidate[candidate.index('static void contact_point'):]
for name,source in (('baseline',baseline),('candidate',candidate)):
 source=source.replace('static contact_t Ct[2];','contact_t Ct[2];').replace('Ct',name+'_Ct').replace('static uint8_t contacts(',f'uint8_t {name}_contacts(').replace('riding_touches(',name+'_touches(')
 source=source.replace('#include "../../nes/src/rsqrt.inc"','#include "'+str(B.parent/'nes/src/rsqrt.inc')+'"')
 (O/(name+'.c')).write_text(source)
(O/'physics_contact_loop.s').write_text((S/'physics_contact_loop.s').read_text().replace('_Ct','_candidate_Ct'))
(O/'vectors.h').write_text('#include <stdint.h>\ntypedef struct{int16_t px,py,dx,dy,ex,ey,len;uint8_t x0,x1,y0,y1;}seg_t;\ntypedef struct{int16_t qx,qy;uint8_t count;seg_t seg['+str(maximum)+'];}group_t;extern group_t copy;\n')
sources=[]
for bank,start in enumerate(range(0,len(groups),50),44):
 block=groups[start:start+50];rows=[]
 for g in block:
  ss=['{'+','.join(map(str,struct.unpack('<7h4B',bytes(s))))+'}'for s in g['segments']]
  if not ss:ss=['{0}']
  rows.append('{'+str(g['qx'])+','+str(g['qy'])+','+str(len(g['segments']))+',{'+','.join(ss)+'}}')
 path=O/f'vectors{bank}.c';path.write_text(f'#pragma bank {bank}\n#include "vectors.h"\nconst group_t groups{bank}[]={{'+','.join(rows)+'};\n');sources.append(path)
(O/'case.c').write_text('''#include <gb/gb.h>
#include <string.h>
#include "vectors.h"
#pragma bank 9
const seg_t *Seg_cur;uint8_t Seg_left;
uint8_t query_x,query_y,query_sub;
void seg_query(uint8_t a,uint8_t b,uint8_t c){query_x=a;query_y=b;query_sub=c;Seg_cur=copy.seg;Seg_left=copy.count;}
const seg_t *seg_next(void){if(!Seg_left)return 0;--Seg_left;return Seg_cur++;}
uint8_t baseline_contacts(int32_t,int32_t);uint8_t candidate_contacts(int32_t,int32_t);
uint8_t baseline_touches(int32_t,int32_t,int16_t) BANKED;
uint8_t candidate_touches(int32_t,int32_t,int16_t) BANKED;
extern uint8_t baseline_Ct[20],candidate_Ct[20];
volatile uint16_t cases,failures,touch_failures,bank_failures,cursor_failures,grid_failures,first_bad;volatile uint8_t first_byte;
void loop_case(void) BANKED {
 uint8_t i,n0,n1,left;int16_t rad;const seg_t *cursor;
 uint8_t gx=(uint8_t)cases,gy=(uint8_t)(cases>>3),sub=(copy.qx>>10)|((copy.qy>>8)&12);
 int32_t x=4096L*gx+copy.qx,y=4096L*gy+copy.qy;
 /* The stub supplies the same ordered records at each address. Verify the
  * actual directory key too, including negative coordinates and high aliases. */
 if((cases&511)==0){x-=0x100000L;gx=255;}
 if((cases&511)==511){y+=0x1000000L;gy=255;}
 memset(baseline_Ct,0x5a,20);memset(candidate_Ct,0x5a,20);
 n0=baseline_contacts(x,y);left=Seg_left;cursor=Seg_cur;n1=candidate_contacts(x,y);if(left!=Seg_left||cursor!=Seg_cur)++cursor_failures;
 if(query_x!=gx || query_y!=gy || query_sub!=sub)++grid_failures;
 if(n0!=n1){if(!failures){first_bad=cases;first_byte=20;}++failures;}
 for(i=0;i<20;++i)if(baseline_Ct[i]!=candidate_Ct[i]){if(!failures){first_bad=cases;first_byte=i;}++failures;}
 for(i=0;i<4;++i){rad=i==0?0:i==1?1:i==2?326:410;
  n0=baseline_touches(copy.qx,copy.qy,rad);n1=candidate_touches(copy.qx,copy.qy,rad);
  if(n0!=n1)++touch_failures;
 }
 if(CURRENT_BANK!=9)++bank_failures;++cases;
}
''')
(O/'driver.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "vectors.h"
group_t copy;volatile uint8_t done;void loop_case(void) BANKED;
void main(void){uint16_t i,bank,count;const group_t *v;disable_interrupts();DISPLAY_OFF;cpu_fast();
'''+f'for(bank=44;bank<={43+len(sources)};++bank){{count=bank=={43+len(sources)}?{len(groups)%50 or 50}:50;v=(const group_t*)0x4000;SWITCH_ROM(bank);for(i=0;i<count;++i,++v){{memcpy(&copy,v,sizeof(copy));loop_case();}}}}\n'+'done=1;while(1){} }\n')
cmd=[B/'.toolchain/gbdk/bin/lcc','-msm83:gb','-Wf--opt-code-size','-Wf--max-allocs-per-node','-Wf100000','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(O),'-I'+str(S),'-I'+str(G),'-o',O/'check.gbc',O/'driver.c',O/'case.c',O/'baseline.c',O/'candidate.c',O/'physics_contact_loop.s']
cmd += [S/f'physics_{n}.s'for n in ('math','mul_fast','kmul_fast','normal_fast','sqrt_fast','div_fast','shift_fast','segment_scan')]+[G/f'physics_quarter_{i}.c'for i in range(20,36)]+[G/f'physics_scale_{i}.c'for i in range(36,44)]+sources
r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True);(O/'compile.log').write_text(r.stdout+r.stderr);assert not r.returncode,r.stdout+r.stderr
sy={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(O/'check.noi').read_text())}
p=PyBoy(str(O/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0);timings={n:[]for n in ('baseline_contacts','candidate_contacts','baseline_touches','candidate_touches')};pending=[];rets=set()
def returned(key):
 if pending and pending[-1][1]==key and (p.register_file.SP-pending[-1][0])&65535<=24:
  sp,ret,cycles,name=pending.pop();timings[name].append(p._cycles()-cycles)
def entered(name):
 sp=p.register_file.SP;ret=p.memory[sp]+256*p.memory[sp+1];key=(0 if ret<0x4000 else 9,ret)
 if key not in rets:p.hook_register(*key,returned,key);rets.add(key)
 pending.append((sp,key,p._cycles(),name))
for name in timings:
 adr=sy['_'+name];p.hook_register(adr>>16,adr&65535,entered,name)

for _ in range(1000):
 p.tick(100,False)
 if p.memory[sy['_done']]:break
def get(n,size=2):return int.from_bytes(bytes(p.memory[sy['_'+n]:sy['_'+n]+size]),'little')
report={n:get(n)for n in ('cases','failures','touch_failures','bank_failures','cursor_failures','grid_failures','first_bad')};report.update(done=get('done',1),first_byte=get('first_byte',1),timings={n:{'calls':len(v),'total':sum(v),'mean':sum(v)/len(v)if v else None,'min':min(v)if v else None,'max':max(v)if v else None}for n,v in timings.items()})
report['source_sha256']=source_hashes;report['source_still_current']=all(hashlib.sha256((S/p).read_bytes()).hexdigest()==h for p,h in source_hashes.items())
report['paired_savings']={kind:{'total':sum(timings['baseline_'+kind])-sum(timings['candidate_'+kind]),'per_call':(sum(timings['baseline_'+kind])-sum(timings['candidate_'+kind]))/len(timings['baseline_'+kind])}for kind in ('contacts','touches')}
(O/'cycles.json').write_text(json.dumps(timings)+'\n')
(O/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));p.stop(save=False)
assert report['source_still_current']and report['done']and report['cases']==len(groups)and not any(report[n]for n in ('failures','touch_failures','bank_failures','cursor_failures','grid_failures'))
