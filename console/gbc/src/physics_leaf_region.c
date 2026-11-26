#pragma bank 31
#include "physics_core.h"
#include <stddef.h>

/* The plane evaluator shares offsets 4..12 and 17..20 with the wheel
 * surface cache. A full cache key also distinguishes windows of one leaf.
 * Ambiguous entries use bytes 5..8 for the narrowed span, 9..12 for
 * the exact center and 16..21 for admission and iterator results. */
typedef struct {
    uint8_t box_x, box_y;
    const seg_t *first;
    uint8_t kind;
    int16_t base_x, base_y, nx, ny;
    uint8_t count;
    const seg_t *end;
    uint8_t reserved;
    int32_t intercept;
    uint8_t padding[11];
} leaf_region_t;
typedef char leaf_region_layout[sizeof(leaf_region_t)==32 &&
    offsetof(leaf_region_t,first)==2 && offsetof(leaf_region_t,kind)==4 &&
    offsetof(leaf_region_t,base_x)==5 && offsetof(leaf_region_t,nx)==9 &&
    offsetof(leaf_region_t,count)==13 && offsetof(leaf_region_t,end)==14 &&
    offsetof(leaf_region_t,reserved)==16 && offsetof(leaf_region_t,intercept)==17 &&
    offsetof(leaf_region_t,padding)==21 ? 1 : -1];
leaf_region_t riding_leaf_regions[4];
extern int16_t riding_contact_qx, riding_contact_qy;
int16_t riding_terrain_dotq14(int16_t,int16_t,int16_t,int16_t);

/* A box spans 64 integer coordinates. From its center, either rounded
 * projection can move by at most ceil(32*(sqrt(2)+1/16384)) = 46.
 * Packed level records contain rounded Q14 unit directions. */
enum { DELTA=46, EMPTY=3, PLANE=4, UNIT_Y=5 };

const seg_t *riding_leaf_one;
uint8_t riding_leaf_proven;

void riding_leaf_classify(leaf_region_t *entry) {
    const seg_t *one=riding_leaf_one;
    int16_t cx=(riding_contact_qx & ~63)+32, cy=(riding_contact_qy & ~63)+32;
    /* The ordered scan passes exactly one possible contributor here. */
    int16_t x=cx-one->px, y=cy-one->py;
    if((uint16_t)(x+32736u)>=65472u || (uint16_t)(y+32736u)>=65472u) return;
    if(!riding_leaf_proven) {
        int16_t p=riding_terrain_dotq14(y,x,one->ey,one->ex);
        int16_t length=SEG_LENGTH(one);
        if((p < -DELTA && (one->len & SEG_INTERNAL_START)) ||
           (p > length+DELTA && (one->len & SEG_INTERNAL_END))) {
            entry->kind=EMPTY;
            return;
        }
        if(p<DELTA || p>=length-DELTA) return;
    }
    entry->base_x=cx-32-one->px;
    entry->base_y=cy-32-one->py;
    entry->nx=-one->ey;
    entry->ny=one->ex;
    entry->kind=((entry->ny==16384 || entry->ny==-16384) &&
                 (uint16_t)(entry->nx+127u)<255u) ? UNIT_Y : PLANE;
}
