/* Lossless visible-pattern cache. Old visible patterns remain referenced until
 * all entering strips have been uploaded, leaving enough space for a diagonal
 * scroll even when every tile in the viewport has a different pattern. */
#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
#include <string.h>
#include "world.h"
#include "world_memory.h"

#pragma bank 6
#define CACHE_COUNT 444
#define INVALID 65535U
#define WORLD_FREE_BITMAP 1
#define FREE_BYTES ((CACHE_COUNT+7)/8)
world_level_t game_world;
game_object_t game_objects[LEVEL_OBJECT_MAX];
uint8_t world_level_index;
uint16_t world_uploads,world_cache_failures;
/* Internal cache symbols are shared with the near bank6 acquisition kernel. */
uint16_t world_cache_ids[CACHE_COUNT],world_cache_next;
uint16_t world_cache_references[CACHE_COUNT];
uint8_t world_cache_free_bits[FREE_BYTES];
#define cached_ids world_cache_ids
#define next_slot world_cache_next
#define references world_cache_references
#define free_bits world_cache_free_bits
static const uint8_t slot_masks[8]={1,2,4,8,16,32,64,128};
static uint8_t strip_low[21],strip_high[21],strip_attrs[21];
static uint8_t output_tiles[21],output_attrs[21];
static uint16_t output_slots[21];
static uint8_t tile_buffer[16];
static uint16_t palettes[28];
static uint16_t retired[40];
static uint8_t retired_count;
static uint16_t last_chunk;
static world_far_t chunk;

/* Prepare only incoming ring cells, which are outside the old21x19 view.
 * Old399 references and at most39 new ones coexist within444 cache slots. */
enum {PREP_NONE,PREP_COL_FETCH,PREP_COL_ACQUIRE,PREP_COL_PUBLISH,
      PREP_ROW_FETCH,PREP_ROW_ACQUIRE,PREP_ROW_PUBLISH,PREP_READY};
static uint8_t prepare_stage,prepare_horizontal,prepare_vertical;
static uint8_t prepare_index,prepare_count,prepare_added_count;
static uint16_t prepare_old_x,prepare_old_y,prepare_x,prepare_y;
static uint16_t prepare_left,prepare_top,prepare_old_left,prepare_old_top;
static uint16_t prepare_strip_x,prepare_strip_y;
static uint16_t prepare_added[39];


void gbc_video_strip_pair(uint8_t x,uint8_t y,uint8_t vertical,uint8_t count,const uint8_t *tiles,const uint8_t *attrs) __sdcccall(0);
void world_upload_tile(uint16_t bank,uint16_t source,uint16_t pattern) NONBANKED;
uint16_t world_find_free(uint16_t next,uint8_t *bitmap) __sdcccall(0);
void world_refs_retire(uint16_t *refs,const uint16_t *slots,uint8_t count,uint8_t *bitmap) __sdcccall(0);

void world_level_name(uint8_t index,char *dest) NONBANKED {
    if(index>=LEVEL_COUNT){dest[0]=0;return;}
    world_far_copy(14,(const uint8_t *)world_names+(uint16_t)index*20,(uint8_t *)dest,20);
    dest[19]=0;
}

uint8_t world_select(uint8_t index) BANKED {
    if(index>=LEVEL_COUNT)return 0;
    world_far_copy(14,(const uint8_t *)world_levels+(uint16_t)index*sizeof(world_level_t),
                   (uint8_t *)&game_world,sizeof(game_world));
    world_far_copy(game_world.objects.bank,(const uint8_t *)game_world.objects.address,
                   (uint8_t *)game_objects,(uint16_t)game_world.object_count*sizeof(game_object_t));
    world_far_copy(game_world.palette.bank,(const uint8_t *)game_world.palette.address,
                   (uint8_t *)palettes,sizeof(palettes));
    world_level_index=index;last_chunk=INVALID;
    return 1;
}

void world_game_assets(void) BANKED {
    world_far_copy(14,killer_tiles,tile_buffer,16);VBK_REG=0;set_sprite_data(252,1,tile_buffer);
    world_far_copy(14,killer_tiles+32,tile_buffer,16);set_sprite_data(253,1,tile_buffer);
    world_far_copy(14,killer_tiles+16,tile_buffer,16);set_sprite_data(254,1,tile_buffer);
    world_far_copy(14,killer_tiles+48,tile_buffer,16);set_sprite_data(255,1,tile_buffer);
    world_far_copy(14,(const uint8_t *)killer_palette,tile_buffer,8);set_sprite_palette(5,1,(const uint16_t *)tile_buffer);
    world_far_copy(14,(const uint8_t *)object_palette,tile_buffer,16);set_sprite_palette(1,2,(const uint16_t *)tile_buffer);
    VBK_REG=1;
    {uint8_t i;for(i=0;i<8;++i){world_far_copy(14,object_tiles+(uint16_t)((i&4)|((i&1)<<1)|((i&2)>>1))*16,tile_buffer,16);set_sprite_data(248+i,1,tile_buffer);}}
    VBK_REG=0;set_bkg_palette(0,7,palettes);
}

#define physical(slot) ((slot)<252U ? (slot) : (slot)+4U)

void world_cache_upload(uint16_t slot,uint16_t id) __sdcccall(0) {
    uint16_t offset=game_world.patterns.address+((id&1023)<<4);
    uint16_t bank=game_world.patterns.bank+(id>>10);
    uint16_t target=physical(slot);
    /* A pattern base may begin partway through a bank. */
    if(offset>=0x8000U){offset-=0x4000; ++bank;}
    world_upload_tile(bank,offset,target);
    ++world_uploads;
}

#ifndef WORLD_ACQUIRE_C_REFERENCE
uint16_t world_acquire_fast(uint16_t id) __sdcccall(0);
#define acquire world_acquire_fast
#else
static uint16_t acquire(uint16_t id) {
    uint16_t slot=world_lookup_get(id),old;
    if(slot<CACHE_COUNT) {
        if(!references[slot])free_bits[slot>>3]&=~slot_masks[slot&7];
        ++references[slot];return slot;
    }
    slot=next_slot;
    if(references[slot]) {
        /* The helper clears exactly the chosen free bit, preserving the
         * circular selection order and the direct unreferenced-slot path. */
        slot=world_find_free(slot,free_bits);
        if(slot>=CACHE_COUNT){++world_cache_failures;return 0;}
    } else {
        free_bits[slot>>3]&=~slot_masks[slot&7];
    }
    next_slot=slot+1;if(next_slot==CACHE_COUNT)next_slot=0;
    old=cached_ids[slot];
    if(old!=INVALID)world_lookup_set(old,INVALID);
    world_cache_upload(slot,id);cached_ids[slot]=id;references[slot]=1;
    world_lookup_set(id,slot);
    return slot;
}

#endif

static void fetch_strip(uint16_t x,uint16_t y,uint8_t vertical,uint8_t count) {
    uint16_t ci,local;uint8_t run,i=0;
    while(i<count) {
        if(x>=game_world.width/8 || y>=game_world.height/8) {
            strip_low[i]=strip_high[i]=strip_attrs[i]=0;++i;
            if(vertical)++y;else ++x;
            continue;
        }
        ci=(y>>4)*game_world.chunks_x+(x>>5);
        if(ci!=last_chunk) {
            world_far_copy(game_world.chunks.bank,(const uint8_t *)(game_world.chunks.address+ci*4),
                           (uint8_t *)&chunk,4);last_chunk=ci;
        }
        local=(y&15)*32+(x&31);
        run=vertical?16-(y&15):32-(x&31);if(run>count-i)run=count-i;
        if(vertical){if(game_world.height/8-y<run)run=game_world.height/8-y;}
        else if(game_world.width/8-x<run)run=game_world.width/8-x;
        world_far_gather(chunk.bank,(const uint8_t *)(chunk.address+local),strip_low+i,run,vertical?32:1);
        world_far_gather(chunk.bank,(const uint8_t *)(chunk.address+512+local),strip_high+i,run,vertical?32:1);
        world_far_gather(chunk.bank,(const uint8_t *)(chunk.address+1024+local),strip_attrs+i,run,vertical?32:1);
        i+=run;if(vertical)y+=run;else x+=run;
    }
}

static void load_strip(uint16_t x,uint16_t y,uint8_t vertical,uint8_t count) {
    uint8_t i;uint16_t slot,id;
    fetch_strip(x,y,vertical,count);
    for(i=0;i<count;++i) {
        id=strip_low[i]|((uint16_t)strip_high[i]<<8);slot=acquire(id);
        output_slots[i]=slot;
        if(slot<252U){output_tiles[i]=(uint8_t)slot;output_attrs[i]=strip_attrs[i];}
        else {output_tiles[i]=(uint8_t)(slot+4U);output_attrs[i]=strip_attrs[i]|8;}
    }
    world_slot_strip_set(x,y,vertical,count,output_slots);
    gbc_video_strip_pair(x,y,vertical,count,output_tiles,output_attrs);
}

static void release_strip(uint16_t x,uint16_t y,uint8_t vertical,uint8_t count) {
    world_slot_strip_get(x,y,vertical,count,retired+retired_count);
    retired_count+=count;
}

void world_begin(uint16_t x,uint16_t y) BANKED {
    uint16_t i;
    prepare_stage=PREP_NONE;prepare_added_count=0;retired_count=0;
    world_lookup_clear(game_world.pattern_count);
    for(i=0;i<CACHE_COUNT;++i){cached_ids[i]=INVALID;references[i]=0;}
    for(i=0;i<FREE_BYTES;++i)free_bits[i]=255;
    free_bits[FREE_BYTES-1]=(CACHE_COUNT&7)?(1U<<(CACHE_COUNT&7))-1U:255U;
    next_slot=0;last_chunk=INVALID;world_cache_failures=0;world_uploads=0;
    set_bkg_palette(0,7,palettes);
    for(i=y>>3;i<(y>>3)+19;++i)load_strip(x>>3,i,0,21);
    move_bkg((uint8_t)x,(uint8_t)y);
}

/* One unknown partial scanline plus3K caller/end margin is excluded.
 * A pending VBlank can precede its sys_time ISR; account for it atomically.
 * At fast CPU, required lines include bounded work,3K margin and a partial
 * scanline: setup21,fetch35,publish25,acquire20. */
static uint8_t prepare_budget(uint16_t start,uint8_t required_lines) {
    uint16_t now,elapsed,lines;
    uint8_t ly,pending;
    __critical {now=sys_time;ly=LY_REG;pending=IF_REG&VBL_IFLAG;}
    if(pending)++now;
    elapsed=now-start;
    if(elapsed>=2)return 0;
    lines=ly<144?144-ly:298-ly;
    if(!elapsed)lines+=154;
    return lines>required_lines;
}

static void prepare_cancel(void) {
    if(prepare_added_count)
        world_refs_retire(references,prepare_added,prepare_added_count,free_bits);
    prepare_stage=PREP_NONE;prepare_added_count=0;retired_count=0;
}

static uint8_t prepare_matches(uint16_t old_x,uint16_t old_y,uint16_t x,uint16_t y) {
    /* Fine scrolling keeps exactly the same21x19 cells and their refs. */
    return prepare_stage && ((prepare_old_x^old_x)|(prepare_old_y^old_y)
                              |(prepare_x^x)|(prepare_y^y))<8U;
}

static void prepare_begin(uint16_t old_x,uint16_t old_y,uint16_t x,uint16_t y) {
    prepare_old_x=old_x;prepare_old_y=old_y;prepare_x=x;prepare_y=y;
    prepare_old_left=old_x>>3;prepare_old_top=old_y>>3;
    prepare_left=x>>3;prepare_top=y>>3;
    prepare_horizontal=prepare_old_left!=prepare_left;
    prepare_vertical=prepare_old_top!=prepare_top;
    retired_count=0;prepare_added_count=0;prepare_index=0;
    if(prepare_horizontal)release_strip(x>old_x?prepare_old_left:prepare_old_left+20,
                                        prepare_old_top,1,19);
    if(prepare_vertical)release_strip(prepare_horizontal
                    ?(prepare_left>prepare_old_left?prepare_left:prepare_old_left):prepare_old_left,
                    y>old_y?prepare_old_top:prepare_old_top+18,0,prepare_horizontal?20:21);
    prepare_stage=prepare_horizontal?PREP_COL_FETCH:prepare_vertical?PREP_ROW_FETCH:PREP_READY;
}

static void prepare_acquire(void) {
    uint8_t i=prepare_index;
    uint16_t id=strip_low[i]|((uint16_t)strip_high[i]<<8),slot=acquire(id);
    output_slots[i]=slot;prepare_added[prepare_added_count++]=slot;
    if(slot<252U){output_tiles[i]=(uint8_t)slot;output_attrs[i]=strip_attrs[i];}
    else{output_tiles[i]=(uint8_t)(slot+4U);output_attrs[i]=strip_attrs[i]|8;}
    ++prepare_index;
}

static void prepare_publish(uint8_t vertical) {
    world_slot_strip_set(prepare_strip_x,prepare_strip_y,vertical,prepare_count,output_slots);
    gbc_video_strip_pair(prepare_strip_x,prepare_strip_y,vertical,prepare_count,output_tiles,output_attrs);
}

/* Budgeted callers can stop after every bounded work unit. The synchronous
 * world_scroll caller completes the exact same sequence before committing. */
static void prepare_run(uint16_t start,uint8_t budgeted) {
    while(prepare_stage!=PREP_NONE && prepare_stage!=PREP_READY) {
        if(budgeted) {
            uint8_t lines=prepare_stage==PREP_COL_ACQUIRE||prepare_stage==PREP_ROW_ACQUIRE?20
                :prepare_stage==PREP_COL_FETCH||prepare_stage==PREP_ROW_FETCH?35:25;
            if(!prepare_budget(start,lines))return;
        }
        switch(prepare_stage) {
            case PREP_COL_FETCH:
                prepare_strip_x=prepare_x>prepare_old_x?prepare_left+20:prepare_left;
                prepare_strip_y=prepare_vertical&&prepare_y<prepare_old_y?prepare_top+1:prepare_top;
                prepare_count=prepare_vertical?18:19;
                fetch_strip(prepare_strip_x,prepare_strip_y,1,prepare_count);
                prepare_index=0;prepare_stage=PREP_COL_ACQUIRE;break;
            case PREP_COL_ACQUIRE:
                prepare_acquire();
                if(prepare_index==prepare_count)prepare_stage=PREP_COL_PUBLISH;
                break;
            case PREP_COL_PUBLISH:
                prepare_publish(1);
                prepare_stage=prepare_vertical?PREP_ROW_FETCH:PREP_READY;break;
            case PREP_ROW_FETCH:
                prepare_strip_x=prepare_left;
                prepare_strip_y=prepare_y>prepare_old_y?prepare_top+18:prepare_top;
                prepare_count=21;fetch_strip(prepare_strip_x,prepare_strip_y,0,21);
                prepare_index=0;prepare_stage=PREP_ROW_ACQUIRE;break;
            case PREP_ROW_ACQUIRE:
                prepare_acquire();
                if(prepare_index==prepare_count)prepare_stage=PREP_ROW_PUBLISH;
                break;
            case PREP_ROW_PUBLISH:
                prepare_publish(0);prepare_stage=PREP_READY;break;
        }
    }
}

void world_prepare(uint16_t old_x,uint16_t old_y,uint16_t x,uint16_t y,uint16_t start) BANKED {
    if(!prepare_matches(old_x,old_y,x,y)) {
        if(prepare_stage)prepare_cancel();
        if(!prepare_budget(start,21))return;
        /* Runtime camera movement is at most one tile on either axis. */
        if((uint16_t)((x>>3)-(old_x>>3)+1)>2
           || (uint16_t)((y>>3)-(old_y>>3)+1)>2)return;
        prepare_begin(old_x,old_y,x,y);
    }
    prepare_run(start,1);
}

void world_scroll(uint16_t old_x,uint16_t old_y,uint16_t x,uint16_t y) BANKED {
    if(((old_x^x)|(old_y^y))<8U) {
        /* A lookahead target stays hidden while this tile remains current.
         * Preserve both its new refs and partially acquired strip buffers. */
        if(prepare_stage && ((prepare_old_x^old_x)|(prepare_old_y^old_y))>=8U)
            prepare_cancel();
        move_bkg((uint8_t)x,(uint8_t)y);return;
    }
    if(!prepare_matches(old_x,old_y,x,y)) {
        if(prepare_stage)prepare_cancel();
        prepare_begin(old_x,old_y,x,y);
    }
    prepare_run(0,0);
    move_bkg((uint8_t)x,(uint8_t)y);
    world_refs_retire(references,retired,retired_count,free_bits);
    prepare_stage=PREP_NONE;prepare_added_count=0;retired_count=0;
}
