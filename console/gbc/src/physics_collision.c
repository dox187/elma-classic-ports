/* Fixed-ROM reader and contact caches for all original internal levels. */
#include "physics_core.h"
#include "riding_level.h"
#ifdef __SDCC
#include <gb/gb.h>
#include <stddef.h>
#endif
#include <string.h>

#define CACHES 3
static seg_t cells[CACHES*RIDING_CELL_MAX];
static seg_t * const cell_records[CACHES]={cells,cells+RIDING_CELL_MAX,cells+2*RIDING_CELL_MAX};
static uint16_t cell_ids[CACHES];
static uint8_t cell_subcells[CACHES],cell_counts[CACHES];
static uint8_t next_cell;
physics_level_desc_t riding_level;
#ifndef __SDCC
int32_t physics_level_origin_x,physics_level_origin_y;
int32_t physics_level_start_x,physics_level_start_y;
#endif
uint8_t physics_level_index=255;
const seg_t *Seg_cur;
uint8_t Seg_left,Seg_subcell;
#ifdef __SDCC
/* Zero invalidates the swept-head empty rectangle on every collision reset. */
uint8_t riding_head_clear_mask;
#ifdef RIDING_PC_SCHEDULE
/* The general wheel iterator memoizes projections by FIFO record address. */
uint8_t riding_contact_regions_dirty;
uint8_t riding_window_valid[2];
uint8_t riding_leaf_regions_dirty;
#endif
#if !defined(PHYSICS_WHEEL_C) && !defined(PHYSICS_CONTACT_LOOP_C) && !defined(PHYSICS_SEGMENT_SCAN_C)
void riding_surface_reset(void) __nonbanked;
#endif
#endif

typedef struct {uint16_t address;uint8_t bank,count;} cell_pointer_t;
typedef char descriptor_layout[sizeof(physics_level_desc_t)==48?1:-1];
#ifdef __SDCC
typedef char coordinate_layout[offsetof(physics_level_desc_t,origin_x)==0 &&
    offsetof(physics_level_desc_t,origin_y)==4 && offsetof(physics_level_desc_t,start_x)==8 &&
    offsetof(physics_level_desc_t,start_y)==12 ? 1 : -1];
#endif
typedef char cell_pointer_layout[sizeof(cell_pointer_t)==4?1:-1];

/* High ROM bank bits exist only during this ROM0 copy. No banked function is
 * called until ROMB1=0 and GBDK's tracked low bank have both been restored.
 * The game's interrupt handlers and memcpy remain in fixed ROM0. */
static void read_data(void *dest,uint16_t bank,uint16_t address,uint16_t size) {
#ifdef __SDCC
    uint8_t previous=CURRENT_BANK;
    rROMB1=(uint8_t)(bank>>8);
    rROMB0=(uint8_t)bank;
    CURRENT_BANK=(uint8_t)bank;
    memcpy(dest,(const void *)address,size);
    rROMB1=0;
    rROMB0=previous;
    CURRENT_BANK=previous;
#else
    memcpy(dest,physics_bank_data[bank-RIDING_FIRST_BANK]+address-0x4000,size);
#endif
}

void physics_collision_reset(void) {
    uint8_t i;
#ifdef __SDCC
#if !defined(PHYSICS_WHEEL_C) && !defined(PHYSICS_CONTACT_LOOP_C) && !defined(PHYSICS_SEGMENT_SCAN_C)
    riding_surface_reset();
#endif
    riding_head_clear_mask=0;
#ifdef RIDING_PC_SCHEDULE
    riding_leaf_regions_dirty=riding_contact_regions_dirty=1;
    riding_window_valid[0]=riding_window_valid[1]=0;
#endif
#endif
    for(i=0;i<CACHES;++i)cell_ids[i]=65535;
    next_cell=0;Seg_left=0;
}

#if defined(__SDCC) && defined(RIDING_PC_SCHEDULE)
void riding_prepare_level_bounds(void) __banked;
#endif

uint8_t physics_collision_select(uint8_t index) {
    if(index>=RIDING_LEVEL_COUNT)return 0;
#ifdef __SDCC
    read_data(&riding_level,RIDING_DESCRIPTOR_BANK,(uint16_t)&physics_levels[index],sizeof(riding_level));
#else
    memcpy(&riding_level,&physics_levels[index],sizeof(riding_level));
#endif
#ifdef __SDCC
    /* The exported coordinates are the first four 32-bit fields of the selected
     * descriptor. Give its fields the existing cartridge symbol names. */
    __asm
        .globl _physics_level_origin_x, _physics_level_origin_y
        .globl _physics_level_start_x, _physics_level_start_y
        _physics_level_origin_x = _riding_level
        _physics_level_origin_y = _riding_level+4
        _physics_level_start_x = _riding_level+8
        _physics_level_start_y = _riding_level+12
    __endasm;
#else
    physics_level_origin_x=riding_level.origin_x;
    physics_level_origin_y=riding_level.origin_y;
    physics_level_start_x=riding_level.start_x;
    physics_level_start_y=riding_level.start_y;
#endif
#if defined(__SDCC) && defined(RIDING_PC_SCHEDULE)
    riding_prepare_level_bounds();
#endif
    physics_level_index=index;
    physics_collision_reset();
    return 1;
}

#ifdef __SDCC
typedef char cache_query_layout[offsetof(physics_level_desc_t,width)==22 &&
    offsetof(physics_level_desc_t,height)==23 &&
    offsetof(physics_level_desc_t,base_bank)==16 && offsetof(physics_level_desc_t,directory_bank)==18 &&
    offsetof(physics_level_desc_t,directory_address)==20 && sizeof(seg_t)==18 ? 1 : -1];

void seg_query(uint8_t cx,uint8_t cy,uint8_t subcell) __naked {
    cx;cy;subcell;
    __asm
#ifdef RIDING_PC_SCHEDULE
    .globl _candidate_slots, _candidate_cell_ids, _candidate_subcells
    _candidate_slots = _cell_records
    _candidate_cell_ids = _cell_ids
    _candidate_subcells = _cell_subcells
#endif
    ; ABI1 A=cx, E=cy, SP+2=subcell. FFFF never names an in-range cell.
    ld d,a
    ld hl,#(_riding_level+22)
    cp (hl)
    jr nc,seg_outside
    inc hl
    ld a,e
    cp (hl)
    jr nc,seg_outside
    ldhl sp,#2
    ld c,(hl)
    ld hl,#_cell_ids
    ld a,(hl+)
    cp d
    jr nz,seg_test_slot1
    ld a,(hl)
    cp e
    jr nz,seg_test_slot1
    ld a,(#_cell_subcells)
    cp c
    jr z,seg_hit0
    cp #255
    jr nz,seg_test_slot1
seg_hit0:
    ld (#_Seg_subcell),a
    ld a,(#_cell_counts)
    ld hl,#_cells
    jr seg_hit

seg_test_slot1:
    ld hl,#(_cell_ids+2)
    ld a,(hl+)
    cp d
    jr nz,seg_test_slot2
    ld a,(hl)
    cp e
    jr nz,seg_test_slot2
    ld a,(#(_cell_subcells+1))
    cp c
    jr z,seg_hit1
    cp #255
    jr nz,seg_test_slot2
seg_hit1:
    ld (#_Seg_subcell),a
    ld a,(#(_cell_counts+1))
    ld hl,#(_cells+18*RIDING_CELL_MAX)
    jr seg_hit

seg_test_slot2:
    ld hl,#(_cell_ids+4)
    ld a,(hl+)
    cp d
    jr nz,seg_miss
    ld a,(hl)
    cp e
    jr nz,seg_miss
    ld a,(#(_cell_subcells+2))
    cp c
    jr z,seg_hit2
    cp #255
    jr nz,seg_miss
seg_hit2:
    ld (#_Seg_subcell),a
    ld a,(#(_cell_counts+2))
    ld hl,#(_cells+36*RIDING_CELL_MAX)
seg_hit:
    ld (#_Seg_left),a
    ld a,l
    ld (#_Seg_cur),a
    ld a,h
    ld (#_Seg_cur+1),a
seg_return:
    pop hl
    inc sp
    jp (hl)
seg_outside:
    xor a
    ld (#_Seg_left),a
    dec a
    ld (#_Seg_subcell),a
    jr seg_return
seg_miss:
    ; DE = cx:cy, C = subcell. Directory entries are four bytes.
    push de
    push bc
    ld a,(#(_riding_level+22))
    ld c,a
    ld b,#0
    ld d,b
    call __mulint
    ldhl sp,#3
    ld l,(hl)
    ld h,#0
    add hl,bc
    add hl,hl
    add hl,hl
    ld d,h
    ld e,l
    ld hl,#(_riding_level+18)
    ld a,(hl+)
    ld (#0x2000),a
    ld a,(hl+)
    ld (#0x3000),a
    ld a,(hl+)
    ld h,(hl)
    ld l,a
    add hl,de
    call seg_read_pointer
    ld a,b
    cp #255
    jr nz,seg_whole_cell
    call seg_map_relative
    pop hl
    push hl
    ld h,#0
    add hl,hl
    add hl,hl
    add hl,de
    call seg_read_pointer
    pop hl
    ld a,l
    jr seg_install
seg_whole_cell:
    pop hl
    ld a,#255
seg_install:
    ; Save the record source and the key while installing the next FIFO slot.
    pop hl
    push bc
    push de
    push hl
    push af
#ifdef RIDING_PC_SCHEDULE
    ; A different resident key, including an empty level leaf, can change
    ; the slot which seg_query would return on the next reference.
    xor a
    ld (#_riding_window_valid),a
    ld (#(_riding_window_valid+1)),a
#endif
    ld a,(#_next_cell)
    ld e,a
    ld d,#0
    inc a
    cp #3
    jr nz,seg_next_slot
    xor a
seg_next_slot:
    ld (#_next_cell),a
    ld hl,#_cell_subcells
    add hl,de
    pop af
    ld (hl),a
    ld (#_Seg_subcell),a
    ld hl,#_cell_ids
    add hl,de
    add hl,de
    pop bc
    ld (hl),b
    inc hl
    ld (hl),c
    ld hl,#_cell_records
    add hl,de
    add hl,de
    ld a,(hl+)
    ld (#_Seg_cur),a
    ld a,(hl)
    ld (#_Seg_cur+1),a
    ld hl,#_cell_counts
    add hl,de
    pop de
    pop bc
    ld (hl),b
    ld a,b
    ld (#_Seg_left),a
    or a
    jr z,seg_restore
#ifdef RIDING_PC_SCHEDULE
    ; This slot is about to overwrite the records named by wheel certificates.
    ld (#_riding_contact_regions_dirty),a
    ld (#_riding_leaf_regions_dirty),a
#endif
    call seg_map_relative
    ld h,d
    ld l,e
    ld a,(#_Seg_cur)
    ld e,a
    ld a,(#_Seg_cur+1)
    ld d,a
seg_copy_record:
    ; A counted record copy has one loop branch per 18-byte segment. Both
    ; full pointers advance across pages, including the last byte in a bank.
    .rept 18
    ld a,(hl+)
    ld (de),a
    inc de
    .endm
    dec b
    jr nz,seg_copy_record
seg_restore:
    ; IRQ handlers execute in fixed ROM. As in the terrain lookup reader,
    ; keep the logical GBDK bank and restore both physical bank bits.
    xor a
    ld (#0x3000),a
    ld a,(#__current_bank)
    ld (#0x2000),a
    jp seg_return

seg_read_pointer:
    ; DE = record address, C = bank relative to base_bank, B = count.
    ld a,(hl+)
    ld e,a
    ld a,(hl+)
    ld d,a
    ld a,(hl+)
    ld c,a
    ld b,(hl)
    ret
seg_map_relative:
    ld hl,#(_riding_level+16)
    ld a,(hl+)
    add c
    ld (#0x2000),a
    ld a,(hl)
    adc #0
    ld (#0x3000),a
    ret
    __endasm;
}
#else
void seg_query(uint8_t cx,uint8_t cy,uint8_t subcell) {
    uint16_t id;
    uint8_t c,sub=255;
    cell_pointer_t pointer;
    if(cx>=riding_level.width||cy>=riding_level.height){
        Seg_left=0;Seg_subcell=255;return;
    }
    /* Cache identity needs only the two coordinates. Delay the directory's
     * row multiplication until a miss; all levels are smaller than256 cells
     * on either axis, so FFFF remains reserved for an invalid entry. */
    id=((uint16_t)cy<<8)|cx;
    if(cell_ids[0]==id && (cell_subcells[0]==255 || cell_subcells[0]==subcell)){c=0;goto found;}
    if(cell_ids[1]==id && (cell_subcells[1]==255 || cell_subcells[1]==subcell)){c=1;goto found;}
    if(cell_ids[2]==id && (cell_subcells[2]==255 || cell_subcells[2]==subcell)){c=2;goto found;}
    read_data(&pointer,riding_level.directory_bank,
              riding_level.directory_address+((uint16_t)cy*riding_level.width+cx)*4,4);
    if(pointer.count==255) {
        read_data(&pointer,riding_level.base_bank+pointer.bank,pointer.address+(uint16_t)subcell*4,4);
        sub=subcell;
    }
    c=next_cell;
    if(++next_cell==CACHES)next_cell=0;
    cell_ids[c]=id;cell_subcells[c]=sub;
    cell_counts[c]=pointer.count;
    if(pointer.count)
        read_data(cell_records[c],riding_level.base_bank+pointer.bank,pointer.address,(uint16_t)pointer.count*sizeof(seg_t));
found:
    Seg_cur=cell_records[c];Seg_left=cell_counts[c];Seg_subcell=cell_subcells[c];
}
#endif

const seg_t *seg_next(void) {
    if(!Seg_left)return 0;
    --Seg_left;return Seg_cur++;
}
