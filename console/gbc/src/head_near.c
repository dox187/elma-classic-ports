/* Certify a whole 8-by-8 square in one already bound collision leaf. */
#pragma bank 1
#include "physics_core.h"
#include "physics_math.h"

uint8_t riding_head_near_xlow, riding_head_near_ylow;

uint8_t riding_head_near_clear(int16_t px,int16_t py) PH_BANKED {
    /* A square is contained in one 1 m leaf. Its farthest point from
     * (origin+4,origin+4) is sqrt(32) units away, strictly less than six. */
    const uint16_t radius=R_HEAD+6;
    int16_t x=(px&~7)+4, y=(py&~7)+4;
    const int16_t margin=R_WHEEL-(int16_t)radius+1;
    uint8_t x0=seg_box1(x+margin),x1=seg_box1(x-margin);
    uint8_t y0=seg_box1(y+margin),y1=seg_box1(y-margin);
    const seg_t *s=Seg_cur;
    for (uint8_t left=Seg_left; left; --left, ++s) {
        if(x1<s->x0 || x0>s->x1 || y1<s->y0 || y0>s->y1) continue;
        /* The length stored by the packer is rounded. Its successor bounds
         * the true length from above. Separation from the infinite line
         * proves separation from its segment, including either endpoint. */
        int32_t cross=mul16(x-s->px,s->dy)-mul16(y-s->py,s->dx);
        int32_t limit=mul16(radius,SEG_LENGTH(s)+1);
        if(cross < limit && cross > -limit) return 0;
    }
    riding_head_near_xlow=(uint8_t)px&0xf8;
    riding_head_near_ylow=(uint8_t)py&0xf8;
    return 1;
}
