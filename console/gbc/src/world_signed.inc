/* The old and incoming viewports span at most 22 by 20 cells. Their
 * coordinates are therefore distinct modulo this rectangle. Replacing an
 * entering cell cannot disturb a currently displayed tile, even after a
 * canceled diagonal prediction. Pinned patterns are immutable. */
extern const uint16_t world_scenery_pins[][52];
/* SRAM0 A000..A1FF holds the exact pin tags. A200..A56F holds a 16-bit
 * source ID for each of the 440 replaceable slots. The map mirror starts
 * at B000 and the journal at B800. SRAM0 stays selected during riding. */
#define COORDINATE_IDS 0xa200
#define COORDINATE_FIRST 52
#define COORDINATE_COUNT 440
static uint8_t all_patterns;
#ifdef WORLD_SCENERY_SLOTS
uint8_t world_load_scenery_slots(void) BANKED;
void world_preload_scenery_slot(uint8_t slot,uint16_t id) BANKED {
    world_cache_upload(256U+slot,id);
}
#endif
uint8_t world_direct_map;

/* With uniform-zero high bytes, the second plane already contains the
 * final attributes. On a resident course, packed high IDs are at most one:
 * their encoded bit is exactly the CGB tile-bank flag. Other encodings
 * retain the ordinary three-plane decode and the resident attribute pass. */
static uint8_t direct_map_supported(void) {
    uint16_t i,count=(uint16_t)game_world.chunks_x*game_world.chunks_y;
    world_far_t entry;
    for(i=0;i<count;++i) {
        world_far_copy(game_world.chunks.bank,(const uint8_t *)(game_world.chunks.address+4U*i),
                       (uint8_t *)&entry,sizeof(entry));
        if((entry.bank&0xfe00U)!=0x8000U && (entry.bank&0xfe00U)!=0x4000U)return 0;
    }
    return 1;
}
static uint16_t coord_start,coord_wrap;
static uint8_t coord_boundary,coord_vertical;
static const uint16_t coord_steps[]={0,22,44,66,88,110,132,154,176,198,220,242,264,286,308,330,352,374,396,418,440};
/* Residues for floor(coordinate/2). The high nibble is modulo 11, the
 * low nibble modulo 10. Appending the original parity restores modulo
 * 22 or 20 respectively, so both axes share the same 128-byte table. */
static const uint8_t coord_modulo[]={
    0x00,0x11,0x22,0x33,0x44,0x55,0x66,0x77,0x88,0x99,0xa0,0x01,0x12,0x23,0x34,0x45,
    0x56,0x67,0x78,0x89,0x90,0xa1,0x02,0x13,0x24,0x35,0x46,0x57,0x68,0x79,0x80,0x91,
    0xa2,0x03,0x14,0x25,0x36,0x47,0x58,0x69,0x70,0x81,0x92,0xa3,0x04,0x15,0x26,0x37,
    0x48,0x59,0x60,0x71,0x82,0x93,0xa4,0x05,0x16,0x27,0x38,0x49,0x50,0x61,0x72,0x83,
    0x94,0xa5,0x06,0x17,0x28,0x39,0x40,0x51,0x62,0x73,0x84,0x95,0xa6,0x07,0x18,0x29,
    0x30,0x41,0x52,0x63,0x74,0x85,0x96,0xa7,0x08,0x19,0x20,0x31,0x42,0x53,0x64,0x75,
    0x86,0x97,0xa8,0x09,0x10,0x21,0x32,0x43,0x54,0x65,0x76,0x87,0x98,0xa9,0x00,0x11,
    0x22,0x33,0x44,0x55,0x66,0x77,0x88,0x99,0xa0,0x01,0x12,0x23,0x34,0x45,0x56,0x67,
};
/* Both fetch stages leave the strip's exact tile origin in these two words.
 * The common 8-bit case indexes a residue table. A second page folds by
 * 256 modulo either period; larger unsigned coordinates use full division. */
static void set_coordinate_slots(uint8_t vertical) __naked {
    vertical;
    __asm
        ld (#_coord_vertical),a
        ld a,(#_all_patterns)
        or a
        ret nz
        ld hl,#_prepare_strip_x
        ld a,(hl+)
        ld e,a
        ld d,(hl)
        ld a,d
        or a
        jr z,coord_x_lookup
        dec a
        jr nz,coord_x_wide
        ld a,e
        add #14
        jr c,coord_x_wide
        ld e,a
coord_x_lookup:
        ld a,e
        rrca
        ld c,a
        and #127
        ld e,a
        ld d,#0
        ld hl,#_coord_modulo
        add hl,de
        ld a,(hl)
        swap a
        and #15
        rl c
        rla
        jr coord_x_ready
coord_x_wide:
        ld bc,#22
        call __moduint
        ld a,c
coord_x_ready:
        push af
        ld hl,#_prepare_strip_y
        ld a,(hl+)
        ld e,a
        ld d,(hl)
        ld a,d
        or a
        jr z,coord_y_lookup
        dec a
        jr nz,coord_y_wide
        ld a,e
        add #16
        jr c,coord_y_wide
        ld e,a
coord_y_lookup:
        ld a,e
        rrca
        ld c,a
        and #127
        ld e,a
        ld d,#0
        ld hl,#_coord_modulo
        add hl,de
        ld a,(hl)
        and #15
        rl c
        rla
        ld c,a
        jr coord_y_ready
coord_y_wide:
        ld bc,#20
        call __moduint
coord_y_ready:
        ld a,c
        add a
        ld e,a
        ld d,#0
        ld hl,#_coord_steps
        add hl,de
        ld a,(hl+)
        ld h,(hl)
        ld l,a
        pop af
        ld b,a
        add #52
        ld e,a
        add hl,de
        ld a,l
        ld (#_coord_start),a
        ld a,h
        ld (#_coord_start+1),a
        ld a,(#_coord_vertical)
        or a
        jr nz,coord_vertical_span
        ld a,#22
        sub b
        ld de,#-22
        jr coord_set_span
coord_vertical_span:
        ld a,#20
        sub c
        ld de,#-440
coord_set_span:
        ld (#_coord_boundary),a
        add hl,de
        ld a,l
        ld (#_coord_wrap),a
        ld a,h
        ld (#_coord_wrap+1),a
        ret
    __endasm;
}
static void prepare_acquire(uint8_t limit) __naked {
    limit;
    __asm
        ld c,a
        ld a,(#_all_patterns)
        or a
        jr z,coord_item
#ifdef WORLD_SCENERY_SLOTS
        dec a
        jp nz,scenery_slot_acquire
#endif
        ; An all-resident level maps each logical ID directly to its BG bank/tile.
        ld hl,#_strip_high
        ld de,#_strip_attrs
        ld a,(#_prepare_count)
        ld b,a
coord_full_attrs:
        ld a,(hl+)
        or a
        jr z,coord_full_next
        ld a,(de)
        or #8
        ld (de),a
coord_full_next:
        inc de
        dec b
        jr nz,coord_full_attrs
        ld a,(#_prepare_count)
        ld (#_prepare_index),a
        ret
coord_item:
        ; Resolve four cells per idle budget guard or all cells at publication.
        ; The low-ID plane becomes the published tile plane after acquisition.
        ld a,(#_prepare_index)
        ld e,a
        add c
        ld hl,#_prepare_count
        cp (hl)
        jr c,coord_group
        ld a,(hl)
coord_group:
        ld (#_prepare_index),a
        ld d,#0
        ld hl,#_strip_low
        add hl,de
        push hl
        ld hl,#_strip_high
        add hl,de
        pop de
        ld b,#0xa1
coord_pin:
        ld a,(de)
        ld c,a
        ld a,(bc)
        cp (hl)
        jr nz,coord_dynamic
        dec b
        ld a,(bc)
        or a
        jr z,coord_dynamic
        dec a
        inc b
coord_store:
        ld (de),a
        inc de
        inc hl
        ld a,(#_prepare_index)
        add #<(_strip_low)
        cp e
        jr nz,coord_pin
        ret
coord_dynamic:
        push hl
        push de
        ld b,(hl)
        ld a,e
        sub #<(_strip_low)
        ld e,a
        ld d,#0
        ld hl,#_coord_boundary
        cp (hl)
        ld hl,#_coord_start
        jr c,coord_base
        ld hl,#_coord_wrap
coord_base:
        ld a,(hl+)
        ld h,(hl)
        ld l,a
        ld a,(#_coord_vertical)
        or a
        jr z,coord_offset
        push hl
        ld hl,#_coord_steps
        add hl,de
        add hl,de
        ld a,(hl+)
        ld d,(hl)
        ld e,a
        pop hl
coord_offset:
        add hl,de
        ld d,h
        ld e,l
        ld hl,#(COORDINATE_IDS-2*COORDINATE_FIRST)
        add hl,de
        add hl,de
        ld a,(hl+)
        cp c
        jr nz,coord_replace
        ld a,(hl)
        cp b
        jr z,coord_resolved
coord_replace:
        ld (hl),b
        dec hl
        ld (hl),c
        push bc
        push de
        call _world_cache_upload
        pop de
        pop bc
coord_resolved:
        ld a,d
        or a
        ld a,e
        pop de
        jr z,coord_bank_ready
        ld h,d
        ld l,e
        ld bc,#(_strip_attrs-_strip_low)
        add hl,bc
        set 3,(hl)
coord_bank_ready:
        pop hl
        ld b,#0xa1
        jr coord_store
#ifdef WORLD_SCENERY_SLOTS
scenery_slot_acquire:
        ; All low IDs are immutable in VRAM bank 0. A high ID has one
        ; assigned bank-1 slot and a full two-byte tag in SRAM.
        ld a,(#_prepare_index)
        ld e,a
        ld d,#0
        add c
        ld hl,#_prepare_count
        cp (hl)
        jr c,scenery_slot_span
        ld a,(hl)
scenery_slot_span:
        ld (#_prepare_index),a
        sub e
        ld b,a
        ld hl,#_strip_high
        add hl,de
scenery_slot_next:
        ld a,(hl+)
        or a
        jr z,scenery_slot_done
        push hl
        push bc
        ld b,a
        ld de,#(_strip_low-_strip_high-1)
        add hl,de
        ld c,(hl)
        push hl
        add #0x9f
        ld h,a
        ld l,c
        ld e,(hl)
        pop hl
        ld (hl),e
        push de
        ld de,#(_strip_attrs-_strip_low)
        add hl,de
        set 3,(hl)
        pop de
        ld l,e
        ld h,#0xa4
        ld a,(hl)
        cp b
        jr nz,scenery_slot_replace
        dec h
        ld a,(hl)
        cp c
        jr z,scenery_slot_resolved
        inc h
scenery_slot_replace:
        ld (hl),b
        dec h
        ld (hl),c
        ld d,#1
        push bc
        push de
        call _world_cache_upload
        pop de
        pop bc
scenery_slot_resolved:
        pop bc
        pop hl
scenery_slot_done:
        dec b
        jr nz,scenery_slot_next
        ret
#endif
    __endasm;
}
/* Both input planes live in the same WRAM strip buffers on every signed
 * course. Supply them directly to the common map writer at publication. */
static void prepare_publish(uint8_t vertical) __naked {
    vertical;
    __asm
        ld c,a
        xor a
        ld (#0x4000),a
        ld a,(#_prepare_strip_y)
        and #31
        .rept 3
        rrca
        .endm
        ld e,a
        and #3
        or #0xb0
        ld h,a
        ld a,e
        and #0xe0
        ld e,a
        ld a,(#_prepare_strip_x)
        and #31
        or e
        ld l,a
        push hl
        ld a,(#_prepare_count)
        ld b,a
        ld de,#_strip_attrs
        ld hl,#_strip_low
        jp _world_write_planes
    __endasm;
}

extern uint8_t wheel_course_size[2];
/* The first 64 entries of each page are reserved for wheel-row metadata.
 * Five nine-entry scenery rows fit in the remainder, including every
 * released course. Larger level packs use their original ROM directory. */
static const uint16_t scenery_rows[15]={
    0xad40,0xad64,0xad88,0xadac,0xadd0,0xae40,0xae64,0xae88,
    0xaeac,0xaed0,0xaf40,0xaf64,0xaf88,0xafac,0xafd0
};
void world_prepare_directory(void) {
    uint16_t address=game_world.chunks.address;
    uint8_t i;
    if(wheel_course_size[1]<=64 && game_world.chunks_x<=9 && game_world.chunks_y<=15) {
        uint8_t bytes=4*game_world.chunks_x;
        for(i=0;i<game_world.chunks_y;++i) {
            uint16_t target=scenery_rows[i];
            raw_chunk_rows[i]=target;
            world_far_copy(game_world.chunks.bank,(const uint8_t *)address,(uint8_t *)target,bytes);
            address+=bytes;
        }
    } else {
        uint16_t bytes=4U*game_world.chunks_x;
        for(i=0;i<16;++i) {
            raw_chunk_rows[i]=address;
            address+=bytes;
        }
    }
}

void world_begin(uint16_t x,uint16_t y) BANKED {
    uint16_t i;
    prepare_stage=PREP_NONE;
    last_chunk=INVALID;
    world_cache_failures=world_uploads=0;
    raw_tile_bounds[0]=game_world.width>>3;
    raw_tile_bounds[1]=game_world.height>>3;
    ENABLE_RAM_MBC5;
    rRAMB=0;
    world_prepare_directory();
    world_map_snapshot();
    all_patterns=game_world.pattern_count<=492;
    world_direct_map=all_patterns && direct_map_supported();
#ifdef WORLD_SCENERY_SLOTS
    if(!all_patterns)all_patterns=world_load_scenery_slots();
    if(all_patterns==2) {
        for(i=0;i<256;++i)world_cache_upload(i,i);
    } else
#endif
    if(all_patterns) {
        for(i=0;i<game_world.pattern_count;++i)world_cache_upload(i,i);
    } else {
        uint16_t pins[52];
        memset((void *)COORDINATE_IDS,0xff,2U*COORDINATE_COUNT);
        memset((void *)0xa000,0,256);
        world_far_copy(447,(const uint8_t *)world_scenery_pins[world_level_index],
                       (uint8_t *)pins,sizeof(pins));
        for(i=0;i<52;++i) {
            uint16_t id=pins[i];
            ((volatile uint8_t *)0xa000)[(uint8_t)id]=i+1;
            ((volatile uint8_t *)0xa100)[(uint8_t)id]=(uint8_t)(id>>8);
            world_cache_upload(i,id);
        }
    }
    set_bkg_palette(0,7,palettes);
    prepare_strip_x=x>>3;
    prepare_count=21;
    for(i=y>>3;i<(y>>3)+19;++i) {
        prepare_strip_y=i;
        fetch_strip(prepare_strip_x,i,0,21,0,0);
        if(!world_direct_map) {
            set_coordinate_slots(0);
            prepare_index=0;
            prepare_acquire(21);
        }
        prepare_publish(0);
    }
    move_bkg((uint8_t)x,(uint8_t)y);
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
    prepare_index=0;
    prepare_stage=prepare_horizontal?PREP_COL_FETCH:prepare_vertical?PREP_ROW_FETCH:PREP_READY;
}

static uint8_t extend_ready(uint16_t old_x,uint16_t old_y,uint16_t x,uint16_t y) {
    uint16_t left=x>>3,top=y>>3;
    if(prepare_stage!=PREP_READY || prepare_horizontal==prepare_vertical ||
       ((prepare_old_x^old_x)|(prepare_old_y^old_y))>=8U ||
       left==prepare_old_left || top==prepare_old_top)return 0;
    if(prepare_horizontal && left==prepare_left) {
        /* The entering row supplies the new diagonal corner. */
        prepare_stage=PREP_ROW_FETCH;
    } else if(prepare_vertical && top==prepare_top) {
        /* Publish the entire entering column, including the new corner. */
        prepare_stage=PREP_COL_FETCH;
    } else return 0;
    prepare_x=x;prepare_y=y;prepare_left=left;prepare_top=top;
    prepare_index=0;
    return 1;
}

static void prepare_run(uint16_t start,uint8_t budgeted) {
    while(1) {
        switch(prepare_stage) {
            case PREP_COL_FETCH:
                if(!prepare_index) {
                    prepare_strip_x=prepare_x>prepare_old_x?prepare_left+20:prepare_left;
                    prepare_strip_y=prepare_vertical&&prepare_horizontal&&prepare_y<prepare_old_y?prepare_top+1:prepare_top;
                    prepare_count=prepare_vertical&&prepare_horizontal?18:19;
                }
                if(budgeted && !prepare_budget(start,PREP_FETCH_LINES))return;
                prepare_index+=fetch_strip(prepare_strip_x,prepare_strip_y+prepare_index,1,
                                          prepare_count-prepare_index,prepare_index,budgeted);
                if(prepare_index==prepare_count) {
                    if(world_direct_map)prepare_stage=PREP_COL_PUBLISH;
                    else {
                        set_coordinate_slots(1);
                        prepare_index=0;
                        prepare_stage=PREP_COL_ACQUIRE;
                    }
                }
                break;
            case PREP_COL_PUBLISH:
                if(budgeted && !prepare_budget(start,25))return;
                prepare_publish(1);
                prepare_index=0;
                prepare_stage=prepare_vertical&&prepare_horizontal?PREP_ROW_FETCH:PREP_READY;
                prepare_horizontal=1;break;
            case PREP_ROW_FETCH:
                if(!prepare_index) {
                    prepare_strip_x=prepare_left;
                    prepare_strip_y=prepare_y>prepare_old_y?prepare_top+18:prepare_top;
                    prepare_count=21;
                }
                if(budgeted && !prepare_budget(start,PREP_FETCH_LINES))return;
                prepare_index+=fetch_strip(prepare_strip_x+prepare_index,prepare_strip_y,0,
                                          prepare_count-prepare_index,prepare_index,budgeted);
                if(prepare_index==prepare_count) {
                    if(world_direct_map)prepare_stage=PREP_ROW_PUBLISH;
                    else {
                        set_coordinate_slots(0);
                        prepare_index=0;
                        prepare_stage=PREP_ROW_ACQUIRE;
                    }
                }
                break;
            case PREP_COL_ACQUIRE:
            case PREP_ROW_ACQUIRE:
                do {
                    if(budgeted && !prepare_budget(start,20))return;
                    prepare_acquire(budgeted?4:21);
                } while(prepare_index!=prepare_count);
                ++prepare_stage;
                break;
            case PREP_ROW_PUBLISH:
                if(budgeted && !prepare_budget(start,25))return;
                prepare_publish(0);prepare_vertical=1;prepare_stage=PREP_READY;break;
            default:
                return;
        }
    }
}

void world_prepare(uint16_t old_x,uint16_t old_y,uint16_t x,uint16_t y,uint16_t start) BANKED {
    if(!prepare_matches(old_x,old_y,x,y) && !extend_ready(old_x,old_y,x,y)) {
        prepare_stage=PREP_NONE;
        if(!prepare_budget(start,21))return;
        if((uint16_t)((x>>3)-(old_x>>3)+1)>2 || (uint16_t)((y>>3)-(old_y>>3)+1)>2)return;
        prepare_begin(old_x,old_y,x,y);
    }
    prepare_run(start,1);
}

void world_scroll(uint16_t old_x,uint16_t old_y,uint16_t x,uint16_t y) BANKED {
    if(((old_x^x)|(old_y^y))<8U) {
        if(prepare_stage && ((prepare_old_x^old_x)|(prepare_old_y^old_y))>=8U)
            prepare_stage=PREP_NONE;
    } else {
        if(!prepare_matches(old_x,old_y,x,y) && !extend_ready(old_x,old_y,x,y))prepare_begin(old_x,old_y,x,y);
        prepare_run(0,0);
        prepare_stage=PREP_NONE;
    }
    move_bkg((uint8_t)x,(uint8_t)y);
}
