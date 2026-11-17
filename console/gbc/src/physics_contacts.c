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
static uint8_t contacts(int32_t cx,int32_t cy) {
 int16_t qx=(int16_t)(cx&4095),qy=(int16_t)(cy&4095);
 seg_query(seg_cell(cx),seg_cell(cy),(uint8_t)((qx>>10)|((qy>>8)&12)));
 return riding_contacts_loop(qx,qy);
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

// helyigazitas: does not let the wheel into the ground deeper than the band.
// The other contact point gets farther by the push along its direction.
#if defined(__SDCC) && !defined(PHYSICS_PUSHOUT_C)
#include <stddef.h>
typedef char pushout_layout[sizeof(circle_t)==22 && offsetof(circle_t,rx)==0 &&
 offsetof(circle_t,ry)==4 && sizeof(contact_t)==10 && offsetof(contact_t,nx)==0 &&
 offsetof(contact_t,ny)==2 && offsetof(contact_t,l)==4 && R_WHEEL-BAND==405?1:-1];
void riding_pushout32(circle_t*,contact_t*,contact_t*) __sdcccall(1);
#define pushout riding_pushout32
#else
static void pushout( circle_t* k, contact_t* c, contact_t* other ) {
	int16_t push = R_WHEEL-BAND-c->l;
	if( push <= 0 )
		return;
	int16_t px = mulq14( push, c->nx ), py = mulq14( push, c->ny );
	k->rx += (int32_t)px << 8;
	k->ry += (int32_t)py << 8;
	c->l += push;
	if( other )
		other->l += dotq14( px, py, other->nx, other->ny );
}
#endif

// talppontigazitas: true if the point really supports the wheel. With two
// points, the velocity towards it is removed (with one, rolling around it
// takes only the velocity along the ground anyway).
#if defined(__SDCC) && defined(RIDING_COEFFICIENT_LOOKUP)
uint8_t riding_supports32(circle_t*,const contact_t*,int32_t,int32_t,uint8_t) __sdcccall(1);
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
/* For a nonnegative contact length, each positive coefficient below one
 * half preserves the projected impulse sign and leaves >32768 headroom.
 * Classifying same-sign terms first is exact, including zero geometry. */
#if C_NEW_M*2 >= (1L<<C_NEW_E) || C_OLD_M*2 >= (1L<<C_OLD_E)
#error Contact sign shortcut requires coefficients below one half
#endif
static uint8_t sure_new(const contact_t *t1,const contact_t *t2,const circle_t *k) {
 int16_t d=dotq14(t1->tx-t2->tx,t1->ty-t2->ty,-t2->ny,t2->nx);
 int32_t vn,m;
 if(!d)return 1;
 vn=riding_dotq32(k->vx,k->vy,-t2->ny,t2->nx,14);
 if(t2->l>=0){
  if(!vn || !t2->l)return same_side(d,k->omega);
  if(k->omega>0 && vn>=0)return d>0;
  if(k->omega<0 && vn<=0)return d<0;
 }
 m=k->omega+KMUL32(riding_mulshift32(vn,t2->l,10),C_NEW);
 return same_side(d,m);
}
static uint8_t sure_old(const contact_t *t1,const contact_t *t2,int32_t dvx,int32_t dvy,int16_t tq) {
 int16_t d=dotq14(t1->tx-t2->tx,t1->ty-t2->ty,-t2->ny,t2->nx);
 int32_t dvn,p,m;
 if(!d)return 1;
 dvn=riding_dotq32(dvx,dvy,-t2->ny,t2->nx,14);
 if(t2->l>=0){
  if(!dvn || !t2->l)return same_side(d,tq);
  if(tq>0 && dvn>=0)return d>0;
  if(tq<0 && dvn<=0)return d<0;
 }
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

#ifdef __SDCC
#define move riding_move32
#else
static void move( circle_t* k ) {
	k->alfa += (int32_t)k->omega << 7;
	k->rx += (int32_t)k->vx << 2;
	k->ry += (int32_t)k->vy << 2;
}
#endif

#if defined(__SDCC) && defined(RIDING_COEFFICIENT_LOOKUP)
#include <stddef.h>
typedef char wheel_response_layout[ELSZ==10 && sizeof(circle_t)==22 && offsetof(circle_t,vx)==8 &&
 offsetof(circle_t,vy)==12 && offsetof(circle_t,omega)==20 &&
 offsetof(contact_t,nx)==0 && offsetof(contact_t,ny)==2?1:-1];
void riding_free32(circle_t*,int32_t,int32_t,int16_t) __sdcccall(0);
void riding_roll32(circle_t*,const contact_t*,int32_t,int32_t,int16_t) __sdcccall(0);
#endif

// beallit for a wheel: dv is the velocity change from the forces, tq the
// torque on it.
uint8_t riding_audio_contact[2], riding_audio_impact[2];
void riding_wheel( circle_t* k, int32_t dvx, int32_t dvy, int16_t tq ) PH_BANKED {
	uint8_t n = contacts( riding_sra8(k->rx), riding_sra8(k->ry) );
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
	if( n == 0 ) {
#if defined(__SDCC) && defined(RIDING_COEFFICIENT_LOOKUP)
        riding_free32(k,dvx,dvy,tq);
#else
		k->omega = sat16((int32_t)k->omega+KMUL(tq,C_FREE));
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
#if defined(__SDCC) && defined(RIDING_COEFFICIENT_LOOKUP)
 riding_roll32(k,&Ct[0],dvx,dvy,tq);
#else
	// Rolls around the contact point:
	int16_t n90x = -Ct[0].ny, n90y = Ct[0].nx;
	int32_t vn = riding_dotq32(k->vx,k->vy,n90x,n90y,14);
	int32_t dvn = riding_dotq32(dvx,dvy,n90x,n90y,14);
	int32_t t = (int32_t)tq+KMUL32(dvn,C_ROLL_T);
	int32_t w = KMUL32(vn,C_ROLL_W)+KMUL32(t,C_ROLL_DW);
	/* Angular state remains16; no linear velocity is narrowed here. */
	k->omega = sat16(w);
	int32_t sp = KMUL32((int32_t)k->omega,C_ROLL_V);
	k->vx = riding_mulq32(sp,n90x,14);
	k->vy = riding_mulq32(sp,n90y,14);
	move( k );
#endif
}
