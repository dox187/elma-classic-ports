"""Native batched object OAM against an independent model and scalar helper.

Covers counts0..13, all kinds,64 object IDs, phase wrap, cameras/coordinates,
right-first priority, untouched sprites/globals, bank and IRQ preservation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess
from pyboy import PyBoy
BASE=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assembly',type=Path,default=BASE/'src/objects_draw_fast.s');p.add_argument('--out',type=Path,default=BASE/'build/objects-draw-check');p.add_argument('--lcc',type=Path,default=BASE/'.toolchain/gbdk/bin/lcc');a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    old=BASE/'src/object16.s';header=BASE/'src/world.h';sha={path.name:hashlib.sha256(path.read_bytes()).hexdigest()for path in(a.assembly,old,header)}
    fields=re.search(r'typedef struct\s*\{(.*?)\}\s*game_object_t;',header.read_text(),re.S)[1]
    (out/'object_type.h').write_text('#include <stdint.h>\ntypedef struct{'+fields+'}game_object_t;\n')
    r=random.Random(146413);cases=[]
    for visible in(1,2,7,13,14,31,64):
        for n in range(14):
            for phase in(0,visible-1):
                for right in(0,1):cases.append((visible,phase,n,right,r.randrange(65536),r.randrange(65536),r.randrange(65536)))
    cases += [(0,0,0,right,65535,65535,12345)for right in(0,1)]
    for _ in range(512):
        visible=r.randrange(1,65);cases.append((visible,r.randrange(visible),r.randrange(14),r.randrange(2),r.randrange(65536),r.randrange(65536),r.randrange(65536)))
    (out/'vectors.h').write_text('#include <stdint.h>\ntypedef struct{uint8_t visible,phase,n,right;uint16_t camx,camy,seed;} draw_case_t;\nextern const draw_case_t draw_cases[];\nextern const uint8_t objects_bank_tag[];\n#define CASES %d\n'%len(cases))
    (out/'vectors.c').write_text('#include "vectors.h"\n#pragma bank 5\nconst draw_case_t draw_cases[]={\n'+',\n'.join('{%d,%d,%d,%d,%du,%du,%du}'%row for row in cases)+'\n};\nconst uint8_t objects_bank_tag[]={0x5d};\n')
    driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "object_type.h"
#include "vectors.h"
uint8_t gbc_objects_draw(const uint8_t*,uint8_t,uint8_t,uint8_t,uint8_t) __sdcccall(0);
void gbc_video_object16(uint8_t,uint8_t,uint8_t,uint8_t,uint8_t) __sdcccall(0);
game_object_t game_objects[64];uint16_t game_camera_x,game_camera_y;
uint8_t visible_arena[192],expected[160],snapshot[1092];
volatile uint8_t objects_done,objects_irq_phase;
volatile uint16_t objects_cases,objects_case_index,fast_failures,baseline_failures,global_failures,bank_failures,irq_failures,irq_ticks;
typedef char object_size[sizeof(game_object_t)==14&&offsetof(game_object_t,x)==0&&offsetof(game_object_t,y)==2&&offsetof(game_object_t,kind)==4?1:-1];
typedef char case_size[sizeof(draw_case_t)==10?1:-1];
static void initialize(uint16_t seed){uint16_t i;uint8_t *raw=(uint8_t*)game_objects;
 for(i=0;i<896;++i)raw[i]=(uint8_t)(seed*17u+i*37u+(i>>3));
 for(i=0;i<64;++i){game_objects[i].kind=(uint8_t)((seed+i)&3);if((seed&128)&&!(i&7))game_objects[i].kind=255;}
 for(i=0;i<192;++i)visible_arena[i]=(uint8_t)(0xa5u^i^seed);
}
static void reset_oam(uint16_t seed){uint8_t i;for(i=0;i<160;++i)((uint8_t*)shadow_OAM)[i]=expected[i]=(uint8_t)(0x5du^i^seed);}
static void save_globals(void){memcpy(snapshot,game_objects,896);memcpy(snapshot+896,visible_arena,192);memcpy(snapshot+1088,&game_camera_x,2);memcpy(snapshot+1090,&game_camera_y,2);}
static void check_globals(void){if(memcmp(snapshot,game_objects,896)||memcmp(snapshot+896,visible_arena,192)||memcmp(snapshot+1088,&game_camera_x,2)||memcmp(snapshot+1090,&game_camera_y,2))++global_failures;}
static uint8_t model(const uint8_t *visible,uint8_t count,uint8_t phase,uint8_t n,uint8_t right){uint8_t i,j,id,column,x,y,tile,prop;uint16_t offset;
 if(!count||!n)return 13;
 for(i=0;i<n;++i){id=visible[(phase+i)%count];x=(uint8_t)((int16_t)game_objects[id].x-game_camera_x);y=(uint8_t)((int16_t)game_objects[id].y-game_camera_y+8);
 if(game_objects[id].kind==3){tile=252;prop=5;}else if(game_objects[id].kind==2){tile=248;prop=9;}else{tile=252;prop=10;}
 for(j=0;j<2;++j){column=j^right;offset=(13u+2u*i+j)*4u;expected[offset]=y;expected[offset+1]=x+column*8u;expected[offset+2]=tile+column*2u;expected[offset+3]=prop;}}
 return 13+2*n;
}
uint8_t baseline_objects(const uint8_t *visible,uint8_t count,uint8_t phase,uint8_t n,uint8_t right) __sdcccall(0){uint8_t i,index=phase,sprite=13,tile,prop;int16_t x,y;const game_object_t *object;
 if(!count||!n)return 13;
 for(i=0;i<n;++i){object=&game_objects[visible[index]];x=(int16_t)object->x-game_camera_x;y=(int16_t)object->y-game_camera_y+8;
 if(object->kind==3){tile=252;prop=5;}else if(object->kind==2){tile=248;prop=9;}else{tile=252;prop=10;}
 gbc_video_object16(sprite,(uint8_t)x,(uint8_t)y,tile|right,prop);sprite+=2;if(++index==count)index=0;}
 return sprite;
}
void main(void){uint16_t c,start;uint8_t j,pos,want,got;uint8_t *visible;const draw_case_t *v;
 disable_interrupts();DISPLAY_OFF;cpu_fast();TAC_REG=0;SC_REG=0;SWITCH_ROM(5);
 for(c=0;c<CASES;++c){objects_case_index=c;v=&draw_cases[c];initialize(v->seed);game_camera_x=v->camx;game_camera_y=v->camy;pos=(uint8_t)((c*23u)%128u);visible=visible_arena+pos;
 for(j=0;j<64;++j)visible[j]=(uint8_t)((j*((v->seed&63)|1)+(v->seed>>6))&63);
 save_globals();reset_oam(v->seed);want=model(visible,v->visible,v->phase,v->n,v->right);IE_REG=31;IF_REG=4;
 got=gbc_objects_draw(visible,v->visible,v->phase,v->n,v->right);
 if(got!=want||memcmp(expected,(const uint8_t*)shadow_OAM,160))++fast_failures;
 if(IE_REG!=31||(IF_REG&31)!=4)++irq_failures;check_globals();
 if(CURRENT_BANK!=5||*(const volatile uint8_t*)objects_bank_tag!=0x5d)++bank_failures;
 reset_oam(v->seed);want=model(visible,v->visible,v->phase,v->n,v->right);
 got=baseline_objects(visible,v->visible,v->phase,v->n,v->right);
 if(got!=want||memcmp(expected,(const uint8_t*)shadow_OAM,160))++baseline_failures;check_globals();
 if(CURRENT_BANK!=5||*(const volatile uint8_t*)objects_bank_tag!=0x5d)++bank_failures;
 ++objects_cases;
 }
 objects_irq_phase=1;IE_REG=VBL_IFLAG;IF_REG=0;DISPLAY_ON;enable_interrupts();start=sys_time;
 for(c=0;c<512;++c){memcpy(expected,(const uint8_t*)shadow_OAM,160);model(visible,64,c&63,13,c&1);
 if(gbc_objects_draw(visible,64,c&63,13,c&1)!=39||memcmp(expected,(const uint8_t*)shadow_OAM,160))++fast_failures;
 if(CURRENT_BANK!=5||*(const volatile uint8_t*)objects_bank_tag!=0x5d)++bank_failures;}
 check_globals();
 irq_ticks=sys_time-start;if(!irq_ticks||IE_REG!=VBL_IFLAG)++irq_failures;
 objects_done=1;while(1)vsync();}
''';(out/'driver.c').write_text(driver)
    command=[str(a.lcc),'-msm83:gb','-Wf--opt-code-size','-Wf--max-allocs-per-node','-Wf100000','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(out),'-o',str(out/'check.gbc'),str(out/'driver.c'),str(out/'vectors.c'),str(old),str(a.assembly)];subprocess.run(command,check=True,capture_output=True,text=True)
    symbols={name:int(address,16)for name,address in re.findall(r'DEF (_\w+) 0x([0-9a-fA-F]+)',(out/'check.noi').read_text())};start=symbols['_gbc_objects_draw'];end=symbols['_gbc_objects_draw_end'];assert start>>16==end>>16==5
    emulator=PyBoy(str(out/'check.gbc'),window='null',sound_emulated=False,cgb=True);emulator.set_emulation_speed(0);active=[];returns=set();timing={'fast':[],'baseline':[]}
    def completed(key):
        if not active or active[-1]['key']!=key or active[-1]['sp']+2!=emulator.register_file.SP:return
        call=active.pop();call['cycles']=emulator._cycles()-call.pop('start');call.pop('key');call.pop('sp')
        if not call.pop('irq_phase'):timing[call.pop('kind')].append(call)
    def entered(kind):
        sp=emulator.register_file.SP;ret=emulator.memory[sp]+256*emulator.memory[sp+1];key=(0 if ret<0x4000 else emulator.memory[symbols['__current_bank']],ret)
        if key not in returns:emulator.hook_register(*key,completed,key);returns.add(key)
        active.append({'kind':kind,'sp':sp,'key':key,'start':emulator._cycles(),'irq_phase':emulator.memory[symbols['_objects_irq_phase']],'count':emulator.memory[sp+6],'visible_count':emulator.memory[sp+4]})
    emulator.hook_register(5,start&65535,entered,'fast');address=symbols['_baseline_objects'];emulator.hook_register(address>>16,address&65535,entered,'baseline')
    try:
        for _ in range(1000):
            emulator.tick(100)
            if emulator.memory[symbols['_objects_done']]:break
        def n(name,size=2):
            address=symbols['_'+name];return int.from_bytes(bytes(emulator.memory[address:address+size]),'little')
        report={name:n(name)for name in('objects_cases','fast_failures','baseline_failures','global_failures','bank_failures','irq_failures','irq_ticks')}
        report.update({'done':n('objects_done',1),'irq_enabled_calls':512,'source_sha256':sha,'rom_bank':5,'rom_bytes':end-start,'api_cycles':{}})
        for kind,records in timing.items():
            report['api_cycles'][kind]={}
            for label in('all','thirteen_realistic'):
                values=[row['cycles']for row in records if label=='all' or row['count']==13 and row['visible_count']>=13]
                report['api_cycles'][kind][label]={'calls':len(values),'min':min(values),'max':max(values),'mean':sum(values)/len(values)}
        assert sha=={path.name:hashlib.sha256(path.read_bytes()).hexdigest()for path in(a.assembly,old,header)},'Object sources changed during native test'
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');(out/'calls.json').write_text(json.dumps(timing,indent=2)+'\n');print(json.dumps(report,indent=2))
        assert report['api_cycles']['fast']['thirteen_realistic']['mean']<report['api_cycles']['baseline']['thirteen_realistic']['mean'],'Batch regressed against scalar rendering'
        assert report['done']and report['objects_cases']==len(cases)and not any(report[name]for name in('fast_failures','baseline_failures','global_failures','bank_failures','irq_failures')),report
    finally:emulator.stop(save=False)


if __name__=='__main__':main()
