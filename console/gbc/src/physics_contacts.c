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
#ifdef RIDING_NORMAL_ATLAS
uint8_t riding_normal_merge_ring(int16_t x,int16_t y);
#if MERGE == 102
uint8_t riding_merge_close(int16_t x,int16_t y);
#endif
#endif
#ifdef RIDING_NORMAL_ATLAS
uint8_t riding_contact_point_lookup(contact_t *c);
uint8_t riding_ring_equal_points(void);
#if MERGE != 102
static void merge_point(contact_t *c,int16_t qx,int16_t qy) {
    if (!riding_contact_point_lookup(c)) contact_point(c,qx,qy);
}
#endif
#else
#define merge_point contact_point
#endif
#if defined(RIDING_NORMAL_ATLAS) && MERGE == 102
static void merge_normal_slow(int16_t x,int16_t y) {
    normalize(x,y,mul16(x,x)+mul16(y,y),&Ct[0]);
}

uint8_t riding_contact_merge(void) __naked {
    __asm
    ld b,#0
_riding_contact_merge_kind::
    ; B is one only when the iterator just copied the physical atlas
    ; normal into Ct[1]. The six-byte equality check also proves Ct[0].
    ld hl,#_Ct
    ld de,#(_Ct+10)
    .rept 6
    ld a,(de)
    cp (hl)
    jr nz,merge_different
    inc hl
    inc de
    .endm
    ; Equal projected points still require normalization after Q14 rounding.
    dec b
    jr nz,merge_equal_unverified
    call _riding_ring_equal_known
    jr merge_equal_result
merge_equal_unverified:
    call _riding_ring_equal_points
merge_equal_result:
    or a
    jp nz,merge_complete
    ld de,#_Ct
    call merge_project
    ld hl,#(_Ct+6)
    ld de,#(_Ct+16)
    .rept 4
    ld a,(hl+)
    ld (de),a
    inc de
    .endm
    ld de,#0
    ld b,d
    ld c,e
    jr merge_average
merge_different:
    ld de,#(_Ct+10)
    dec b
    jr nz,merge_second
    call _riding_ring_point_known
    or a
    jr nz,merge_first
    ld de,#(_Ct+10)
merge_second:
    call merge_project
merge_first:
    ld de,#_Ct
    call merge_project
    ld hl,#(_Ct+6)
    ld a,(#_Ct+16)
    sub (hl)
    inc hl
    ld e,a
    ld a,(#_Ct+17)
    sbc (hl)
    inc hl
    ld d,a
    ld a,(#_Ct+18)
    sub (hl)
    inc hl
    ld c,a
    ld a,(#_Ct+19)
    sbc (hl)
    ld b,a
    push de
    push bc
    call _riding_merge_close
    pop bc
    pop de
    or a
    ld a,#2
    ret z
    ; Signed half-differences round toward negative infinity.
    sra d
    rr e
    sra b
    rr c
merge_average:
    ; Subtract the midpoint in the same 16-bit coordinate domain as the solver.
    ld hl,#(_Ct+6)
    ld a,(hl+)
    add e
    ld e,a
    ld a,(hl+)
    adc d
    ld d,a
    ld a,(hl+)
    add c
    ld c,a
    ld a,(hl)
    adc b
    ld b,a
    ld a,(#_riding_contact_qx)
    sub e
    ld e,a
    ld a,(#_riding_contact_qx+1)
    sbc d
    ld d,a
    ld a,(#_riding_contact_qy)
    sub c
    ld c,a
    ld a,(#_riding_contact_qy+1)
    sbc b
    ld b,a
    push de
    push bc
    call _riding_normal_merge_ring
    pop bc
    pop de
    or a
    jp nz,merge_complete
    call _merge_normal_slow
merge_complete:
    xor a
    ret
merge_project:
    push de
    call _riding_contact_point_lookup
    pop de
    or a
    ret nz
    ; Project both normal components with the same signed length.
    ld hl,#4
    add hl,de
    ld a,(hl+)
    ld c,a
    ld b,(hl)
    push bc
    ld h,d
    ld l,e
    ld a,(hl+)
    ld e,a
    ld a,(hl+)
    ld d,a
    push hl
    call _mulq14
    pop hl
    ld d,b
    ld e,c
    pop bc
    push de
    ld a,(hl+)
    ld e,a
    ld a,(hl+)
    ld d,a
    inc hl
    inc hl
    push hl
    call _mulq14
    pop hl
    pop de
    ld a,(#_riding_contact_qx)
    sub e
    ld (hl+),a
    ld a,(#_riding_contact_qx+1)
    sbc d
    ld (hl+),a
    ld a,(#_riding_contact_qy)
    sub c
    ld (hl+),a
    ld a,(#_riding_contact_qy+1)
    sbc b
    ld (hl),a
    ret
    __endasm;
}
#else
#ifdef RIDING_NORMAL_ATLAS
/* Alternate merge radii retain the ordinary point and distance solver. */
uint8_t riding_contact_merge_kind(void) __naked {
    __asm
    jp _riding_contact_merge
    __endasm;
}
#endif
uint8_t riding_contact_merge(void) {
 int16_t qx=riding_contact_qx,qy=riding_contact_qy;
 /* Equal normals and lengths project to the same point. Keep the final
  * normalization: rounding does not make that operation idempotent. */
 if(Ct[0].nx==Ct[1].nx && Ct[0].ny==Ct[1].ny && Ct[0].l==Ct[1].l) {
#ifdef RIDING_NORMAL_ATLAS
  if(riding_ring_equal_points()) return 0;
#endif
  merge_point(&Ct[0],qx,qy);
  int16_t ax=qx-Ct[0].tx, ay=qy-Ct[0].ty;
  Ct[1].tx=Ct[0].tx;Ct[1].ty=Ct[0].ty;
#ifdef RIDING_NORMAL_ATLAS
  if (riding_normal_merge_ring(ax,ay)) return 0;
#endif
  normalize(ax,ay,mul16(ax,ax)+mul16(ay,ay),&Ct[0]);
  return 0;
 }
	merge_point( &Ct[0], qx, qy );
	merge_point( &Ct[1], qx, qy );
	int16_t dx = Ct[1].tx-Ct[0].tx, dy = Ct[1].ty-Ct[0].ty;
#if defined(RIDING_NORMAL_ATLAS) && MERGE == 102
    if (riding_merge_close(dx,dy)) {
#else
	if( dx < MERGE && dx > -MERGE && dy < MERGE && dy > -MERGE &&
		mul16( dx, dx )+mul16( dy, dy ) < (int32_t)MERGE*MERGE ) {
#endif
		// Merged into their average:
		int16_t ax = qx-Ct[0].tx-(dx >> 1);
		int16_t ay = qy-Ct[0].ty-(dy >> 1);
#ifdef RIDING_NORMAL_ATLAS
  if (riding_normal_merge_ring(ax,ay)) return 0;
#endif
		normalize( ax, ay, mul16( ax, ax )+mul16( ay, ay ), &Ct[0] );
	}
	else
		return 2;
 return 0;
}
#endif
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
#define FINE_PUSH_TARGET 103547L
#define FINE_CONTACT_RADIUS 104858L
#define FINE_REJECT_PUSH (FINE_PUSH_TARGET - FINE_CONTACT_RADIUS)

static void apply_push(circle_t *k, contact_t *c, contact_t *other, int32_t push) {
    int32_t px = riding_mulq32(push, c->nx, 14), py = riding_mulq32(push, c->ny, 14);
    k->rx += px;
    k->ry += py;
    c->l += (push + 128) >> 8;
    if (other)
        other->l += (riding_dotq32(px, py, other->nx, other->ny, 14) + 128) >> 8;
}

#if defined(__SDCC) && !defined(PHYSICS_WHEEL_C) && !defined(PHYSICS_CONTACT_LOOP_C) && !defined(PHYSICS_SEGMENT_SCAN_C)
#define NATIVE_FINE_CONTACTS
#if RIDING_PC_SCHEDULE && !defined(RIDING_COEFFICIENT_LOOKUP)
#define NATIVE_ORDERED_PAIR
#endif
/* The native kernel uses 103547-distance. It may return zero for an
 * accepted contact proven to need no push. */
typedef char fine_contact_constants[FINE_PUSH_TARGET==103547L && FINE_REJECT_PUSH==-1311L ? 1 : -1];
int32_t riding_contact_push(circle_t *, const contact_t *);

static void remember_prepared_pair(circle_t *k);
#ifdef NATIVE_ORDERED_PAIR
/* 0 = unknown, 1 = rounded zero, 2 = positive, 128 = negative.
 * Each row belongs to one ordered pair at its exact cached center. */
static uint8_t pair_separation[2][2];
#endif

/* One or two coarse candidates arrive in record order. Filter both against
 * the original center. The first push changes both the center fractions and
 * the other contact's length, so recompute its push only in that case. */
uint8_t riding_prepare_contacts(circle_t *k, uint8_t n) __naked {
    k;n;
    __asm
    ; The filter returns A=0 reject, 1 accepted and clear, 2 positive push.
    ; DE:BC always carries the exact positive push. Keep the sole candidate
    ; in registers from the filter through the common single-contact return.
    push de
    cp #2
    jr z,prepare_pair
    ld bc,#_Ct
    call _riding_contact_push
prepare_single:
    cp #2
    jr z,prepare_single_push
    pop de
    ret
prepare_single_push:
    ld a,d
    or e
    or b
    jr nz,prepare_single_wide
    ld a,c
    ld bc,#_Ct
    pop de
    call _riding_push_byte
    ld a,#1
    ret
prepare_single_wide:
    push de
    push bc
    ld hl,#0
    push hl
    ld bc,#_Ct
    call prepare_apply
    pop de
    ld a,#1
    ret
prepare_pair:
    ld bc,#_Ct
    call _riding_contact_push
    push de
    push bc
    push af
    ldhl sp,#6
    ld a,(hl+)
    ld d,(hl)
    ld e,a
    ld bc,#(_Ct+10)
    call _riding_contact_push
    ld h,a
    pop af
    ld l,a
    ld a,h
    or a
    jr z,prepare_first_only
    ld a,l
    or a
    jr z,prepare_second_only
    cp #2
    jr z,prepare_first_push
    add sp,#4
    ld a,h
    cp #2
    jr z,prepare_second_push
    pop de
    call _remember_prepared_pair
    ld a,#2
    ret
prepare_first_push:
    ; The first push is already on the stack as the last argument.
    ld hl,#(_Ct+10)
    push hl
    ld bc,#_Ct
    call prepare_apply
    ; Recompute the second push at the moved center and updated length.
    ; The acceptance of both contacts was already decided before moving.
    pop de
    push de
    ld bc,#(_Ct+10)
    call _riding_contact_push
    cp #2
    jr nz,prepare_two
prepare_second_push:
    ld a,d
    or e
    or b
    jr nz,prepare_second_wide
    ld a,c
    ld bc,#(_Ct+10)
    pop de
    call _riding_push_byte
    ld a,#2
    ret
prepare_second_wide:
    push de
    push bc
    ld hl,#0
    push hl
    ld bc,#(_Ct+10)
    call prepare_apply
prepare_two:
    pop de
    ld a,#2
    ret
prepare_first_only:
    ld a,l
    pop bc
    pop de
    jp prepare_single
prepare_second_only:
    add sp,#4
    push de
    push bc
    push hl
    ld hl,#(_Ct+10)
    ld de,#_Ct
    ld b,#10
prepare_copy:
    ld a,(hl+)
    ld (de),a
    inc de
    dec b
    jr nz,prepare_copy
    pop hl
    pop bc
    pop de
    ld a,h
    jp prepare_single
prepare_apply:
    ; _apply_push takes DE=wheel, BC=contact, then other and push on
    ; the stack. Tail-call so it removes those six argument bytes.
    ldhl sp,#8
    ld a,(hl+)
    ld d,(hl)
    ld e,a
    jp _apply_push
    __endasm;
}
#else
static void pushout(circle_t *k, contact_t *c, contact_t *other) {
    int32_t fine_l = (int32_t)c->l * 256 + riding_dotq32(k->rx & 255, k->ry & 255,
                                                          c->nx, c->ny, 14);
    int32_t push = FINE_PUSH_TARGET - fine_l;
    if (push > 0)
        apply_push(k, c, other, push);
}
#endif

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


#ifndef NATIVE_ORDERED_PAIR
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

#endif

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

/* The banked ABI passes k and the three int32 impulses contiguously.
 * The contact resolver reads these inputs when the fine filter accepts a
 * candidate. An empty query passes the same block to the free-wheel kernel. */
typedef char wheel_input_layout[sizeof(wheel_input_t)==14 && offsetof(wheel_input_t,dvx)==2 &&
    offsetof(wheel_input_t,dvy)==6 && offsetof(wheel_input_t,tq)==10 &&
    offsetof(bike_t,wheel[1])==48?1:-1];
void riding_wheel_contact(const wheel_input_t *input,uint8_t n);

/* A 256u square fits within the 1m collision subcell. After five consecutive
 * queries to the same square, classify it from the ordered segment list.
 * Modes 0..4 are invalid, empty, interior, clipped interior and general.
 * Modes 8..5 count down to classification; fast-moving wheels normally use
 * the original query throughout. Entries own their geometry across eviction
 * of the three collision-reader slots. Mode 9 holds a prepared pair at one
 * exact center in a square already known to have multiple candidates.
 * Kinds 10/11 retain the exact affine intercept. A signed unit Y plane
 * with a small X component also holds its two exact X crossings.
 * Kinds 64..254 identify contiguous windows in the original ordered leaf. */
typedef struct {
    uint16_t x,y;
    uint8_t kind;
    union {
        struct {
            int16_t base_x,base_y,nx,ny;
            uint8_t x0,x1,y0,y1;
            int32_t intercept;
        } plane;
        struct {
            uint16_t low_x,low_y;
            contact_t contacts[2];
        } pair;
    };
} surface_cache_t;
surface_cache_t wheel_surface_cache[2];
/* The square key contains the upper half of each position. Keep the lower
 * halves and both complete records before the motion resolver can edit Ct. */
static void remember_prepared_pair(circle_t *k) {
    surface_cache_t *w=&wheel_surface_cache[k==&Bike.wheel[1]];
#ifdef NATIVE_ORDERED_PAIR
    uint8_t *signs=pair_separation[k==&Bike.wheel[1]];
    signs[0]=signs[1]=0;
#endif
    w->kind=9;
    w->pair.low_x=(uint16_t)k->rx;
    w->pair.low_y=(uint16_t)k->ry;
    w->pair.contacts[0]=Ct[0];
    w->pair.contacts[1]=Ct[1];
}
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
    w->plane.base_x=(qx&0xf00)-one->px;
    w->plane.base_y=(qy&0xf00)-one->py;
    w->plane.nx=-one->ey;
    w->plane.ny=one->ex;
    w->plane.x0=one->x0<=bx ? 0 : (one->x0-bx)*64;
    w->plane.x1=one->x1>=bx+3u ? 255 : (one->x1-bx)*64+63;
    w->plane.y0=one->y0<=by ? 0 : (one->y0-by)*64;
    w->plane.y1=one->y1>=by+3u ? 255 : (one->y1-by)*64+63;
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
typedef char wheel_cache_layout[sizeof(surface_cache_t)==29 &&
    offsetof(surface_cache_t,kind)==4 && offsetof(surface_cache_t,plane.base_x)==5 &&
    offsetof(surface_cache_t,plane.nx)==9 && offsetof(surface_cache_t,plane.x0)==13 &&
    offsetof(surface_cache_t,plane.intercept)==17 &&
    offsetof(surface_cache_t,pair.low_x)==5 && offsetof(surface_cache_t,pair.low_y)==7 &&
    offsetof(surface_cache_t,pair.contacts)==9 ? 1 : -1];
/* ABI1 DE is the wheel. A=255 falls through to the existing full query.
 * A=254 restores an already filtered, ordered pair. An interior hit writes
 * the iterator's normal and length for the ordinary filter and pushout. */
uint8_t riding_cert_hit(circle_t *k) __naked {
    k;
    __asm
    ld hl,#_wheel_surface_cache
    ld a,e
    cp #<(_Bike+48)
    jr nz,ws_slot
    ld hl,#(_wheel_surface_cache+29)
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
#ifdef RIDING_WHEEL_TERRAIN
    ld b,a
    and #0xf6
    cp #2
    ld a,b
    jr z,ws_interior
#else
    cp #2
    jr z,ws_interior
    cp #3
    jr z,ws_interior
#endif
    cp #5
    jr z,ws_build
    jr c,ws_kind_low
    cp #9
    jr z,ws_pair
#ifdef RIDING_WHEEL_TERRAIN
    cp #64
    jp nc,_riding_wheel_cached_window
#endif
    dec (hl)
    jr ws_fallback
ws_kind_low:
#ifdef RIDING_WHEEL_TERRAIN
    ; The dynamic classifier marked this square ambiguous. Keep its full
    ; ordered span under the same FIFO lifetime as a compiled window.
    cp #4
    jp z,_riding_wheel_full_window
#endif
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
#ifdef RIDING_WHEEL_TERRAIN
    push hl
    push de
#endif
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
#ifdef RIDING_WHEEL_TERRAIN
    pop de
    pop bc
    jp _riding_compiled_surface
#else
    ld a,#255
    ret
#endif
ws_pair:
    ; The upper halves already matched. Compare every remaining center byte.
    pop bc
    pop de
    push hl   ; kind, reset to general on a miss within this square
    inc hl
    ld a,(de)
    cp (hl)
    jr nz,ws_pair_miss
    inc de
    inc hl
    ld a,(de)
    cp (hl)
    jr nz,ws_pair_miss
    inc de
    inc de
    inc de
    inc hl
    ld a,(de)
    cp (hl)
    jr nz,ws_pair_miss
    inc de
    inc hl
    ld a,(de)
    cp (hl)
    jr nz,ws_pair_miss
    inc hl
    pop bc
    ld de,#_Ct
    ld b,#20
ws_pair_copy:
    ld a,(hl+)
    ld (de),a
    inc de
    dec b
    jr nz,ws_pair_copy
    ld a,#254
    ret
ws_pair_miss:
    pop hl
    ld (hl),#4
    ld a,#255
    ret
ws_empty:
    pop hl
    pop de
    xor a,a
    ret
ws_interior:
#ifdef RIDING_WHEEL_TERRAIN
_riding_wheel_cached_plane::
#endif
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
    bit 0,a
    jr z,ws_compute
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
#ifdef RIDING_WHEEL_TERRAIN
    ld hl,#4
    add hl,de
    bit 3,(hl)
    jp nz,_riding_plane_affine
    push bc
    push de
#endif
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
    ; The Q14 dot is the signed coordinate on exact unit axes.
    push hl
    ld a,(hl+)
    or a
    jr nz,ws_full_dot
    ld a,(hl+)
    or a
    jr z,ws_plane_y
    cp #0x40
    jr z,ws_plane_x
    cp #0xc0
    jr nz,ws_full_dot
ws_plane_x:
    ld a,(hl+)
    or (hl)
    jr nz,ws_full_dot
    dec hl
    dec hl
    ld c,e
    ld b,d
    bit 7,(hl)
    jr z,ws_plane_distance
    jr ws_plane_neg
ws_plane_y:
    ld a,(hl+)
    or a
    jr nz,ws_full_dot
    ld a,(hl)
    cp #0x40
    jr z,ws_plane_distance
    cp #0xc0
    jr nz,ws_full_dot
ws_plane_neg:
    ; Both signed extremes are rejected by the radius test below.
    xor a
    sub c
    ld c,a
    sbc a,a
    sub b
    ld b,a
    jr ws_plane_distance
ws_full_dot:
    pop hl
#ifdef RIDING_WHEEL_TERRAIN
    push hl
    ; Every within-square coordinate is at most 255u away from this
    ; one. Exclude signed16 wrap anywhere in either relative coordinate.
    ld a,d
    add #129
    cp #2
    jr c,ws_original_dot
    ld a,b
    add #129
    cp #2
    jr c,ws_original_dot
    pop hl
    pop de
    pop bc
    jp _riding_plane_fill
ws_original_dot:
    pop hl
#endif
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
#ifdef RIDING_WHEEL_TERRAIN
    call _riding_terrain_dotq14
#else
    call _dotq14
#endif
    pop hl  ; discard saved point Y
ws_plane_distance:
    pop hl  ; normal at offset 9
#ifdef RIDING_WHEEL_TERRAIN
    add sp,#4
_riding_plane_distance::
#endif
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
#ifdef RIDING_WHEEL_TERRAIN
_riding_plane_positive::
#endif
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
#ifdef RIDING_WHEEL_TERRAIN
_riding_plane_negative::
#endif
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
_riding_wheel_inputs::
    ; Preserve the record and the wheel across queries, pushes and dot products.
    push hl
    ld a,(hl+)
    ld d,(hl)
    ld e,a
    push de
    call _riding_cert_hit
    cp #254
    jr c,ws_have_answer
    jr z,wheel_prepared_pair
    pop hl
    push hl
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
    jp z,wheel_no_contact
    pop de
    push de
    call _riding_prepare_contacts
    or a,a
    jp z,wheel_no_contact
wheel_resolve:
    cp #1
    jp z,wheel_single
wheel_pair_inputs:
    pop de  ; discard the wheel, pass its input record in DE
    pop de
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
wheel_prepared_pair:
#ifdef NATIVE_ORDERED_PAIR
    ; 254 carries the exact prepared-geometry proof to the ordered resolver.
    jr wheel_pair_inputs
#else
    ld a,#2
    jr wheel_resolve
#endif

wheel_single:
    ; Keep the wheel in DE and the input record on the stack throughout the
    ; common case. The xor sign tests also accept an exact zero coefficient.
    pop de
    pop hl
    push hl
    ld bc,#5
    add hl,bc
    ld a,(#_Ct+1)
    ld b,a
    xor (hl)
    rlca
    jr c,wheel_single_y
    ld a,(#_Ct)
    or b
    jr nz,wheel_single_test_impulse
wheel_single_y:
    ld bc,#4
    add hl,bc
    ld a,(#_Ct+3)
    ld b,a
    xor (hl)
    rlca
    jr c,wheel_single_accepted
    ld a,(#_Ct+2)
    or b
    jr z,wheel_single_accepted
wheel_single_test_impulse:
    pop hl
    push hl
    push de
    inc hl
    inc hl
    ld d,h
    ld e,l
    call _riding_single_impulse_outward
    pop de
    jr z,wheel_single_accepted
    ; Outward impulse: accept exactly when normal velocity <= -ELSZ.
    push de
    call wheel_normal_velocity
    bit 7,h
    jp z,wheel_no_contact
    ld a,h
    and l
    and d
    inc a
    jr nz,wheel_single_known_velocity
    ld a,(#_riding_supports_threshold)
    or a
    jr z,wheel_single_known_velocity
    cp e
    jp c,wheel_no_contact
    jp z,wheel_no_contact
wheel_single_known_velocity:
    ; This velocity already passed the support test. Its impact bit can
    ; serve a first contact before rolling changes the wheel velocity.
    call wheel_single_impact_value
    pop de
    ld h,a
    jr wheel_single_record
wheel_single_accepted:
    ld h,#2                     ; first contact must sample velocity
wheel_single_record:
    ld a,e
    ld bc,#0
    cp #<(_Bike+48)
    jr nz,wheel_single_slot
    ld a,d
    cp #>(_Bike+48)
    jr nz,wheel_single_slot
    inc c
wheel_single_slot:
    push bc
    ld a,h
    ld hl,#_riding_audio_contact
    add hl,bc
    ld b,a
    ld a,(hl)
    ld (hl),#1
    or a
    jr nz,wheel_single_quiet
    ld a,b
    cp #2
    jr c,wheel_single_impact
    call wheel_normal_velocity
    call wheel_single_impact_value
    jr wheel_single_impact
wheel_single_quiet:
    xor a
wheel_single_impact:
    pop bc
    ld hl,#_riding_audio_impact
    add hl,bc
    ld (hl),a
    ld hl,#_riding_landing_contact
    add hl,bc
    ld (hl),#1
    sla c
    ld hl,#_riding_landing_nx
    add hl,bc
    ld a,(#_Ct)
    ld (hl+),a
    ld a,(#_Ct+1)
    ld (hl),a
    ld hl,#_riding_landing_ny
    add hl,bc
    ld a,(#_Ct+2)
    ld (hl+),a
    ld a,(#_Ct+3)
    ld (hl),a
    pop hl
    ld bc,#_Ct
    jp _riding_roll_inputs
wheel_single_impact_value:
    bit 7,h
    jr nz,wheel_single_impact_negative
    xor a
    ret
wheel_single_impact_negative:
    ld a,h
    and l
    inc a
    ld a,#1
    ret nz
    ld hl,#_riding_impact_low
    ld a,e
    sub (hl)
    inc hl
    ld a,d
    sbc (hl)
    rla
    and #1
    ret
wheel_normal_velocity:
    ld hl,#8
    add hl,de
    ld d,h
    ld e,l
    ld hl,#_Ct
    jp _riding_dotq14_regs
wheel_no_contact:
    ; Clear every reported field, even on the first airborne substep.
    pop de
    pop hl
    ld a,e
    cp a,#<(_Bike+48)
    jr nz,wheel_air_left
    ld a,d
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
    jp _riding_free_inputs

; DE points to two signed 32-bit impulses. Z means the single rounded Q14
; projection is <= 0 (raw sum <8192). Ct supplies the fallback coefficients.
_riding_single_impulse_outward::
    ld a,(#_Ct+3)
    sub #33
    cp #95
    jr nc,wheel_impulse_exact  ; ny outside [8448,32767]
    ld a,(#_Ct+1)
    add #64
    cp #128
    jr nc,wheel_impulse_exact  ; nx outside [-16384,16383]
    sub #32
    push af
    ld hl,#3
    add hl,de
    ld a,(hl-)
    ld c,a
    inc a
    cp #2
    jr nc,wheel_impulse_wide_x
    ld a,(hl-)
    xor c
    jr nz,wheel_impulse_wide_x
    ; U(v) is v for v>=0, ~v for v<0, so U<=abs(v)<=U+1.
    ; X=floor(U(dx)/256) fits a byte after both upper bytes agree.
    ld a,(hl)
    xor c
    ld b,a
    pop af
    cp #64
    jr c,wheel_impulse_narrow_x
    ; For |nx| up to 16384, Y>2*X+1 proves abs(dy)>=2*abs(dx).
    ; The positive ny>=8448 leaves a strict margin above the rounding tie.
    sla b
    jr c,wheel_impulse_exact
    inc b
    jr wheel_impulse_y_bound
wheel_impulse_narrow_x:
    sub #16
    cp #32
    jr nc,wheel_impulse_y_bound
    srl b                      ; |nx|<=4096, so twice the Y bin suffices
    sub #12
    cp #8
    jr nc,wheel_impulse_y_bound
    srl b
    srl b
wheel_impulse_y_bound:
    ld hl,#7
    add hl,de
    ld a,(hl-)
    ld c,a
    inc a
    cp #2
    jr nc,wheel_impulse_y_dominates
    ld a,(hl-)
    xor c
    jr nz,wheel_impulse_y_dominates
    ld a,(hl)
    xor c
    cp b
    jr c,wheel_impulse_exact
    jr z,wheel_impulse_exact
wheel_impulse_y_dominates:
    ; In the broad nx band Y>X proves abs(dy)>=abs(dx), with Y>=1.
    ; In the narrow band Y>floor(X/8) proves 8*abs(dy)>=abs(dx).
    ; Both give abs(dy*ny)-abs(dx*nx)>=256*256, above the half-Q14
    ; rounding threshold. This proof also covers a wider y against byte X.
    ld a,c
    cpl
    and #128                   ; Z when the dominant y is negative
    ret
wheel_impulse_wide_x:
    pop af
wheel_impulse_exact:
    ld hl,#_Ct
    call _riding_dotq14_regs
    bit 7,h
    jr nz,wheel_impulse_inward
    ld a,h
    or l
    or d
    or e
    ret
wheel_impulse_inward:
    xor a
    ret
    __endasm;
}

#ifdef NATIVE_ORDERED_PAIR
/* Like Ct, this state is private to the active serial wheel query. The two
 * support tests reread the wheel velocity after the previous removal. */
int32_t *riding_pair_velocity;
const int32_t *riding_pair_impulse;
const int32_t *riding_pair_vector, *riding_pair_moment;
uint8_t riding_pair_shift, riding_pair_coefficient, riding_pair_stopped;
uint8_t riding_pair_moment_side;
uint8_t riding_pair_fast_side(const int32_t *velocity);
uint8_t riding_pair_sure(const contact_t *pivot,uint8_t *separation);
uint8_t riding_pair_supports(const contact_t *contact);

#ifdef RIDING_STOPPED_PAIR
uint8_t riding_stopped_pair_proof(void) __banked;
#endif

static uint8_t resolve_ordered_pair(const wheel_input_t *input,uint8_t *signs) {
    circle_t *k=input->k;
    riding_pair_velocity=&k->vx;
    riding_pair_impulse=&input->dvx;
    riding_pair_moment_side=0;
    riding_pair_stopped=!(k->vx || k->vy);
    if(!riding_pair_stopped && faster_1ms(k)) {
        riding_pair_vector=riding_pair_velocity;
        riding_pair_moment=&k->omega;
        riding_pair_shift=10;
#ifdef RIDING_STOPPED_PAIR
        riding_pair_moment_side=riding_pair_fast_side(riding_pair_velocity);
#endif
        riding_pair_coefficient=q24_index_C_NEW[riding_subphase];
    } else {
        riding_pair_vector=riding_pair_impulse;
        riding_pair_moment=&input->tq;
        riding_pair_shift=6;
        riding_pair_coefficient=q24_index_C_OLD[riding_subphase];
    }
#ifdef RIDING_STOPPED_PAIR
    if(riding_pair_stopped && (signs[0] == 2 || signs[0] == 128)) {
        uint8_t proof = riding_stopped_pair_proof();
        if(proof && proof != signs[0]) {
            /* The first pivot rejected. Its proven support becomes Ct[0].
             * Rolling publishes the final fraction after this decision. */
            Ct[0]=Ct[1];
            return 1;
        }
        if(proof && (signs[1] == 2 || signs[1] == 128)) {
            /* Both supports are inward at rest and remove exactly zero.
             * The second pivot still publishes its complete Q24 result. */
            return 1+riding_pair_sure(&Ct[0],signs+1);
        }
    }
#endif
    if(!riding_pair_sure(&Ct[1],signs)) {
        Ct[0]=Ct[1];
    } else if(riding_pair_sure(&Ct[0],signs+1) && riding_pair_supports(&Ct[1])) {
        if(riding_pair_supports(&Ct[0])) return 2;
        Ct[0]=Ct[1];
        return 1;
    }
    return riding_pair_supports(&Ct[0]);
}

/* SDCC passes input in DE. Keep the record in place after resolving a pair,
 * including when only one or neither of its contacts supports the wheel. */
static void wheel_free_record(const wheel_input_t *input) __naked {
    input;
    __asm
    ld h,d
    ld l,e
    jp _riding_free_inputs
    __endasm;
}
static void wheel_roll_record(const wheel_input_t *input) __naked {
    input;
    __asm
    ld h,d
    ld l,e
    ld bc,#_Ct
    jp _riding_roll_inputs
    __endasm;
}
#endif

void riding_wheel_contact(const wheel_input_t *input,uint8_t n) {
    circle_t *k=input->k;
#ifndef NATIVE_ORDERED_PAIR
    int32_t dvx=input->dvx,dvy=input->dvy,tq=input->tq;
#endif
#else
void riding_wheel( circle_t* k, int32_t dvx, int32_t dvy, int32_t tq ) PH_BANKED {
    uint8_t n = contacts( riding_sra8(k->rx), riding_sra8(k->ry) );
    uint8_t valid=0;
    for(uint8_t j=0;j<n;++j) {
        int32_t distance=(int32_t)Ct[j].l*256+riding_dotq32(k->rx&255,k->ry&255,Ct[j].nx,Ct[j].ny,14);
        if(distance<FINE_CONTACT_RADIUS)Ct[valid++]=Ct[j];
    }
    n=valid;
#endif
#ifdef NATIVE_ORDERED_PAIR
    uint8_t two = n == 2 || n == 254;
#else
    uint8_t two = n == 2;
#endif
	uint8_t wheel = k==&Bike.wheel[1];
#ifndef NATIVE_FINE_CONTACTS
	if( n > 0 )
		pushout( k, &Ct[0], two ? &Ct[1] : 0 );
	if( two )
		pushout( k, &Ct[1], 0 );
#endif
#ifdef NATIVE_ORDERED_PAIR
    if(two) {
        uint8_t local_signs[2]={0,0};
        n=resolve_ordered_pair(input,n==254?pair_separation[wheel]:local_signs);
    } else if(n && !supports(k,&Ct[0],input->dvx,input->dvy,0))
        n=0;
#else
	if( two ) {
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
#endif
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
#ifdef NATIVE_ORDERED_PAIR
        wheel_free_record(input);
#elif defined(__SDCC) && !defined(PHYSICS_WHEEL_C)
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
#ifdef NATIVE_ORDERED_PAIR
    wheel_roll_record(input);
#elif defined(__SDCC) && !defined(PHYSICS_WHEEL_C)
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

#if defined(__SDCC) && !defined(NATIVE_FINE_CONTACTS)
/* The reference configurations keep their C solver and its public banked ABI. */
void riding_wheel_from_record(const wheel_input_t *input) {
    riding_wheel(input->k,input->dvx,input->dvy,input->tq);
}
void riding_wheel_inputs(void) __naked {
    __asm
    ld d,h
    ld e,l
    jp _riding_wheel_from_record
    __endasm;
}
#endif
