"""Compare exact native object overlap with independent wrapping integer cases."""
import hashlib,json,random,re,struct,subprocess
from pathlib import Path
from pyboy import PyBoy
BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'build/objects-touch-check'


def signed(x):return (x+2**31)%2**32-2**31


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source=(BASE/'src/objects_touch_fast.s').read_bytes();(OUT/'touch.s').write_bytes(source)
    rng=random.Random(0x0b1ec7)
    rows=[]
    tangent=[]
    for head,radius,diagonal in ((0,819,756),(1,653,572)):
        for ux,uy in ((radius,0),(0,radius),(315,diagonal)):
            for sx in (-1,1):
                for sy in (-1,1):
                    for axis in (0,1):
                        for fraction in (-1,0,1,13,14,63):
                            d=[sx*ux*64,sy*uy*64];d[axis]+=fraction
                            tangent.append((*d,head))
    edges=[-65537,-65536,-52430,-52429,-52428,-1,0,1,52428,52429,52430,65535,65536]
    for n in range(4096):
        ox,oy=[rng.randrange(-2**31,2**31) for _ in range(2)]
        head=n&1
        if n<len(tangent):dx,dy,head=tangent[n]
        elif n<1024:dx,dy=rng.choice(edges),rng.choice(edges)
        elif n<3584:dx,dy=[rng.randrange(-100000,100001)for _ in range(2)]
        else:dx,dy=[rng.randrange(-2**31,2**31)for _ in range(2)]
        px,py=signed(ox+dx),signed(oy+dy);radius=653 if head else 819
        coarse=lambda p,o:((((p>>16)-(o>>16))&65535)+1)&65535
        x,y=signed(px-ox),signed(py-oy)
        hit=int(coarse(px,ox)<=2 and coarse(py,oy)<=2 and abs(x)<=52429 and abs(y)<=52429
                and (x>>6)**2+(y>>6)**2<=radius*radius)
        rows.append(struct.pack('<4iBB',px,py,ox,oy,head,hit))
    sources=[]
    header='#include <stdint.h>\ntypedef struct{int32_t xy[4];uint8_t head,expected;} case_t;\ntypedef char layout[sizeof(case_t)==18?1:-1];\n'
    for bank in range(1,9):
        blob=rows[(bank-1)*512:bank*512]
        p=OUT/('cases%d.c'%bank)
        p.write_text('#include "cases.h"\n#pragma bank %d\nconst case_t cases%d[]={\n'%(bank,bank)+',\n'.join('{{%dL,%dL,%dL,%dL},%d,%d}'%struct.unpack('<4iBB',r)for r in blob)+'\n};\n')
        sources.append(p);header+='extern const case_t cases%d[];\n'%bank
    (OUT/'cases.h').write_text(header)
    (OUT/'near.c').write_text('''#include <gb/gb.h>
#pragma bank 5
uint8_t gbc_object_touch(const uint8_t *,const uint8_t *,uint8_t) __sdcccall(0);
extern uint8_t pose[12],object[18];
uint8_t fixture_touch(uint8_t head) BANKED {return gbc_object_touch(pose+1,object+1,head);}
''')
    driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "cases.h"
uint8_t fixture_touch(uint8_t) BANKED;
uint8_t pose[12],object[18];
volatile uint16_t completed,failures,bank_failures,guard_failures;
volatile uint8_t done;
static void check(const case_t *p,uint8_t bank){
 uint16_t i;uint8_t j;
 for(i=0;i<512;++i){
  memset(pose,0xa5,sizeof(pose));memset(object,0x5a,sizeof(object));
  memcpy(pose+1,p[i].xy,8);memcpy(object+6,p[i].xy+2,8);
  if(fixture_touch(p[i].head)!=p[i].expected)++failures;
  if(CURRENT_BANK!=bank)++bank_failures;
  if(memcmp(pose+1,p[i].xy,8)||memcmp(object+6,p[i].xy+2,8))++guard_failures;
  for(j=0;j<sizeof(pose);++j)if((j<1||j>8)&&pose[j]!=0xa5)++guard_failures;
  for(j=0;j<sizeof(object);++j)if((j<6||j>13)&&object[j]!=0x5a)++guard_failures;
  ++completed;
 }
}
void main(void){cpu_fast();
'''
    for bank in range(1,9):driver+='SWITCH_ROM(%d);check(cases%d,%d);\n'%(bank,bank,bank)
    driver+='done=1;while(1)vsync();}\n';(OUT/'check.c').write_text(driver)
    gen=BASE/'build/gen'
    tables=sorted(gen.glob('physics_quarter_*.c'))+sorted(gen.glob('physics_scale_*.c'))
    command=[str(BASE/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(OUT),'-o',str(OUT/'check.gbc'),str(OUT/'check.c'),str(OUT/'near.c'),str(OUT/'touch.s'),str(BASE/'src/physics_mul_fast.s'),str(BASE/'src/physics_kmul_fast.s'),*map(str,sources+tables)]
    r=subprocess.run(command,capture_output=True,text=True);assert not r.returncode,r.stdout+r.stderr
    sym={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(OUT/'check.noi').read_text())}
    p=PyBoy(str(OUT/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0)
    def word(name):a=sym['_'+name];return p.memory[a]+256*p.memory[a+1]
    try:
        for _ in range(100):
            p.tick(100,False)
            if p.memory[sym['_done']]:break
        report={'cases':word('completed'),'failures':word('failures'),'bank_failures':word('bank_failures'),'guard_failures':word('guard_failures'),
                'source_sha256':hashlib.sha256(source).hexdigest(),'source_still_current':(BASE/'src/objects_touch_fast.s').read_bytes()==source}
        assert report['cases']==4096 and not any(report[k]for k in('failures','bank_failures','guard_failures'))and report['source_still_current'],report
    finally:p.stop(save=False)
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
