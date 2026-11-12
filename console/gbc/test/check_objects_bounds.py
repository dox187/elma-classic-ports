"""Compare native coarse object bounds and rectangle tests with signed models."""
import hashlib,json,random,re,struct,subprocess
from pathlib import Path
from pyboy import PyBoy
BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'build/objects-bounds-check'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source=(BASE/'src/objects_bounds_fast.s').read_bytes();(OUT/'bounds.s').write_bytes(source)
    rng=random.Random(0xb0a0d5);edges=[-32768,-32767,-1024,-1,0,1,1024,32766,32767]
    rows=[]
    for n in range(4096):
        v=[rng.choice(edges)if n<1024 else rng.randrange(-32768,32768)for _ in range(8)]
        if n>=2048:
            v=[rng.randrange(-1000,1001)for _ in range(8)]
            if n&1:v[6:]=v[:2]
        xs=v[0:6:2];ys=v[1:6:2]
        b=[max(-32768,min(xs)-1),min(32767,max(xs)+1),max(-32768,min(ys)-1),min(32767,max(ys)+1)]
        hit=int(b[0]<=v[6]<=b[1] and b[2]<=v[7]<=b[3])
        rows.append((*v,*[x^0x8000 if x>=0 else(x&65535)^0x8000 for x in b],hit))
    header='#include <stdint.h>\ntypedef struct{int16_t xy[8];uint16_t bounds[4];uint8_t expected;} case_t;\ntypedef char layout[sizeof(case_t)==25?1:-1];\n'
    sources=[]
    for bank in range(1,9):
        p=OUT/('cases%d.c'%bank)
        batch=rows[(bank-1)*512:bank*512]
        p.write_text('#include "cases.h"\n#pragma bank %d\nconst case_t cases%d[]={\n'%(bank,bank)+',\n'.join('{{'+','.join(map(str,r[:8]))+'},{'+','.join(map(str,r[8:12]))+'},%d}'%r[12]for r in batch)+'\n};\n')
        sources.append(p);header+='extern const case_t cases%d[];\n'%bank
    (OUT/'cases.h').write_text(header)
    (OUT/'near.c').write_text('''#include <gb/gb.h>
#pragma bank 5
void gbc_objects_bounds(uint16_t *) __sdcccall(0);
uint8_t gbc_object_near(const uint8_t *,const uint16_t *) __sdcccall(0);
extern uint8_t object[18];extern uint16_t result[6];
uint8_t fixture_bounds(void) BANKED {gbc_objects_bounds(result+1);return gbc_object_near(object+1,result+1);}
''')
    driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "cases.h"
uint8_t fixture_bounds(void) BANKED;
uint8_t gbc_bike[52],object[18];
uint16_t result[6];
volatile uint16_t completed,failures,bank_failures,guard_failures;
volatile uint8_t done;
static void check(const case_t *p,uint8_t bank){
 uint16_t i;uint8_t j,before[52];
 for(i=0;i<512;++i){
  memset(gbc_bike,0xa5,52);memset(object,0x5a,18);memset(result,0x39,12);
  memcpy(gbc_bike+42,p[i].xy,2);memcpy(gbc_bike+46,p[i].xy+1,2);
  memcpy(gbc_bike+12,p[i].xy+2,2);memcpy(gbc_bike+16,p[i].xy+3,2);
  memcpy(gbc_bike+22,p[i].xy+4,2);memcpy(gbc_bike+26,p[i].xy+5,2);
  memcpy(object+8,p[i].xy+6,2);memcpy(object+12,p[i].xy+7,2);
  memcpy(before,gbc_bike,52);
  if(fixture_bounds()!=p[i].expected||memcmp(result+1,p[i].bounds,8))++failures;
  if(CURRENT_BANK!=bank)++bank_failures;
  if(memcmp(before,gbc_bike,52)||result[0]!=0x3939||result[5]!=0x3939)++guard_failures;
  if(memcmp(object+8,p[i].xy+6,2)||memcmp(object+12,p[i].xy+7,2))++guard_failures;
  for(j=0;j<18;++j)if((j<8||(j>9&&j<12)||j>13)&&object[j]!=0x5a)++guard_failures;
  ++completed;
 }
}
void main(void){cpu_fast();
'''
    for bank in range(1,9):driver+='SWITCH_ROM(%d);check(cases%d,%d);\n'%(bank,bank,bank)
    driver+='done=1;while(1)vsync();}\n';(OUT/'check.c').write_text(driver)
    command=[str(BASE/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yo16','-Wl-m','-Wl-j','-I'+str(OUT),'-o',str(OUT/'check.gbc'),str(OUT/'check.c'),str(OUT/'near.c'),str(OUT/'bounds.s'),*map(str,sources)]
    r=subprocess.run(command,capture_output=True,text=True);assert not r.returncode,r.stdout+r.stderr
    sym={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(OUT/'check.noi').read_text())}
    p=PyBoy(str(OUT/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0)
    def word(name):a=sym['_'+name];return p.memory[a]+256*p.memory[a+1]
    try:
        for _ in range(100):
            p.tick(100,False)
            if p.memory[sym['_done']]:break
        report={'cases':word('completed'),'failures':word('failures'),'bank_failures':word('bank_failures'),'guard_failures':word('guard_failures'),
                'source_sha256':hashlib.sha256(source).hexdigest(),'source_still_current':(BASE/'src/objects_bounds_fast.s').read_bytes()==source}
        assert report['cases']==4096 and not any(report[k]for k in('failures','bank_failures','guard_failures'))and report['source_still_current'],report
    finally:p.stop(save=False)
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
