#!/usr/bin/env python3
"""Exact original Q48-table native trig baseline; not a solver/FPS result."""
import argparse,contextlib,hashlib,io,json,random,re,statistics,subprocess
from pathlib import Path
import mesen
from wide_native_trig_check import build,encode
from m7_latch_check import sites

def generate(out,base):
 text=(base/'wide_trig_table.h').read_text();pi=int(re.search(r'WIDE_PI_Q48=(\d+)',text)[1]);q=pi//2
 arrays=[list(map(int,re.search(r'wide_'+name+r'_q48\[\]=\{([^}]+)',text)[1].split(',')))for name in ['sin','cos']]
 source='.include "hdr.asm"\n.include "phys.inc"\n.include "test/wide_native_math.asm"\n'
 for bank in range(9):
  data=b''.join(encode((i*q+4095)//4096,8)+encode(arrays[0][i],8)+encode(arrays[1][i],8)for i in range(bank*512,min(4097,(bank+1)*512)));p=out/('table%d.bin'%bank);p.write_bytes(data);source+='\n.SECTION ".wq_table%d" SUPERFREE\nwq_table%d:\n.incbin "%s"\n.ENDS\n'%(bank,bank,p.resolve())
 native=out/'native.asm';native.write_text(source)
 driver=Path('test/wide_native_q44_trig_driver.c').read_text();driver=driver.replace('static u16 pi[5]={0xb6a3,0x5444,0x243f,3,0};','static u16 pi[5];');init=[]
 for name,value in [('pi',pi),('quarter',q),('period',2*pi)]:
  init.extend('%s[%d]=%d;'%(name,i,(value>>(16*i))&65535)for i in range(5))
 driver=driver.replace('/* WQ_CONSTANTS */',''.join(init));path=out/'q44_driver.c';path.write_text(driver);return native,path

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=Path('build/native-q44-trig'));ap.add_argument('--base',type=Path,default=Path('build/wide-unit-q44-v2'));ap.add_argument('--limit',type=int);ap.add_argument('--inject-latch',action='store_true');ap.add_argument('--negative-control',action='store_true');ap.add_argument('--assembly',action='store_true');ap.add_argument('--all-cells',action='store_true');ap.add_argument('--wrapper',action='store_true');ap.add_argument('--specialized',action='store_true');ap.add_argument('--far-wrapper',action='store_true');ap.add_argument('--control-fast',action='store_true');ap.add_argument('--square-fast',action='store_true');ap.add_argument('--short-products',action='store_true');ap.add_argument('--index-fast',action='store_true');a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True);a.wrapper=a.wrapper or a.far_wrapper;
 if (a.index_fast or a.wrapper or a.control_fast or a.square_fast or a.short_products or a.specialized) and not a.assembly:ap.error('Native options require --assembly')
 if (a.square_fast or a.short_products) and not a.specialized:ap.error('Square/short products require --specialized')
 sources=[Path(__file__),Path('test/wide_native_q44_trig_driver.c'),Path('test/wide_native_q44_trig_asm.py'),Path('test/wide_native_q44_products.py'),Path('test/wide_native_math.asm'),Path('test/wide_arith.inc'),Path('src/core.asm'),a.base/'wide_fixed.h',a.base/'wide_trig_table.h']
 frozen=a.out/'source-frozen';frozen.mkdir(exist_ok=True);frozen_manifest={}
 for src in sources:
  dst=frozen/src.name;dst.write_bytes(src.read_bytes());frozen_manifest[str(src)]={'sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),'snapshot':str(dst)}
 (frozen/'manifest.json').write_text(json.dumps(frozen_manifest,indent=2)+'\n')
 native,driver=generate(a.out,a.base)
 if a.assembly:
  from wide_native_q44_trig_asm import generate as asm_generate
  native,driver=asm_generate(a.out,native,a.specialized,a.control_fast,a.square_fast,a.short_products,a.index_fast)
 try:rom=build(a.out,str(native),str(driver))
 except subprocess.CalledProcessError as e:print(e.stdout,e.stderr);raise
 rng=random.Random(840187);angles=[0,1,-1,-(1<<63),(1<<63)-1,1<<44,-(1<<44),128<<44,-(128<<44)]
 for _ in range(100):angles.extend([rng.randrange(-128<<44,128<<44),rng.randrange(-(1<<63),1<<63)])
 pi=884279719003555
 for k in [-80000,-10,-1,0,1,10,80000]:
  for n in [0,pi//2,pi,3*pi//2,2*pi]:
   raw=(k*2*pi+n)//16
   if -(1<<63)+2<=raw<(1<<63)-2:angles.extend([raw-1,raw,raw+1])

 if a.all_cells:
  angles.extend((((i*(pi//2))//4096)+8)//16 for i in range(4097))
 angles.extend([1<<44,2<<44,1<<44,2<<44,3<<44,1<<44])
 cases=[x for v in angles for x in [v,v]];cases=cases[:a.limit]if a.limit else cases
 cpp=a.out/'reference.cpp';cpp.write_text('#include <iostream>\n#include "wide_fixed.h"\nint main(){int64_t a;while(std::cin>>a){auto x=wide_scalar::from_raw(a);std::cout<<sin(x).raw<<" "<<cos(x).raw<<"\\n";}}');exe=a.out/'reference';subprocess.run(['c++','-std=c++17','-O2','-DWIDE_BITS=44','-I'+str(a.base.resolve()),str(cpp),'-o',str(exe)],check=True);ref=subprocess.run([str(exe)],input=''.join(str(x)+'\n'for x in cases),text=True,capture_output=True,check=True);wants=[tuple(map(int,x.split()))for x in ref.stdout.splitlines()];sym=mesen.read_symbols(str(rom))
 if a.far_wrapper:sym.update({'wq_angle':0x7f0200,'wq_sin':0x7f0220,'wq_cos':0x7f0240})
 lua=['local m=emu.memType.snesMemory;local cases,results,clocks,stages={},{},{},{};local i,waiting,f,t0,dt,hits,mt0,finished=1,false,0,0,0,0,0,false']
 for x in cases:lua.append('cases[#cases+1]=%r'%encode(x,8).hex())
 lua+=['emu.addMemoryCallback(function()t0=emu.getMasterClock()end,emu.callbackType.exec,%d)'%sym['wide_q44_trig_pair'if a.wrapper else'wq_native_pair'if a.assembly else'wide_q44_trig_pair'],'emu.addMemoryCallback(function()dt=emu.getMasterClock()-t0 end,emu.callbackType.exec,%d)'%sym['wide_q44_trig_pair_end'if a.wrapper else'wq_native_pair_end'if a.assembly else'wide_q44_trig_end']]
 if a.assembly:
  for j in range(1,9):
   if 'wqa_mul%d_begin'%j in sym:
    lua+=['emu.addMemoryCallback(function()mt0=emu.getMasterClock()end,emu.callbackType.exec,%d)'%sym['wqa_mul%d_begin'%j],'emu.addMemoryCallback(function()stages[#stages+1]=tostring(%d+4*emu.read16(%d,m)).." "..tostring(emu.getMasterClock()-mt0)end,emu.callbackType.exec,%d)'%(j,sym['wqa_ram']+132,sym['wqa_mul%d_end'%j])]
 if a.inject_latch:
  for address in sites(rom,sym['core_m7_latch']):
   restore=''if a.negative_control else 'emu.write(0x80211f,emu.read(%d,m),m);'%(sym['core_m7_latch']+1)
   lua.append('emu.addMemoryCallback(function()hits=hits+1;emu.write(0x80210d,0x5a,m);emu.write(0x80210d,0xc3,m);emu.write(0x80210e,0x39,m);emu.write(0x80210e,0xa6,m);%s end,emu.callbackType.exec,%d)'%(restore,address))
 lua.append('''local function read(a,n)local s={}for j=0,n-1 do s[#s+1]=string.char(emu.read(a+j,m))end return table.concat(s)end
emu.addEventCallback(function()f=f+1;if f<120 or finished then return end;if waiting then if emu.read16(%(done)d,m)==0 then return end;results[#results+1]=read(%(sin)d,8)..read(%(cos)d,8)..read(%(status)d,2)..read(%(hit)d,2);clocks[#clocks+1]=tostring(dt);i=i+1;waiting=false end;if i>#cases then finished=true;out("DATA","results.bin",table.concat(results));out("DATA","clocks.txt",table.concat(clocks,"\\n"));out("DATA","hits.txt",tostring(hits));out("DATA","stages.txt",table.concat(stages,"\\n"));emu.stop(0);return end;for j=1,16,2 do emu.write(%(angle)d+(j-1)/2,tonumber(cases[i]:sub(j,j+1),16),m)end;emu.write16(%(done)d,0,m);emu.write16(%(go)d,%(command)d,m);waiting=true end,emu.eventType.endFrame)'''%dict({k:sym['wq_'+k]for k in ['done','go','sin','cos','angle','status','hit']},command=3 if a.far_wrapper else 2 if a.wrapper else 1))
 p=a.out/'check.lua';p.write_text('\n'.join(lua));log=io.StringIO();err=io.StringIO()
 try:
  with contextlib.redirect_stdout(log),contextlib.redirect_stderr(err):returned=mesen.run(str(rom),'W%d'%(125+4*len(cases)),str(a.out),lua=str(p),timeout=900)
 finally:
  (a.out/'raw.txt').write_text(log.getvalue());(a.out/'stderr.txt').write_text(err.getvalue())
 data={n:v for k,n,v in returned};raw=data.get('results.bin',b'');clocks=list(map(int,data.get('clocks.txt',b'').split()));fails=[];groups={'miss':[],'hit':[]}
 if len(raw)!=20*len(cases):fails.append({'incomplete':len(raw),'expected':20*len(cases)})
 for i,want in enumerate(wants):
  got=raw[i*20:(i+1)*20];expected=encode(want[0],8)+encode(want[1],8)+b'\0\0';
  if got[:18]!=expected:fails.append({'case':i,'angle':cases[i],'want':expected.hex(),'got':got.hex()})
  if len(got)==20 and i<len(clocks):groups['hit'if int.from_bytes(got[18:],'little')else'miss'].append(clocks[i])
 stage_groups={str(j):[]for j in range(1,9)}
 for line in data.get('stages.txt',b'').splitlines():
  j,c=line.split();stage_groups[j.decode()].append(int(c))
 manifest={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [native,driver]+sorted(a.out.glob('table*.bin'))};(a.out/'source_manifest.json').write_text(json.dumps({'frozen_sources':frozen_manifest,'generated_sources':manifest},indent=2)+'\n')
 report={'index_fast':a.index_fast,'short_products':a.short_products,'square_fast':a.square_fast,'control_fast':a.control_fast,'far_wrapper':a.far_wrapper,'specialized_products':a.specialized,'wrapper':a.wrapper,'implementation':'direct65816 control'if a.assembly else'816C control','original_table_cells':4097,'packed_table_bytes':sum(p.stat().st_size for p in a.out.glob('table*.bin')),'input':'signed64Q44, complete representable domain','output':'signed64Q44','private_dp_bytes':256 if a.specialized else 512 if a.assembly else 256,'cases':len(cases),'differences':len(fails),'failures':fails[:30],'latch_injections':int(data.get('hits.txt',b'0')),'stage_master_clocks':{k:{'median':statistics.median(v),'min':min(v),'max':max(v),'samples':len(v)}for k,v in stage_groups.items()if v},'timings_master_clocks':{k:{'median':statistics.median(v),'max':max(v),'min':min(v)}for k,v in groups.items()if v},'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'scope':'Original ordered Q48-table sin/cos; either generic F48 or proven-domain exact unsigned products. Entry-to-exit timing excludes caller JSL/RTL/setup. Standalone arithmetic/ABI test, not full solver fidelity or FPS.'};(a.out/'check.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return bool(fails)
if __name__=='__main__':raise SystemExit(main())
