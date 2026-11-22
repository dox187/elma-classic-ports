#ifdef __SDCC
#pragma bank 9
#endif
#include "physics_core.h"
#include "physics_math.h"
#include "physics_math32.h"
// Wheel torques are in units of 1/4 Nm. The constants are in physconst.h.
typedef struct {
	int16_t nx, ny;  // from the contact point to the center, 16384 is 1
	int16_t l;       // distance of the center, u
	int16_t tx, ty;  // the contact point, u from the origin of the lines
} contact_t;

#if defined(__SDCC) && !defined(PHYSICS_CONTACT_LOOP_C) && !defined(PHYSICS_SEGMENT_SCAN_C)
#include <stddef.h>
contact_t Ct[2];
/* The native iterator uses these exact layouts and the wheel-radius bounds. */
typedef char contact_loop_layout[sizeof(contact_t)==10 &&
 offsetof(contact_t,nx)==0 && offsetof(contact_t,ny)==2 && offsetof(contact_t,l)==4 &&
 offsetof(contact_t,tx)==6 && offsetof(contact_t,ty)==8 && sizeof(seg_t)==18 &&
 offsetof(seg_t,px)==0 && offsetof(seg_t,py)==2 && offsetof(seg_t,dx)==4 &&
 offsetof(seg_t,dy)==6 && offsetof(seg_t,ex)==8 && offsetof(seg_t,ey)==10 &&
 offsetof(seg_t,len)==12 && R_WHEEL==410?1:-1];
#else
static contact_t Ct[2];
#endif
// 2^18/sqrt( d2 ) for d2 in steps of 512 u^2 from 16384 u^2:
#ifdef __SDCC
#define Rsqrt riding_normal_rsqrt
const int16_t Rsqrt[] = {
#else
static const int16_t Rsqrt[] = {
#endif
#include "../../nes/src/rsqrt.inc"
};

// Unit vector and length of a short vector in u, d2 its length squared:
#ifdef __SDCC
/* The table kernel is fixed to the original297-entry reciprocal-root table. */
typedef char normal_table_layout[sizeof(Rsqrt)==594?1:-1];
void riding_normalize_deep(int16_t dx,int16_t dy,int32_t d2,contact_t *c) __sdcccall(0) {
 int16_t l=(int16_t)riding_isqrt20((uint32_t)d2);
 if(!l){c->nx=0;c->ny=16384;c->l=0;return;}
 c->nx=(int16_t)(((int32_t)dx<<14)/l);
 c->ny=(int16_t)(((int32_t)dy<<14)/l);
 c->l=l;
}
void riding_normal_fast(int16_t,int16_t,int32_t,contact_t*) __sdcccall(0);
#define normalize riding_normal_fast
#else
static void normalize( int16_t dx, int16_t dy, int32_t d2, contact_t* c ) {
	if( d2 < 16384 ) {
		// Deep in the ground, rare:
		int16_t l = (int16_t)riding_isqrt20( (uint32_t)d2 );
		if( l == 0 ) {
			c->nx = 0;
			c->ny = 16384;
			c->l = 0;
			return;
		}
		c->nx = (int16_t)(((int32_t)dx << 14)/l);
		c->ny = (int16_t)(((int32_t)dy << 14)/l);
		c->l = l;
		return;
	}
	uint16_t i = (uint16_t)(riding_sra8(d2-16384)>>1);
	if( i >= sizeof( Rsqrt )/sizeof( Rsqrt[0] ) )
		i = sizeof( Rsqrt )/sizeof( Rsqrt[0] )-1;
	int16_t r = Rsqrt[i];
	c->nx = sat16( mul16( dx, r ) >> 4 );
	c->ny = sat16( mul16( dy, r ) >> 4 );
	c->l = dotq14( c->nx, c->ny, dx, dy );
}

#endif

static void contact_point( contact_t* c, int16_t qx, int16_t qy ) {
	c->tx = qx-mulq14( c->nx, c->l );
	c->ty = qy-mulq14( c->ny, c->l );
}

/* Consume rejected boxes in record order, leaving the same cursor as the
 * original seg_next loop at every returned candidate and at exhaustion. */
#if defined(__SDCC) && !defined(PHYSICS_SEGMENT_SCAN_C)
#include <stddef.h>
typedef char segment_scan_layout[sizeof(seg_t)==18 && offsetof(seg_t,x0)==14 &&
 offsetof(seg_t,x1)==15 && offsetof(seg_t,y0)==16 && offsetof(seg_t,y1)==17?1:-1];
const seg_t *riding_segment_box(uint8_t bx,uint8_t by) __sdcccall(0);
#define segment_next_box riding_segment_box
#else
static const seg_t *segment_next_box(uint8_t bx,uint8_t by) {
	const seg_t *s;
	while( (s = seg_next()) ) {
		if( bx < s->x0 || bx > s->x1 || by < s->y0 || by > s->y1 )
			continue;
		return s;
	}
	return 0;
}
#endif

#if defined(__SDCC) && !defined(PHYSICS_CONTACT_LOOP_C) && !defined(PHYSICS_SEGMENT_SCAN_C)
/* Ct and the segment cursor already make contact queries serial. Keep only
 * the native iterator coordinates here; projection and merge math stay exact. */
int16_t riding_contact_qx, riding_contact_qy;
uint8_t riding_contacts_loop(int16_t,int16_t);
typedef char equal_contact_merge_radius[MERGE>0?1:-1];
uint8_t riding_contact_merge(void) {
 int16_t qx=riding_contact_qx,qy=riding_contact_qy;
	contact_point( &Ct[0], qx, qy );
 /* Equal normals and lengths project to the same point. Keep the final
  * normalization: rounding does not make that operation idempotent. */
 if(Ct[0].nx==Ct[1].nx && Ct[0].ny==Ct[1].ny && Ct[0].l==Ct[1].l) {
  int16_t ax=qx-Ct[0].tx, ay=qy-Ct[0].ty;
  Ct[1].tx=Ct[0].tx;Ct[1].ty=Ct[0].ty;
  normalize(ax,ay,mul16(ax,ax)+mul16(ay,ay),&Ct[0]);
  return 0;
 }
	contact_point( &Ct[1], qx, qy );
	int16_t dx = Ct[1].tx-Ct[0].tx, dy = Ct[1].ty-Ct[0].ty;
	if( dx < MERGE && dx > -MERGE && dy < MERGE && dy > -MERGE &&
		mul16( dx, dx )+mul16( dy, dy ) < (int32_t)MERGE*MERGE ) {
		// Merged into their average:
		int16_t ax = qx-Ct[0].tx-(dx >> 1);
		int16_t ay = qy-Ct[0].ty-(dy >> 1);
		normalize( ax, ay, mul16( ax, ax )+mul16( ay, ay ), &Ct[0] );
	}
	else
		return 2;
 return 0;
}
/* ABI1 passes X in DE:BC and Y on the stack. Save the low 12 bits of each
 * coordinate for the contact geometry. Only their upper bits select a grid
 * cell, so no signed32 shifts or full coordinate copies are needed. */
static uint8_t contacts(int32_t cx,int32_t cy) __naked {
 cx;cy;
 __asm
    ld a,b
    and a,#15
    ld h,a
    ld l,c
    push hl
    call contact_query_axis
    ld c,a
    push bc
    ldhl sp,#6
    ld a,(hl+)
    ld c,a
    ld a,(hl+)
    ld b,a
    ld a,(hl+)
    ld e,a
    ld d,(hl)
    ld a,b
    and a,#15
    ld h,a
    ld l,c
    push hl
    call contact_query_axis
    ld e,a
    ldhl sp,#5
    ld a,(hl)
    rrca
    rrca
    and a,#3
    ld b,a
    ldhl sp,#1
    ld a,(hl)
    and a,#12
    or a,b
    ld b,a
    ldhl sp,#2
    ld a,(hl)
    push bc
    inc sp
    call _seg_query
    pop bc
    pop de
    pop de
    call _riding_contacts_loop
    pop hl
    add sp,#4
    jp (hl)
contact_query_axis:
    ld a,d
    or a,a
    jr nz,contact_query_outside
    ld a,e
    cp a,#16
    jr nc,contact_query_outside
    swap a
    ld c,a
    ld a,b
    swap a
    and a,#15
    or a,c
    ret
contact_query_outside:
    ld a,#255
    ret
 __endasm;
}
#else
// talppontkereses of UTKOZES.CPP: at most two contact points of the wheel
// with its center at cx, cy (u).
static uint8_t contacts( int32_t cx, int32_t cy ) {
	uint8_t found = 0;
	const seg_t* s;
	int16_t qx = (int16_t)(cx & 4095), qy = (int16_t)(cy & 4095);
	seg_query( seg_cell(cx), seg_cell(cy), (uint8_t)((qx>>10)|((qy>>8)&12)) );
	uint8_t bx = SEG_BOX( qx ), by = SEG_BOX( qy );
	while( (s = segment_next_box(bx,by)) ) {
		int16_t x = qx-s->px, y = qy-s->py;
		int16_t d = dotq14( x, y, -s->ey, s->ex );
		if( d >= R_WHEEL || d <= -R_WHEEL )
			continue;
		int16_t pos = dotq14( x, y, s->ex, s->ey );
		contact_t* k = &Ct[found];
		if( pos >= 0 && pos <= SEG_LENGTH(s) ) {
            /* Half-open artificial pieces avoid duplicate normalization at a join. */
            if(pos==SEG_LENGTH(s) && ((uint16_t)s->len & SEG_INTERNAL_END))continue;
			if( d >= 0 ) {
				k->nx = -s->ey;
				k->ny = s->ex;
				k->l = d;
			}
			else {
				k->nx = s->ey;
				k->ny = -s->ex;
				k->l = -d;
			}
		}
		else {
			// Near an original endpoint; subdivision joins have no radial cap.
            if((uint16_t)s->len & (pos<0?SEG_INTERNAL_START:SEG_INTERNAL_END))
                continue;
			if( pos > 0 ) {
				x -= s->dx;
				y -= s->dy;
			}
			if( x >= R_WHEEL || x <= -R_WHEEL || y >= R_WHEEL || y <= -R_WHEEL )
				continue;
			int32_t d2 = mul16( x, x )+mul16( y, y );
			if( d2 >= (int32_t)R_WHEEL*R_WHEEL )
				continue;
			normalize( x, y, d2, k );
		}
		if( found == 0 ) {
			found = 1;
			continue;
		}
		contact_point( &Ct[0], qx, qy );
		contact_point( &Ct[1], qx, qy );
		int16_t dx = Ct[1].tx-Ct[0].tx, dy = Ct[1].ty-Ct[0].ty;
		if( dx < MERGE && dx > -MERGE && dy < MERGE && dy > -MERGE &&
				mul16( dx, dx )+mul16( dy, dy ) < (int32_t)MERGE*MERGE ) {
			// Merged into their average:
			int16_t ax = qx-Ct[0].tx-(dx >> 1);
			int16_t ay = qy-Ct[0].ty-(dy >> 1);
			normalize( ax, ay, mul16( ax, ax )+mul16( ay, ay ), &Ct[0] );
		}
		else
			return 2;
	}
	return found;
}

#endif

// Whether a circle at cx, cy (u) touches the ground:
uint8_t riding_touches( int32_t cx, int32_t cy, int16_t rad ) PH_BANKED {
	const seg_t* s;
	int16_t qx = (int16_t)(cx & 4095), qy = (int16_t)(cy & 4095);
	seg_query( seg_cell(cx), seg_cell(cy), (uint8_t)((qx>>10)|((qy>>8)&12)) );
	uint8_t bx = SEG_BOX( qx ), by = SEG_BOX( qy );
	// The box is larger by the radius of a wheel, more than rad:
	while( (s = segment_next_box(bx,by)) ) {
		int16_t x = qx-s->px, y = qy-s->py;
		int16_t d = dotq14( x, y, -s->ey, s->ex );
		if( d >= rad || d <= -rad )
			continue;
		int16_t pos = dotq14( x, y, s->ex, s->ey );
		if( pos >= 0 && pos <= SEG_LENGTH(s) )
			return 1;
		if((uint16_t)s->len & (pos<0?SEG_INTERNAL_START:SEG_INTERNAL_END))continue;
		if( pos > 0 ) {
			x -= s->dx;
			y -= s->dy;
		}
		if( mul16( x, x )+mul16( y, y ) < (int32_t)rad*rad )
			return 1;
	}
	return 0;
}

// helyigazitas: does not let the wheel into the ground deeper than the band.
// The other contact point gets farther by the push along its direction.
static void pushout( circle_t* k, contact_t* c, contact_t* other ) {

    int32_t fine_l=(int32_t)c->l*256+riding_dotq32(k->rx&255,k->ry&255,c->nx,c->ny,14);
    int32_t push=103547-fine_l;
    if(push<=0)return;
    int32_t px=riding_mulq32(push,c->nx,14),py=riding_mulq32(push,c->ny,14);
    k->rx+=px;k->ry+=py;c->l+=(push+128)>>8;
    if(other)other->l+=(riding_dotq32(px,py,other->nx,other->ny,14)+128)>>8;

}

// talppontigazitas: true if the point really supports the wheel. With two
// points, the velocity towards it is removed (with one, rolling around it
// takes only the velocity along the ground anyway).
#if defined(__SDCC) && !defined(PHYSICS_WHEEL_C)
#include <stddef.h>
typedef char wheel_contact_layout[sizeof(contact_t)==10 && offsetof(contact_t,nx)==0 && offsetof(contact_t,ny)==2?1:-1];
uint8_t riding_supports32(circle_t*,const contact_t*,int32_t,int32_t,uint8_t);
void riding_free32(circle_t*,int32_t,int32_t,int32_t) __sdcccall(0);
void riding_roll32(circle_t*,const contact_t*,int32_t,int32_t,int32_t) __sdcccall(0);
#define supports riding_supports32
#else
static uint8_t supports( circle_t* k, const contact_t* c, int32_t dvx, int32_t dvy,
						 uint8_t remove ) {
	int32_t nv = riding_dotq32(k->vx,k->vy,c->nx,c->ny,14);
	if( nv > -ELSZ && riding_dotq32(dvx,dvy,c->nx,c->ny,14) > 0 )
		return 0;
	if( remove ) {
		k->vx -= riding_mulq32(nv,c->nx,14);
		k->vy -= riding_mulq32(nv,c->ny,14);
	}
	return 1;
}
#endif


static uint8_t same_side( int32_t d, int32_t m ) {
	return !((d < 0 && m > 0) || (d > 0 && m < 0));
}

// biztostalppont_uj: true if the wheel stays on t1 turning around t2.
/* Preserve the complete projected impulse before deciding its sign. */

static uint8_t sure_new(const contact_t *t1,const contact_t *t2,const circle_t *k) {
 int16_t d=dotq14(t1->tx-t2->tx,t1->ty-t2->ty,-t2->ny,t2->nx);
 int32_t vn,m;
 if(!d)return 1;
 vn=riding_dotq32(k->vx,k->vy,-t2->ny,t2->nx,14);
 m=k->omega+KMUL32(riding_mulshift32(vn,t2->l,10),C_NEW);
 return same_side(d,m);
}
static uint8_t sure_old(const contact_t *t1,const contact_t *t2,int32_t dvx,int32_t dvy,int32_t tq) {
 int16_t d=dotq14(t1->tx-t2->tx,t1->ty-t2->ty,-t2->ny,t2->nx);
 int32_t dvn,p,m;
 if(!d)return 1;
 dvn=riding_dotq32(dvx,dvy,-t2->ny,t2->nx,14);
 p=riding_mulshift32(dvn,t2->l,6);
 m=(int32_t)tq+KMUL32(p,C_OLD);
 return same_side(d,m);
}

static uint8_t faster_1ms( const circle_t* k ) {
	if( k->vx >= VEL_1MS || k->vx <= -VEL_1MS || k->vy >= VEL_1MS || k->vy <= -VEL_1MS )
		return 1;
	/* The early return proves |v|<VEL_1MS<32768 here. Narrowing only these
	 * small comparison operands is exact; stored/projected velocities stay32. */
	return mul16((int16_t)k->vx,(int16_t)k->vx)+mul16((int16_t)k->vy,(int16_t)k->vy) > (int32_t)VEL_1MS*VEL_1MS;
}

#if !defined(__SDCC) || defined(PHYSICS_WHEEL_C)
static void move( circle_t* k ) {
	k->alfa += phase_move(k->omega,7);
	k->rx += phase_advance(k->vx,2,k==&Bike.body?0:k==&Bike.wheel[0]?2:4);
	k->ry += phase_advance(k->vy,2,k==&Bike.body?1:k==&Bike.wheel[0]?3:5);
}
#endif

// beallit for a wheel: dv is the velocity change from the forces, tq the
// torque on it.
uint8_t riding_audio_contact[2], riding_audio_impact[2];
/* Resolved support for the next body damper impulse; ph_init resets it. */
int16_t riding_landing_nx[2], riding_landing_ny[2];
uint8_t riding_landing_contact[2];
#if defined(__SDCC) && !defined(PHYSICS_WHEEL_C) && !defined(PHYSICS_CONTACT_LOOP_C) && !defined(PHYSICS_SEGMENT_SCAN_C)
uint8_t riding_contact_filter(circle_t*,uint8_t);

/* The banked ABI passes k and the three int32 impulses contiguously.
 * The contact resolver reads these inputs when the fine filter accepts a
 * candidate. An empty query passes the same block to the free-wheel kernel. */
typedef struct {
    circle_t *k;
    int32_t dvx,dvy,tq;
} wheel_input_t;
typedef char wheel_input_layout[sizeof(wheel_input_t)==14 && offsetof(wheel_input_t,dvx)==2 &&
    offsetof(wheel_input_t,dvy)==6 && offsetof(wheel_input_t,tq)==10 &&
    offsetof(bike_t,wheel[1])==48?1:-1];
void riding_wheel_contact(const wheel_input_t *input,uint8_t n);

/* A 256u square fits within the 1m collision subcell. After five consecutive
 * queries to the same square, classify it from the ordered segment list.
 * Modes 0..4 are invalid, empty, interior, clipped interior and general.
 * Modes 8..5 count down to classification; fast-moving wheels normally use
 * the original query throughout. Entries own their geometry across eviction
 * of the three collision-reader slots. */
typedef struct {
    uint16_t x,y;
    uint8_t kind;
    int16_t base_x,base_y,nx,ny;
    uint8_t x0,x1,y0,y1;
} surface_cache_t;
surface_cache_t wheel_surface_cache[2];
void riding_surface_reset(void) __nonbanked {
    wheel_surface_cache[0].kind=wheel_surface_cache[1].kind=0;
}
/* ABI1 supplies by:bx in DE. Return NULL, the sole record, or address 1
 * for multiple records. Peek without modifying Seg_cur or Seg_left so the
 * fill query still executes the complete original iterator. */
static const seg_t *surface_candidate(uint16_t box) __naked {
    box;
    __asm
    ld b,d
    ld c,e
    ld a,(#_Seg_left)
    or a,a
    jr z,ws_no_candidate
    ld d,a
    ld e,#0
    ld hl,#_Seg_cur
    ld a,(hl+)
    ld h,(hl)
    ld l,a
ws_scan:
    ld a,l
    add #14
    ld l,a
    jr nc,ws_bbox
    inc h
ws_bbox:
    ld a,c
    add #3
    cp (hl)
    inc hl
    jr c,ws_reject1
    ld a,(hl+)
    cp c
    jr c,ws_reject2
    ld a,b
    add #3
    cp (hl)
    inc hl
    jr c,ws_reject3
    ld a,(hl+)
    cp b
    jr c,ws_next
    ld a,e
    or a,a
    jr nz,ws_multiple
    inc e
    push hl
    jr ws_next
ws_reject1:
    inc hl
ws_reject2:
    inc hl
ws_reject3:
    inc hl
ws_next:
    dec d
    jr nz,ws_scan
    ld a,e
    or a,a
    jr z,ws_no_candidate
    pop hl
    ld a,l
    sub #18
    ld c,a
    ld a,h
    sbc #0
    ld b,a
    ret
ws_multiple:
    pop hl
    ld bc,#1
    ret
ws_no_candidate:
    ld bc,#0
    ret
    __endasm;
}

static void wheel_classify(surface_cache_t *w,uint16_t qx,uint16_t qy){
    uint8_t bx=((qx>>6)&0xfc)+128,by=((qy>>6)&0xfc)+128;
    const seg_t *one=surface_candidate((uint16_t)by*256+bx);
    if(one==(const seg_t *)1){w->kind=4;return;}
    if(!one){w->kind=1;return;}
    int16_t x=(qx&0xf00)+128-one->px,y=(qy&0xf00)+128-one->py;
    int16_t t=dotq14(x,y,one->ex,one->ey);
    /* The center-to-corner change in either component is at most 128u.
     * Each Q14 direction component has magnitude <=16384, so the rounded
     * tangent projection can change by at most 256u. Strictly exclude the
     * far endpoint to preserve ownership of artificial subdivision joins. */
    if(t<256 || t>=(one->len&0x3fff)-256){w->kind=4;return;}
    w->base_x=(qx&0xf00)-one->px;
    w->base_y=(qy&0xf00)-one->py;
    w->nx=-one->ey;
    w->ny=one->ex;
    w->x0=one->x0<=bx ? 0 : (one->x0-bx)*64;
    w->x1=one->x1>=bx+3u ? 255 : (one->x1-bx)*64+63;
    w->y0=one->y0<=by ? 0 : (one->y0-by)*64;
    w->y1=one->y1>=by+3u ? 255 : (one->y1-by)*64+63;
    w->kind=one->x0<=bx && one->x1>=bx+3u && one->y0<=by && one->y1>=by+3u ? 2 : 3;
}
uint8_t riding_wheel_surface(circle_t *k) {
    const uint8_t *p=(const uint8_t *)k;
    uint16_t x=*(const uint16_t*)(p+2),y=*(const uint16_t*)(p+6);
    uint16_t qx=*(const uint16_t*)(p+1)&4095,qy=*(const uint16_t*)(p+5)&4095;
    surface_cache_t *w=&wheel_surface_cache[k==&Bike.wheel[1]];
    w->x=x;w->y=y;
    seg_query(x>=4096?255:(uint8_t)(x>>4),y>=4096?255:(uint8_t)(y>>4),
            (uint8_t)((qx>>10)|((qy>>8)&12)));
    wheel_classify(w,qx,qy);
    return riding_contacts_loop(qx,qy);
}
typedef char wheel_cache_layout[sizeof(surface_cache_t)==17 &&
    offsetof(surface_cache_t,kind)==4 && offsetof(surface_cache_t,base_x)==5 &&
    offsetof(surface_cache_t,nx)==9 && offsetof(surface_cache_t,x0)==13 ? 1 : -1];
/* ABI1 DE is the wheel. A=255 falls through to the existing full query.
 * An interior hit writes exactly the normal and length produced by the
 * original iterator. Filtering, pushout, landing and audio follow as usual. */
uint8_t riding_cert_hit(circle_t *k) __naked {
    k;
    __asm
    ld hl,#_wheel_surface_cache
    ld a,e
    cp #<(_Bike+48)
    jr nz,ws_slot
    ld hl,#(_wheel_surface_cache+17)
ws_slot:
    push de
    push hl
    inc de
    inc de
    ld a,(de)
    cp (hl)
    jr nz,ws_change
    inc de
    inc hl
    ld a,(de)
    cp (hl)
    jr nz,ws_change
    inc de
    inc de
    inc de
    inc hl
    ld a,(de)
    cp (hl)
    jr nz,ws_change
    inc de
    inc hl
    ld a,(de)
    cp (hl)
    jr nz,ws_change
    inc hl
    ld a,(hl)
    cp #1
    jr z,ws_empty
    cp #2
    jr z,ws_interior
    cp #3
    jr z,ws_interior
    cp #5
    jr z,ws_build
    jr c,ws_kind_low
    dec (hl)
    jr ws_fallback
ws_kind_low:
    or a,a
    jr z,ws_change
ws_fallback:
    pop hl
    pop de
    ld a,#255
    ret
ws_build:
    ld (hl),#0
    pop hl
    pop de
    jp _riding_wheel_surface
ws_change:
    pop hl
    pop de
    inc de
    inc de
    ld a,(de)
    ld (hl+),a
    inc de
    ld a,(de)
    ld (hl+),a
    inc de
    inc de
    inc de
    ld a,(de)
    ld (hl+),a
    inc de
    ld a,(de)
    ld (hl+),a
    ld (hl),#8
    ld a,#255
    ret
ws_empty:
    pop hl
    pop de
    xor a,a
    ret
ws_interior:
    pop de
    pop hl
    inc hl
    ld c,(hl)
    inc hl
    inc hl
    inc hl
    inc hl
    ld b,(hl)
    ; C,B are the within-square X,Y offsets. DE is the entry.
    cp #3
    jr nz,ws_compute
    ld hl,#13
    add hl,de
    ld a,c
    cp (hl)
    jp c,ws_no_contact
    inc hl
    ld a,(hl+)
    cp c
    jp c,ws_no_contact
    ld a,b
    cp (hl)
    jp c,ws_no_contact
    inc hl
    ld a,(hl)
    cp b
    jp c,ws_no_contact
ws_compute:
    ld hl,#5
    add hl,de
    ld a,c
    add a,(hl)
    inc hl
    ld e,a
    ld a,#0
    adc a,(hl)
    inc hl
    ld d,a
    ld a,b
    add a,(hl)
    inc hl
    ld c,a
    ld a,#0
    adc a,(hl)
    inc hl
    ld b,a
    ; HL points at the immutable normal. Save it across the rounded dot.
    push hl
    push bc
    ld a,(hl+)
    ld c,a
    ld a,(hl+)
    ld b,a
    ld a,(hl+)
    ld h,(hl)
    ld l,a
    push hl
    push bc
    ldhl sp,#4
    ld a,(hl+)
    ld c,a
    ld b,(hl)
    call _dotq14
    pop hl  ; discard saved point Y
    pop hl  ; normal at offset 9
    ; BC is d. Wheel radius is 410, inclusive max length 409.
    ld a,c
    add a,#0x99
    ld e,a
    ld a,b
    adc a,#1
    ld d,a
    ld a,e
    sub a,#0x33
    ld a,d
    sbc a,#3
    jr nc,ws_no_contact
    bit 7,b
    jr nz,ws_negative
    ld de,#_Ct
    ld a,(hl+)
    ld (de),a
    inc de
    ld a,(hl+)
    ld (de),a
    inc de
    ld a,(hl+)
    ld (de),a
    inc de
    ld a,(hl)
    ld (de),a
    inc de
    jr ws_length
ws_negative:
    ld de,#_Ct
    xor a,a
    sub (hl)
    ld (de),a
    inc de
    inc hl
    ld a,#0
    sbc (hl)
    ld (de),a
    inc de
    inc hl
    xor a,a
    sub (hl)
    ld (de),a
    inc de
    inc hl
    ld a,#0
    sbc (hl)
    ld (de),a
    inc de
    xor a,a
    sub c
    ld c,a
    ld a,#0
    sbc b
    ld b,a
ws_length:
    ld a,c
    ld (de),a
    inc de
    ld a,b
    ld (de),a
    ld a,#1
    ret
ws_no_contact:
    xor a,a
    ret
    __endasm;
}

void riding_wheel(circle_t *k,int32_t dvx,int32_t dvy,int32_t tq) PH_BANKED __naked {
    k;dvx;dvy;tq;
    __asm
    ldhl sp,#6
    ld a,(hl+)
    ld d,(hl)
    ld e,a
    call _riding_cert_hit
    cp #255
    jr nz,ws_have_answer
    ldhl sp,#6
    ld a,(hl+)
    ld h,(hl)
    ld l,a
    ; Form both signed F>>8 coordinates from their upper three bytes.
    ld de,#5
    add hl,de
    call wheel_query_position
    push de
    push bc
    ld de,#-6
    add hl,de
    call wheel_query_position
    call _contacts
ws_have_answer:
    or a,a
    jr z,wheel_no_contact
    ldhl sp,#6
    ld e,(hl)
    inc hl
    ld d,(hl)
    call _riding_contact_filter
    or a,a
    jr z,wheel_no_contact
    ldhl sp,#6
    ld d,h
    ld e,l
    jp _riding_wheel_contact
wheel_query_position:
    ld a,(hl+)
    ld c,a
    ld a,(hl+)
    ld b,a
    ld a,(hl)
    ld e,a
    add a,a
    sbc a,a
    ld d,a
    ret
wheel_no_contact:
    ; Clear every reported field, even on the first airborne substep.
    ldhl sp,#6
    ld a,(hl+)
    cp a,#<(_Bike+48)
    jr nz,wheel_air_left
    ld a,(hl)
    cp a,#>(_Bike+48)
    jr nz,wheel_air_left
    xor a,a
    ld (#_riding_audio_impact+1),a
    ld (#_riding_audio_contact+1),a
    ld (#_riding_landing_contact+1),a
    ld (#_riding_landing_nx+2),a
    ld (#_riding_landing_nx+3),a
    ld (#_riding_landing_ny+2),a
    ld (#_riding_landing_ny+3),a
    jr wheel_air_move
wheel_air_left:
    xor a,a
    ld (#_riding_audio_impact),a
    ld (#_riding_audio_contact),a
    ld (#_riding_landing_contact),a
    ld (#_riding_landing_nx),a
    ld (#_riding_landing_nx+1),a
    ld (#_riding_landing_ny),a
    ld (#_riding_landing_ny+1),a
wheel_air_move:
    ldhl sp,#6
    jp _riding_free_inputs
    __endasm;
}

void riding_wheel_contact(const wheel_input_t *input,uint8_t n) {
    circle_t *k=input->k;
    int32_t dvx=input->dvx,dvy=input->dvy,tq=input->tq;
#else
void riding_wheel( circle_t* k, int32_t dvx, int32_t dvy, int32_t tq ) PH_BANKED {
    uint8_t n = contacts( riding_sra8(k->rx), riding_sra8(k->ry) );
    uint8_t valid=0;
    for(uint8_t j=0;j<n;++j) {
        int32_t distance=(int32_t)Ct[j].l*256+riding_dotq32(k->rx&255,k->ry&255,Ct[j].nx,Ct[j].ny,14);
        if(distance<104858)Ct[valid++]=Ct[j];
    }
    n=valid;
#endif
    uint8_t two = n == 2;
	uint8_t wheel = k==&Bike.wheel[1];
	if( n > 0 )
		pushout( k, &Ct[0], two ? &Ct[1] : 0 );
	if( two ) {
		pushout( k, &Ct[1], 0 );
		if( faster_1ms( k ) ) {
			if( !sure_new( &Ct[0], &Ct[1], k ) ) {
				n = 1;
				Ct[0] = Ct[1];
			}
			else if( !sure_new( &Ct[1], &Ct[0], k ) )
				n = 1;
		}
		else {
			if( !sure_old( &Ct[0], &Ct[1], dvx, dvy, tq ) ) {
				n = 1;
				Ct[0] = Ct[1];
			}
			else if( !sure_old( &Ct[1], &Ct[0], dvx, dvy, tq ) )
				n = 1;
		}
		if( n == 2 && !supports( k, &Ct[1], dvx, dvy, 1 ) )
			n = 1;
	}
	if( n >= 1 && !supports( k, &Ct[0], dvx, dvy, two ) ) {
		if( n == 2 ) {
			n = 1;
			Ct[0] = Ct[1];
		}
		else
			n = 0;
	}
    /* Audio observes a new supported collision before its response changes
     * velocity. Tangential speed and suspension travel do not imply impact.
     * This event does not alter native bike state or collision decisions. */
    riding_audio_impact[wheel]=0;
    if(n && !riding_audio_contact[wheel]) {
        if(riding_dotq32(k->vx,k->vy,Ct[0].nx,Ct[0].ny,14)<-(int32_t)(2.0*PH_VS)
           || (n==2 && riding_dotq32(k->vx,k->vy,Ct[1].nx,Ct[1].ny,14)<-(int32_t)(2.0*PH_VS)))
            riding_audio_impact[wheel]=1;
    }
    riding_audio_contact[wheel]=n;
    riding_landing_contact[wheel]=n;
    riding_landing_nx[wheel]=n?Ct[0].nx:0;
    riding_landing_ny[wheel]=n?Ct[0].ny:0;
	if( n == 0 ) {
#if defined(__SDCC) && !defined(PHYSICS_WHEEL_C)
        riding_free32(k,dvx,dvy,tq);
#else
		k->omega += KMUL32(tq,C_FREE);
		k->vx += dvx;
		k->vy += dvy;
		move( k );
#endif
		return;
	}
	if( n == 2 ) {
		k->vx = k->vy = 0;
		k->omega = 0;
		return;
	}
#if defined(__SDCC) && !defined(PHYSICS_WHEEL_C)
    riding_roll32(k,&Ct[0],dvx,dvy,tq);
#else
	// Rolls around the contact point:
	int16_t n90x = -Ct[0].ny, n90y = Ct[0].nx;
	int32_t vn = riding_dotq32(k->vx,k->vy,n90x,n90y,14);
	int32_t dvn = riding_dotq32(dvx,dvy,n90x,n90y,14);
	int32_t t = (int32_t)tq+KMUL32(dvn,C_ROLL_T);
    /* Integrate linear rolling speed before quantizing angular state. */
	int32_t sp = vn+Q24_MUL(t,C_ROLL_DV);
 k->omega=Q24_MUL(sp,C_ROLL_W);
	k->vx = riding_mulq32(sp,n90x,14);
	k->vy = riding_mulq32(sp,n90y,14);
	move( k );
#endif
}
