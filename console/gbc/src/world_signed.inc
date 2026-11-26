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
/* Most courses fit these 308-column and 260-row lookup ranges. Keep the
 * division fallback for larger maps supported by the 16-bit camera. */
#define COLUMN_CYCLE 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21
#define ROW_CYCLE    0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19
static const uint8_t column_modulo[]={
    COLUMN_CYCLE,COLUMN_CYCLE,COLUMN_CYCLE,COLUMN_CYCLE,COLUMN_CYCLE,COLUMN_CYCLE,COLUMN_CYCLE,
    COLUMN_CYCLE,COLUMN_CYCLE,COLUMN_CYCLE,COLUMN_CYCLE,COLUMN_CYCLE,COLUMN_CYCLE,COLUMN_CYCLE
};
static const uint8_t row_modulo[]={
    ROW_CYCLE,ROW_CYCLE,ROW_CYCLE,ROW_CYCLE,ROW_CYCLE,ROW_CYCLE,ROW_CYCLE,
    ROW_CYCLE,ROW_CYCLE,ROW_CYCLE,ROW_CYCLE,ROW_CYCLE,ROW_CYCLE
};
static void set_coordinate_slots(uint16_t x,uint16_t y,uint8_t vertical){
    uint8_t column,row;
    if(all_patterns)return;
    column=x<sizeof(column_modulo)?column_modulo[x]:x%22U;
    row=y<sizeof(row_modulo)?row_modulo[y]:y%20U;
    coord_start=COORDINATE_FIRST+coord_steps[row]+column;
    coord_wrap=coord_start-(vertical?440:22);
    coord_boundary=vertical?20-row:22-column;
    coord_vertical=vertical;
}
static void prepare_acquire(void) __naked {
    __asm
        ld a,(#_all_patterns)
        or a
        jr z,coord_item
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
        ld a,(#_prepare_index)
        ld e,a
        ld d,#0
        ld hl,#_strip_low
        add hl,de
        ld c,(hl)
        ld hl,#_strip_high
        add hl,de
        ld b,(hl)
        ld h,#0xa0
        ld l,c
        ld a,(hl)
        or a
        jr z,coord_dynamic
        inc h
        ld d,a
        ld a,(hl)
        cp b
        jr nz,coord_dynamic
        ld a,d
        dec a
        jr coord_publish_low
coord_dynamic:
        ld d,#0
        push de
        ld a,(#_coord_vertical)
        or a
        jr z,coord_offset
        ld hl,#_coord_steps
        add hl,de
        add hl,de
        ld a,(hl+)
        ld d,(hl)
        ld e,a
coord_offset:
        ld hl,#_coord_start
        ld a,(#_prepare_index)
        push de
        ld e,a
        ld a,(#_coord_boundary)
        cp e
        jr z,coord_wrapped
        jr nc,coord_base
coord_wrapped:
        ld hl,#_coord_wrap
coord_base:
        pop de
        ld a,(hl+)
        ld h,(hl)
        ld l,a
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
        jr z,coord_publish_low
        ld hl,#_strip_attrs
        add hl,de
        set 3,(hl)
coord_publish_low:
        ld d,#0
        ld hl,#_output_tiles
        add hl,de
        ld (hl),a
        ld hl,#_prepare_index
        inc (hl)
        ld a,(hl)
        ld hl,#_prepare_count
        cp (hl)
        ret z
        and #3
        jp nz,coord_item
        ret
    __endasm;
}
static void prepare_publish(uint8_t vertical) {
    gbc_video_world_strip_pair(prepare_strip_x,prepare_strip_y,vertical,prepare_count,
                               all_patterns ? strip_low : output_tiles,strip_attrs);
}

void world_begin(uint16_t x,uint16_t y) BANKED {
    uint16_t i;
    prepare_stage=PREP_NONE;
    last_chunk=INVALID;
    world_cache_failures=world_uploads=0;
    ENABLE_RAM_MBC5;
    rRAMB=0;
    world_map_snapshot();
    all_patterns=game_world.pattern_count<=492;
    world_direct_map=all_patterns && direct_map_supported();
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
            set_coordinate_slots(prepare_strip_x,i,0);
            prepare_index=0;
            do {prepare_acquire();} while(prepare_index<21);
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
    while(prepare_stage!=PREP_NONE && prepare_stage!=PREP_READY) {
        if(prepare_stage==PREP_COL_FETCH) {
            prepare_strip_x=prepare_x>prepare_old_x?prepare_left+20:prepare_left;
            prepare_strip_y=prepare_vertical&&prepare_horizontal&&prepare_y<prepare_old_y?prepare_top+1:prepare_top;
            prepare_count=prepare_vertical&&prepare_horizontal?18:19;
        } else if(prepare_stage==PREP_ROW_FETCH) {
            prepare_strip_x=prepare_left;
            prepare_strip_y=prepare_y>prepare_old_y?prepare_top+18:prepare_top;
            prepare_count=21;
        }
        if(budgeted) {
            uint16_t lines=prepare_stage==PREP_COL_ACQUIRE||prepare_stage==PREP_ROW_ACQUIRE?20
                :prepare_stage==PREP_COL_FETCH||prepare_stage==PREP_ROW_FETCH?PREP_FETCH_LINES:25;
            if(!prepare_budget(start,lines))return;
        }
        switch(prepare_stage) {
            case PREP_COL_FETCH:
                prepare_index+=fetch_strip(prepare_strip_x,prepare_strip_y+prepare_index,1,
                                          prepare_count-prepare_index,prepare_index,budgeted);
                if(prepare_index==prepare_count) {
                    if(world_direct_map)prepare_stage=PREP_COL_PUBLISH;
                    else {
                        set_coordinate_slots(prepare_strip_x,prepare_strip_y,1);
                        prepare_index=0;
                        prepare_stage=PREP_COL_ACQUIRE;
                    }
                }
                break;
            case PREP_COL_PUBLISH:
                prepare_publish(1);
                prepare_index=0;
                prepare_stage=prepare_vertical&&prepare_horizontal?PREP_ROW_FETCH:PREP_READY;
                prepare_horizontal=1;break;
            case PREP_ROW_FETCH:
                prepare_index+=fetch_strip(prepare_strip_x+prepare_index,prepare_strip_y,0,
                                          prepare_count-prepare_index,prepare_index,budgeted);
                if(prepare_index==prepare_count) {
                    if(world_direct_map)prepare_stage=PREP_ROW_PUBLISH;
                    else {
                        set_coordinate_slots(prepare_strip_x,prepare_strip_y,0);
                        prepare_index=0;
                        prepare_stage=PREP_ROW_ACQUIRE;
                    }
                }
                break;
            case PREP_COL_ACQUIRE:
            case PREP_ROW_ACQUIRE:
                do {
                    prepare_acquire();
                    if(prepare_index==prepare_count)break;
                    if(budgeted && !prepare_budget(start,20))return;
                } while(1);
                ++prepare_stage;
                break;
            case PREP_ROW_PUBLISH:
                prepare_publish(0);prepare_vertical=1;prepare_stage=PREP_READY;break;
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
