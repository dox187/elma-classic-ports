"""Compare complete native/HOST32-bit physics trajectories and wide freefall.

Warm Up completion comes from controller inputs and original object contacts.
The native fixture replays those inputs and compares109 internal +52 public
state bytes after every call; no completion/object state is injected.
"""
import argparse
import ctypes as C
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys

from pyboy import PyBoy

BASE=Path(__file__).resolve().parents[1]
# Resolve the sibling parser without depending on the working directory.
sys.path.insert(0,str(BASE.parent/'snes/tools'))
from elmadata import Resource,internal_levels


class Pose(C.Structure):
    _fields_=[('x',C.c_int32),('y',C.c_int32),('angle',C.c_uint16)]
class Public(C.Structure):
    _fields_=[('body',Pose),('wheel',Pose*2),('rider',Pose),('head',Pose),('alive',C.c_uint8),('turned',C.c_uint8)]
class Circle(C.Structure):
    _fields_=[('rx',C.c_int32),('ry',C.c_int32),('vx',C.c_int32),('vy',C.c_int32),('alfa',C.c_uint32),('omega',C.c_int16)]
class Bike(C.Structure):
    _fields_=[('body',Circle),('wheel',Circle*2),('rider_x',C.c_int32),('rider_y',C.c_int32),
              ('rider_vx',C.c_int32),('rider_vy',C.c_int32),('head_x',C.c_int32),('head_y',C.c_int32),
              ('turned',C.c_uint8),('gravity',C.c_uint8),('brake_was',C.c_uint8),('steps',C.c_uint8),
              ('gfrac',C.c_uint8),('dbrake',C.c_uint32*2),('volt',C.c_uint8*2),('voltomega',C.c_int16*2)]


def run(command,log):
    result=subprocess.run(list(map(str,command)),capture_output=True,text=True)
    log.write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(log.read_text())


def snapshot(b,p):
    out=bytearray()
    for k in(b.body,*b.wheel):out.extend(struct.pack('<iiiiIh',k.rx,k.ry,k.vx,k.vy,k.alfa,k.omega))
    out.extend(struct.pack('<iiiiii',b.rider_x,b.rider_y,b.rider_vx,b.rider_vy,b.head_x,b.head_y))
    out.extend(struct.pack('<BBBBBIIBBhh',b.turned,b.gravity,b.brake_was,b.steps,b.gfrac,
                           *b.dbrake,*b.volt,*b.voltomega))
    for k in(p.body,*p.wheel,p.rider,p.head):out.extend(struct.pack('<iiH',k.x,k.y,k.angle))
    out.extend(bytes((p.alive,p.turned)))
    assert len(out)==161
    return bytes(out)


def touch(p,obj):
    for k,radius in((p.wheel[0],819),(p.wheel[1],819),(p.head,653)):
        dx,dy=k.x-obj[0],k.y-obj[1]
        if abs(dx)<=52429 and abs(dy)<=52429 and (dx>>6)**2+(dy>>6)**2<=radius*radius:return True
    return False


def state_metrics(b,p,metrics):
    metrics['max_axle_m']=max(metrics['max_axle_m'],*(math.hypot(k.x-p.body.x,k.y-p.body.y)/65536 for k in p.wheel))
    metrics['max_rider_m']=max(metrics['max_rider_m'],math.hypot(p.rider.x-p.body.x,p.rider.y-p.body.y)/65536)
    metrics['max_linear_units']=max(metrics['max_linear_units'],*[abs(v)for k in(b.body,*b.wheel)for v in(k.vx,k.vy)],abs(b.rider_vx),abs(b.rider_vy))
    metrics['max_body_vertical_units']=max(metrics['max_body_vertical_units'],abs(b.body.vy))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--res',type=Path,required=True)
    parser.add_argument('--gen',type=Path,default=BASE/'build/gen')
    parser.add_argument('--out',type=Path,default=BASE/'build/physics-trace-check')
    parser.add_argument('--first-bank',type=int,default=252,help='first coefficient ROM bank (508 for the 8 MiB profile)')
    parser.add_argument('--reference-host',type=Path,help='also replay against a previously frozen HOST library')
    parser.add_argument('--sweep-source',type=Path,default=BASE/'src/physics_sweep.c',help='isolated exact sweep candidate')
    parser.add_argument('--collision-source',type=Path,default=BASE/'src/physics_collision.c',help='isolated exact cache candidate')
    args=parser.parse_args();gen=args.gen.resolve();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    common=[BASE/'src'/name for name in('physics.c','physics_core.c','physics_contacts.c','physics_math.c','physics_math32.c')]+[args.collision_source.resolve(),args.sweep_source.resolve()]
    data=[gen/'physics_level_data.c']+sorted(gen.glob('physics_bank_*.c'))
    (out/'host.c').write_text('#include "physics_core.h"\n#include "runtime.h"\n'
        'uint16_t fixture_internal_size(void){return sizeof(Bike);}\n'
        'uint16_t fixture_public_size(void){return sizeof(gbc_bike);}\n')
    run(['cc','-shared','-fPIC','-O0','-fwrapv','-Wno-unknown-pragmas','-I'+str(BASE/'src'),'-I'+str(gen),
         out/'host.c',*common,*data,'-o',out/'host.dylib'],out/'host-compile.log')
    f=C.CDLL(str(out/'host.dylib'));f.physics_step.argtypes=[C.c_uint8];f.physics_select_level.argtypes=[C.c_uint8]
    assert f.fixture_internal_size()==C.sizeof(Bike) and f.fixture_public_size()==C.sizeof(Public)
    b=Bike.in_dll(f,'Bike');p=Public.in_dll(f,'gbc_bike')
    constants=(gen/'riding_constants.h').read_text();rate=float(re.search(r'#define PH_RATE ([\d.]+)',constants)[1]);dt=.4368/rate
    assert int(re.search(r'#define PH_HZ (\d+)',constants)[1])==30,'this controller targets the30Hz profile'
    levels=internal_levels(Resource(args.res));objects=levels[0].objects
    obj=lambda kind:tuple(math.floor(v*65536+.5)for v in next(o[1:3]for o in objects if o[0]==kind))
    apple,flower=obj(2),obj(1)
    f.physics_select_level(0);f.physics_reset_current();f.physics_turn()
    def angle():return ((p.body.angle+32768)&65535)*2*math.pi/65536-math.pi
    expected=[[],[],[],[]];inputs=[];apple_step=None;turn_step=None;last_volt=-10000;previous=angle()
    metrics=[{'max_axle_m':0,'max_rider_m':0,'max_linear_units':0,'max_body_vertical_units':0}for _ in range(4)]
    for i in range(1600):
        a=angle();omega=((a-previous+math.pi)%(2*math.pi)-math.pi)/dt;previous=a
        k=1;score=a+(.025*omega if apple_step is None else 0)
        if i-last_volt>=28:
            if score>(.4 if apple_step is None else 0):k|=8;last_volt=i
            elif score<(-.4 if apple_step is None else 0):k|=4;last_volt=i
        if apple_step is not None and turn_step is None and i-apple_step>=60:f.physics_turn();turn_step=i
        f.physics_step(k);inputs.append(k);expected[0].append(snapshot(b,p));state_metrics(b,p,metrics[0])
        assert p.alive,'HOST Warm Up controller died at step%d'%i
        assert metrics[0]['max_axle_m']<3 and metrics[0]['max_rider_m']<3,'detached HOST bike'
        if apple_step is None and touch(p,apple):apple_step=i
        if apple_step is not None and touch(p,flower):break
    else:raise AssertionError('HOST controller did not earn Warm Up completion')
    f.physics_select_level(43);f.physics_reset_current();freefall_death=None
    for i in range(520):
        f.physics_step(0);expected[1].append(snapshot(b,p));state_metrics(b,p,metrics[1])
        if not p.alive and freefall_death is None:freefall_death=i
    assert metrics[1]['max_body_vertical_units']>32767,'Freefall did not exercise widened velocity'
    assert metrics[1]['max_axle_m']<3 and metrics[1]['max_rider_m']<3,'detached Freefall bike'
    brake_inputs=[1]*10+[2]*120+[1]*50+[2 if i%4<2 else 1 for i in range(60)]
    f.physics_select_level(0);f.physics_reset_current();f.physics_turn();brake_death=None
    for i,k in enumerate(brake_inputs):
        f.physics_step(k);expected[2].append(snapshot(b,p));state_metrics(b,p,metrics[2])
        if not p.alive and brake_death is None:brake_death=i
    assert metrics[2]['max_axle_m']<3 and metrics[2]['max_rider_m']<3,'detached braking bike'
    # Exercise cache invariants through the supported API transitions.
    f.physics_select_level(0);f.physics_reset_current();f.physics_turn()
    for i in range(160):
        if i%40==0:
            f.physics_select_level(43 if (i//40)&1 else 0);f.physics_reset_current()
        if i%13==5:f.physics_turn()
        if i%20==0:f.physics_set_gravity((i//20)%4+1)
        f.physics_step(1 if i%3==0 else 2)
        expected[3].append(snapshot(b,p));state_metrics(b,p,metrics[3])
    if args.reference_host:
        reference=C.CDLL(str(args.reference_host.resolve()))
        reference.physics_step.argtypes=[C.c_uint8];reference.physics_select_level.argtypes=[C.c_uint8]
        rb=Bike.in_dll(reference,'Bike');rp=Public.in_dll(reference,'gbc_bike')
        for case in range(4):
            reference.physics_select_level(43 if case==1 else 0);reference.physics_reset_current()
            if case!=1:reference.physics_turn()
            for i,want in enumerate(expected[case]):
                if case==0 and i==turn_step:reference.physics_turn()
                if case==3:
                    if i%40==0:
                        reference.physics_select_level(43 if (i//40)&1 else 0);reference.physics_reset_current()
                    if i%13==5:reference.physics_turn()
                    if i%20==0:reference.physics_set_gravity((i//20)%4+1)
                reference.physics_step(inputs[i] if case==0 else 0 if case==1 else brake_inputs[i] if case==2 else 1 if i%3==0 else 2)
                assert snapshot(rb,rp)==want,('reference model changed',case,i)
    (out/'inputs.json').write_text(json.dumps({'input_encoding':'runtime left4 right8','inputs':inputs,
        'return_turn_step':turn_step,'apple_step':apple_step,'finish_step':len(inputs)-1})+'\n')
    (out/'native.c').write_text('''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "runtime.h"
#include "physics_core.h"
uint8_t physics_select_level(uint8_t) GBC_BANKED;void physics_reset_current(void) GBC_BANKED;
typedef char core_layout[sizeof(bike_t)==109?1:-1];
typedef char public_layout[sizeof(gbc_bike_t)==52?1:-1];
volatile uint8_t fixture_case,fixture_done,fixture_ready,fixture_heartbeat,fixture_tock;
volatile uint16_t fixture_step;
uint8_t fixture_state[161];
void fixture_mark(void){++fixture_heartbeat;}
void fixture_after_step(void){++fixture_tock;}
const uint8_t inputs[]={'''+','.join(map(str,inputs))+'''};
const uint8_t brake_inputs[]={'''+','.join(map(str,brake_inputs))+'''};
void main(void){uint16_t i;uint8_t k;cpu_fast();fixture_ready=1;
 for(fixture_case=0;fixture_case<4;++fixture_case){
  physics_select_level(fixture_case==1?43:0);physics_reset_current();
  if(fixture_case!=1)physics_turn();
  for(i=0;i<(fixture_case==0?'''+str(len(inputs))+''':fixture_case==1?520:fixture_case==2?240:160);++i){
   if(!fixture_case && i=='''+str(turn_step)+''')physics_turn();
   if(fixture_case==3){
    if(i%40==0){physics_select_level((i/40)&1?43:0);physics_reset_current();}
    if(i%13==5)physics_turn();
    if(i%20==0)physics_set_gravity((i/20)%4+1);
   }
   k=fixture_case==0?inputs[i]:fixture_case==1?0:fixture_case==2?brake_inputs[i]:i%3==0?1:2;
   physics_step(k);fixture_after_step();
   memcpy(fixture_state,&Bike,109);memcpy(fixture_state+109,&gbc_bike,52);
   fixture_step=i;fixture_mark();vsync();
  }
 }
 fixture_done=1;while(1)vsync();}
''')
    assembly=[path for path in sorted((BASE/'src').glob('physics_*.s'))if path.name!='physics_mul16.s']
    if not (gen/'physics_sine_16.c').is_file():
        run([sys.executable,BASE/'tools/physics_sine.py','--out',gen],out/'sine-generate.log')
    run([sys.executable,BASE/'tools/math32_coefficients.py','--constants',gen/'riding_constants.h','--out',gen,'--first-bank',args.first_bank],out/'coefficient-generate.log')
    tables=sorted(gen.glob('physics_quarter_*.c'))+sorted(gen.glob('physics_scale_*.c'))+sorted(gen.glob('physics_sine_*.c'))
    tables+=sorted(gen.glob('physics_coefficient_*.c'))+[gen/'physics_coefficient_calls.s']
    rom=out/'native.gbc'
    run([BASE/'.toolchain/gbdk/bin/lcc','-msm83:gb','-Wf--opt-code-size','-Wf--max-allocs-per-node','-Wf100000',
         '-DRIDING_COEFFICIENT_LOOKUP','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(BASE/'src'),'-I'+str(gen),'-o',rom,
         out/'native.c',*common,*assembly,*data,*tables],out/'native-compile.log')
    symbols={key:int(value,16)for key,value in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',rom.with_suffix('.noi').read_text())}
    emu=PyBoy(str(rom),window='null',sound_emulated=False,cgb=True);emu.set_emulation_speed(0)
    seen=[0,0,0,0];observed=[set(),set(),set(),set()];duplicate_observations=[0];differences=[];timings=[[],[],[],[]];started=[None]
    def byte(name):return emu.memory[symbols['_fixture_'+name]]
    def enter(_):started[0]=emu._cycles()
    def after(_):
        if started[0]is not None:
            timings[byte('case')].append(emu._cycles()-started[0]);started[0]=None
    def mark(_):
        if not byte('ready'):return
        case=byte('case');a=symbols['_fixture_step'];step=emu.memory[a]+256*emu.memory[a+1]
        if case>=4 or step>=len(expected[case]):return
        a=symbols['_fixture_state'];actual=bytes(emu.memory[a:a+161]);want=expected[case][step]
        if actual!=want and len(differences)<5:
            differences.append({'case':case,'step':step,'first_byte':next(i for i in range(161)if actual[i]!=want[i]),
                                'actual':actual.hex(),'host':want.hex()})
        # An interrupt accepted before the hooked instruction may revisit
        # its PC without executing it twice. Count each physics snapshot once.
        if step in observed[case]:duplicate_observations[0]+=1;return
        observed[case].add(step);seen[case]+=1
    address=symbols['_physics_step'];emu.hook_register(address>>16,address&65535,enter,None)
    emu.hook_register(0,symbols['_fixture_after_step'],after,None)
    emu.hook_register(0,symbols['_fixture_mark'],mark,None)
    try:
        for _ in range(200):
            emu.tick(100,False)
            if byte('done'):break
        assert byte('done'),'native trajectory fixture did not finish'
        assert not differences,differences
        assert seen==list(map(len,expected)),seen
    finally:emu.stop(save=False)
    report={'state_bytes_per_step':161,'native_host_steps':seen,'observer_reentries':duplicate_observations[0],'differences':differences,
            'warmup':dict(metrics[0],apple_step=apple_step,finish_step=len(inputs)-1),
            'freefall':dict(metrics[1],first_death=freefall_death),
            'braking':dict(metrics[2],first_death=brake_death),
            'api_transitions':dict(metrics[3],steps=160,resets=4,gravity_changes=8),
            'physics_call_cycles':[{'min':min(t),'mean':sum(t)/len(t),'max':max(t),'max_step':t.index(max(t))}for t in timings]}
    (out/'cycles.json').write_text(json.dumps(timings)+'\n')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
