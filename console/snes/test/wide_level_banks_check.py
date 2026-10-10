#!/usr/bin/env python3
"""Link and read every banked level byte through native816-C far pointers."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess

import mesen

ROOT=Path(__file__).resolve().parent.parent

DRIVER=r'''
#include <snes.h>
#include "core.h"
extern const unsigned char* const wide_level_catalog[];
volatile u16 banks_go,banks_done,banks_index,banks_size,banks_hash;
int main(void){
    const unsigned char* p;u16 i,h;
    consoleInit();core_init();core_screen_off();banks_go=0;banks_done=0;
    while(1){if(banks_go){
        banks_go=0;banks_done=0;p=wide_level_catalog[banks_index];h=0;
        for(i=0;i<banks_size;++i){h=(h<<1)|(h>>15);h^=*p++;}
        banks_hash=h;banks_done=1;
    }}return 0;
}
'''


def run(command,path):
    result=subprocess.run(command,capture_output=True,text=True)
    path.write_text(result.stdout+result.stderr);result.check_returncode()


def checksum(data):
    value=0
    for byte in data:value=(((value<<1)|(value>>15))^byte)&65535
    return value


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--banks',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();banks=a.banks.resolve();out=a.out.resolve()
    if out.exists():raise ValueError('Use a fresh output directory')
    out.mkdir(parents=True);report=json.loads((banks/'report.json').read_text())
    dev=Path.home()/'.local/share/elma-snes/pvsneslib-4.6.0/pvsneslib/devkitsnes'
    bins=dev/'bin';lib=dev.parent/'pvsneslib/lib/LoROM_FastROM'
    (out/'driver.c').write_text(DRIVER)
    commands=[
        [str(bins/'816-tcc'),'-Wall','-F','-Isrc','-I'+str(dev/'include'),'-I'+str(dev.parent/'pvsneslib/include'),'-c',str(out/'driver.c'),'-o',str(out/'driver.ps')],
        [str(dev/'tools/816-opt'),'-i',str(out/'driver.ps'),'-o',str(out/'driver.s')],
        [str(bins/'wla-65816'),'-d','-s','-x','-Ibuild/gen','-Isrc','-o',str(out/'driver.obj'),str(out/'driver.s')],
        [str(bins/'wla-65816'),'-h','-s','-x','-Ibuild/gen','-Isrc','-o',str(out/'banks.obj'),str(banks/'wide_level_banks.asm')]]
    objects=[out/'driver.obj',out/'banks.obj',ROOT/'build/obj/core.obj',*sorted(lib.glob('*.obj'))]
    link=out/'banks.sfc.link';link.write_text('[objects]\n'+'\n'.join(map(str,objects))+'\n')
    commands.append([str(bins/'wlalink'),'-d','-s','-A','-c','-L',str(lib),str(link),str(out/'banks.sfc')])
    for i,command in enumerate(commands):run(command,out/('build-%d.log'%i))
    rom=out/'banks.sfc';symbols=mesen.read_symbols(str(rom));image=rom.read_bytes()
    def romoffset(address):return ((address>>16)&127)*32768+(address&32767)
    table=romoffset(symbols['wide_level_catalog']);cases=[]
    for entry in report['entries']:
        for part,(label,size,digest) in enumerate(zip(entry['labels'],entry['section_bytes'],entry['section_sha256'])):
            index=len(cases);address=symbols[label]
            assert address&0x8000 and (address&65535)+size<=65536, 'Section crosses LoROM bank'
            assert struct.unpack_from('<I',image,table+4*index)[0]==address, 'Invalid native far pointer'
            start=romoffset(address);data=image[start:start+size]
            assert hashlib.sha256(data).hexdigest()==digest, 'ROM bytes differ from exact source'
            cases.append({'index':index,'level':entry['level'],'part':part,'address':address,
                          'size':size,'checksum':checksum(data)})
    lua='''
local m=emu.memType.snesMemory
local cases={CASES}
local index,phase,test_frame,bad=1,0,0,0
emu.addEventCallback(function()
 test_frame=test_frame+1 if test_frame<60 then return end
 local c=cases[index]
 if not c then
  out("BANKS","native-results.json",string.format('{"cases":%d,"failures":%d}',index-1,bad))
  emu.stop(0) return
 end
 if phase==0 then
  emu.write16(INDEX,c[1],m) emu.write16(SIZE,c[2],m)
  emu.write16(DONE,0,m) emu.write16(GO,1,m) phase=1
 elseif emu.read16(DONE,m)~=0 then
  local actual=emu.read16(HASH,m)
  if actual~=c[3] then bad=bad+1 print("BANKFAIL "..c[1].." "..actual.." "..c[3]) end
  index=index+1 phase=0
 end
end,emu.eventType.endFrame)
'''.replace('CASES',','.join('{%d,%d,%d}'%(c['index'],c['size'],c['checksum']) for c in cases))
    for token,label in [('INDEX','banks_index'),('SIZE','banks_size'),('DONE','banks_done'),('GO','banks_go'),('HASH','banks_hash')]:
        lua=lua.replace(token,str(symbols[label]))
    script=out/'check.lua';script.write_text(lua);log=io.StringIO()
    with contextlib.redirect_stdout(log):rows=mesen.run(str(rom),'W10000',str(out),lua=str(script))
    (out/'raw.txt').write_text(log.getvalue())
    native=[json.loads(data) for kind,name,data in rows if kind=='BANKS']
    assert len(native)==1 and native[0]=={'cases':len(cases),'failures':0}, 'Native section reads failed or timed out'
    result={'exact_rom_payloads':True,'native_pointer_reads':native[0],
            'payload_bytes':sum(c['size'] for c in cases),'rom_sha256':hashlib.sha256(image).hexdigest(),
            'scope':'All54 levels placed and read through compiled native far pointers; solver speed not tested',
            'commands':commands,'sections':cases}
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('commands','sections')}))


if __name__=='__main__':main()
