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
static uint8_t close_point(int16_t x,int16_t y,uint16_t radius,uint32_t radius2){
    if(x>=(int16_t)radius||x<=-(int16_t)radius||y>=(int16_t)radius||y<=-(int16_t)radius)return 0;
    return(uint32_t)(mul16(x,x)+mul16(y,y))<radius2;
}

/* Exact squared-distance comparison without a64-bit multiplication:
 * |cross|=q*R+r. Only the ambiguous q^2<=L^2<(q+1)^2 case needs
 * 2*R*q*r+r^2 < R^2*(L^2-q^2). Both sides fit32 for these8m pieces.
 */
static uint8_t close_segment(int16_t x,int16_t y,int16_t dx,int16_t dy,uint32_t length2,
                            uint16_t radius,uint32_t radius2,int32_t c){
    int16_t adx,ady;
    int32_t dot;
    uint32_t distance,q2,delta,left,right;
    uint16_t q,r;
    if(!length2)return close_point(x,y,radius,radius2);
    dot=mul16(x,dx)+mul16(y,dy);
    if(dot<=0)return close_point(x,y,radius,radius2);
    if((uint32_t)dot>=length2)return close_point(x-dx,y-dy,radius,radius2);
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

/* Keep the infinite-line rejection first, then reuse its exact cross
 * products through the finite capsule. With d=q-p and e=b-a, c0=(p-a)x e,
 * cd=d x e and ca=(a-p)x d give the other three crosses by addition.
 * Bounded8m pieces keep all relative vectors in signed16 and products32. */
static uint8_t capsule(int16_t px,int16_t py,int16_t qx,int16_t qy,
                       const seg_t *s,uint16_t radius){
    int16_t ax=s->px,ay=s->py,ex=s->dx,ey=s->dy;
    int16_t bx=ax+ex,by=ay+ey,dx=qx-px,dy=qy-py,x=px-ax,y=py-ay;
    uint32_t d2,e2,r2;
    int32_t c0=cross(x,y,ex,ey),cd=0,ca=0;
    /* Stored length is nearest-integer; len+1 bounds its exact length. */
    int32_t limit=mul16((int16_t)radius,SEG_LENGTH(s)+1);
    uint8_t have_cd=0,have_ca=0;
    if(!(c0<limit && c0>-limit)){
        cd=cross(dx,dy,ex,ey);have_cd=1;
        if(c0>=limit ? c0+cd>=limit : c0+cd<=-limit)return 0;
    }
    if(maximum(px,qx)+(int16_t)radius<=minimum(ax,bx)||minimum(px,qx)-(int16_t)radius>=maximum(ax,bx)
       ||maximum(py,qy)+(int16_t)radius<=minimum(ay,by)||minimum(py,qy)-(int16_t)radius>=maximum(ay,by))return 0;
    if(maximum(px,qx)>=minimum(ax,bx)&&minimum(px,qx)<=maximum(ax,bx)
       &&maximum(py,qy)>=minimum(ay,by)&&minimum(py,qy)<=maximum(ay,by)){
        if(!have_cd){cd=cross(dx,dy,ex,ey);have_cd=1;}
        ca=cross(-x,-y,dx,dy);have_ca=1;
        if(straddles(ca,ca-cd)&&straddles(c0,c0+cd))return 1;
    }
    d2=(uint32_t)(mul16(dx,dx)+mul16(dy,dy));
    e2=(uint32_t)(mul16(ex,ex)+mul16(ey,ey));r2=(uint32_t)mul16(radius,radius);
    if(close_segment(x,y,ex,ey,e2,radius,r2,c0))return 1;
    if(!have_cd)cd=cross(dx,dy,ex,ey);
    if(close_segment(x+dx,y+dy,ex,ey,e2,radius,r2,c0+cd))return 1;
    if(!have_ca)ca=cross(-x,-y,dx,dy);
    if(close_segment(-x,-y,dx,dy,d2,radius,r2,ca))return 1;
    return close_segment(ex-x,ey-y,dx,dy,d2,radius,r2,ca-cd);
}

/* Cached wheel-expanded boxes conservatively contain the smaller head
 * capsule. Reject distant records before constructing the exact predicate. */
static uint8_t scan(int16_t px,int16_t py,int16_t qx,int16_t qy,uint16_t radius){
    if(!Seg_left)return 0;
    uint8_t x0=seg_box1(minimum(px,qx)),x1=seg_box1(maximum(px,qx));
    uint8_t y0=seg_box1(minimum(py,qy)),y1=seg_box1(maximum(py,qy));
    const seg_t *s;
    while((s=seg_next())){
        if(x1<s->x0||x0>s->x1||y1<s->y0||y0>s->y1)continue;
        if(capsule(px,py,qx,qy,s,radius))return 1;
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
static uint16_t clear_x,clear_y;

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
        jp z,_riding_swept_head_uncached
        ld c,a
        ld hl,#_clear_x
        ld a,(hl+)
        ld e,a
        ld d,(hl)
        ldhl sp,#7
        call head_axis_clear
        jr nz,head_uncached
        ldhl sp,#15
        call head_axis_clear
        jr nz,head_uncached
        ld hl,#_clear_y
        ld a,(hl+)
        ld e,a
        ld d,(hl)
        ldhl sp,#11
        call head_axis_clear
        jr nz,head_uncached
        ldhl sp,#19
        call head_axis_clear
        ret z  ; On a match A is zero (no collision).
head_uncached:
        jp _riding_swept_head_uncached
head_axis_clear:
        ld a,(hl+)
        and a,c
        cp a,e
        ret nz
        ld a,(hl+)
        cp a,d
        ret nz
        ld a,(hl)
        or a,a
        ret
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
                clear_x=(uint16_t)((uint32_t)qx>>8)&(0xff00u|mask);
                clear_y=(uint16_t)((uint32_t)qy>>8)&(0xff00u|mask);
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
    return capsule(px,py,qx,qy,&s,radius);
}
#endif
