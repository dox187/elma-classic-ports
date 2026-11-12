"""Check all 65536 phases against original HOST and native integer fsin.

All generated tables and fixtures stay under the requested ignored output.
The original interpolation and new lookup run in the same native ROM; table
bytes, logical/physical bank restoration and API cycle costs are checked.
"""
import argparse
import ctypes as C
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from pyboy import PyBoy

BASE=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=BASE/'build/sine-check')
    p.add_argument('--lcc',type=Path,default=BASE/'.toolchain/gbdk/bin/lcc')
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    source=BASE/'src';generator=BASE/'tools/physics_sine.py'
    source_files=[source/name for name in('physics_math.c','physics_math.h','physics_math.s','physics_mul_fast.s','physics_kmul_fast.s','physics_sin_fast.s','physics_sin_fast.h')]+[generator,Path(__file__)]
    sha={path.name:hashlib.sha256(path.read_bytes()).hexdigest()for path in source_files}
    spec=importlib.util.spec_from_file_location('sine_generator',generator);sine=importlib.util.module_from_spec(spec);spec.loader.exec_module(sine)
    tables=out/'tables';manifest=sine.generate(source/'physics_math.c',tables)
    table=sine.read_sintab(source/'physics_math.c');expected=[sine.interpolate(table,angle)for angle in range(65536)]
    library=out/('reference.dylib'if sys.platform=='darwin'else'reference.so')
    subprocess.run(['cc','-shared','-fPIC','-std=c99','-I'+str(source),str(source/'physics_math.c'),'-o',str(library)],check=True)
    reference=C.CDLL(str(library));reference.fsin.argtypes=[C.c_uint16];reference.fsin.restype=C.c_int16
    for angle,want in enumerate(expected):assert reference.fsin(angle)==want,('HOST fsin',angle,want)
    header='#include <stdint.h>\n';fixtures=[]
    for bank in range(44,52):
        name='sine_expected_%d'%bank;values=expected[(bank-44)*8192:(bank-43)*8192]
        header+='extern const int16_t '+name+'[];\n'
        path=out/(name+'.c');rows=[','.join(map(str,values[i:i+16]))for i in range(0,8192,16)]
        path.write_text('#include <stdint.h>\n#pragma bank %d\n'%bank+'const int16_t '+name+'[]={\n'+',\n'.join(rows)+'\n};\n');fixtures.append(path)
    (out/'expected.h').write_text(header)
    # Keep this native oracle independent when production fsin adopts lookup.
    (out/'original.c').write_text('#include "physics_math.h"\nstatic const int16_t original_table[257]={\n'
        +','.join(map(str,table))+'\n};\nint16_t sine_original_fsin(uint16_t a){\n'
        +' uint8_t i=a>>8,f=a&255;int16_t s0=original_table[i];\n'
        +' return s0+(int16_t)(mul16(original_table[i+1]-s0,f)>>8);\n}\n')
    driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include "physics_math.h"
#include "physics_sin_fast.h"
#include "expected.h"
int16_t sine_original_fsin(uint16_t);
volatile uint8_t sine_done;
volatile uint16_t sine_angle,first_bad;
volatile int16_t first_actual,first_expected;
volatile uint32_t sine_cases,sine_failures,reference_failures,bank_failures;
static void check(const volatile int16_t *values,uint16_t first,uint8_t bank){uint16_t i;int16_t want,actual;
 for(i=0;i<8192;++i){sine_angle=first+i;want=values[i];actual=riding_sin16(sine_angle);
  if(actual!=want){if(!sine_failures){first_bad=sine_angle;first_actual=actual;first_expected=want;}++sine_failures;}
  if(CURRENT_BANK!=bank||values[i]!=want)++bank_failures;
  if(sine_original_fsin(sine_angle)!=want)++reference_failures;
  if(CURRENT_BANK!=bank||values[i]!=want)++bank_failures;
  ++sine_cases;
 }}
void main(void){disable_interrupts();DISPLAY_OFF;cpu_fast();
'''
    for bank in range(44,52):driver+=' SWITCH_ROM(%d);check(sine_expected_%d,%du,%d);\n'%(bank,bank,(bank-44)*8192,bank)
    driver+=' sine_done=1;while(1){} }\n';(out/'driver.c').write_text(driver)
    for name in('mul_table.py','scale_table.py'):
        subprocess.run([sys.executable,str(BASE/'tools'/name),'--out',str(tables)],check=True,capture_output=True,text=True)
    data=sorted(tables.glob('physics_sine_*.c'))+sorted(tables.glob('physics_quarter_*.c'))+sorted(tables.glob('physics_scale_*.c'))
    cmd=[str(a.lcc),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(source),'-I'+str(out),'-o',str(out/'check.gbc'),str(out/'driver.c'),str(out/'original.c')]
    cmd += [str(source/name)for name in('physics_math.c','physics_math.s','physics_mul_fast.s','physics_kmul_fast.s','physics_sin_fast.s')]+list(map(str,data+fixtures))
    subprocess.run(cmd,check=True,capture_output=True,text=True)
    symbols={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9a-fA-F]+)',(out/'check.noi').read_text())}
    rom=(out/'check.gbc').read_bytes()
    for bank in range(16,20):
        assert symbols['_physics_sine_%d'%bank]==(bank<<16)|0x4000,('sine bank layout',bank)
        values=[sine.interpolate(table,phase+(32768 if bank>=18 else 0))for phase in range((bank&1)*8192,(bank&1)*8192+8192)]
        want=b''.join(value.to_bytes(2,'little',signed=True)for value in values)
        assert rom[bank*16384:(bank+1)*16384]==want,('sine ROM bytes',bank)
    for bank in range(44,52):
        assert symbols['_sine_expected_%d'%bank]==(bank<<16)|0x4000,('reference bank layout',bank)
        want=b''.join(value.to_bytes(2,'little',signed=True)for value in expected[(bank-44)*8192:(bank-43)*8192])
        assert rom[bank*16384:(bank+1)*16384]==want,('reference ROM bytes',bank)
    emulator=PyBoy(str(out/'check.gbc'),window='null',sound_emulated=False,cgb=True);emulator.set_emulation_speed(0)
    active=[];returns=set();timing={'riding_sin16':[],'sine_original_fsin':[]}
    def completed(key):
        if not active or active[-1]['key']!=key or active[-1]['sp']+2!=emulator.register_file.SP:return
        call=active.pop();timing[call['name']].append(emulator._cycles()-call['cycles'])
    def entered(name):
        sp=emulator.register_file.SP;ret=emulator.memory[sp]+256*emulator.memory[sp+1];key=(0,ret)
        if key not in returns:emulator.hook_register(*key,completed,key);returns.add(key)
        active.append({'name':name,'key':key,'sp':sp,'cycles':emulator._cycles()})
    for name in timing:
        address=symbols['_'+name];emulator.hook_register(address>>16,address&65535,entered,name)
    try:
        for _ in range(300):
            emulator.tick(100)
            if emulator.memory[symbols['_sine_done']]:break
        def n(name,size=4,signed=False):
            address=symbols['_'+name];return int.from_bytes(bytes(emulator.memory[address:address+size]),'little',signed=signed)
        report={name:n(name)for name in('sine_cases','sine_failures','reference_failures','bank_failures')}
        report.update({'done':n('sine_done',1),'first_bad':n('first_bad',2),'first_actual':n('first_actual',2,True),'first_expected':n('first_expected',2,True),
            'host_original_matches_python':True,'lookup_rom_bytes_verified':65536,'reference_rom_bytes_verified':131072,
            'negative_values_differ_from_negated_positive':manifest['negative_values_differ_from_negated_positive'],'source_sha256':sha,
            'api_cycles':{name:{'calls':len(values),'min':min(values),'max':max(values),'mean':sum(values)/len(values)}for name,values in timing.items()}})
        assert sha=={path.name:hashlib.sha256(path.read_bytes()).hexdigest()for path in source_files},'Sources changed during the sine check'
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
        assert report['done']and report['sine_cases']==65536 and not any(report[name]for name in('sine_failures','reference_failures','bank_failures')),report
    finally:emulator.stop(save=False)


if __name__=='__main__':main()
