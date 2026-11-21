/* Fixed-ROM reader and contact caches for all original internal levels. */
#include "physics_core.h"
#include "riding_level.h"
#ifdef __SDCC
#include <gb/gb.h>
#endif
#include <string.h>

#define CACHES 3
static seg_t cells[CACHES][RIDING_CELL_MAX];
static uint16_t cell_ids[CACHES];
static uint8_t cell_subcells[CACHES],cell_counts[CACHES];
static uint8_t next_cell;
physics_level_desc_t riding_level;
int32_t physics_level_origin_x,physics_level_origin_y;
int32_t physics_level_start_x,physics_level_start_y;
uint8_t physics_level_index=255;
const seg_t *Seg_cur;
uint8_t Seg_left,Seg_subcell;

typedef struct {uint16_t address;uint8_t bank,count;} cell_pointer_t;
typedef char descriptor_layout[sizeof(physics_level_desc_t)==48?1:-1];
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
    for(i=0;i<CACHES;++i)cell_ids[i]=65535;
    next_cell=0;Seg_left=0;
}

uint8_t physics_collision_select(uint8_t index) {
    if(index>=RIDING_LEVEL_COUNT)return 0;
#ifdef __SDCC
    read_data(&riding_level,RIDING_DESCRIPTOR_BANK,(uint16_t)&physics_levels[index],sizeof(riding_level));
#else
    memcpy(&riding_level,&physics_levels[index],sizeof(riding_level));
#endif
    physics_level_origin_x=riding_level.origin_x;
    physics_level_origin_y=riding_level.origin_y;
    physics_level_start_x=riding_level.start_x;
    physics_level_start_y=riding_level.start_y;
    physics_level_index=index;
    physics_collision_reset();
    return 1;
}

void seg_query(uint8_t cx,uint8_t cy,uint8_t subcell) {
    uint16_t id;
    uint8_t c,sub=255;
    cell_pointer_t pointer;
    Seg_left=0;Seg_subcell=255;
    if(cx>=riding_level.width||cy>=riding_level.height)return;
    /* Cache identity needs only the two coordinates. Delay the directory's
     * row multiplication until a miss; all levels are smaller than256 cells
     * on either axis, so FFFF remains reserved for an invalid entry. */
    id=((uint16_t)cy<<8)|cx;
    for(c=0;c<CACHES;++c)
        if(cell_ids[c]==id && (cell_subcells[c]==255 || cell_subcells[c]==subcell))goto found;
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
        read_data(cells[c],riding_level.base_bank+pointer.bank,pointer.address,(uint16_t)pointer.count*sizeof(seg_t));
found:
    Seg_cur=cells[c];Seg_left=cell_counts[c];Seg_subcell=cell_subcells[c];
}

const seg_t *seg_next(void) {
    if(!Seg_left)return 0;
    --Seg_left;return Seg_cur++;
}
