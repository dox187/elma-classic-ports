"""Run production video assembly against independent C references on the SM83.

This isolated helper ROM uses real banked ROM, LCD-on VRAM transactions and
interrupts. It never modifies or substitutes state in the playable game ROM.
"""
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
OUT = BASE/'build/playtest/video-check'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source = BASE/'src/video.s'
    assembly = source.read_bytes()
    tested = OUT/'video-under-test.s'
    tested.write_bytes(assembly)
    body = b'_gbc_video_body::' in assembly
    pixels = b'_gbc_video_pixels::' in assembly
    objects = b'_gbc_video_object::' in assembly
    object16_source=BASE/'src/object16.s'
    object16=object16_source.read_bytes() if object16_source.exists() else None
    if object16 is not None:(OUT/'object16-under-test.s').write_bytes(object16)
    rng = random.Random(0xC6B)
    strips = [(x,y,vertical,count,bank)
              for x,y in ((0,0),(30,31),(31,30),(31,31),(32,32),(255,255))
              for vertical in (0,1) for count in (1,2,19,21,32) for bank in (0,1)]
    strips += [(rng.randrange(256),rng.randrange(256),rng.randrange(2),
                rng.randrange(1,33),rng.randrange(2)) for _ in range(96)]
    gathers = [(offset,count,stride)
               for offset in (0,1,31,32,248,255,256,511,512,7168)
               for count in (1,2,19,21,32) for stride in (1,32)]
    bodies = [(x,y,mask) for x,y in ((0,0),(1,1),(7,255),(240,248),(255,255),(80,68))
              for mask in (0,1,0x8000,0xffff,0xa55a,0x5aa5,0x000f,0xf000)]
    object_cases = [(sprite,x,y,tile,prop) for sprite in (25,29,33,36)
                    for x,y in ((0,0),(1,1),(7,255),(248,248),(255,255),(80,68))
                    for tile in (248,252) for prop in (0,0x37,0xa8,0xff)]
    object16_cases=[(sprite,x,y,tile|right,prop) for sprite in range(13,38)
                    for x,y in ((0,0),(1,1),(7,255),(248,248),(255,255),(80,68))
                    for tile in (248,252) for right in (0,1) for prop in (0,0x37,0xa8,0xff)]
    deltas = {-2147483648,2147483647,-16777217,-16777216,-16777215,
              16777215,16777216,16777217,-1,0,1}
    for high in range(-256,257):
        for quarter in range(4):
            for fraction in (0,1,5461,5462,5463,10922,10923,10924,16383):
                deltas.add(high*65536+quarter*16384+fraction)
    deltas.update(rng.randrange(-2147483648,2147483648) for _ in range(2048))
    deltas.update(rng.randrange(-16777216,16777217) for _ in range(2048))
    pixel_batches = [sorted(deltas)[i:i+1024] for i in range(0,len(deltas),1024)] if pixels else []
    pixel_sources = []
    pixel_declarations = []
    pixel_calls = []
    for bank,batch in enumerate(pixel_batches,16):
        path = OUT/('pixels%d.c'%bank)
        path.write_text('#include "vectors.h"\n#pragma bank %d\nconst pixel_case_t pixels%d[]={\n'%(bank,bank)
            + ',\n'.join('{%dL,%d}'%(d,max(-3072,min(3072,d*3//16384))) for d in batch)+'\n};\n')
        pixel_sources.append(str(path))
        pixel_declarations.append('extern const pixel_case_t pixels%d[];'%bank)
        pixel_calls.append('SWITCH_ROM(%d);check_pixels(pixels%d,%d);'%(bank,bank,len(batch)))
    data = bytes(((i*73)^(i>>3)^0xa7)&255 for i in range(8192))
    (OUT/'data.c').write_text('#include <stdint.h>\n#pragma bank 15\nconst uint8_t bank_data[]={\n'
        + ','.join(map(str,data))+'\n};\n')
    (OUT/'vectors.h').write_text('''#include <stdint.h>
extern const uint8_t bank_data[];
typedef struct {uint8_t x,y,vertical,count,bank;} strip_case_t;
static const strip_case_t strips[]={
''' + ',\n'.join('{%d,%d,%d,%d,%d}'%v for v in strips) + '''};
typedef struct {uint16_t offset;uint8_t count,stride;} gather_case_t;
static const gather_case_t gathers[]={
''' + ',\n'.join('{%d,%d,%d}'%v for v in gathers) + '''};
typedef struct {uint8_t x,y;uint16_t mask;} body_case_t;
static const body_case_t bodies[]={
''' + ',\n'.join('{%d,%d,%d}'%v for v in bodies) + '''};
#define STRIP_CASES %d
#define GATHER_CASES %d
#define BODY_CASES %d
#define TEST_BODY %d
#define TEST_PIXELS %d
#define TEST_OBJECTS %d
#define TEST_OBJECTS16 %d
typedef struct {int32_t delta;int16_t expected;} pixel_case_t;
''' % (len(strips),len(gathers),len(bodies),body,pixels,objects,object16 is not None)
        + '\n'.join(pixel_declarations)+'''
typedef struct {uint8_t sprite,x,y,tile,prop;} object_case_t;
static const object_case_t objects[]={
''' + ',\n'.join('{%d,%d,%d,%d,%d}'%v for v in object_cases)+'''\n};
#define OBJECT_CASES %d
extern const object_case_t objects16[];
#define OBJECT16_CASES %d
'''%(len(object_cases),len(object16_cases)))
    (OUT/'objects16.c').write_text('#include "vectors.h"\n#pragma bank 14\nconst object_case_t objects16[]={\n'
        + ',\n'.join('{%d,%d,%d,%d,%d}'%v for v in object16_cases)+'\n};\n')
    (OUT/'check.c').write_text(r'''#include <gb/gb.h>
#include <gb/cgb.h>
#include "vectors.h"
void gbc_video_strip(uint8_t x,uint8_t y,uint8_t vertical,uint8_t count,const uint8_t *data) __sdcccall(0);
void gbc_video_gather(const uint8_t *source,uint8_t *dest,uint8_t count,uint8_t stride) __sdcccall(0);
#if TEST_BODY
void gbc_video_body(uint8_t x,uint8_t y,uint16_t mask) __sdcccall(0);
#endif
#if TEST_PIXELS
int16_t gbc_video_pixels(int32_t delta) __sdcccall(0);
#endif
#if TEST_OBJECTS
void gbc_video_object(uint8_t sprite,uint8_t x,uint8_t y,uint8_t tile,uint8_t prop) __sdcccall(0);
#endif
#if TEST_OBJECTS16
void gbc_video_object16(uint8_t sprite,uint8_t x,uint8_t y,uint8_t tile,uint8_t prop) __sdcccall(0);
#endif
volatile uint16_t strip_failures,gather_failures,body_failures,interrupt_failures,pixel_failures,object_failures;
volatile uint16_t completed_strips,completed_gathers,completed_bodies,completed_pixels,completed_objects;
volatile uint16_t completed_objects16;
volatile uint8_t object16_failures;
volatile uint8_t video_done;
static uint8_t expected[2][1024],transfer[32],guarded[40];
static uint8_t read_vram(uint16_t address) {
 while(STAT_REG&2){}
 return *(volatile uint8_t*)address;
}
#if TEST_PIXELS
static void check_pixels(const pixel_case_t *v,uint16_t count) {
 uint16_t i;
 for(i=0;i!=count;++i) {
  if(gbc_video_pixels(v[i].delta)!=v[i].expected)++pixel_failures;
  ++completed_pixels;
 }
}
#endif
void main(void) {
 uint16_t c,i,index,time;
 uint8_t bank,x,y,value;
 cpu_fast();DISPLAY_OFF;
 for(bank=0;bank!=2;++bank) {
  VBK_REG=bank;
  for(i=0;i!=1024;++i) {
   value=(uint8_t)(i*17U+(i>>5)+bank*93U);
   expected[bank][i]=value;
   *(volatile uint8_t*)(0x9800U+i)=value;
  }
 }
 DISPLAY_ON;set_interrupts(VBL_IFLAG);enable_interrupts();
 for(c=0;c!=STRIP_CASES;++c) {
  const strip_case_t *v=&strips[c];
  for(i=0;i!=v->count;++i) {
   transfer[i]=(uint8_t)(c*29U+i*37U);
   x=(v->x+(v->vertical?0:i))&31;
   y=(v->y+(v->vertical?i:0))&31;
   expected[v->bank][(uint16_t)y*32U+x]=transfer[i];
  }
  VBK_REG=v->bank;
  if(!(LCDC_REG&0x80))++interrupt_failures;
  time=sys_time;
  gbc_video_strip(v->x,v->y,v->vertical,v->count,transfer);
  for(bank=0;bank!=2;++bank) {
   VBK_REG=bank;
   for(i=0;i!=1024;++i)
    if(read_vram(0x9800U+i)!=expected[bank][i] && strip_failures!=65535U)++strip_failures;
  }
  if(sys_time==time)++interrupt_failures;
  ++completed_strips;
 }
 VBK_REG=0;SWITCH_ROM(15);
 for(c=0;c!=GATHER_CASES;++c) {
  const gather_case_t *v=&gathers[c];
  for(i=0;i!=40;++i)guarded[i]=0xc7;
  gbc_video_gather(bank_data+v->offset,guarded+4,v->count,v->stride);
  for(i=0;i!=40;++i) {
   value=0xc7;
   if(i>=4 && i<4U+v->count) {
    index=v->offset+(i-4U)*v->stride;
    value=(uint8_t)((index*73U)^(index>>3)^0xa7U);
   }
   if(guarded[i]!=value)++gather_failures;
  }
  ++completed_gathers;
 }
#if TEST_BODY
 for(c=0;c!=BODY_CASES;++c) {
  const body_case_t *v=&bodies[c];
  for(i=0;i!=40;++i) {
   shadow_OAM[i].x=0x57;shadow_OAM[i].y=0x39;
   shadow_OAM[i].tile=(uint8_t)(17U+i);shadow_OAM[i].prop=(uint8_t)(0x80U+i);
  }
  gbc_video_body(v->x,v->y,v->mask);
  for(i=0;i!=40;++i) {
   x=0x57;y=0x39;
   if(i<16) {
    x=(uint8_t)(v->x+(i%4)*8U);
    y=(v->mask&(1U<<i))?(uint8_t)(v->y+(i/4)*8U):0;
   }
   if(shadow_OAM[i].x!=x || shadow_OAM[i].y!=y ||
      shadow_OAM[i].tile!=(uint8_t)(17U+i) ||
      shadow_OAM[i].prop!=(uint8_t)(0x80U+i))++body_failures;
  }
  ++completed_bodies;
 }
#endif
#if TEST_OBJECTS
 for(c=0;c!=OBJECT_CASES;++c) {
  const object_case_t *v=&objects[c];
  for(i=0;i!=40;++i) {
   shadow_OAM[i].x=0x57;shadow_OAM[i].y=0x39;
   shadow_OAM[i].tile=(uint8_t)(17U+i);shadow_OAM[i].prop=(uint8_t)(0x80U+i);
  }
  gbc_video_object(v->sprite,v->x,v->y,v->tile,v->prop);
  for(i=0;i!=40;++i) {
   if(i>=v->sprite && i<v->sprite+4U) {
    index=i-v->sprite;
    x=(uint8_t)(v->x+(index%2U)*8U);y=(uint8_t)(v->y+(index/2U)*8U);
    if(shadow_OAM[i].x!=x || shadow_OAM[i].y!=y ||
       shadow_OAM[i].tile!=(uint8_t)(v->tile+index) || shadow_OAM[i].prop!=v->prop)++object_failures;
   } else if(shadow_OAM[i].x!=0x57 || shadow_OAM[i].y!=0x39 ||
             shadow_OAM[i].tile!=(uint8_t)(17U+i) || shadow_OAM[i].prop!=(uint8_t)(0x80U+i))++object_failures;
  }
  ++completed_objects;
 }
#endif
#if TEST_OBJECTS16
 SPRITES_8x16;SWITCH_ROM(14);
 for(c=0;c!=OBJECT16_CASES;++c) {
  const object_case_t *v=&objects16[c];
  for(i=0;i!=40;++i) {
   shadow_OAM[i].x=0x57;shadow_OAM[i].y=0x39;
   shadow_OAM[i].tile=(uint8_t)(17U+i);shadow_OAM[i].prop=(uint8_t)(0x80U+i);
  }
  gbc_video_object16(v->sprite,v->x,v->y,v->tile,v->prop);
  for(i=0;i!=40;++i) {
   if(i>=v->sprite && i<v->sprite+2U) {
    index=(i-v->sprite)^(v->tile&1U);
    x=(uint8_t)(v->x+index*8U);y=v->y;
    if(shadow_OAM[i].x!=x || shadow_OAM[i].y!=y ||
       shadow_OAM[i].tile!=(uint8_t)((v->tile&254U)+index*2U) || shadow_OAM[i].prop!=v->prop)object16_failures=1;
   } else if(shadow_OAM[i].x!=0x57 || shadow_OAM[i].y!=0x39 ||
             shadow_OAM[i].tile!=(uint8_t)(17U+i) || shadow_OAM[i].prop!=(uint8_t)(0x80U+i))object16_failures=1;
  }
  ++completed_objects16;
 }
#endif
/*PIXEL_CALLS*/
 time=sys_time;
 while(sys_time==time){}
 video_done=1;
 while(1)vsync();
}
'''.replace('/*PIXEL_CALLS*/','\n'.join(pixel_calls)))
    command = [str(BASE/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size',
        '-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(OUT),
        '-o',str(OUT/'check.gbc'),str(OUT/'check.c'),str(OUT/'data.c'),*pixel_sources,str(tested)]
    if object16 is not None:command.extend((str(OUT/'objects16.c'),str(OUT/'object16-under-test.s')))
    subprocess.run(command,check=True,capture_output=True,text=True)
    symbols = {k:int(v,16) for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',
               (OUT/'check.noi').read_text())}
    p = PyBoy(str(OUT/'check.gbc'),window='null',sound_emulated=False,cgb=True)
    p.set_emulation_speed(0)
    def word(name):
        a=symbols['_'+name]
        return p.memory[a]+256*p.memory[a+1]
    try:
        for _ in range(200):
            p.tick(100,False)
            if p.memory[symbols['_video_done']]:break
        report = {'status':'passed','fixture':'isolated production-helper ROM; LCD on, VBlank interrupts enabled',
            'source':str(source.resolve()),'source_sha256':hashlib.sha256(assembly).hexdigest(),
            'rom_sha256':hashlib.sha256((OUT/'check.gbc').read_bytes()).hexdigest(),
            'source_still_current':source.read_bytes()==assembly,
            'strips':word('completed_strips'),'gathers':word('completed_gathers'),
            'bodies':word('completed_bodies'),
            'pixels':word('completed_pixels'),
            'objects':word('completed_objects'),
            'objects16':word('completed_objects16'),
            'failures':{name:word(name+'_failures') for name in ('strip','gather','body','interrupt','pixel','object')},
            'object16_failures':p.memory[symbols['_object16_failures']],
            'object16_source_sha256':hashlib.sha256(object16).hexdigest() if object16 else None,
            'hardware_tested':False}
        assert p.memory[symbols['_video_done']], 'helper ROM did not finish (interrupts may be disabled)'
        assert report['strips']==len(strips) and report['gathers']==len(gathers)
        assert report['bodies']==(len(bodies) if body else 0)
        assert report['pixels']==(len(deltas) if pixels else 0)
        assert report['objects']==(len(object_cases) if objects else 0)
        assert report['objects16']==(len(object16_cases) if object16 else 0) and not report['object16_failures'],report
        assert not any(report['failures'].values()),report
        assert report['source_still_current'],'production assembly changed while testing; rerun current source'
        assert object16 is None or object16_source.read_bytes()==object16,'object16 helper changed while testing; rerun'
    except BaseException:
        if 'report' in locals():
            report['status']='failed'
            (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        raise
    finally:
        p.stop(save=False)
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
