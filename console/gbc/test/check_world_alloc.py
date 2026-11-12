"""Check the native round-robin bitmap claim against independent C/Python.

Includes all444 slots, wrap/boundary/zero/full maps, invalid high nibble,
random densities, mutation/guard checks, caller banks and IRQ preservation.
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


def reference(next_slot,bitmap):
    bitmap=bytearray(bitmap)
    for n in range(444):
        slot=(next_slot+n)%444;mask=1<<(slot&7)
        if bitmap[slot>>3]&mask:
            bitmap[slot>>3]&=~mask;return slot,bytes(bitmap)
    return 65535,bytes(bitmap)


def vectors():
    r=random.Random(44456);cases=[]
    for slot in range(444):
        data=bytearray(56);data[slot>>3]|=1<<(slot&7);data[55]|=0xf0
        cases += [(slot,bytes(data)),((slot+1)%444,bytes(data))]
    for slot in range(444):
        cases += [(slot,bytes(56)),(slot,bytes([255])*56),(slot,bytes(55)+b'\xf0')]
    data=bytes([255])*55+b'\xdf';next_slot=117
    for _ in range(445):
        cases.append((next_slot,data));selected,data=reference(next_slot,data)
        if selected!=65535:next_slot=(selected+1)%444
    while len(cases)<8192:
        density=r.choice((0,1,4,16,64,128,255));data=bytearray(56)
        for slot in range(444):
            if r.randrange(256)<density:data[slot>>3]|=1<<(slot&7)
        data[55]|=r.randrange(16)<<4;next_slot=r.randrange(444)
        if r.randrange(2):data[next_slot>>3]&=~(1<<(next_slot&7))
        cases.append((next_slot,bytes(data)))
    return cases


C_REFERENCE='''uint16_t allocator_reference(uint16_t next,uint8_t *bits){
 uint16_t slot=next,n;uint8_t mask;
 for(n=0;n<444;++n){mask=(uint8_t)(1u<<(slot&7));if(bits[slot>>3]&mask){bits[slot>>3]&=(uint8_t)~mask;return slot;}if(++slot==444)slot=0;}
 return 65535u;}
'''


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assembly',type=Path,default=BASE/'src/world_alloc_fast.s');p.add_argument('--out',type=Path,default=BASE/'build/world-alloc-check');p.add_argument('--lcc',type=Path,default=BASE/'.toolchain/gbdk/bin/lcc');a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    sha=hashlib.sha256(a.assembly.read_bytes()).hexdigest();test_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();cases=vectors();expected=[reference(*row)for row in cases]
    (out/'reference.c').write_text('#include <stdint.h>\n'+C_REFERENCE)
    lib=out/('host.dylib'if sys.platform=='darwin'else'host.so');subprocess.run(['cc','-shared','-fPIC','-std=c99',str(out/'reference.c'),'-o',str(lib)],check=True)
    host=C.CDLL(str(lib));host.allocator_reference.argtypes=[C.c_uint16,C.POINTER(C.c_uint8)];host.allocator_reference.restype=C.c_uint16
    for row,want in zip(cases,expected):
        bits=(C.c_uint8*56).from_buffer_copy(row[1]);assert host.allocator_reference(row[0],bits)==want[0]and bytes(bits)==want[1]
    header='#include <stdint.h>\ntypedef struct{uint16_t next,expected;uint8_t bits[56];} allocator_vector_t;\n';sources=[]
    for bank,start in enumerate(range(0,len(cases),256),1):
        rows=cases[start:start+256];name='allocator_vectors_%d'%bank;header+='extern const allocator_vector_t '+name+'[];\nextern const uint8_t allocator_tag_%d[];\n'%bank
        data=[]
        for (next_slot,bits),(selected,_)in zip(rows,expected[start:start+256]):data.append('{%du,%du,{'%(next_slot,selected)+','.join(map(str,bits))+'}}')
        path=out/(name+'.c');path.write_text('#include "vectors.h"\n#pragma bank %d\n'%bank+'const allocator_vector_t '+name+'[]={\n'+',\n'.join(data)+'\n};\nconst uint8_t allocator_tag_%d[]={%d};\n'%(bank,bank));sources.append(path)
    (out/'vectors.h').write_text(header)
    driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "vectors.h"
uint16_t world_find_free(uint16_t next,uint8_t *bits) __sdcccall(0);
volatile uint8_t allocator_done,allocator_phase;
volatile uint16_t allocator_cases,result_failures,mutation_failures,guard_failures,bank_failures,irq_failures;
volatile uint16_t first_bad=65535u,irq_ticks;
uint8_t arena[512],reference_bits[56];
typedef char vector_size[sizeof(allocator_vector_t)==60?1:-1];
'''+C_REFERENCE+'''
static void batch(const volatile allocator_vector_t *v,uint8_t bank,const volatile uint8_t *tag){uint16_t i,j,pos,selected,want;uint8_t pattern;
 for(i=0;i<256;++i){
  pos=16+(allocator_cases*37u)%400u;
  for(j=0;j<512;++j)arena[j]=(uint8_t)(0xa5u^j^allocator_cases);
  for(j=0;j<56;++j)arena[pos+j]=reference_bits[j]=v[i].bits[j];
  want=allocator_reference(v[i].next,reference_bits);
  if(want!=v[i].expected)++result_failures;
  IE_REG=31;IF_REG=4;
  selected=world_find_free(v[i].next,arena+pos);
  if(IE_REG!=31||(IF_REG&31)!=4)++irq_failures;
  if(selected!=want){if(first_bad==65535u)first_bad=allocator_cases;++result_failures;}
  for(j=0;j<56;++j)if(arena[pos+j]!=reference_bits[j])++mutation_failures;
  for(j=0;j<512;++j)if(j<pos||j>=pos+56){pattern=(uint8_t)(0xa5u^j^allocator_cases);if(arena[j]!=pattern)++guard_failures;}
  if(CURRENT_BANK!=bank||*tag!=bank)++bank_failures;
  ++allocator_cases;
 }}
void main(void){uint16_t i,start;disable_interrupts();DISPLAY_OFF;cpu_fast();TAC_REG=0;SC_REG=0;
'''
    for bank in range(1,len(sources)+1):driver+=' SWITCH_ROM(%d);batch(allocator_vectors_%d,%d,allocator_tag_%d);\n'%(bank,bank,bank,bank)
    driver+=''' allocator_phase=1;memset(arena,0,56);arena[55]=240;
 IE_REG=VBL_IFLAG;IF_REG=0;DISPLAY_ON;enable_interrupts();start=sys_time;
 for(i=0;i<512;++i)if(world_find_free(i%444u,arena)!=65535u)++result_failures;
 irq_ticks=sys_time-start;if(!irq_ticks)++irq_failures;
 allocator_done=1;while(1)vsync();}
''';(out/'driver.c').write_text(driver)
    command=[str(a.lcc),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(out),'-o',str(out/'check.gbc'),str(out/'driver.c'),str(a.assembly)]+list(map(str,sources));subprocess.run(command,check=True,capture_output=True,text=True)
    symbols={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9a-fA-F]+)',(out/'check.noi').read_text())}
    emulator=PyBoy(str(out/'check.gbc'),window='null',sound_emulated=False,cgb=True);emulator.set_emulation_speed(0);active=[];returns=set();cycles=[]
    def completed(key):
        if not active or active[-1]['sp']+2!=emulator.register_file.SP or active[-1]['key']!=key:return
        call=active.pop()
        if not call['phase']:cycles.append(emulator._cycles()-call['start'])
    def entered(_):
        sp=emulator.register_file.SP;ret=emulator.memory[sp]+256*emulator.memory[sp+1];key=(0,ret)
        if key not in returns:emulator.hook_register(*key,completed,key);returns.add(key)
        active.append({'sp':sp,'key':key,'start':emulator._cycles(),'phase':emulator.memory[symbols['_allocator_phase']]})
    emulator.hook_register(0,symbols['_world_find_free'],entered,None)
    try:
        for _ in range(2000):
            emulator.tick(100)
            if emulator.memory[symbols['_allocator_done']]:break
        def n(name,size=2):
            address=symbols['_'+name];return int.from_bytes(bytes(emulator.memory[address:address+size]),'little')
        report={name:n(name)for name in('allocator_cases','result_failures','mutation_failures','guard_failures','bank_failures','irq_failures','first_bad','irq_ticks')}
        report.update({'done':n('allocator_done',1),'host_c_matches_python':True,'irq_enabled_calls':512,'source_sha256':sha,'test_sha256':test_sha,'api_cycles':{'calls':len(cycles),'min':min(cycles),'max':max(cycles),'mean':sum(cycles)/len(cycles)}})
        assert hashlib.sha256(a.assembly.read_bytes()).hexdigest()==sha,'Allocator changed during native check'
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
        assert report['done']and report['allocator_cases']==8192 and not any(report[name]for name in('result_failures','mutation_failures','guard_failures','bank_failures','irq_failures')),report
    finally:emulator.stop(save=False)


if __name__=='__main__':main()
