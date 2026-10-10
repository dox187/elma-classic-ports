"""Build/test isolated native compact integration; never builds production.

Accepted position/unwrapped angle layout is signed48 Q32 with signed48 Q40
per-step rates (--rate-width48). The narrower historical Q29/Q34/Q37 test is
retained with --rate-width40. This tests arithmetic, not full-solver fidelity.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys

import mesen


def rounded_shift(value, shift):
    magnitude = (abs(value) + (1 << (shift - 1))) >> shift
    return -magnitude if value < 0 else magnitude


def encode(value, size):
    return (value & ((1 << (size * 8)) - 1)).to_bytes(size, 'little')


def expected(state, rate, shift):
    value = state + rounded_shift(rate, shift)
    overflow = int(not -(1 << 47) <= value < (1 << 47))
    return encode(value, 6) + encode(overflow, 2)


def cases(seed=203714, rate_width=40):
    result = []
    rng = random.Random(seed)
    states = [0, 1, -1, (2000 << 29), -(2000 << 29),
              -(1 << 47), (1 << 47)-1, -(1 << 32), (1 << 32)-1,
              -65536, 65535, -(32 << 29), (32 << 29)]
    commands=((1,5),(2,8)) if rate_width==40 else ((3,8),(4,8))
    for command, shift in commands:
        half = 1 << (shift-1)
        rates = [0, 1, -1, half-1, half, half+1, -half+1, -half,
                 -half-1, -(1 << (rate_width-1)), (1 << (rate_width-1))-1,
                 65535, 65536, -65536, (1 << 32)-1, -(1 << 32)]
        for state in states:
            for rate in rates:
                result.append((command, shift, state, rate))
        for _ in range(1500):
            result.append((command, shift, rng.randrange(-(1 << 47), 1 << 47),
                           rng.randrange(-(1 << (rate_width-1)), 1 << (rate_width-1))))
    return result


def build(folder):
    home = Path(os.environ.get('PVSNESLIB_HOME',
                    '~/.local/share/elma-snes/pvsneslib-4.6.0/pvsneslib')).expanduser()
    dev = home / 'devkitsnes'
    folder.mkdir(parents=True, exist_ok=True)
    driver = folder / 'driver'
    commands = [
        [str(dev/'bin/816-tcc'), '-Wall', '-F', '-Isrc', '-Ibuild/gen',
         '-I'+str(home/'pvsneslib/include'), '-I'+str(dev/'include'),
         '-c', 'test/wide_integrate_driver.c', '-o', str(driver)+'.ps'],
        [str(dev/'tools/816-opt'), '-i', str(driver)+'.ps', '-o', str(driver)+'.s'],
        [str(dev/'bin/wla-65816'), '-d', '-s', '-x', '-Ibuild/gen', '-Isrc',
         '-o', str(driver)+'.obj', str(driver)+'.s'],
        [str(dev/'bin/wla-65816'), '-h', '-s', '-x', '-Ibuild/gen', '-Isrc', '-Itest',
         '-o', str(folder/'integrate.obj'), 'test/wide_integrate.asm'],
    ]
    for command in commands:
        subprocess.run(command, check=True, capture_output=True, text=True)
    objects = Path('build/render-iterations/frozen/test_render.link').read_text().splitlines()
    objects[1] = str(driver)+'.obj'
    objects.insert(2, str(folder/'integrate.obj'))
    link = folder / 'integrate.link'
    link.write_text('\n'.join(objects)+'\n')
    rom = folder / 'integrate.sfc'
    command = [str(dev/'bin/wlalink'), '-d', '-s', '-v', '-A', '-c', '-L',
               str(home/'pvsneslib/lib/LoROM_FastROM'), str(link), str(rom)]
    completed = subprocess.run(command, capture_output=True, text=True)
    (folder/'link.log').write_text(completed.stdout+completed.stderr)
    completed.check_returncode()
    subprocess.run([sys.executable, 'tools/romfix.py', str(rom), str(rom), '--tv', 'ntsc'],
                   check=True, capture_output=True, text=True)
    for name in ('wide_integrate.py', 'wide_integrate.asm', 'wide_integrate.inc',
                 'wide_integrate_driver.c'):
        (folder/name).write_bytes((Path('test')/name).read_bytes())
    return rom


def check(rom, folder, rate_width=40):
    tests = cases(rate_width=rate_width)
    syms = mesen.read_symbols(str(rom))
    lua = [r'''
local memory=emu.memType.snesMemory
local tests,results,clocks={}, {}, {}
local index,waiting,t0,dt,finished=1,false,0,0,false
local function put(addr,hex)
 for i=1,#hex,2 do emu.write(addr+(i-1)/2,tonumber(hex:sub(i,i+1),16),memory) end
end
local function read(addr,n)
 local bytes={}
 for i=0,n-1 do bytes[#bytes+1]=string.char(emu.read(addr+i,memory)) end
 return table.concat(bytes)
end
''']
    for command, shift, state, rate in tests:
        data = encode(state, 6)+b'\x5a\xa5'+encode(rate, rate_width//8)+b'\x7e'*(8-rate_width//8)
        lua.append('tests[#tests+1]={%d,%r}' % (command, data.hex()))
    functions=('position','angle') if rate_width==40 else ('position_wide','angle_wide')
    for function in functions:
        lua.append('emu.addMemoryCallback(function() t0=emu.getMasterClock() end,emu.callbackType.exec,%d)' %
                   syms['wide_integrate_'+function])
        lua.append('emu.addMemoryCallback(function() dt=emu.getMasterClock()-t0 end,emu.callbackType.exec,%d)' %
                   syms['wide_integrate_'+function+'_end'])
    lua.append('''
local frame=0
emu.addEventCallback(function()
 frame=frame+1
 if frame<120 or finished then return end
 if waiting then
  if emu.read16(%(done)d,memory)==0 then return end
  results[#results+1]=read(%(ram)d+16,6)..read(%(ram)d+24,2)..read(%(ram)d,16)
  clocks[#clocks+1]=tostring(dt)
  index=index+1 waiting=false
 end
 if index>#tests then
  out("DATA","results.bin",table.concat(results))
  out("DATA","clocks.txt",table.concat(clocks,"\\n"))
  finished=true
  return
 end
 put(%(ram)d,tests[index][2])
 emu.write16(%(done)d,0,memory)
 emu.write16(%(go)d,tests[index][1],memory)
 waiting=true
end,emu.eventType.endFrame)
''' % {'done':syms['wi_done'], 'go':syms['wi_go'], 'ram':syms['wi_ram']})
    path = folder/'check.lua'
    path.write_text('\n'.join(lua))
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        returned = mesen.run(str(rom), 'W%d' % (125+2*len(tests)), str(folder),
                             lua=str(path), timeout=600)
    (folder/'raw.txt').write_text(log.getvalue())
    data = {name:value for kind,name,value in returned}
    raw = data.get('results.bin', b'')
    clocks = list(map(int,data.get('clocks.txt',b'').split()))
    failures = []
    if len(raw) != len(tests)*24 or len(clocks) != len(tests):
        failures.append('Incomplete emulator output')
    for n,(command,shift,state,rate) in enumerate(tests):
        want = expected(state,rate,shift)
        inputs = encode(state,6)+b'\x5a\xa5'+encode(rate,rate_width//8)+b'\x7e'*(8-rate_width//8)
        got = raw[n*24:(n+1)*24]
        if got != want+inputs:
            failures.append({'case':n,'shift':shift,'state':state,'rate':rate,
                             'want':(want+inputs).hex(),'got':got.hex()})
    timings = {}
    commands=((1,'position'),(2,'unwrapped_angle')) if rate_width==40 else ((3,'position_wide'),(4,'unwrapped_angle_wide'))
    for command,name in commands:
        group=[clock for clock,test in zip(clocks,tests) if test[0]==command]
        if group:
            timings[name]={'median':statistics.median(group),'minimum':min(group),
                           'maximum':max(group),'mean':statistics.mean(group)}
    report = {'cases':len(tests),'differences':len(failures),'failures':failures,
              'timings_master_clocks':timings,
              'rom_sha256':hashlib.sha256(Path(rom).read_bytes()).hexdigest(),
              'scope':'Arithmetic-only experimental component; no production solver change'}
    (folder/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:value for key,value in report.items() if key!='failures'},indent=2))
    return bool(failures)


def main():
    ap=argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out',default='build/wide-integrate')
    ap.add_argument('--rom',help='Use existing ROM instead of building')
    ap.add_argument('--rate-width',type=int,choices=(40,48),default=40)
    a=ap.parse_args()
    folder=Path(a.out)
    folder.mkdir(parents=True,exist_ok=True)
    return check(Path(a.rom) if a.rom else build(folder),folder,a.rate_width)


if __name__=='__main__':
    sys.exit(main())
