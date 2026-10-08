// The physics of the SNES version in C: what src/phys.asm does, to the bit.
// It follows LEPTET.CPP, BEALLIT.CPP, UTKOZES.CPP, UTKOZES2.CPP and the
// object handling of LEJATSZO.CPP of the original game, in fixed point.
//
// The arithmetic is the one of the PPU multiplier, which multiplies a
// 16-bit number by one signed byte at a time: mq16 and mq24 are products of
// a 16-bit number or of a 24-bit one (of three signed bytes, larger ones are
// clamped) and a 16-bit one, without their lowest byte (>> 8, rounded
// down); mf16 is a whole product. rsh shifts right rounding to nearest.
#include "phys_spec.h"
#include "phys_const.h"
#include "phys_tables.h"

ps_state_t PS;
ps_obj_t PS_obj[52];
uint16_t PS_nobjs, PS_apples_needed;
uint16_t PS_eaten, PS_bump, PS_friction, PS_wheel_omega;

// The level:
static const uint8_t* Lev;
static int32_t Grid_x, Grid_y, Racs_x, Racs_y, Kill[4];
static uint16_t Grid_w, Grid_h, Off_rows;

static int Racs;              // Racsonkivul of the step

static uint16_t rd16( uint16_t off ) { return Lev[off] | Lev[off+1] << 8; }
static int16_t rds16( uint16_t off ) { return (int16_t)rd16( off ); }
static int32_t rd24( uint16_t off ) { return Lev[off] | Lev[off+1] << 8 | (int32_t)Lev[off+2] << 16; }
static int32_t rd32( uint16_t off ) { return (int32_t)((uint32_t)rd16( off ) | (uint32_t)rd16( off+2 ) << 16); }

// The range of a 24-bit number of three signed bytes:
static int32_t clamp24( int32_t x ) {
	if( x > 0x7F7F7F ) return 0x7F7F7F;
	if( x < -0x808080 ) return -0x808080;
	return x;
}

// The range of a 16-bit number of two signed bytes (and of its negative):
static int16_t clamp16( int32_t x ) {
	if( x > 32639 ) return 32639;
	if( x < -32640 ) return -32640;
	return (int16_t)x;
}

static int32_t mf16( int16_t a, int16_t b ) { return (int32_t)a*b; }
static int32_t mq16( int16_t a, int16_t b ) { return ((int32_t)a*b) >> 8; }
static int32_t mq24( int32_t x, int16_t m ) { return (int32_t)(((int64_t)clamp24( x )*m) >> 8); }

// x >> n, rounded to nearest (halves up):
static int32_t rsh( int32_t x, int n ) {
	if( n == 0 )
		return x;
	return (int32_t)(((int64_t)x + ((int64_t)1 << (n-1))) >> n);
}

// x times the constant K_M/2^K_SH:
#define MULK( x, K ) rsh( mq24( (x), K##_M ), K##_SH-8 )

static int32_t iabs( int32_t x ) { return x < 0 ? -x : x; }

// An angle back between -pi and pi:
static int32_t wrap( int32_t a ) {
	if( a >= PI_W )
		a -= TWOPI_W;
	else if( a < -PI_W )
		a += TWOPI_W;
	return a;
}

// sin of an angle from 0 to pi/2 (W), Q22:
static int32_t qsin( int32_t b ) {
	int i = b >> 19;
	int16_t f = (int16_t)((b >> 4) & 0x7FFF);
	return phys_qsin[i]+rsh( mq16( f, phys_qsind[i] ), 7 );
}

static int32_t Cs22, Sn22;    // cos and sin of the body, Q22
static int16_t Cs, Sn;        // the same, Q15

static int16_t q15( int32_t v ) {
	v >>= 7;
	return (int16_t)(v > 32767 ? 32767 : v < -32767 ? -32767 : v);
}

static void trig( int32_t a ) {
	int32_t b = a < 0 ? -a : a;
	int32_t s = qsin( b > HALFPI_W ? PI_W-b : b );
	Sn22 = a < 0 ? -s : s;
	Cs22 = b > HALFPI_W ? -qsin( b-HALFPI_W ) : qsin( HALFPI_W-b );
	Sn = q15( Sn22 );
	Cs = q15( Cs22 );
}

// 1/sqrt: Y and k with 1/sqrt( d2 ) = Y * 2^(k-30); X is d2 << 2k.
static int16_t frsqrt( uint32_t d2, int* pk, uint32_t* pX ) {
	int k = 0;
	uint32_t X = d2;
	while( X < 0x40000000u ) {
		X <<= 2;
		k++;
	}
	int m = (int)(X >> 24) - 64;
	int f = (X >> 17) & 127;
	*pk = k;
	*pX = X;
	return (int16_t)(phys_rsq[m] + ((phys_rsqd[m]*f + 64) >> 7));
}

// A contact of a circle with the ground: its point t (P), and the unit
// vector n (Q15) from it to the center and the distance h (P) when known;
// dn tells how far n is from length 1 ((2^30 - |n|^2)/2).
typedef struct {
	int32_t tx, ty;
	int16_t nx, ny, h, dn;
	uint8_t has_t, has_n;
} contact_t;

// A component of a unit vector (Q15):
static int16_t unit15( int32_t x ) {
	if( x > 32767 ) return 32767;
	if( x < -32767 ) return -32767;
	return (int16_t)x;
}

// The unit vector and length of d (P), for a contact:
static void norm( int32_t dx, int32_t dy, contact_t* c ) {
	int sh = 0;
	while( dx > 32767 || dx < -32767 || dy > 32767 || dy < -32767 ) {
		dx >>= 1;
		dy >>= 1;
		sh++;
	}
	uint32_t d2 = (uint32_t)(mf16( (int16_t)dx, (int16_t)dx )+mf16( (int16_t)dy, (int16_t)dy ));
	c->dn = 0;
	c->has_n = 1;
	if( d2 == 0 ) {
		c->nx = 0;
		c->ny = 32767;
		c->h = 0;
		return;
	}
	int k;
	uint32_t X;
	int16_t Y = frsqrt( d2, &k, &X );
	c->nx = unit15( rsh( mf16( (int16_t)dx, Y ), 15-k ) );
	c->ny = unit15( rsh( mf16( (int16_t)dy, Y ), 15-k ) );
	c->h = clamp16( rsh( mf16( (int16_t)(X >> 17), Y ), 13+k ) << sh );
}

static void need_t( contact_t* c, int32_t rx, int32_t ry ) {
	if( c->has_t )
		return;
	c->tx = rx-rsh( mq16( c->nx, c->h ), 7 );
	c->ty = ry-rsh( mq16( c->ny, c->h ), 7 );
	c->has_t = 1;
}

static void need_n( contact_t* c, int32_t rx, int32_t ry ) {
	if( !c->has_n )
		norm( rx-c->tx, ry-c->ty, c );
}

// talppontkereses (UTKOZES.CPP) with gombszakasz: the contacts of a circle
// at rx, ry with the lines of the level, at most two, in the order of the
// lines. With ct NULL (the head) only whether there is one.
static int contacts( int32_t rx, int32_t ry, int32_t R, uint32_t RSQ, contact_t* ct ) {
	if( rx >= Racs_x || ry >= Racs_y )
		Racs = 1;
	int32_t qx = rx-Grid_x, qy = ry-Grid_y;
	if( qx < 0 || qy < 0 || qx >= (int32_t)Grid_w << 17 || qy >= (int32_t)Grid_h << 17 )
		return 0;
	int cx = qx >> 17, cy = qy >> 17;
	uint16_t bx = (uint16_t)(qx >> 8), by = (uint16_t)(qy >> 8);
	// The run of the row with the cell:
	uint16_t run = rd16( Off_rows+2*cy ), end = rd16( Off_rows+2*cy+2 );
	uint16_t list = 0;
	for( ; run < end; run += 3 ) {
		if( Lev[run] > cx )
			break;
		list = rd16( run+1 );
	}
	if( !list )
		return 0;
	int n = 0;
	uint16_t count = rd16( list );
	for( uint16_t j = 0; j < count; j++ ) {
		uint16_t L = rd16( list+2+2*j );
		if( bx < rd16( L ) || bx > rd16( L+2 ) || by < rd16( L+4 ) || by > rd16( L+6 ) )
			continue;
		// From the middle of the line, in 2^-15 m:
		int32_t rx15 = (qx-rd24( L+8 )) >> 1, ry15 = (qy-rd24( L+11 )) >> 1;
		int16_t ex = rds16( L+20 ), ey = rds16( L+22 );
		int8_t elx = (int8_t)Lev[L+24], ely = (int8_t)Lev[L+25];
		// The distance from the line, its direction to the precision of
		// the level (e and the rest of it), and where along it:
		int32_t tav = rsh( mq24( ry15, ex )+mq24( rx15, (int16_t)-ey )+
				  mq16( (int16_t)(ry15 >> 8), elx )+mq16( (int16_t)(rx15 >> 8), (int16_t)-ely ), 6 );
		if( tav > R || tav < -R )
			continue;
		int32_t pos = rsh( mq24( rx15, ex )+mq24( ry15, ey ), 6 );
		contact_t c;
		c.has_t = c.has_n = 0;
		c.dn = 0;
		int32_t dx = 0, dy = 0;
		int point = 1;
		int32_t half = rd24( L+28 );
		if( pos < -half ) {
			// The start of the line, A = 2M - B - par:
			int par = Lev[L+31];
			dx = qx-(2*rd24( L+8 )-rd24( L+14 )-(par & 1));
			dy = qy-(2*rd24( L+11 )-rd24( L+17 )-(par >> 1));
		}
		else if( pos > half ) {
			dx = qx-rd24( L+14 );
			dy = qy-rd24( L+17 );
		}
		else
			point = 0;
		if( point ) {
			if( dx >= R || dx <= -R || dy >= R || dy <= -R )
				continue;
			uint32_t d2 = (uint32_t)(mf16( (int16_t)dx, (int16_t)dx )+mf16( (int16_t)dy, (int16_t)dy ));
			if( d2 >= RSQ )
				continue;
			c.tx = rx-dx;
			c.ty = ry-dy;
			c.has_t = 1;
		}
		else {
			if( tav >= 0 ) {
				c.nx = (int16_t)-ey;
				c.ny = ex;
				c.h = (int16_t)tav;
			}
			else {
				c.nx = ey;
				c.ny = (int16_t)-ex;
				c.h = (int16_t)-tav;
			}
			c.dn = rds16( L+26 );
			c.has_n = 1;
		}
		if( !ct )
			return 1;
		if( n == 0 ) {
			ct[0] = c;
			n = 1;
			continue;
		}
		// The second one: one with the first if they are near.
		need_t( &ct[0], rx, ry );
		need_t( &c, rx, ry );
		int32_t mx = ct[0].tx-c.tx, my = ct[0].ty-c.ty;
		if( mx < MERGE_P && mx > -MERGE_P && my < MERGE_P && my > -MERGE_P &&
				(uint32_t)(mf16( (int16_t)mx, (int16_t)mx )+mf16( (int16_t)my, (int16_t)my )) < MERGE_SQ ) {
			ct[0].tx = (ct[0].tx+c.tx) >> 1;
			ct[0].ty = (ct[0].ty+c.ty) >> 1;
			ct[0].has_n = 0;
			ct[0].dn = 0;
			continue;
		}
		ct[1] = c;
		return 2;
	}
	return n;
}

// helyigazitas: a wheel not deeper than the band. True if it moved.
static int push( ps_circle_t* k, contact_t* c ) {
	if( c->h >= BAND_P )
		return 0;
	int16_t p = (int16_t)(BAND_P-c->h);
	k->rx += rsh( mq16( c->nx, p ), 7 );
	k->ry += rsh( mq16( c->ny, p ), 7 );
	c->h = BAND_P;
	return 1;
}

static int32_t Fx, Fy;          // the force on the wheel, as the velocity it adds (V)
static int32_t Mk;              // the torque on it (T)

static int same_side( int32_t d, int32_t m ) {
	return !((d < 0 && m > 0) || (d > 0 && m < 0));
}

// (t1-t2)*n90 of biztostalppont, n90 of the contact at t2:
static int32_t side( const contact_t* c1, const contact_t* c2 ) {
	int16_t dx = clamp16( (c1->tx-c2->tx) >> 1 ), dy = clamp16( (c1->ty-c2->ty) >> 1 );
	return mq16( (int16_t)-c2->ny, dx )+mq16( c2->nx, dy );
}

// biztostalppont_uj: true if t1 stays a contact point turning around t2.
static int sure_new( const ps_circle_t* k, const contact_t* c1, const contact_t* c2 ) {
	int16_t vx = clamp16( rsh( k->vx, 8 ) ), vy = clamp16( rsh( k->vy, 8 ) );
	int16_t nv = clamp16( rsh( mq16( (int16_t)-c2->ny, vx )+mq16( c2->nx, vy ), 7 ) );
	int32_t m = k->w+rsh( mf16( nv, c2->h ), 4 );
	return same_side( side( c1, c2 ), m );
}

// biztostalppont_regi:
static int sure_old( const contact_t* c1, const contact_t* c2 ) {
	int32_t fn = rsh( mq24( Fx, (int16_t)-c2->ny )+mq24( Fy, c2->nx ), 7 );
	int32_t x = rsh( mq24( fn, c2->h ), 8 );
	int32_t m = Mk+MULK( x, K_REGI );
	return same_side( side( c1, c2 ), m );
}

// talppontigazitas: true if the point really holds the wheel; then the
// velocity towards it goes (only where it matters: the second of two).
static int holds( ps_circle_t* k, const contact_t* c, int remove, uint16_t* pev ) {
	int16_t vx = clamp16( k->vx >> 8 ), vy = clamp16( k->vy >> 8 );
	int32_t nv = rsh( mf16( c->nx, vx )+mf16( c->ny, vy ), 7 );
	if( nv > -ELSZ_V && mq24( Fx, c->nx )+mq24( Fy, c->ny ) > 0 )
		return 0;
	if( remove ) {
		k->vx -= rsh( mq24( nv, c->nx ), 7 );
		k->vy -= rsh( mq24( nv, c->ny ), 7 );
	}
	int32_t a = iabs( nv );
	if( a > BUMP_MIN_V ) {
		int32_t b = MULK( a, K_BUMP );
		if( b > 253 )
			b = 253;
		if( b > PS_bump )
			PS_bump = (uint16_t)b;
		*pev |= PH_BUMP;
	}
	return 1;
}

// beallit for a wheel; returns the change of its angle.
static int32_t wheel( ps_circle_t* k, ps_roll_t* rs, uint16_t* pev ) {
	contact_t ct[2];
	int n = contacts( k->rx, k->ry, R_WHEEL_P, R_WHEEL_SQ, ct );
	if( n >= 1 ) {
		need_n( &ct[0], k->rx, k->ry );
		if( push( k, &ct[0] ) && n == 2 )
			ct[1].has_n = 0;
	}
	if( n == 2 ) {
		need_n( &ct[1], k->rx, k->ry );
		if( push( k, &ct[1] ) )
			norm( k->rx-ct[0].tx, k->ry-ct[0].ty, &ct[0] );
		int16_t vx = clamp16( rsh( k->vx, 8 ) ), vy = clamp16( rsh( k->vy, 8 ) );
		uint32_t v2 = (uint32_t)(mf16( vx, vx )+mf16( vy, vy ));
		if( v2 > (uint32_t)V1MS_16*V1MS_16 ) {
			if( !sure_new( k, &ct[0], &ct[1] ) ) {
				n = 1;
				ct[0] = ct[1];
			}
			else if( !sure_new( k, &ct[1], &ct[0] ) )
				n = 1;
		}
		else if( v2 < (uint32_t)V1MS_16*V1MS_16 ) {
			if( !sure_old( &ct[0], &ct[1] ) ) {
				n = 1;
				ct[0] = ct[1];
			}
			else if( !sure_old( &ct[1], &ct[0] ) )
				n = 1;
		}
	}
	if( n == 2 && !holds( k, &ct[1], 1, pev ) )
		n = 1;
	if( n >= 1 && !holds( k, &ct[0], 0, pev ) ) {
		if( n == 2 ) {
			n = 1;
			ct[0] = ct[1];
		}
		else
			n = 0;
	}
	if( n != 1 )
		rs->on = 0;
	if( n == 0 ) {
		// Free in the air (a torque in whole products, K_FREE is large):
		k->w += rsh( (int32_t)(((int64_t)clamp24( Mk )*K_FREE_M) >> 4), K_FREE_SH-4 );
		k->a = wrap( k->a+k->w );
		k->vx += Fx;
		k->vy += Fy;
		k->rx += rsh( k->vx, 8 );
		k->ry += rsh( k->vy, 8 );
		return k->w;
	}
	if( n == 2 ) {
		// Held:
		k->vx = k->vy = 0;
		k->w = 0;
		return 0;
	}
	// Rolls around the contact point. Its speed along the ground is the one
	// of the last step if it rolled the same way then (its velocity is that
	// speed along the same direction):
	contact_t* c = &ct[0];
	int16_t n90x = (int16_t)-c->ny, n90y = c->nx;
	int32_t sp;
	if( rs->on && rs->nx == c->nx && rs->ny == c->ny )
		sp = rs->s;
	else {
		// v*n90/|n90|:
		sp = rsh( mq24( k->vx, n90x )+mq24( k->vy, n90y ), 7 );
		sp += rsh( mq24( sp, c->dn ), 22 );
	}
	int32_t fn = rsh( mq24( Fx, n90x )+mq24( Fy, n90y ), 7 );
	int h = c->h;
	if( h < 0 ) h = 0;
	if( h > 26367 ) h = 26367;
	int i = h >> 7, f = h & 127;
	int16_t rho = (int16_t)(phys_rho[i]+((phys_rhod[i]*f+64) >> 7));
	int32_t b = MULK( fn, K_FN )+MULK( Mk, K_MR );
	sp = clamp24( sp+rsh( mq24( b, rho ), 5 ) );
	k->w = sp*40;
	k->a = wrap( k->a+k->w );
	k->vx = rsh( mq24( sp, n90x ), 7 );
	k->vy = rsh( mq24( sp, n90y ), 7 );
	k->rx += rsh( k->vx, 8 );
	k->ry += rsh( k->vy, 8 );
	rs->on = 1;
	rs->nx = c->nx;
	rs->ny = c->ny;
	rs->s = sp;
	return k->w;
}

// szamitfejr:
static void head( void ) {
	int16_t hx = PS.turned ? K09_15 : -K09_15;
	PS.head_x = PS.rider_x+rsh( mq16( Cs, hx )+mq16( Sn, -K63_15 ), 6 );
	PS.head_y = PS.rider_y+rsh( mq16( Sn, hx )+mq16( Cs, K63_15 ), 6 );
}

// utkozikesprite: the first active object the circle touches.
static int sprite( int32_t rx, int32_t ry, int32_t lim, uint32_t sq ) {
	for( int i = 0; i < PS_nobjs; i++ ) {
		const ps_obj_t* o = &PS_obj[i];
		if( !o->active )
			continue;
		int32_t dx = rx-o->x, dy = ry-o->y;
		if( dx >= lim || dx <= -lim || dy >= lim || dy <= -lim )
			continue;
		int16_t x = (int16_t)(dx >> 1), y = (int16_t)(dy >> 1);
		if( (uint32_t)(mf16( x, x )+mf16( y, y )) < sq )
			return i;
	}
	return -1;
}

void ps_level( const uint8_t* blob ) {
	Lev = blob;
	Grid_x = rd32( 0 );
	Grid_y = rd32( 4 );
	Grid_w = rd16( 8 );
	Grid_h = rd16( 10 );
	PS_nobjs = rd16( 14 );
	uint16_t off_objs = rd16( 18 );
	Off_rows = rd16( 22 );
	Racs_x = rd32( 24 );
	Racs_y = rd32( 28 );
	for( int i = 0; i < 4; i++ )
		Kill[i] = rd32( 32+4*i );
	uint8_t* p = (uint8_t*)&PS;
	for( unsigned i = 0; i < sizeof( PS ); i++ )
		p[i] = 0;
	for( int i = 0; i < 3; i++ ) {
		PS.c[i].rx = rd32( 48+8*i );
		PS.c[i].ry = rd32( 52+8*i );
	}
	PS.rider_x = rd32( 72 );
	PS.rider_y = rd32( 76 );
	PS_apples_needed = rd16( 80 );
	PS.gravity = 1;
	PS.last_volt = 255;
	PS.volt_t[0] = PS.volt_t[1] = 255;
	for( int i = 0; i < PS_nobjs; i++ ) {
		uint16_t o = off_objs+12*i;
		PS_obj[i].type = Lev[o];
		PS_obj[i].anim = Lev[o+1];
		PS_obj[i].gravity = Lev[o+2];
		PS_obj[i].active = Lev[o] != 4;
		PS_obj[i].x = rd32( o+4 );
		PS_obj[i].y = rd32( o+8 );
	}
	PS_eaten = PS_bump = PS_friction = PS_wheel_omega = 0;
	trig( 0 );
	head();
}

void ps_turn( void ) {
	PS.turned = !PS.turned;
	trig( PS.c[0].a );
	head();
}

uint16_t ps_angle16( int32_t a ) {
	return (uint16_t)MULK( a >> 15, K_WVIEW );
}

uint16_t ps_step( uint16_t input ) {
	uint16_t ev = 0;
	Racs = 0;
	PS_bump = 0;
	int32_t fric = 0;
	ps_circle_t* body = &PS.c[0];
	trig( body->a );
	int32_t w1 = rsh( body->w, 4 );

	// Gas and brake (leptet):
	int brake = (input & PH_BRAKE) != 0;
	if( brake && !PS.brake_was )
		PS.defl[0] = PS.defl[1] = 0;
	PS.brake_was = (uint8_t)brake;
	int32_t M[2] = { 0, 0 };
	if( input & PH_GAS ) {
		if( PS.turned ) {
			if( PS.c[1].w > -TULP_W )
				M[0] = -GAS_T;
		}
		else if( PS.c[2].w < TULP_W )
			M[1] = GAS_T;
	}
	if( brake ) {
		for( int k = 0; k < 2; k++ ) {
			int32_t dw = rsh( PS.c[1+k].w-body->w, 8 );
			M[k] = -(MULK( PS.defl[k], K_BRK_S )+MULK( dw, K_BRK_W ));
		}
	}

	// erokszamitasa: the springs and dampers between the body and the
	// wheels. The anchors of the wheels on the body (P):
	int32_t a = rsh( mq24( Cs22, K85_15 ), 13 );
	int32_t b = rsh( mq24( Sn22, K60_15 ), 13 );
	int32_t cc = rsh( mq24( Sn22, K85_15 ), 13 );
	int32_t d = rsh( mq24( Cs22, K60_15 ), 13 );
	int32_t gsx[2] = { b-a, a+b };
	int32_t gsy[2] = { -cc-d, cc-d };
	int32_t Dx[2], Dy[2];
	int32_t cross_s = 0, cross_d = 0;
	for( int k = 0; k < 2; k++ ) {
		ps_circle_t* w = &PS.c[1+k];
		int32_t gx = gsx[k]+body->rx-w->rx;
		int32_t gy = gsy[k]+body->ry-w->ry;
		int16_t kx = clamp16( rsh( w->rx-body->rx, 3 ) );
		int16_t ky = clamp16( rsh( w->ry-body->ry, 3 ) );
		int32_t relx = rsh( mq24( w1, (int16_t)-ky ), 5 )+body->vx-w->vx;
		int32_t rely = rsh( mq24( w1, kx ), 5 )+body->vy-w->vy;
		Dx[k] = MULK( relx, K_DAMP );
		Dy[k] = MULK( rely, K_DAMP );
		if( iabs( gx ) > SPRING_ZERO_P || iabs( gy ) > SPRING_ZERO_P ) {
			Dx[k] += MULK( gx, K_SPRING );
			Dy[k] += MULK( gy, K_SPRING );
			cross_s += mq24( gy, (int16_t)rsh( gsx[k], 2 ) )+mq24( gx, (int16_t)-rsh( gsy[k], 2 ) );
		}
		cross_d += mq24( rely, kx )+mq24( relx, (int16_t)-ky );
		if( M[k] ) {
			// Ftestnyom: the torque of the wheel pushes its axle.
			uint32_t k2 = (uint32_t)(mf16( kx, kx )+mf16( ky, ky ));
			if( k2 < 65536 )
				k2 = 65536;
			int s = 0;
			uint32_t X = k2;
			while( !(X & 0x80000000u) ) {
				X <<= 1;
				s++;
			}
			int m = (int)(X >> 24)-128, f = (X >> 17) & 127;
			int16_t rc = (int16_t)(phys_rcp[m]+((phys_rcpd[m]*f+64) >> 7));
			int32_t B = rsh( mq24( M[k], rc ), 8 );
			int32_t px = mq24( B, ky ), py = mq24( B, kx );
			if( s <= 7 ) {
				Dx[k] += rsh( px, 7-s );
				Dy[k] -= rsh( py, 7-s );
			}
			else {
				Dx[k] += px << (s-7);
				Dy[k] -= py << (s-7);
			}
		}
		// surlodasverseny: the friction for the sound, with the direction
		// of the body in a byte (not in a quick step):
		if( input & PH_QUICK )
			continue;
		int16_t g16x = clamp16( rsh( gx, 2 ) ), g16y = clamp16( rsh( gy, 2 ) );
		int16_t rvx = clamp16( rsh( relx, 8 ) ), rvy = clamp16( rsh( rely, 8 ) );
		int16_t s8 = (int16_t)(Sn >> 8), c8 = (int16_t)((-Cs) >> 8);
		int32_t fg = mq16( g16x, s8 )+mq16( g16y, c8 );
		int32_t sb = mq16( rvx, s8 )+mq16( rvy, c8 );
		if( fg > 0 && sb > 0 ) {
			int32_t e = MULK( mq16( clamp16( fg ), clamp16( sb ) ), K_FRIC );
			if( e > fric )
				fric = e;
		}
	}

	// Volts:
	int volt1 = 0, volt2 = 0;
	if( PS.last_volt >= VOLT_GAP ) {
		if( input & PH_VOLT_R ) {
			volt1 = 1;
			PS.last_volt = 0;
			PS.volt1 = 1;
			ev |= PH_VOLT;
		}
		if( input & PH_VOLT_L ) {
			volt2 = 1;
			PS.last_volt = 0;
			PS.volt1 = 0;
			ev |= PH_VOLT;
		}
	}
	int32_t oldw = body->w;
	if( PS.volt_on[0] && (volt1 || volt2 || PS.volt_t[0] >= VOLT_END) ) {
		body->w += LOKET_W;
		if( body->w > PS.volt_w[0] )
			body->w = PS.volt_w[0];
		if( body->w > 0 ) {
			body->w -= OMEGAVALT_W;
			if( body->w < 0 )
				body->w = 0;
		}
		PS.volt_on[0] = 0;
	}
	if( PS.volt_on[1] && (volt1 || volt2 || PS.volt_t[1] >= VOLT_END) ) {
		body->w -= LOKET_W;
		if( body->w < PS.volt_w[1] )
			body->w = PS.volt_w[1];
		if( body->w < 0 ) {
			body->w += OMEGAVALT_W;
			if( body->w > 0 )
				body->w = 0;
		}
		PS.volt_on[1] = 0;
	}
	if( volt1 ) {
		PS.volt_on[0] = 1;
		PS.volt_w[0] = body->w;
		PS.volt_t[0] = 0;
		body->w -= LOKET_W;
	}
	if( volt2 ) {
		PS.volt_on[1] = 1;
		PS.volt_w[1] = body->w;
		PS.volt_t[1] = 0;
		body->w += LOKET_W;
	}
	if( volt1 || volt2 ) {
		// The rider turns with the body:
		int16_t dw = clamp16( rsh( body->w-oldw, 12 ) );
		int16_t dx = clamp16( rsh( PS.rider_x-body->rx, 1 ) );
		int16_t dy = clamp16( rsh( PS.rider_y-body->ry, 1 ) );
		PS.rider_vx -= rsh( mf16( dw, dy ), 7 );
		PS.rider_vy += rsh( mf16( dw, dx ), 7 );
	}

	// Gravity:
	int32_t gvx = 0, gvy = 0;
	switch( PS.gravity ) {
		case 0: gvy = G_V; break;
		case 2: gvx = -G_V; break;
		case 3: gvx = G_V; break;
		default: gvy = -G_V; break;
	}

	// beallitvezeto: the rider. vezeto_hatarolas keeps him over the seat
	// (in the frame of the body, 2^-15 m):
	{
		int16_t dx = clamp16( rsh( PS.rider_x-body->rx, 1 ) );
		int16_t dy = clamp16( rsh( PS.rider_y-body->ry, 1 ) );
		int16_t x = clamp16( rsh( mq16( Cs, dx )+mq16( Sn, dy ), 7 ) );
		int16_t y = clamp16( rsh( mq16( Cs, dy )+mq16( (int16_t)-Sn, dx ), 7 ) );
		if( PS.turned )
			x = (int16_t)-x;
		int moved = 0;
		int32_t lel = mq16( x, SEAT_NX )+mq16( y, SEAT_NY )-SEAT_C8;
		if( lel < 0 ) {
			int16_t l = clamp16( rsh( lel, 7 ) );
			x = clamp16( x-rsh( mq16( l, SEAT_NX ), 7 ) );
			y = clamp16( y-rsh( mq16( l, SEAT_NY ), 7 ) );
			moved = 1;
		}
		if( y > RIDER_TOP ) {
			y = RIDER_TOP;
			moved = 1;
		}
		if( x < RIDER_LEFT ) {
			x = RIDER_LEFT;
			moved = 1;
		}
		if( x > RIDER_RIGHT ) {
			x = RIDER_RIGHT;
			moved = 1;
		}
		if( x > 0 && y > 0 ) {
			int16_t xs = (int16_t)rsh( mq16( x, RIDER_ELL ), 6 );
			uint32_t t2 = (uint32_t)(mf16( xs, xs )+mf16( y, y ));
			if( t2 > RIDER_TOP_SQ ) {
				int k;
				uint32_t X;
				int16_t Y = frsqrt( t2, &k, &X );
				int16_t sc = (int16_t)rsh( mf16( Y, RIDER_TOP ), 15-k );
				x = (int16_t)rsh( mq16( sc, x ), 7 );
				y = (int16_t)rsh( mq16( sc, y ), 7 );
				moved = 1;
			}
		}
		if( moved ) {
			if( PS.turned )
				x = (int16_t)-x;
			PS.rider_x = body->rx+rsh( mq16( Cs, x )+mq16( (int16_t)-Sn, y ), 6 );
			PS.rider_y = body->ry+rsh( mq16( Sn, x )+mq16( Cs, y ), 6 );
		}
		// The spring to its place over the body, and its damper:
		int32_t wb = rsh( body->w, 4 );
		int32_t rgx = body->rx-rsh( mq16( Sn, K44_15 ), 6 );
		int32_t rgy = body->ry+rsh( mq16( Cs, K44_15 ), 6 );
		int16_t dirx = clamp16( rsh( rgx-PS.rider_x, 1 ) );
		int16_t diry = clamp16( rsh( rgy-PS.rider_y, 1 ) );
		dx = clamp16( rsh( PS.rider_x-body->rx, 1 ) );
		dy = clamp16( rsh( PS.rider_y-body->ry, 1 ) );
		int32_t mvx = body->vx-rsh( mq24( wb, dy ), 7 );
		int32_t mvy = body->vy+rsh( mq24( wb, dx ), 7 );
		PS.rider_vx += MULK( dirx, K_RIDER_S )-MULK( PS.rider_vx-mvx, K_RIDER_D )+gvx;
		PS.rider_vy += MULK( diry, K_RIDER_S )-MULK( PS.rider_vy-mvy, K_RIDER_D )+gvy;
		PS.rider_x += rsh( PS.rider_vx, 8 );
		PS.rider_y += rsh( PS.rider_vy, 8 );
	}

	// beallit: the body (no contacts).
	body->w += -MULK( rsh( cross_s, 2 ), K_TS )-MULK( rsh( cross_d, 8 ), K_TD );
	int32_t da1 = body->w;
	body->a = wrap( body->a+body->w );
	body->vx += -MULK( Dx[0]+Dx[1], K_20 )+gvx;
	body->vy += -MULK( Dy[0]+Dy[1], K_20 )+gvy;
	body->rx += rsh( body->vx, 8 );
	body->ry += rsh( body->vy, 8 );

	// The wheels:
	int32_t da[2];
	for( int k = 0; k < 2; k++ ) {
		Fx = Dx[k]+gvx;
		Fy = Dy[k]+gvy;
		Mk = M[k];
		da[k] = wheel( &PS.c[1+k], &PS.roll[k], &ev );
	}
	for( int k = 0; k < 2; k++ )
		PS.defl[k] += rsh( da[k]-da1, 8 );

	trig( body->a );
	head();

	if( PS.last_volt < 255 )
		PS.last_volt++;
	for( int k = 0; k < 2; k++ )
		if( PS.volt_t[k] < 255 )
			PS.volt_t[k]++;

	// The sounds (not in a quick step):
	if( !(input & PH_QUICK) ) {
		PS_friction = (uint16_t)(fric > 65535 ? 65535 : fric);
		int32_t om = MULK( iabs( PS.c[PS.turned ? 1 : 2].w ) >> 8, K_OMEGA );
		PS_wheel_omega = (uint16_t)(om > 65535 ? 65535 : om);
	}

	// vizsgalat: the head, leaving the level, the objects.
	if( contacts( PS.head_x, PS.head_y, R_HEAD_P, R_HEAD_SQ, 0 ) )
		return ev | PH_DEAD;
	if( Racs || body->rx < Kill[0] || body->rx >= Kill[1] || body->ry < Kill[2] || body->ry >= Kill[3] )
		return ev | PH_DEAD;
	int dead = 0, fin = 0;
	int again = 1;
	while( again ) {
		again = 0;
		for( int i = 0; i < 3; i++ ) {
			int o;
			if( i < 2 )
				o = sprite( PS.c[1+i].rx, PS.c[1+i].ry, OBJ_WHEEL_P, OBJ_WHEEL_SQ );
			else
				o = sprite( PS.head_x, PS.head_y, OBJ_HEAD_P, OBJ_HEAD_SQ );
			if( o < 0 )
				continue;
			// spritefeldolgoz, in the order the game takes them:
			switch( PS_obj[o].type ) {
				case 3:
					dead = 1;
					break;
				case 2:
					PS_obj[o].active = 0;
					again = 1;
					PS.apples++;
					if( PS_obj[o].gravity )
						PS.gravity = (uint8_t)(PS_obj[o].gravity-1);
					PS_eaten = (uint16_t)o;
					ev |= PH_EAT;
					break;
				case 1:
					if( PS.apples >= PS_apples_needed )
						fin = 1;
					break;
			}
		}
	}
	if( fin )
		return ev | PH_FINISH;
	if( dead )
		return ev | PH_DEAD;
	return ev;
}

// For the tests: the trigonometry of the last step (CS22, SN22, CS, SN of
// the direct page of the assembly).
void ps_trig_dump( uint8_t* out ) {
	uint32_t v[2] = { (uint32_t)Cs22, (uint32_t)Sn22 };
	for( int j = 0; j < 8; j++ )
		out[j] = (uint8_t)(v[j >> 2] >> 8*(j & 3));
	out[8] = (uint8_t)Cs;
	out[9] = (uint8_t)((uint16_t)Cs >> 8);
	out[10] = (uint8_t)Sn;
	out[11] = (uint8_t)((uint16_t)Sn >> 8);
}

// The state in the order of the direct page of the assembly:
void ps_dump( uint8_t* out ) {
	int n = 0;
#define PUT( v, size ) do { uint32_t u = (uint32_t)(v); for( int j = 0; j < size; j++ ) out[n++] = (uint8_t)(u >> 8*j); } while( 0 )
	for( int i = 0; i < 3; i++ ) {
		PUT( PS.c[i].rx, 4 ); PUT( PS.c[i].ry, 4 ); PUT( PS.c[i].vx, 4 );
		PUT( PS.c[i].vy, 4 ); PUT( PS.c[i].a, 4 ); PUT( PS.c[i].w, 4 );
	}
	PUT( PS.rider_x, 4 ); PUT( PS.rider_y, 4 ); PUT( PS.rider_vx, 4 ); PUT( PS.rider_vy, 4 );
	PUT( PS.head_x, 4 ); PUT( PS.head_y, 4 );
	PUT( PS.defl[0], 4 ); PUT( PS.defl[1], 4 );
	PUT( PS.volt_w[0], 4 ); PUT( PS.volt_w[1], 4 );
	for( int i = 0; i < 2; i++ ) {
		PUT( PS.roll[i].s, 4 ); PUT( PS.roll[i].nx, 2 ); PUT( PS.roll[i].ny, 2 );
		PUT( PS.roll[i].on, 1 ); PUT( 0, 1 );
	}
	PUT( PS.volt_on[0], 1 ); PUT( PS.volt_on[1], 1 );
	PUT( PS.volt_t[0], 1 ); PUT( PS.volt_t[1], 1 );
	PUT( PS.last_volt, 1 ); PUT( PS.turned, 1 ); PUT( PS.gravity, 1 );
	PUT( PS.brake_was, 1 ); PUT( PS.volt1, 1 ); PUT( PS.apples, 1 );
#undef PUT
}
