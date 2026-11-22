"""Exercise every 256..511 magnitude through public and register multiply APIs.

Boundary, sign, square, power-of-two and seeded random vectors retain all32
product bits. All fixtures and exact lookup tables are generated in the
ignored output directory; no game assets or shared generated files change.
"""
import argparse,hashlib,json,random,re,subprocess,sys
from pathlib import Path
from pyboy import PyBoy
BASE=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser();p.add_argument('--assembly',type=Path,default=BASE/'src/physics_mul_fast.s');p.add_argument('--out',type=Path,default=BASE/'build/mul9-check');a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 sha=hashlib.sha256(a.assembly.read_bytes()).hexdigest();raw=BASE/'src/physics_kmul_fast.s';raw_sha=hashlib.sha256(raw.read_bytes()).hexdigest();r=random.Random(256511);pairs=[]
 bounds=[-32768,-32767,-16384,-1024,-512,-511,-256,-255,-1,0,1,127,255,256,257,511,512,1024,16384,32767]
 for m in range(256,512):
  for sign in(-1,1):
   for x in bounds+[r.randrange(-32768,32768)for _ in range(4)]:pairs += [(x,sign*m),(sign*m,x)]
  pairs += [(m,m),(m,-m),(-m,m),(-m,-m)]
 header='#include <stdint.h>\ntypedef struct{int16_t a,b;int32_t product;} product_t;\n';sources=[];calls=[]
 for bank,start in enumerate(range(0,len(pairs),2048),44):
  rows=pairs[start:start+2048];name='mul9_pairs_%d'%bank
  header+='extern const product_t '+name+'[];\n'
  path=out/(name+'.c');path.write_text('#include "vectors.h"\n#pragma bank %d\n'%bank+'const product_t '+name+'[]={\n'+',\n'.join('{%d,%d,%dL}'%(x,y,x*y)for x,y in rows)+'\n};\n');sources.append(path)
  calls.append(' SWITCH_ROM(%d);check(%s,%d,%d);'%(bank,name,len(rows),bank))
 (out/'vectors.h').write_text(header)
 (out/'regs.s').write_text('''.module mul9_regs
.area _CODE
_mul9_regs::
 ldhl sp,#2
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 jp _riding_mul16_regs
''')
 (out/'driver.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include "vectors.h"
int32_t riding_mul16(int16_t,int16_t) __sdcccall(0);
int32_t mul9_regs(int16_t,int16_t) __sdcccall(0);
volatile uint8_t done;volatile uint16_t public_failures,register_failures,bank_failures,checked_cases;
static void check(const volatile product_t *p,uint16_t count,uint8_t bank){uint16_t i;int16_t x,y;int32_t want;
 for(i=0;i<count;++i){x=p[i].a;y=p[i].b;want=p[i].product;
 if(riding_mul16(x,y)!=want)++public_failures;if(CURRENT_BANK!=bank||p[i].a!=x||p[i].b!=y)++bank_failures;
 if(mul9_regs(x,y)!=want)++register_failures;if(CURRENT_BANK!=bank||p[i].product!=want)++bank_failures;
 ++checked_cases;}}
void main(void){disable_interrupts();DISPLAY_OFF;cpu_fast();
'''+ '\n'.join(calls)+'\n done=1;while(1){} }\n')
 tables_dir=out/'tables'
 for tool in ('mul_table.py','scale_table.py'):
  subprocess.run([sys.executable,str(BASE/'tools'/tool),'--out',str(tables_dir)],check=True,capture_output=True,text=True)
 tables=sorted(tables_dir.glob('physics_quarter_*.c'))+sorted(tables_dir.glob('physics_scale_*.c'))
 cmd=[str(BASE/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(out),'-o',str(out/'check.gbc'),str(out/'driver.c'),str(out/'regs.s'),str(a.assembly),str(BASE/'src/physics_kmul_fast.s')]+list(map(str,sources+tables));subprocess.run(cmd,check=True,capture_output=True,text=True)
 sy={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9a-fA-F]+)',(out/'check.noi').read_text())};rom=(out/'check.gbc').read_bytes()
 for bank in range(36,44):
  first=(bank-36)*32;want=bytes(((m*x) >> shift) & 255 for m in range(first,first+32) for shift in (0,8) for x in range(256));assert rom[bank*16384:(bank+1)*16384]==want
 for bank in range(20,36):
  first=(bank-20)*4096;want=b''.join((x*x//4).to_bytes(4,'little')for x in range(first,first+4096));assert rom[bank*16384:(bank+1)*16384]==want
 emu=PyBoy(str(out/'check.gbc'),window='null',sound_emulated=False,cgb=True);emu.set_emulation_speed(0)
 try:
  for _ in range(300):
   emu.tick(100)
   if emu.memory[sy['_done']]:break
  def n(name,size=2):
   q=sy['_'+name];return int.from_bytes(bytes(emu.memory[q:q+size]),'little')
  report={name:n(name)for name in('public_failures','register_failures','bank_failures','checked_cases')};report.update({'done':n('done',1),'expected_cases':len(pairs),'native_products':2*len(pairs),'quarter_rom_bytes_verified':262144,'scale_rom_bytes_verified':131072,'source_sha256':sha,'raw_unsigned_dependency_sha256':raw_sha})
  assert hashlib.sha256(a.assembly.read_bytes()).hexdigest()==sha and hashlib.sha256(raw.read_bytes()).hexdigest()==raw_sha,'Multiplication sources changed during the native check'
  (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));assert report['done']and report['checked_cases']==len(pairs)and not any(report[x]for x in('public_failures','register_failures','bank_failures')),report
 finally:emu.stop(save=False)
if __name__=='__main__':main()
