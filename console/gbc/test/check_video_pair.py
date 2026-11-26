"""Native paired map-plane writes: independent VRAM model, IRQs and cycle proof.

Runs the existing two-strip path and the new pair on LCD-on CGB hardware
emulation, with scroll phase and ten sprites. No playable-game state is used.
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
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--assembly',type=Path,default=BASE/'src/video_strip_pair.s');parser.add_argument('--out',type=Path,default=BASE/'build/video-pair-check');parser.add_argument('--lcc',type=Path,default=BASE/'.toolchain/gbdk/bin/lcc');a=parser.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    old=BASE/'src/video.s';sha=hashlib.sha256(a.assembly.read_bytes()).hexdigest();oldsha=hashlib.sha256(old.read_bytes()).hexdigest()
    randomizer=random.Random(21632)
    cases=[(0,0,v,n)for v in(0,1)for n in range(1,33)]
    cases += [(x,y,v,n)for x,y in((30,31),(31,30),(31,31),(32,32),(255,255))for v in(0,1)for n in(1,2,19,21,32)]
    cases += [(randomizer.randrange(256),randomizer.randrange(256),randomizer.randrange(2),randomizer.randrange(1,33))for _ in range(216-len(cases))]
    cases += [(255,255,0,0),(255,255,1,0)]
    (out/'vectors.h').write_text('#include <stdint.h>\ntypedef struct{uint8_t x,y,vertical,count;} pair_case_t;\nstatic const pair_case_t cases[]={\n'+',\n'.join('{%d,%d,%d,%d}'%row for row in cases)+'\n};\n#define CASES %d\n'%len(cases))
    (out/'bank.c').write_text('#include <stdint.h>\n#pragma bank 6\nconst uint8_t pair_bank_tag[]={0x6a};\n')
    driver='''#include <gb/gb.h>
#include <gb/cgb.h>
#include <string.h>
#include "vectors.h"
void gbc_video_strip(uint8_t,uint8_t,uint8_t,uint8_t,const uint8_t*) __sdcccall(0);
void gbc_video_strip_pair(uint8_t,uint8_t,uint8_t,uint8_t,const uint8_t*,const uint8_t*) __sdcccall(0);
extern const uint8_t pair_bank_tag[];
volatile uint8_t pair_done,pair_active,pair_callback_failures;
volatile uint16_t pair_case_index,pair_cases,baseline_cases,pair_failures,baseline_failures,input_failures,bank_failures,irq_failures,pair_callbacks,stress_cases,vram_guard_failures;
volatile uint16_t pair_focus,input_seed;
uint8_t expected[2][1024],tiles[40],attrs[40];
static const uint8_t blank[32]={0};
static uint8_t safe_read(uint16_t address){while(STAT_REG&2){}return *(volatile uint8_t*)address;}
static void latch(void) NONBANKED {
 uint8_t tile,attr;
 if(pair_active){
  ++pair_callbacks;if(VBK_REG&1)pair_callback_failures|=1;
  VBK_REG=0;tile=safe_read(pair_focus);VBK_REG=1;attr=safe_read(pair_focus);VBK_REG=0;
  if(attr!=(uint8_t)(tile^0x5a))pair_callback_failures|=2;
 }
}
void baseline_pair(uint8_t x,uint8_t y,uint8_t vertical,uint8_t count,const uint8_t *t,const uint8_t *a) __sdcccall(0) {
 VBK_REG=1;gbc_video_strip(x,y,vertical,count,a);VBK_REG=0;gbc_video_strip(x,y,vertical,count,t);
}
static void model(uint8_t x,uint8_t y,uint8_t vertical,uint8_t count){uint8_t i;uint16_t address;
 for(i=0;i<count;++i){address=(uint16_t)(y&31)*32+(x&31);expected[0][address]=tiles[4+i];expected[1][address]=attrs[4+i];if(vertical)++y;else ++x;}
}
static void check(uint8_t pair){uint16_t i;uint8_t bank;
 for(bank=0;bank<2;++bank){VBK_REG=bank;for(i=0;i<1024;++i)if(safe_read(0x9800+i)!=expected[bank][i]){if(pair)++pair_failures;else ++baseline_failures;}
 for(i=0;i<32;++i)if(safe_read(0x97e0+i)!=(uint8_t)(0x39u+i+bank)||safe_read(0x9c00+i)!=(uint8_t)(0xc7u^i^bank))++vram_guard_failures;}
 VBK_REG=0;
 for(i=0;i<40;++i)if(tiles[i]!=(uint8_t)(input_seed*29u+i*37u)||attrs[i]!=(uint8_t)(tiles[i]^0x5a))++input_failures;
 if(CURRENT_BANK!=6||*(const volatile uint8_t*)pair_bank_tag!=0x6a)++bank_failures;
 if(IE_REG!=VBL_IFLAG)++irq_failures;
}
static void data(uint16_t n){uint8_t i;input_seed=n;for(i=0;i<40;++i){tiles[i]=(uint8_t)(n*29u+i*37u);attrs[i]=tiles[i]^0x5a;}}
void main(void){uint16_t i,c,start;uint8_t bank,target;
 cpu_fast();DISPLAY_OFF;HIDE_WIN;HIDE_SPRITES;
 for(bank=0;bank<2;++bank){VBK_REG=bank;for(i=0;i<1024;++i){expected[bank][i]=(uint8_t)(i*17u+(i>>5));if(bank)expected[bank][i]^=0x5a;*(volatile uint8_t*)(0x9800+i)=expected[bank][i];}}
 for(bank=0;bank<2;++bank){VBK_REG=bank;for(i=0;i<32;++i){*(volatile uint8_t*)(0x97e0+i)=(uint8_t)(0x39u+i+bank);*(volatile uint8_t*)(0x9c00+i)=(uint8_t)(0xc7u^i^bank);}}
 VBK_REG=0;set_sprite_data(0,2,blank);SPRITES_8x16;
 for(i=0;i<10;++i){set_sprite_tile(i,0);move_sprite(i,(uint8_t)(8+i*8),16);}SHOW_SPRITES;SHOW_BKG;
 pair_focus=0x9800;add_VBL(latch);DISPLAY_ON;set_interrupts(VBL_IFLAG);enable_interrupts();SWITCH_ROM(6);
 for(c=0;c<CASES;++c){const pair_case_t *v=&cases[c];pair_case_index=c;SCX_REG=c&7;SCY_REG=(uint8_t)(c*3u);
  data(c);model(v->x,v->y,v->vertical,v->count);pair_focus=0x9800u+(uint16_t)(v->y&31)*32u+(v->x&31);
  target=(c&3)?(uint8_t)((c*17u)%144u):144;vsync();while(LY_REG!=target){}pair_active=1;gbc_video_strip_pair(v->x,v->y,v->vertical,v->count,tiles+4,attrs+4);pair_active=0;
  if(VBK_REG&1)++pair_failures;check(1);++pair_cases;
  if(v->count){data(c+317u);model(v->x,v->y,v->vertical,v->count);vsync();while(LY_REG!=target){}baseline_pair(v->x,v->y,v->vertical,v->count,tiles+4,attrs+4);check(0);++baseline_cases;}
 }
 for(c=0;c<32;++c){data(c+701u);model(31,(uint8_t)c,c&1,32);pair_focus=0x9800u+(uint16_t)(c&31)*32u+31;
  while(LY_REG!=143){}pair_active=1;gbc_video_strip_pair(31,(uint8_t)c,c&1,32,tiles+4,attrs+4);pair_active=0;check(1);++stress_cases;
 }
 start=sys_time;while(sys_time==start){}if(!pair_callbacks)++irq_failures;
 pair_done=1;while(1)vsync();}
''';(out/'driver.c').write_text(driver)
    command=[str(a.lcc),'-msm83:gb','-Wf--opt-code-size','-Wm-yC','-Wm-yt0x19','-Wm-yoA','-Wl-m','-Wl-j','-I'+str(out),'-o',str(out/'check.gbc'),str(out/'driver.c'),str(out/'bank.c'),str(old),str(a.assembly)]
    subprocess.run(command,check=True,capture_output=True,text=True)
    symbols={name:int(address,16)for name,address in re.findall(r'DEF (_\w+) 0x([0-9a-fA-F]+)',(out/'check.noi').read_text())};rom=(out/'check.gbc').read_bytes()
    start=symbols['_gbc_video_strip_pair'];end=symbols['_gbc_video_strip_pair_end'];assert start>>16==end>>16==6
    offset=6*16384+(start&65535)-0x4000;code=rom[offset:offset+(end-start)]
    # The raw row copies five bytes after a mode 0/1 sample. The final
    # row tail selects one through four writes while that window is open.
    poll=bytes.fromhex('f0 41 e6 02 20 fa')
    row=bytes.fromhex('1a 13 22');column=bytes.fromhex('1a 13 77 09')
    assert code.count(poll+row*5)==1 and code.count(poll+column*4)==1
    assert all(code.count(poll+column*n+b'\xc9')==1 for n in (1,2,3))
    tail=(bytes.fromhex('78 fe 04 20 0d')+row*4+bytes.fromhex('c9 05 28 09 05 28 03')+row*3+b'\xc9')
    assert code.count(poll+tail)==1 and code.count(poll)==6
    sample=12+8+8
    row_tail_cycles=[sample+4+8+12+4+12+24, sample+4+8+12+4+8+4+12+2*24,
                     sample+4+8+12+4+8+4+8+3*24, sample+4+8+8+4*24]
    safe_window_cycles=max(sample+5*24,sample+4*32,*row_tail_cycles)
    assert safe_window_cycles==156<160 and max(row_tail_cycles)==148
    emulator=PyBoy(str(out/'check.gbc'),window='null',sound_emulated=False,cgb=True);emulator.set_emulation_speed(0);active=[];returns=set();timing={'pair':[],'baseline':[]}
    def completed(key):
        if not active or active[-1]['key']!=key or active[-1]['sp']+2!=emulator.register_file.SP:return
        call=active.pop();call['cycles']=emulator._cycles()-call.pop('start');call.pop('key');call.pop('sp');timing[call.pop('kind')].append(call)
    def entered(kind):
        sp=emulator.register_file.SP;ret=emulator.memory[sp]+256*emulator.memory[sp+1];key=(0 if ret<0x4000 else emulator.memory[symbols['__current_bank']],ret)
        if key not in returns:emulator.hook_register(*key,completed,key);returns.add(key)
        active.append({'kind':kind,'sp':sp,'key':key,'start':emulator._cycles(),'case':emulator.memory[symbols['_pair_case_index']]+256*emulator.memory[symbols['_pair_case_index']+1],'count':emulator.memory[sp+5]})
    emulator.hook_register(6,start&65535,entered,'pair');address=symbols['_baseline_pair'];emulator.hook_register(address>>16,address&65535,entered,'baseline')
    try:
        for _ in range(1000):
            emulator.tick(100)
            if emulator.memory[symbols['_pair_done']]:break
        def n(name,size=2):
            address=symbols['_'+name];return int.from_bytes(bytes(emulator.memory[address:address+size]),'little')
        report={name:n(name)for name in('pair_cases','baseline_cases','pair_failures','baseline_failures','input_failures','bank_failures','irq_failures','pair_callbacks','stress_cases','vram_guard_failures')}
        report.update({'done':n('pair_done',1),'latched_callback_failures':n('pair_callback_failures',1),'source_sha256':sha,'baseline_sha256':oldsha,'hardware_tested':False,'rom_bank':6,'rom_bytes':end-start,'safe_write_window_tcycles':safe_window_cycles,'minimum_following_mode2_fast_tcycles':160,'api_cycles':{}})
        for kind,records in timing.items():
            values=[r['cycles']for r in records if r['case']<216 and r['count']>0]
            report['api_cycles'][kind]={'calls':len(values),'min':min(values),'max':max(values),'mean':sum(values)/len(values)}
        report['publication_cycles']={}
        for count in (19,21):
            report['publication_cycles'][count]={}
            for kind,records in timing.items():
                values=[r['cycles']for r in records if r['case']<216 and r['count']==count]
                report['publication_cycles'][count][kind]={'calls':len(values),'mean':sum(values)/len(values),'max':max(values)}
        assert hashlib.sha256(a.assembly.read_bytes()).hexdigest()==sha and hashlib.sha256(old.read_bytes()).hexdigest()==oldsha,'Video sources changed during native test'
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');(out/'calls.json').write_text(json.dumps(timing,indent=2)+'\n');print(json.dumps(report,indent=2))
        assert report['done']and report['pair_cases']==218 and report['baseline_cases']==216 and report['stress_cases']==32 and report['pair_callbacks']>0
        assert report['api_cycles']['pair']['mean']<report['api_cycles']['baseline']['mean'],'Paired writer regressed against two-strip baseline'
        assert not any(report[name]for name in('pair_failures','baseline_failures','input_failures','bank_failures','irq_failures','latched_callback_failures','vram_guard_failures')),report
    finally:emulator.stop(save=False)


if __name__=='__main__':main()
