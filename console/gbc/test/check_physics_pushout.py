"""Exact native pushout against original C and an independent integer oracle."""
from pathlib import Path
import argparse,json,struct,random,re,subprocess
from pyboy import PyBoy
B=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--gen',type=Path,default=B/'build/gen-8m')
parser.add_argument('--out',type=Path,default=B/'build/physics-pushout-check')
parser.add_argument('--captures',type=Path,help='optional JSON array of captured circle/contact/other hex records')
args=parser.parse_args();S=B/'src';G=args.gen.resolve();O=args.out.resolve();O.mkdir(parents=True,exist_ok=True)
r=random.Random(0x919405);vectors=[]
def add(state,mode,kind):vectors.append(dict(state=list(state),mode=mode,kind=kind))
for v in json.loads(args.captures.read_text())if args.captures else []:add(bytes.fromhex(v['circle']+v['contact']+(v['other']or'00'*10)),2 if v['alias'] else 1 if v['other'] else 0,'captured'+str(v.get('case','')))
coords=[-2147483648,-2147483647,2147483647,2147483646,-16777216,-65536,-256,-1,0,1,255,256,65535,65536,16777215,16777216]
normals=[(0,0),(0,16384),(16384,0),(0,-16384),(-16384,0),(11585,-11585),(-32768,32767),(32767,-32768),(-32768,-32768),(1,-1)]
lengths=[-32768,-32767,-32365,-32364,-32363,-32362,-32361,-4096,-410,-405,-256,-1,0,1,404,405,406,32766,32767]
for ni,(nx,ny)in enumerate(normals):
 for l in lengths:
  for j in range(len(coords)):
   for mode in (0,1,2):
    k=struct.pack('<iiiiIh',coords[j],coords[(j+5)%16],r.randrange(-2**31,2**31),r.randrange(-2**31,2**31),r.getrandbits(32),r.randrange(-32768,32768))
    other=normals[(ni+j)%len(normals)];ct=struct.pack('<10h',nx,ny,l,-12345,12345,*other,lengths[(j+ni)%len(lengths)],32767,-32768)
    add(k+ct,mode,'boundary-mode'+str(mode))
for i in range(2000):add(bytes(r.getrandbits(8)for _ in range(42)),i%3,'random-mode'+str(i%3))
# Exhaustively prove the narrowed length identity and branch across all int16 l.
def s16(v):return (v+32768)%65536-32768
def s32(v):return (v+2**31)%2**32-2**31
for l in range(-32768,32768):assert s16(l+s16(405-l))==405
reference='void reference_pushout( circle_t* k, contact_t* c, contact_t* other ) {\n\tint16_t push = R_WHEEL-BAND-c->l;\n\tif( push <= 0 )\n\t\treturn;\n\tint16_t px = mulq14( push, c->nx ), py = mulq14( push, c->ny );\n\tk->rx += (int32_t)px << 8;\n\tk->ry += (int32_t)py << 8;\n\tc->l += push;\n\tif( other )\n\t\tother->l += dotq14( px, py, other->nx, other->ny );\n}\n\n'
preamble='#pragma bank 9\n#include "physics_core.h"\n#include "physics_math.h"\ntypedef struct{int16_t nx,ny,l,tx,ty;}contact_t;\n#include <stddef.h>\ntypedef char layout[sizeof(circle_t)==22 && offsetof(circle_t,rx)==0 && offsetof(circle_t,ry)==4 && sizeof(contact_t)==10 && offsetof(contact_t,l)==4 && R_WHEEL-BAND==405?1:-1];\n'
(O/'reference.c').write_text(preamble+reference)
(O/'vectors.h').write_text('#include <stdint.h>\ntypedef struct{uint8_t state[42],mode;}vector_t;extern vector_t copy;\n')
assert len(vectors)<=53000,'captured fixture exceeds the available low source banks'
sources=[]
for bank,start in enumerate(range(0,len(vectors),250),44):
 block=vectors[start:start+250];rows=['{{'+','.join(map(str,v['state']))+'},'+str(v['mode'])+'}'for v in block];path=O/f'vectors{bank}.c';path.write_text(f'#pragma bank {bank}\n#include "vectors.h"\nconst vector_t vectors{bank}[]={{'+','.join(rows)+'};\n');sources.append(path)
(O/'case.c').write_text('''#pragma bank 9
#include <gb/gb.h>
#include <string.h>
#include "physics_core.h"
#include "vectors.h"
typedef struct{int16_t nx,ny,l,tx,ty;}contact_t;
typedef struct{circle_t k;contact_t c,other;}state_t;
typedef char state_layout[sizeof(state_t)==42?1:-1];
struct {uint8_t before[8];state_t state;uint8_t after[8];} box;
uint8_t want[42];volatile uint16_t cases,failures,bank_failures,guards,first_bad;volatile uint8_t first_byte;
void reference_pushout(circle_t*,contact_t*,contact_t*);void riding_pushout32(circle_t*,contact_t*,contact_t*) __sdcccall(1);
void marker(void){}
void run_case(void) BANKED {
 uint8_t i;contact_t *other=copy.mode==2?&box.state.c:copy.mode?&box.state.other:0;
 memset(box.before,0xa5,8);memset(box.after,0xa5,8);
 memcpy(&box.state,copy.state,42);reference_pushout(&box.state.k,&box.state.c,other);memcpy(want,&box.state,42);
 if(CURRENT_BANK!=9)++bank_failures;
 memcpy(&box.state,copy.state,42);riding_pushout32(&box.state.k,&box.state.c,other);
 for(i=0;i<42;++i)if(((uint8_t*)&box.state)[i]!=want[i]){if(!failures){first_bad=cases;first_byte=i;}++failures;}
 for(i=0;i<8;++i)if(box.before[i]!=0xa5||box.after[i]!=0xa5)++guards;
 if(CURRENT_BANK!=9)++bank_failures;marker();++cases;
}
''')
(O/'driver.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "vectors.h"
vector_t copy;volatile uint8_t done;volatile uint16_t source_bank_failures;void run_case(void) BANKED;
void main(void){uint16_t i,bank,count;const vector_t *v;disable_interrupts();DISPLAY_OFF;cpu_fast();
'''+f'for(bank=44;bank<={43+len(sources)};++bank){{count=bank=={43+len(sources)}?{len(vectors)%250 or 250}:250;v=(const vector_t*)0x4000;SWITCH_ROM(bank);for(i=0;i<count;++i,++v){{memcpy(&copy,v,sizeof(copy));run_case();if(CURRENT_BANK!=bank)++source_bank_failures;}}}}\n'+'done=1;while(1){} }\n')
cmd=[B/'.toolchain/gbdk/bin/lcc','-msm83:gb','-Wf--opt-code-size','-Wf--max-allocs-per-node','-Wf100000','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(O),'-I'+str(S),'-I'+str(G),'-o',O/'check.gbc',O/'driver.c',O/'case.c',O/'reference.c',S/'physics_pushout.s']
cmd += [S/f'physics_{n}.s'for n in ('math','mul_fast','kmul_fast')]+[G/f'physics_quarter_{i}.c'for i in range(20,36)]+[G/f'physics_scale_{i}.c'for i in range(36,44)]+sources
r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True);(O/'compile.log').write_text(r.stdout+r.stderr);assert not r.returncode,r.stdout+r.stderr
sy={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(O/'check.noi').read_text())};p=PyBoy(str(O/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0);timings={n:[]for n in ('reference_pushout','riding_pushout32')};pending=[];rets=set();depths={n:[]for n in timings};oracle_failures=[];oracle_seen=[0]
def returned(key):
 if pending and pending[-1][1]==key and p.register_file.SP==pending[-1][0]+4:
  sp,ret,cycles,name,pattern=pending.pop();timings[name].append(p._cycles()-cycles)
  actual=bytes(p.memory[sp-128:sp]);changed=[i for i,(a,b)in enumerate(zip(actual,pattern))if a!=b];depths[name].append(128-min(changed)if changed else 0)
def entered(name):
 sp=p.register_file.SP;ret=p.memory[sp]+256*p.memory[sp+1];key=(0 if ret<0x4000 else 9,ret)
 if key not in rets:p.hook_register(*key,returned,key);rets.add(key)
 pattern=bytes((i*157+43)&255 for i in range(128));p.memory[sp-128:sp]=list(pattern);pending.append((sp,key,p._cycles(),name,pattern))
for name in timings:
 adr=sy['_'+name];p.hook_register(adr>>16,adr&65535,entered,name)
def oracle(v):
 s=bytearray(v['state']);nx,ny,l=struct.unpack_from('<3h',s,22);push=s16(405-l)
 if push<=0:return s
 sat=lambda n:max(-32768,min(32767,n));px=sat((push*nx+8192)>>14);py=sat((push*ny+8192)>>14)
 for offset,delta in [(0,px),(4,py)]:struct.pack_into('<i',s,offset,s32(struct.unpack_from('<i',s,offset)[0]+delta*256))
 struct.pack_into('<h',s,26,s16(l+push))
 if v['mode']:
  off=22 if v['mode']==2 else 32;ox,oy,ol=struct.unpack_from('<3h',s,off);delta=sat(s32(px*ox+py*oy+8192)>>14);struct.pack_into('<h',s,off+4,s16(ol+delta))
 return s
def marker(_):
 i=get('cases');got=bytes(p.memory[sy['_box']+8:sy['_box']+50]);want=oracle(vectors[i]);oracle_seen[0]+=1
 if got!=want and len(oracle_failures)<10:oracle_failures.append(dict(case=i,first_byte=next(j for j in range(42)if got[j]!=want[j]),got=got.hex(),want=want.hex()))
def get(n,size=2):return int.from_bytes(bytes(p.memory[sy['_'+n]:sy['_'+n]+size]),'little')
a=sy['_marker'];p.hook_register(a>>16,a&65535,marker,None)
for _ in range(1000):
 p.tick(100,False)
 if p.memory[sy['_done']]:break
report={n:get(n)for n in ('cases','failures','bank_failures','source_bank_failures','guards','first_bad')};report.update(done=get('done',1),first_byte=get('first_byte',1),oracle_seen=oracle_seen[0],oracle_failures=oracle_failures,length_identity_exhaustive=65536,source_banks=[44,43+len(sources)]);report['timings']={}
for kind in sorted(set(v['kind']for v in vectors)):
 ids=[i for i,v in enumerate(vectors)if v['kind']==kind];a=[timings['reference_pushout'][i]for i in ids];b=[timings['riding_pushout32'][i]for i in ids];d=[y-x for x,y in zip(a,b)];report['timings'][kind]=dict(count=len(ids),baseline_mean=sum(a)/len(a),candidate_mean=sum(b)/len(b),baseline_max=max(a),candidate_max=max(b),delta_mean=sum(d)/len(d),delta_min=min(d),delta_max=max(d))
report['stack']={n:dict(min=min(v),max=max(v),values=sorted(set(v)))for n,v in depths.items()}
(O/'cycles.json').write_text(json.dumps(timings));(O/'vectors.json').write_text(json.dumps(vectors));(O/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));p.stop(save=False)
assert report['done']and report['cases']==len(vectors)and report['oracle_seen']==len(vectors)and not oracle_failures and not any(report[n]for n in ('failures','bank_failures','source_bank_failures','guards'))
