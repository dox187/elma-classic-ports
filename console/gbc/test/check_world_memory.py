"""Exercise production SRAM lookup and nine-bit MBC5 reads on the SM83.

This isolated helper ROM uses 32 KiB cartridge RAM, real ROM banks 300/511,
VBlank interrupts and a banked caller. No playable-game state is injected.
"""
import hashlib
import json
from pathlib import Path
import re
import random
import subprocess

from pyboy import PyBoy

BASE = Path(__file__).resolve().parents[1]
OUT = BASE/'build/playtest/world-memory-check'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source = BASE/'src/world_memory.s'
    assembly = source.read_bytes()
    tested = OUT/'world-memory-under-test.s'
    tested.write_bytes(assembly)
    rng=random.Random(0x5107)
    cases=[(x,y,vertical,count) for x,y in ((0,0),(1,30),(30,1),(31,31),(32,63),(63,32),(255,255))
           for vertical in (0,1) for count in (0,1,2,19,21)]
    cases += [(rng.randrange(256),rng.randrange(256),rng.randrange(2),rng.randrange(22)) for _ in range(128)]
    (OUT/'slot_cases.h').write_text('typedef struct {uint8_t x,y,vertical,count;} slot_case_t;\nstatic const slot_case_t slot_cases[]={\n'
        + ','.join('{%d,%d,%d,%d}'%case for case in cases)+'\n};\n#define SLOT_CASES %d\n'%len(cases))
    for bank,size in ((8,512),(300,16384),(511,16384)):
        data = [((i*29)^(i>>7)^(bank*17))&255 for i in range(size)]
        extra = '''
uint8_t caller_probe(void) BANKED {
 return ((const volatile uint8_t *)data8)[91];
}
uint8_t caller_copy(uint16_t bank,const uint8_t *src,uint8_t *dst,uint16_t length) BANKED {
 world_far_copy(bank,src,dst,length);
 return ((const volatile uint8_t *)data8)[91];
}
uint8_t caller_gather(uint16_t bank,const uint8_t *src,uint8_t *dst,uint8_t count,uint8_t stride) BANKED {
 world_far_gather(bank,src,dst,count,stride);
 return ((const volatile uint8_t *)data8)[91];
}
''' if bank == 8 else ''
        (OUT/('data%d.c'%bank)).write_text('#include <gb/gb.h>\n#include "world_memory.h"\n#pragma bank %d\n'%bank
            + 'const uint8_t data%d[]={\n'%bank+', '.join(map(str,data))+'\n};\n'+extra)
    fixed = [((i*29)^(i>>7)^0x5a)&255 for i in range(512)]
    (OUT/'fixed.h').write_text('static const uint8_t fixed_data[]={'+','.join(map(str,fixed))+'};\n')
    (OUT/'check.c').write_text(r'''#include <gb/gb.h>
#include <gb/cgb.h>
#include "world_memory.h"
#include "fixed.h"
#include "slot_cases.h"
extern const uint8_t data8[],data300[],data511[];
uint8_t caller_probe(void) BANKED;
uint8_t caller_copy(uint16_t bank,const uint8_t *src,uint8_t *dst,uint16_t length) BANKED;
uint8_t caller_gather(uint16_t bank,const uint8_t *src,uint8_t *dst,uint8_t count,uint8_t stride) BANKED;
volatile uint8_t lookup_failures,clear_failures,ram_restore_failures;
volatile uint8_t far_failures,rom_restore_failures,interrupt_failures,memory_done;
volatile uint8_t gather_failures,collision_failures;
volatile uint8_t slot_failures,slot_protection_failures;
volatile uint32_t lookup_checks,clear_checks;
volatile uint16_t far_checks,irq_count;
volatile uint16_t gather_checks,collision_checks;
volatile uint16_t slot_checks;
static uint8_t guarded[4104];
static uint16_t mirror_expected[1024];
static const uint16_t clear_counts[]={0,1,4095,4096,4097,8191,8192,28410,32768,65535};
static const uint16_t lengths[]={0,1,2,15,16,19,21,255,256,257,1024,4096};
static const uint16_t offsets[]={0,1,248,255,256,511,1024,12288};
static const uint8_t gather_counts[]={0,1,2,16,19,21,32};
static const uint8_t gather_strides[]={0,1,32};
static uint16_t slot_value(uint16_t id) {
 return (uint16_t)((id*73U)^(id>>3)^0x6a91U);
}
static void tick(void) {++irq_count;}
static void check_copy(uint16_t bank,const uint8_t *base,uint16_t offset,uint16_t length) {
 uint16_t i,before,index;
 uint8_t expected;
 for(i=0;i!=4104;++i)guarded[i]=0xc7;
 SWITCH_ROM(8);before=irq_count;
 if(caller_copy(bank,base+offset,guarded+4,length)!=(uint8_t)((91U*29U)^(91U>>7)^(8U*17U)))rom_restore_failures=1;
 if(CURRENT_BANK!=8 || ((const volatile uint8_t *)data8)[91]!=(uint8_t)((91U*29U)^(91U>>7)^(8U*17U)))rom_restore_failures=1;
 if(caller_probe()!=(uint8_t)((91U*29U)^(91U>>7)^(8U*17U)))rom_restore_failures=1;
 if(length==4096 && irq_count==before)interrupt_failures=1;
 for(i=0;i!=4104;++i) {
  expected=0xc7;
  if(i>=4 && i<length+4U) {
   index=offset+i-4U;
   expected=(uint8_t)((index*29U)^(index>>7)^(bank?bank*17U:0x5aU));
  }
  if(guarded[i]!=expected)far_failures=1;
 }
 ++far_checks;
}
static void check_gather(uint16_t bank,const uint8_t *base,uint16_t offset,uint8_t count,uint8_t stride) {
 uint16_t i,index;
 uint8_t expected;
 for(i=0;i!=40;++i)guarded[i]=0xc7;
 SWITCH_ROM(8);
 if(caller_gather(bank,base+offset,guarded+4,count,stride)!=(uint8_t)((91U*29U)^(91U>>7)^(8U*17U)))rom_restore_failures=1;
 if(CURRENT_BANK!=8 || ((const volatile uint8_t *)data8)[91]!=(uint8_t)((91U*29U)^(91U>>7)^(8U*17U)))rom_restore_failures=1;
 if(caller_probe()!=(uint8_t)((91U*29U)^(91U>>7)^(8U*17U)))rom_restore_failures=1;
 for(i=0;i!=40;++i) {
  expected=0xc7;
  if(i>=4 && i<count+4U) {
   index=offset+(i-4U)*stride;
   expected=(uint8_t)((index*29U)^(index>>7)^(bank?bank*17U:0x5aU));
  }
  if(guarded[i]!=expected)gather_failures=1;
 }
 ++gather_checks;
}
static void check_clear(void) {
 uint16_t i,j;uint8_t bank,expected;
 for(j=0;j!=sizeof(clear_counts)/sizeof(clear_counts[0]);++j) {
  *(volatile uint8_t *)0x0000=0x0a;
  for(bank=0;bank<4;++bank) {
   *(volatile uint8_t *)0x4000=bank;
   for(i=0;i<8192;++i)*(volatile uint8_t *)(0xa000U+i)=0x93+bank;
  }
  /* Every count, including zero, enables RAM and clears the fixed table. */
  *(volatile uint8_t *)0x0000=0;
  world_lookup_clear(clear_counts[j]);
  if(*(volatile uint16_t *)0xa000!=0xffff)ram_restore_failures=1;
  for(bank=0;bank<4;++bank) {
   *(volatile uint8_t *)0x4000=bank;
   for(i=0;i<8192;++i) {
    expected=!bank&&i<0xef0?0xff:0x93+bank;
    if(*(volatile uint8_t *)(0xa000U+i)!=expected)clear_failures=1;
    ++clear_checks;
   }
  }
  if(world_lookup_get(65535)!=65535)clear_failures=1;
  if(*(volatile uint16_t *)0xa000!=0xffff)ram_restore_failures=1;
 }
}
static void check_lookup(void) {
 uint16_t id=0,slot=0,old,expected;uint8_t full=0;
 /* Visit every 16-bit ID with at most 444 live bindings. Remove an evicted
  * binding before reusing its slot, exactly as production acquire does. */
 do {
  *(volatile uint8_t *)0x4000=3;
  if(world_lookup_get(id)!=65535)lookup_failures=1;
  if(*(volatile uint8_t *)0xaef0!=0x93)ram_restore_failures=1;
  if(full) {
   old=id-444U;
   *(volatile uint8_t *)0x4000=2;
   world_lookup_set(old,65535);
   if(*(volatile uint8_t *)0xaef0!=0x93)ram_restore_failures=1;
   if(world_lookup_get(old)!=65535)lookup_failures=1;
  }
  *(volatile uint8_t *)0x4000=1;
  world_lookup_insert_absent(id,slot);
  if(*(volatile uint8_t *)0xaef0!=0x93)ram_restore_failures=1;
  if(world_lookup_get(id)!=slot)lookup_failures=1;
  ++lookup_checks;
  if(++slot==444){slot=0;full=1;}
 } while(++id);
 /* The final 444 bindings survive, and every earlier ID is absent. */
 id=0;slot=0;
 do {
  expected=id>=65092U?slot:65535U;
  if(world_lookup_get(id)!=expected)lookup_failures=1;
  ++lookup_checks;
  if(++slot==444)slot=0;
 } while(++id);
}
static void check_collisions(void) {
 uint16_t i,id,expected;
 world_lookup_clear(0);
 /* All64 IDs share bucket1023, including ID65535; use distinct valid slots. */
 for(i=0;i<64;++i)world_lookup_insert_absent(1023U+(i<<10),i);
 for(i=0;i<64;++i) {
  id=1023U+(i<<10);
  if(world_lookup_get(id)!=i)collision_failures=1;
  ++collision_checks;
 }
 /* Remove the head, interior nodes and tail, then move surviving IDs to
  * unused slots. Reinsertions must never resurrect old slot bindings. */
 for(i=0;i<64;i+=2)world_lookup_set(1023U+(i<<10),65535);
 world_lookup_set(65535,65535);
 for(i=1;i<63;i+=2)world_lookup_set(1023U+(i<<10),i+128U);
 for(i=0;i<64;++i) {
  expected=(i&1)&&i!=63?i+128U:65535U;
  if(world_lookup_get(1023U+(i<<10))!=expected)collision_failures=1;
  ++collision_checks;
 }
 for(i=0;i<64;i+=2)world_lookup_insert_absent(1023U+(i<<10),i+256U);
 world_lookup_insert_absent(65535,443);
 for(i=0;i<64;++i) {
  id=1023U+(i<<10);expected=i==63?443U:i+((i&1)?128U:256U);
  if(world_lookup_get(id)!=expected)collision_failures=1;
  world_lookup_set(id,expected); /* Updating an existing binding is stable. */
  if(world_lookup_get(id)!=expected)collision_failures=1;
  ++collision_checks;
 }
 world_lookup_clear(65535);
}
static void check_slots(void) {
 uint16_t c,i,index,value;uint8_t bank,expected,x,y;
 for(i=0;i<2048;++i)*(volatile uint8_t *)(0xb000U+i)=0x9d;
 for(i=0;i<1024;++i)mirror_expected[i]=0x9d9d;
 for(c=0;c<SLOT_CASES;++c) {
  const slot_case_t *v=&slot_cases[c];
  for(i=0;i<50;++i)guarded[i]=0xc7;
  for(i=0;i<v->count;++i) {
   value=slot_value(c*37U+i);((uint16_t *)(guarded+4))[i]=value;
   x=(v->x+(v->vertical?0:i))&31;y=(v->y+(v->vertical?i:0))&31;
   mirror_expected[(uint16_t)y*32U+x]=value;
  }
  *(volatile uint8_t *)0x4000=3;
  world_slot_strip_set(v->x,v->y,v->vertical,v->count,(const uint16_t *)(guarded+4));
  if(*(volatile uint16_t *)0xa000!=0xffff)ram_restore_failures=1;
  for(i=0;i<50;++i) {
   expected=0xc7;
   if(i>=4 && i<4U+v->count*2U) {
    value=slot_value(c*37U+(i-4U)/2U);expected=(i&1)?value>>8:(uint8_t)value;
   }
   if(guarded[i]!=expected)slot_protection_failures=1;
   guarded[i]=0xc7;
  }
  *(volatile uint8_t *)0x4000=2;
  world_slot_strip_get(v->x,v->y,v->vertical,v->count,(uint16_t *)(guarded+4));
  if(*(volatile uint16_t *)0xa000!=0xffff)ram_restore_failures=1;
  for(i=0;i<50;++i) {
   expected=0xc7;
   if(i>=4 && i<4U+v->count*2U) {
    index=(i-4U)/2U;x=(v->x+(v->vertical?0:index))&31;y=(v->y+(v->vertical?index:0))&31;
    value=mirror_expected[(uint16_t)y*32U+x];expected=(i&1)?value>>8:(uint8_t)value;
   }
   if(guarded[i]!=expected)slot_failures=1;
  }
  for(i=0;i<8192;++i) {
   value=i<0xef0?0xffff:0x9393;
   if(i>=0x1000&&i<0x1800)value=mirror_expected[(i-0x1000)/2U];
   expected=(i&1)?value>>8:(uint8_t)value;
   if(*(volatile uint8_t *)(0xa000U+i)!=expected)slot_protection_failures=1;
  }
  ++slot_checks;
 }
 /* All other RAM banks and bank0 guard/save bytes retain their canaries. */
 for(bank=1;bank<4;++bank) {
  *(volatile uint8_t *)0x4000=bank;
  for(i=0;i<8192;++i)
   if(*(volatile uint8_t *)(0xa000U+i)!=(uint8_t)(0x93+bank))slot_protection_failures=1;
 }
 *(volatile uint8_t *)0x4000=0;
}
void main(void) {
 uint16_t i,j,k;
 cpu_fast();add_VBL(tick);set_interrupts(VBL_IFLAG);enable_interrupts();
 check_clear();check_lookup();check_collisions();
 for(j=0;j!=sizeof(offsets)/sizeof(offsets[0]);++j)
  for(k=0;k!=sizeof(lengths)/sizeof(lengths[0]);++k) {
   if(offsets[j]+lengths[k]>16384U)continue;
   check_copy(300,data300,offsets[j],lengths[k]);
   check_copy(511,data511,offsets[j],lengths[k]);
  }
 for(j=0;j!=5;++j) {
  check_copy(0,fixed_data,j,lengths[j]);
  check_copy(8,data8,j,lengths[j]);
 }
 for(j=0;j!=sizeof(gather_counts);++j)
  for(k=0;k!=sizeof(gather_strides);++k)
   for(i=0;i!=sizeof(offsets)/sizeof(offsets[0]);++i) {
    check_gather(300,data300,offsets[i],gather_counts[j],gather_strides[k]);
    check_gather(511,data511,offsets[i],gather_counts[j],gather_strides[k]);
   }
 /* Last source byte exactly at 0x7fff; final stride may point past it. */
 check_gather(300,data300,16352,32,1);check_gather(511,data511,15391,32,32);
 check_gather(0,fixed_data,255,21,1);check_gather(8,data8,255,21,1);
 check_slots();
 if(!irq_count)interrupt_failures=1;
 memory_done=1;
 while(1)vsync();
}
''')
    command = [str(BASE/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size',
        '-Wm-yC','-Wm-yt0x1a','-Wm-yo512','-Wm-ya4','-Wl-m','-Wl-j',
        '-I'+str(OUT),'-I'+str(BASE/'src'),'-o',str(OUT/'check.gbc'),str(OUT/'check.c'),
        *(str(OUT/('data%d.c'%bank)) for bank in (8,300,511)),str(tested)]
    compiled = subprocess.run(command,capture_output=True,text=True)
    if compiled.returncode:
        raise AssertionError(compiled.stdout+compiled.stderr)
    symbols = {k:int(v,16) for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',
               (OUT/'check.noi').read_text())}
    rom = (OUT/'check.gbc').read_bytes()
    assert len(rom)==8*1024*1024 and rom[0x147]==0x1a and rom[0x149]==3
    p = PyBoy(str(OUT/'check.gbc'),window='null',sound_emulated=False,cgb=True)
    p.set_emulation_speed(0)
    def number(name,size):
        address=symbols['_'+name]
        return int.from_bytes(bytes(p.memory[address:address+size]),'little')
    try:
        for _ in range(400):
            p.tick(100,False)
            if p.memory[symbols['_memory_done']]:break
        report = {'status':'passed','fixture':'isolated production-helper ROM; 8MiB MBC5+32KiB RAM',
            'source':str(source.resolve()),'source_sha256':hashlib.sha256(assembly).hexdigest(),
            'rom_sha256':hashlib.sha256(rom).hexdigest(),'source_still_current':source.read_bytes()==assembly,
            'lookup_checks':number('lookup_checks',4),'clear_checks':number('clear_checks',4),
            'far_copy_checks':number('far_checks',2),'interrupts':number('irq_count',2),
            'far_gather_checks':number('gather_checks',2),
            'slot_strip_checks':number('slot_checks',2),
            'collision_checks':number('collision_checks',2),'lookup_capacity':444,
            'protected_ranges':['bank0 AEF0-AFFF','bank0 B800-BFFF','banks1..3 A000-BFFF'],
            'source_banks':[0,8,300,511],'restored_caller_bank':8,
            'failures':{name:number(name+'_failures',1) for name in
                ('lookup','collision','clear','ram_restore','far','gather','slot','slot_protection','rom_restore','interrupt')},'hardware_tested':False}
        assert p.memory[symbols['_memory_done']],'helper ROM did not finish (bank restoration or interrupt failure)'
        assert report['lookup_checks']==131072 and report['clear_checks']==327680
        assert report['collision_checks']==192,report
        assert report['far_copy_checks']==202,report
        assert report['far_gather_checks']==340,report
        assert report['slot_strip_checks']==len(cases),report
        assert not any(report['failures'].values()),report
        assert report['source_still_current'],'production helper changed during test; rerun'
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
