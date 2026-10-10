#!/usr/bin/env python3
"""Exercise exact fast scalar assembly through real compiled struct callers."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import random
import shutil
import struct

import mesen
from wide_fast_scalar_gen import FUNCTIONS,generate
from wide_level_banks_check import ROOT,run

DRIVER=r'''
#include <snes.h>
#include "core.h"
#define WIDE_PORT_BRIDGE
#include "wide_port.h"
volatile u16 scalar_go,scalar_done,scalar_operation,wp_native_error;
wp_scalar scalar_inputs[4];
struct {u16 before[2];wp_vec value;u16 after[2];} scalar_buffer;
void scalar_call(void){
    wp_vec a,b;
    a.x=scalar_inputs[0];a.y=scalar_inputs[1];
    b.x=scalar_inputs[2];b.y=scalar_inputs[3];
    switch(scalar_operation){
    case 0:scalar_buffer.value.x=wp_add(a.x,a.y);break;
    case 1:scalar_buffer.value.x=wp_sub(a.x,a.y);break;
    case 2:scalar_buffer.value.x=wp_neg(a.x);break;
    case 3:scalar_buffer.value.x=wp_fabs(a.x);break;
    case 4:scalar_buffer.value.x=wp_floor(a.x);break;
    case 5:scalar_buffer.value.x=wp_int((int)a.x.word[0]);break;
    case 6:scalar_buffer.value.x.word[0]=wp_to_int(a.x);break;
    case 7:scalar_buffer.value.x.word[0]=wp_eq(a.x,a.y);break;
    case 8:scalar_buffer.value.x.word[0]=wp_ne(a.x,a.y);break;
    case 9:scalar_buffer.value.x.word[0]=wp_lt(a.x,a.y);break;
    case 10:scalar_buffer.value.x.word[0]=wp_gt(a.x,a.y);break;
    case 11:scalar_buffer.value.x.word[0]=wp_le(a.x,a.y);break;
    case 12:scalar_buffer.value.x.word[0]=wp_ge(a.x,a.y);break;
    case 13:scalar_buffer.value=wp_vec_make(a.x,a.y);break;
    case 14:scalar_buffer.value=wp_add_v(a,b);break;
    case 15:scalar_buffer.value=wp_sub_v(a,b);break;
    case 16:scalar_buffer.value=wp_forgatas90fokkal(a);break;
    }
}
int main(void){consoleInit();core_init();core_screen_off();scalar_go=scalar_done=wp_native_error=0;
 while(1){if(scalar_go){scalar_go=0;scalar_done=0;scalar_call();scalar_done=1;}}return 0;}
'''


def vectors(bits):
    rng=random.Random(114488);lo=-(1<<63);hi=(1<<63)-1;scale=1<<bits
    edges=[lo,lo+1,hi,hi-1,0,1,-1,scale,-scale,scale-1,-scale-1,
           65535,-65536,(1<<32)-1,-(1<<32),32767,-32768]
    rows=[]
    for op in range(len(FUNCTIONS)):
        candidates=[(a,b,a,b) for a in edges for b in edges]
        candidates += [tuple(rng.randrange(lo,hi+1) for _ in range(4)) for _ in range(200)]
        for a,b,c,d in candidates:
            if op==0:values=[a+b]
            elif op==1:values=[a-b]
            elif op==2:values=[-a]
            elif op==3:values=[abs(a)]
            elif op==4:values=[(a>>bits)<<bits]
            elif op==5:values=[(((a&65535)^32768)-32768)*scale]
            elif op==6:values=[(abs(a)//scale)*(-1 if a<0 else 1)]
            elif op==7:values=[int(a==b)]
            elif op==8:values=[int(a!=b)]
            elif op==9:values=[int(a<b)]
            elif op==10:values=[int(a>b)]
            elif op==11:values=[int(a<=b)]
            elif op==12:values=[int(a>=b)]
            elif op==13:values=[a,b]
            elif op==14:values=[a+c,b+d]
            elif op==15:values=[a-c,b-d]
            else:values=[-b,a]
            if any(v<lo or v>hi for v in values):continue
            result=bytearray(b'\x5a'*16)
            if 6<=op<=12:result[:2]=struct.pack('<H',values[0]&65535)
            else:
                for i,value in enumerate(values):result[8*i:8*i+8]=struct.pack('<q',value)
            rows.append({'op':op,'input':struct.pack('<4q',a,b,c,d).hex(),'output':result.hex()})
    return rows


def overflow_check(rom,out):
    symbols=mesen.read_symbols(str(rom));lo=-(1<<63);hi=(1<<63)-1
    cases=[(0,[hi,1,0,0]),(0,[lo,-1,0,0]),(1,[hi,-1,0,0]),(1,[lo,1,0,0]),
           (2,[lo,0,0,0]),(3,[lo,0,0,0]),(14,[0,hi,0,1]),
           (15,[lo,0,1,0]),(16,[0,lo,0,0])]
    result=[];out.mkdir(parents=True,exist_ok=True)
    for index,(op,values) in enumerate(cases):
        folder=out/str(index);folder.mkdir()
        raw=struct.pack('<4q',*values).hex()
        lua='''
local m=emu.memType.snesMemory
local ticks=0
emu.addEventCallback(function()
 ticks=ticks+1
 if ticks==60 then
  local address=INPUT
  for byte in ("RAW"):gmatch("..") do emu.write(address,tonumber(byte,16),m) address=address+1 end
  emu.write16(OPERATION,OPCODE,m) emu.write16(GO,1,m)
 end
end,emu.eventType.endFrame)
'''
        for token,value in [('INPUT',symbols['scalar_inputs']),('RAW',raw),('OPERATION',symbols['scalar_operation']),('OPCODE',op),('GO',symbols['scalar_go'])]:
            lua=lua.replace(token,str(value))
        script=folder/'check.lua';script.write_text(lua);log=io.StringIO()
        with contextlib.redirect_stdout(log):
            rows=mesen.run(str(rom),'W90 PEEK:wp_native_error:2 PEEK:scalar_done:2',str(folder),lua=str(script))
        (folder/'raw.txt').write_text(log.getvalue());actual={name:data for kind,name,data in rows if kind=='PEEK'}
        assert actual=={'wp_native_error':b'\x01\x00','scalar_done':b'\x00\x00'},'Overflow did not trap'
        result.append({'operation':FUNCTIONS[op],'inputs':values,'trapped':True})
    report={'cases':len(result),'failures':0,'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),
            'scope':'Signed64 overflow sets native error and does not return, as the native C facade', 'runs':result}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',type=Path,default=Path('build/wide-native-port-q44-v2'))
    ap.add_argument('--bits',type=int,choices=(40,44),default=44)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--timing-sample',type=int,help='Use this many evenly spaced cases per operation for timing only')
    ap.add_argument('--overflow-rom',type=Path,help='Check signed-overflow traps in an existing scalar ROM instead of building')
    a=ap.parse_args();out=a.out.resolve()
    if out.exists():raise ValueError('Use a fresh output directory')
    if a.overflow_rom:
        overflow_check(a.overflow_rom.resolve(),out);return
    out.mkdir(parents=True);shutil.copy2(a.port/'wide_port.h',out/'wide_port.h')
    header=out/'wide_port.h'
    if 'wp_fabs(' not in header.read_text():header.write_text(header.read_text()+'\nwp_scalar wp_fabs(wp_scalar);\n')
    (out/'driver.c').write_text(DRIVER)
    (out/'scalar.asm').write_text('.include "hdr.asm"\n.BASE $80\n'+generate(a.bits))
    dev=Path.home()/'.local/share/elma-snes/pvsneslib-4.6.0/pvsneslib/devkitsnes';bins=dev/'bin'
    lib=dev.parent/'pvsneslib/lib/LoROM_FastROM'
    commands=[
        [str(bins/'816-tcc'),'-Wall','-F','-DWIDE_TARGET_SNES=1','-Isrc','-I'+str(out),'-I'+str(dev/'include'),'-I'+str(dev.parent/'pvsneslib/include'),'-c',str(out/'driver.c'),'-o',str(out/'driver.ps')],
        [str(dev/'tools/816-opt'),'-i',str(out/'driver.ps'),'-o',str(out/'driver.s')],
        [str(bins/'wla-65816'),'-d','-s','-x','-Ibuild/gen','-Isrc','-o',str(out/'driver.obj'),str(out/'driver.s')],
        [str(bins/'wla-65816'),'-h','-s','-x','-Ibuild/gen','-Isrc','-o',str(out/'scalar.obj'),str(out/'scalar.asm')]]
    objects=[out/'driver.obj',out/'scalar.obj',ROOT/'build/obj/core.obj',*sorted(lib.glob('*.obj'))]
    link=out/'scalar.sfc.link';link.write_text('[objects]\n'+'\n'.join(map(str,objects))+'\n')
    rom=out/'scalar.sfc';commands.append([str(bins/'wlalink'),'-d','-s','-A','-c','-L',str(lib),str(link),str(rom)])
    for i,command in enumerate(commands):run(command,out/('build-%d.log'%i))
    symbols=mesen.read_symbols(str(rom));cases=vectors(a.bits)
    if a.timing_sample:
        selected=[]
        for op in range(len(FUNCTIONS)):
            group=[c for c in cases if c['op']==op]
            selected += [group[i*len(group)//a.timing_sample] for i in range(a.timing_sample)]
        cases=selected
    lua='''
local m=emu.memType.snesMemory
local cases={CASES}
local index,phase,test_frame,bad,started,elapsed=1,0,0,0,0,0
local times,kernel_times={},{}
local kernel_started,kernel_elapsed=nil,0
KERNEL_CALLBACKS
local function put(addr,hex) for byte in hex:gmatch("..") do emu.write(addr,tonumber(byte,16),m) addr=addr+1 end end
local function get(addr,n) local t={} for i=0,n-1 do t[#t+1]=string.format("%02x",emu.read(addr+i,m)) end return table.concat(t) end
emu.addMemoryCallback(function() started=emu.getMasterClock() end,emu.callbackType.exec,CALL,CALL)
emu.addMemoryCallback(function(addr,value) if value==1 then elapsed=emu.getMasterClock()-started end end,emu.callbackType.write,DONE,DONE)
emu.addEventCallback(function()
 test_frame=test_frame+1 if test_frame<60 then return end
 local c=cases[index]
 if not c then
  local fields={string.format('"cases":%d,"failures":%d',index-1,bad)}
  for op,t in pairs(times) do table.sort(t) fields[#fields+1]=string.format('"op%d":{"count":%d,"median":%d,"max":%d}',op,#t,t[math.floor((#t+1)/2)],t[#t]) end
  for op,t in pairs(kernel_times) do table.sort(t) fields[#fields+1]=string.format('"kernel%d":{"count":%d,"median":%d,"max":%d}',op,#t,t[math.floor((#t+1)/2)],t[#t]) end
  out("SCALAR","native-results.json","{"..table.concat(fields,",").."}") emu.stop(0) return
 end
 if phase==0 then
  put(INPUT,c[2]) put(BUFFER,"3cc35aa5"..string.rep("5a",16).."a55ac33c")
  emu.write16(OP,c[1],m) emu.write16(DONE,0,m) emu.write16(GO,1,m) phase=1
 elseif emu.read16(DONE,m)~=0 then
  local actual=get(BUFFER,24)
  if actual~="3cc35aa5"..c[3].."a55ac33c" or get(INPUT,32)~=c[2] or emu.read16(ERROR,m)~=0 then
   bad=bad+1 if bad<12 then print("SCALARFAIL "..index.." "..c[1].." "..actual.." expected "..c[3]) end
  end
  local t=times[c[1]] or {} times[c[1]]=t t[#t+1]=elapsed
  local k=kernel_times[c[1]] or {} kernel_times[c[1]]=k k[#k+1]=kernel_elapsed
  index=index+1 phase=0
 end
end,emu.eventType.endFrame)
'''.replace('CASES',','.join('{%d,"%s","%s"}'%(c['op'],c['input'],c['output']) for c in cases))
    callbacks=[]
    for name in FUNCTIONS:
        callbacks.append('emu.addMemoryCallback(function() if not kernel_started then kernel_started=emu.getMasterClock() end end,emu.callbackType.exec,%d,%d)'%(symbols[name],symbols[name]))
    for name,address in symbols.items():
        if name.startswith('wide_fast_scalar_return_'):
            callbacks.append('emu.addMemoryCallback(function() if kernel_started then kernel_elapsed=emu.getMasterClock()-kernel_started kernel_started=nil end end,emu.callbackType.exec,%d,%d)'%(address,address))
    lua=lua.replace('KERNEL_CALLBACKS','\n'.join(callbacks))
    for token,label in [('INPUT','scalar_inputs'),('BUFFER','scalar_buffer'),('DONE','scalar_done'),
                        ('OP','scalar_operation'),('GO','scalar_go'),('ERROR','wp_native_error'),('CALL','scalar_call')]:
        lua=lua.replace(token,str(symbols[label]))
    script=out/'check.lua';script.write_text(lua);log=io.StringIO()
    with contextlib.redirect_stdout(log):rows=mesen.run(str(rom),'W'+str(2*len(cases)+1000),str(out),lua=str(script))
    (out/'raw.txt').write_text(log.getvalue())
    reports=[json.loads(data) for kind,name,data in rows if kind=='SCALAR']
    if len(reports)!=1:raise RuntimeError('Native scalar run did not complete; inspect raw.txt')
    result=reports[0]
    result.update(bits=a.bits,functions=FUNCTIONS,rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),
                  source_sha256=hashlib.sha256((out/'scalar.asm').read_bytes()).hexdigest(),
                  scope='Compiled C struct caller, scalar/vector output, input preservation and surrounding canaries; overflow excluded',
                  clock_scope='Entire compiled switch/call/copy wrapper, including vector input staging and done write')
    result['kernel_clock_scope']='Measured entry up to the RTL instruction; caller copying, JSL and RTL excluded'
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result));assert result['cases']==len(cases) and result['failures']==0


if __name__=='__main__':main()
