#!/usr/bin/env python3
"""Measure native complete-step call costs and observed stack adjustments."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import mesen


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rom-dir',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();folder=args.rom_dir.resolve();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    rom=folder/'wide_step.sfc';symbols=mesen.read_symbols(rom);labels=json.loads((folder/'profile_labels.json').read_text());data=rom.read_bytes()
    def rtl(address):return data[((address>>16)&127)*32768+(address&32767)]==0x6b
    lua=r'''
local m=emu.memType.snesMemory
local active=false
local stack={}
local stats={}
local errors={}
local minsp=65535
local minsite=''
local function peak(site)
 if not active then return end
 local sp=emu.getState()['cpu.sp'];if sp<minsp then minsp=sp;minsite=site end
end
local function enter(name)
 if name=='wp_pc_step' then active=true;stack={} end
 if not active then return end
 peak(name)
 stack[#stack+1]={name=name,start=emu.getMasterClock(),child=0}
end
local function finish()
 active=false
 local rows={};for n,r in pairs(stats) do rows[#rows+1]=string.format('%q:{"calls":%d,"inclusive":%d,"exclusive":%d,"max":%d}',n,r.calls,r.inclusive,r.exclusive,r.max) end
 local err={};for i=1,math.min(#errors,20) do err[#err+1]=string.format('%q',errors[i]) end
 out('PROFILE','profile.json','{"minimum_observed_sp":'..minsp..',"minimum_site":'..string.format('%q',minsite)..',"stack_mismatch_count":'..#errors..',"errors":['..table.concat(err,',')..'],"remaining_depth":'..#stack..',"functions":{'..table.concat(rows,',')..'}}')
end
local function leave(name)
 if not active then return end
 local top=stack[#stack]
 -- All three raw arithmetic APIs branch to the same register-restoring RTL.
 if name=='wide_mul64' and top and (top.name=='wide_div64' or top.name=='wide_sqrt64') then name=top.name end
 if not top or top.name~=name then errors[#errors+1]=name..' expected '..(top and top.name or 'empty');return end
 local elapsed=emu.getMasterClock()-top.start
 stack[#stack]=nil
 local row=stats[name] or {calls=0,inclusive=0,exclusive=0,max=0}
 stats[name]=row;row.calls=row.calls+1;row.inclusive=row.inclusive+elapsed;row.exclusive=row.exclusive+elapsed-top.child;row.max=math.max(row.max,elapsed)
 if #stack>0 then stack[#stack].child=stack[#stack].child+elapsed end
 if name=='wp_pc_step' then
  finish()
 end
end
'''
    short=lambda name:name.split('.s_')[-1]if name.startswith('tccs_')else name
    for name in labels['entries']:
        if name not in symbols:continue # WLA removes unreachable functions.
        lua+='emu.addMemoryCallback(function() enter('+json.dumps(short(name))+') end,emu.callbackType.exec,%d,%d)\n'%(symbols[name],symbols[name])
    for name,function in labels['exits'].items():
        if name not in symbols:continue
        if not rtl(symbols[name]):continue
        lua+='emu.addMemoryCallback(function() leave('+json.dumps(short(function))+') end,emu.callbackType.exec,%d,%d)\n'%(symbols[name],symbols[name])
    for name in labels['stack_changes']:
        if name not in symbols:continue
        lua+='emu.addMemoryCallback(function() peak('+json.dumps(name)+') end,emu.callbackType.exec,%d,%d)\n'%(symbols[name],symbols[name])
    lua+='''local frame=0;local phase=0
emu.addEventCallback(function()
 frame=frame+1;if frame<120 then return end
 if phase==0 then emu.write16(%(go)d,1,m);phase=1;return end
 if emu.read16(%(done)d,m)==0 then return end
 if phase==1 then emu.write16(%(done)d,0,m);emu.write16(%(input)d,1,m);emu.write16(%(go)d,2,m);phase=2;return end
 if phase==2 then if active then finish() end;dump('STATE','state.bin',m,%(state)d,240);dump('META','meta.bin',m,%(meta)d,14);dump('TIME','time.bin',m,%(time)d,8);dump('OBJECTS','objects.bin',m,%(objects)d,52);dump('EVENTS','events.bin',m,%(events)d,2);phase=3;emu.stop(0) end
end,emu.eventType.endFrame)
'''%{k:symbols[v]for k,v in {'go':'wide_step_go','done':'wide_step_done','input':'wide_step_input','state':'wide_step_state','meta':'wide_step_meta','time':'wide_step_time','objects':'wide_step_objects','events':'wide_step_events'}.items()}
    (out/'profile.lua').write_text(lua);log=io.StringIO()
    with contextlib.redirect_stdout(log):mesen.run(str(rom),'W2000',str(out),lua=str(out/'profile.lua'),timeout=600)
    (out/'raw.txt').write_text(log.getvalue());report=json.loads((out/'profile.json').read_text())
    report['timing_scope']='Entry through pre-RTL; return instruction is charged to caller. Exclusive includes library calls not instrumented. Stack sampling covers all annotated C/ASM pushes/adjustments plus entries; library internal pushes are not annotated.'
    (out/'profile.json').write_text(json.dumps(report,indent=2)+'\n')
    print('minimum SP',report['minimum_observed_sp'],'stack mismatches',report['stack_mismatch_count'])
    for name,row in sorted(report['functions'].items(),key=lambda x:x[1]['exclusive'],reverse=True)[:15]:print(name,row)
    return bool(report['stack_mismatch_count'])


if __name__=='__main__':raise SystemExit(main())
