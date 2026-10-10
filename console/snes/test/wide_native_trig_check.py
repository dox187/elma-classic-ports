#!/usr/bin/env python3
"""Private ROM exact coefficient/u24 product checks, not a full solver/FPS test."""
import argparse,contextlib,hashlib,io,json,os,random,statistics,subprocess,sys
from pathlib import Path
import mesen

def build(folder, native_source="test/wide_native_trig.asm", driver_source="test/wide_native_trig_driver.c"):
    home = Path(os.environ.get('PVSNESLIB_HOME',
                    '~/.local/share/elma-snes/pvsneslib-4.6.0/pvsneslib')).expanduser()
    dev = home / 'devkitsnes'
    folder.mkdir(parents=True, exist_ok=True)
    driver = folder / 'driver'
    commands = [
        [str(dev/'bin/816-tcc'), '-Wall', '-F', '-Isrc', '-Ibuild/gen',
         '-I'+str(home/'pvsneslib/include'), '-I'+str(dev/'include'),
         '-c', driver_source, '-o', str(driver)+'.ps'],
        [str(dev/'tools/816-opt'), '-i', str(driver)+'.ps', '-o', str(driver)+'.s'],
        [str(dev/'bin/wla-65816'), '-d', '-s', '-x', '-Ibuild/gen', '-Isrc',
         '-o', str(driver)+'.obj', str(driver)+'.s'],
        [str(dev/'bin/wla-65816'), '-h', '-s', '-x', '-Ibuild/gen', '-Isrc', '-Itest',
         '-o', str(folder/'native_trig.obj'), native_source],
    ]
    for command in commands:
        subprocess.run(command, check=True, capture_output=True, text=True)
        if driver_source.endswith('wide_native_trig_full_driver.c') and command[0].endswith('816-opt'):
            path=Path(str(driver)+'.s');source=path.read_text()
            for wrapper in ['wide_trig_pair','wide_trig_pair_words']:
                start=source.index(wrapper+':\n');end=source.index('.ENDS',start);body=source[start:end];assert body.count('rtl')==1;body=body.replace('rtl',wrapper+'_end:\nrtl');source=source[:start]+body+source[end:]
            for wrapper in ['wide_trig_pair','wide_trig_pair_words']:
                call=source.index('jsr.l '+wrapper+'\n');start=source.rfind('pea.w :wnf_cos',0,call);end=source.index('\ntas\n',call)+len('\ntas\n');source=source[:start]+wrapper+'_call_begin:\n'+source[start:end]+wrapper+'_call_end:\n'+source[end:]
            call=source.rindex('jsr.l wnt_trig\n');end=call+len('jsr.l wnt_trig\n');source=source[:call]+'wnt_trig_call_begin:\n'+source[call:end]+'wnt_trig_call_end:\n'+source[end:]
            path.write_text(source)
    subprocess.run([str(dev/'bin/wla-65816'),'-h','-s','-x','-Ibuild/gen','-Isrc','-o',str(folder/'core.obj'),'src/core.asm'],check=True,capture_output=True,text=True)
    objects = Path('build/render-iterations/frozen/test_render.link').read_text().splitlines()
    objects=[str(folder/'core.obj') if line.endswith('/008-core.obj') else line for line in objects]
    objects[1] = str(driver)+'.obj'
    objects.insert(2, str(folder/'native_trig.obj'))
    link = folder / 'native_trig.link'
    link.write_text('\n'.join(objects)+'\n')
    rom = folder / 'native_trig.sfc'
    command = [str(dev/'bin/wlalink'), '-d', '-s', '-v', '-A', '-c', '-L',
               str(home/'pvsneslib/lib/LoROM_FastROM'), str(link), str(rom)]
    completed = subprocess.run(command, capture_output=True, text=True)
    (folder/'link.log').write_text(completed.stdout+completed.stderr)
    completed.check_returncode()
    subprocess.run([sys.executable, 'tools/romfix.py', str(rom), str(rom), '--tv', 'ntsc'],
                   check=True, capture_output=True, text=True)
    for name in ('wide_native_trig_check.py', 'wide_native_trig.asm', 'wide_native_trig.inc',
                 'wide_native_trig_driver.c'):
        (folder/name).write_bytes((Path('test')/name).read_bytes())
    return rom



def encode(value,n):return (value&((1<<(8*n))-1)).to_bytes(n,'little')
def tests():
 rng=random.Random(840187);result=[]
 for command,bits in [(1,40),(2,29),(3,17)]:
  coefficients=[-(1<<(bits-1)),-(1<<(bits-1))+1,-65536,-43691,-32768,-1,0,1,32767,43691,(1<<(bits-1))-1]
  us=[0,1,127,128,255,256,32767,32768,65535,65536,(1<<23)-1,1<<23,(1<<23)+1,(1<<24)-2,(1<<24)-1]
  for a in coefficients:
   if -(1<<(bits-1))<=a<(1<<(bits-1)):
    result.extend((command,a,u) for u in us)
  result.extend((command,rng.randrange(-(1<<(bits-1)),1<<(bits-1)),rng.randrange(1<<24)) for _ in range(900))
 return result

def check(rom,folder):
 cases=tests();syms=mesen.read_symbols(str(rom));lua=[r'''
local memory=emu.memType.snesMemory
local tests,results,clocks={}, {}, {}
local index,waiting,t0,dt,finished=1,false,0,0,false
local function put(addr,hex)for i=1,#hex,2 do emu.write(addr+(i-1)/2,tonumber(hex:sub(i,i+1),16),memory)end end
local function read(addr,n)local bytes={}for i=0,n-1 do bytes[#bytes+1]=string.char(emu.read(addr+i,memory))end return table.concat(bytes)end
''']
 for command,a,u in cases:
  data=encode(a,5)+b'\x5a\xa5\x3c'+encode(u,3)+b'\x11'*5
  lua.append('tests[#tests+1]={%d,%r}'%(command,data.hex()))
 for function in ['mul40','mul29','mul17']:
  lua.append('emu.addMemoryCallback(function()t0=emu.getMasterClock()end,emu.callbackType.exec,%d)'%syms['wnt_'+function])
  lua.append('emu.addMemoryCallback(function()dt=emu.getMasterClock()-t0 end,emu.callbackType.exec,%d)'%syms['wnt_'+function+'_end'])
 lua.append(r'''
local frame=0
emu.addEventCallback(function()
 frame=frame+1
 if frame<120 or finished then return end
 if waiting then
  if emu.read16(%(done)d,memory)==0 then return end
  results[#results+1]=read(%(ram)d+16,5)..read(%(ram)d,16)
  clocks[#clocks+1]=tostring(dt)
  index=index+1 waiting=false
 end
 if index>#tests then
  out("DATA","results.bin",table.concat(results));out("DATA","clocks.txt",table.concat(clocks,"\n"));finished=true;return
 end
 put(%(ram)d,tests[index][2]);emu.write16(%(done)d,0,memory);emu.write16(%(go)d,tests[index][1],memory);waiting=true
end,emu.eventType.endFrame)
'''%{'done':syms['wnt_done'],'go':syms['wnt_go'],'ram':syms['wnt_ram']})
 path=folder/'check.lua';path.write_text('\n'.join(lua));log=io.StringIO()
 with contextlib.redirect_stdout(log):returned=mesen.run(str(rom),'W%d'%(125+2*len(cases)),str(folder),lua=str(path),timeout=600)
 (folder/'raw.txt').write_text(log.getvalue());data={name:value for kind,name,value in returned};raw=data.get('results.bin',b'');clocks=list(map(int,data.get('clocks.txt',b'').split()));failures=[]
 if len(raw)!=len(cases)*21 or len(clocks)!=len(cases):failures.append('Incomplete emulator output')
 for i,(command,a,u) in enumerate(cases):
  product=abs(a)*u;rounded=(product+(1<<23))>>24;rounded=-rounded if a<0 else rounded
  inputs=encode(a,5)+b'\x5a\xa5\x3c'+encode(u,3)+b'\x11'*5;want=encode(rounded,5)+inputs;got=raw[i*21:(i+1)*21]
  if got!=want:failures.append({'case':i,'command':command,'a':a,'u':u,'expected':want.hex(),'actual':got.hex()})
 timings={}
 for command,name in [(1,'signed40'),(2,'signed29'),(3,'signed17')]:
  group=[c for c,t in zip(clocks,cases) if t[0]==command]
  if group:timings[name]={'median':statistics.median(group),'mean':statistics.mean(group),'min':min(group),'max':max(group)}
 report={'cases':len(cases),'failures':failures,'differences':len(failures),'timings_master_clocks':timings,'rom_sha256':hashlib.sha256(Path(rom).read_bytes()).hexdigest(),'note':'Exact native helper arithmetic only; not fullsolver fidelity or FPS.'};(folder/'check.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='failures'},indent=2));return int(bool(failures))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=Path('build/native-trig-product'));a=ap.parse_args();rom=build(a.out);raise SystemExit(check(rom,a.out))
