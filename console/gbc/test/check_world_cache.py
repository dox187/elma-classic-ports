"""Native regression for the production streamed world cache.

Synthetic helper-ROM fixtures exercise uniform399-reference tiles, unique
viewports, high pattern IDs, nine-bit ROM banks, all diagonal directions and
world padding. Budgeted preparation additionally preserves the old viewport
through partial work, cancellation and mismatched commits. Independently
reconstructed references must include exactly the pending incoming cells.
The default fixture uses raw graphics; --compressed exercises production ZX0
map and pattern blocks, including eviction and reload of conflicting blocks.
Both fixtures declare 32 KiB SRAM. Save bytes in bank 0 remain guarded across
initialization, course changes, scrolling and preparation cancellation. Linked
instruction hooks reject RAM bank requests outside 0..3 before MBC5 aliasing.
The compressed synthetic ROM retains nine-bit banks to test that helper API;
its 8 MiB ROM size is not the production compressed cartridge's size.
This does not claim playable-level completion.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

from pyboy import PyBoy

BASE=Path(__file__).resolve().parents[1]
OUT=BASE/'build/playtest/world-cache-check'


def pattern(value):
    return bytes((value&255,value>>8))+bytes(((value*37)+(i*19)+(value>>(i&7)))&255 for i in range(2,16))


def logical(level,x,y):
    if x>=64 or y>=48:return 0,0
    value=0 if level==0 else y*64+x if level==1 else 28000+(y*64+x)%410
    attribute=0 if level==0 else ((x+2*y)%7)|((x&1)<<5)|((y&1)<<6)|(128 if (x+y)%5==0 else 0)
    return value,attribute


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gen',type=Path,default=BASE/'build/gen')
    parser.add_argument('--out',type=Path,default=OUT)
    parser.add_argument('--world-source',type=Path,default=BASE/'src/world.c')
    parser.add_argument('--helper-dir',type=Path,help='private assembly snapshot; missing files use production sources')
    parser.add_argument('--compressed',action='store_true',help='exercise the production WORLD_GRAPHICS_ZX0 path')
    args=parser.parse_args()
    OUT=args.out
    OUT.mkdir(parents=True,exist_ok=True)
    source_paths={name:(args.world_source if name=='world.c' else BASE/'src'/name)
                  for name in ('world.c','world.h','world_dma.c','world_memory.s','world_memory.h','world_retire_fast.s','video.s')}
    optional_helpers=('world_alloc_fast.s','world_acquire_fast.s','video_strip_pair.s','world_prepare_fast.s','world_zx0.s')
    for name in optional_helpers:
        path=BASE/'src'/name
        if args.helper_dir and(args.helper_dir/name).exists():path=args.helper_dir/name
        if name=='world_acquire_fast.s'and b'world_cache_ids'not in args.world_source.read_bytes():continue
        if path.exists():source_paths[name]=path
    if args.helper_dir:
        for name in source_paths:
            if name.endswith('.s')and(args.helper_dir/name).exists():source_paths[name]=args.helper_dir/name
    sources={name:path.read_bytes() for name,path in source_paths.items()}
    production_source=args.world_source.resolve()==(BASE/'src/world.c').resolve()
    # The production API must retain all coverage even after comment changes.
    # Explicit historical snapshots may predate preparation or fine retention.
    phased=production_source or b'void world_prepare('in sources['world.c']
    fine_phased=production_source or b'lookahead target stays hidden'in sources['world.c']
    split_units=b'prepare_fetch_plane'in sources['world.c']
    (OUT/'world-under-test.c').write_bytes(sources['world.c'])
    for name in sources:
        if name.endswith('.s')or name=='world_dma.c':(OUT/name).write_bytes(sources[name])
    header=(args.gen/'level_catalogue.h').read_text()
    header=re.sub(r'^\s*#define WORLD_GRAPHICS_ZX0\b[^\n]*\n','',header,flags=re.M)
    if args.compressed:header='#define WORLD_GRAPHICS_ZX0 1\n'+header
    (OUT/'level_catalogue.h').write_text(re.sub(r'#define LEVEL_COUNT \d+','#define LEVEL_COUNT 3',header))
    (OUT/'assets.h').write_text('#include <stdint.h>\nextern const uint8_t object_tiles[];\nextern const uint16_t object_palette[];\n')
    bank_data={}
    patterns=b''.join(pattern(i)for i in range(28410))
    level_chunks=[]
    for level in range(3):
        chunks=[]
        for cy in range(3):
            for cx in range(2):
                pairs=[logical(level,cx*32+x,cy*16+y)for y in range(16)for x in range(32)]
                chunks.append(bytes(v&255 for v,a in pairs)+bytes(v>>8 for v,a in pairs)+bytes(a for v,a in pairs))
        level_chunks.append(chunks)
    if args.compressed:
        sys.path.insert(0,str(BASE/'tools'))
        from pack_graphics import compress
        compiler=BASE/'.toolchain/gbdk/bin/gbcompress'
        cache=OUT/'zx0-cache'/hashlib.sha256(compiler.read_bytes()).hexdigest()[:16]
        cache.mkdir(parents=True,exist_ok=True)
        blocks=[patterns[offset:offset+1024]for offset in range(0,len(patterns),1024)]
        unique=list(dict.fromkeys(blocks+[chunk for chunks in level_chunks for chunk in chunks]))
        with ThreadPoolExecutor(max_workers=4)as pool:
            packed=dict(zip(unique,pool.map(lambda blob:compress(blob,compiler,cache),unique)))
        # The first complete stream ends at a ROM-bank boundary; no compressed
        # block may cross one. Both directories and data use nine-bit banks.
        bank=300;bank_data[bank]=bytearray(16384-len(packed[blocks[0]]))
        pointers=[]
        for block in blocks:
            data=packed[block]
            if len(bank_data[bank])+len(data)>16384:bank+=1;bank_data[bank]=bytearray()
            pointers.append((bank,0x4000+len(bank_data[bank])))
            bank_data[bank].extend(data)
        bank_data[299]=b''.join(struct.pack('<HH',*pointer)for pointer in pointers)
        pattern_pointer=(299,0x4000)
        chunk_pointers=[]
        for level,chunks in enumerate(level_chunks):
            data=bytearray();pointers=[]
            for chunk in chunks:
                pointers.append((500+level,0x4000+len(data)));data.extend(packed[chunk])
            assert len(data)<=16384,'compressed map fixture crosses a ROM bank'
            bank_data[500+level]=data;chunk_pointers.append(pointers)
    else:
        payload=bytes(16368)+patterns
        for offset in range(0,len(payload),16384):bank_data[300+offset//16384]=payload[offset:offset+16384]
        pattern_pointer=(300,32752)
        chunk_pointers=[]
        for level,chunks in enumerate(level_chunks):
            bank_data[500+level]=b''.join(chunks)
            chunk_pointers.append([(500+level,0x4000+i*1536)for i in range(6)])
    bank_sources=[]
    for bank,data in bank_data.items():
        path=OUT/('data%d.c'%bank);path.write_text('#include <stdint.h>\n#pragma bank %d\nconst uint8_t fixture_data%d[]={\n'%(bank,bank)+','.join(map(str,data))+'\n};\n');bank_sources.append(str(path))
    catalogue=['#include "level_catalogue.h"\n#pragma bank 14\n']
    for level in range(3):catalogue.append('const world_far_t directory%d[]={%s};\n'%(level,','.join('{%d,%d}'%pointer for pointer in chunk_pointers[level])))
    catalogue.append('const uint16_t palette_data[28]={0};\nconst uint8_t no_objects[1]={0};\nconst world_level_t world_levels[]={\n')
    for level,count in enumerate((1,3072,28410)):
        catalogue.append('{512,384,0,0,%d,{%d,%d},{14,%d},{14,16456},{14,16512},2,3,0},\n'%(count,*pattern_pointer,0x4000+level*24))
    catalogue.append('};\nconst char world_names[][20]={"UNIFORM","DIVERSE","HIGH IDS"};\nconst uint8_t killer_tiles[64]={0},object_tiles[128]={0};\nconst uint16_t killer_palette[4]={0},object_palette[8]={0};\n')
    (OUT/'catalogue.c').write_text(''.join(catalogue))
    commands=[]
    def path(level,start,moves):
        x,y=start;commands.append((level,1,x,y))
        for dx,dy in moves:
            x+=dx;y+=dy;assert 0<=x<=352 and 0<=y<=240;commands.append((level,0,x,y))
    square=[(8,8)]*8+[(8,-8)]*8+[(-8,-8)]*8+[(-8,8)]*8
    path(0,(64,64),square);path(0,(352,240),[(-8,-8)]*8+[(8,8)]*8)
    path(1,(248,120),[(8,8),(8,-8),(-8,-8),(-8,8)]*20)
    path(1,(352,240),[(-8,-8)]*16+[(8,8)]*16)
    path(2,(0,0),[(8,0)]*44+[(0,8)]*30+[(-8,0)]*44+[(0,-8)]*30)
    path(2,(248,120),[(8,8),(8,-8),(-8,-8),(-8,8)]*4)
    (OUT/'commands.h').write_text('typedef struct {uint8_t level,begin;uint16_t x,y;} command_t;\nstatic const command_t commands[]={\n'+','.join('{%d,%d,%d,%d}'%c for c in commands)+'\n};\n#define COMMAND_COUNT %d\n'%len(commands))
    (OUT/'inspect.c').write_text(('#define FIXTURE_PHASED 1\n'if phased else '')+('#define FIXTURE_SPLIT_UNITS 1\n'if split_units else '')+r'''#include "world-under-test.c"
+/* Read-only instrumentation shares the translation unit to inspect private
+ * production counters without changing or exporting the production module. */
+volatile uint8_t reference_failures,map_failures,pattern_failures,lookup_failures,cache_failures,mirror_failures;
+volatile uint16_t inspected_views,max_reference;
volatile uint16_t bad_level,bad_x,bad_y,bad_id,bad_target,bad_byte;
volatile uint8_t bad_expected,bad_actual;
+volatile uint16_t prepared_views,partial_preparations,full_preparations,expired_preparations,cancelled_preparations;
+volatile uint16_t max_pending_references;
+volatile uint8_t prepare_deadline_failures,max_prepare_elapsed_vblanks;
+volatile uint8_t pattern_block_conflict_checks;
+volatile uint8_t highest_pattern_block_checks;
+volatile uint16_t fine_pixel_checks;
+volatile uint8_t partial_plane_mask,publish_chunk_mask;
+volatile uint16_t cached_acquisition_partial_checks,split_extra_views,split_cases,split_plane_cancellations,split_publish_cancellations,split_mismatches;
+volatile uint8_t split_attempts[4],split_cancel_seen[4],split_final_kind[4];
+static uint16_t expected_references[CACHE_COUNT];
+void fixture_guard_check(void) NONBANKED;
+void fixture_verify(uint8_t level,uint16_t x,uint16_t y) BANKED {
+ uint16_t tx,ty,address,slot,target,id,i,mirror,total=0;uint8_t tile,attribute,expected,byte;
+ DISPLAY_OFF;
+ fixture_guard_check();
+ for(i=0;i<CACHE_COUNT;++i)expected_references[i]=0;
+ if(SCX_REG!=(uint8_t)x || SCY_REG!=(uint8_t)y)map_failures=1;
+ for(ty=y/8;ty<y/8+19;++ty)for(tx=x/8;tx<x/8+21;++tx) {
+  address=0x9800+(ty%32)*32+tx%32;VBK_REG=0;tile=*(volatile uint8_t*)address;
+  VBK_REG=1;attribute=*(volatile uint8_t*)address;target=tile+(attribute&8?256:0);
+  if((target>=252 && target<256) || target>=448){map_failures=1;continue;}
+  slot=target<252?target:target-4;++expected_references[slot];
+  mirror=*(volatile uint16_t*)(0xb000U+2U*((ty&31U)*32U+(tx&31U)));
+  if(mirror!=slot)mirror_failures=1;
+  if(tx>=64 || ty>=48){id=0;expected=0;}
+  else {
+   id=level==0?0:level==1?ty*64+tx:28000U+(ty*64+tx)%410U;
+   expected=level==0?0:(uint8_t)(((tx+2*ty)%7)|((tx&1)<<5)|((ty&1)<<6)|((tx+ty)%5==0?128:0));
+  }
+  if((attribute&247)!=expected || cached_ids[slot]!=id)map_failures=1;
+  VBK_REG=target>=256;
+  for(i=0;i<16;++i) {
+   byte=i==0?(uint8_t)id:i==1?(uint8_t)(id>>8):(uint8_t)(id*37U+i*19U+(id>>(i&7)));
+   if(*(volatile uint8_t*)(0x8000+(uint16_t)tile*16+i)!=byte && !pattern_failures) {bad_level=level;bad_x=tx;bad_y=ty;bad_id=id;bad_target=target;bad_byte=i;bad_expected=byte;bad_actual=*(volatile uint8_t*)(0x8000+(uint16_t)tile*16+i);pattern_failures=1;}
+  }
+ }
+#ifdef FIXTURE_PHASED
+ if(prepare_stage) {
+  ++prepared_views;
+  for(i=0;i<prepare_added_count;++i)++expected_references[prepare_added[i]];
+#ifdef FIXTURE_SPLIT_UNITS
+  if((prepare_stage==PREP_COL_FETCH || prepare_stage==PREP_ROW_FETCH) && prepare_fetch_plane)
+   partial_plane_mask|=1U<<prepare_fetch_plane;
+  if((prepare_stage==PREP_COL_PUBLISH || prepare_stage==PREP_ROW_PUBLISH) && prepare_index && prepare_index<prepare_count)
+   publish_chunk_mask|=1U<<(prepare_index/7);
+  if(level==0 && prepare_added_count && prepare_added_count<39 &&
+     (prepare_stage==PREP_COL_ACQUIRE || prepare_stage==PREP_ROW_ACQUIRE))++cached_acquisition_partial_checks;
+#endif
+ }
+#endif
+ for(i=0;i<CACHE_COUNT;++i) {
+  total+=references[i];
+  if(references[i]>max_reference)max_reference=references[i];
+  if(references[i]!=expected_references[i])reference_failures|=1;
+#ifdef WORLD_FREE_BITMAP
+  if(((free_bits[i>>3]>>(i&7))&1)!=(references[i]==0))reference_failures|=2;
+#endif
+  if(cached_ids[i]!=INVALID && world_lookup_get(cached_ids[i])!=i)lookup_failures=1;
+ }
+#ifdef FIXTURE_PHASED
+ if(total!=399U+prepare_added_count || total>438U)reference_failures|=4;
+ if(total>max_pending_references)max_pending_references=total;
+#else
+ if(total!=399)reference_failures=1;
+#endif
+ if(level==0 && max_reference<399)reference_failures|=8;
+ if(world_cache_failures)cache_failures=1;
+ VBK_REG=0;++inspected_views;DISPLAY_ON;
+}
+#ifdef FIXTURE_PHASED
+static void fixture_budget_check(uint16_t start) {
+ uint16_t now,elapsed;
+ __critical {now=sys_time;if(IF_REG&VBL_IFLAG)++now;}
+ elapsed=now-start;
+ if(elapsed>max_prepare_elapsed_vblanks)max_prepare_elapsed_vblanks=elapsed;
+ if(elapsed>=2)prepare_deadline_failures=1;
+}
+void fixture_prepare(uint16_t ox,uint16_t oy,uint16_t x,uint16_t y,uint8_t mode) BANKED {
+ uint8_t attempt;uint16_t start;
+ if(!mode) {
+  world_prepare(ox,oy,x,y,sys_time-2);
+  if(prepare_stage || prepare_added_count)reference_failures|=16;
+  ++expired_preparations;
+ } else if(mode==1) {
+  for(attempt=0;attempt<10;++attempt) {
+   start=sys_time;world_prepare(ox,oy,x,y,start);fixture_budget_check(start);
+   if(prepare_stage==PREP_READY)break;
+   vsync();
+  }
+  if(prepare_stage!=PREP_READY)reference_failures|=32;
+  ++full_preparations;
+ } else {
+  while(LY_REG>=60);while(LY_REG<60);
+  start=sys_time-1;world_prepare(ox,oy,x,y,start);fixture_budget_check(start);
+  if(prepare_stage && prepare_stage!=PREP_READY && prepare_added_count)++partial_preparations;
+ }
+}
+void fixture_cancel(uint16_t ox,uint16_t oy,uint16_t x,uint16_t y) BANKED {
+ uint8_t had=prepare_added_count;
+#ifdef FIXTURE_SPLIT_UNITS
+ if((prepare_stage==PREP_COL_FETCH || prepare_stage==PREP_ROW_FETCH) && prepare_fetch_plane)++split_plane_cancellations;
+ if((prepare_stage==PREP_COL_PUBLISH || prepare_stage==PREP_ROW_PUBLISH) && prepare_index && prepare_index<prepare_count)++split_publish_cancellations;
+#endif
+ world_prepare(ox,oy,x,y,sys_time-2);
+ if(prepare_stage || prepare_added_count)reference_failures|=64;
+ if(had)++cancelled_preparations;
+}
+void fixture_expect_pending(uint8_t count) BANKED {
+ if(prepare_added_count!=count || (count && prepare_stage!=PREP_READY)
+    || (!count && prepare_stage!=PREP_NONE))reference_failures|=128;
+ ++fine_pixel_checks;
+}
+#ifdef FIXTURE_SPLIT_UNITS
+void fixture_prepare_late(uint16_t ox,uint16_t oy,uint16_t x,uint16_t y,uint8_t line) BANKED {
+ uint16_t start;
+ while(LY_REG>=line);while(LY_REG<line);
+ start=sys_time-1;world_prepare(ox,oy,x,y,start);fixture_budget_check(start);
+}
+uint8_t fixture_partial_kind(void) BANKED {
+ if((prepare_stage==PREP_COL_FETCH || prepare_stage==PREP_ROW_FETCH) && prepare_fetch_plane)return 1;
+ if((prepare_stage==PREP_COL_PUBLISH || prepare_stage==PREP_ROW_PUBLISH) && prepare_index && prepare_index<prepare_count)return 2;
+ return prepare_stage==PREP_READY?3:0;
+}
+uint8_t fixture_late_line(uint8_t level,uint8_t attempt) BANKED {
+ if(prepare_stage==PREP_NONE)return 120;
+ if(prepare_stage==PREP_COL_FETCH || prepare_stage==PREP_ROW_FETCH)return 124;
+ if(prepare_stage==PREP_COL_PUBLISH || prepare_stage==PREP_ROW_PUBLISH)return 126;
+ return level?123:(attempt%4==3?135:130);
+}
+#endif
+#endif
+void fixture_probe_start(void) NONBANKED;
+void fixture_probe_end(void) NONBANKED;
+void fixture_compressed_cache_probe(void) BANKED {
+#ifdef WORLD_GRAPHICS_ZX0
+ uint8_t attempt,i,expected,which;uint16_t id;
+ DISPLAY_OFF;world_select(1);world_begin(0,0);
+ /* Blocks0/16 share slot0, and15/31 share slot15 at bank3 BC00-BFFF.
+  * Check hits, conflicting reloads and the last physical SRAM byte. */
+ for(which=0;which<2;++which)for(attempt=0;attempt<3;++attempt) {
+  id=(which?1023:0)+(attempt==1?1024:0);world_cache_upload(0,id);
+  if(pattern_cache_ids[(id>>6)&15]!=(id>>6))cache_failures=1;
+  VBK_REG=0;
+  for(i=0;i<16;++i) {
+   expected=i==0?(uint8_t)id:i==1?(uint8_t)(id>>8):(uint8_t)(id*37U+i*19U+(id>>(i&7)));
+   if(*(volatile uint8_t*)(0x8000+i)!=expected)pattern_failures=1;
+  }
+  ++pattern_block_conflict_checks;
+  if(which)++highest_pattern_block_checks;
+  fixture_guard_check();
+ }
+#endif
+}
+void fixture_probe_setup(uint8_t which) BANKED {
+ uint16_t i;uint8_t free;
+ DISPLAY_OFF;world_select(1);world_lookup_clear(3072);next_slot=which==2?7:0;
+ fixture_guard_check();
+#ifdef WORLD_FREE_BITMAP
+ for(i=0;i<FREE_BYTES;++i)free_bits[i]=0;
+#endif
+ for(i=0;i<CACHE_COUNT;++i) {
+  free=which==1?i>=437:i<7;
+  references[i]=!free;cached_ids[i]=free?INVALID:i;
+  if(!free)world_lookup_set(i,i);
+#ifdef WORLD_FREE_BITMAP
+  else free_bits[i>>3]|=1U<<(i&7);
+#endif
+ }
+}
+uint16_t fixture_acquire_probe(void) BANKED {
+ uint16_t result;
+ fixture_probe_start();result=acquire(2000);fixture_probe_end();return result;
+}
+'''.replace('\n+','\n'))
    (OUT/'check.c').write_text(('#define FIXTURE_PHASED 1\n'if phased else '')+('#define FIXTURE_FINE_PHASED 1\n'if fine_phased else '')+('#define FIXTURE_SPLIT_UNITS 1\n'if split_units else '')+r'''#include <gb/gb.h>
+#include <gb/cgb.h>
+#include "world.h"
+#include "commands.h"
+void fixture_verify(uint8_t level,uint16_t x,uint16_t y) BANKED;
+void fixture_probe_setup(uint8_t which) BANKED;
+uint16_t fixture_acquire_probe(void) BANKED;
+void fixture_compressed_cache_probe(void) BANKED;
+void fixture_probe_start(void) NONBANKED {}
+void fixture_probe_end(void) NONBANKED {}
+void fixture_guard_init(void) NONBANKED {}
+void fixture_guard_check(void) NONBANKED {}
+#ifdef FIXTURE_PHASED
+void fixture_prepare(uint16_t ox,uint16_t oy,uint16_t x,uint16_t y,uint8_t mode) BANKED;
+void fixture_cancel(uint16_t ox,uint16_t oy,uint16_t x,uint16_t y) BANKED;
+void fixture_expect_pending(uint8_t count) BANKED;
+#endif
+#ifdef FIXTURE_SPLIT_UNITS
+void fixture_prepare_late(uint16_t ox,uint16_t oy,uint16_t x,uint16_t y,uint8_t line) BANKED;
+uint8_t fixture_partial_kind(void) BANKED;
+uint8_t fixture_late_line(uint8_t level,uint8_t attempt) BANKED;
+extern volatile uint16_t inspected_views,split_extra_views,split_cases,split_mismatches;
+extern volatile uint8_t split_attempts[4],split_cancel_seen[4],split_final_kind[4];
+#endif
+volatile uint8_t cache_done,select_failures;
+volatile uint8_t probe_case;
+volatile uint16_t cache_irq;
+static void tick(void){++cache_irq;}
+void main(void) {
+ uint16_t i,x=0,y=0,mx,my,px,py,ox,oy;uint8_t variant,direction,n,pending,level,kind,cancel_done;
+ int8_t dx,dy;
+ cpu_fast();LCDC_REG|=LCDCF_BG8000;add_VBL(tick);set_interrupts(VBL_IFLAG);enable_interrupts();
+ fixture_guard_init();fixture_guard_check();
+ for(variant=0;variant<
+#ifdef FIXTURE_PHASED
+ 4
+#else
+ 1
+#endif
+ ;++variant)for(i=0;i<COMMAND_COUNT;++i) {
+  const command_t *c=&commands[i];
+  if(c->begin) {
+   DISPLAY_OFF;
+   if(!world_select(c->level))select_failures=1;
+   fixture_guard_check();
+   world_begin(c->x,c->y);DISPLAY_ON;
+  } else {
+#ifdef FIXTURE_PHASED
+   if(variant) {
+    fixture_prepare(x,y,c->x,c->y,variant-1);
+    fixture_verify(c->level,x,y);
+    if(variant==3) {
+     mx=x?x-8:x+8;my=y;
+     if(mx==c->x && my==c->y){mx=x;my=y?y-8:y+8;}
+     fixture_cancel(x,y,mx,my);fixture_verify(c->level,x,y);
+     fixture_prepare(x,y,mx,my,2);fixture_verify(c->level,x,y);
+    }
+   }
+#endif
+   world_scroll(x,y,c->x,c->y);
+  }
+  x=c->x;y=c->y;fixture_verify(c->level,x,y);
+ }
+#ifdef FIXTURE_PHASED
+ /* Starting another course must discard a fully prepared old-course view. */
+ fixture_prepare(x,y,x+8,y+8,1);fixture_verify(2,x,y);
+ DISPLAY_OFF;world_select(0);world_begin(64,64);DISPLAY_ON;fixture_verify(0,64,64);
+#endif
+#ifdef FIXTURE_FINE_PHASED
+ /* Retain each predicted incoming union through seven fine-pixel moves. */
+ for(direction=0;direction<9;++direction) {
+  dx=(int8_t)(direction%3)-1;dy=(int8_t)(direction/3)-1;if(!dx&&!dy)continue;
+  x=dx<0?263:dx?256:259;y=dy<0?135:dy?128:131;
+  DISPLAY_OFF;world_select(1);world_begin(x,y);DISPLAY_ON;fixture_verify(1,x,y);
+  px=x+(int16_t)dx*8;py=y+(int16_t)dy*8;pending=dx?(dy?39:19):21;
+  fixture_prepare(x,y,px,py,1);fixture_verify(1,x,y);fixture_expect_pending(pending);
+  for(n=0;n<7;++n) {
+   ox=x;oy=y;x+=dx;y+=dy;world_scroll(ox,oy,x,y);
+   world_prepare(x,y,px,py,sys_time-2);fixture_verify(1,x,y);fixture_expect_pending(pending);
+  }
+  ox=x;oy=y;x+=dx;y+=dy;world_scroll(ox,oy,x,y);fixture_verify(1,x,y);fixture_expect_pending(0);
+ }
+ /* Reverse fine motion, then replace a ready prediction on the other side. */
+ DISPLAY_OFF;world_select(1);world_begin(132,132);DISPLAY_ON;fixture_verify(1,132,132);
+ fixture_prepare(132,132,140,132,1);fixture_verify(1,132,132);fixture_expect_pending(19);
+ world_scroll(132,132,131,132);fixture_verify(1,131,132);fixture_expect_pending(19);
+ fixture_prepare(131,132,123,132,1);fixture_verify(1,131,132);fixture_expect_pending(19);
+ world_scroll(131,132,127,132);fixture_verify(1,127,132);fixture_expect_pending(0);
+ /* A diagonal guess must cancel cleanly when only one axis crosses. */
+ DISPLAY_OFF;world_select(1);world_begin(132,132);DISPLAY_ON;fixture_verify(1,132,132);
+ fixture_prepare(132,132,140,140,1);fixture_verify(1,132,132);fixture_expect_pending(39);
+ world_scroll(132,132,133,133);fixture_verify(1,133,133);fixture_expect_pending(39);
+ world_scroll(133,133,136,133);fixture_verify(1,136,133);fixture_expect_pending(0);
+#endif
+#ifdef FIXTURE_SPLIT_UNITS
+ split_extra_views=inspected_views;
+ for(variant=0;variant<4;++variant) {
+  level=variant?variant==1?1:2:0;x=variant==1?263:255;y=variant==1?135:127;
+  px=variant==1?x-8:x+8;py=variant==3?y:variant==1?y-8:y+8;
+  DISPLAY_OFF;world_select(level);world_begin(x,y);DISPLAY_ON;fixture_verify(level,x,y);cancel_done=0;
+  for(n=0;n<120;++n) {
+   fixture_prepare_late(x,y,px,py,fixture_late_line(level,n));fixture_verify(level,x,y);
+   kind=fixture_partial_kind();
+   if(variant==3 && kind==2) {
+    world_scroll(x,y,x,y+8);y+=8;fixture_verify(level,x,y);fixture_expect_pending(0);++split_mismatches;break;
+   }
+   if(variant<2 && !cancel_done && kind==variant+1) {
+    fixture_cancel(x,y,x-8,y);fixture_verify(level,x,y);cancel_done=1;continue;
+   }
+   if(kind==3) {
+    world_scroll(x,y,px,py);fixture_verify(level,px,py);fixture_expect_pending(0);break;
+   }
+   ox=x;oy=y;x^=1;y^=1;world_scroll(ox,oy,x,y);fixture_verify(level,x,y);
+  }
+  if(n==120 || (variant<2 && !cancel_done) || (variant==3 && !split_mismatches))select_failures=1;
+  split_attempts[variant]=n;split_cancel_seen[variant]=cancel_done;split_final_kind[variant]=kind;
+  ++split_cases;
+ }
+ split_extra_views=inspected_views-split_extra_views;
+#endif
+ if(world_select(3))select_failures=1;
+ fixture_guard_check();
+ fixture_compressed_cache_probe();
+ for(probe_case=0;probe_case<3;++probe_case) {
+  fixture_probe_setup(probe_case);
+  if(fixture_acquire_probe()!=(probe_case==1?437:0))select_failures=1;
+ }
+ DISPLAY_ON;
+ fixture_guard_check();
+ cache_done=1;while(1)vsync();
+}
+'''.replace('\n+','\n'))
    flags=[str(BASE/'.toolchain/gbdk/bin/lcc'),'-msm83:gb','-Wf--opt-code-size','-Wf--max-allocs-per-node','-Wf100000','-Wm-yC','-Wm-yt0x1a','-Wm-yo512','-Wm-ya4','-Wl-m','-Wl-j','-I'+str(OUT),'-I'+str(BASE/'src')]
    # Keep linked instruction listings for executable code only. Looking for
    # opcode bytes across ROM data would corrupt fixtures when hooks replace
    # a coincidentally matching graphics byte with the breakpoint opcode.
    code_names=['check.c','inspect.c','world_dma.c','world_memory.s','world_retire_fast.s','video.s']
    code_names.extend(name for name in optional_helpers if name in sources)
    objects=[];compile_log=[]
    def build(command):
        built=subprocess.run(command,capture_output=True,text=True)
        compile_log.append(built.stdout+built.stderr)
        (OUT/'compile.log').write_text(''.join(compile_log))
        assert built.returncode==0,built.stdout+built.stderr
    for name in code_names:
        obj=OUT/(Path(name).stem+'.o');objects.append(obj)
        build(flags+['-Wa-l','-c','-o',str(obj),str(OUT/name)])
    build(flags+['-Wl-u','-o',str(OUT/'check.gbc'),*map(str,objects),str(OUT/'catalogue.c'),*bank_sources])
    symbols={k:int(v,16)for k,v in re.findall(r'DEF (_\w+) 0x([0-9A-Fa-f]+)',(OUT/'check.noi').read_text())}
    rom=(OUT/'check.gbc').read_bytes()
    assert rom[0x149]==3,('fixture must declare 32 KiB SRAM',rom[0x149])
    p=PyBoy(str(OUT/'check.gbc'),window='null',sound_emulated=False,cgb=True);p.set_emulation_speed(0)
    launches=Counter();launch_states={};dma_durations=Counter();probe_start=None;probe_cycles={};hook_errors=[]
    ram_requests=Counter();ram_write_sites=[];last_ram_bank=0
    guard_checks=0;guard_failures=[];bank_restore_failures=[]
    save_guard=bytes((i*37+(i>>8)*19+0x5b)&255 for i in range(2048))
    high_guard=bytes((i*29+0x67)&255 for i in range(16))
    def observe(callback):
        def checked(context):
            try:callback(context)
            except BaseException as error:hook_errors.append(str(error))
        return checked
    # Probe MBC5 through its mapped registers, including the highest byte of
    # each real bank. PyBoy aliases requested banks modulo the header size;
    # the instruction hooks below therefore validate the unmasked request.
    p.memory[0x0000]=0x0a
    for bank in range(4):
        p.memory[0x4000]=bank;p.memory[0xbfff]=0x60+bank
    ram_aliases=[]
    for bank in range(16):
        p.memory[0x4000]=bank;ram_aliases.append(p.memory[0xbfff]-0x60)
    assert ram_aliases==[bank%4 for bank in range(16)],('unexpected PyBoy MBC5 RAM mapping',ram_aliases)
    p.memory[0x4000]=8;p.memory[0xbffe]=0xa7
    p.memory[0x4000]=0
    assert p.memory[0xbffe]==0xa7,'out-of-range write did not alias the selected RAM bank'
    p.memory[0x0000]=0
    def guard_init(_):
        # Initial SRAM contents are deliberate fixture input; no game state
        # or ROM data is substituted while the runtime is executing.
        p.memory[0,0xb800:0xbfff]=save_guard[:-1];p.memory[0,0xbfff]=save_guard[-1]
        p.memory[3,0xbff0:0xbfff]=high_guard[:-1];p.memory[3,0xbfff]=high_guard[-1]
    def guard_check(_):
        nonlocal guard_checks
        guard_checks+=1
        if last_ram_bank and not bank_restore_failures:
            bank_restore_failures.append({'checkpoint':guard_checks,'requested_bank':last_ram_bank})
        regions=[(0,0xb800,save_guard)]
        if not args.compressed:regions.append((3,0xbff0,high_guard))
        for bank,address,expected in regions:
            actual=bytes(p.memory[bank,address:address+len(expected)-1])+bytes([p.memory[bank,address+len(expected)-1]])
            if actual!=expected and not guard_failures:
                offset=next(i for i,(a,b)in enumerate(zip(actual,expected))if a!=b)
                guard_failures.append({'checkpoint':guard_checks,'bank':bank,'address':address+offset,'expected':expected[offset],'actual':actual[offset]})
    p.hook_register(0,symbols['_fixture_guard_init'],observe(guard_init),None)
    p.hook_register(0,symbols['_fixture_guard_check'],observe(guard_check),None)
    def ram_selected(site):
        nonlocal last_ram_bank
        last_ram_bank=p.register_file.A;ram_requests[last_ram_bank]+=1
        assert last_ram_bank<4,('RAM bank request exceeds 32 KiB cartridge',site,last_ram_bank)
    for obj in objects:
        bank=0
        for line in obj.with_suffix('.rst').read_text().splitlines():
            area=re.search(r'\.area\s+(_\w+)',line)
            if area:
                suffix=re.fullmatch(r'_CODE_(\d+)',area[1]);bank=int(suffix[1])if suffix else 0
            instruction=re.match(r'\s*([0-9A-Fa-f]{8})\s+EA 00 40\s+\[.*\]\s+\d+\s+ld\b',line)
            if instruction:
                address=int(instruction[1],16)&0xffff
                offset=bank*16384+(address&0x3fff)if bank else address
                assert rom[offset:offset+3]==b'\xea\x00\x40',('linked RAM-write listing differs from ROM',obj.name,bank,address)
                site=(bank,address);ram_write_sites.append(site)
                p.hook_register(bank,address,observe(ram_selected),site)
    assert ram_write_sites,'no linked RAM bank writes were observed'
    start=symbols['_world_upload_tile']
    end=min(address for address in symbols.values()if start<address<0x8000)
    dma_writes=[start+i for i in range(end-start-1)if rom[start+i:start+i+2]==b'\xe0\x55']
    assert len(dma_writes)in(2,3),('expected production GDMA launch sites',dma_writes)
    def dma_launch(address):
        lcd_on=bool(p.memory[0xff40]&128);mode=p.memory[0xff41]&3
        category='lcd_off' if not lcd_on else 'hblank' if mode==0 else 'vblank' if mode==1 else 'oam_scan' if mode==2 else 'unsafe'
        launches[category]+=1
        assert category!='unsafe',('GDMA started while VRAM is inaccessible',mode,p.memory[0xff44])
        assert p.register_file.A==0,'background upload must transfer exactly one GDMA block'
        launch_states[address]=(lcd_on,mode,p.memory[0xff44],p._cycles())
    def dma_completed(address):
        state=launch_states.pop(address,None)
        if state is None:return  # shared epilogue may be reached from another launch site
        lcd_on,mode,line,cycles=state
        dma_durations[p._cycles()-cycles]+=1
        if lcd_on:
            after=p.memory[0xff41]&3
            assert after==mode and after!=3,('GDMA outlasted its safe visibility window',mode,after,line,p.memory[0xff44])
            if mode in (0,2):assert p.memory[0xff44]==line,'short-window GDMA crossed a scanline'
    for address in dma_writes:
        p.hook_register(0,address,observe(dma_launch),address)
        p.hook_register(0,address+2,observe(dma_completed),address)
    def started(_):
        nonlocal probe_start
        probe_start=p._cycles()
    def ended(_):
        probe_cycles[p.memory[symbols['_probe_case']]]=p._cycles()-probe_start
    p.hook_register(0,symbols['_fixture_probe_start'],observe(started),None)
    p.hook_register(0,symbols['_fixture_probe_end'],observe(ended),None)
    def word(name):
        address=symbols['_'+name];return p.memory[address]+256*p.memory[address+1]
    try:
        for _ in range(2500 if phased else 500):
            p.tick(100,False)
            if p.memory[symbols['_cache_done']]:break
        expected_views=len(commands) if not phased else len(commands)*4+5*sum(not command[1]for command in commands)+2
        if fine_phased:expected_views+=89
        if split_units:expected_views+=word('split_extra_views')
        report={'status':'passed','fixture':'synthetic source maps; production bank6 module, LCD-on scrolls, read-only counter inspection',
            'graphics_codec':'zx0'if args.compressed else 'raw',
            'cartridge':{'rom_bytes':len(rom),'ram_header_code':rom[0x149],'ram_bytes':32768,'ram_banks':4},
            'ram_bank_checks':{'requested_banks':dict(ram_requests),'instruction_sites':ram_write_sites,
                               'pyboy_requested_bank_aliases':ram_aliases,'pyboy_out_of_range_write_aliases':True,
                               'restoration_failures':bank_restore_failures},
            'save_guard':{'bank':0,'start':0xb800,'bytes':len(save_guard),'checks':guard_checks,'failures':guard_failures},
            'highest_ram_bank_guard':{'bank':3,'start':0xbff0,'bytes':len(high_guard),'preserved_during_raw_runtime':not args.compressed,
                                      'compressed_pattern_checks':p.memory[symbols['_highest_pattern_block_checks']]},
            'source_sha256':{name:hashlib.sha256(data).hexdigest()for name,data in sources.items()},
            'source_still_current':all(source_paths[name].read_bytes()==data for name,data in sources.items()),
            'rom_sha256':hashlib.sha256((OUT/'check.gbc').read_bytes()).hexdigest(),
            'expected_views':expected_views,'verified_views':word('inspected_views'),'max_single_pattern_references':word('max_reference'),
            'phased_preparation':phased,
            'fine_pixel_preparation':fine_phased,'fine_pixel_checks':word('fine_pixel_checks'),
            'split_work_units':split_units,
            'split_checks':{name:p.memory[symbols['_'+name]] if name.endswith('_mask')else word(name)
                            for name in('partial_plane_mask','publish_chunk_mask','cached_acquisition_partial_checks',
                                        'split_cases','split_extra_views','split_plane_cancellations','split_publish_cancellations','split_mismatches')},
            'preparation_checks':{name:word(name)for name in('prepared_views','partial_preparations','full_preparations','expired_preparations','cancelled_preparations','max_pending_references')},
            'prepare_deadline_failures':p.memory[symbols['_prepare_deadline_failures']],
            'max_prepare_elapsed_vblanks':p.memory[symbols['_max_prepare_elapsed_vblanks']],
            'pattern_block_conflict_checks':p.memory[symbols['_pattern_block_conflict_checks']],
            'gdma_launch_modes':dict(launches),
            'gdma_instruction_and_transfer_cycles':dict(dma_durations),
            'allocator_probe_cycles':probe_cycles,
            'compiler_register_allocation_limit':100000,
            'observer_errors':hook_errors,
            'gdma_stall_observed_in_cpu_cycles':all(n>=76 for n in dma_durations),
            'gdma_hardware_safety_bound_cycles':{'poll_and_launch_max':76,'block':64,'total':140,'mode2_min':160},
            'interrupts':word('cache_irq'),'first_pattern_mismatch':{name:word('bad_'+name)for name in('level','x','y','id','target','byte')},'bad_expected':p.memory[symbols['_bad_expected']],'bad_actual':p.memory[symbols['_bad_actual']],'failures':{name:p.memory[symbols['_'+name+'_failures']] for name in('reference','map','pattern','lookup','cache','mirror','select')},'hardware_tested':False}
        assert p.memory[symbols['_cache_done']],'cache fixture did not finish'
        assert report['verified_views']==expected_views and 399<=report['max_single_pattern_references']<=(438 if phased else 399),report
        assert report['pattern_block_conflict_checks']==(6 if args.compressed else 0),report
        assert report['highest_ram_bank_guard']['compressed_pattern_checks']==(3 if args.compressed else 0),report
        assert guard_checks>=report['verified_views'] and not guard_failures and not bank_restore_failures,report
        assert ram_requests and all(0<=bank<4 for bank in ram_requests),report
        if args.compressed:assert all(ram_requests[bank] for bank in range(4)),report
        if phased:
            assert all(report['preparation_checks'][name]>0 for name in('partial_preparations','full_preparations','expired_preparations','cancelled_preparations')),report
            assert report['preparation_checks']['max_pending_references']==438,report
            assert not report['prepare_deadline_failures'],report
        if fine_phased:assert report['fine_pixel_checks']==79+(4 if split_units else 0),report
        if split_units:
            checks=report['split_checks']
            assert checks['partial_plane_mask']&6==6 and checks['publish_chunk_mask']&6==6,report
            assert checks['split_cases']==4 and checks['split_mismatches']==1,report
            assert all(checks[name]>0 for name in('cached_acquisition_partial_checks','split_plane_cancellations','split_publish_cancellations')),report
        assert not any(report['failures'].values()),report
        assert not hook_errors,report
        assert not launch_states and sum(dma_durations.values())==sum(launches.values()),'missing DMA completion observation'
        assert report['source_still_current'],'production sources changed during test; rerun current source'
    except BaseException:
        if 'report'in locals():report['status']='failed';(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        raise
    finally:p.stop(save=False)
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
