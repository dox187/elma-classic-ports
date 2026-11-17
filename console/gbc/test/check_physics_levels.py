"""Verify every level's collision bank/cache protocol on HOST and real SM83.

The converter model supplies binary protocol expectations; a separate source-edge
coverage pass verifies that every quantized original edge subdivision is present.
"""
import argparse
import ctypes as C
import importlib.util
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys

from pyboy import PyBoy

BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('physics_converter',BASE/'tools/physics_level.py')
converter=importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)


def command(args,log):
    run=subprocess.run(list(map(str,args)),capture_output=True,text=True)
    log.write_text(run.stdout+run.stderr)
    if run.returncode:
        raise RuntimeError(log.read_text())


def source_models(res):
    models=[]
    for level in converter.internal_levels(converter.Resource(res)):
        ox,oy,w,h,segments,cells,edge_count=converter.geometry(level)
        models.append((level,ox,oy,w,h,cells))
    return models


def expected(cell,cx,cy,sub):
    leaf=cell if len(cell)<=converter.DENSE_THRESHOLD else [s for s in cell
        if converter.overlaps(s,cx*4096+(sub&3)*1024,cy*4096+(sub>>2)*1024,1024)]
    return b''.join(converter.record(s,cx,cy)for s in leaf)


def host_check(gen,out,models):
    (out/'host.c').write_text('''#include <string.h>
#include "physics_core.h"
#include "runtime.h"
uint8_t physics_select_level(uint8_t) GBC_BANKED;void physics_reset_current(void) GBC_BANKED;void physics_set_gravity(uint8_t) GBC_BANKED;
uint8_t fixture_query(uint8_t x,uint8_t y,uint8_t sub,uint8_t *out) {
 const seg_t *s;uint8_t n=0;seg_query(x,y,sub);
 while((s=seg_next())){memcpy(out+n*18,s,18);++n;}return n;
}
uint8_t fixture_gravity(void){return Bike.gravity;}
void fixture_wheel0(int32_t *p){p[0]=gbc_bike.wheel[0].x;p[1]=gbc_bike.wheel[0].y;}
''')
    common=[BASE/'src'/n for n in('physics.c','physics_core.c','physics_contacts.c','physics_collision.c','physics_math.c','physics_math32.c','physics_sweep.c')]
    data=[gen/'physics_level_data.c']+sorted(gen.glob('physics_bank_*.c'))
    command(['cc','-shared','-fPIC','-O0','-fwrapv','-Wno-unknown-pragmas',
             '-I'+str(BASE/'src'),'-I'+str(gen),out/'host.c',*common,*data,
             '-o',out/'host.dylib'],out/'host-compile.log')
    f=C.CDLL(str(out/'host.dylib'))
    f.fixture_query.argtypes=[C.c_uint8,C.c_uint8,C.c_uint8,C.POINTER(C.c_uint8)]
    f.fixture_query.restype=f.physics_select_level.restype=C.c_uint8
    buf=(C.c_uint8*(255*18))();xy=(C.c_int32*2)();queries=coverage=0
    for index,(level,ox,oy,w,h,cells)in enumerate(models):
        assert f.physics_select_level(index)==1
        f.physics_reset_current();f.fixture_wheel0(xy)
        assert list(xy)==[math.floor(v*65536+.5)for v in level.start()]
        for ci,cell in enumerate(cells):
            cx,cy=ci%w,ci//w
            for sub in(range(16)if len(cell)>converter.DENSE_THRESHOLD else(0,15)):
                count=f.fixture_query(cx,cy,sub,buf)
                assert bytes(buf[:count*18])==expected(cell,cx,cy,sub),(index,ci,sub)
                queries+=1
        # Independent endpoint coverage from the original polygons. No bank
        # packing or record() helper participates in this expectation.
        for grass,polygon in level.polygons:
            if grass:continue
            for i,(x,y)in enumerate(polygon):
                ex,ey=polygon[(i+1)%len(polygon)];dx,dy=ex-x,ey-y
                n=int(math.hypot(dx,dy)/8)+1
                for k in range(n):
                    px=math.floor((x-ox+dx*k/n)*1024+.5)
                    py=math.floor((y-oy+dy*k/n)*1024+.5)
                    qx=math.floor((x-ox+dx*(k+1)/n)*1024+.5)
                    qy=math.floor((y-oy+dy*(k+1)/n)*1024+.5)
                    if px==qx and py==qy:continue
                    mx,my=(px+qx)//2,(py+qy)//2;cx,cy=mx//4096,my//4096
                    sub=((mx>>10)&3)|((my>>8)&12)
                    count=f.fixture_query(cx,cy,sub,buf)
                    endpoints=[struct.unpack_from('<hhhh',buf,j*18)for j in range(count)]
                    assert(px-cx*4096,py-cy*4096,qx-px,qy-py)in endpoints,(index,i,k)
                    coverage+=1
        for gravity in range(1,5):
            f.physics_set_gravity(gravity);assert f.fixture_gravity()==gravity-1
        f.physics_set_gravity(0);assert f.fixture_gravity()==3
        f.physics_set_gravity(5);assert f.fixture_gravity()==3
        f.physics_reset_current();assert f.fixture_gravity()==1
    assert f.physics_select_level(len(models))==0 and f.physics_select_level(255)==0
    return common,data,{'host_queries':queries,'source_subdivisions_covered':coverage}


def native_check(gen,out,models,common,data):
    dense=[]
    for _,_,_,w,h,cells in models:dense.extend(len(c)>converter.DENSE_THRESHOLD for c in cells)
    flags=[sum((1<<j)for j in range(8)if i+j<len(dense)and dense[i+j])for i in range(0,len(dense),8)]
    (out/'meta.c').write_text('#include <stdint.h>\n#pragma bank 14\n'
       +'const uint8_t fixture_widths[]={'+','.join(str(m[3])for m in models)+'};\n'
       +'const uint8_t fixture_heights[]={'+','.join(str(m[4])for m in models)+'};\n'
       +'const uint8_t fixture_dense[]={'+','.join(map(str,flags))+'};\n'
       +'const uint16_t fixture_magic=0xb14f;\n')
    (out/'native.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include "runtime.h"
#include "physics_core.h"
#include "riding_level.h"
uint8_t physics_select_level(uint8_t) GBC_BANKED;void physics_reset_current(void) GBC_BANKED;void physics_set_gravity(uint8_t) GBC_BANKED;
extern const uint8_t fixture_widths[],fixture_heights[],fixture_dense[];
extern const uint16_t fixture_magic;
volatile uint8_t fixture_level,fixture_x,fixture_y,fixture_sub,fixture_kind,fixture_done,fixture_ready;
volatile uint16_t fixture_failures;
void fixture_mark(void){}
void main(void) {
 uint16_t cell=0;uint8_t n,g;
 cpu_fast();SWITCH_ROM(14);fixture_ready=1;
 for(fixture_level=0;fixture_level<RIDING_LEVEL_COUNT;++fixture_level) {
  if(!physics_select_level(fixture_level))++fixture_failures;
  physics_reset_current();fixture_kind=1;fixture_mark();
  for(g=1;g<=4;++g){physics_set_gravity(g);if(Bike.gravity!=g-1)++fixture_failures;}
  physics_reset_current();
  for(fixture_y=0;fixture_y<fixture_heights[fixture_level];++fixture_y)
   for(fixture_x=0;fixture_x<fixture_widths[fixture_level];++fixture_x,++cell) {
    n=(fixture_dense[cell>>3]&(1u<<(cell&7)))?16:1;
    for(fixture_sub=0;fixture_sub<n;++fixture_sub) {
     seg_query(fixture_x,fixture_y,fixture_sub);
     if(CURRENT_BANK!=14 || fixture_magic!=0xb14f)++fixture_failures;
     fixture_kind=2;fixture_mark();
    }
   }
 }
 fixture_done=1;while(1)vsync();
}
''')
    assembly=[p for p in sorted((BASE/'src').glob('physics_*.s'))if p.name not in ('physics_mul16.s','physics_suspension_fast.s','physics_brake_fast.s','physics_roll_fast.s','physics_supports_fast.s','physics_free_fast.s','physics_rider_response.s','physics_head_pose.s')]
    if not (gen/'physics_sine_16.c').is_file():
        subprocess.run([sys.executable,str(BASE/'tools/physics_sine.py'),'--out',str(gen)],check=True)
    tables=sorted((BASE/'build/gen').glob('physics_quarter_*.c'))+sorted((BASE/'build/gen').glob('physics_scale_*.c'))+sorted(gen.glob('physics_sine_*.c'))
    assert len(tables)==28,'generate the production arithmetic tables first'
    rom=out/'native.gbc'
    command([BASE/'.toolchain/gbdk/bin/lcc','-msm83:gb','-Wf--opt-code-size',
        '-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-Wl-g_riding_coefficient_bank_lo=252','-Wl-g_riding_coefficient_bank_hi=0','-I'+str(BASE/'src'),
        '-I'+str(gen),'-o',rom,out/'native.c',out/'meta.c',*common,*assembly,*data,*tables],out/'native-compile.log')
    sym={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',rom.with_suffix('.noi').read_text())}
    p=PyBoy(str(rom),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0)
    queries=0;selected=[];differences=[];last_observation=[None]
    def byte(name):return p.memory[sym['_fixture_'+name]]
    def mark(_):
        nonlocal queries
        if not byte('ready'):return
        li=byte('level');level,ox,oy,w,h,cells=models[li]
        if byte('kind')==1:
            a=sym['_gbc_bike']+10
            actual=struct.unpack('<ii',bytes(p.memory[a:a+8]))
            want=tuple(math.floor(v*65536+.5)for v in level.start())
            if actual!=want and len(differences)<5:differences.append(('spawn',li,actual,want))
            key=(1,li)
            if last_observation[0]!=key:selected.append(li)
            last_observation[0]=key;return
        x,y,sub=byte('x'),byte('y'),byte('sub')
        if x>=w or y>=h:
            if len(differences)<5:differences.append(('range',li,x,y,sub))
            return
        a=sym['_Seg_cur'];ptr=p.memory[a]+256*p.memory[a+1]
        count=p.memory[sym['_Seg_left']]
        actual=bytes(p.memory[ptr:ptr+count*18]) if count else b'';want=expected(cells[y*w+x],x,y,sub)
        if actual!=want and len(differences)<5:differences.append(('cell',li,x,y,sub,len(actual),len(want)))
        key=(2,li,x,y,sub)
        if last_observation[0]!=key:queries+=1
        last_observation[0]=key
    p.hook_register(0,sym['_fixture_mark'],mark,None)
    try:
        for _ in range(500):
            p.tick(100,False)
            if byte('done'):break
        assert byte('done'),'native level fixture did not finish'
        a=sym['_fixture_failures'];failures=p.memory[a]+256*p.memory[a+1]
        assert not failures and not differences,(failures,differences)
        assert selected==list(range(len(models))),selected
        assert queries==sum(16 if len(cell)>converter.DENSE_THRESHOLD else 1 for model in models for cell in model[5]),queries
    finally:p.stop(save=False)
    return{'native_queries':queries,'native_levels':len(selected),'bank_restore_failures':failures,
            'highest_data_bank':json.loads((gen/'physics_bank_manifest.json').read_text())['banks'][-1]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--res',type=Path,required=True)
    parser.add_argument('--gen',type=Path,default=BASE/'build/gen')
    parser.add_argument('--out',type=Path,default=BASE/'build/physics-level-check')
    parser.add_argument('--high-bank',action='store_true',help='regenerate at bank280 to exercise the MBC5 ninth bit')
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    gen=args.gen
    if args.high_bank:
        gen=args.out/'high-gen'
        command([sys.executable,BASE/'tools/physics_level.py','--res',args.res,'--out',gen,
                 '--hz','30','--damper','exponential','--bank-base','280'],args.out/'generation.log')
    models=source_models(args.res)
    common,data,report=host_check(gen,args.out,models)
    report.update(native_check(gen,args.out,models,common,data))
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
