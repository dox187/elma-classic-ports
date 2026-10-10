#!/usr/bin/env python3
"""Full signed48Q32 native trig, cache, C ABI and interrupt checks."""
import argparse,contextlib,hashlib,io,json,random,re,statistics,subprocess,sys
from pathlib import Path
import mesen
from m7_latch_check import sites
from wide_native_trig_check import build,encode

def rounded(n,d):return (-1 if n<0 else 1)*((abs(n)+d//2)//d)
def generate(folder,base):
 text=(base/'wide_trig_table.h').read_text();rows=[json.loads(line.strip().rstrip(',').replace('{','[').replace('}',']')) for line in text.splitlines() if line.startswith('{{')]
 full=Path('test/wide_native_trig_full.asm').read_text();lite=Path('test/wide_native_trig_lite.asm').read_text();macro=lite[lite.index('.MACRO WNL_HORNER'):lite.index('wnt_pair:')];dispatch=lite[lite.index(' lda.b 0\n and #$07FF'):lite.index('_wnl_done:\n plx')];dispatch=dispatch.replace('_wnl_done','_wnlf_done');banks=lite[lite.index('\nwnl_bank0:')+1:lite.index('wnl_text_end:')]
 full=full.rsplit('.ENDS',1)[0]+macro+'wnl_dispatch:\n'+dispatch+'_wnlf_done:\n rts\n'+banks+'wnf_text_end:\n.ENDS\n'
 # Expand potentially distant branches in the phase reducer; short cache macros
 # stay short. WLA has no automatic bank-local long conditional branch.
 inverses={'bcc':'bcs','bcs':'bcc','beq':'bne','bne':'beq','bpl':'bmi','bmi':'bpl'};count=0
 def branch(m):
  nonlocal count
  count+=1;op,label=m.groups();return ' '+inverses[op]+' wnf_long_'+str(count)+'\n jmp '+label+'\nwnf_long_'+str(count)+':'
 full=re.sub(r'^ (bcc|bcs|beq|bne|bpl|bmi) (wnf_[A-Za-z0-9_]+)$',branch,full,flags=re.M);full=re.sub(r'^ bra (wnf_[A-Za-z0-9_]+)$',r' jmp \1',full,flags=re.M)
 for fi,name in enumerate(['sin','cos']):
  for bank in range(4):
   blob=b''.join(b''.join(encode(abs(c),n) for c,n in zip(row[fi][:3],[6,4,3])) for row in rows[bank*2048:(bank+1)*2048]);path=folder/(name+str(bank)+'.bin');path.write_bytes(blob);full+='\n.SECTION ".wnl_'+name+str(bank)+'_table" SUPERFREE\nwnl_'+name+str(bank)+':\n.incbin "'+str(path.resolve())+'"\n.ENDS\n'
 source=folder/'full.asm';source.write_text(full);return source,rows,text

def tests():
 rng=random.Random(840187);minimum=-(1<<47);maximum=(1<<47)-1;angles=set([minimum,minimum+1,minimum+255,maximum,maximum-1,maximum-255,0,1,-1,1<<32,-(1<<32),128<<32,-(128<<32),127<<32,-(127<<32)])
 for _ in range(250):angles.add(rng.randrange(-128<<32,128<<32));angles.add(rng.randrange(minimum,maximum+1))
 pi=884279719003555
 for i in range(0,6434,256):
  for k in [-5000,0,5000]:
   for phase in [i*(1<<36),pi-i*(1<<36),pi+i*(1<<36),2*pi-i*(1<<36)]:
    angle=rounded(phase+2*pi*k,1<<16)
    for offset in [-1,0,1]:
     if minimum<=angle+offset<=maximum:angles.add(angle+offset)
 # P32->Q48 conversion has steps65536, uhalf-way points are exact at16P32.
 for i in [0,1,1023,2047,2048,4095,4096,6143,6144,6433]:
  for off in [-1,0,1]:angles.add((i<<20)+8+off)
 result=[]
 for angle in sorted(angles):
  other=angle+1 if angle<maximum else angle-1
  third=angle+2 if angle<maximum-1 else angle-2
  result.extend([(1,angle),(1,angle),(2,other),(2,other),(3,third),(3,third)])
 return result

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--base',type=Path,default=Path('build/wide-compact-trig-lite-q40'));ap.add_argument('--out',type=Path,default=Path('build/native-trig-full'));ap.add_argument('--limit',type=int);ap.add_argument('--inject-latch',action='store_true');ap.add_argument('--negative-control',action='store_true');a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True);source,rows,text=generate(a.out,a.base)
 try:rom=build(a.out,str(source),'test/wide_native_trig_full_driver.c')
 except subprocess.CalledProcessError as e:print(e.stdout,e.stderr);raise
 cases=tests();cases=cases[:a.limit] if a.limit else cases
 reference_cpp=a.out/'reference.cpp';reference_cpp.write_text('#include <iostream>\n#include "wide_fixed.h"\nint main(){int64_t a;while(std::cin>>a){wide_scalar p[2];wide_native_trig_pair(wide_scalar::from_raw(a*256),p);std::cout<<int64_t(wide_round_div(p[0].raw,1024))<<" "<<int64_t(wide_round_div(p[1].raw,1024))<<"\\n";}}\n')
 reference_exe=a.out/'reference';subprocess.run(['c++','-std=c++17','-O2','-DWIDE_BITS=40','-I'+str(a.base.resolve()),str(reference_cpp),'-o',str(reference_exe)],check=True)
 reference_run=subprocess.run([str(reference_exe)],input=''.join(str(angle)+'\n'for command,angle in cases),capture_output=True,text=True,check=True);reference=[tuple(map(int,line.split()))for line in reference_run.stdout.splitlines()];assert len(reference)==len(cases)
 syms=mesen.read_symbols(str(rom));lua=['local memory=emu.memType.snesMemory\nlocal tests,results,clocks,native,callclocks={},{},{},{},{}\nlocal i,waiting,frame,t0,nt0,dt,ndt,finished,hits,ct0,cdt=1,false,0,0,0,0,0,false,0,0,0\nlocal function put(a,s)for j=1,#s,2 do emu.write(a+(j-1)/2,tonumber(s:sub(j,j+1),16),memory)end end\nlocal function read(a,n)local s={}for j=0,n-1 do s[#s+1]=string.char(emu.read(a+j,memory))end return table.concat(s)end']
 for command,angle in cases:lua.append('tests[#tests+1]={%d,%r}'%(command,encode(angle,6).hex()))
 lua+=['emu.addMemoryCallback(function()nt0=emu.getMasterClock();if tests[i][1]==1 then t0=nt0 end end,emu.callbackType.exec,%d)'%syms['wnt_trig'],'emu.addMemoryCallback(function()ndt=emu.getMasterClock()-nt0;if tests[i][1]==1 then dt=ndt end end,emu.callbackType.exec,%d)'%syms['wnt_trig_end'],'emu.addMemoryCallback(function()t0=emu.getMasterClock()end,emu.callbackType.exec,%d)'%syms['wide_trig_pair'],'emu.addMemoryCallback(function()dt=emu.getMasterClock()-t0 end,emu.callbackType.exec,%d)'%syms['wide_trig_pair_end'],'emu.addMemoryCallback(function()t0=emu.getMasterClock()end,emu.callbackType.exec,%d)'%syms['wide_trig_pair_words'],'emu.addMemoryCallback(function()dt=emu.getMasterClock()-t0 end,emu.callbackType.exec,%d)'%syms['wide_trig_pair_words_end']]
 for label in ['wnt_trig','wide_trig_pair','wide_trig_pair_words']:
  lua+=['emu.addMemoryCallback(function()ct0=emu.getMasterClock()end,emu.callbackType.exec,%d)'%syms[label+'_call_begin'],'emu.addMemoryCallback(function()cdt=emu.getMasterClock()-ct0 end,emu.callbackType.exec,%d)'%syms[label+'_call_end']]
 if a.inject_latch:
  for address in sites(rom,syms['core_m7_latch']):
   if syms['wnt_trig']<=address<=syms['wnf_text_end']:
    restore='' if a.negative_control else 'emu.write(0x80211f,emu.read(%d,memory),memory)'%(syms['core_m7_latch']+1)
    lua.append('emu.addMemoryCallback(function()hits=hits+1;emu.write(0x80210d,0x5a,memory);emu.write(0x80210d,0xc3,memory);emu.write(0x80210e,0x39,memory);emu.write(0x80210e,0xa6,memory);%s end,emu.callbackType.exec,%d)'%(restore,address))
 lua.append('''emu.addEventCallback(function()frame=frame+1;if frame<120 or finished then return end
if waiting then if emu.read16(%(done)d,memory)==0 then return end
local s,c=%(ram)d+80,%(ram)d+88;if tests[i][1]>1 then s,c=%(sin)d,%(cos)d end
results[#results+1]=read(s,4)..read(c,4)..read(%(ram)d+182,2);clocks[#clocks+1]=tostring(dt);native[#native+1]=tostring(ndt);callclocks[#callclocks+1]=tostring(cdt);i=i+1;waiting=false end
if i>#tests then finished=true;out("DATA","hits.txt",tostring(hits));out("DATA","results.bin",table.concat(results));out("DATA","clocks.txt",table.concat(clocks,"\\n"));out("DATA","native_clocks.txt",table.concat(native,"\\n"));out("DATA","call_clocks.txt",table.concat(callclocks,"\\n"));return end
local target=%(ram)d;if tests[i][1]>1 then target=%(angle)d end;put(target,tests[i][2]);emu.write16(%(done)d,0,memory);emu.write16(%(go)d,tests[i][1],memory);waiting=true
end,emu.eventType.endFrame)'''%{'ram':syms['wnt_ram'],'go':syms['wnt_go'],'done':syms['wnt_done'],'angle':syms['wnf_angle'],'sin':syms['wnf_sin'],'cos':syms['wnf_cos']})
 path=a.out/'check.lua';path.write_text('\n'.join(lua));log,error=io.StringIO(),io.StringIO()
 try:
  with contextlib.redirect_stdout(log),contextlib.redirect_stderr(error):returned=mesen.run(str(rom),'W%d'%(125+2*len(cases)),str(a.out),lua=str(path),timeout=900)
 finally:(a.out/'raw.txt').write_text(log.getvalue());(a.out/'stderr.txt').write_text(error.getvalue())
 data={name:v for kind,name,v in returned};raw=data.get('results.bin',b'');clocks=list(map(int,data.get('clocks.txt',b'').split()));native=list(map(int,data.get('native_clocks.txt',b'').split()));callclocks=list(map(int,data.get('call_clocks.txt',b'').split()));pi=884279719003555;cache=[None,None];nextslot=0;failures=[];model_differences=0;groups={}
 for k,(command,angle) in enumerate(cases):
  phase=(angle<<16)%(2*pi);ns=phase>pi
  if ns:phase-=pi
  nc=phase>pi//2
  if nc:phase=pi-phase
  if ns:nc=not nc
  index,d=divmod(phase,1<<36);u=rounded(d,1<<20)
  if u==65536:index+=1;u=0
  pair=[]
  for c,neg in zip(rows[index],[ns,nc]):
   h=c[1]+rounded(c[2]*u,65536);result=c[0]+rounded(h*u,65536);pair.append((-1 if neg else 1)*rounded(result,1024))
  if tuple(pair)!=reference[k]:model_differences+=1
  pair=reference[k]
  hit=angle in cache
  if not hit:cache[nextslot]=angle;nextslot^=1
  wanted=b''.join(encode(x,4)for x in pair)+encode(int(hit),2);got=raw[k*10:(k+1)*10]
  if got!=wanted:failures.append({'case':k,'command':command,'angle_raw':angle,'index':index,'u':u,'expected':wanted.hex(),'actual':got.hex()})
  key=('cwords'if command==3 else 'cwrapper'if command==2 else 'direct')+('_hit'if hit else '_miss');groups.setdefault(key,[]).append((clocks[k],native[k],callclocks[k])) if k<len(clocks) and k<len(native) and k<len(callclocks) else None
 if len(raw)!=10*len(cases) or len(clocks)!=len(cases)or len(native)!=len(cases)or len(callclocks)!=len(cases):failures.append('Incomplete runner output')
 timing={}
 for key,values in groups.items():
  whole=[x[0]for x in values];core=[x[1]for x in values];overhead=[x[0]-x[1]for x in values];called=[x[2]for x in values];calloverhead=[x[2]-x[1]for x in values];timing[key]={'cases':len(values),'clocks':{'median':statistics.median(whole),'mean':statistics.mean(whole),'min':min(whole),'max':max(whole)},'native_median':statistics.median(core),'wrapper_overhead_median':statistics.median(overhead),'with_constant_argument_setup_return_cleanup':{'median':statistics.median(called),'mean':statistics.mean(called),'min':min(called),'max':max(called)},'complete_call_overhead_median':statistics.median(calloverhead)}
 report={'cases':len(cases),'differences':len(failures),'integer_model_vs_frozen_cpp_differences':model_differences,'failures':failures[:30],'timings':timing,'injected_latch_sequences':int(data.get('hits.txt',b'0')),'negative_control':a.negative_control,'angle_domain_radians':[-32768,32768-2**-32],'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'table_sha256':hashlib.sha256(text.encode()).hexdigest(),'scope':'Native signed48Q32 angle -> exactQ48 phase -> quadraticQ30 pair/twoentrycache incl measuredgenericCwrapper; not fullsolver FPS.'};(a.out/'check.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return bool(failures) or bool(model_differences)
if __name__=='__main__':raise SystemExit(main())
