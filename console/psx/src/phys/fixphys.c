// Fixed point physics of the bike (see fixphys.h for the number formats).
// The functions follow LEPTET.CPP, BEALLIT.CPP, UTKOZES.CPP and UTKOZES2.CPP
// of the original game step by step; where the original builds a vector out
// of components along an orthonormal pair (rudegys and rudegysmer, kotoe and
// kotoemer), the vector itself is used, which is the same value without the
// square roots.
#include <math.h>
#include <string.h>
#include "fixphys.h"

#define Q40 40
#define ONE40 ((int64_t)1 << 40)
#define ONE30 ((int32_t)1 << 30)

// pi, 2pi and pi/2 (Q40) for the tables, which are in true radians (K_pi
// of the original, 3.141592, is only used where the original uses it):
#define TPI ((int64_t)3454217652358)
#define TTWOPI ((int64_t)6908435304716)
#define THALFPI ((int64_t)1727108826179)

// T_CEL of TOPOL.H:
#define FX_T_CEL 1

// ---------------------------------------------------------------------------
// Arithmetic

static inline int64_t mul( int32_t a, int32_t b ) { return (int64_t)a*b; }
static inline uint64_t mulu( uint32_t a, uint32_t b ) { return (uint64_t)a*b; }

// a*b >> s for |a| < 2^62, with two 32x32->64 products:
static inline int64_t m64( int64_t a, int32_t b, int s ) {
	int64_t hi = mul( (int32_t)(a >> 31), b );
	int64_t lo = mul( (int32_t)(a & 0x7fffffff), b );
	if( s >= 31 ) {
		// (a*b) >> 31, then the rest of the shift:
		int64_t t = hi+(lo >> 31);
		return s-31 < 63 ? t >> (s-31) : (t < 0 ? -1 : 0);
	}
	return (hi << (31-s))+(lo >> s);
}

static inline int64_t mulk( int64_t a, fx_kq k ) { return m64( a, k.m, k.s ); }

static inline int32_t sat32( int64_t x ) {
	if( x > 0x7fffffff )
		return 0x7fffffff;
	if( x < -0x7fffffff )
		return -0x7fffffff;
	return (int32_t)x;
}

static inline int64_t iabs64( int64_t x ) { return x < 0 ? -x : x; }

// A relative vector of the bike as 32-bit numbers: x * 2^-s m, Q30 while
// it is shorter than 2 m (always, except for a badly stretched bike), else
// with fewer fraction bits.
typedef struct { int32_t x, y; int s; } rel32;

static inline rel32 to_rel32( int64_t x, int64_t y ) {
	rel32 r;
	int sh = 10;
	uint64_t m = (uint64_t)(iabs64( x ) | iabs64( y ));
	while( (m >> sh) > 0x7fffffff )
		sh++;
	r.x = (int32_t)(x >> sh);
	r.y = (int32_t)(y >> sh);
	r.s = 40-sh;
	return r;
}

static int msb32( uint32_t w );

static int msb64( uint64_t x ) {
	uint32_t hi = (uint32_t)(x >> 32);
	return hi ? 32+msb32( hi ) : msb32( (uint32_t)x );
}

// m * 2^-s brought to 2^30 <= |m| < 2^31:
static fx_kq kq_norm( int64_t m, int s ) {
	fx_kq k;
	if( m == 0 ) {
		k.m = 0;
		k.s = 0;
		return k;
	}
	int neg = m < 0;
	uint64_t u = neg ? (uint64_t)-m : (uint64_t)m;
	int p = msb64( u );
	if( p > 30 ) {
		int sh = p-30;
		u = (u + ((uint64_t)1 << (sh-1))) >> sh;
		s -= sh;
		if( u >> 31 ) {
			u >>= 1;
			s--;
		}
	}
	else if( p < 30 ) {
		u <<= 30-p;
		s += 30-p;
	}
	k.m = neg ? -(int32_t)u : (int32_t)u;
	k.s = s;
	return k;
}

static fx_kq kq_mul( fx_kq a, fx_kq b ) {
	return kq_norm( mul( a.m, b.m ), a.s+b.s );
}

int64_t fx_d2q( double d, int q ) {
	uint64_t u;
	__builtin_memcpy( &u, &d, 8 );
	int e = (int)((u >> 52) & 0x7ff);
	if( e == 0 )
		return 0;
	uint64_t m = (u & (((uint64_t)1 << 52)-1)) | ((uint64_t)1 << 52);
	int sh = e-1075+q;
	uint64_t r;
	if( sh >= 0 )
		r = sh > 10 ? (uint64_t)0x7fffffffffffffff : m << sh;
	else if( sh < -60 )
		r = 0;
	else
		r = (m + ((uint64_t)1 << (-sh-1))) >> -sh;
	return (u >> 63) ? -(int64_t)r : (int64_t)r;
}

// The position of the highest set bit of a 32-bit number > 0:
static int msb32( uint32_t w ) {
	static const uint8_t top[256] = {
#define R2(n) n, n
#define R4(n) R2(n), R2(n)
#define R8(n) R4(n), R4(n)
#define R16(n) R8(n), R8(n)
#define R32(n) R16(n), R16(n)
#define R64(n) R32(n), R32(n)
#define R128(n) R64(n), R64(n)
		0, 0, R2(1), R4(2), R8(3), R16(4), R32(5), R64(6), R128(7)
#undef R2
#undef R4
#undef R8
#undef R16
#undef R32
#undef R64
#undef R128
	};
	if( w >> 16 )
		return w >> 24 ? 24+top[w >> 24] : 16+top[w >> 16];
	return w >> 8 ? 8+top[w >> 8] : top[w];
}

double fx_q2d( int64_t x, int q ) {
	if( x == 0 )
		return 0.0;
	uint64_t sign = 0;
	uint64_t u = (uint64_t)x;
	if( x < 0 ) {
		sign = (uint64_t)1 << 63;
		u = (uint64_t)-x;
	}
	uint32_t hi = (uint32_t)(u >> 32);
	int p = hi ? 32+msb32( hi ) : msb32( (uint32_t)u );
	uint64_t m;
	if( p <= 52 )
		m = u << (52-p);
	else {
		// Rounded to the nearest, ties to even:
		int sh = p-52;
		m = u >> sh;
		uint64_t rest = u & (((uint64_t)1 << sh)-1);
		uint64_t half = (uint64_t)1 << (sh-1);
		if( rest > half || (rest == half && (m & 1)) )
			m++;
		if( m >> 53 ) {
			m >>= 1;
			p++;
		}
	}
	uint64_t bits = sign | ((uint64_t)(p-q+1023) << 52) | (m & (((uint64_t)1 << 52)-1));
	double d;
	__builtin_memcpy( &d, &bits, 8 );
	return d;
}

fx_kq fx_kq_of( double d ) {
	fx_kq k = { 0, 0 };
	uint64_t u;
	__builtin_memcpy( &u, &d, 8 );
	int e = (int)((u >> 52) & 0x7ff);
	if( e == 0 )
		return k;
	uint64_t m = (u & (((uint64_t)1 << 52)-1)) | ((uint64_t)1 << 52);
	return kq_norm( (u >> 63) ? -(int64_t)(m >> 22) - (int64_t)((m >> 21) & 1)
							  : (int64_t)(m >> 22) + (int64_t)((m >> 21) & 1), 1053-e );
}

// ---------------------------------------------------------------------------
// Tables: sin and cos of k/256 rad (Q30, k = 0..403), 1/sqrt and 1/x of the
// top byte of a number (Q30), the first guess of the Newton iterations.

#define TRIG_N 404
static int32_t Sin_tab[TRIG_N], Cos_tab[TRIG_N];
static uint32_t Rsqrt_tab[192], Recip_tab[128];
static int Tables_done = 0;

void fx_init( void ) {
	if( Tables_done )
		return;
	for( int k = 0; k < TRIG_N; k++ ) {
		// Taylor series with + - * / only, which every IEEE 754 machine
		// rounds the same:
		double x = k/256.0, x2 = x*x;
		double s = 0, c = 0, ts = x, tc = 1.0;
		for( int n = 1; n <= 30; n += 2 ) {
			s += ts;
			c += tc;
			ts = -ts*x2/((n+1)*(n+2));
			tc = -tc*x2/(n*(n+1));
		}
		Sin_tab[k] = (int32_t)fx_d2q( s, 30 );
		Cos_tab[k] = (int32_t)fx_d2q( c, 30 );
	}
	for( int b = 64; b < 256; b++ ) {
		double y = 1.0/sqrt( (b+0.5)/256.0 );
		Rsqrt_tab[b-64] = (uint32_t)fx_d2q( y, 30 );
	}
	for( int b = 128; b < 256; b++ )
		Recip_tab[b-128] = (uint32_t)fx_d2q( 256.0/(b+0.5), 30 );
	Tables_done = 1;
}

// The engine sound of LEJATSZO.CPP belsoresz: 2 - exp( -min( |omega|*0.025,
// 30 ) ) of the wheel's angular velocity (Q40), as Q31. Its tables are
// made with exp (sound only, not the physics).
static uint32_t Exp_n[31], Exp_hi[256], Exp_lo[256];
static int Exp_done = 0;

int64_t fx_motorfrekvencia( int64_t omega ) {
	if( !Exp_done ) {
		for( int i = 0; i < 31; i++ )
			Exp_n[i] = (uint32_t)fx_d2q( exp( -(double)i ), 31 );
		for( int i = 0; i < 256; i++ ) {
			Exp_hi[i] = (uint32_t)fx_d2q( exp( -i/256.0 ), 31 );
			Exp_lo[i] = (uint32_t)fx_d2q( exp( -i/65536.0 ), 31 );
		}
		Exp_done = 1;
	}
	if( omega < 0 )
		omega = -omega;
	const int64_t limit = (int64_t)30 << 40;
	int64_t x = omega >= limit*40 ? limit : m64( omega, 1717986918, 36 );   // *0.025
	if( x > limit )
		x = limit;
	int n = (int)(x >> 40);
	uint32_t y = Exp_n[n];
	y = (uint32_t)(mulu( y, Exp_hi[(x >> 32) & 255] ) >> 31);
	y = (uint32_t)(mulu( y, Exp_lo[(x >> 24) & 255] ) >> 31);
	y = (uint32_t)(mulu( y, 0x80000000u-(uint32_t)((x & 0xffffff) >> 9) ) >> 31);
	return ((int64_t)1 << 32)-y;   // 2 - e^-x
}

// sin and cos (Q30) of an angle between -pi and pi (Q40):
static void trig( int64_t a, int32_t* pc, int32_t* ps ) {
	int sneg = a < 0;
	if( sneg )
		a = -a;
	int cneg = 0;
	if( a > THALFPI ) {
		a = TPI-a;
		cneg = 1;
		if( a < 0 )
			a = 0;
	}
	int i = (int)(a >> 32);
	int32_t d39 = (int32_t)((uint32_t)a >> 1);   // the rest, < 1/256 rad
	int32_t d2 = (int32_t)(mul( d39, d39 ) >> 48);                    // Q30
	int32_t cosd = ONE30-(d2 >> 1);
	int32_t d3 = (int32_t)(mul( d39, d2 ) >> 30);                     // Q39
	int32_t sind = d39-(int32_t)(mul( d3, 715827883 ) >> 32);         // Q39
	int32_t s0 = Sin_tab[i], c0 = Cos_tab[i];
	int64_t s = mul( s0, cosd )+(mul( c0, sind ) >> 9);
	int64_t c = mul( c0, cosd )-(mul( s0, sind ) >> 9);
	int32_t si = (int32_t)((s + ((int64_t)1 << 29)) >> 30);
	int32_t co = (int32_t)((c + ((int64_t)1 << 29)) >> 30);
	*ps = sneg ? -si : si;
	*pc = cneg ? -co : co;
}

// 1/sqrt( x ) of an integer x > 0 as a constant.
static fx_kq rsqrt_kq( uint64_t x ) {
	int z = (63-msb64( x )) & ~1;
	uint32_t m = (uint32_t)((x << z) >> 32);       // Q32, 1/4 .. 1
	uint32_t y = Rsqrt_tab[(m >> 24)-64];          // Q30
	for( int it = 0; it < 2; it++ ) {
		uint32_t a = (uint32_t)(mulu( m, y ) >> 32);
		uint32_t t = (uint32_t)(mulu( a, y ) >> 30);
		y = (uint32_t)(mulu( y, (3u << 30)-t ) >> 31);
	}
	if( y > 0x7fffffff )
		y = 0x7fffffff;
	return kq_norm( (int64_t)y, 62-z/2 );
}

// 1/x of an integer x > 0 as a constant.
static fx_kq recip_kq( uint64_t x ) {
	int z = 63-msb64( x );
	uint32_t m = (uint32_t)((x << z) >> 32);       // Q32, 1/2 .. 1
	uint32_t y = Recip_tab[(m >> 24)-128];         // Q30
	for( int it = 0; it < 2; it++ ) {
		uint32_t t = (uint32_t)(mulu( m, y ) >> 32);
		y = (uint32_t)(mulu( y, (2u << 30)-t ) >> 30);
	}
	if( y > 0x7fffffff )
		y = 0x7fffffff;
	return kq_norm( (int64_t)y, 94-z );
}

// The unit vector (Q30) and the length of d (Q40).
static void unit( fx_vec d, int32_t* pnx, int32_t* pny, int64_t* ph ) {
	uint64_t ax = (uint64_t)iabs64( d.x ), ay = (uint64_t)iabs64( d.y );
	uint64_t mx = ax > ay ? ax : ay;
	if( mx == 0 ) {
		*pnx = 0;
		*pny = ONE30;
		*ph = 0;
		return;
	}
	int k = msb64( mx )-29;
	int32_t dx, dy;
	if( k >= 0 ) {
		dx = (int32_t)(d.x >> k);
		dy = (int32_t)(d.y >> k);
	}
	else {
		dx = (int32_t)(d.x << -k);
		dy = (int32_t)(d.y << -k);
	}
	int64_t s2 = mul( dx, dx )+mul( dy, dy );     // < 2^61
	fx_kq r = rsqrt_kq( (uint64_t)s2 );
	*pnx = (int32_t)m64( (int64_t)dx, r.m, r.s-30 );
	*pny = (int32_t)m64( (int64_t)dy, r.m, r.s-30 );
	// sqrt( s2 ) with one Newton correction:
	int64_t h = mulk( s2, r );
	int64_t res = s2-h*h;
	h += m64( res, r.m, r.s+1 );
	*ph = k >= 0 ? h << k : h >> -k;
}

int64_t fx_wrap( int64_t a ) {
	while( a > TPI )
		a -= TTWOPI;
	while( a < -TPI )
		a += TTWOPI;
	return a;
}

// ---------------------------------------------------------------------------
// Constants

void fx_params( fx_param* p, const fx_input* in ) {
	memset( p, 0, sizeof( *p ) );
	p->kord2x = (int32_t)fx_d2q( in->kord2x, 30 );
	p->kord2y = (int32_t)fx_d2q( in->kord2y, 30 );
	p->kord4x = (int32_t)fx_d2q( in->kord4x, 30 );
	p->kord4y = (int32_t)fx_d2q( in->kord4y, 30 );
	p->kord5y = (int32_t)fx_d2q( in->kord5y, 30 );
	p->drsugar = fx_kq_of( in->drsugar );
	p->sr = fx_kq_of( in->sr );
	p->drsugar5 = fx_kq_of( in->drsugar*5.0 );
	p->sr3 = fx_kq_of( in->sr*3.0 );
	for( int i = 0; i < 3; i++ ) {
		p->gm[i] = fx_d2q( in->kor_m[i]*in->g, Q40 );
		p->inv_m[i] = fx_kq_of( 1.0/in->kor_m[i] );
		p->inv_theta[i] = fx_kq_of( 1.0/in->kor_theta[i] );
		p->sugar[i] = fx_d2q( in->kor_sugar[i], Q40 );
	}
	p->theta2 = fx_d2q( in->kor_theta[1], 56 );
	p->m2 = fx_kq_of( in->kor_m[1] );
	p->sugar2k = fx_kq_of( in->kor_sugar[1] );
	p->inv_sugar2 = fx_kq_of( 1.0/in->kor_sugar[1] );
	p->sugar2_62 = fx_d2q( in->kor_sugar[1]*in->kor_sugar[1], 62 );
	p->belso = fx_d2q( in->kor_sugar[1]-in->belsosav, Q40 );
	p->elszakad = fx_d2q( in->elszakad, Q40 );
	p->merge = fx_d2q( in->merge, Q40 );
	p->merge2 = fx_d2q( in->merge*in->merge, 60 );
	p->fejsugar = fx_d2q( in->fejsugar, Q40 );
	p->fejsugar2 = fx_d2q( in->fejsugar*in->fejsugar, 62 );
	p->objsugar = fx_d2q( in->objsugar, Q40 );
	p->ugroturelem = in->ugroturelem;
	p->pi = fx_d2q( in->pi, Q40 );
	p->twopi = fx_d2q( 2*in->pi, Q40 );
	// vezeto_hatarolas (BEALLIT.CPP):
	p->avn_x = (int32_t)fx_d2q( in->avn_x, 30 );
	p->avn_y = (int32_t)fx_d2q( in->avn_y, 30 );
	p->ar_x = fx_d2q( -0.35, Q40 );
	p->ar_y = fx_d2q( 0.13, Q40 );
	double felhat = 0.48, jobbhat = 0.26;
	p->felhat = fx_d2q( felhat, Q40 );
	p->balhat = fx_d2q( -0.5, Q40 );
	p->jobbhat = fx_d2q( jobbhat, Q40 );
	p->rxszorzo = fx_kq_of( (felhat/jobbhat)*(felhat/jobbhat) );
	double tavmax2 = felhat*felhat;
	p->tavmax2 = fx_d2q( tavmax2, 60 );
	p->tavmax = fx_kq_of( sqrt( tavmax2 ) );
	p->dt_m = 0;
	p->dt_s = -1;
}

static void set_dt( fx_param* p, double dt ) {
	fx_kq k = fx_kq_of( dt );
	if( k.m == p->dt_m && k.s == p->dt_s )
		return;
	p->dt_m = k.m;
	p->dt_s = k.s;
	p->dt = k;
	for( int i = 0; i < 3; i++ ) {
		p->dt_m1[i] = kq_mul( k, p->inv_m[i] );
		p->dt_theta[i] = kq_mul( k, p->inv_theta[i] );
	}
}

// ---------------------------------------------------------------------------
// Ground contacts (UTKOZES.CPP)

// A contact point t of a circle at r: d = r - t, and the unit vector n and
// the length h of d when fresh.
typedef struct {
	fx_vec d;
	int32_t nx, ny;
	int64_t h;
	int fresh;
} contact_t;

static void geom( contact_t* c ) {
	if( !c->fresh ) {
		unit( c->d, &c->nx, &c->ny, &c->h );
		c->fresh = 1;
	}
}

// A point contact (an end of a line) if |d| < sugar:
static int point_contact( fx_vec d, int64_t sugar, int64_t sugar2_62, contact_t* c ) {
	if( d.x >= sugar || d.x <= -sugar || d.y >= sugar || d.y <= -sugar )
		return 0;
	int32_t x = (int32_t)(d.x >> 9), y = (int32_t)(d.y >> 9);    // Q31
	if( mul( x, x )+mul( y, y ) >= sugar2_62 )
		return 0;
	c->d = d;
	c->fresh = 0;
	return 1;
}

// The margin of the rough products (2^-19 m):
#define ROUGH ((int64_t)1 << 21)

// gombszakasz: true if the circle at r touches line l, with its contact.
static int gombszakasz( const fx_line* l, fx_vec r, int64_t sugar, int64_t sugar2_62,
						contact_t* c ) {
	fx_vec rel = { r.x-l->p.x, r.y-l->p.y };
	int32_t cx = sat32( rel.x >> 18 ), cy = sat32( rel.y >> 18 );   // Q22
	// Where along the line, roughly, then exactly near the ends:
	int64_t pos = (mul( cx, l->ux )+mul( cy, l->uy )) >> 12;
	int where;   // -1 before the start, 1 after the end, 0 along it
	if( pos < -ROUGH )
		where = -1;
	else if( pos > l->len+ROUGH )
		where = 1;
	else if( pos > ROUGH && pos < l->len-ROUGH )
		where = 0;
	else {
		pos = m64( rel.x, l->ux, 30 )+m64( rel.y, l->uy, 30 )+
			  ((mul( cx, l->lx )+mul( cy, l->ly )) >> 43);
		where = pos < 0 ? -1 : pos > l->len ? 1 : 0;
	}
	if( where < 0 )
		return point_contact( rel, sugar, sugar2_62, c );
	if( where > 0 ) {
		fx_vec d = { r.x-l->e.x, r.y-l->e.y };
		return point_contact( d, sugar, sugar2_62, c );
	}
	// The distance from the line along its normal n = (-uy, ux):
	int64_t tav = (mul( cx, -l->uy )+mul( cy, l->ux )) >> 12;
	if( tav < -sugar-ROUGH || tav > sugar+ROUGH )
		return 0;
	tav = m64( rel.x, -l->uy, 30 )+m64( rel.y, l->ux, 30 )+
		  ((mul( cx, -l->ly )+mul( cy, l->lx )) >> 43);
	if( tav < -sugar || tav > sugar )
		return 0;
	int32_t t20 = (int32_t)(tav >> 20);
	c->d.x = m64( tav, -l->uy, 30 )+(mul( t20, -l->ly ) >> 41);
	c->d.y = m64( tav, l->ux, 30 )+(mul( t20, l->lx ) >> 41);
	if( tav >= 0 ) {
		c->nx = -l->uy;
		c->ny = l->ux;
		c->h = tav;
	}
	else {
		c->nx = l->uy;
		c->ny = -l->ux;
		c->h = -tav;
	}
	c->fresh = 1;
	return 1;
}

// talppontkereses with szakaszok::felsorolasreset: the contacts (0-2) of a
// circle; with ct NULL only whether there is one.
static int talppontkereses( const fx_level* lev, const fx_param* p, fx_vec r, int64_t sugar,
							int64_t sugar2_62, contact_t* ct, int* pracs ) {
	int64_t qx = r.x-lev->origo.x, qy = r.y-lev->origo.y;
	int cellx = qx > 0 ? (int)(qx >> 40) : 0;
	int celly = qy > 0 ? (int)(qy >> 40) : 0;
	if( cellx > lev->xdim ) {
		*pracs = 1;
		cellx = lev->xdim;
	}
	if( cellx == lev->xdim )
		cellx = lev->xdim-1;
	if( celly > lev->ydim ) {
		*pracs = 1;
		celly = lev->ydim;
	}
	if( celly == lev->ydim )
		celly = lev->ydim-1;
	const uint16_t* sor = lev->list+lev->row[celly];
	const uint16_t* cell = lev->cell+(lev->xdim+1)*celly+cellx;
	const uint16_t* it = sor+cell[0];
	const uint16_t* end = sor+cell[1];
	int n = 0;
	contact_t c;
	for( ; it < end; it++ ) {
		if( !gombszakasz( &lev->lines[*it], r, sugar, sugar2_62, &c ) )
			continue;
		if( !ct )
			return 1;
		if( n == 1 ) {
			// Two points nearer than Talppontegybeolvadasitav are one:
			int64_t dx = c.d.x-ct[0].d.x, dy = c.d.y-ct[0].d.y;
			if( dx < p->merge && dx > -p->merge && dy < p->merge && dy > -p->merge ) {
				int32_t x = (int32_t)(dx >> 10), y = (int32_t)(dy >> 10);
				if( mul( x, x )+mul( y, y ) < p->merge2 ) {
					ct[0].d.x = (ct[0].d.x+c.d.x) >> 1;
					ct[0].d.y = (ct[0].d.y+c.d.y) >> 1;
					ct[0].fresh = 0;
					continue;
				}
			}
			ct[1] = c;
			return 2;
		}
		ct[0] = c;
		n = 1;
	}
	return n;
}

// ---------------------------------------------------------------------------
// beallit (BEALLIT.CPP)

// n90*w of a vector w with n90 = rot90( n ):
static inline int64_t dot90( int32_t nx, int32_t ny, fx_vec w ) {
	return m64( w.x, -ny, 30 )+m64( w.y, nx, 30 );
}

static inline int64_t dotn( int32_t nx, int32_t ny, fx_vec w ) {
	return m64( w.x, nx, 30 )+m64( w.y, ny, 30 );
}

// helyigazitas: pushes the wheel out to sugar - Belsosav from contact i.
static void helyigazitas( fx_kor* k, const fx_param* p, contact_t* ct, int n, int i ) {
	geom( &ct[i] );
	if( ct[i].h >= p->belso )
		return;
	int64_t push = p->belso-ct[i].h;
	int64_t dx = m64( push, ct[i].nx, 30 ), dy = m64( push, ct[i].ny, 30 );
	k->r.x += dx;
	k->r.y += dy;
	for( int j = 0; j < n; j++ ) {
		ct[j].d.x += dx;
		ct[j].d.y += dy;
		if( j == i )
			ct[j].h = p->belso;
		else
			ct[j].fresh = 0;
	}
}

static int same_side( int64_t a, int64_t b ) {
	return !((a < 0 && b > 0) || (a > 0 && b < 0));
}

// biztostalppont_uj (m is the angular velocity) and biztostalppont_regi
// (m is the torque, w the force): true if t1 stays a contact turning around
// t2 (of c2).
static int biztostalppont( contact_t* c1, contact_t* c2, int64_t m, fx_vec w ) {
	geom( c2 );
	int32_t h30 = sat32( c2->h >> 10 );
	int64_t mtm = m+m64( dot90( c2->nx, c2->ny, w ), h30, 30 );
	fx_vec t12 = { c2->d.x-c1->d.x, c2->d.y-c1->d.y };
	return same_side( dot90( c2->nx, c2->ny, t12 ), mtm );
}

// talppontigazitas: false if t is not a contact; else takes the velocity
// into the ground away (and the bump sound).
static int talppontigazitas( fx_bike* b, fx_kor* k, const fx_param* p, contact_t* c, fx_vec F ) {
	geom( c );
	int64_t nv = dotn( c->nx, c->ny, k->v );
	if( nv > -p->elszakad && dotn( c->nx, c->ny, F ) > 0 )
		return 0;
	k->v.x -= m64( nv, c->nx, 30 );
	k->v.y -= m64( nv, c->ny, 30 );
	int64_t ero = iabs64( nv );
	// Utodeshatar = 1.5:
	if( ero > (ONE40 + (ONE40 >> 1)) && b->nbump < 8 )
		b->bump[b->nbump++] = ero;
	return 1;
}

static void szabad( fx_bike* b, int ki, const fx_param* p, fx_vec F, int64_t M ) {
	fx_kor* k = &b->k[ki];
	k->w += mulk( M, p->dt_theta[ki] );
	int64_t da = mulk( k->w, p->dt );
	k->a += da;
	if( ki == 0 ) {
		b->aw = fx_wrap( b->aw+da );
	}
	k->v.x += mulk( F.x, p->dt_m1[ki] );
	k->v.y += mulk( F.y, p->dt_m1[ki] );
	k->r.x += mulk( k->v.x, p->dt );
	k->r.y += mulk( k->v.y, p->dt );
}

static void beallit_kerek( fx_bike* b, int ki, const fx_level* lev, const fx_param* p,
						   fx_vec F, int64_t M ) {
	fx_kor* k = &b->k[ki];
	contact_t ct[2];
	int n = talppontkereses( lev, p, k->r, p->sugar[ki], p->sugar2_62, ct, &b->racs );
	if( n > 0 )
		helyigazitas( k, p, ct, n, 0 );
	if( n > 1 )
		helyigazitas( k, p, ct, n, 1 );

	if( n == 2 ) {
		int32_t vx = sat32( k->v.x >> 20 ), vy = sat32( k->v.y >> 20 );
		int64_t v2 = mul( vx, vx )+mul( vy, vy );     // Q40
		if( v2 > ONE40 ) {
			// The new way: whether the velocity turns it out of the contact:
			if( !biztostalppont( &ct[0], &ct[1], k->w, k->v ) ) {
				n = 1;
				ct[0] = ct[1];
			}
			else if( !biztostalppont( &ct[1], &ct[0], k->w, k->v ) )
				n = 1;
		}
		else if( v2 < ONE40 ) {
			// The old way, with the forces, only at low speed:
			if( !biztostalppont( &ct[0], &ct[1], M, F ) ) {
				n = 1;
				ct[0] = ct[1];
			}
			else if( !biztostalppont( &ct[1], &ct[0], M, F ) )
				n = 1;
		}
	}

	if( n == 2 ) {
		if( !talppontigazitas( b, k, p, &ct[1], F ) )
			n = 1;
	}
	if( n >= 1 ) {
		if( !talppontigazitas( b, k, p, &ct[0], F ) ) {
			if( n == 2 ) {
				n = 1;
				ct[0] = ct[1];
			}
			else
				n = 0;
		}
	}

	if( n == 0 ) {
		szabad( b, ki, p, F, M );
		return;
	}
	if( n == 2 ) {
		// The wheel is held:
		k->v.x = k->v.y = 0;
		k->w = 0;
		return;
	}
	// Turns around one contact:
	contact_t* c = &ct[0];
	geom( c );
	k->w = mulk( dot90( c->nx, c->ny, k->v ), p->inv_sugar2 );
	M += mulk( dot90( c->nx, c->ny, F ), p->sugar2k );
	int32_t h30 = sat32( c->h >> 10 );
	int64_t ts = p->theta2+mulk( mul( h30, h30 ) >> 4, p->m2 );   // Q56
	fx_kq rk = recip_kq( (uint64_t)ts );
	rk.s -= 56;
	k->w += mulk( M, kq_mul( rk, p->dt ) );
	k->a += mulk( k->w, p->dt );
	int64_t sw = mulk( k->w, p->sugar2k );
	k->v.x = m64( sw, -c->ny, 30 );
	k->v.y = m64( sw, c->nx, 30 );
	k->r.x += mulk( k->v.x, p->dt );
	k->r.y += mulk( k->v.y, p->dt );
}

// vezeto_hatarolas and beallitvezeto (the rider).
static void beallitvezeto( fx_bike* b, const fx_param* p, int gx, int gy,
						   int32_t c, int32_t s, int hatra ) {
	fx_kor* k1 = &b->k[0];
	fx_vec d = { b->vr.x-k1->r.x, b->vr.y-k1->r.y };
	int64_t x = m64( d.x, c, 30 )+m64( d.y, s, 30 );
	int64_t y = m64( d.x, -s, 30 )+m64( d.y, c, 30 );
	if( hatra )
		x = -x;
	int changed = 0;
	// The seat holds it:
	int64_t lelogas = m64( x-p->ar_x, p->avn_x, 30 )+m64( y-p->ar_y, p->avn_y, 30 );
	if( lelogas < 0 ) {
		x -= m64( lelogas, p->avn_x, 30 );
		y -= m64( lelogas, p->avn_y, 30 );
		changed = 1;
	}
	if( y > p->felhat ) {
		y = p->felhat;
		changed = 1;
	}
	if( x < p->balhat ) {
		x = p->balhat;
		changed = 1;
	}
	if( x > p->jobbhat ) {
		x = p->jobbhat;
		changed = 1;
	}
	if( x > 0 && y > 0 ) {
		int32_t x30 = (int32_t)(x >> 10), y30 = (int32_t)(y >> 10);
		int64_t t2 = mulk( mul( x30, x30 ), p->rxszorzo )+mul( y30, y30 );   // Q60
		if( t2 > p->tavmax2 ) {
			fx_kq r = rsqrt_kq( (uint64_t)t2 );
			r.s -= 30;
			fx_kq sz = kq_mul( p->tavmax, r );
			x = mulk( x, sz );
			y = mulk( y, sz );
			changed = 1;
		}
	}
	if( changed ) {
		if( hatra ) {
			b->vr.x = k1->r.x+m64( y, -s, 30 )-m64( x, c, 30 );
			b->vr.y = k1->r.y+m64( y, c, 30 )-m64( x, s, 30 );
		}
		else {
			b->vr.x = k1->r.x+m64( x, c, 30 )+m64( y, -s, 30 );
			b->vr.y = k1->r.y+m64( x, s, 30 )+m64( y, c, 30 );
		}
	}

	// The spring to the seat:
	fx_vec rug = { k1->r.x+((mul( -s, p->kord5y )+(1 << 19)) >> 20)-b->vr.x,
				   k1->r.y+((mul( c, p->kord5y )+(1 << 19)) >> 20)-b->vr.y };
	fx_vec F = { mulk( rug.x, p->drsugar5 ), mulk( rug.y, p->drsugar5 ) };
	// Friction against the body's velocity at the rider:
	rel32 t = to_rel32( b->vr.x-k1->r.x, b->vr.y-k1->r.y );
	fx_vec relv = { b->vv.x-(m64( k1->w, -t.y, t.s )+k1->v.x),
					b->vv.y-(m64( k1->w, t.x, t.s )+k1->v.y) };
	F.x -= mulk( relv.x, p->sr3 );
	F.y -= mulk( relv.y, p->sr3 );
	F.x += gx*p->gm[0];
	F.y += gy*p->gm[0];
	b->vv.x += mulk( F.x, p->dt_m1[0] );
	b->vv.y += mulk( F.y, p->dt_m1[0] );
	b->vr.x += mulk( b->vv.x, p->dt );
	b->vr.y += mulk( b->vv.y, p->dt );
}

// ---------------------------------------------------------------------------
// leptet (LEPTET.CPP)

// erokszamitasa: the forces of a wheel and the body on each other.
static void erokszamitasa( fx_bike* b, const fx_param* p, int ki, int32_t kx, int32_t ky,
						   int32_t c, int32_t s, fx_vec* pFk, fx_vec* pFt, int64_t* pMt,
						   int64_t Mk ) {
	fx_kor* k1 = &b->k[0];
	fx_kor* k = &b->k[ki];
	// gumis = i1*kordx + j1*kordy:
	int64_t gx = mul( c, kx )-mul( s, ky ), gy = mul( s, kx )+mul( c, ky );   // Q60
	fx_vec gumis = { (gx + (1 << 19)) >> 20, (gy + (1 << 19)) >> 20 };
	int32_t g30x = (int32_t)((gx + (1 << 29)) >> 30), g30y = (int32_t)((gy + (1 << 29)) >> 30);
	fx_vec gumi = { k1->r.x+gumis.x-k->r.x, k1->r.y+gumis.y-k->r.y };
	const int64_t eps = 109951163;   // 0.0001 (Q40)
	fx_vec Fk = { 0, 0 }, Ft = { 0, 0 };
	int64_t Mt = 0;
	if( gumi.x < -eps || gumi.x > eps || gumi.y < -eps || gumi.y > eps ) {
		// The spring: Drsugar*gumi on the wheel, its torque on the body:
		Fk.x = mulk( gumi.x, p->drsugar );
		Fk.y = mulk( gumi.y, p->drsugar );
		Ft.x = -Fk.x;
		Ft.y = -Fk.y;
		int64_t cross = m64( gumi.y, g30x, 30 )-m64( gumi.x, g30y, 30 );
		Mt = -mulk( cross, p->drsugar );
	}
	// The damping: Sr times the velocity of the body at the wheel against
	// the wheel's:
	rel32 ko = to_rel32( k->r.x-k1->r.x, k->r.y-k1->r.y );
	fx_vec kv = { m64( k1->w, -ko.y, ko.s )+k1->v.x-k->v.x,
				  m64( k1->w, ko.x, ko.s )+k1->v.y-k->v.y };
	fx_vec Fs = { mulk( kv.x, p->sr ), mulk( kv.y, p->sr ) };
	// The torque of the wheel pushes the body: rot90( koto )*Mk/|koto|^2:
	fx_vec Ftn = { 0, 0 };
	if( Mk != 0 ) {
		int64_t l2 = mul( ko.x, ko.x )+mul( ko.y, ko.y );   // Q(2s)
		if( l2 > 0 ) {
			fx_kq rl = recip_kq( (uint64_t)l2 );
			rl.s -= 2*ko.s;
			int64_t q = mulk( Mk, rl );
			Ftn.x = m64( q, -ko.y, ko.s );
			Ftn.y = m64( q, ko.x, ko.s );
		}
	}
	Fk.x += Fs.x-Ftn.x;
	Fk.y += Fs.y-Ftn.y;
	Mt -= mulk( m64( kv.x, -ko.y, ko.s )+m64( kv.y, ko.x, ko.s ), p->sr );
	Ft.x += -Fs.x+Ftn.x;
	Ft.y += -Fs.y+Ftn.y;
	*pFk = Fk;
	*pFt = Ft;
	*pMt = Mt;

	// surlodasverseny: the friction sound, along joirany = (sin, -cos):
	int64_t fg = m64( gumi.x, s, 30 )-m64( gumi.y, c, 30 );
	int64_t sb = m64( kv.x, s, 30 )-m64( kv.y, c, 30 );
	if( fg > 0 && sb > 0 ) {
		int64_t e = mul( sat32( fg >> 20 ), sat32( sb >> 20 ) );
		if( e > b->maxsurl )
			b->maxsurl = e;
	}
}

static void szogigazit( const fx_param* p, int64_t* pa ) {
	if( *pa < -p->pi )
		*pa += p->twopi;
	if( *pa > p->pi )
		*pa -= p->twopi;
}

// szamitfejr: the head from the rider and the body angle.
void fx_szamitfejr( fx_bike* b, int hatra_f ) {
	int32_t c, s;
	trig( b->aw, &c, &s );
	const int32_t k09 = 96636764, k63 = 676457349;   // 0.09, 0.63 (Q30)
	int64_t ix = mul( c, k09 ), iy = mul( s, k09 );
	int64_t jx = mul( -s, k63 ), jy = mul( c, k63 );
	if( !hatra_f ) {
		ix = -ix;
		iy = -iy;
	}
	b->fej.x = b->vr.x+((ix+jx+(1 << 19)) >> 20);
	b->fej.y = b->vr.y+((iy+jy+(1 << 19)) >> 20);
}

void fx_leptet( fx_bike* b, const fx_level* lev, fx_param* p, double most, double dt,
				int gaz, int fek, int ugrik1, int ugrik2, int hatra_f, int gravirany ) {
	set_dt( p, dt );
	b->maxsurl = 0;
	b->nbump = 0;
	fx_kor* k1 = &b->k[0];
	fx_kor* k2 = &b->k[1];
	fx_kor* k4 = &b->k[2];

	int32_t c, s;
	trig( b->aw, &c, &s );

	// Brake, gas:
	if( !b->voltfek && fek ) {
		b->dfek2 = k2->a-k1->a;
		b->dfek4 = k4->a-k1->a;
	}
	b->voltfek = fek;
	int64_t Mk2 = 0, Mk4 = 0;
	if( gaz ) {
		const int64_t tulporges = 110*ONE40, gaznyomatek = 600*ONE40;
		if( hatra_f ) {
			if( k2->w > -tulporges )
				Mk2 = -gaznyomatek;
		}
		else {
			if( k4->w < tulporges )
				Mk4 = gaznyomatek;
		}
	}
	if( fek ) {
		const fx_kq fekero = { 1000 << 20, 20 }, surlodas = { 100 << 24, 24 };
		int64_t dalfa = k2->a-(k1->a+b->dfek2);
		int64_t domega = k2->w-k1->w;
		Mk2 = -mulk( dalfa, fekero )-mulk( domega, surlodas );
		dalfa = k4->a-(k1->a+b->dfek4);
		domega = k4->w-k1->w;
		Mk4 = -mulk( dalfa, fekero )-mulk( domega, surlodas );
	}
	else {
		szogigazit( p, &k2->a );
		szogigazit( p, &k4->a );
	}

	fx_vec Fk2, Ft2, Fk4, Ft4;
	int64_t Mt2, Mt4;
	erokszamitasa( b, p, 1, p->kord2x, p->kord2y, c, s, &Fk2, &Ft2, &Mt2, Mk2 );
	erokszamitasa( b, p, 2, p->kord4x, p->kord4y, c, s, &Fk4, &Ft4, &Mt4, Mk4 );

	// Volts (Loket = 12, Omegavalt = 3):
	const int64_t loket = 12*ONE40, omegavalt = 3*ONE40;
	int64_t oldomega = k1->w;
	if( b->ugrasban1 && (ugrik1 || ugrik2 || most > b->ugras1kezd+p->ugroturelem*0.25) ) {
		k1->w += loket;
		if( k1->w > b->kezdoomega1 )
			k1->w = b->kezdoomega1;
		if( k1->w > 0 ) {
			k1->w -= omegavalt;
			if( k1->w < 0 )
				k1->w = 0;
		}
		b->ugrasban1 = 0;
		b->kezdoomega1 = -ONE40;
		b->ugras1kezd = -1.0;
	}
	if( b->ugrasban2 && (ugrik1 || ugrik2 || most > b->ugras2kezd+p->ugroturelem*0.25) ) {
		k1->w -= loket;
		if( k1->w < b->kezdoomega2 )
			k1->w = b->kezdoomega2;
		if( k1->w < 0 ) {
			k1->w += omegavalt;
			if( k1->w > 0 )
				k1->w = 0;
		}
		b->ugrasban2 = 0;
		b->kezdoomega2 = -ONE40;
		b->ugras2kezd = -1.0;
	}
	if( ugrik1 ) {
		b->ugrasban1 = 1;
		b->kezdoomega1 = k1->w;
		b->ugras1kezd = most;
		k1->w -= loket;
	}
	if( ugrik2 ) {
		b->ugrasban2 = 1;
		b->kezdoomega2 = k1->w;
		b->ugras2kezd = most;
		k1->w += loket;
	}
	if( ugrik1 || ugrik2 ) {
		// The rider turns separately:
		int64_t domega = k1->w-oldomega;
		rel32 t = to_rel32( b->vr.x-k1->r.x, b->vr.y-k1->r.y );
		b->vv.x += m64( domega, -t.y, t.s );
		b->vv.y += m64( domega, t.x, t.s );
	}

	int gx = 0, gy = -1;
	switch( gravirany ) {
		case 0: gy = 1; break;
		case 2: gx = -1; gy = 0; break;
		case 3: gx = 1; gy = 0; break;
	}
	beallitvezeto( b, p, gx, gy, c, s, hatra_f );
	fx_vec F = { Ft2.x+Ft4.x+gx*p->gm[0], Ft2.y+Ft4.y+gy*p->gm[0] };
	szabad( b, 0, p, F, Mt2+Mt4 );
	F.x = Fk2.x+gx*p->gm[1];
	F.y = Fk2.y+gy*p->gm[1];
	beallit_kerek( b, 1, lev, p, F, Mk2 );
	F.x = Fk4.x+gx*p->gm[2];
	F.y = Fk4.y+gy*p->gm[2];
	beallit_kerek( b, 2, lev, p, F, Mk4 );

	fx_szamitfejr( b, hatra_f );
}

// ---------------------------------------------------------------------------
// vizsgalat (LEPTET.CPP, UTKOZES2.CPP)

int fx_fejutkozik( fx_bike* b, const fx_level* lev, const fx_param* p ) {
	return talppontkereses( lev, p, b->fej, p->fejsugar, p->fejsugar2, NULL, &b->racs );
}

int fx_utkozikesprite( const fx_level* lev, const fx_param* p, fx_vec r, int64_t sugar,
					   int skipcel ) {
	int64_t maxtav = sugar+p->objsugar;
	int32_t m31 = (int32_t)(maxtav >> 9);
	int64_t max2 = mul( m31, m31 );
	for( int i = 0; i < lev->nobjs; i++ ) {
		const fx_obj* o = &lev->objs[i];
		if( !*o->aktiv )
			continue;
		if( skipcel && o->tipus == FX_T_CEL )
			continue;
		int64_t dx = r.x-o->r.x, dy = r.y-o->r.y;
		if( dx >= maxtav || dx <= -maxtav || dy >= maxtav || dy <= -maxtav )
			continue;
		int32_t x = (int32_t)(dx >> 9), y = (int32_t)(dy >> 9);
		if( mul( x, x )+mul( y, y ) < max2 )
			return i;
	}
	return -1;
}

int fx_kilogna( const fx_level* lev, fx_vec r ) {
	return r.x < lev->kill_x1 || r.x >= lev->kill_x2 ||
		   r.y < lev->kill_y1 || r.y >= lev->kill_y2;
}
