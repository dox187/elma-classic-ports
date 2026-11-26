"""Link the scheduled motion routine into a cartridge and check against integer rounding."""
import argparse
import hashlib
import json
import random
import re
import struct
import subprocess
from pathlib import Path
from pyboy import PyBoy

base = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--gen', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
gen, out = args.gen.resolve(), args.out.resolve()
out.mkdir(parents=True, exist_ok=True)
header = (gen / 'physics_q24_coefficients.h').read_text()
move = int(re.search(r'#define Q24_MOVE (\d+)', header)[1])
manifest = json.loads((gen / 'physics_q24_manifest.json').read_text())
first = manifest['first_bank']
bank = first + move // 2
coef = manifest['coefficient_values'][move]
assert 0 <= coef <= (1 << 23)

(out/'fixture.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
const uint8_t riding_move_index=MOVEINDEX,riding_angle_index=0,q24_first_bank_low=FIRSTLOW;
uint8_t riding_subphase,caller_bank;
int32_t move_residual[8];
uint32_t position[8];
int32_t velocity[8],delta[8],fractions[8];
uint8_t saturated[8],marker[8],shadow[8],phase_slot;
extern int32_t q24_fraction;
extern uint8_t q24_saturated;
int32_t phase_advance(int32_t velocity,uint8_t shift,uint8_t slot);
void fixture_init(void){}
void fixture_load(void){}
void fixture_check(void){}
void main(void) {
 uint8_t i;
 disable_interrupts();
 DISPLAY_OFF;
 cpu_fast();
 fixture_init();
 while(1){
   fixture_load();
   SWITCH_ROM(caller_bank);
   for(i=0;i!=8;i++){
     delta[i]=phase_advance(velocity[i],2,i);
     position[i]+=(uint32_t)delta[i];
     fractions[i]=q24_fraction;
     saturated[i]=q24_saturated;
     marker[i]=*(volatile uint8_t *)0x4000;
     shadow[i]=CURRENT_BANK;
   }
   fixture_check();
 }
}
''')
for b in [2,7]:
    (out/f'bank{b}.c').write_text(f'#pragma bank {b}\nconst unsigned char marker{b}={0xa0+b};\n')

rom = out/'fixture.gbc'
lcc = base/'.toolchain/gbdk/bin/lcc'
cmd = [lcc,'-msm83:gb','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-j',
       f'-DMOVEINDEX={move}',f'-DFIRSTLOW={first&255}','-o',rom,
       out/'fixture.c',base/'src/physics_phase.s',base/'src/physics_q24.s',
       out/'bank2.c',out/'bank7.c',gen/f'physics_q24_table_{bank}.c']
subprocess.run(cmd,cwd=out,check=True)
sy = {k:int(v,16) for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)', rom.with_suffix('.noi').read_text())}
emu = PyBoy(str(rom),window='null',sound_emulated=False,cgb=True)
emu.set_emulation_speed(0)
def wr(name, data):
    a=sy['_'+name]
    emu.memory[a:a+len(data)]=data
def rd(name, length):
    a=sy['_'+name]
    return bytes(emu.memory[a:a+length])
def arr(name, fmt, values):
    wr(name,struct.pack('<'+fmt*len(values),*values))
def check(name, fmt, values):
    actual=struct.unpack('<'+fmt*len(values),rd(name,struct.calcsize('<'+fmt*len(values))))
    assert actual==tuple(values),(name,count,phase,actual,values,vel,previous)
half=1<<23; unit=2*half; rng=random.Random(691380)
edges={0,1,-1,(1<<31)-1,-(1<<31)}
for n in range(32):
    for sg in (-1,1):
        edges.update(v for k in (-2,-1,0,1,2) if -(1<<31)<=(v:=sg*(1<<n)+k)<(1<<31))
# Every residual carry/tie for each edge input; exercise product byte boundaries.
pairs=[]
for v in sorted(edges):
    frac=((v*coef+half)%unit)-half
    for r in sorted({0,1,-1,-half,half-1,
                  *((-frac-half+k+half)%unit-half for k in (-1,0,1))}):
        pairs.append((v,r))
for digit in range(256):
    for shift in (0,8,16,24):
        for fill in (0,0xffffffff,0x7fff80ff,0x0101fffe):
            u=fill & ~(255<<shift) | digit<<shift
            v=(u+2**31)%2**32-2**31
            pairs.append((v,rng.randrange(-half,half)))
for _ in range(4096):
    width=rng.choice((8,16,24,32))
    pairs.append((rng.randrange(-(1<<(width-1)),1<<(width-1)),rng.randrange(-half,half)))
rng.shuffle(pairs)
while len(pairs)%8:pairs.append((0,0))
# Each eight-lane example runs partial, full, partial, full with live residuals and
# positions. The full step must also preserve each seeded/preceding Q24 side effect.
count=0; phase=0; done=False
def load(_):
    global bank_in,vel,previous,pos,frac,sat,phase,done
    if count==len(pairs)//8*4:
        done=True
        return
    group=count//4
    stage=count%4
    phase=1-stage%2
    bank_in=(2,7)[(group+stage)%2]
    if stage==0:
        chunk=pairs[8*group:8*group+8]
        previous=[v[1] for v in chunk]
        pos=[rng.randrange(1<<32) for _ in range(8)]
        arr('move_residual','i',previous)
        arr('position','I',pos)
    vel=([v[0] for v in pairs[8*group:8*group+8]] if stage==0 else
         [rng.choice(tuple(edges)) if i&1 else rng.randrange(-(1<<31),1<<31) for i in range(8)])
    frac=rng.randrange(-(1<<31),1<<31); sat=rng.randrange(256)
    arr('q24_fraction','i',[frac]); arr('q24_saturated','B',[sat])
    arr('riding_subphase','B',[phase]);arr('caller_bank','B',[bank_in])
    arr('velocity','i',vel)
def observe(_):
    global previous,pos,count,frac,sat
    if done:return
    deltas=[];res=[];fs=[];ss=[]
    for v,r in zip(vel,previous):
        prod=v*(coef if phase else 1<<20)
        delta=(prod+r+half)//unit
        deltas.append(delta);res.append(prod+r-delta*unit)
        if phase:
            frac=prod-((prod+half)//unit)*unit;sat=0
        fs.append(frac);ss.append(sat)
    pos=[(p+d)&0xffffffff for p,d in zip(pos,deltas)]
    check('delta','i',deltas);check('move_residual','i',res);check('position','I',pos)
    check('fractions','i',fs);check('saturated','B',ss);check('marker','B',[0xa0+bank_in]*8)
    check('shadow','B',[bank_in]*8);check('velocity','i',vel)
    previous=res
    count+=1
emu.hook_register(0,sy['_fixture_load'],load,None)
emu.hook_register(0,sy['_fixture_check'],observe,None)
try:
    for _ in range(2000):
        emu.tick(8,False)
        if done:break
    assert done,(count,len(pairs))
finally:
    emu.stop(save=False)
report=dict(passed=True,coefficient=coef,cases=len(pairs),axis_calls=count*8,
            partial_calls=count*4,full_calls=count*4,
            eight_axis_sequences=len(pairs)//8,source_sha256=hashlib.sha256((base/'src/physics_phase.s').read_bytes()).hexdigest(),
            rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest())
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report)
