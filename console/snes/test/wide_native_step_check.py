#!/usr/bin/env python3
"""Compare full experimental native steps and stack-lowering opcode canaries."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import re
import statistics
import struct
import subprocess
import mesen


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rom-dir',type=Path,required=True)
    ap.add_argument('--host-port',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--script',default='G16')
    ap.add_argument('--timeout',type=int,default=1800,help='Mesen runner and subprocess wall-time limit')
    args=ap.parse_args();folder=args.rom_dir.resolve();host=args.host_port.resolve();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    inputs=[]
    for keys,count in re.findall(r'([NGBRL]+)(\d+)',args.script):
        mask=sum(value for key,value in [('G',1),('B',2),('R',4),('L',8)]if key in keys);inputs.extend([mask]*int(count))
    if not inputs:raise ValueError('Empty script')
    source=(folder/'wide_native_step_driver.c').read_text().split('int main(void)')[0]
    source=source.replace('#include <snes.h>','#include <stdint.h>\n#include <stdio.h>\n#include <stdlib.h>\ntypedef uint16_t u16;').replace('#include "core.h"','').replace('extern const unsigned char wide_native_level00[];','')
    raw=json.loads((folder/'native_rom.json').read_text())['dt_raw']
    source+='''static void word(unsigned v){printf("%02x%02x",v&255,(v>>8)&255);}
static void show(void){unsigned i;snapshot();for(i=0;i<120;++i)word(wide_step_state[i]);for(i=0;i<7;++i)word(wide_step_meta[i]);for(i=0;i<4;++i)word(wide_step_time[i]);for(i=0;i<52;++i)printf("%02x",wide_step_objects[i]);word(wide_step_events);printf("\\n");}
int main(int argc,char**argv){unsigned char blob[2794];unsigned i;FILE*f=fopen(argv[1],"rb");if(!f||fread(blob,1,sizeof(blob),f)!=sizeof(blob))return 2;fclose(f);
'''+''.join('dt.word['+str(i)+']='+str((raw>>(16*i))&65535)+';'for i in range(4))+'''
if(!wp_load_level(blob))return 3;show();for(i=0;argv[2][i];++i){char c=argv[2][i];wide_step_events=wp_pc_step(c<='9'?c-'0':c-'a'+10,dt);show();if(wide_step_events&3)break;}return 0;}
'''
    (out/'oracle.c').write_text(source)
    names=['wide_controller','wide_level_loader','wide_port_native_math','native_host_shim']+['wp_native_'+k+'_'+str(i)for k in ('sin','cos')for i in range(8)]
    command=['cc','-O2','-DWIDE_TARGET_SNES=1','-I'+str(folder),'-o',str(out/'oracle'),str(out/'oracle.c')]+[str(host/(n+'.o'))for n in names]
    subprocess.run(command,check=True)
    result=subprocess.run([str(out/'oracle'),str(folder/'lev00.bin'),''.join(format(n,'x')for n in inputs)],capture_output=True,text=True,check=True)
    (out/'oracle.txt').write_text(result.stdout);expected=result.stdout.splitlines();inputs=inputs[:len(expected)-1]
    s=mesen.read_symbols(folder/'wide_step.sfc')
    lua='''local m=emu.memType.snesMemory
local inputs={%s}
local phase=0
local index=0
local frame=0
local start=0
local times={}
local minsp=65535
local stop=false
local function peak() local sp=emu.getState()['cpu.sp'];if sp<minsp then minsp=sp end end
local function state()
 local t={}
 local function bytes(a,n) for i=0,n-1 do t[#t+1]=string.char(emu.read(a+i,m)) end end
 bytes(%d,240);bytes(%d,14);bytes(%d,8);bytes(%d,52);bytes(%d,2)
 dump('PEEK','error'..index,m,%d,2)
 out('STATE','state'..index..'.bin',table.concat(t))
end
'''%(','.join(map(str,inputs)),s['wide_step_state'],s['wide_step_meta'],s['wide_step_time'],s['wide_step_objects'],s['wide_step_events'],s['wp_native_error'])
    # Entry sampling observes nested C and raw arithmetic frames. The report
    # explicitly distinguishes this from an every-instruction stack proof.
    for name,address in s.items():
        if name.startswith('wp_') or name in ('wide_mul64','wide_div64','wide_sqrt64'):
            lua+='emu.addMemoryCallback(peak,emu.callbackType.exec,%d,%d)\n'%(address,address)
    lua+='''emu.addEventCallback(function()
 frame=frame+1;if frame<120 or stop then return end
 if phase==0 then emu.write16(%(done)d,0,m);emu.write16(%(go)d,1,m);phase=1;return end
 if emu.read16(%(error)d,m)~=0 then out('FAIL','domain.txt',tostring(index));stop=true;emu.stop();return end
 if emu.read16(%(done)d,m)==0 then return end
 if phase==1 then state();emu.write16(%(done)d,0,m);emu.write16(%(go)d,4,m);phase=2;return end
 if phase==2 then dump('PROOF','stack.bin',m,%(proof)d,384);phase=3 end
 if phase==4 then times[#times+1]=emu.getMasterClock()-start;state();phase=3 end
 if index>=#inputs then out('TIMES','clocks.txt',table.concat(times,'\\n'));out('STACK','stack-sample.json','{"entry_sample_min_sp":'..minsp..'}');stop=true;emu.stop(0);return end
 index=index+1;emu.write16(%(done)d,0,m);emu.write16(%(input)d,inputs[index],m);emu.write16(%(go)d,2,m);start=emu.getMasterClock();phase=4
end,emu.eventType.endFrame)
'''%{k:s[v]for k,v in {'go':'wide_step_go','done':'wide_step_done','error':'wp_native_error','input':'wide_step_input','proof':'wide_stack_proof_results'}.items()}
    (out/'check.lua').write_text(lua);log=io.StringIO()
    try:
        with contextlib.redirect_stdout(log):results=mesen.run(str(folder/'wide_step.sfc'),'W'+str(2000+len(inputs)*400),str(out),lua=str(out/'check.lua'),timeout=args.timeout+30)
    finally:(out/'raw.txt').write_text(log.getvalue())
    (out/'raw.txt').write_text(log.getvalue());got={name:data for _,name,data in results};fail=[]
    for i,want in enumerate(expected):
        if got.get('state'+str(i)+'.bin')!=bytes.fromhex(want):fail.append('state'+str(i)+' differs')
    proof=got.get('stack.bin',b'');cases=json.loads((folder/'stack_cases.json').read_text())
    for i,case in enumerate(cases):
        if len(proof)<12*(i+1):fail.append('Missing opcode case '+str(i));continue
        a,x,p,before,value,after=struct.unpack_from('<6H',proof,12*i)
        flags=case['flags']
        if case['op']=='lda':flags=(flags&~0x82)|(0x80 if case['a']&0x8000 else 0)|(2 if case['a']==0 else 0)
        if (a,x,p,before,value,after)!=(case['a'],0x4321,flags,0xcafe,case['a'],0xbeef):fail.append('Opcode case'+str(i)+': '+str((a,x,p,before,value,after)))
    clocks=[int(v)for v in got.get('clocks.txt',b'').decode().split()]
    report={'script':args.script,'native_steps':len(inputs),'exact_complete_states':len(expected)-sum(x.startswith('state')for x in fail),
            'opcode_cases':len(cases),'failures':fail,'median_master_clocks':statistics.median(clocks)if clocks else None,'max_master_clocks':max(clocks)if clocks else None,
            'stack_entry_sampling':json.loads(got.get('stack-sample.json',b'{}')),
            'scope':'Complete raw state including brake/volt history, object activity and events; sampling covers function entries, not all stack writes. Generic backend is not60FPS.'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return bool(fail)


if __name__=='__main__':raise SystemExit(main())
