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

static contact_t Ct[2];
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
		if( pos >= 0 && pos <= s->len ) {
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
			// Near an end point:
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
		if( pos >= 0 && pos <= s->len )
			return 1;
		if( pos > 0 ) {
			x -= s->dx;
			y -= s->dy;
		}
		if( mul16( x, x )+mul16( y, y ) < (int32_t)rad*rad )
			return 1;
	}
	return 0;
}
