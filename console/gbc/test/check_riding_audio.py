"""Native APU regression for source-derived suspension, volt and turn effects.

The fixture supplies exported poses and native volt counters, without running
or altering physics. It verifies detection, channel ownership, priorities,
clock wrap, actual PCM, bank restoration and the bounded motion update cost.
"""
import argparse
import json
import math
import re
import subprocess
from pathlib import Path

import numpy as np
from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen', type=Path, default=BASE/'build/gen-8m')
    parser.add_argument('--out', type=Path, default=BASE/'build/riding-audio-check')
    args = parser.parse_args()
    out, gen = args.out.resolve(), args.gen.resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((gen/'audio-manifest.json').read_text())
    for name, source, channel in [('creak','dorzsol.wav',2),('volt','ugras.wav',4),('turn','fordul.wav',4)]:
        effect = manifest['effects'][name]
        assert effect['source'] == source and effect['channel'] == channel
        assert effect['duration_vblanks'] == int(np.ceil(effect['samples']*4194304/70224/11025))
        assert effect['wav_sha256'] == {
            'creak':'f7109c034b709f436a15879fa61f5b75b2ac481aa3d91c5d8b74daaedb77a142',
            'volt':'dcbc9d35b9a4ab54dd8bce7768d465bdb9f4e9785043de5900ca07bc1c03cb3f',
            'turn':'2b670ef9dd6e41bc8d2db20e8ea4c90357d8a327f6b7e71001a638a0f7e74cc9'}[name]
        assert len({step['period'] for step in effect['windows']}) > 1
    (out/'driver.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include "audio.h"
#include "runtime.h"
#include "physics_core.h"
gbc_bike_t gbc_bike;
bike_t Bike;
volatile uint8_t ready,fx=255,reset_request,riding=1,hold,half_rate=1,native_size=sizeof(Bike);
volatile uint16_t banks_bad,irq_count;
void vblank(void) NONBANKED { ++irq_count; }
void service(void) BANKED;
void main(void) NONBANKED {
 cpu_fast();add_VBL(vblank);SWITCH_ROM(9);audio_init();ready=1;
 while(1) {
  vsync();
  if(reset_request) { audio_init();reset_request=0; }
  if(!hold)service();
  if(CURRENT_BANK!=9)++banks_bad;
 }
}
''')
    (out/'caller.c').write_text('''#pragma bank 5
#include <gb/gb.h>
#include "audio.h"
extern volatile uint8_t fx,riding,half_rate;
extern volatile uint16_t banks_bad;
void service(void) BANKED {
 if(fx!=255) { audio_effect(fx);fx=255; }
 if(!half_rate || !(sys_time&1))audio_update(riding,0,0,0);
 if(CURRENT_BANK!=5)++banks_bad;
}
''')
    (out/'observed_audio.c').write_text('''#include "audio.c"
const void * const observed[] = {
 &effect_active,&effect_start,&effect_id,&creak_active,&creak_start,
 &motion_valid,&Bike.volt[0],&Bike.volt[1]
};
''')
    rom=out/'check.gbc'
    subprocess.run([str(BASE/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size',
                    '-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j',
                    '-I'+str(BASE/'src'),'-I'+str(gen),'-o',str(rom),
                    str(out/'driver.c'),str(out/'caller.c'),str(out/'observed_audio.c')],
                   check=True,capture_output=True,text=True)
    symbols={k:int(v,16) for k,v in re.findall(r'DEF (_\w+) 0x([\dA-Fa-f]+)',rom.with_suffix('.noi').read_text())}
    data=rom.read_bytes()
    address=symbols['_observed'];offset=(address>>16)*16384+(address&65535)-16384
    for i,name in enumerate(('effect_active','effect_start','effect_id','creak_active','creak_start',
                             'motion_valid','volt0','volt1')):
        symbols['_'+name]=int.from_bytes(data[offset+2*i:offset+2*i+2],'little')
    p=PyBoy(str(rom),window='null',sound_emulated=True,sound_sample_rate=48000,cgb=True)
    p.set_emulation_speed(0)
    cycles=[];starts=[];returns=set()
    def returned(_):
        if starts and starts[-1][0]==p.register_file.SP-2:
            _,start=starts.pop();cycles.append(p._cycles()-start)
    def entered(_):
        sp=p.register_file.SP;pc=p.memory[sp]+256*p.memory[sp+1]
        assert pc<0x4000
        if pc not in returns:p.hook_register(0,pc,returned,None);returns.add(pc)
        starts.append((sp,p._cycles()))
    p.hook_register(3,symbols['_audio_update']&65535,entered,None)
    def put(name,value,width=1):
        address=symbols['_'+name];p.memory[address:address+width]=list(int(value).to_bytes(width,'little',signed=value<0))
    def get(name,width=1):
        address=symbols['_'+name];return int.from_bytes(bytes(p.memory[address:address+width]),'little')
    def frames(count):
        chunks=[]
        for _ in range(count):
            size=get('native_size')
            bike=symbols['_Bike'];export=symbols['_gbc_bike']
            before=(bytes(p.memory[bike:bike+size])+bytes(p.memory[export:export+52])) if size and get('ready') else None
            p.tick(1,False);chunks.append(p.sound.ndarray.copy())
            if before is not None:
                after=bytes(p.memory[bike:bike+size])+bytes(p.memory[export:export+52])
                assert before==after,'audio modified a native or exported bike state'
        return np.concatenate(chunks)
    def pose(angle=0,compression=0,origin=0):
        # Rigid rotation of both wheels through every detector direction. Original
        # anchors are +/-0.85 m across and 0.6 m below the chassis.
        address=symbols['_gbc_bike']
        p.memory[address:address+52]=[0]*52
        p.memory[address:address+4]=list(int(origin*65536).to_bytes(4,'little',signed=True))
        p.memory[address+8:address+10]=list(angle.to_bytes(2,'little'))
        p.memory[address+50]=1
        for i,x in enumerate((-.85,.85)):
            depth=compression[i] if isinstance(compression,tuple) else compression
            y=-.6+depth
            radians=angle*math.tau/65536
            x,y=x*math.cos(radians)-y*math.sin(radians)+origin,x*math.sin(radians)+y*math.cos(radians)
            location=address+10+10*i
            p.memory[location:location+8]=list(int(x*65536).to_bytes(4,'little',signed=True)+int(y*65536).to_bytes(4,'little',signed=True))
    def reset(angle=0):
        put('reset_request',1);put('volt0',0);put('volt1',0);put('riding',1)
        pose(angle);frames(4)
        assert get('motion_valid') and not get('creak_active')
    report={}
    try:
        for _ in range(120):
            frames(1)
            if get('ready'):break
        assert get('ready')
        for angle in range(0,65536,2048):
            reset(angle)
            frames(24)
            assert not get('creak_active'),'stationary wheels creaked'
            pose(angle,-.2);frames(4)
            assert not get('creak_active'),'extending suspension creaked'
            pose(angle,.2);pcm=frames(4)
            assert get('creak_active'),'compression failed to creak'
            assert p.memory[0xff26]&7==7,'creak did not coexist with engine'
            onset=get('creak_start',2)
            pose(angle,.3);frames(4)
            assert get('creak_start',2)==onset,'continued compression restarted creak'
            frames(44)
            assert not get('creak_active'),'stationary compressed wheel restarted creak'
        report['compression_orientations_degrees']=list(np.arange(0,360,11.25))
        for wheel in (0,1):
            reset()
            pose(compression=(.2,0) if wheel==0 else (0,.2))
            frames(4)
            assert get('creak_active'),('one wheel compression missed',wheel)
        # Quantized relative coordinates must cross their modular boundary
        # without inventing compression from a rigid translation.
        for origin in (127.9,128.1,-128.1,-127.9):
            reset();pose(origin=origin);frames(8)
            assert not get('creak_active'),'world translation creaked'
            pose(compression=.2,origin=origin);frames(4)
            assert get('creak_active'),'compression across position wrap missed'
        reset()
        # Isolate each effect in APU routing while leaving engine generators
        # live, and inspect every non-silent source window at 30 Hz servicing.
        levels={}
        for effect,name,route in ((4,'creak',0x22),(5,'volt',0x88),(6,'turn',0x88)):
            p.memory[0xff25]=route
            put('fx',effect)
            active='creak_active' if effect==4 else 'effect_active'
            start='creak_start' if effect==4 else 'effect_start'
            chunks=[frames(2)];onset=get(start,2);seen={}
            while get(active):
                chunk=frames(1);chunks.append(chunk)
                age=(get('sys_time',2)-onset)&65535
                level=int(np.ptp(chunk[:,0].astype(np.int16)))
                if age%4 in (2,3):seen[age//4]=max(seen.get(age//4,0),level)
                assert age<64,'effect did not stop'
            for i,step in enumerate(manifest['effects'][name]['windows']):
                if step['volume']>=2 and manifest['effects'][name]['duration_vblanks']-4*i>=4:
                    assert seen.get(i,0)>0,(name,'silent source contour',i,seen)
            levels[name]=int(np.ptp(np.concatenate(chunks)[:,0].astype(np.int16)))
            assert levels[name]>=6
            frames(4)
        p.memory[0xff25]=0xff
        reset()
        put('volt0',7);frames(2)
        assert get('effect_id')==5 and get('effect_active'),'left volt not detected'
        onset=get('effect_start',2)
        put('volt0',6);frames(2)
        assert get('effect_start',2)==onset,'volt countdown retriggered sound'
        frames(22)
        put('volt1',7);frames(2)
        assert get('effect_id')==5 and get('effect_active'),'right volt not detected'
        assert p.memory[0xff26]&13==13,'volt stopped engine or missed CH4'
        frames(22)
        p.memory[symbols['_gbc_bike']+51]=1;frames(2)
        assert get('effect_id')==6 and get('effect_active'),'turn not detected'
        frames(58)
        # Lower-priority CH2 creak can coexist with CH4 volt, but an apple
        # replaces it and a finish/crash protects its own full contour.
        put('fx',4);frames(2);onset=get('creak_start',2)
        put('fx',5);frames(2)
        assert get('creak_active') and get('creak_start',2)==onset
        assert p.memory[0xff26]&15==15,'volt silenced independent creak'
        frames(22)
        put('fx',1);frames(2)
        assert not get('creak_active') and get('effect_id')==1
        put('fx',4);frames(2)
        assert not get('creak_active'),'creak interrupted apple'
        put('fx',3);frames(2);onset=get('effect_start',2)
        for effect in (4,5,6,0):put('fx',effect);frames(2)
        assert get('effect_id')==3 and get('effect_start',2)==onset,'effect interrupted finish'
        put('riding',0);frames(2)
        assert not p.memory[0xff26]&7,'riding channels survived stop'
        frames(50)
        reset();put('fx',4);frames(2);put('riding',0);frames(2)
        assert not get('creak_active'),'creak continued in pause'
        # Reset detection across pause; a pose changed while stopped must
        # not produce a synthetic landing or turn on resume.
        pose(16384,.3);put('riding',1);frames(4)
        assert not get('creak_active') and not get('effect_active')
        put('hold',1);frames(2);put('sys_time',65532,2)
        put('fx',4);put('hold',0);frames(4)
        assert get('creak_active'),'creak missing across VBlank clock wrap'
        frames(42)
        assert not get('creak_active'),'creak duration extended by clock wrap'
        assert get('banks_bad',2)==0 and get('irq_count',2)>100
        assert max(cycles)<10000,('unbounded motion/audio cost',max(cycles))
        report.update(status='passed',effect_pcm_peak_to_peak=levels,
                      max_audio_update_cycles=max(cycles), audio_update_percentiles=np.percentile(cycles,[0,25,50,75,95,100]).tolist(),bank_restore_failures=get('banks_bad',2),
                      physics_state_is_fixture=True,native_and_exported_states_unchanged=True,
                      clock_wrap_verified=True,hardware_tested=False)
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    finally:p.stop(save=False)


if __name__=='__main__':main()
