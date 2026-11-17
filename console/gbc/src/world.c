/* Lossless visible-pattern cache. Old visible patterns remain referenced until
 * all entering strips have been uploaded, leaving enough space for a diagonal
 * scroll even when every tile in the viewport has a different pattern. */
#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
#include <stddef.h>
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
const uint8_t world_lookup_format=1;
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
#ifdef WORLD_GRAPHICS_ZX0
/* SRAM0 holds the compact lookup, viewport mirror and protected saves.
 * Five decoded maps use bank1; 32 half-KiB pattern blocks use banks2..3.
 * Each map plane is decoded independently, so preparation can yield between
 * low IDs, high IDs and attributes without exposing incomplete cells. */
#if WORLD_PATTERN_BLOCK_BYTES != 512 || WORLD_MAP_PLANE_BYTES != 512 || WORLD_ZX0_COST_PREFIX != 1
#error Regenerate the 0.91 half-KiB graphics profile.
#endif
#define MAP_CACHE_COUNT 5
#define PATTERN_CACHE_COUNT 32
static uint16_t map_cache_ids[MAP_CACHE_COUNT],pattern_cache_ids[PATTERN_CACHE_COUNT];
static uint8_t map_cache_next,chunk_ram_bank,chunk_cache;
static uint8_t map_cache_planes[MAP_CACHE_COUNT],prepare_map_plane;
#endif

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
void world_decompress(uint16_t bank,uint16_t source,uint8_t ram_bank,uint16_t dest) NONBANKED;
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

#ifdef WORLD_GRAPHICS_ZX0
static uint16_t cached_pattern_address(uint16_t block) {
    uint8_t cache=block&(PATTERN_CACHE_COUNT-1),ram_bank=2+(cache>>4);
    uint16_t address=0xa000U+((uint16_t)(cache&15)<<9);
    if(pattern_cache_ids[cache]!=block) {
        world_far_t pointer;
        world_far_copy(game_world.patterns.bank,(const uint8_t *)(game_world.patterns.address+block*4),
                       (uint8_t *)&pointer,4);
        world_decompress(pointer.bank,pointer.address+WORLD_ZX0_COST_PREFIX,ram_bank,address);
        pattern_cache_ids[cache]=block;
    }
    return address;
}
#endif

#ifdef WORLD_GRAPHICS_ZX0
void world_cache_upload(uint16_t slot,uint16_t id) __sdcccall(0) {
    uint16_t address=cached_pattern_address(id>>5);
    rRAMB=2+((id>>9)&1);
    world_upload_tile(CURRENT_BANK,address+((id&31)<<4),physical(slot));
    rRAMB=0;
    ++world_uploads;
}
#else
typedef char world_raw_pattern_bank_offset[(offsetof(world_level_t,patterns)+offsetof(world_far_t,bank)==14)?1:-1];
typedef char world_raw_pattern_address_offset[(offsetof(world_level_t,patterns)+offsetof(world_far_t,address)==16)?1:-1];
void world_cache_upload_raw(uint16_t slot,uint16_t id) __sdcccall(0);
void world_cache_upload(uint16_t slot,uint16_t id) __sdcccall(0) __naked {
    __asm jp _world_cache_upload_raw __endasm;
}
#endif

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

static uint8_t fetch_strip(uint16_t x,uint16_t y,uint8_t vertical,uint8_t count,uint8_t offset,uint8_t partial) {
    uint16_t ci,local;uint8_t run,i=offset;
#ifdef WORLD_GRAPHICS_ZX0
    uint8_t plane;
    if(!partial)prepare_map_plane=0;
#endif
    count+=offset;
    while(i<count) {
        if(x>=game_world.width/8 || y>=game_world.height/8) {
            strip_low[i]=strip_high[i]=strip_attrs[i]=0;++i;
            if(vertical)++y;else ++x;
            continue;
        }
        ci=(y>>4)*game_world.chunks_x+(x>>5);
        if(ci!=last_chunk) {
#ifdef WORLD_GRAPHICS_ZX0
            uint8_t cached;
            for(cached=0;cached<MAP_CACHE_COUNT;++cached)if(map_cache_ids[cached]==ci)break;
            if(cached==MAP_CACHE_COUNT) {
                cached=map_cache_next;
                if(++map_cache_next==MAP_CACHE_COUNT)map_cache_next=0;
                map_cache_ids[cached]=ci;
                map_cache_planes[cached]=0;
            }
            chunk_ram_bank=1;chunk_cache=cached;
            chunk.address=0xa000U+(uint16_t)cached*1536;
            last_chunk=ci;
#else
            world_far_copy(game_world.chunks.bank,(const uint8_t *)(game_world.chunks.address+ci*4),
                           (uint8_t *)&chunk,4);last_chunk=ci;
#endif
        }
        local=(y&15)*32+(x&31);
        run=vertical?16-(y&15):32-(x&31);if(run>count-i)run=count-i;
        if(vertical){if(game_world.height/8-y<run)run=game_world.height/8-y;}
        else if(game_world.width/8-x<run)run=game_world.width/8-x;
#ifdef WORLD_GRAPHICS_ZX0
        /* A complete cached map has no cold work to budget between planes.
         * Gather the fragment once, as for the raw profile, instead of paying
         * three dispatches and cache-budget checks for the same cells. */
        if(map_cache_planes[chunk_cache]==7) {
            world_sram_gather(1,(const uint8_t *)(chunk.address+local),strip_low+i,run,vertical?32:1);
            world_sram_gather(1,(const uint8_t *)(chunk.address+512+local),strip_high+i,run,vertical?32:1);
            world_sram_gather(1,(const uint8_t *)(chunk.address+1024+local),strip_attrs+i,run,vertical?32:1);
            prepare_map_plane=0;
        } else {
        /* A partial fetch completes one plane of this fragment. Its row or
         * column index advances only after all three output arrays are ready. */
        for(plane=partial?prepare_map_plane:0;plane<3;++plane) {
            uint16_t source=chunk.address+((uint16_t)plane<<9);
            uint8_t mask=1U<<plane;
            uint8_t *dest=plane==0?strip_low:plane==1?strip_high:strip_attrs;
            if(!(map_cache_planes[chunk_cache]&mask)) {
                world_far_t pointer;
                world_far_copy(game_world.chunks.bank,
                    (const uint8_t *)(game_world.chunks.address+ci*12U+(uint16_t)plane*4U),
                    (uint8_t *)&pointer,4);
                world_decompress(pointer.bank,pointer.address+WORLD_ZX0_COST_PREFIX,1,source);
                map_cache_planes[chunk_cache]|=mask;
            }
            world_sram_gather(1,(const uint8_t *)(source+local),dest+i,run,vertical?32:1);
            if(partial) {
                if(++prepare_map_plane<3)return 0;
                prepare_map_plane=0;break;
            }
        }
        }
#else
#define gather(source,dest) world_far_gather(chunk.bank,(const uint8_t *)(source),dest,run,vertical?32:1)
        gather(chunk.address+local,strip_low+i);
        gather(chunk.address+512+local,strip_high+i);
        gather(chunk.address+1024+local,strip_attrs+i);
#undef gather
#endif
        i+=run;if(vertical)y+=run;else x+=run;
        if(partial)break;
    }
    return i-offset;
}

static void load_strip(uint16_t x,uint16_t y,uint8_t vertical,uint8_t count) {
    uint8_t i;uint16_t slot,id;
    fetch_strip(x,y,vertical,count,0,0);
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
#ifdef WORLD_GRAPHICS_ZX0
    for(i=0;i<MAP_CACHE_COUNT;++i){map_cache_ids[i]=INVALID;map_cache_planes[i]=0;}
    for(i=0;i<PATTERN_CACHE_COUNT;++i)pattern_cache_ids[i]=INVALID;
    map_cache_next=0;prepare_map_plane=0;
#endif
    for(i=0;i<CACHE_COUNT;++i){cached_ids[i]=INVALID;references[i]=0;}
    for(i=0;i<FREE_BYTES;++i)free_bits[i]=255;
    free_bits[FREE_BYTES-1]=(CACHE_COUNT&7)?(1U<<(CACHE_COUNT&7))-1U:255U;
    next_slot=0;last_chunk=INVALID;world_cache_failures=0;world_uploads=0;
#ifdef WORLD_GRAPHICS_ZX0
    /* Small courses fit entirely in the decoded caches. Load their remaining
     * blocks with the LCD off so riding never pays a first-use decode cost. */
    if(game_world.pattern_count<=PATTERN_CACHE_COUNT*32U)
        for(i=0;i<(game_world.pattern_count+31U)/32U;++i)cached_pattern_address(i);
    if((uint16_t)game_world.chunks_x*game_world.chunks_y<=MAP_CACHE_COUNT)
        for(i=0;i<(uint16_t)game_world.chunks_x*game_world.chunks_y;++i)
            fetch_strip((i%game_world.chunks_x)*32U,(i/game_world.chunks_x)*16U,0,1,0,0);
#endif
    set_bkg_palette(0,7,palettes);
    for(i=y>>3;i<(y>>3)+19;++i)load_strip(x>>3,i,0,21);
    move_bkg((uint8_t)x,(uint8_t)y);
}

/* One unknown partial scanline plus3K caller/end margin is excluded.
 * A pending VBlank can precede its sys_time ISR; account for it atomically.
 * At fast CPU, required lines include bounded work,3K margin and a partial
 * scanline: setup21,cached/raw fetch20,publish25,acquire20. */
/* A raw fetch reads at most one chunk fragment (three planes). Reserve
 * 18,240 cycles including the caller and partial-line margin. */
#define PREP_FETCH_LINES 20
static uint8_t prepare_budget(uint16_t start,uint16_t required_lines) {
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
#ifdef WORLD_GRAPHICS_ZX0
    prepare_map_plane=0;
#endif
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
#ifdef WORLD_GRAPHICS_ZX0
    prepare_map_plane=0;
#endif
    if(prepare_horizontal)release_strip(x>old_x?prepare_old_left:prepare_old_left+20,
                                        prepare_old_top,1,19);
    if(prepare_vertical)release_strip(prepare_horizontal
                    ?(prepare_left>prepare_old_left?prepare_left:prepare_old_left):prepare_old_left,
                    y>old_y?prepare_old_top:prepare_old_top+18,0,prepare_horizontal?20:21);
    prepare_stage=prepare_horizontal?PREP_COL_FETCH:prepare_vertical?PREP_ROW_FETCH:PREP_READY;
}

#ifdef WORLD_ACQUIRE_C_REFERENCE
static void prepare_acquire(void) {
    uint8_t i=prepare_index;
    uint16_t id=strip_low[i]|((uint16_t)strip_high[i]<<8),slot=acquire(id);
    output_slots[i]=slot;prepare_added[prepare_added_count++]=slot;
    if(slot<252U){output_tiles[i]=(uint8_t)slot;output_attrs[i]=strip_attrs[i];}
    else{output_tiles[i]=(uint8_t)(slot+4U);output_attrs[i]=strip_attrs[i]|8;}
    ++prepare_index;
}
#else
/* Near bank6 bookkeeping keeps both slot lists and the acquisition order.
 * Indices remain bounded by the staged caller; no scratch RAM is needed. */
static void prepare_acquire(void) __naked {
    __asm
        ld a,(#_prepare_index)
        ld c,a
        ld b,#0
        ld hl,#_strip_low
        add hl,bc
        ld e,(hl)
        ld hl,#_strip_high
        add hl,bc
        ld d,(hl)
        push bc
        push de
        call _world_acquire_fast
        pop hl
        pop bc

        ld a,c
        add a,a
        add a,#<(_output_slots)
        ld l,a
        ld a,#>(_output_slots)
        adc a,#0
        ld h,a
        ld a,e
        ld (hl+),a
        ld (hl),d

        ld hl,#_prepare_added_count
        ld a,(hl)
        inc (hl)
        add a,a
        add a,#<(_prepare_added)
        ld l,a
        ld a,#>(_prepare_added)
        adc a,#0
        ld h,a
        ld a,e
        ld (hl+),a
        ld (hl),d

        ld a,e
        cp #252
        ld a,d
        sbc a,#0
        ld a,e
        jr c,00110$
        add a,#4
        ld e,a
        ld hl,#_strip_attrs
        add hl,bc
        ld a,(hl)
        or #8
        jr 00111$
00110$:
        ld hl,#_strip_attrs
        add hl,bc
        ld a,(hl)
00111$:
        ld hl,#_output_tiles
        add hl,bc
        ld (hl),e
        ld hl,#_output_attrs
        add hl,bc
        ld (hl),a
        ld hl,#_prepare_index
        inc (hl)
        ret
    __endasm;
}
#endif

static void prepare_publish(uint8_t vertical) {
    world_slot_strip_set(prepare_strip_x,prepare_strip_y,vertical,prepare_count,output_slots);
    gbc_video_strip_pair(prepare_strip_x,prepare_strip_y,vertical,prepare_count,output_tiles,output_attrs);
}

#ifdef WORLD_GRAPHICS_ZX0
static uint16_t block_decode_lines(uint16_t bank,uint16_t address,uint16_t start) {
    world_far_t pointer;
    uint8_t lines;
    /* Do not spend the tail of the frame reading a cold unit's metadata.
     * The exact decoder prefix excludes the wrapper and all other work;
     * another 30 lines cover directory reads, cache/gather/DMA, IRQs and
     * returning through the dispatcher. */
    if(!prepare_budget(start,12))return 65535U;
    world_far_copy(bank,(const uint8_t *)address,(uint8_t *)&pointer,4);
    world_far_copy(pointer.bank,(const uint8_t *)pointer.address,&lines,1);
    return (uint16_t)lines+30U;
}

static uint16_t prepare_fetch_lines(uint16_t start) {
    uint8_t cached;
    uint16_t x=prepare_strip_x,y=prepare_strip_y,ci;
    if(prepare_stage==PREP_COL_FETCH)y+=prepare_index;else x+=prepare_index;
    if(x>=game_world.width/8 || y>=game_world.height/8)return 20;
    ci=(y>>4)*game_world.chunks_x+(x>>5);
    for(cached=0;cached<MAP_CACHE_COUNT;++cached)
        if(map_cache_ids[cached]==ci && (map_cache_planes[cached]&(1U<<prepare_map_plane)))return 20;
    return block_decode_lines(game_world.chunks.bank,
        game_world.chunks.address+ci*12U+(uint16_t)prepare_map_plane*4U,start);
}

static uint16_t prepare_acquire_lines(uint16_t start) {
    uint16_t id=strip_low[prepare_index]|((uint16_t)strip_high[prepare_index]<<8);
    uint16_t block=id>>5;
    if(pattern_cache_ids[block&(PATTERN_CACHE_COUNT-1)]!=block && world_lookup_get(id)>=CACHE_COUNT)
        return block_decode_lines(game_world.patterns.bank,game_world.patterns.address+block*4U,start);
    return 20;
}
#endif

/* Budgeted callers can stop after every bounded work unit. The synchronous
 * world_scroll caller completes the exact same sequence before committing. */
static void prepare_run(uint16_t start,uint8_t budgeted) {
    while(prepare_stage!=PREP_NONE && prepare_stage!=PREP_READY) {
        if(prepare_stage==PREP_COL_FETCH) {
            prepare_strip_x=prepare_x>prepare_old_x?prepare_left+20:prepare_left;
            prepare_strip_y=prepare_vertical&&prepare_y<prepare_old_y?prepare_top+1:prepare_top;
            prepare_count=prepare_vertical?18:19;
        } else if(prepare_stage==PREP_ROW_FETCH) {
            prepare_strip_x=prepare_left;
            prepare_strip_y=prepare_y>prepare_old_y?prepare_top+18:prepare_top;
            prepare_count=21;
        }
        if(budgeted) {
            uint16_t lines=prepare_stage==PREP_COL_ACQUIRE||prepare_stage==PREP_ROW_ACQUIRE?20
                :prepare_stage==PREP_COL_FETCH||prepare_stage==PREP_ROW_FETCH?PREP_FETCH_LINES:25;
#ifdef WORLD_GRAPHICS_ZX0
            if(prepare_stage==PREP_COL_ACQUIRE || prepare_stage==PREP_ROW_ACQUIRE)
                lines=prepare_acquire_lines(start);
            else if(prepare_stage==PREP_COL_FETCH || prepare_stage==PREP_ROW_FETCH)
                lines=prepare_fetch_lines(start);
#endif
            if(!prepare_budget(start,lines))return;
        }
        switch(prepare_stage) {
            case PREP_COL_FETCH:
                prepare_index+=fetch_strip(prepare_strip_x,prepare_strip_y+prepare_index,1,
                                          prepare_count-prepare_index,prepare_index,budgeted);
                if(prepare_index==prepare_count){prepare_index=0;prepare_stage=PREP_COL_ACQUIRE;}
                break;
            case PREP_COL_ACQUIRE:
                /* Synchronous publication must finish the strip anyway.
                 * Avoid repeating the stage dispatcher for every tile;
                 * idle preparation still yields at each bounded unit. */
                do {prepare_acquire();}
                while(!budgeted && prepare_index<prepare_count);
                if(prepare_index==prepare_count)prepare_stage=PREP_COL_PUBLISH;
                break;
            case PREP_COL_PUBLISH:
                prepare_publish(1);
                prepare_index=0;
                prepare_stage=prepare_vertical?PREP_ROW_FETCH:PREP_READY;break;
            case PREP_ROW_FETCH:
                prepare_index+=fetch_strip(prepare_strip_x+prepare_index,prepare_strip_y,0,
                                          prepare_count-prepare_index,prepare_index,budgeted);
                if(prepare_index==prepare_count){prepare_index=0;prepare_stage=PREP_ROW_ACQUIRE;}
                break;
            case PREP_ROW_ACQUIRE:
                do {prepare_acquire();}
                while(!budgeted && prepare_index<prepare_count);
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
