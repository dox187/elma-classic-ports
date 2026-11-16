"""Prove exact generated constant entries, wide fallback,16 saturation and banks.

The generator exhaustively decodes every narrow input for every coefficient;
the compiled HOST int64 oracle independently verifies those same inputs.
Native tests exercise both API families, boundary/random inputs and wide x.
"""
import argparse
import ctypes as C
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import re
import subprocess
import sys
from pyboy import PyBoy

BASE=Path(__file__).resolve().parents[1]


def clamp(x,bits):return max(-(1<<(bits-1)),min((1<<(bits-1))-1,x))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--constants',type=Path,default=BASE/'build/gen/riding_constants.h')
    p.add_argument('--out',type=Path,default=BASE/'build/coefficient-check')
    p.add_argument('--first-bank',type=int,choices=(252,477,508),default=252)
    p.add_argument('--assembly',type=Path,default=BASE/'src/physics_math32.s')
    p.add_argument('--lcc',type=Path,default=BASE/'.toolchain/gbdk/bin/lcc')
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True);source=BASE/'src';generator=BASE/'tools/math32_coefficients.py'
    spec=importlib.util.spec_from_file_location('coefficients',generator);g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
    tables=out/'tables';manifest=g.generate(a.constants,tables,first_bank=a.first_bank);pairs=g.coefficients(a.constants);ordered=sorted(pairs)
    sources=[source/'physics_math32.c',a.assembly,source/'physics_math32.h',source/'physics_mul_fast.s',source/'physics_kmul_fast.s',a.constants,generator,Path(__file__)]
    sha={path.name:hashlib.sha256(path.read_bytes()).hexdigest()for path in sources}
    lib=out/('host.dylib'if sys.platform=='darwin'else'host.so');subprocess.run(['cc','-shared','-fPIC','-std=c99','-I'+str(source),str(source/'physics_math32.c'),'-o',str(lib)],check=True)
    host=C.CDLL(str(lib));host.riding_kmul32.argtypes=[C.c_int32,C.c_uint8,C.c_uint8];host.riding_kmul32.restype=C.c_int32
    checked=0
    for mult,e in ordered:
        for x in range(-32768,32768):assert host.riding_kmul32(x,mult,e)==(x*mult+(1<<(e-1)))>>e;checked+=1
    r=random.Random(477480);vectors=[]
    for index,(mult,e)in enumerate(ordered):
        xs=[-32768,-32767,-256,-1,0,1,255,256,32766,32767]+[r.randint(-32768,32767)for _ in range(6)]
        xs += [-2147483648,-8388609,-65537,-32769,32768,65536,8388608,2147483647]
        for x in xs:
            x16=(x+32768)%65536-32768
            vectors.append((x,clamp((x*mult+(1<<(e-1)))>>e,32),clamp((x16*mult+(1<<(e-1)))>>e,16),index))
    (out/'vectors.h').write_text('#include <stdint.h>\ntypedef struct{int32_t x,expected32;int16_t expected16;uint8_t index;} vector_t;\nextern const vector_t vectors[];\n#define COUNT %d\n'%len(vectors))
    (out/'vectors.c').write_text('#include "vectors.h"\n#pragma bank 1\nconst vector_t vectors[]={\n'+',\n'.join('{%dL,%dL,%d,%d}'%row for row in vectors)+'\n};\n')
    driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include "vectors.h"
#include "physics_coefficient_calls.h"
typedef int32_t (*call32_t)(int32_t) __sdcccall(0);
typedef int16_t (*call16_t)(int16_t) __sdcccall(0);
volatile uint8_t coefficient_done;
volatile uint16_t failures32,failures16,bank_failures,coefficient_cases;
typedef char packed_vector[sizeof(vector_t)==11?1:-1];
'''
    driver+='const call32_t calls32[]={'+','.join('riding_coeff32_'+pairs[pair][0]for pair in ordered)+'};\n'
    driver+='const call16_t calls16[]={'+','.join('riding_coeff16_'+pairs[pair][0]for pair in ordered)+'};\n'
    driver+='''void main(void){uint16_t i;int32_t x,want32;int16_t want16;uint8_t index;const volatile vector_t *v=vectors;
 disable_interrupts();DISPLAY_OFF;cpu_fast();SWITCH_ROM(1);
 for(i=0;i<COUNT;++i){x=v[i].x;want32=v[i].expected32;want16=v[i].expected16;index=v[i].index;
 if(calls32[index](x)!=want32)++failures32;
 if(CURRENT_BANK!=1||v[i].expected32!=want32)++bank_failures;
 if(calls16[index]((int16_t)x)!=want16)++failures16;
 if(CURRENT_BANK!=1||v[i].expected16!=want16)++bank_failures;
 ++coefficient_cases;}
 coefficient_done=1;while(1){} }
''';(out/'driver.c').write_text(driver)
    for tool in('mul_table.py','scale_table.py'):
        subprocess.run([sys.executable,str(BASE/'tools'/tool),'--out',str(tables)],check=True,capture_output=True,text=True)
    data=sorted(tables.glob('physics_coefficient_*.c'))+sorted(tables.glob('physics_quarter_*.c'))+sorted(tables.glob('physics_scale_*.c'))
    command=[str(a.lcc),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(source),'-I'+str(out),'-I'+str(tables),'-o',str(out/'check.gbc'),str(out/'driver.c'),str(out/'vectors.c'),str(source/'physics_math32.c'),str(a.assembly),str(source/'physics_mul_fast.s'),str(source/'physics_kmul_fast.s'),str(tables/'physics_coefficient_calls.s')]+list(map(str,data))
    subprocess.run(command,check=True,capture_output=True,text=True)
    symbols={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9a-fA-F]+)',(out/'check.noi').read_text())};rom=(out/'check.gbc').read_bytes()
    for bank in manifest['banks']:
        n=bank['bank'];assert symbols['_physics_coefficient_%d'%n]==(n<<16)|0x4000
        assert hashlib.sha256(rom[n*16384:(n+1)*16384]).hexdigest()==bank['sha256'],('coefficient ROM bank',n)
    emulator=PyBoy(str(out/'check.gbc'),window='null',sound_emulated=False,cgb=True);emulator.set_emulation_speed(0)
    active=[];returns=set();timing=[]
    def completed(key):
        if not active or active[-1]['key']!=key or active[-1]['sp']+2!=emulator.register_file.SP:return
        call=active.pop();call['cycles']=emulator._cycles()-call.pop('start');call.pop('sp');call.pop('key');timing.append(call)
    def entered(context):
        bits,mult,e=context;sp=emulator.register_file.SP;ret=emulator.memory[sp]+256*emulator.memory[sp+1];key=(0,ret)
        if key not in returns:emulator.hook_register(*key,completed,key);returns.add(key)
        size=bits//8;x=int.from_bytes(bytes(emulator.memory[sp+2:sp+2+size]),'little',signed=True)
        active.append({'bits':bits,'m':mult,'e':e,'x':x,'sp':sp,'key':key,'start':emulator._cycles()})
    for mult,e in ordered:
        for bits in(32,16):emulator.hook_register(0,symbols['_riding_coeff%d_%s'%(bits,pairs[mult,e][0])],entered,(bits,mult,e))
    try:
        for _ in range(200):
            emulator.tick(100)
            if emulator.memory[symbols['_coefficient_done']]:break
        def n(name,size=2):
            address=symbols['_'+name];return int.from_bytes(bytes(emulator.memory[address:address+size]),'little')
        report={name:n(name)for name in('failures32','failures16','bank_failures','coefficient_cases')}
        report.update({'done':n('coefficient_done',1),'host_exhaustive_cases':checked,'native_vectors_per_coefficient':24,'coefficients':len(ordered),'rom_bytes_verified':65536,'source_sha256':sha,'api_cycles':{}})
        for bits in(32,16):
            for kind in('narrow','wide'):
                cycles=[row['cycles']for row in timing if row['bits']==bits and (-32768<=row['x']<=32767)==(kind=='narrow')]
                if cycles:report['api_cycles']['coefficient%d_%s'%(bits,kind)]={'calls':len(cycles),'min':min(cycles),'max':max(cycles),'mean':sum(cycles)/len(cycles)}
        assert sha=={path.name:hashlib.sha256(path.read_bytes()).hexdigest()for path in sources},'Coefficient sources changed during the check'
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');(out/'calls.json').write_text(json.dumps(timing,indent=2)+'\n');print(json.dumps(report,indent=2))
        assert report['done']and report['coefficient_cases']==len(vectors)and not any(report[name]for name in('failures32','failures16','bank_failures')),report
    finally:emulator.stop(save=False)


if __name__=='__main__':main()
