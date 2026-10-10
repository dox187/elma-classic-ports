#!/usr/bin/env python3
"""Native first-quadrant LUT/Horner arithmetic; no full solver/FPS claim."""
import argparse,contextlib,hashlib,io,json,random,statistics
from pathlib import Path
import mesen
from m7_latch_check import sites
from wide_native_trig_check import build,encode

def rounded(n,d):
 return (1 if n>=0 else -1)*((abs(n)+d//2)//d)
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--table-build',type=Path,default=Path('build/wide-unit-native-trig-u24-q40'));ap.add_argument('--out',type=Path,default=Path('build/native-horner'));ap.add_argument('--case-limit',type=int);ap.add_argument('--inject-latch',action='store_true');ap.add_argument('--negative-control',action='store_true');a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 text=(a.table_build/'wide_trig_table.h').read_text();rows=[json.loads(line.strip().rstrip(',').replace('{','[').replace('}',']')) for line in text.splitlines() if line.startswith('{{')]
 asm=Path('test/wide_native_horner.asm').read_text()
 for fi,name in enumerate(['sin','cos']):
  blob=b''.join(b''.join(encode(abs(c),n) for c,n in zip(row[fi],[7,5,4,3])) for row in rows);path=a.out/(name+'.bin');path.write_bytes(blob);asm+='\n.SECTION ".wnt_'+name+'_table" SUPERFREE\nwnt_'+name+':\n.incbin "'+str(path.resolve())+'"\n.ENDS\n'
 source=a.out/'pair.asm';source.write_text(asm);rom=build(a.out,str(source),'test/wide_native_horner_driver.c');syms=mesen.read_symbols(str(rom));rng=random.Random(840187);cases=[]
 import re
 pi=int(re.search(r'WIDE_PI_Q48=(\d+)',text)[1]);last_u=rounded((pi//2-(len(rows)-1)*(1<<38)),1<<14)
 for index in range(len(rows)):
  umax=last_u if index==len(rows)-1 else (1<<24)-1
  for u in sorted(set([0,1,min(umax,1<<23),max(0,umax-1),umax,rng.randrange(umax+1)])):cases.append((index,u))
 if a.case_limit:cases=cases[:a.case_limit]
 for name in ['wide_native_horner_check.py','wide_native_horner.asm','wide_native_horner_driver.c']:(a.out/name).write_bytes((Path('test')/name).read_bytes())
 lua=['local memory=emu.memType.snesMemory\nlocal tests,results,clocks={},{},{}\nlocal i,waiting,frame,t0,dt,finished,hits=1,false,0,0,0,false,0\nlocal function read(a,n)local s={}for j=0,n-1 do s[#s+1]=string.char(emu.read(a+j,memory))end return table.concat(s)end']
 for index,u in cases:lua.append('tests[#tests+1]={%d,%d}'%(index,u))
 lua+=['emu.addMemoryCallback(function()t0=emu.getMasterClock()end,emu.callbackType.exec,%d)'%syms['wnt_pair'],'emu.addMemoryCallback(function()dt=emu.getMasterClock()-t0 end,emu.callbackType.exec,%d)'%syms['wnt_pair_end']]
 if a.inject_latch:
  for address in sites(rom,syms['core_m7_latch']):
   if syms['wnt_pair']<=address<=syms['wnt_pair_end']:
    restore='' if a.negative_control else 'emu.write(0x80211f,emu.read(%d,memory),memory)'%(syms['core_m7_latch']+1)
    lua.append('emu.addMemoryCallback(function()hits=hits+1;emu.write(0x80210d,0x5a,memory);emu.write(0x80210d,0xc3,memory);emu.write(0x80210e,0x39,memory);emu.write(0x80210e,0xa6,memory);%s end,emu.callbackType.exec,%d)'%(restore,address))
 lua.append('''emu.addEventCallback(function()frame=frame+1;if frame<120 or finished then return end
if waiting then if emu.read16(%(done)d,memory)==0 then return end;results[#results+1]=read(%(ram)d+80,6)..read(%(ram)d+88,6);clocks[#clocks+1]=tostring(dt);i=i+1;waiting=false end
if i>#tests then finished=true;out("DATA","hits.txt",tostring(hits));out("DATA","results.bin",table.concat(results));out("DATA","clocks.txt",table.concat(clocks,"\\n"));return end
emu.write16(%(ram)d,tests[i][1],memory);emu.write16(%(ram)d+8,tests[i][2]%%65536,memory);emu.write(%(ram)d+10,math.floor(tests[i][2]/65536),memory);emu.write16(%(done)d,0,memory);emu.write16(%(go)d,1,memory);waiting=true
end,emu.eventType.endFrame)'''%{'ram':syms['wnt_ram'],'go':syms['wnt_go'],'done':syms['wnt_done']})
 luapath=a.out/'check.lua';luapath.write_text('\n'.join(lua));log=io.StringIO()
 with contextlib.redirect_stdout(log):result=mesen.run(str(rom),'W%d'%(125+2*len(cases)),str(a.out),lua=str(luapath),timeout=900)
 (a.out/'raw.txt').write_text(log.getvalue());data={name:v for kind,name,v in result};raw=data.get('results.bin',b'');clocks=list(map(int,data.get('clocks.txt',b'').split()));failures=[];sign_fail=0
 for k,(index,u) in enumerate(cases):
  expected=[]
  for f,c in enumerate(rows[index]):
   h2=c[2]+rounded(c[3]*u,1<<24);h1=c[1]+rounded(h2*u,1<<24);h0=c[0]+rounded(h1*u,1<<24);sign_fail+=h2>0 or (h1<0 if f==0 else h1>0) or h0<0;expected.append(rounded(h0,256))
  want=b''.join(encode(x,6) for x in expected);got=raw[k*12:(k+1)*12]
  if got!=want:failures.append({'index':index,'u':u,'expected':want.hex(),'actual':got.hex()})
 if len(raw)!=12*len(cases) or len(clocks)!=len(cases):failures.append('Incomplete output')
 report={'cases':len(cases),'differences':len(failures),'failures':failures[:30],'model_sign_violations':sign_fail,'clocks':{'median':statistics.median(clocks),'mean':statistics.mean(clocks),'min':min(clocks),'max':max(clocks)} if clocks else {},'last_cell_max_u':last_u,'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'table_sha256':hashlib.sha256(text.encode()).hexdigest(),'injected_latch_sequences':int(data.get('hits.txt',b'0')),'negative_control':a.negative_control,'scope':'Shared-entry native LUT/Horner pair only; excludes radian range reduction/cache, solver and FPS.'};(a.out/'check.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return bool(failures) or bool(sign_fail)
if __name__=='__main__':raise SystemExit(main())
