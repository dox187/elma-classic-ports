"""Exact native visibility against original C and exhaustive uint16 offsets.

Checks every16-bit X/Y delta, clipping cross-boundaries, counts0..64, active
flags, ordered IDs, unused output guards, read-only globals, banks and IRQs.
"""
import argparse,hashlib,json,random,re,subprocess
from pathlib import Path
from pyboy import PyBoy
BASE=Path(__file__).resolve().parents[1]
DX=(-8,-7,-6,166,167,168)
DY=(-8,-7,-6,142,143,144)


def positions(scene,i):
    mode,active,n,cx,cy,seed,start=scene
    if mode==0:x,y=(cx+start+i)&65535,cy
    elif mode==1:x,y=cx,(cy+start+i)&65535
    elif mode==2:x,y=(cx+DX[i%6])&65535,(cy+DY[(i//6)%6])&65535
    elif mode==3:x,y=(cx+((seed*29+i*71)&65535)%400-200)&65535,(cy+((seed*37+i*83)&65535)%350-175)&65535
    elif mode==4:x,y=(seed*17+i*907)&65535,(seed*31+i*1877)&65535
    else:x,y=373+i*30,679+(i*17)%220
    enabled=0 if active==0 else 1 if active==1 else i&1 if active==2 else(0,2,255,128)[(seed+i*7)&3]
    return x,y,enabled


def expected(scene):
    result=bytearray(8);cx,cy=scene[3:5]
    for i in range(scene[2]):
        x,y,active=positions(scene,i)
        sx=((x-cx-8+32768)&65535)-32768;sy=((y-cy-8+32768)&65535)-32768
        if active and -15<=sx<160 and -15<=sy<136:result[i>>3]|=1<<(i&7)
    return bytes(result)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assembly',type=Path,default=BASE/'src/objects_visible_fast.s');p.add_argument('--out',type=Path,default=BASE/'build/objects-visible-check');p.add_argument('--lcc',type=Path,default=BASE/'.toolchain/gbdk/bin/lcc');a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    header=BASE/'src/world.h';sha={path.name:hashlib.sha256(path.read_bytes()).hexdigest()for path in(a.assembly,header)}
    fields=re.search(r'typedef struct\s*\{(.*?)\}\s*game_object_t;',header.read_text(),re.S)[1];(out/'object_type.h').write_text('#include <stdint.h>\ntypedef struct{'+fields+'}game_object_t;\n')
    r=random.Random(175151);cameras=[0,1,6,7,8,255,256,32767,32768,65528,65529,65535];cases=[]
    for axis in(0,1):
        for block in range(1024):cases.append((axis,1,64,cameras[block%12],cameras[(block*7)%12],r.randrange(65536),block*64))
    for n in range(65):
        for mode in(2,3,4):cases.append((mode,n&3,n,r.choice(cameras),r.choice(cameras),r.randrange(65536),0))
    for camera in cameras:
        for active in range(4):cases.append((2,active,64,camera,65535-camera,r.randrange(65536),0))
    for _ in range(512):cases.append((r.choice((3,4)),r.randrange(4),r.randrange(65),r.randrange(65536),r.randrange(65536),r.randrange(65536),0))
    for i in range(32):cases.append((5,1,51,1807+(i&15),666+(i&7),r.randrange(65536),0))
    decl='#include <stdint.h>\ntypedef struct{uint8_t mode,active,count;uint16_t cx,cy,seed,start;uint8_t mask[8];} scene_t;\n';sources=[];calls=[]
    for bank,start in enumerate(range(0,len(cases),512),1):
        rows=cases[start:start+512];name='visibility_cases_%d'%bank;decl+='extern const scene_t '+name+'[];\n'
        path=out/(name+'.c');path.write_text('#include "vectors.h"\n#pragma bank %d\n'%bank+'const scene_t '+name+'[]={\n'+',\n'.join('{%d,%d,%d,%du,%du,%du,%du,{'%row+','.join(map(str,expected(row)))+'}}'for row in rows)+'\n};\n');sources.append(path);calls.append(' SWITCH_ROM(%d);batch(%s,%d,%d);'%(bank,name,len(rows),bank))
    (out/'vectors.h').write_text(decl);(out/'tag.c').write_text('#include <stdint.h>\n#pragma bank 5\nconst uint8_t visibility_bank_tag[]={0xa7};\n')
    driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "object_type.h"
#include "vectors.h"
uint8_t gbc_objects_visible(uint8_t*) __sdcccall(0);
extern const uint8_t visibility_bank_tag[];
uint8_t game_world[33];game_object_t game_objects[64];
__at(0xc5f0) uint8_t game_object_active[64];
uint16_t game_camera_x,game_camera_y;
uint8_t output[192],model_output[192],snapshot[997],oracle[64];
volatile uint8_t visible_done,visible_irq_phase,case_mode;
volatile uint16_t visible_cases,fast_failures,reference_failures,guard_failures,global_failures,bank_failures,irq_failures,irq_ticks;
typedef char object_size[sizeof(game_object_t)==14&&offsetof(game_object_t,x)==0&&offsetof(game_object_t,y)==2?1:-1];
typedef char scene_size[sizeof(scene_t)==19?1:-1];
static const int16_t dx[6]={-8,-7,-6,166,167,168},dy[6]={-8,-7,-6,142,143,144};
uint8_t baseline_visible(uint8_t *ids) __sdcccall(0){uint8_t i,count=0;int16_t x,y;const game_object_t *o;
 for(i=0,o=game_objects;i<game_world[32];++i,++o){if(!game_object_active[i])continue;x=(int16_t)o->x-game_camera_x-8;y=(int16_t)o->y-game_camera_y-8;if(x>=-15&&x<160&&y>=-15&&y<136)ids[count++]=i;}return count;}
static void initialize(const scene_t *v){uint16_t i,q;uint8_t *raw=(uint8_t*)game_objects;
 for(i=0;i<33;++i)game_world[i]=(uint8_t)(v->seed^i^0xa5);game_world[32]=v->count;game_camera_x=v->cx;game_camera_y=v->cy;
 for(i=0;i<896;++i)raw[i]=(uint8_t)(v->seed*17u+i*37u+(i>>3));
 for(i=0;i<64;++i){
  switch(v->mode){
  case 0:game_objects[i].x=v->cx+v->start+i;game_objects[i].y=v->cy;break;
  case 1:game_objects[i].x=v->cx;game_objects[i].y=v->cy+v->start+i;break;
  case 2:game_objects[i].x=v->cx+dx[i%6];game_objects[i].y=v->cy+dy[(i/6)%6];break;
  case 3:q=(uint16_t)(v->seed*29u+i*71u);game_objects[i].x=v->cx+q%400u-200u;q=(uint16_t)(v->seed*37u+i*83u);game_objects[i].y=v->cy+q%350u-175u;break;
  case 4:game_objects[i].x=v->seed*17u+i*907u;game_objects[i].y=v->seed*31u+i*1877u;break;
  default:game_objects[i].x=373+i*30u;game_objects[i].y=679+(i*17u)%220u;break;
  }
  game_object_active[i]=v->active==0?0:v->active==1?1:v->active==2?(i&1):((v->seed+i*7u)&3)==0?0:((v->seed+i*7u)&3)==1?2:((v->seed+i*7u)&3)==2?255:128;
 }
 memcpy(snapshot,game_world,33);memcpy(snapshot+33,game_objects,896);memcpy(snapshot+929,game_object_active,64);memcpy(snapshot+993,&game_camera_x,2);memcpy(snapshot+995,&game_camera_y,2);
}
static void check_globals(void){if(memcmp(snapshot,game_world,33)||memcmp(snapshot+33,game_objects,896)||memcmp(snapshot+929,game_object_active,64)||memcmp(snapshot+993,&game_camera_x,2)||memcmp(snapshot+995,&game_camera_y,2))++global_failures;}
static void batch(const scene_t *source,uint16_t count,uint8_t bank){uint16_t i,j;uint8_t got,want,python_count,pos;scene_t v;
 for(i=0;i<count;++i){memcpy(&v,source+i,sizeof(v));initialize(&v);case_mode=v.mode;pos=(uint8_t)((visible_cases*23u)%128u);
 for(j=0;j<192;++j)output[j]=model_output[j]=(uint8_t)(0xa5u^j^v.seed);
 python_count=0;for(j=0;j<v.count;++j)if(v.mask[j>>3]&(1u<<(j&7)))oracle[python_count++]=(uint8_t)j;
 SWITCH_ROM(5);want=baseline_visible(model_output+pos);
 if(want!=python_count||memcmp(model_output+pos,oracle,want))++reference_failures;
 IE_REG=31;IF_REG=4;got=gbc_objects_visible(output+pos);
 if(got!=want||memcmp(output,model_output,192))++fast_failures;
 if(IE_REG!=31||(IF_REG&31)!=4)++irq_failures;check_globals();
 if(CURRENT_BANK!=5||*(const volatile uint8_t*)visibility_bank_tag!=0xa7)++bank_failures;
 SWITCH_ROM(bank);++visible_cases;
 }}
void main(void){uint16_t i,start;uint8_t want,got;scene_t v;
 disable_interrupts();DISPLAY_OFF;cpu_fast();TAC_REG=0;SC_REG=0;
'''+ '\n'.join(calls)+'''
 visible_irq_phase=1;v.mode=3;v.active=1;v.count=64;v.cx=65535u;v.cy=0;v.seed=19273;v.start=0;initialize(&v);SWITCH_ROM(5);IE_REG=VBL_IFLAG;IF_REG=0;DISPLAY_ON;enable_interrupts();start=sys_time;
 for(i=0;i<256;++i){memset(output,0xa5,192);memset(model_output,0xa5,192);want=baseline_visible(model_output+63);got=gbc_objects_visible(output+63);if(got!=want||memcmp(output,model_output,192))++fast_failures;}
 check_globals();irq_ticks=sys_time-start;if(!irq_ticks||IE_REG!=VBL_IFLAG)++irq_failures;
 visible_done=1;while(1)vsync();}
''';(out/'driver.c').write_text(driver)
    cmd=[str(a.lcc),'-msm83:gb','-Wf--opt-code-size','-Wf--max-allocs-per-node','-Wf100000','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-Wl-b_DATA=0xc700','-I'+str(out),'-o',str(out/'check.gbc'),str(out/'driver.c'),str(out/'tag.c'),str(a.assembly)]+list(map(str,sources));subprocess.run(cmd,check=True,capture_output=True,text=True)
    sy={n:int(v,16)for n,v in re.findall(r'DEF (_\w+) 0x([0-9a-fA-F]+)',(out/'check.noi').read_text())};start=sy['_gbc_objects_visible'];end=sy['_gbc_objects_visible_end'];assert start>>16==end>>16==5
    emu=PyBoy(str(out/'check.gbc'),window='null',sound_emulated=False,cgb=True);emu.set_emulation_speed(0);active=[];returns=set();timing={'fast':[],'baseline':[]}
    def returned(key):
        if not active or active[-1]['key']!=key or active[-1]['sp']+2!=emu.register_file.SP:return
        call=active.pop();call['cycles']=emu._cycles()-call.pop('start');call.pop('key');call.pop('sp')
        if not call.pop('irq_phase'):timing[call.pop('kind')].append(call)
    def entered(kind):
        sp=emu.register_file.SP;ret=emu.memory[sp]+256*emu.memory[sp+1];key=(0 if ret<0x4000 else emu.memory[sy['__current_bank']],ret)
        if key not in returns:emu.hook_register(*key,returned,key);returns.add(key)
        active.append({'kind':kind,'sp':sp,'key':key,'start':emu._cycles(),'irq_phase':emu.memory[sy['_visible_irq_phase']],'count':emu.memory[sy['_game_world']+32],'mode':emu.memory[sy['_case_mode']]})
    emu.hook_register(5,start&65535,entered,'fast');address=sy['_baseline_visible'];emu.hook_register(address>>16,address&65535,entered,'baseline')
    try:
        for _ in range(1000):
            emu.tick(100)
            if emu.memory[sy['_visible_done']]:break
        def n(name,size=2):q=sy['_'+name];return int.from_bytes(bytes(emu.memory[q:q+size]),'little')
        report={name:n(name)for name in('visible_cases','fast_failures','reference_failures','guard_failures','global_failures','bank_failures','irq_failures','irq_ticks')};report.update({'done':n('visible_done',1),'expected_cases':len(cases),'exhaustive_coordinate_deltas':131072,'irq_enabled_calls':256,'source_sha256':sha,'rom_bank':5,'rom_bytes':end-start,'api_cycles':{}})
        for kind,records in timing.items():
            report['api_cycles'][kind]={}
            for label in('all','far_scan_51'):
                values=[x['cycles']for x in records if label=='all'or x['mode']==5 and x['count']==51]
                report['api_cycles'][kind][label]={'calls':len(values),'min':min(values),'max':max(values),'mean':sum(values)/len(values)}
        assert sha=={path.name:hashlib.sha256(path.read_bytes()).hexdigest()for path in(a.assembly,header)},'Visibility sources changed during native check'
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');(out/'calls.json').write_text(json.dumps(timing,indent=2)+'\n');print(json.dumps(report,indent=2))
        assert report['done']and report['visible_cases']==len(cases)and not any(report[x]for x in('fast_failures','reference_failures','guard_failures','global_failures','bank_failures','irq_failures')),report
    finally:emu.stop(save=False)


if __name__=='__main__':main()
