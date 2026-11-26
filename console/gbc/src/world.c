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
#ifdef WORLD_GRAPHICS_ZX0
const uint8_t world_lookup_format=1;
#else
const uint8_t world_lookup_format=2;
#endif
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
static uint8_t output_tiles[21];
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


#ifndef WORLD_GRAPHICS_ZX0
#define WORLD_MAP_PLANES 1
void world_map_snapshot(void);
void world_plane_slots(uint8_t x,uint8_t y,uint8_t vertical,uint8_t count,uint16_t *slots) __sdcccall(0);
void gbc_video_world_strip_pair(uint8_t x,uint8_t y,uint8_t vertical,uint8_t count,const uint8_t *tiles,const uint8_t *attrs) __sdcccall(0);
#else
void gbc_video_strip_pair(uint8_t x,uint8_t y,uint8_t vertical,uint8_t count,const uint8_t *tiles,const uint8_t *attrs) __sdcccall(0);
#endif
void world_upload_tile(uint16_t bank,uint16_t source,uint16_t pattern) NONBANKED;
void world_decompress(uint16_t bank,uint16_t source,uint8_t ram_bank,uint16_t dest) NONBANKED;
uint16_t world_find_free(uint16_t next,uint8_t *bitmap) __sdcccall(0);
void world_refs_retire_fixed(const uint16_t *slots,uint8_t count) __sdcccall(0);

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
typedef char world_raw_map_layout[(offsetof(world_level_t,width)==0 && offsetof(world_level_t,height)==2
    && offsetof(world_level_t,chunks)==18 && offsetof(world_level_t,chunks_x)==30
    && sizeof(world_far_t)==4)?1:-1];
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

#ifndef WORLD_GRAPHICS_ZX0
/* Read all three map planes while the nine-bit data bank is selected once. */
void world_far_gather3(uint16_t bank,const uint8_t *source,uint8_t *low,
    uint8_t *high,uint8_t *attrs,uint8_t count,uint8_t stride) __sdcccall(0);
#endif

static uint8_t fetch_strip(uint16_t x,uint16_t y,uint8_t vertical,uint8_t count,uint8_t offset,uint8_t partial);
#ifndef WORLD_GRAPHICS_ZX0
/* Return one in-bounds raw fragment, or zero at a padded cell. The caller
 * advances unsigned coordinates and owns the three destination arrays. */
static uint8_t raw_map_fragment(uint16_t x,uint16_t y,uint8_t vertical,uint8_t count,
                                uint8_t *low,uint8_t *high,uint8_t *attrs) __sdcccall(0) __naked {
    x;y;vertical;count;low;high;attrs;
    __asm
        ld hl,#_game_world
        ld a,(hl+)
        ld e,a
        ld d,(hl)
        .rept 3
        srl d
        rr e
        .endm
        ldhl sp,#2
        ld a,e
        sub (hl)
        ld e,a
        inc hl
        ld a,d
        sbc (hl)
        jp c,raw_outside
        ld d,a
        or e
        jp z,raw_outside
        push de
        ld hl,#_game_world+2
        ld a,(hl+)
        ld e,a
        ld d,(hl)
        .rept 3
        srl d
        rr e
        .endm
        ldhl sp,#6
        ld a,e
        sub (hl)
        ld e,a
        inc hl
        ld a,d
        sbc (hl)
        pop bc
        jp c,raw_outside
        ld d,a
        or e
        jp z,raw_outside
        ldhl sp,#6
        ld a,(hl)
        or a
        jr z,raw_row_limit
        ldhl sp,#4
        ld a,(hl)
        and #15
        cpl
        add #17
        jr raw_limit
raw_row_limit:
        ld d,b
        ld e,c
        ldhl sp,#2
        ld a,(hl)
        and #31
        cpl
        add #33
raw_limit:
        ld b,a
        ld a,d
        or a
        jr nz,raw_limit_count
        ld a,e
        cp b
        jr nc,raw_limit_count
        ld b,a
raw_limit_count:
        ldhl sp,#7
        ld a,(hl)
        cp b
        jr c,raw_run
        ld a,b
raw_run:
        push af
        ; y / 16 can use nine bits after the world bounds test.
        ldhl sp,#6
        ld a,(hl+)
        swap a
        and #15
        ld e,a
        ld a,(hl)
        swap a
        ld d,a
        and #0xf0
        or e
        ld e,a
        ld a,d
        and #15
        ld d,a
        ld hl,#0
        ld a,(#_game_world+30)
raw_multiply_row:
        srl a
        jr nc,raw_skip_add
        add hl,de
raw_skip_add:
        jr z,raw_row_product
        sla e
        rl d
        jr raw_multiply_row
raw_row_product:
        ld b,h
        ld c,l
        ; x / 32 fits one byte because the pixel width is uint16_t.
        ldhl sp,#4
        ld a,(hl+)
        .rept 3
        rlca
        .endm
        and #7
        ld e,a
        ld a,(hl)
        .rept 3
        rlca
        .endm
        and #248
        or e
        ld e,a
        ld d,#0
        ld h,b
        ld l,c
        add hl,de
        ld a,(#_last_chunk)
        cp l
        jr nz,raw_load_chunk
        ld a,(#_last_chunk+1)
        cp h
        jr z,raw_have_chunk
raw_load_chunk:
        ld a,l
        ld (#_last_chunk),a
        ld a,h
        ld (#_last_chunk+1),a
        add hl,hl
        add hl,hl
        ld a,(#_game_world+20)
        ld e,a
        ld a,(#_game_world+21)
        ld d,a
        add hl,de
        ld de,#4
        push de
        ld de,#_chunk
        push de
        push hl
        ld hl,#_game_world+18
        ld a,(hl+)
        ld h,(hl)
        ld l,a
        push hl
        call _world_far_copy
        add sp,#8
raw_have_chunk:
        ldhl sp,#4
        ld a,(hl)
        and #31
        ld e,a
        ldhl sp,#6
        ld a,(hl)
        and #15
        .rept 3
        rrca
        .endm
        ld d,a
        and #0xe0
        or e
        ld e,a
        ld a,d
        and #1
        ld d,a
        ld hl,#_chunk+2
        ld a,(hl+)
        ld h,(hl)
        ld l,a
        add hl,de
        ld d,h
        ld e,l
        ldhl sp,#8
        ld a,(hl)
        or a
        ld b,#1
        jr z,raw_arguments
        ld b,#32
raw_arguments:
        ldhl sp,#1
        ld c,(hl)
        push bc
        ; Each push moves the following source word to the same displacement.
        .rept 3
        ldhl sp,#16
        ld a,(hl+)
        ld h,(hl)
        ld l,a
        push hl
        .endm
        push de
        ld hl,#_chunk
        ld a,(hl+)
        ld h,(hl)
        ld l,a
        push hl
        call _world_far_gather3
        add sp,#12
        pop af
        ld e,a
        ret
raw_outside:
        ld e,#0
        ret
    __endasm;
}

#endif
#ifdef WORLD_GRAPHICS_ZX0
static uint8_t fetch_strip(uint16_t x,uint16_t y,uint8_t vertical,uint8_t count,uint8_t offset,uint8_t partial) {
    uint16_t ci,local;uint8_t run,i=offset;
    uint8_t plane;
    if(!partial)prepare_map_plane=0;
    count+=offset;
    while(i<count) {
        if(x>=game_world.width/8 || y>=game_world.height/8) {
            strip_low[i]=strip_high[i]=strip_attrs[i]=0;++i;
            if(vertical)++y;else ++x;
            continue;
        }
        ci=(y>>4)*game_world.chunks_x+(x>>5);
        if(ci!=last_chunk) {
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
        }
        local=(y&15)*32+(x&31);
        run=vertical?16-(y&15):32-(x&31);if(run>count-i)run=count-i;
        if(vertical){if(game_world.height/8-y<run)run=game_world.height/8-y;}
        else if(game_world.width/8-x<run)run=game_world.width/8-x;
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
        i+=run;if(vertical)y+=run;else x+=run;
        if(partial)break;
    }
    return i-offset;
}
#else
static uint8_t fetch_strip(uint16_t x,uint16_t y,uint8_t vertical,uint8_t count,uint8_t offset,uint8_t partial) {
    uint8_t done=0;
    while(done<count) {
        uint8_t index=offset+done;
        uint8_t run=raw_map_fragment(x,y,vertical,count-done,
                                     strip_low+index,strip_high+index,strip_attrs+index);
        if(!run) {
            uint16_t axis=vertical?y:x;
            run=count-done;
            /* Unsigned coordinates can wrap into the first map cell. */
            if(axis && (uint16_t)(0U-axis)<run)run=(uint8_t)(0U-axis);
            memset(strip_low+index,0,run);
            memset(strip_high+index,0,run);
            memset(strip_attrs+index,0,run);
        } else if(partial)return done+run;
        done+=run;
        if(vertical)y+=run;else x+=run;
    }
    return done;
}
#endif

static void load_strip(uint16_t x,uint16_t y,uint8_t vertical,uint8_t count) {
    uint8_t i;uint16_t slot,id;
    fetch_strip(x,y,vertical,count,0,0);
    for(i=0;i<count;++i) {
        id=strip_low[i]|((uint16_t)strip_high[i]<<8);slot=acquire(id);
#ifndef WORLD_MAP_PLANES
        prepare_added[i]=slot;
#endif
        if(slot<252U)output_tiles[i]=(uint8_t)slot;
        else {output_tiles[i]=(uint8_t)(slot+4U);strip_attrs[i]|=8;}
    }
#ifdef WORLD_MAP_PLANES
    gbc_video_world_strip_pair(x,y,vertical,count,output_tiles,strip_attrs);
#else
    world_slot_strip_set(x,y,vertical,count,prepare_added);
    gbc_video_strip_pair(x,y,vertical,count,output_tiles,strip_attrs);
#endif
}

static void release_strip(uint16_t x,uint16_t y,uint8_t vertical,uint8_t count) {
#ifdef WORLD_MAP_PLANES
    world_plane_slots(x,y,vertical,count,retired+retired_count);
#else
    world_slot_strip_get(x,y,vertical,count,retired+retired_count);
#endif
    retired_count+=count;
}

void world_begin(uint16_t x,uint16_t y) BANKED {
    uint16_t i;
    prepare_stage=PREP_NONE;prepare_added_count=0;retired_count=0;
#ifdef WORLD_GRAPHICS_ZX0
    world_lookup_clear(game_world.pattern_count);
#else
    world_lookup_raw_clear(game_world.pattern_count);
#endif
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
#ifdef WORLD_MAP_PLANES
    world_map_snapshot();
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
#ifndef WORLD_GRAPHICS_ZX0
/* Raw stages request at most 25 lines. Across the first display period, or
 * in VBlank of the second, more than that remains. Sample the pending IRQ,
 * time and LY together, just as the full-width compressed guard does. */
static uint8_t prepare_budget(uint16_t start,uint16_t required_lines) __naked {
    start;required_lines;
    __asm
        di
        ld hl,#_sys_time
        ld a,(hl+)
        ld h,(hl)
        ld l,a
        ldh a,(#0x44)
        ld b,a
        ldh a,(#0x0f)
        ei
        rrca
        jr nc,raw_budget_time
        inc hl
raw_budget_time:
        ld a,l
        sub e
        ld l,a
        ld a,h
        sbc d
        jr nz,raw_budget_late
        ld a,l
        or a
        jr z,raw_budget_room
        dec a
        jr nz,raw_budget_late
        ld a,#144
        sub b
        jr c,raw_budget_room
        jr z,raw_budget_room
        cp c
        jr c,raw_budget_late
        jr nz,raw_budget_room
raw_budget_late:
        xor a
        ret
raw_budget_room:
        ld a,#1
        ret
    __endasm;
}
#else
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

#endif

static void prepare_cancel(void) {
    if(prepare_added_count)
        world_refs_retire_fixed(prepare_added,prepare_added_count);
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

/* Fixed forward overlap copy: destination is two bytes below the source.
 * Keep this small operation in bank 6 instead of linking ROM0 memmove. */
static void prepare_shift_added(void) __naked {
    __asm
        ld hl,#(_prepare_added+2)
        ld de,#_prepare_added
        ld b,#36
prepare_shift_added_loop:
        ld a,(hl+)
        ld (de),a
        inc de
        dec b
        jr nz,prepare_shift_added_loop
        ret
    __endasm;
}

#ifndef WORLD_GRAPHICS_ZX0
static void shift_column_prefix(void) __naked {
            __asm
                ld hl,#_strip_low+1
                call fpa_shift_plane
                ld hl,#_strip_high+1
                call fpa_shift_plane
                ld hl,#_strip_attrs+1
                call fpa_shift_plane
                ld hl,#_output_tiles+1
                call fpa_shift_plane
                ret
fpa_shift_plane:
                ld d,h
                ld e,l
                dec de
                .rept 18
                ld a,(hl+)
                ld (de),a
                inc de
                .endm
                ret

            __endasm;
}
#endif

/* A completed horizontal strip already contains18 of the19 diagonal edge
 * cells. Keep those exact references and published hidden cells; the ordinary
 * row stage replaces the corner and publishes the new row before commit. */
static uint8_t prepare_rebase_column(uint16_t old_x,uint16_t old_y,uint16_t x,uint16_t y,
                                     uint16_t start,uint8_t budgeted) {
    uint16_t top;
#ifndef WORLD_GRAPHICS_ZX0
    /* A partially acquired column has no published map cells. Its retained
     * prefix would be reacquired, in exactly this order, before any misses. */
    uint8_t partial=prepare_stage==PREP_COL_ACQUIRE && !budgeted
                 && prepare_index==prepare_added_count && prepare_index<19;
#else
    const uint8_t partial=0;
#endif
    if((!partial && (prepare_stage!=PREP_READY || prepare_added_count!=19))
       || !prepare_horizontal || prepare_vertical || retired_count!=19
       || ((prepare_old_x^old_x)|(prepare_old_y^old_y)|(prepare_x^x))>=8U)return 0;
    top=y>>3;
    if((uint16_t)(prepare_left-prepare_old_left+1)>2 || prepare_left==prepare_old_left
       || (top!=prepare_old_top+1 && (uint16_t)(top+1)!=prepare_old_top))return 0;
    if(budgeted && !prepare_budget(start,21))return 0;
    if(top>prepare_old_top) {
        if(prepare_added_count) {
            world_refs_retire_fixed(prepare_added,1);
            prepare_shift_added();
            --prepare_added_count;
        }
#ifndef WORLD_GRAPHICS_ZX0
        if(partial) {
            /* Copy the four retained prefixes forwards. Each source overlaps
             * its destination by one cell, so each read precedes its write. */
            shift_column_prefix();
            ++prepare_strip_y;
        }
#endif
    } else if(!partial) {
        world_refs_retire_fixed(prepare_added+18,1);
        --prepare_added_count;
    }
    release_strip(prepare_left>prepare_old_left?prepare_left:prepare_old_left,
                  top>prepare_old_top?prepare_old_top:prepare_old_top+18,0,20);
    prepare_old_x=old_x;prepare_old_y=old_y;prepare_x=x;prepare_y=y;
    prepare_top=top;prepare_vertical=1;
    if(partial) {
        prepare_index=prepare_added_count;prepare_count=18;
        prepare_stage=prepare_index==18?PREP_COL_PUBLISH:PREP_COL_ACQUIRE;
    } else {
        prepare_index=0;prepare_stage=PREP_ROW_FETCH;
    }
    return 1;
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
    prepare_added[prepare_added_count++]=slot;
    if(slot<252U)output_tiles[i]=(uint8_t)slot;
    else{output_tiles[i]=(uint8_t)(slot+4U);strip_attrs[i]|=8;}
    ++prepare_index;
}
#else
/* Raw preparation retains the pattern ID and selected slot in the exact
 * argument order used by the upload and lookup helpers. No shared scratch. */
#ifndef WORLD_GRAPHICS_ZX0
static void prepare_acquire(void) __naked {
    __asm
        ld a,(#_prepare_index)
        ld c,a
        ld b,#0
        ld hl,#_strip_low
        add hl,bc
        ld a,(hl-)
        ld e,a
        ld a,c
        or a
        jr z,fpa_read_high
        ld a,(hl)
        cp e
        jr nz,fpa_read_high
        ld hl,#_strip_high
        add hl,bc
        ld a,(hl-)
        ld d,a
        cp (hl)
        jr nz,fpa_lookup
        ; A failed acquire returns a placeholder without pinning a slot.
        ld a,(#_world_cache_failures)
        ld hl,#_world_cache_failures+1
        or (hl)
        jp z,fpa_repeat
        jr fpa_lookup
fpa_read_high:
        ld hl,#_strip_high
        add hl,bc
        ld d,(hl)
fpa_lookup:
        push de
        ld a,(#_world_lookup_direct)
        or a
        jr z,fpa_general_lookup
        ld a,d
        cp #0x30
        jr nc,fpa_general_lookup
        ld h,d
        ld l,e
        add hl,hl
        ld a,h
        and #31
        or #0xa0
        ld h,a
        ld a,d
        swap a
        and #3
        inc a
        ld (#0x4000),a
        ld a,(hl+)
        ld e,a
        ld a,(hl)
        ld d,a
        or a
        jr z,fpa_direct_hit
        dec a
        jr nz,fpa_direct_absent
        ld a,e
        cp #188
        jr nc,fpa_direct_absent
fpa_direct_hit:
        xor a
        ld (#0x4000),a
        jr fpa_hit
fpa_direct_absent:
        ; Keep the high-byte pointer and SRAM bank across the WRAM-only
        ; free-slot search. On success the same entry receives the new slot.
        push hl
        jr fpa_allocate
fpa_general_lookup:
        call _world_lookup_get
        ld a,d
        or a
        jr z,fpa_hit
        cp #1
        jr nz,fpa_miss
        ld a,e
        cp #188
        jr nc,fpa_miss
fpa_hit:
        ld h,d
        ld l,e
        add hl,hl
        ld bc,#_world_cache_references
        add hl,bc
        ld a,(hl+)
        ld b,a
        ld a,(hl)
        or b
        jr z,fpa_hit_zero
        dec hl
        inc (hl)
        jp nz,fpa_done_id
        inc hl
        inc (hl)
        jp fpa_done_id
fpa_hit_zero:
        dec hl
        ld (hl),#1
        call fpa_clear_free
        jp fpa_done_id
fpa_miss:
        ld hl,#0
        push hl
fpa_allocate:
        ld a,(#_world_cache_next)
        ld e,a
        ld a,(#_world_cache_next+1)
        ld d,a
        ld h,d
        ld l,e
        add hl,hl
        ld bc,#_world_cache_references
        add hl,bc
        ld a,(hl+)
        or (hl)
        jr z,fpa_direct_free
        ld hl,#_world_cache_free_bits
        push hl
        push de
        call _world_find_free
        add sp,#4
        ld a,d
        cp #255
        jr nz,fpa_chosen
        ld hl,#_world_cache_failures
        inc (hl)
        jr nz,fpa_failed
        inc hl
        inc (hl)
fpa_failed:
        pop hl
        xor a
        ld (#0x4000),a
        ld de,#0
        jp fpa_done_id
fpa_direct_free:
        call fpa_clear_free
fpa_chosen:
        pop hl
        bit 7,h
        jr z,fpa_bound
        ld (hl),d
        dec hl
        ld (hl),e
        xor a
        ld (#0x4000),a
fpa_bound:
        ; No IRQ accesses the lookup. Restore SRAM0 before evicting the
        ; previous ID or starting the original one-tile GDMA upload.
        push de
        ld h,d
        ld l,e
        inc hl
        ld a,h
        cp #1
        jr nz,fpa_next_ready
        ld a,l
        cp #188
        jr nz,fpa_next_ready
        ld hl,#0
fpa_next_ready:
        ld a,l
        ld (#_world_cache_next),a
        ld a,h
        ld (#_world_cache_next+1),a
        ld h,d
        ld l,e
        add hl,hl
        ld bc,#_world_cache_ids
        add hl,bc
        ld a,(hl+)
        ld e,a
        ld d,(hl)
        ld a,d
        and e
        inc a
        jr z,fpa_upload
        ld a,(#_world_lookup_direct)
        or a
        jr z,fpa_unlink_chain
        ld a,d
        cp #0x30
        jr nc,fpa_upload
        swap a
        and #3
        inc a
        ld (#0x4000),a
        ld h,d
        ld l,e
        add hl,hl
        ld a,h
        and #31
        or #0xa0
        ld h,a
        ld a,#255
        ld (hl+),a
        ld (hl),a
        xor a
        ld (#0x4000),a
        jr fpa_upload
fpa_unlink_chain:
        ld hl,#65535
        push hl
        push de
        call _world_lookup_set
        add sp,#4
fpa_upload:
        ; The retained slot and ID are already the upload ABI0 arguments.
        call _world_cache_upload
        pop de
        pop bc
        ld hl,#_world_cache_ids
        add hl,de
        add hl,de
        ld (hl),c
        inc hl
        ld (hl),b
        ld hl,#_world_cache_references
        add hl,de
        add hl,de
        ld (hl),#1
        inc hl
        ld (hl),#0
        ; Valid direct IDs were bound above. Out-of-range direct stores
        ; are no-ops. The linked table still inserts after the old unlink.
        ld a,(#_world_lookup_direct)
        or a
        jr nz,fpa_outputs
        push de
        push bc
        call _world_lookup_insert_absent
        pop bc
        pop de
        jr fpa_outputs
fpa_done_id:
        pop bc
fpa_outputs:
        ld a,(#_prepare_index)
        ld c,a
        ld b,#0
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
        ld hl,#_strip_attrs
        add hl,bc
        set 3,(hl)
00110$:
        ld hl,#_output_tiles
        add hl,bc
        ld (hl),a
        ld hl,#_prepare_index
        inc (hl)
        ; Up to three additional pinned direct hits fit in the existing
        ; twenty-line acquisition allowance. Stop at every fourth index.
        ; A miss, a revived slot, and repeated IDs use the normal path.
        ld a,(#_world_lookup_direct)
        or a
        ret z
        ld c,(hl)
        ld b,#0
fpa_batch_next:
        ld a,c
        and #3
        jr z,fpa_batch_close
        ld a,(#_prepare_count)
        cp c
        jr z,fpa_batch_close
        ld hl,#_strip_low
        add hl,bc
        ld a,(hl-)
        ld e,a
        cp (hl)
        jr z,fpa_batch_close
        ld hl,#_strip_high
        add hl,bc
        ld d,(hl)
        ld a,d
        cp #0x30
        jr nc,fpa_batch_close
        swap a
        and #3
        inc a
        ld (#0x4000),a
        ld h,d
        ld l,e
        add hl,hl
        ld a,h
        and #31
        or #0xa0
        ld h,a
        ld a,(hl+)
        ld e,a
        ld a,(hl)
        ld d,a
        or a
        jr z,fpa_batch_valid
        dec a
        jr nz,fpa_batch_close
        ld a,e
        cp #188
        jr nc,fpa_batch_close
fpa_batch_valid:
        ; Require the
        ; slot to be already pinned, leaving free-slot revival to the caller.
        ld hl,#_world_cache_references
        add hl,de
        add hl,de
        ld a,(hl+)
        or (hl)
        jr z,fpa_batch_close
        dec hl
        inc (hl)
        jr nz,fpa_batch_pin
        inc hl
        inc (hl)
fpa_batch_pin:
        ld hl,#_prepare_added_count
        ld a,(hl)
        inc (hl)
        add a,a
        add #<(_prepare_added)
        ld l,a
        ld a,#>(_prepare_added)
        adc #0
        ld h,a
        ld a,e
        ld (hl+),a
        ld (hl),d
        cp #252
        ld a,d
        sbc #0
        ld a,e
        jr c,fpa_batch_tile
        add #4
        ld hl,#_strip_attrs
        add hl,bc
        set 3,(hl)
fpa_batch_tile:
        ld hl,#_output_tiles
        add hl,bc
        ld (hl),a
        inc c
        ld a,c
        ld (#_prepare_index),a
        jr fpa_batch_next
fpa_batch_close:
        xor a
        ld (#0x4000),a
        ret
fpa_repeat:
        ; The preceding cell pinned this ID and is still in the rollback log.
        ; Find the identical prefix in each ID plane. The palette and flips
        ; are independent per cell. BC starts as the current 0-based index.
        ld hl,#_strip_low
        add hl,bc
        ld a,(#_prepare_count)
        sub c
        ld b,a
        push bc
fpa_same_low:
        ld a,(hl+)
        cp e
        jr nz,fpa_low_end
        dec b
        jr nz,fpa_same_low
fpa_low_end:
        ld e,b
        pop bc
        ld a,b
        sub e
        ld e,a
        ld b,#0
        ld hl,#_strip_high
        add hl,bc
        ld b,e
fpa_same_high:
        ld a,(hl+)
        cp d
        jr nz,fpa_high_end
        dec b
        jr nz,fpa_same_high
fpa_high_end:
        ld a,e
        sub b
        ld b,a
        add c
        ld (#_prepare_index),a
        ld hl,#_prepare_added_count
        ld a,(hl)
        ld e,a
        add b
        ld (hl),a
        ld a,e
        add a,a
        add a,#<(_prepare_added-2)
        ld l,a
        ld a,#>(_prepare_added-2)
        adc a,#0
        ld h,a
        ld a,(hl+)
        ld e,a
        ld a,(hl+)
        ld d,a
        push bc
fpa_log_repeats:
        ld a,e
        ld (hl+),a
        ld a,d
        ld (hl+),a
        dec b
        jr nz,fpa_log_repeats
        pop bc
        ld h,d
        ld l,e
        add hl,hl
        push bc
        ld bc,#_world_cache_references
        add hl,bc
        pop bc
        ld a,(hl)
        add b
        ld (hl+),a
        jr nc,fpa_repeat_tiles
        inc (hl)
fpa_repeat_tiles:
        ld a,e
        cp #252
        ld a,d
        sbc a,#0
        ld a,e
        jr c,fpa_tile_run
        add a,#4
        push af
        ld hl,#_strip_attrs
        ld e,b
        ld b,#0
        add hl,bc
        ld b,e
fpa_bank_run:
        set 3,(hl)
        inc hl
        dec b
        jr nz,fpa_bank_run
        ld b,e
        pop af
fpa_tile_run:
        ld hl,#_output_tiles
        ld e,b
        ld b,#0
        add hl,bc
fpa_store_run:
        ld (hl+),a
        dec e
        jr nz,fpa_store_run
        ret
fpa_clear_free:
        ld a,e
        and #7
        add #<fpa_clear_masks
        ld l,a
        ld a,#>fpa_clear_masks
        adc #0
        ld h,a
        ld b,(hl)
        ; The complete slot is nine bits. Rotate its ninth bit into bit 5
        ; of the byte index, with no full-width shift or stack temporary.
        ld a,e
        rrca
        rrca
        rrca
        and #31
        bit 0,d
        jr z,fpa_free_index
        or #32
fpa_free_index:
        add #<(_world_cache_free_bits)
        ld l,a
        ld a,#>(_world_cache_free_bits)
        adc #0
        ld h,a
        ld a,(hl)
        and b
        ld (hl),a
        ret
fpa_clear_masks:
 .db 254,253,251,247,239,223,191,127
    __endasm;
}
#else
/* Near bank6 bookkeeping keeps the rollback slots in acquisition order.
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
        ld hl,#_strip_attrs
        add hl,bc
        set 3,(hl)
00110$:
        ld hl,#_output_tiles
        add hl,bc
        ld (hl),a
        ld hl,#_prepare_index
        inc (hl)
        ret
    __endasm;
}
#endif
#endif

static void prepare_publish(uint8_t vertical) {
#ifdef WORLD_MAP_PLANES
    gbc_video_world_strip_pair(prepare_strip_x,prepare_strip_y,vertical,prepare_count,output_tiles,strip_attrs);
#else
    /* The rollback log already holds this strip's complete ordered slots. */
    world_slot_strip_set(prepare_strip_x,prepare_strip_y,vertical,prepare_count,
                         prepare_added+(prepare_added_count-prepare_count));
    gbc_video_strip_pair(prepare_strip_x,prepare_strip_y,vertical,prepare_count,output_tiles,strip_attrs);
#endif
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
#ifdef WORLD_GRAPHICS_ZX0
                do {prepare_acquire();}
                while(!budgeted && prepare_index<prepare_count);
#else
                /* The outer guard covers the first item. Later items keep
                 * the same guard without repeating the stage dispatcher. */
                do {
                    prepare_acquire();
                    if(prepare_index>=prepare_count)break;
                    if(budgeted && !prepare_budget(start,20))return;
                } while(1);
#endif
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
#ifdef WORLD_GRAPHICS_ZX0
                do {prepare_acquire();}
                while(!budgeted && prepare_index<prepare_count);
#else
                /* The outer guard covers the first item. Later items keep
                 * the same guard without repeating the stage dispatcher. */
                do {
                    prepare_acquire();
                    if(prepare_index>=prepare_count)break;
                    if(budgeted && !prepare_budget(start,20))return;
                } while(1);
#endif
                if(prepare_index==prepare_count)prepare_stage=PREP_ROW_PUBLISH;
                break;
            case PREP_ROW_PUBLISH:
                prepare_publish(0);prepare_stage=PREP_READY;break;
        }
    }
}

void world_prepare(uint16_t old_x,uint16_t old_y,uint16_t x,uint16_t y,uint16_t start) BANKED {
    if(!prepare_matches(old_x,old_y,x,y)
       && (prepare_stage!=PREP_READY || !prepare_rebase_column(old_x,old_y,x,y,start,1))) {
        if(prepare_stage)prepare_cancel();
        if(!prepare_budget(start,21))return;
        /* Runtime camera movement is at most one tile on either axis. */
        if((uint16_t)((x>>3)-(old_x>>3)+1)>2
           || (uint16_t)((y>>3)-(old_y>>3)+1)>2)return;
        prepare_begin(old_x,old_y,x,y);
    }
    prepare_run(start,1);
}

#ifndef WORLD_GRAPHICS_ZX0
/* Finish a vertical run directly into the hidden column. The twenty cells
 * retained from the prepared row are already in VRAM and its SRAM mirror. */
static void finish_column(uint16_t x,uint16_t y,uint8_t count) {
    prepare_strip_x=x;prepare_strip_y=y;prepare_count=count;
    prepare_index=0;prepare_added_count=0;
    fetch_strip(x,y,1,count,0,0);
    do {prepare_acquire();} while(prepare_index<count);
    prepare_publish(1);
}

static uint8_t finish_prepared_row(uint16_t old_x,uint16_t old_y,uint16_t x,uint16_t y) {
    uint16_t left,slot,column;
    uint8_t i,right,down;
    if(prepare_horizontal || !prepare_vertical || prepare_added_count!=21 || retired_count!=21
       || ((prepare_old_x^old_x)|(prepare_old_y^old_y)|(prepare_y^y))>=8U)return 0;
    left=x>>3;
    if(left==prepare_old_left || (uint16_t)(left-prepare_old_left+1)>2)return 0;
    /* The original cancel-and-reacquire sequence can consume at most 19
     * free slots (18 column cells and one corner). If all next 19 slots
     * are free now, its circular allocator cannot select any of the 21
     * pinned row slots, even if a column hit revives another cached slot.
     * Both paths then choose identical slots, evictions and DMA uploads. */
    slot=next_slot;
    for(i=0;i<19;++i) {
        if(references[slot])return 0;
        if(++slot==CACHE_COUNT)slot=0;
    }
    right=left>prepare_old_left;
    down=prepare_top>prepare_old_top;
    world_refs_retire_fixed(prepare_added+(right?0:20),1);
    /* The prepared outgoing row already contains the corner belonging to
     * the outgoing column. Retire its other eighteen cells at commit. */
    release_strip(right?prepare_old_left:prepare_old_left+20,
                  down?prepare_old_top+1:prepare_old_top,1,18);
    column=right?left+20:left;
    if(down)finish_column(column,prepare_top,19);
    else {
        /* Keep original allocation order: non-corner cells then corner. */
        finish_column(column,prepare_top+1,18);
        finish_column(column,prepare_top,1);
    }
    prepare_stage=PREP_READY;
    return 1;
}
#endif

void world_scroll(uint16_t old_x,uint16_t old_y,uint16_t x,uint16_t y) BANKED {
    if(((old_x^x)|(old_y^y))<8U) {
        /* A lookahead target stays hidden while this tile remains current.
         * Preserve both its new refs and partially acquired strip buffers. */
        if(prepare_stage && ((prepare_old_x^old_x)|(prepare_old_y^old_y))>=8U)
            prepare_cancel();
        move_bkg((uint8_t)x,(uint8_t)y);return;
    }
    if(!prepare_matches(old_x,old_y,x,y)
       && ((prepare_stage!=PREP_READY
#ifndef WORLD_GRAPHICS_ZX0
            && prepare_stage!=PREP_COL_ACQUIRE
#endif
           ) || (!prepare_rebase_column(old_x,old_y,x,y,0,0)
#ifndef WORLD_GRAPHICS_ZX0
               && !(prepare_stage==PREP_READY && finish_prepared_row(old_x,old_y,x,y))
#endif
           ))) {
        if(prepare_stage)prepare_cancel();
        prepare_begin(old_x,old_y,x,y);
    }
    prepare_run(0,0);
    move_bkg((uint8_t)x,(uint8_t)y);
    world_refs_retire_fixed(retired,retired_count);
    prepare_stage=PREP_NONE;prepare_added_count=0;retired_count=0;
}
