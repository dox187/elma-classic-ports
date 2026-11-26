/* Continuous head capsule against the original fixed-point polygon edges.
 * Geometry uses exact32-bit integer products after bounded8m path pieces.
 */
#ifdef __SDCC
#pragma bank 4
#endif
#include "physics_core.h"
#include "physics_math.h"

extern uint8_t Seg_subcell;
#if R_HEAD+2 > R_WHEEL
#error Cached wheel boxes must contain the swept head radius
#endif

#define minimum(a,b) ((int16_t)((a)<(b)?(a):(b)))
#define maximum(a,b) ((int16_t)((a)>(b)?(a):(b)))
#define absolute(x) ((int16_t)((x)<0?-(x):(x)))
static int32_t cross(int16_t ax,int16_t ay,int16_t bx,int16_t by){return mul16(ax,by)-mul16(ay,bx);}
static uint8_t straddles(int32_t a,int32_t b){return(a<=0&&b>=0)||(a>=0&&b<=0);}
#if defined(__SDCC) && R_HEAD == 244
/* Largest |y| strictly inside the circle, at every possible |x|. The
 * ordinary sweep and the subdivided sweep use radii 244 and 246. */
static const uint8_t circle_y[2][246]={
    {
        243,243,243,243,243,243,243,243,243,243,243,243,243,243,243,243,243,243,243,243,
        243,243,243,242,242,242,242,242,242,242,242,242,241,241,241,241,241,241,241,240,
        240,240,240,240,239,239,239,239,239,239,238,238,238,238,237,237,237,237,237,236,
        236,236,235,235,235,235,234,234,234,234,233,233,233,232,232,232,231,231,231,230,
        230,230,229,229,229,228,228,227,227,227,226,226,225,225,225,224,224,223,223,223,
        222,222,221,221,220,220,219,219,218,218,217,217,216,216,215,215,214,214,213,213,
        212,211,211,210,210,209,208,208,207,207,206,205,205,204,203,203,202,201,201,200,
        199,199,198,197,196,196,195,194,193,193,192,191,190,190,189,188,187,186,185,185,
        184,183,182,181,180,179,178,177,176,175,175,174,173,172,171,170,168,167,166,165,
        164,163,162,161,160,159,157,156,155,154,153,151,150,149,147,146,145,143,142,141,
        139,138,136,135,133,132,130,129,127,125,124,122,120,119,117,115,113,111,109,107,
        105,103,101,99,96,94,91,89,86,84,81,78,75,72,69,65,61,58,53,49,
        43,38,31,22,
    },
    {
        245,245,245,245,245,245,245,245,245,245,245,245,245,245,245,245,245,245,245,245,
        245,245,245,244,244,244,244,244,244,244,244,244,243,243,243,243,243,243,243,242,
        242,242,242,242,242,241,241,241,241,241,240,240,240,240,239,239,239,239,239,238,
        238,238,238,237,237,237,236,236,236,236,235,235,235,234,234,234,233,233,233,232,
        232,232,231,231,231,230,230,230,229,229,228,228,228,227,227,226,226,226,225,225,
        224,224,223,223,222,222,221,221,221,220,220,219,219,218,217,217,216,216,215,215,
        214,214,213,213,212,211,211,210,210,209,208,208,207,206,206,205,204,204,203,202,
        202,201,200,200,199,198,197,197,196,195,194,194,193,192,191,191,190,189,188,187,
        186,185,185,184,183,182,181,180,179,178,177,176,175,174,173,172,171,170,169,168,
        167,166,165,164,163,162,160,159,158,157,156,155,153,152,151,149,148,147,145,144,
        143,141,140,138,137,135,134,132,131,129,128,126,124,123,121,119,117,115,113,112,
        110,108,105,103,101,99,97,94,92,89,87,84,81,78,75,72,69,65,62,58,
        53,49,44,38,31,22,
    },
};
#endif
static uint8_t close_point(int16_t x,int16_t y,uint16_t radius,uint32_t radius2){
    if(x>=(int16_t)radius||x<=-(int16_t)radius||y>=(int16_t)radius||y<=-(int16_t)radius)return 0;
#if defined(__SDCC) && R_HEAD == 244
    if(radius==244 || radius==246)
        return (uint8_t)absolute(y)<=circle_y[radius==246][(uint8_t)absolute(x)];
#endif
    return(uint32_t)(mul16(x,x)+mul16(y,y))<radius2;
}

/* Exact squared-distance comparison without a64-bit multiplication:
 * |cross|=q*R+r. Only the ambiguous q^2<=L^2<(q+1)^2 case needs
 * 2*R*q*r+r^2 < R^2*(L^2-q^2). Both sides fit32 for these8m pieces.
 */
static uint8_t close_line(int16_t dx,int16_t dy,uint32_t length2,
                          uint16_t radius,uint32_t radius2,int32_t c){
    int16_t adx,ady;
    uint32_t distance,q2,delta,left,right;
    uint16_t q,r;
    distance=c<0?(uint32_t)(-c):(uint32_t)c;
    adx=absolute(dx);ady=absolute(dy);
    if(distance<(uint32_t)mul16(radius,maximum(adx,ady)))return 1;
    if(distance>=(uint32_t)mul16(radius,adx+ady))return 0;
    q=riding_div_u32_u16(distance,radius);
    q2=(uint32_t)mul16(q,q);
    if(q2>=length2)return 0;
    if(q2+2UL*q+1<=length2)return 1;
    r=(uint16_t)(distance-(uint32_t)mul16(q,radius));
    delta=length2-q2;
    left=(uint32_t)mul16(q,r)*(uint32_t)(2*radius)+(uint32_t)mul16(r,r);
    right=(uint32_t)mul16((int16_t)delta,(int16_t)radius2);
    if(radius2&32768UL)right+=delta<<16;
    return left<right;
}

static uint8_t close_segment(int16_t x,int16_t y,int16_t dx,int16_t dy,uint32_t length2,
                             uint16_t radius,uint32_t radius2,int32_t c){
    int32_t dot;
    if(!length2)return close_point(x,y,radius,radius2);
    dot=mul16(x,dx)+mul16(y,dy);
    if(dot<=0)return close_point(x,y,radius,radius2);
    if((uint32_t)dot>=length2)return close_point(x-dx,y-dy,radius,radius2);
    return close_line(dx,dy,length2,radius,radius2,c);
}

/* A path entirely in the endpoint's outward coordinate quadrant projects
 * beyond that endpoint at every point. Its distance to the edge therefore
 * equals its distance to the one vertex, including when the path is still.
 * A zero edge component imposes no restriction on that axis. */
static uint8_t behind(int16_t p,int16_t q,int16_t direction){
    if(direction>0)return p<=0 && q<=0;
    if(direction<0)return p>=0 && q>=0;
    return 1;
}

static uint8_t close_vertex(int16_t x,int16_t y,int16_t dx,int16_t dy,uint16_t radius){
    int16_t xq=x-dx,yq=y-dy;
    uint32_t r2=(uint32_t)mul16(radius,radius);
    if(!(dx|dy))return close_point(x,y,radius,r2);
    int32_t dot=mul16(xq,dx)+mul16(yq,dy);
    uint32_t d2;
    if(dot>=0)return close_point(xq,yq,radius,r2);
    d2=(uint32_t)(mul16(dx,dx)+mul16(dy,dy));
    if((uint32_t)(-dot)>=d2)return close_point(x,y,radius,r2);
    return close_line(dx,dy,d2,radius,r2,cross(x,y,dx,dy));
}

/* Keep the infinite-line rejection first, then reuse its exact cross
 * products through the finite capsule. With d=q-p and e=b-a, c0=(p-a)x e,
 * cd=d x e and ca=(a-p)x d give the other three crosses by addition.
 * Bounded8m pieces keep all relative vectors in signed16 and products32. */
static uint8_t capsule(int16_t px,int16_t py,int16_t qx,int16_t qy,
                       const seg_t *s,uint16_t radius,int32_t c0){
    int16_t ax=s->px,ay=s->py,ex=s->dx,ey=s->dy;
    int16_t bx=ax+ex,by=ay+ey,dx=qx-px,dy=qy-py,x=px-ax,y=py-ay;
    uint32_t d2,e2,r2;
    /* A sweep whose endpoints project inside a horizontal or vertical
     * edge stays above its finite span. The exact test then needs only
     * the transverse interval, including a strict miss at tangency. */
    if(!ey && ex){
        int16_t y1=qy-ay;
        if((y>=(int16_t)radius && y1>=(int16_t)radius) ||
           (y<=-(int16_t)radius && y1<=-(int16_t)radius))return 0;
        if(minimum(px,qx)>=minimum(ax,bx) && maximum(px,qx)<=maximum(ax,bx))return 1;
    }else if(!ex && ey){
        int16_t x1=qx-ax;
        if((x>=(int16_t)radius && x1>=(int16_t)radius) ||
           (x<=-(int16_t)radius && x1<=-(int16_t)radius))return 0;
        if(minimum(py,qy)>=minimum(ay,by) && maximum(py,qy)<=maximum(ay,by))return 1;
    }
    int32_t cd=0,ca=0;
    /* Stored length is nearest-integer; len+1 bounds its exact length. */
    int32_t limit=mul16((int16_t)radius,SEG_LENGTH(s)+1);
    uint8_t have_cd=0,have_ca=0;
    if(!(c0<limit && c0>-limit)){
        cd=cross(dx,dy,ex,ey);have_cd=1;
        if(c0>=limit ? c0+cd>=limit : c0+cd<=-limit)return 0;
    }
    if(behind(x,qx-ax,ex)&&behind(y,qy-ay,ey))
        return close_vertex(-x,-y,dx,dy,radius);
    if(behind(bx-px,bx-qx,ex)&&behind(by-py,by-qy,ey))
        return close_vertex(bx-px,by-py,dx,dy,radius);
    if(!have_cd)cd=cross(dx,dy,ex,ey);
    /* Nonparallel segments intersect exactly when both pairs of endpoints
     * straddle the other line. For parallel or degenerate segments the
     * four finite point-to-segment distances below already include overlap. */
    if(cd && straddles(c0,c0+cd)){
        ca=cross(-x,-y,dx,dy);have_ca=1;
        if(straddles(ca,ca-cd))return 1;
    }
    e2=(uint32_t)(mul16(ex,ex)+mul16(ey,ey));r2=(uint32_t)mul16(radius,radius);
    /* The advancing centre ordinarily enters the capsule at the new end.
     * Its distance to the terrain segment does not need the path length. */
    if(close_segment(x+dx,y+dy,ex,ey,e2,radius,r2,c0+cd))return 1;
    if(close_segment(x,y,ex,ey,e2,radius,r2,c0))return 1;
    d2=(uint32_t)(mul16(dx,dx)+mul16(dy,dy));
    if(!have_ca)ca=cross(-x,-y,dx,dy);
    if(close_segment(-x,-y,dx,dy,d2,radius,r2,ca))return 1;
    return close_segment(ex-x,ey-y,dx,dy,d2,radius,r2,ca-cd);
}

/* The cached box spans [edge_min-R_WHEEL, edge_max+R_WHEEL] on each
 * axis. An integer point strictly inside the head radius can extend at
 * most radius-1 units past the edge. Shift each query extreme by the
 * unused expansion before applying the same monotone saturated encoding.
 * A strict comparison of the encoded values therefore proves separation,
 * even when a long piece or a stored edge clips the encoding range. */
static uint8_t scan(int16_t px,int16_t py,int16_t qx,int16_t qy,uint16_t radius){
    if(!Seg_left)return 0;
    int16_t margin=R_WHEEL-(int16_t)radius+1;
    uint8_t x0=seg_box1(minimum(px,qx)+margin),x1=seg_box1(maximum(px,qx)-margin);
    uint8_t y0=seg_box1(minimum(py,qy)+margin),y1=seg_box1(maximum(py,qy)-margin);
    const seg_t *s;
    /* The swept centre stays within |dx|+|dy| of its first point. A
     * line farther than that plus the radius cannot meet the capsule.
     * Compute the common radius once for all edges in this leaf. */
    int16_t outer=radius+absolute(qx-px)+absolute(qy-py);
    while((s=seg_next())){
        if(x1<s->x0||x0>s->x1||y1<s->y0||y0>s->y1)continue;
        int32_t c=cross(px-s->px,py-s->py,s->dx,s->dy);
        int32_t limit=mul16(outer,SEG_LENGTH(s)+1);
        if(c>=limit || c<=-limit)continue;
        if(capsule(px,py,qx,qy,s,radius,c))return 1;
    }
    return 0;
}

static uint8_t piece(int32_t px,int32_t py,int32_t qx,int32_t qy,uint16_t radius){
    int32_t minx=px<qx?px:qx,maxx=px>qx?px:qx,miny=py<qy?py:qy,maxy=py>qy?py:qy;
    int32_t x0=(riding_sra8(minx)>>4),x1=(riding_sra8(maxx)>>4),y0=(riding_sra8(miny)>>4),y1=(riding_sra8(maxy)>>4),bx,by,v;
    uint8_t cx,cy,sx,sy,sx0,sx1,sy0,sy1;
    if(x1<0||y1<0||x0>254||y0>254)return 0;
    if(x0<0)x0=0;if(y0<0)y0=0;if(x1>254)x1=254;if(y1>254)y1=254;
    for(cy=(uint8_t)y0;cy<=(uint8_t)y1;++cy)for(cx=(uint8_t)x0;cx<=(uint8_t)x1;++cx){
        bx=(int32_t)cx*4096L;by=(int32_t)cy*4096L;
        v=minx-bx;sx0=v<=0?0:(uint8_t)(v>>10);
        v=maxx-bx;sx1=v>=4095?3:(uint8_t)(v>>10);
        v=miny-by;sy0=v<=0?0:(uint8_t)(v>>10);
        v=maxy-by;sy1=v>=4095?3:(uint8_t)(v>>10);
        for(sy=sy0;sy<=sy1;++sy)for(sx=sx0;sx<=sx1;++sx){
            seg_query(cx,cy,(sy<<2)|sx);
            if(scan((int16_t)(px-bx),(int16_t)(py-by),(int16_t)(qx-bx),(int16_t)(qy-by),radius))return 1;
            if(Seg_subcell==255)goto next_cell;
        }
next_cell:;
    }
    return 0;
}

#ifdef __SDCC
extern uint8_t riding_head_clear_mask;
uint16_t riding_head_clear_x,riding_head_clear_y;
#ifdef RIDING_HEAD_TERRAIN
static uint8_t head_tiles[4];
extern uint16_t riding_head_cell_mask(uint8_t cx,uint8_t cy);
static const uint16_t head_bits[16]={
    1,2,4,8,16,32,64,128,256,512,1024,2048,4096,8192,16384,32768
};
/* Inclusive spans of columns and rows inside a 4 m cell, indexed by 4*lo+hi. */
static const uint16_t head_columns[16]={
    0x1111,0x3333,0x7777,0xffff,0,0x2222,0x6666,0xeeee,0,0,0x4444,0xcccc,0,0,0,0x8888
};
static const uint16_t head_rows[16]={
    0x000f,0x00ff,0x0fff,0xffff,0,0x00f0,0x0ff0,0xfff0,0,0,0x0f00,0xff00,0,0,0,0xf000
};

/* The metre dictionary groups four adjacent 4 m cells. Each occupied
 * metre gets a conservative 4x4 mask in the group's sparse quarter map. */
typedef struct {uint16_t address; uint8_t bank;} head_quarter_level_t;
extern const head_quarter_level_t head_quarter_levels[];
extern const uint16_t head_quarter_palette[];
extern const uint8_t head_count_bits[],riding_head_level_count;
extern uint8_t head_group_index,head_cache_x,head_cache_y,head_cache_level,physics_level_index;
extern uint8_t riding_head_quarter_code(uint16_t address,uint8_t bank,uint8_t group,
    uint8_t cell,uint8_t rank) __sdcccall(0);
static uint8_t head_fractions[4];
static uint8_t quarter_level=0;
static uint8_t quarter_x,quarter_y;
static uint16_t quarter_mask;
/* A failed map proof in a single quarter means every sweep starting in
 * that quarter can proceed directly to the finite terrain records. */
static uint16_t occupied_x,occupied_y;
static uint8_t occupied_level;

uint16_t riding_head_quarters(uint8_t tx,uint8_t ty) {
    uint8_t level=physics_level_index,cx=tx>>2,cy=ty>>2;
    if(level>=riding_head_level_count)return 0xffff;
    if(quarter_level==level+1 && quarter_x==tx && quarter_y==ty)return quarter_mask;
    uint16_t coarse=riding_head_cell_mask(cx,cy);
    uint16_t bit=head_bits[(tx&3)|((ty&3)<<2)];
    if(!(coarse&bit))return 0;
    const head_quarter_level_t *desc=&head_quarter_levels[level];
    if(!desc->address || head_cache_level!=level+1 || cx!=head_cache_x || cy!=head_cache_y)return 0xffff;
    coarse&=bit-1;
    uint8_t rank=head_count_bits[(uint8_t)coarse]+head_count_bits[(uint8_t)(coarse>>8)];
    quarter_mask=head_quarter_palette[riding_head_quarter_code(desc->address,desc->bank,
        head_group_index,cx&3,rank)];
    quarter_x=tx;quarter_y=ty;quarter_level=level+1;
    return quarter_mask;
}

static uint8_t head_refine_clear(void) {
    uint16_t xe=4u*head_tiles[2]+head_fractions[2],ye=4u*head_tiles[3]+head_fractions[3];
    uint16_t x0=4u*head_tiles[0]+head_fractions[0],y0=4u*head_tiles[1]+head_fractions[1];
    uint16_t x1=xe,y1=ye,t;
    if(x0>x1){t=x0;x0=x1;x1=t;}
    if(y0>y1){t=y0;y0=y1;y1=t;}
    /* At most a 2 m span per axis. Longer sweeps keep the original DDA
     * and its enlarged radius. Inspect every closed quarter in the box. */
    if(x1-x0>=8 || y1-y0>=8)return 0;
    uint8_t xlo=x0>>2,xhi=x1>>2,ylo=y0>>2,yhi=y1>>2,x,y;
    for(y=ylo;;++y){
        uint8_t lo=y==ylo?(y0&3):0,hi=y==yhi?(y1&3):3;
        uint16_t rows=head_rows[4*lo+hi];
        for(x=xlo;;++x){
            lo=x==xlo?(x0&3):0;hi=x==xhi?(x1&3):3;
            if(riding_head_quarters(x,y)&rows&head_columns[4*lo+hi]){
                if(x0==x1 && y0==y1){
                    occupied_x=xe;occupied_y=ye;occupied_level=physics_level_index+1;
                }
                return 0;
            }
            if(x==xhi)break;
        }
        if(y==yhi)break;
    }
    riding_head_clear_x=xe;riding_head_clear_y=ye;riding_head_clear_mask=0xff;
    return 1;
}
/* A zero mask extends the cached certificate to the whole coarse cell. */
static void head_remember(uint8_t tx,uint8_t ty,uint8_t mask) __naked {
    tx;ty;mask;
    __asm
        ld b,a
        ldhl sp,#2
        ld a,(hl)
        ld (#_riding_head_clear_mask),a
        cp #0xf0
        jr nz,head_cache_coords
        ld a,b
        and #0xfc
        ld b,a
        ld a,e
        and #0xfc
        ld e,a
head_cache_coords:
        ld l,b
        ld h,#0
        add hl,hl
        add hl,hl
        ld a,l
        ld (#_riding_head_clear_x),a
        ld a,h
        ld (#_riding_head_clear_x+1),a
        ld l,e
        ld h,#0
        add hl,hl
        add hl,hl
        ld a,l
        ld (#_riding_head_clear_y),a
        ld a,h
        ld (#_riding_head_clear_y+1),a
        pop hl
        inc sp
        jp (hl)
    __endasm;
}

static uint8_t head_single_clear(uint8_t tx,uint8_t ty){
    uint16_t occupied=riding_head_cell_mask(tx>>2,ty>>2);
    if(occupied & head_bits[(tx&3)|((ty&3)<<2)])return 0;
    head_remember(tx,ty,occupied?0xfc:0xf0);
    return 1;
}

static uint8_t head_terrain_clear(void) {
    uint8_t x0=head_tiles[0],y0=head_tiles[1],x1=head_tiles[2],y1=head_tiles[3];
    uint8_t cx,cy,last_x,last_y,t;
    uint16_t occupied;
    if(x0>x1){t=x0;x0=x1;x1=t;}
    if(y0>y1){t=y0;y0=y1;y1=t;}
    /* At an eight-tile difference the fractional positions can take the
     * sweep beyond 8 m. Keep the original DDA and enlarged radius there. */
    if(x1-x0>=8 || y1-y0>=8)return 0;
    last_x=x1>>2;last_y=y1>>2;
    for(cy=y0>>2;cy<=last_y;++cy){
        uint8_t lo=cy==(y0>>2)?(y0&3):0;
        uint8_t hi=cy==last_y?(y1&3):3;
        uint16_t rows=head_rows[lo*4+hi];
        for(cx=x0>>2;cx<=last_x;++cx){
            lo=cx==(x0>>2)?(x0&3):0;
            hi=cx==last_x?(x1&3):3;
            occupied=riding_head_cell_mask(cx,cy);
            if(occupied & rows & head_columns[lo*4+hi])return 0;
        }
    }
    /* The sweep may run towards the smaller coordinate. Remember its
     * actual endpoint; its containing metre is certified by this check. */
    head_remember(head_tiles[2],head_tiles[3],0xfc);
    return 1;
}
#endif


/* A cached nonempty leaf can still have whole square metres free of all
 * wheel-expanded boxes. Test the query endpoint's 1 m tile in that leaf.
 * A matching pair of endpoints puts their entire sweep inside the tile. */
static uint8_t tile_clear(uint16_t origin) __naked {
    origin;
    __asm
        ; DE is the tile's lower corner in the record's 64u box units.
        ld a,(#_Seg_left)
        ld b,a
        ld hl,#_Seg_cur
        ld a,(hl+)
        ld h,(hl)
        ld l,a
        ld a,#14
tile_advance:
        add a,l
        ld l,a
        ld a,h
        adc a,#0
        ld h,a
        ld a,(hl+)
        and a,#0xf0
        cp e
        jr z,tile_xmax
        jr c,tile_xmax
        ld a,#17
        jr tile_next
tile_xmax:
        ld a,(hl+)
        cp e
        jr nc,tile_ymin
        ld a,#16
        jr tile_next
tile_ymin:
        ld a,(hl+)
        and a,#0xf0
        cp d
        jr z,tile_ymax
        jr c,tile_ymax
        ld a,#15
        jr tile_next
tile_ymax:
        ld a,(hl+)
        cp d
        jr nc,tile_occupied
        ld a,#14
tile_next:
        dec b
        jr nz,tile_advance
        ld a,#1
        ret
tile_occupied:
        xor a
        ret
    __endasm;
}
/* In the banked ABI the four coordinates start at SP+6. A zero-count leaf
 * contains no wheel-expanded boxes. Both endpoints inside that same convex
 * 4 m cell (or 1 m child) prove the complete head path clear. Compare all
 * integer bits, including the high byte that rules out negative coordinates.
 * The mask selects bits 12..31 or 10..31 of each coordinate. */
uint8_t riding_swept_head(int32_t px,int32_t py,int32_t qx,int32_t qy) PH_BANKED __naked {
    px;py;qx;qy;
    __asm
        ld a,(#_riding_head_clear_mask)
        or a,a
        jr z,head_uncached
        ld c,a
        ld hl,#_riding_head_clear_x
        ld a,(hl+)
        ld e,a
        ld d,(hl)
        ldhl sp,#7
        ld a,(hl+)
        and c
        cp e
        jr nz,head_uncached
        ld a,(hl+)
        cp d
        jr nz,head_uncached
        ld a,(hl)
        or a
        jr nz,head_uncached
        ldhl sp,#15
        ld a,(hl+)
        and c
        cp e
        jr nz,head_uncached
        ld a,(hl+)
        cp d
        jr nz,head_uncached
        ld a,(hl)
        or a
        jr nz,head_uncached
        ld hl,#_riding_head_clear_y
        ld a,(hl+)
        ld e,a
        ld d,(hl)
        ldhl sp,#11
        ld a,(hl+)
        and c
        cp e
        jr nz,head_uncached
        ld a,(hl+)
        cp d
        jr nz,head_uncached
        ld a,(hl)
        or a
        jr nz,head_uncached
        ldhl sp,#19
        ld a,(hl+)
        and c
        cp e
        jr nz,head_uncached
        ld a,(hl+)
        cp d
        jr nz,head_uncached
        ld a,(hl)
        or a
        ret z   ; A is zero on a complete certificate match.
head_uncached:
_riding_head_terrain_query::
#ifdef RIDING_HEAD_TERRAIN
        ld a,(#_physics_level_index)
        inc a
        ld hl,#_occupied_level
        cp (hl)
        jr nz,head_read_map
        ld hl,#_occupied_x
        ld a,(hl+)
        ld e,a
        ld d,(hl)
        ldhl sp,#7
        ld a,(hl+)
        cp e
        jr nz,head_read_map
        ld a,(hl+)
        cp d
        jr nz,head_read_map
        ld a,(hl)
        or a
        jr nz,head_read_map
        ld hl,#_occupied_y
        ld a,(hl+)
        ld e,a
        ld d,(hl)
        ldhl sp,#11
        ld a,(hl+)
        cp e
        jr nz,head_read_map
        ld a,(hl+)
        cp d
        jr nz,head_read_map
        ld a,(hl)
        or a
        jp z,_riding_swept_head_uncached
head_read_map:
        ; Native banked stack still contains both Q10 endpoints. Extract the
        ; eight metre bits only after checking all remaining high bits.
        ldhl sp,#7
        ld de,#_head_tiles
        ld b,#4
head_tile_coordinate:
        ld a,(hl+)
        ld c,a
        ld a,(hl+)
        cp #4
        jr nc,head_original
        rra
        rr c
        rra
        rr c
        ld a,(hl+)
        or a,a
        jr nz,head_original
        ld a,c
        ld (de),a
        inc de
        inc hl
        dec b
        jr nz,head_tile_coordinate
        ld hl,#_head_tiles
        ld a,(hl+)
        ld b,a
        ld e,(hl)
        inc hl
        cp (hl)
        jr nz,head_multi_tile
        inc hl
        ld a,e
        cp (hl)
        jr nz,head_multi_tile
        ld a,b
        call _head_single_clear
        jr head_map_result
head_multi_tile:
        call _head_terrain_clear
head_map_result:
        or a,a
        jr nz,head_map_clear
        ldhl sp,#7
        ld de,#_head_fractions
        ld b,#4
head_quarter_coordinate:
        ld a,(hl+)
        and #3
        ld (de),a
        inc de
        inc hl
        inc hl
        inc hl
        dec b
        jr nz,head_quarter_coordinate
        call _head_refine_clear
        or a,a
        jr z,head_original
head_map_clear:
        xor a,a
        ret
head_original:
#endif
        jp _riding_swept_head_uncached
    __endasm;
}
#define HEAD_QUERY riding_swept_head_uncached
#else
#define HEAD_QUERY riding_swept_head
#endif
uint8_t HEAD_QUERY(int32_t px,int32_t py,int32_t qx,int32_t qy) PH_BANKED {
    /* Most frames stay in one convex4m cell. Unsplit cells, or one1m leaf,
     * already contain every possible hit for the whole center segment. */
    if((((uint32_t)px^(uint32_t)qx)|((uint32_t)py^(uint32_t)qy))<4096UL){
        uint8_t cx=seg_cell(px),cy=seg_cell(py);
        if(cx!=255&&cy!=255){
            int16_t x0=(int16_t)((uint16_t)px&4095),y0=(int16_t)((uint16_t)py&4095);
            int16_t x1=(int16_t)((uint16_t)qx&4095),y1=(int16_t)((uint16_t)qy&4095);
            uint8_t a=(uint8_t)((x0>>10)|((y0>>8)&12));
            uint8_t b=(uint8_t)((x1>>10)|((y1>>8)&12));
            seg_query(cx,cy,b);
#ifdef __SDCC
            uint8_t mask=0;
            if(!Seg_left) mask=Seg_subcell==255?0xf0:0xfc;
            else {
                uint8_t lo=(uint8_t)(128u+((b&3u)<<4));
                uint8_t hi=(uint8_t)(128u+((b&12u)<<2));
                if(tile_clear(((uint16_t)hi<<8)|lo))mask=0xfc;
            }
            if(mask) {
                riding_head_clear_x=(uint16_t)((uint32_t)qx>>8)&(0xff00u|mask);
                riding_head_clear_y=(uint16_t)((uint32_t)qy>>8)&(0xff00u|mask);
                riding_head_clear_mask=mask;
                if(mask==0xf0||a==b)return 0;
            }
#endif
            if(Seg_subcell==255||a==b)return scan(x0,y0,x1,y1,R_HEAD);
        }
    }
    int32_t dx=qx-px,dy=qy-py,sx,sy,nx,ny;
    uint32_t ax=dx<0?(uint32_t)-dx:(uint32_t)dx,ay=dy<0?(uint32_t)-dy:(uint32_t)dy;
    uint16_t count=(uint16_t)(((ax>ay?ax:ay)+8191)>>13),i,rx,ry,errx=0,erry=0;
    int8_t signx=dx<0?-1:1,signy=dy<0?-1:1;
    if(count<=1)return piece(px,py,qx,qy,R_HEAD);
    /* Integer DDA vertices deviate by less than sqrt(2)u from the original
     * line. Only this >8m-per-frame fallback enlarges the radius by2u. */
    sx=dx/count;sy=dy/count;rx=(uint16_t)(ax%count);ry=(uint16_t)(ay%count);
    for(i=0;i<count;++i){
        nx=px+sx;ny=py+sy;errx+=rx;erry+=ry;
        if(errx>=count){nx+=signx;errx-=count;}if(erry>=count){ny+=signy;erry-=count;}
        if(piece(px,py,nx,ny,R_HEAD+2))return 1;px=nx;py=ny;
    }
    return 0;
}

#ifdef PHYSICS_SWEEP_TEST
uint8_t riding_capsule_test(int16_t px,int16_t py,int16_t qx,int16_t qy,
 int16_t ax,int16_t ay,int16_t ex,int16_t ey,uint16_t radius) PH_BANKED {
    seg_t s;
    s.px=ax;s.py=ay;s.dx=ex;s.dy=ey;
    s.len=(int16_t)isqrt32((uint32_t)(mul16(ex,ex)+mul16(ey,ey)));
    uint8_t narrow=capsule(px,py,qx,qy,&s,radius,cross(px-ax,py-ay,ex,ey));
    /* Build the same saturated wheel bounds as the geometry exporter and
     * check the broad phase independently of the direct capsule result. */
    s.x0=seg_box1(minimum(ax,ax+ex)-R_WHEEL);
    s.x1=seg_box1(maximum(ax,ax+ex)+R_WHEEL);
    s.y0=seg_box1(minimum(ay,ay+ey)-R_WHEEL);
    s.y1=seg_box1(maximum(ay,ay+ey)+R_WHEEL);
    Seg_cur=&s;Seg_left=1;
    if(scan(px,py,qx,qy,radius)!=narrow)return 2;
    return narrow;
}
#endif
