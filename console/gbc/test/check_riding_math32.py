"""Exact host/int64 and native SM83 tests, including 49/50-bit cancellation.

Builds an isolated ROM in ignored build/math32-check; it never modifies the
game ROM, generated level data or physical coefficients.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess
import sys

from pyboy import PyBoy

BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'build/math32-check'
SOURCE=BASE/'src'
I32_MIN,I32_MAX=-(1<<31),(1<<31)-1


def clamp(x,bits=32):
    return max(-(1<<(bits-1)),min((1<<(bits-1))-1,x))


def vectors():
    r=random.Random(320048)
    xs=[I32_MIN,I32_MIN+1,-1073741824,-65537,-65536,-32769,-32768,-1,0,1,32767,32768,65535,65536,1073741824,I32_MAX]
    ys=[-32768,-32767,-1,0,1,32767]
    kmul=[(x,m,e)for x in xs for m in (0,1,127,128,255)for e in (1,2,8,15,16)]
    kmul += [(r.randint(I32_MIN,I32_MAX),r.randrange(256),r.randint(1,16))for _ in range(256)]
    kmul += [(sign*((1<<(e+7))+offset),m,e)for e in range(1,8)for sign in (-1,1)
             for offset in (-1,0,1)for m in (0,1,127,128,255)]
    mulq=[(x,y,s)for x in xs for y in ys for s in (1,2,15,16)]
    muls=[(x,y,s)for x in xs for y in ys for s in (0,1,15,16)]
    mulq += [(r.randint(I32_MIN,I32_MAX),r.randint(-32768,32767),r.randint(1,16))for _ in range(512)]
    mulq += [(x,y,s)for x in (-32768,-32767,32767)for y in (-32768,-16384,16384,32767)for s in (10,14)]
    muls += [(r.randint(I32_MIN,I32_MAX),r.randint(-32768,32767),r.randint(0,16))for _ in range(512)]
    dot=[(a,b,c,d,s)for a,b,c,d in [(I32_MIN,I32_MIN,-32768,-32768),
        (I32_MIN,I32_MIN,32767,32767),(I32_MAX,-I32_MAX,32767,32767),
        (I32_MIN,I32_MAX,-32768,-32768)]for s in range(1,17)]
    dot += [(r.randint(I32_MIN,I32_MAX),r.randint(I32_MIN,I32_MAX),r.randint(-32768,32767),r.randint(-32768,32767),r.randint(1,16))for _ in range(128)]
    dot += [(r.randint(-32768,32767),r.randint(-32768,32767),r.randint(-16384,16384),r.randint(-16384,16384),r.randint(1,16))for _ in range(128)]
    dot += [(a,b,c,d,s)for a,b,c,d in [(-32768,-32768,-32768,-32768),
        (32767,32767,32767,32767),(-32768,-32768,32767,32767),(-32768,32767,-32768,-32768)]for s in (1,2,15,16)]
    dot += [(a,b,c,d,s)for a in (-32768,-32767,32767)for b in (-32768,-32767,32767)
            for c,d in ((-16384,-16384),(-16384,16384),(16384,-16384),(16384,16384),
                        (-16385,16384),(16384,16385))for s in (10,14)]
    dot += [(a,b,c,d,s)for a in (-32768,-32767,32767)for b in (-32768,-32767,32767)
            for c in (-32768,-32767,32767)for d in (-32768,-32767,32767)for s in (10,14)]
    dot += [(r.randint(-32768,32767),r.randint(-32768,32767),r.randint(-32768,32767),
             r.randint(-32768,32767),r.choice((10,14)))for _ in range(64)]
    for _ in range(256):
        x=r.randint(I32_MIN+1,I32_MAX-1);y=r.randint(-32767,32767)
        dot.append((x,x+r.choice((-1,0,1)),y,-y,r.randint(1,16)))
    torque=[([I32_MIN]*2,[I32_MIN]*2,[-32768]*2,[32767]*2),
            ([I32_MIN]*2,[I32_MIN]*2,[32767]*2,[-32768]*2),
            ([I32_MIN]*2,[I32_MIN]*2,[-32768]*2,[-32768]*2),
            ([-32768]*2,[-32768]*2,[-32768]*2,[32767]*2),
            ([-32768]*2,[-32768]*2,[32767]*2,[-32768]*2),
            ([-32768]*2,[-32768]*2,[-32768,32767],[32767,-32768]),
            ([32767]*2,[-32768]*2,[-32768]*2,[-32768]*2)]
    for _ in range(128):
        torque.append(([r.randint(I32_MIN,I32_MAX)for i in range(2)],
                       [r.randint(I32_MIN,I32_MAX)for i in range(2)],
                       [r.randint(-32768,32767)for i in range(2)],
                       [r.randint(-32768,32767)for i in range(2)]))
    for _ in range(128):
        x=[r.randint(I32_MIN+1,I32_MAX-1)for i in range(2)]
        y=[v+r.choice((-1,0,1))for v in x];k=[r.randint(-32768,32767)for i in range(2)]
        torque.append((x,y,k,k))
    for _ in range(241):
        torque.append(([r.randint(-32768,32767)for i in range(2)],
                       [r.randint(-32768,32767)for i in range(2)],
                       [r.randint(-32768,32767)for i in range(2)],
                       [r.randint(-32768,32767)for i in range(2)]))
    return kmul,mulq,muls,dot,torque


class Torque(C.Structure):
    _fields_=[('relx',C.c_int32*2),('rely',C.c_int32*2),('kx',C.c_int16*2),('ky',C.c_int16*2)]


def main(lcc,implementation=None,out=None,assembly=None,multiply_assembly=None):
    global OUT
    if out is not None:OUT=out.resolve()
    implementation=implementation or SOURCE/'physics_math32.c'
    assembly=assembly or SOURCE/'physics_math32.s'
    multiply_assembly=multiply_assembly or SOURCE/'physics_mul_fast.s'
    source_files={'math32_c':implementation,'math32_s':assembly,
                  'mul16_s':multiply_assembly,'kmul_s':SOURCE/'physics_kmul_fast.s',
                  'test_driver_python':Path(__file__)}
    source_sha256={name:hashlib.sha256(path.read_bytes()).hexdigest()for name,path in source_files.items()}
    OUT.mkdir(parents=True,exist_ok=True)
    cases=vectors()
    expected=[
        [clamp((x*m+(1<<(e-1)))>>e)for x,m,e in cases[0]],
        [clamp((x*y+(1<<(s-1)))>>s)for x,y,s in cases[1]],
        [clamp(x*y>>s)for x,y,s in cases[2]],
        [clamp((a*c+b*d+(1<<(s-1)))>>s)for a,b,c,d,s in cases[3]],
        [clamp(sum(kx[i]*ry[i]-ky[i]*rx[i]for i in range(2))>>10,16)for rx,ry,kx,ky in cases[4]]]
    library=OUT/('host.dylib'if sys.platform=='darwin'else'host.so')
    subprocess.run(['cc','-shared','-fPIC','-std=c99','-I'+str(SOURCE),str(implementation),'-o',str(library)],check=True)
    host=C.CDLL(str(library));assert C.sizeof(Torque)==24
    signatures=[('riding_kmul32',[C.c_int32,C.c_uint8,C.c_uint8]),
                ('riding_mulq32',[C.c_int32,C.c_int16,C.c_uint8]),
                ('riding_mulshift32',[C.c_int32,C.c_int16,C.c_uint8]),
                ('riding_dotq32',[C.c_int32,C.c_int32,C.c_int16,C.c_int16,C.c_uint8])]
    for kind,(name,args)in enumerate(signatures):
        fn=getattr(host,name);fn.argtypes=args;fn.restype=C.c_int32
        for row,want in zip(cases[kind],expected[kind]):assert fn(*row)==want,(name,row,want)
    host.riding_torque_input32.argtypes=[C.POINTER(Torque)];host.riding_torque_input32.restype=C.c_int16
    for row,want in zip(cases[4],expected[4]):
        t=Torque(*[(typ*2)(*values)for typ,values in zip((C.c_int32,C.c_int32,C.c_int16,C.c_int16),row)])
        assert host.riding_torque_input32(C.byref(t))==want
    structs=['typedef struct {int32_t x;uint8_t m,e;int32_t expected;} kv_t;',
             'typedef struct {int32_t x;int16_t y;uint8_t shift;int32_t expected;} mv_t;',
             'typedef struct {int32_t a,b;int16_t c,d;uint8_t shift;int32_t expected;} dv_t;',
             'typedef struct {riding_torque32_t t;int16_t expected;} tv_t;']
    header='#include "physics_math32.h"\n'+'\n'.join(structs)+'\n'
    types=['kv_t','mv_t','mv_t','dv_t','tv_t'];sources=[]
    for kind in range(5):
        values=[]
        for row,want in zip(cases[kind],expected[kind]):
            if kind==4:
                init='{'+','.join('{'+','.join(str(v)+('L'if i<2 else'')for v in a)+'}'for i,a in enumerate(row))+'}'
                values.append('{'+init+','+str(want)+'}')
            else:
                long_fields={0,1}if kind==3 else{0}
                values.append('{'+','.join(str(v)+('L'if i in long_fields else'')for i,v in enumerate(row))+','+str(want)+'L}')
        name='vectors%d'%kind;header+='extern const %s %s[];\n#define COUNT%d %d\n'%(types[kind],name,kind,len(values))
        path=OUT/(name+'.c');path.write_text('#include "vectors.h"\n#pragma bank %d\n'%(kind+1)
            +'const '+types[kind]+' '+name+'[]={\n'+',\n'.join(values)+'\n};\n');sources.append(path)
    (OUT/'vectors.h').write_text(header)
    driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include "vectors.h"
volatile uint8_t math32_done;
volatile uint16_t failures[5],bank_failures;
volatile uint16_t first_bad_index=65535;
volatile uint8_t first_bad_kind;
volatile int32_t first_actual,first_expected;
static void check(uint8_t kind,uint16_t index,int32_t actual,int32_t expected) {
 if(actual!=expected) {++failures[kind];if(first_bad_index==65535){first_bad_kind=kind;first_bad_index=index;first_actual=actual;first_expected=expected;}}
}
void main(void) {uint16_t i;cpu_fast();
 SWITCH_ROM(1);for(i=0;i<COUNT0;++i){check(0,i,riding_kmul32(vectors0[i].x,vectors0[i].m,vectors0[i].e),vectors0[i].expected);if(CURRENT_BANK!=1)++bank_failures;}
 SWITCH_ROM(2);for(i=0;i<COUNT1;++i){check(1,i,riding_mulq32(vectors1[i].x,vectors1[i].y,vectors1[i].shift),vectors1[i].expected);if(CURRENT_BANK!=2)++bank_failures;}
 SWITCH_ROM(3);for(i=0;i<COUNT2;++i){check(2,i,riding_mulshift32(vectors2[i].x,vectors2[i].y,vectors2[i].shift),vectors2[i].expected);if(CURRENT_BANK!=3)++bank_failures;}
 SWITCH_ROM(4);for(i=0;i<COUNT3;++i){check(3,i,riding_dotq32(vectors3[i].a,vectors3[i].b,vectors3[i].c,vectors3[i].d,vectors3[i].shift),vectors3[i].expected);if(CURRENT_BANK!=4)++bank_failures;}
 SWITCH_ROM(5);for(i=0;i<COUNT4;++i){check(4,i,riding_torque_input32(&vectors4[i].t),vectors4[i].expected);if(CURRENT_BANK!=5)++bank_failures;}
 math32_done=1;while(1)vsync();}
'''
    (OUT/'driver.c').write_text(driver)
    gen=BASE/'build/gen'
    if not(gen/'physics_quarter_20.c').is_file():
        subprocess.run([sys.executable,str(BASE/'tools/mul_table.py'),'--out',str(gen)],check=True)
    scale = gen/'physics_scale_36.c'
    if not scale.is_file() or 'physics_scale_planes_36' not in scale.read_text():
        subprocess.run([sys.executable,str(BASE/'tools/scale_table.py'),'--out',str(gen)],check=True)
    table_sources=list(gen.glob('physics_quarter_*.c'))+list(gen.glob('physics_scale_*.c'))
    cmd=[str(lcc),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-Wl-g_riding_coefficient_bank_lo=252','-Wl-g_riding_coefficient_bank_hi=0',
         '-I'+str(SOURCE),'-I'+str(OUT),'-o',str(OUT/'check.gbc'),str(OUT/'driver.c'),
         str(implementation),str(assembly),str(multiply_assembly),
         str(SOURCE/'physics_kmul_fast.s')]+list(map(str,sources+table_sources))
    subprocess.run(cmd,check=True,capture_output=True,text=True)
    sym={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9a-fA-F]+)',(OUT/'check.noi').read_text())}
    p=PyBoy(str(OUT/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0)
    active=[];returns=set();timing={name:[]for name,_ in signatures}
    timing['riding_torque_input32']=[]
    def completed(key):
        if not active or active[-1]['return']!=key or p.register_file.SP!=active[-1]['sp']+2:return
        call=active.pop()
        timing[call['name']].append({'cycles':p._cycles()-call['cycles'],'narrow':call['narrow'],'fast':call['fast']})
    def entered(name):
        sp=p.register_file.SP;address=p.memory[sp]+256*p.memory[sp+1];key=(0,address)
        if key not in returns:p.hook_register(*key,completed,key);returns.add(key)
        x=int.from_bytes(bytes(p.memory[sp+2:sp+6]),'little',signed=True)
        narrow=-32768<=x<=32767
        if name=='riding_dotq32':
            y=int.from_bytes(bytes(p.memory[sp+6:sp+10]),'little',signed=True)
            narrow=narrow and -32768<=y<=32767
        elif name=='riding_torque_input32':
            address=p.memory[sp+2]+256*p.memory[sp+3]
            narrow=all(-32768<=int.from_bytes(bytes(p.memory[address+i:address+i+4]),'little',signed=True)<=32767 for i in (0,4,8,12))
        fast=False
        if name=='riding_kmul32':
            e=p.memory[sp+7];fast=narrow and (e>=8 or abs(x)<=1<<(e+7))
        elif name=='riding_mulq32':fast=narrow and p.memory[sp+8] in (10,14)
        elif name=='riding_dotq32':
            c=int.from_bytes(bytes(p.memory[sp+10:sp+12]),'little',signed=True)
            d=int.from_bytes(bytes(p.memory[sp+12:sp+14]),'little',signed=True)
            fast=narrow and p.memory[sp+14] in (10,14)
        elif name=='riding_torque_input32':fast=narrow
        active.append({'return':key,'sp':sp,'cycles':p._cycles(),'name':name,'narrow':narrow,'fast':fast})
    for name in timing:
        address=sym['_'+name];p.hook_register(address>>16,address&65535,entered,name)
    try:
        for _ in range(200):
            p.tick(100)
            if p.memory[sym['_math32_done']]:break
        def number(name,n=2,signed=False):
            a=sym[name];return int.from_bytes(bytes(p.memory[a:a+n]),'little',signed=signed)
        assert number('_math32_done',1),'native math32 timed out'
        a=sym['_failures'];failures=[int.from_bytes(bytes(p.memory[a+i*2:a+i*2+2]),'little')for i in range(5)]
        report={'vectors':dict(zip(('kmul32','mulq32','mulshift32','dotq32','torque_input32'),map(len,cases))),
                'failures':failures,'bank_restore_failures':number('_bank_failures'),'torque_struct_bytes':24,
                'first_bad_index':number('_first_bad_index'),'first_bad_kind':number('_first_bad_kind',1),
                'first_actual':number('_first_actual',4,True),'first_expected':number('_first_expected',4,True),
                'native_frames':p.frame_count,'host_int64_matches_python':True}
        assert source_sha256=={name:hashlib.sha256(path.read_bytes()).hexdigest()for name,path in source_files.items()},'Math sources changed during the native check'
        report['source_sha256']=source_sha256
        report['api_cycles']={}
        for name,records in timing.items():
            report['api_cycles'][name]={}
            for label in ('all','narrow','wide','asm_fast'):
                values=[r['cycles']for r in records if label=='all' or (r['fast'] if label=='asm_fast' else r['narrow']==(label=='narrow'))]
                if values:report['api_cycles'][name][label]={'calls':len(values),'min':min(values),'max':max(values),'mean':sum(values)/len(values)}
        (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
        assert not any(failures) and report['bank_restore_failures']==0,report
    finally:p.stop(save=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--lcc',type=Path,default=BASE/'.toolchain/gbdk/bin/lcc')
    parser.add_argument('--implementation',type=Path,help='isolated candidate C implementation')
    parser.add_argument('--out',type=Path,help='separate build directory for candidate checks')
    parser.add_argument('--assembly',type=Path,help='isolated candidate assembly helpers')
    parser.add_argument('--multiply-assembly',type=Path,help='isolated candidate signed16 multiplication dependency')
    args=parser.parse_args();main(args.lcc,args.implementation,args.out,args.assembly,args.multiply_assembly)
