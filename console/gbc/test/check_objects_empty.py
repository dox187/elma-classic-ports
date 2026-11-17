"""Native differential object-cache check against a frozen pre-cache C loop.

Builds an isolated test ROM; never writes generated game data or builds the game.
The default 1,094 scene pairs cover counts 0..64, eligibility/effect order,
signed extremes, stale-cache invalidation, fractions, and enabled interrupts.
Also checks 12,544 clipping cases and 729 saturating bike-bound combinations.
--haircut-scenes optionally adds the private 132-pair captured timing sequence.
"""
import argparse
import hashlib
import json
import re
import statistics
import subprocess
from pathlib import Path
from pyboy import PyBoy

BASE = next(p for p in Path(__file__).resolve().parents
            if (p / 'src/play.c').is_file() and (p / 'src/world.h').is_file())

COMMON = r'''
#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "runtime.h"
#include "world.h"
#include "audio.h"
#include "save.h"
#define OBJECT_COUNT (game_world.object_count)
#define level_objects game_objects
#define DEAD 1
#define FINISHED 2
extern volatile uint8_t game_state,game_apples_left,game_player_index,game_level_index,game_new_record;
extern volatile uint32_t game_previous_best,game_time_frames;
extern __at(0xc5f0) uint8_t game_object_active[64];
extern uint8_t objects_empty_valid,objects_empty_apples;
extern uint16_t gbc_objects_empty_bounds[4];
uint8_t gbc_object_touch(const gbc_pose_t*,const game_object_t*,uint8_t) __sdcccall(0);
uint8_t gbc_object_touch_native(const gbc_pose_t*,const game_object_t*,uint8_t) __sdcccall(0);
void gbc_objects_bounds(uint16_t*) __sdcccall(0);
uint8_t gbc_object_near(const game_object_t*,const uint16_t*) __sdcccall(0);
uint8_t gbc_objects_next(uint8_t,const uint16_t*) __sdcccall(0);
void baseline_check(void) BANKED;
void fast_check(void) BANKED;

uint8_t gbc_object_near_baseline(const game_object_t*,const uint16_t*) __sdcccall(0);
'''

ORACLE = r'''
#include "common.h"
#pragma bank 5
void baseline_check(void) BANKED {
    uint8_t i,hit,use_bounds=OBJECT_COUNT>4;
    uint16_t bounds[4];
    const game_object_t *object;
    /* Every collision radius is below one meter. Its object's integer
     * coordinate must lie within the three physical circles' integer bounds
     * expanded by one. Dense courses avoid three full tests per distant item. */
    if(use_bounds)gbc_objects_bounds(bounds);
    for(i=0,object=level_objects;i<OBJECT_COUNT;++i,++object) {
        if(!game_object_active[i] || (object->kind==1 && game_apples_left))continue;
        if(use_bounds && !gbc_object_near_baseline(object,bounds))continue;
        hit=gbc_object_touch(&gbc_bike.wheel[0],object,0)
            || gbc_object_touch(&gbc_bike.wheel[1],object,0)
            || gbc_object_touch(&gbc_bike.head,object,1);
        if(!hit)continue;
        if(object->kind==2) {
            game_object_active[i]=0;
            if(game_apples_left)--game_apples_left;
            if(object->gravity)physics_set_gravity(object->gravity);
            audio_effect(FX_APPLE);
        } else if(object->kind==1 && !game_apples_left)game_state=FINISHED;
        else if(object->kind==3){gbc_bike.alive=0;game_state=DEAD;audio_effect(FX_CRASH);}
    }
    if(game_state==FINISHED) {
        audio_update(0,0,0,0);
        game_previous_best=save_best(game_player_index,game_level_index);
        game_new_record=save_record(game_player_index,game_level_index,game_time_frames);
    }
}
'''

ORACLE_NEAR = r'''
.module oracle_near
.area _CODE_5
; Inclusive coarse rectangle. ABI0 object@2,bounds@4; E=boolean.
_gbc_object_near_baseline::
 ldhl sp,#2
 ld a,(hl+)
 ld d,(hl)
 add a,#7
 ld e,a
 jr nc,object_x_ptr_baseline
 inc d
object_x_ptr_baseline:
 ld a,(de)
 ld c,a
 inc de
 ld a,(de)
 xor a,#0x80
 ld b,a
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push de
 call inside_axis_baseline
 pop de
 or a,a
 jr z,object_outside_baseline
 inc hl
 ld a,e
 add a,#3
 ld e,a
 jr nc,object_y_ptr_baseline
 inc d
object_y_ptr_baseline:
 ld a,(de)
 ld c,a
 inc de
 ld a,(de)
 xor a,#0x80
 ld b,a
 call inside_axis_baseline
 ld e,a
 ret
object_outside_baseline:
 ld e,#0
 ret
inside_axis_baseline:
 ld a,c
 sub a,(hl)
 inc hl
 ld a,b
 sbc a,(hl)
 jr c,axis_outside_baseline
 inc hl
 ld a,(hl+)
 sub a,c
 ld a,(hl)
 sbc a,b
 jr c,axis_outside_baseline
 ld a,#1
 ret
axis_outside_baseline:
 xor a
 ret
'''

DRIVER = r'''
#include "common.h"
world_level_t game_world;game_object_t game_objects[64];gbc_bike_t gbc_bike;
__at(0xc5f0) uint8_t game_object_active[64];
volatile uint8_t game_state,game_apples_left,game_player_index,game_level_index,game_new_record;
volatile uint32_t game_previous_best,game_time_frames;
uint16_t events[256],event_count;uint8_t gravity;
uint8_t original_active[64],expected_active[64],expected_bike[52],snapshot[981];uint16_t expected_events[256],expected_event_count;
uint8_t expected_state,expected_apples,expected_gravity,expected_record;uint32_t expected_best;
volatile uint8_t done,irq_phase,case_mode,case_step;volatile uint16_t completed,failures,scan_failures,guard_failures,bank_failures,irq_failures,irq_ticks;
typedef char object_layout[sizeof(game_object_t)==14&&offsetof(game_object_t,kind)==4&&offsetof(game_object_t,world_x)==5&&offsetof(game_object_t,world_y)==9?1:-1];
typedef char world_layout[sizeof(world_level_t)==33&&offsetof(world_level_t,object_count)==32?1:-1];
extern const uint8_t haircut_game_world[33],haircut_game_objects[896],haircut_game_object_active[64],haircut_gbc_bike[52],haircut_apples,haircut_steps[100][117];
void audio_effect(uint8_t id) BANKED {events[event_count++]=0x100+id;}
void audio_update(uint8_t a,uint8_t b,uint8_t c,uint16_t d) BANKED {events[event_count++]=0x200;}
void physics_set_gravity(uint8_t d) BANKED {events[event_count++]=0x300+d;if(d>=1&&d<=4)gravity=d-1;}
uint32_t save_best(uint8_t p,uint8_t l) BANKED {events[event_count++]=0x400;return 123456L;}
uint8_t save_record(uint8_t p,uint8_t l,uint32_t t) BANKED {events[event_count++]=0x401;return 1;}
static uint16_t state;
static uint16_t rnd(void){state=(uint16_t)(state*25173u+13849u);return state;}
static const int16_t edge[]={-32768,-32767,-1024,-1,0,1,1024,32766,32767};
static void setup(uint16_t seed,uint8_t mode,uint8_t n){uint8_t i;int16_t x,y;uint16_t q;
 if(mode<4||!seed)objects_empty_valid=0;
 state=seed;memset(&game_world,0x5a,sizeof(game_world));game_world.object_count=n;memset(&gbc_bike,0xa5,52);
 x=mode==2?edge[seed%9]:10;y=mode==2?edge[(seed/9)%9]:12;
 gbc_bike.head.x=((int32_t)x<<16)+12345;gbc_bike.head.y=((int32_t)y<<16)+22222;
 gbc_bike.wheel[0].x=gbc_bike.head.x;gbc_bike.wheel[0].y=gbc_bike.head.y;
 gbc_bike.wheel[1].x=gbc_bike.head.x;gbc_bike.wheel[1].y=gbc_bike.head.y;gbc_bike.alive=1;
 memset(game_objects,0x39,sizeof(game_objects));game_apples_left=0;
 for(i=0;i<64;++i){game_object_t *o=game_objects+i;
  q=rnd();game_object_active[i]=(q&3)?(uint8_t)(q|1):0;o->kind=1+rnd()%3;o->gravity=rnd()%7;
  o->world_x=(int32_t)(int16_t)rnd()*65536L+(uint16_t)rnd();o->world_y=(int32_t)(int16_t)rnd()*65536L+(uint16_t)rnd();
  if(mode==0){o->world_x=(int32_t)(x+100+i)*65536L;o->world_y=(int32_t)y*65536L;game_object_active[i]=1;}
  if(mode==1){o->world_x=gbc_bike.head.x+(int16_t)rnd()*2L;o->world_y=gbc_bike.head.y+(int16_t)rnd()*2L;}
  if(mode==2){o->world_x=(int32_t)edge[(i+seed)%9]*65536L+(uint16_t)rnd();o->world_y=(int32_t)edge[(i/9+seed)%9]*65536L+(uint16_t)rnd();}
  if(mode==3){o->world_x=gbc_bike.head.x;o->world_y=gbc_bike.head.y;game_object_active[i]=1;o->kind=2;o->gravity=1+(i&3);}
  if(i<n&&game_object_active[i]&&o->kind==2)++game_apples_left;
 }
 if(mode==3&&n){game_objects[n-1].kind=(seed&1)?1:3;--game_apples_left;if(n>2&&(seed&2))game_objects[1].kind=1;}
#ifdef WITH_HAIRCUT
 if(mode==4||mode==5){SWITCH_ROM(1);memcpy(&game_world,haircut_game_world,33);memcpy(game_objects,haircut_game_objects,896);memcpy(game_object_active,haircut_game_object_active,64);memcpy(&gbc_bike,haircut_gbc_bike,52);game_apples_left=haircut_apples;}
 if(mode==5){memcpy(&gbc_bike,haircut_steps[seed],52);memcpy(game_object_active,haircut_steps[seed]+52,64);game_apples_left=haircut_steps[seed][116];}
#endif
 if(mode>=6){
  for(i=0;i<64;++i){game_object_active[i]=0;game_objects[i].kind=2;game_objects[i].world_x=100L*65536L;game_objects[i].world_y=100L*65536L;}
  game_object_active[0]=1;game_objects[0].kind=1;game_objects[0].world_x=10L*65536L+12345;game_objects[0].world_y=12L*65536L+22222;
  game_apples_left=mode==6?(seed?0:1):0;
  if(mode==7){gbc_bike.head.x=gbc_bike.wheel[0].x=gbc_bike.wheel[1].x=(seed?10L:20L)*65536L+12345;}
  if(mode==8){game_objects[0].world_x=11L*65536L+60000;gbc_bike.head.x=gbc_bike.wheel[0].x=gbc_bike.wheel[1].x=11L*65536L+(seed?60000:0);}
 }
 memcpy(original_active,game_object_active,64);memcpy(snapshot,&game_world,33);memcpy(snapshot+33,game_objects,896);memcpy(snapshot+929,&gbc_bike,52);
 game_state=0;game_previous_best=0;game_new_record=0;game_time_frames=360;gravity=2;event_count=0;case_mode=mode;case_step=seed+1;
}
static void run_case(uint16_t seed,uint8_t mode,uint8_t n){uint8_t start_apples,i;uint16_t x,y;
 setup(seed,mode,n);if(!irq_phase){SWITCH_ROM(5);IE_REG=31;IF_REG=4;}start_apples=game_apples_left;
 baseline_check();memcpy(expected_active,game_object_active,64);memcpy(expected_bike,&gbc_bike,52);expected_event_count=event_count;memcpy(expected_events,events,event_count*2u);
 expected_state=game_state;expected_apples=game_apples_left;expected_gravity=gravity;expected_record=game_new_record;expected_best=game_previous_best;
 memcpy(game_object_active,original_active,64);memcpy(&gbc_bike,snapshot+929,52);game_state=0;game_apples_left=start_apples;gravity=2;event_count=0;game_new_record=0;game_previous_best=0;
 fast_check();if(memcmp(expected_active,game_object_active,64)||memcmp(expected_bike,&gbc_bike,52)||expected_event_count!=event_count||memcmp(expected_events,events,event_count*2u)||expected_state!=game_state||expected_apples!=game_apples_left||expected_gravity!=gravity||expected_record!=game_new_record||expected_best!=game_previous_best)++failures;
 if(objects_empty_valid){for(i=0;i<game_world.object_count;++i){
  if(!game_object_active[i]||(game_objects[i].kind==1&&game_apples_left))continue;
  x=(uint16_t)((uint32_t)game_objects[i].world_x>>16)^0x8000U;y=(uint16_t)((uint32_t)game_objects[i].world_y>>16)^0x8000U;
  if(x>=gbc_objects_empty_bounds[0]&&x<=gbc_objects_empty_bounds[1]&&y>=gbc_objects_empty_bounds[2]&&y<=gbc_objects_empty_bounds[3])++guard_failures;
 }}
 if(memcmp(snapshot,&game_world,33)||memcmp(snapshot+33,game_objects,896))++guard_failures;
 if(!irq_phase){if(CURRENT_BANK!=5)++bank_failures;if(IE_REG!=31||(IF_REG&31)!=4)++irq_failures;}
 ++completed;
}
volatile uint16_t helper_cases,helper_failures,bounds_cases,bounds_failures;
static const uint16_t intervals[8][2]={{0,0},{0,1},{0,65535U},{1,1},{32767,32768U},{65534U,65535U},{65535U,65535U},{12345,54321U}};
static const uint16_t coordinates[]={0,1,2,12344,12345,12346,32767,32768U,54320U,54321U,54322U,65533U,65534U,65535U};
static void direct_helpers(void){uint8_t a,b,c,d,k,near;uint16_t bounds[4],expect[4],x,y,z,min,max;int16_t v[3];
 SWITCH_ROM(5);
 for(a=0;a<8;++a)for(b=0;b<8;++b){
  bounds[0]=intervals[a][0];bounds[1]=intervals[a][1];bounds[2]=intervals[b][0];bounds[3]=intervals[b][1];
  expect[0]=expect[2]=gbc_objects_empty_bounds[0]=gbc_objects_empty_bounds[2]=0;
  expect[1]=expect[3]=gbc_objects_empty_bounds[1]=gbc_objects_empty_bounds[3]=65535U;
  for(c=0;c<14;++c)for(d=0;d<14;++d){
   x=coordinates[c];y=coordinates[d];
   game_objects[0].world_x=(int32_t)(int16_t)(x^0x8000U)*65536L;
   game_objects[0].world_y=(int32_t)(int16_t)(y^0x8000U)*65536L;
   near=x>=bounds[0]&&x<=bounds[1]&&y>=bounds[2]&&y<=bounds[3];
   if(x<bounds[0]){z=x+1;if(z>expect[0])expect[0]=z;}
   else if(x>bounds[1]){z=x-1;if(z<expect[1])expect[1]=z;}
   else if(y<bounds[2]){z=y+1;if(z>expect[2])expect[2]=z;}
   else if(y>bounds[3]){z=y-1;if(z<expect[3])expect[3]=z;}
   if(gbc_object_near(game_objects,bounds)!=near||memcmp(expect,gbc_objects_empty_bounds,8))++helper_failures;
   ++helper_cases;
  }
 }
 for(a=0;a<9;++a)for(b=0;b<9;++b)for(c=0;c<9;++c){
  v[0]=edge[a];v[1]=edge[b];v[2]=edge[c];
  gbc_bike.head.x=(int32_t)v[0]*65536L;gbc_bike.head.y=(int32_t)v[2]*65536L;
  gbc_bike.wheel[0].x=(int32_t)v[1]*65536L;gbc_bike.wheel[0].y=(int32_t)v[0]*65536L;
  gbc_bike.wheel[1].x=(int32_t)v[2]*65536L;gbc_bike.wheel[1].y=(int32_t)v[1]*65536L;
  min=65535U;max=0;for(k=0;k<3;++k){z=(uint16_t)v[k]^0x8000U;if(z<min)min=z;if(z>max)max=z;}
  if(min)--min;if(max<65535U)++max;
  gbc_objects_bounds(bounds);if(bounds[0]!=min||bounds[1]!=max||bounds[2]!=min||bounds[3]!=max)++bounds_failures;
  ++bounds_cases;
 }
}

void main(void){uint16_t i,start;uint8_t mode,n;disable_interrupts();DISPLAY_OFF;cpu_fast();TAC_REG=0;SC_REG=0;
 direct_helpers();
 for(mode=0;mode<4;++mode)for(i=0;i<256;++i)run_case(i*277u+mode,mode,(uint8_t)(i%65));
#ifdef WITH_HAIRCUT
 for(i=0;i<32;++i)run_case(i,4,51);
 for(i=0;i<100;++i)run_case(i,5,51);
#endif
 for(mode=6;mode<=8;++mode)for(i=0;i<2;++i)run_case(i,mode,8);
 irq_phase=1;IE_REG=VBL_IFLAG;IF_REG=0;DISPLAY_ON;enable_interrupts();start=sys_time;
 for(i=0;i<64;++i)run_case(i,1,64);
 irq_ticks=sys_time-start;if(!irq_ticks||IE_REG!=VBL_IFLAG)++irq_failures;
 done=1;while(1)vsync();}
'''

TOUCH_WRAPPER = r'''
extern uint16_t events[256],event_count;
uint8_t gbc_object_touch(const gbc_pose_t *p,const game_object_t *o,uint8_t head) __sdcccall(0){
 events[event_count++]=(uint16_t)(o-game_objects)*4u+(head?2:p==&gbc_bike.wheel[1]?1:0);
 return gbc_object_touch_native(p,o,head);
}
'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=BASE / 'build/objects-empty-check')
    parser.add_argument('--gen', type=Path, default=BASE / 'build/gen-8m')
    parser.add_argument('--play', type=Path, default=BASE / 'src/play.c')
    parser.add_argument('--bounds', type=Path, default=BASE / 'src/objects_bounds_fast.s')
    parser.add_argument('--lcc', type=Path, default=BASE / '.toolchain/gbdk/bin/lcc')
    parser.add_argument('--haircut-scenes', type=Path)
    args = parser.parse_args()
    OUT = args.out.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    gen = args.gen.resolve()
    src = args.play.read_text()
    start = src.index('static void check_objects(void) BANKED {')
    candidate = src[start:src.index('\nuint8_t gbc_bike_bounded', start)]
    candidate = candidate.replace('static void check_objects', 'void fast_check', 1)
    declarations = []
    for pattern in (r'static uint8_t objects_empty_valid,objects_empty_apples;',
                    r'uint16_t gbc_objects_empty_bounds\[4\];'):
        match = re.search(pattern, src)
        if not match:
            raise SystemExit('Expected fused empty-cache declaration missing in ' + str(args.play))
        declarations.append(match[0].replace('static ', ''))
    (OUT / 'common.h').write_text(COMMON)
    (OUT / 'oracle_check.c').write_text(ORACLE)
    (OUT / 'oracle_near.s').write_text(ORACLE_NEAR)
    (OUT / 'driver.c').write_text(DRIVER)
    (OUT / 'checks.c').write_text('#include "common.h"\n#pragma bank 5\n' +
                                  '\n'.join(declarations) + '\n' + candidate + TOUCH_WRAPPER)
    (OUT / 'touch.s').write_text((BASE / 'src/objects_touch_fast.s').read_text().replace(
        '_gbc_object_touch::', '_gbc_object_touch_native::'))
    fixture_sources = []
    if args.haircut_scenes:
        scenes = json.loads(args.haircut_scenes.read_text())
        assert [s['step'] for s in scenes[:100]] == list(range(1, 101))
        scene = scenes[77]
        fixtures = '#include <stdint.h>\n#pragma bank 1\n'
        for name, length in [('game_world', 33), ('game_objects', 896),
                             ('game_object_active', 64), ('gbc_bike', 52)]:
            data = bytes.fromhex(scene[name])
            assert len(data) == length
            fixtures += 'const uint8_t haircut_' + name + '[%d]={' % length
            fixtures += ','.join(map(str, data)) + '};\n'
        fixtures += 'const uint8_t haircut_apples=%d;\n' % scene['apples']
        fixtures += 'const uint8_t haircut_steps[100][117]={\n'
        fixtures += ',\n'.join('{' + ','.join(map(str, bytes.fromhex(s['gbc_bike']) +
                    bytes.fromhex(s['game_object_active']) + bytes([s['apples']]))) + '}'
                    for s in scenes[:100]) + '\n};\n'
        (OUT / 'fixtures.c').write_text(fixtures)
        fixture_sources.append(OUT / 'fixtures.c')
    tables = sorted(gen.glob('physics_quarter_*.c')) + sorted(gen.glob('physics_scale_*.c'))
    assert tables, 'No generated physics tables in ' + str(gen)
    sources = [OUT / 'driver.c', OUT / 'checks.c', OUT / 'oracle_check.c',
               OUT / 'oracle_near.s', *fixture_sources, OUT / 'touch.s', args.bounds,
               BASE / 'src/physics_mul_fast.s', BASE / 'src/physics_kmul_fast.s', *tables]
    cmd = [str(args.lcc), '-msm83:gb', '-Wf--opt-code-size', '-Wf--max-allocs-per-node',
           '-Wf100000', '-Wm-yC', '-Wm-yt0x19', '-Wm-yoA', '-Wl-m', '-Wl-j',
           '-Wl-b_DATA=0xc700', '-I' + str(OUT), '-I' + str(BASE / 'src'),
           '-I' + str(gen)]
    if args.haircut_scenes:
        cmd.append('-DWITH_HAIRCUT')
    cmd += ['-o', str(OUT / 'check.gbc'), *map(str, sources)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    (OUT / 'compile.log').write_text(result.stdout + result.stderr)
    assert not result.returncode, result.stdout + result.stderr
    sy={n:int(v,16)for n,v in re.findall(r'DEF (_\w+) 0x([0-9a-fA-F]+)',(OUT/'check.noi').read_text())}
    p=PyBoy(str(OUT/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0);active=[];returns=set();timing={'baseline':[],'fast':[]}
    def returned(key):
     if not active or active[-1]['key']!=key or active[-1]['sp']+2!=p.register_file.SP:return
     call=active.pop();call['cycles']=p._cycles()-call.pop('start');call.pop('key');call.pop('sp');kind=call.pop('kind')
     if not call.pop('irq'):timing[kind].append(call)
    def entered(kind):
     sp=p.register_file.SP;ret=p.memory[sp]+256*p.memory[sp+1];key=(0 if ret<0x4000 else p.memory[sy['__current_bank']],ret)
     if key not in returns:p.hook_register(*key,returned,key);returns.add(key)
     active.append({'kind':kind,'key':key,'sp':sp,'start':p._cycles(),'irq':p.memory[sy['_irq_phase']],'mode':p.memory[sy['_case_mode']],'count':p.memory[sy['_game_world']+32],'step':p.memory[sy['_case_step']]})
    for kind,name in [('baseline','_baseline_check'),('fast','_fast_check')]:a=sy[name];p.hook_register(a>>16,a&65535,entered,kind)
    try:
     for _ in range(300):
      p.tick(100,False)
      if p.memory[sy['_done']]:break
     def n(name,size=2):a=sy['_'+name];return int.from_bytes(bytes(p.memory[a:a+size]),'little')
     report={name:n(name)for name in ['completed','failures','scan_failures','guard_failures','bank_failures','irq_failures','irq_ticks','helper_cases','helper_failures','bounds_cases','bounds_failures']};report['done']=n('done',1);report['api_cycles']={};report['extra_ram_bytes']=10;report['optional_haircut']=bool(args.haircut_scenes)
     for kind,records in timing.items():
      report['api_cycles'][kind]={}
      for label in ['all','far51','haircut78','haircut78_warm','haircut_sequence','haircut_sequence78','dense_near64','sparse']:
       v=[x['cycles']for x in records if label=='all' or label=='far51' and x['mode']==0 and x['count']==51 or label=='haircut78' and x['mode']==4 or label=='haircut78_warm' and x['mode']==4 and x is not next(y for y in records if y['mode']==4) or label=='haircut_sequence' and x['mode']==5 or label=='haircut_sequence78' and x['mode']==5 and x['step']==78 or label=='dense_near64' and x['mode']==1 and x['count']==64 or label=='sparse' and x['count']<=4]
       if not v:continue
       report['api_cycles'][kind][label]={'calls':len(v),'min':min(v),'max':max(v),'mean':statistics.mean(v)}
     report['sources']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [args.play,args.bounds,BASE/'src/objects_touch_fast.s',Path(__file__)]}
     (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');(OUT/'calls.json').write_text(json.dumps(timing,indent=2)+'\n');print(json.dumps(report,indent=2))
     assert report['done'] and report['completed']==(1226 if args.haircut_scenes else 1094) and report['helper_cases']==12544 and report['bounds_cases']==729 and not any(report[k]for k in ['failures','scan_failures','guard_failures','bank_failures','irq_failures','helper_failures','bounds_failures'])
    finally:p.stop(save=False)

if __name__ == "__main__":
    main()
