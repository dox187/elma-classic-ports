"""Exact segment-capsule geometry against an independent integer oracle."""
import argparse
import ctypes as C
import json
from pathlib import Path
import random
import re
import subprocess

from pyboy import PyBoy
BASE=Path(__file__).resolve().parents[1]


def orientation(a,b,c):return(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def point_segment(p,a,b,r):
    x,y=p[0]-a[0],p[1]-a[1];dx,dy=b[0]-a[0],b[1]-a[1];length=dx*dx+dy*dy;dot=x*dx+y*dy
    if dot<=0:return x*x+y*y<r*r
    if dot>=length:return(p[0]-b[0])**2+(p[1]-b[1])**2<r*r
    return(x*dy-y*dx)**2<r*r*length

def oracle(row):
    px,py,qx,qy,ax,ay,ex,ey,r=row;p=(px,py);q=(qx,qy);a=(ax,ay);b=(ax+ex,ay+ey)
    cross=lambda x,y:(x<=0<=y)or(y<=0<=x)
    overlap=lambda axis:max(min(p[axis],q[axis]),min(a[axis],b[axis]))<=min(max(p[axis],q[axis]),max(a[axis],b[axis]))
    if overlap(0)and overlap(1)and cross(orientation(p,q,a),orientation(p,q,b))and cross(orientation(a,b,p),orientation(a,b,q)):return 1
    return int(point_segment(p,a,b,r)or point_segment(q,a,b,r)or point_segment(a,p,q,r)or point_segment(b,p,q,r))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=BASE/'src/physics_sweep.c')
    parser.add_argument('--gen',type=Path,default=BASE/'build/gen')
    parser.add_argument('--out',type=Path,default=BASE/'build/sweep-check')
    parser.add_argument('--vectors',type=int,default=8192)
    parser.add_argument('--captures',type=Path,help='append JSON capsule rows or records containing a row field')
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True);source=args.source.resolve();gen=args.gen.resolve()
    rows=[]
    for radius in(1,2,16,244,246,255):
        for y in(-radius-1,-radius,-radius+1,0,radius-1,radius,radius+1):
            rows.extend(((-500,y,1500,y,0,0,1000,0,radius),(y,-500,y,1500,0,0,0,1000,radius),
                         (-500,-500,1500,1500,0,y,1000,0,radius)))
    rows += [(0,0,0,0,x,y,0,0,244)for x,y in((0,0),(243,0),(244,0),(245,0),(172,172),(173,173),(-244,0))]
    for radius in (16,244,246):
        pairs=((-radius-1,-1),(-1,0),(0,1),(1,999),(999,1000),(1000,1001),
               (1001,1000+radius),(0,1000),(-1,1001),(-radius,500),(500,1000+radius))
        for px,qx in pairs:
            for py in (-radius-1,-radius,-radius+1,0,radius-1,radius,radius+1):
                for qy in (py,-py,0):
                    rows.append((px,py,qx,qy,0,0,1000,0,radius))
                    rows.append((py,px,qy,qx,0,0,0,1000,radius))
    for dx,dy in((3,4),(30,40),(300,400),(3000,4000),(8192,8191),(8192,1),(1,8192),(129,129)):
        length=(dx*dx+dy*dy)**.5
        for radius in(1,2,16,244,246,255):
            ax=round(dx/2-dy*radius/length);ay=round(dy/2+dx*radius/length)
            for ox in(-1,0,1):
                for oy in(-1,0,1):
                    rows.append((0,0,dx,dy,ax+ox,ay+oy,0,0,radius))
                    rows.append((0,0,dx,dy,ax+ox,ay+oy,dx//10,dy//10,radius))
    rng=random.Random(0xCCD244)
    assert len(rows)<=args.vectors<=65535
    while len(rows)<args.vectors:
        p=[rng.randint(-8192,12288)for _ in range(2)];q=[rng.randint(-8192,12288)for _ in range(2)]
        a=[rng.randint(-8704,12800)for _ in range(2)];b=[rng.randint(-8704,12800)for _ in range(2)]
        if max(abs(q[i]-p[i])for i in range(2))>8192 or max(abs(b[i]-a[i])for i in range(2))>8192:continue
        rows.append((*p,*q,*a,b[0]-a[0],b[1]-a[1],rng.randint(1,255)))
    captured=[]
    if args.captures:
        for record in json.loads(args.captures.read_text()):
            row=record['row']if isinstance(record,dict)else record
            assert len(row)==9 and all(isinstance(v,int)for v in row),row
            assert all(-32768<=v<=32767 for v in row[:8])and 1<=row[8]<=255,row
            captured.append(tuple(row))
        rows.extend(captured)
    assert len(rows)<=65535
    expected=[oracle(row)for row in rows]
    stub='''#include "physics_core.h"\nconst seg_t *Seg_cur;uint8_t Seg_left,Seg_subcell;
void seg_query(uint8_t x,uint8_t y,uint8_t sub){x;y;sub;Seg_left=0;Seg_subcell=255;}
const seg_t *seg_next(void){return 0;}
'''
    (out/'stub.c').write_text(stub)
    command=['cc','-shared','-fPIC','-O0','-fwrapv','-DPHYSICS_SWEEP_TEST','-I'+str(BASE/'src'),'-I'+str(gen),source,BASE/'src/physics_math.c',out/'stub.c','-o',out/'host.dylib']
    result=subprocess.run(list(map(str,command)),capture_output=True,text=True);(out/'host-compile.log').write_text(result.stdout+result.stderr)
    assert not result.returncode,result.stderr
    f=C.CDLL(str(out/'host.dylib')).riding_capsule_test;f.argtypes=[C.c_int16]*8+[C.c_uint16];f.restype=C.c_uint8
    for i,(row,want)in enumerate(zip(rows,expected)):assert f(*row)==want,(i,row,want,f(*row))
    batches=[rows[i:i+512]for i in range(0,len(rows),512)]
    header='#include <stdint.h>\ntypedef struct{int16_t p[8];uint16_t radius;uint8_t expected;} case_t;\n'
    sources=[]
    banks=(1,2,3,*range(5,20),*range(44,256))
    assert len(batches)<=len(banks)
    for batch_index,(bank,batch)in enumerate(zip(banks,batches)):
        offset=batch_index*512;name='cases%d'%bank
        header+='extern const case_t %s[];\n#define COUNT%d %d\n'%(name,bank,len(batch))
        initializers=['{{'+','.join(map(str,row[:8]))+'},%d,%d}'%(row[8],expected[offset+i])for i,row in enumerate(batch)]
        path=out/('cases%d.c'%bank);path.write_text('#include "cases.h"\n#pragma bank %d\n'%bank+'const case_t '+name+'[]={\n'+',\n'.join(initializers)+'\n};\n');sources.append(path)
    (out/'cases.h').write_text(header)
    driver='''#include <gb/gb.h>\n#include <gb/cgb.h>\n#include "cases.h"
uint8_t riding_capsule_test(int16_t,int16_t,int16_t,int16_t,int16_t,int16_t,int16_t,int16_t,uint16_t) BANKED;
volatile uint16_t sweep_failures,bank_failures,sweep_vectors;volatile uint8_t sweep_done;
static void check(const case_t*v,uint16_t count,uint8_t bank){uint16_t i;
 for(i=0;i<count;++i){
  if(riding_capsule_test(v[i].p[0],v[i].p[1],v[i].p[2],v[i].p[3],v[i].p[4],v[i].p[5],v[i].p[6],v[i].p[7],v[i].radius)!=v[i].expected)++sweep_failures;
  if(CURRENT_BANK!=bank)++bank_failures;
  ++sweep_vectors;
 }}
void main(void){cpu_fast();\n'''
    for bank in banks[:len(batches)]:driver+='SWITCH_ROM(%d);check(cases%d,COUNT%d,%d);\n'%(bank,bank,bank,bank)
    driver+='sweep_done=1;while(1)vsync();}\n';(out/'native.c').write_text(driver)
    assembly=[BASE/'src'/name for name in('physics_math.s','physics_mul_fast.s','physics_kmul_fast.s','physics_div_fast.s','physics_shift_fast.s')]
    tables=sorted(gen.glob('physics_quarter_*.c'))+sorted(gen.glob('physics_scale_*.c'))
    command=[BASE/'.toolchain/gbdk/bin/lcc','-msm83:gb','-DPHYSICS_ASM','-DPHYSICS_SWEEP_TEST','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(BASE/'src'),'-I'+str(gen),'-I'+str(out),'-o',out/'native.gbc',out/'native.c',out/'stub.c',source,BASE/'src/physics_math.c',*assembly,*sources,*tables]
    result=subprocess.run(list(map(str,command)),capture_output=True,text=True);(out/'native-compile.log').write_text(result.stdout+result.stderr)
    assert not result.returncode,result.stderr
    symbols={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(out/'native.noi').read_text())}
    emu=PyBoy(str(out/'native.gbc'),window='null',sound_emulated=False,cgb=True);emu.set_emulation_speed(0)
    try:
        for _ in range(500):
            emu.tick(100,False)
            if emu.memory[symbols['_sweep_done']]:break
        assert emu.memory[symbols['_sweep_done']],'native sweep vectors did not finish'
        def word(name):a=symbols[name];return emu.memory[a]+256*emu.memory[a+1]
        report={'captured_vectors':len(captured),'vectors':len(rows),'native_vectors':word('_sweep_vectors'),'failures':word('_sweep_failures'),'bank_restore_failures':word('_bank_failures')}
        assert report['native_vectors']==len(rows),report
        assert report['failures']==report['bank_restore_failures']==0,report
    finally:emu.stop(save=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
