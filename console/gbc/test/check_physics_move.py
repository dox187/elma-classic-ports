"""Independent packed22 motion reference and native carry/wrap/guard checks."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import random
import re
import struct
import subprocess
import sys
from pyboy import PyBoy
BASE=Path(__file__).resolve().parents[1]

def rows():
 r=random.Random(2232128)
 positions=[0,1,0x7fffffff,0x80000000,0xffffffff,0x00ffffff,0x0000ffff,0x000000ff]
 velocity=[0,1,-1,0x7fffffff,-0x80000000,32768,-32769,0x3fffffff,-0x40000000]
 omega=[0,1,-1,32767,-32768,255,-256,256,-257]
 result=[]
 for i,x in enumerate(positions):
  for j,v in enumerate(velocity):
   for w in omega:
    result.append(struct.pack('<IIiiIh',x,positions[(i+3)%len(positions)],v,velocity[(j+4)%len(velocity)],positions[(i+5)%len(positions)],w))
 for _ in range(512):
  result.append(struct.pack('<IIiiIh',r.getrandbits(32),r.getrandbits(32),r.randint(-2**31,2**31-1),r.randint(-2**31,2**31-1),r.getrandbits(32),r.randint(-32768,32767)))
 return result

def expected(data):
 x,y,vx,vy,a,w=struct.unpack('<IIiiIh',data)
 return struct.pack('<IIiiIh',(x+vx*4)&0xffffffff,(y+vy*4)&0xffffffff,vx,vy,(a+w*128)&0xffffffff,w)

def main():
 p=argparse.ArgumentParser();p.add_argument('--assembly',type=Path,default=BASE/'src/physics_move_fast.s');p.add_argument('--out',type=Path,default=BASE/'build/move32-check');p.add_argument('--lcc',type=Path,default=BASE/'.toolchain/gbdk/bin/lcc');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 source_hash=hashlib.sha256(a.assembly.read_bytes()).hexdigest();cases=rows();want=[expected(v)for v in cases]
 reference=a.out/'host.c';reference.write_text('''#include <stdint.h>
#include <string.h>
void reference_move(uint8_t *k){uint32_t x,y,a,vx,vy;int16_t w;
memcpy(&x,k,4);memcpy(&y,k+4,4);memcpy(&vx,k+8,4);memcpy(&vy,k+12,4);memcpy(&a,k+16,4);memcpy(&w,k+20,2);
x+=vx*4u;y+=vy*4u;a+=(uint32_t)(int32_t)w*128u;
memcpy(k,&x,4);memcpy(k+4,&y,4);memcpy(k+16,&a,4);}
''')
 lib=a.out/('host.dylib'if sys.platform=='darwin'else'host.so');subprocess.run(['cc','-shared','-fPIC',str(reference),'-o',str(lib)],check=True)
 host=C.CDLL(str(lib));host.reference_move.argtypes=[C.POINTER(C.c_uint8)]
 for before,after in zip(cases,want):
  buf=(C.c_uint8*22).from_buffer_copy(before);host.reference_move(buf);assert bytes(buf)==after
 sources=[];header='#include <stdint.h>\ntypedef struct {uint8_t before[22],after[22];} vector_t;\n'
 for bank,start in enumerate(range(0,len(cases),256),1):
  subset=list(zip(cases[start:start+256],want[start:start+256]));name=f'vectors{bank}'
  header+=f'extern const vector_t {name}[];\n#define COUNT{bank} {len(subset)}\n'
  path=a.out/f'{name}.c';path.write_text('#include "vectors.h"\n#pragma bank '+str(bank)+'\nconst vector_t '+name+'[]={\n'+',\n'.join('{{'+','.join(map(str,before))+'},{'+','.join(map(str,after))+'}}'for before,after in subset)+'\n};\n');sources.append(path)
 (a.out/'vectors.h').write_text(header)
 driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stddef.h>
#include <string.h>
#include "physics_core.h"
#include "vectors.h"
void riding_move32(circle_t *k) __sdcccall(0);
typedef char packed22[sizeof(circle_t)==22?1:-1];
typedef char packed_offsets[offsetof(circle_t,rx)==0&&offsetof(circle_t,ry)==4&&offsetof(circle_t,vx)==8&&offsetof(circle_t,vy)==12&&offsetof(circle_t,alfa)==16&&offsetof(circle_t,omega)==20?1:-1];
volatile uint8_t move_done;volatile uint16_t move_failures,guard_failures,bank_failures,move_cases;
uint8_t arena[512];
static void check(const vector_t *v,uint16_t id){uint16_t j,pos=16+(id*37u)%256u;uint8_t pattern;
 for(j=0;j<512;++j)arena[j]=(uint8_t)(0xa5u^j^id);
 memcpy(arena+pos,v->before,22);riding_move32((circle_t *)(arena+pos));
 for(j=0;j<22;++j)if(arena[pos+j]!=v->after[j])++move_failures;
 for(j=0;j<512;++j)if(j<pos||j>=pos+22){pattern=(uint8_t)(0xa5u^j^id);if(arena[j]!=pattern)++guard_failures;}
 ++move_cases;}
void main(void){uint16_t i;uint8_t bank;disable_interrupts();DISPLAY_OFF;cpu_fast();
'''
 for bank in range(1,len(sources)+1):driver+=f' bank={bank};SWITCH_ROM({bank});for(i=0;i<COUNT{bank};++i){{check(&vectors{bank}[i],move_cases);if(CURRENT_BANK!=bank)++bank_failures;}}\n'
 driver+=' move_done=1;while(1){} }\n';(a.out/'driver.c').write_text(driver)
 cmd=[str(a.lcc),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(BASE/'src'),'-I'+str(BASE/'build/gen'),'-I'+str(a.out),'-o',str(a.out/'check.gbc'),str(a.out/'driver.c'),str(a.assembly)]+list(map(str,sources))
 subprocess.run(cmd,check=True,capture_output=True,text=True)
 sy={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9a-fA-F]+)',(a.out/'check.noi').read_text())}
 p=PyBoy(str(a.out/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0);pending=[];returns=set();cycles=[]
 def completed(key):
  if not pending or pending[-1][:2]!=(key,p.register_file.SP-2):return
  cycles.append(p._cycles()-pending.pop()[2])
 def entered(_):
  sp=p.register_file.SP;ret=p.memory[sp]+256*p.memory[sp+1];key=(0,ret)
  if key not in returns:p.hook_register(*key,completed,key);returns.add(key)
  pending.append((key,sp,p._cycles()))
 p.hook_register(0,sy['_riding_move32'],entered,None)
 try:
  for _ in range(300):
   p.tick(100)
   if p.memory[sy['_move_done']]:break
  def n(name,size=2):
   q=sy['_'+name];return int.from_bytes(bytes(p.memory[q:q+size]),'little')
  report={name:n(name)for name in ('move_failures','guard_failures','bank_failures','move_cases')};report.update({'move_done':n('move_done',1),'host_matches_python':True,'packed_circle_bytes':22,'api_cycles':{'calls':len(cycles),'min':min(cycles),'max':max(cycles),'mean':sum(cycles)/len(cycles)},'assembly_sha256':source_hash})
  assert hashlib.sha256(a.assembly.read_bytes()).hexdigest()==source_hash,'Assembly changed while checking'
  (a.out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
  assert report['move_done'] and report['move_cases']==len(cases) and not any(report[v]for v in ('move_failures','guard_failures','bank_failures')),report
 finally:p.stop(save=False)
if __name__=='__main__':main()
