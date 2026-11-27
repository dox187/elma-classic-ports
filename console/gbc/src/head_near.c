/* Certify a whole 8-by-8 square in one already bound collision leaf. */
#pragma bank 1
#include "physics_core.h"
#include "physics_math.h"

uint8_t riding_head_near_xlow, riding_head_near_ylow;

/* Project onto the diagonal pointing from the first endpoint towards the
 * square center. A linear projection reaches its minimum at an endpoint.
 * The 4 m cell, 0.5 m search margin and 8 m segment limit bound each
 * coordinate difference by 12.5 m (plus endpoint rounding). Their sum
 * fits int16_t in Q10. */
static uint8_t diagonal_clear(int16_t x, int16_t y, int16_t dx, int16_t dy) {
    /* 99/70 bounds sqrt(2) from above. For the 250-unit enclosing circle
     * this rounds up to 354 units on the unnormalized diagonal. */
    const int16_t limit=((R_HEAD+6)*99L+69)/70;
    if(x<0) { x=-x; dx=-dx; }
    if(y<0) { y=-y; dy=-dy; }
    int16_t gap=x+y;
    return gap>=limit && gap-dx-dy>=limit;
}

static uint8_t edge_clear(const seg_t *s, int16_t x, int16_t y) {
    x-=s->px;
    y-=s->py;
    if(diagonal_clear(x,y,s->dx,s->dy)) return 1;
    /* The successor of the packed, rounded length bounds the true length. */
    int32_t cross=mul16(x,s->dy)-mul16(y,s->dx);
    int32_t limit=mul16(R_HEAD+6,SEG_LENGTH(s)+1);
    return cross>=limit || cross<=-limit;
}

uint8_t riding_head_near_clear(int16_t px,int16_t py) PH_BANKED {
    /* A square is contained in one 1 m leaf. Its farthest point from
     * (origin+4,origin+4) is sqrt(32) units away, strictly less than six. */
    const uint16_t radius=R_HEAD+6;
    int16_t x=(px&~7)+4, y=(py&~7)+4;
    const int16_t margin=R_WHEEL-(int16_t)radius+1;
    /* Both coordinates are local to a 4096-unit cell. The shifted
     * extrema therefore fit the unsaturated [-8192,8191] box encoding. */
    uint8_t x0=SEG_BOX(x+margin),x1=SEG_BOX(x-margin);
    uint8_t y0=SEG_BOX(y+margin),y1=SEG_BOX(y-margin);
    const seg_t *s=Seg_cur;
    for (uint8_t left=Seg_left; left; --left, ++s) {
        if(x1<s->x0 || x0>s->x1 || y1<s->y0 || y0>s->y1) continue;
        if(!edge_clear(s,x,y)) return 0;
    }
    riding_head_near_xlow=(uint8_t)px&0xf8;
    riding_head_near_ylow=(uint8_t)py&0xf8;
    return 1;
}
