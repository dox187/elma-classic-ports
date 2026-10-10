#!/usr/bin/env python3
"""Independent integer edge/random tests for original-trig domain products."""
import argparse,contextlib,hashlib,io,json,random,re,statistics
from pathlib import Path
import mesen
from wide_native_trig_check import build,encode
from wide_native_q44_products import product,square
from m7_latch_check import sites

def generate(out,square_fast=False,short_products=False):
 asm=['.include "hdr.asm"','.include "phys.inc"','.RAMSECTION ".wqp_ram" BANK 0 SLOT 1 ALIGN 256','wqp_ram dsb 256','.ENDS','.SECTION ".wqp_text" SUPERFREE','wqp_run:',' php',' phb',' phd',' rep #$30',' phx',' phy',' sep #$20',' lda.b #$80',' pha',' plb',' rep #$20',' lda #wqp_ram',' tcd']
 for name,dst in [('x',0),('y',8)]:
  for j in range(4):asm+=[' lda.l wqp_%s+%d'%(name,2*j),' sta.b %d'%(dst+2*j)]
 asm+=[' lda.l wqp_kind']
 for j in range(1,4):asm+=[' cmp #%d'%j,' bne +',' jsr wqp_product%d'%j,' jmp wqp_return','+:']
 asm+=[' jsr wqp_product4','wqp_return:']
 for j in range(4):asm+=[' lda.b %d'%(16+2*j),' sta.l wqp_result+%d'%(2*j)]
 asm+=[' ply',' plx',' pld',' plb',' plp','wqp_end:',' rtl']
 for j,args in enumerate([(3,5,False),(2,5,False),(3,5,True),(3,4,True)],1):
  body=square(0,16)if square_fast and j==1 else product(0,8,16,*args,accbytes=8 if short_products and j==2 else 10 if short_products and j==4 else 12)
  asm+=['wqp_product%d:'%j,body.replace('wqp_','wqp_%d_'%j).replace('wqs_','wqp_square_'),' rts']
 asm+=['wqp_text_end:','.ENDS'];text='\n'.join(asm);inverses={'bcc':'bcs','bcs':'bcc','beq':'bne','bne':'beq','bpl':'bmi','bmi':'bpl'};serial=0
 def branch(m):
  nonlocal serial
  serial+=1;op,label=m.groups();return ' '+inverses[op]+' wqp_long_%d\n jmp '%serial+label+'\nwqp_long_%d:'%serial
 text=re.sub(r'^ (bcc|bcs|beq|bne|bpl|bmi) (wqp_\w+)$',branch,text,flags=re.M);native=out/'product.asm';native.write_text(text+'\n');driver=out/'product_driver.c';driver.write_text('#include <snes.h>\n#include "core.h"\nvoid wqp_run(void);u16 wqp_x[4],wqp_y[4],wqp_result[4];volatile u16 wqp_go,wqp_done,wqp_kind;\nint main(void){consoleInit();core_init();core_screen_off();while(1){if(wqp_go){wqp_kind=wqp_go;wqp_go=0;wqp_run();wqp_done=1;}core_frame_done();}return 0;}\n');return native,driver

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,default=Path('build/native-q44-products'));ap.add_argument('--inject-latch',action='store_true');ap.add_argument('--negative-control',action='store_true');ap.add_argument('--square-fast',action='store_true');ap.add_argument('--short-products',action='store_true');a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True);native,driver=generate(a.out,a.square_fast,a.short_products);rom=build(a.out,str(native),str(driver));rng=random.Random(840187);limits=[(107944301637,107944301637),(41396121,107944301637),(1<<48,107944301637),(1<<48,20698061)];cases=[]
 for kind,(xm,ym)in enumerate(limits,1):
  def edges(n):return sorted(set([0,1,2,127,128,255,256,32767,32768,65535,65536,n-1,n]+[(1<<k)+o for k in range(n.bit_length())for o in [-1,0,1]if 0<=(1<<k)+o<=n]))
  xs=edges(xm);ys=edges(ym);cases.extend((kind,x,y)for x in xs for y in [0,1,ym-1,ym]);cases.extend((kind,x,y)for x in [0,1,xm-1,xm]for y in ys);cases.extend((kind,rng.randrange(xm+1),rng.randrange(ym+1))for _ in range(500))
 for kind,(xm,ym)in enumerate(limits,1):
  for k in range(48):
   x=1<<k;y=1<<(47-k)
   for multiplier in [1,3]:
    for dy in [-1,0,1]:
     if x*multiplier<=xm and 0<=y+dy<=ym:cases.append((kind,x*multiplier,y+dy))
 if a.square_fast:cases=[(kind,x,x if kind==1 else y)for kind,x,y in cases]
 sym=mesen.read_symbols(str(rom));lua=['local m=emu.memType.snesMemory;local tests,results,clocks={},{},{};local i,waiting,f,t0,dt,hits,finished=1,false,0,0,0,0,false']
 for kind,x,y in cases:lua.append('tests[#tests+1]={%d,%r,%r}'%(kind,encode(x,8).hex(),encode(y,8).hex()))
 lua+=['emu.addMemoryCallback(function()t0=emu.getMasterClock()end,emu.callbackType.exec,%d)'%sym['wqp_run'],'emu.addMemoryCallback(function()dt=emu.getMasterClock()-t0 end,emu.callbackType.exec,%d)'%sym['wqp_end']]
 if a.inject_latch:
  for address in sites(rom,sym['core_m7_latch']):
   if not sym['wqp_run']<=address<=sym['wqp_text_end']:continue
   restore=''if a.negative_control else'emu.write(0x80211f,emu.read(%d,m),m);'%(sym['core_m7_latch']+1)
   lua.append('emu.addMemoryCallback(function()hits=hits+1;emu.write(0x80210d,0x5a,m);emu.write(0x80210d,0xc3,m);emu.write(0x80210e,0x39,m);emu.write(0x80210e,0xa6,m);%s end,emu.callbackType.exec,%d)'%(restore,address))
 lua.append('''local function put(a,h)for j=1,#h,2 do emu.write(a+(j-1)/2,tonumber(h:sub(j,j+1),16),m)end end
local function read(a)local s={}for j=0,7 do s[#s+1]=string.char(emu.read(a+j,m))end return table.concat(s)end
emu.addEventCallback(function()f=f+1;if f<120 or finished then return end;if waiting then if emu.read16(%(done)d,m)==0 then return end;results[#results+1]=read(%(result)d)..read(%(x)d)..read(%(y)d);clocks[#clocks+1]=tostring(dt);i=i+1;waiting=false end;if i>#tests then finished=true;out("DATA","results.bin",table.concat(results));out("DATA","clocks.txt",table.concat(clocks,"\\n"));out("DATA","hits.txt",tostring(hits));emu.stop(0);return end;put(%(x)d,tests[i][2]);put(%(y)d,tests[i][3]);emu.write16(%(done)d,0,m);emu.write16(%(go)d,tests[i][1],m);waiting=true end,emu.eventType.endFrame)'''%{k:sym['wqp_'+k]for k in ['x','y','done','go','result']});path=a.out/'check.lua';path.write_text('\n'.join(lua));log=io.StringIO();err=io.StringIO()
 try:
  with contextlib.redirect_stdout(log),contextlib.redirect_stderr(err):returned=mesen.run(str(rom),'W%d'%(125+2*len(cases)),str(a.out),lua=str(path),timeout=900)
 finally:(a.out/'raw.txt').write_text(log.getvalue());(a.out/'stderr.txt').write_text(err.getvalue())
 data={n:v for k,n,v in returned};raw=data.get('results.bin',b'');clocks=list(map(int,data.get('clocks.txt',b'').split()));fails=[]
 if len(raw)!=24*len(cases):fails.append({'incomplete':len(raw),'expected':24*len(cases)})
 for i,(kind,x,y)in enumerate(cases):
  expected=encode((x*y+(1<<47))>>48,8)+encode(x,8)+encode(y,8)
  if raw[24*i:24*i+24]!=expected:fails.append({'case':i,'kind':kind,'x':x,'y':y,'want':expected.hex(),'got':raw[24*i:24*i+24].hex()})
 timings={}
 for kind in range(1,5):
  c=[clock for clock,case in zip(clocks,cases)if case[0]==kind];timings[str(kind)]={'median':statistics.median(c),'min':min(c),'max':max(c)}
 report={'square_fast':a.square_fast,'short_products':a.short_products,'cases':len(cases),'differences':len(fails),'failures':fails[:30],'latch_injections':int(data.get('hits.txt',b'0')),'operand_maxima':limits,'timings_master_clocks':timings,'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'scope':'Exact isolated positive products and unchanged inputs; complete bounded64/80/96-bit accumulation and one half-away>>48. Not solver fidelity/FPS.'};(a.out/'check.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return bool(fails)
if __name__=='__main__':raise SystemExit(main())
