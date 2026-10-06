#include "refphys.h"
#include <math.h>
#include <string.h>

static rvec V( double x, double y ) { rvec r = { x, y }; return r; }
static rvec add( rvec a, rvec b ) { return V( a.x+b.x, a.y+b.y ); }
static rvec sub( rvec a, rvec b ) { return V( a.x-b.x, a.y-b.y ); }
static rvec mul( rvec a, double s ) { return V( a.x*s, a.y*s ); }
static double dot( rvec a, rvec b ) { return a.x*b.x + a.y*b.y; }
static double len( rvec a ) { return sqrt( dot( a, a ) ); }
static rvec rot90( rvec a ) { return V( -a.y, a.x ); }

static const double K_spring = 10000.0, K_friction = 1000.0, G = 10.0;
static const double Kord[2][2] = { { -0.85, -0.6 }, { 0.85, -0.6 } };
static const double Kord5y = 0.44;
static const double Head_r = 0.238;

void ref_init( rbike* b, double sx, double sy ) {
	memset( b, 0, sizeof( *b ) );
	b->gravity = 1;
	b->body.r_ = 0.3; b->body.m = 200; b->body.theta = 200*0.55*0.55;
	for( int k = 0; k < 2; k++ ) {
		b->wheel[k].r_ = 0.4; b->wheel[k].m = 10; b->wheel[k].theta = 0.32;
	}
	// The start object is where the left wheel (kor2) stands:
	b->body.r = V( sx+0.85, sy+0.6 );
	b->wheel[0].r = V( sx, sy );
	b->wheel[1].r = V( sx+1.7, sy );
	b->rider_r = V( sx+0.85, sy+1.04 );
	b->volt_start[0] = b->volt_start[1] = -1;
	b->volt_omega[0] = b->volt_omega[1] = -1;
}

static void normangle( double* a ) {
	if( *a < -M_PI ) *a += 2*M_PI;
	if( *a > M_PI ) *a -= 2*M_PI;
}

static void forces( rbike* b, int k, rvec i1, rvec j1, rvec* Fw, rvec* Fb,
					double* Mb, double Mw ) {
	rcircle* w = &b->wheel[k];
	rvec gumis = add( mul( i1, Kord[k][0] ), mul( j1, Kord[k][1] ) );
	rvec gumi = sub( add( gumis, b->body.r ), w->r );
	*Fw = V( 0, 0 ); *Fb = V( 0, 0 ); *Mb = 0;
	if( fabs( gumi.x ) > 0.0001 || fabs( gumi.y ) > 0.0001 ) {
		double rl = len( gumis );
		rvec u = mul( gumis, 1.0/rl );
		rvec un = rot90( u );
		double Fs = dot( gumi, u )*K_spring, Ft = dot( gumi, un )*K_spring;
		*Fw = add( mul( u, Fs ), mul( un, Ft ) );
		*Fb = mul( *Fw, -1 );
		*Mb = -Ft*rl;
	}
	rvec koto = sub( w->r, b->body.r );
	double kl = len( koto );
	rvec ke = mul( koto, 1.0/kl );
	rvec kn = rot90( koto ), ken = rot90( ke );
	rvec relv = sub( add( mul( kn, b->body.omega ), b->body.v ), w->v );
	double vlong = dot( relv, ke ), vtang = dot( relv, ken );
	rvec Fl = mul( ke, vlong*K_friction ), Ft = mul( ken, vtang*K_friction );
	rvec Fn = mul( ken, Mw/kl );
	*Fw = sub( add( add( *Fw, Fl ), Ft ), Fn );
	*Mb += -dot( Ft, kn );
	*Fb = add( sub( sub( *Fb, Fl ), Ft ), Fn );
}

// gombszakasz of UTKOZES.CPP:
static int touch( rvec r, double rad, const rseg* s, rvec* t ) {
	double l = len( s->v );
	rvec e = mul( s->v, 1.0/l );
	rvec rel = sub( r, s->r );
	double pos = dot( rel, e );
	if( pos < 0 ) {
		if( len( rel ) < rad ) { *t = s->r; return 1; }
		return 0;
	}
	if( pos > l ) {
		rvec end = add( s->r, s->v );
		if( len( sub( r, end ) ) < rad ) { *t = end; return 1; }
		return 0;
	}
	double d = dot( rel, rot90( e ) );
	if( d < -rad || d > rad )
		return 0;
	*t = add( s->r, mul( e, pos ) );
	return 1;
}

static int contacts( rvec r, double rad, const rseg* segs, int n, rvec* t1, rvec* t2 ) {
	int c = 0;
	for( int i = 0; i < n; i++ ) {
		rvec t;
		if( !touch( r, rad, &segs[i], &t ) )
			continue;
		if( c == 0 ) { *t1 = t; c = 1; }
		else if( c == 1 ) {
			if( len( sub( *t1, t ) ) < 0.1 ) *t1 = mul( add( *t1, t ), 0.5 );
			else { *t2 = t; c = 2; }
		}
	}
	return c;
}

static void pushout( rcircle* k, rvec t ) {
	double l = len( sub( k->r, t ) );
	rvec n = mul( sub( k->r, t ), 1.0/l );
	if( l < k->r_-0.005 )
		k->r = add( k->r, mul( n, k->r_-0.005-l ) );
}

static int contact_ok( rcircle* k, rvec t, rvec F ) {
	double l = len( sub( k->r, t ) );
	rvec n = mul( sub( k->r, t ), 1.0/l );
	if( dot( n, k->v ) > -0.01 && dot( n, F ) > 0 )
		return 0;
	k->v = sub( k->v, mul( n, dot( n, k->v ) ) );
	return 1;
}

static int sure_old( rvec t1, rvec t2, rcircle* k, rvec F, double M ) {
	double l = len( sub( k->r, t2 ) );
	rvec n = mul( sub( k->r, t2 ), 1.0/l );
	rvec n90 = rot90( n );
	double Mtm = M + l*dot( n90, F );
	return dot( sub( t1, t2 ), n90 )*Mtm >= 0;
}

static int sure_new( rvec t1, rvec t2, rcircle* k ) {
	double l = len( sub( k->r, t2 ) );
	rvec n = mul( sub( k->r, t2 ), 1.0/l );
	rvec n90 = rot90( n );
	double Mtm = k->omega + l*dot( n90, k->v );
	return dot( sub( t1, t2 ), n90 )*Mtm >= 0;
}

static void integrate( rcircle* k, rvec F, double M, double dt, int collide,
					   const rseg* segs, int n ) {
	int c = 0;
	rvec t1 = { 0, 0 }, t2 = { 0, 0 };
	if( collide )
		c = contacts( k->r, k->r_, segs, n, &t1, &t2 );
	if( c > 0 ) pushout( k, t1 );
	if( c > 1 ) pushout( k, t2 );
	if( c == 2 && len( k->v ) > 1.0 ) {
		if( !sure_new( t1, t2, k ) ) { c = 1; t1 = t2; }
		else if( !sure_new( t2, t1, k ) ) c = 1;
	}
	if( c == 2 && len( k->v ) < 1.0 ) {
		if( !sure_old( t1, t2, k, F, M ) ) { c = 1; t1 = t2; }
		else if( !sure_old( t2, t1, k, F, M ) ) c = 1;
	}
	if( c == 2 && !contact_ok( k, t2, F ) )
		c = 1;
	if( c >= 1 && !contact_ok( k, t1, F ) ) {
		if( c == 2 ) { c = 1; t1 = t2; }
		else c = 0;
	}
	if( c == 0 ) {
		k->omega += M/k->theta*dt;
		k->alfa += k->omega*dt;
		k->v = add( k->v, mul( F, dt/k->m ) );
		k->r = add( k->r, mul( k->v, dt ) );
		return;
	}
	if( c == 2 ) {
		k->v = V( 0, 0 );
		k->omega = 0;
		return;
	}
	double l = len( sub( k->r, t1 ) );
	rvec nn = mul( sub( k->r, t1 ), 1.0/l );
	rvec n90 = rot90( nn );
	k->omega = dot( k->v, n90 )/k->r_;
	M += dot( F, n90 )*k->r_;
	double th = k->theta + k->m*l*l;
	k->omega += M/th*dt;
	k->alfa += k->omega*dt;
	k->v = mul( n90, k->omega*k->r_ );
	k->r = add( k->r, mul( k->v, dt ) );
}

static void rider_limit( rbike* b, rvec i, rvec j ) {
	double x, y;
	rvec d = sub( b->rider_r, b->body.r );
	x = b->turned ? -dot( i, d ) : dot( i, d );
	y = dot( j, d );
	rvec ar = V( -0.35, 0.13 ), av = V( 0.14+0.35, 0.36-0.13 );
	rvec avn = rot90( av );
	avn = mul( avn, 1.0/len( avn ) );
	rvec r = V( x, y );
	double under = dot( sub( r, ar ), avn );
	if( under < 0 )
		r = sub( r, mul( avn, under ) );
	const double top = 0.48, right = 0.26;
	if( r.y > top ) r.y = top;
	if( r.x < -0.5 ) r.x = -0.5;
	if( r.x > right ) r.x = right;
	if( r.x > 0 && r.y > 0 ) {
		double m = (top/right)*(top/right);
		double d2 = r.x*r.x*m + r.y*r.y;
		if( d2 > top*top ) {
			double s = top/sqrt( d2 );
			r.x *= s; r.y *= s;
		}
	}
	if( b->turned )
		b->rider_r = add( sub( mul( j, r.y ), mul( i, r.x ) ), b->body.r );
	else
		b->rider_r = add( add( mul( i, r.x ), mul( j, r.y ) ), b->body.r );
}

static void rider( rbike* b, rvec grav, rvec i, rvec j, double dt ) {
	rider_limit( b, i, j );
	rvec rest = add( b->body.r, mul( j, Kord5y ) );
	rvec dir = sub( rest, b->rider_r );
	rvec Fs = mul( dir, K_spring*5.0 );
	rvec tang = rot90( sub( b->rider_r, b->body.r ) );
	rvec bodyv = add( mul( tang, b->body.omega ), b->body.v );
	rvec Ff = mul( sub( b->rider_v, bodyv ), K_friction*3.0 );
	rvec F = add( sub( Fs, Ff ), mul( grav, b->body.m*G ) );
	b->rider_v = add( b->rider_v, mul( F, dt/b->body.m ) );
	b->rider_r = add( b->rider_r, mul( b->rider_v, dt ) );
}

int ref_step( rbike* b, const rseg* segs, int n, double now, double dt,
			  int gas, int brake, int volt1, int volt2 ) {
	rvec i1 = V( cos( b->body.alfa ), sin( b->body.alfa ) );
	rvec j1 = rot90( i1 );
	if( !b->brake_was && brake ) {
		b->dbrake[0] = b->wheel[0].alfa-b->body.alfa;
		b->dbrake[1] = b->wheel[1].alfa-b->body.alfa;
	}
	b->brake_was = brake;
	double Mw[2] = { 0, 0 };
	if( gas ) {
		if( b->turned ) {
			if( b->wheel[0].omega > -110 ) Mw[0] = -600;
		}
		else if( b->wheel[1].omega < 110 )
			Mw[1] = 600;
	}
	if( brake ) {
		for( int k = 0; k < 2; k++ ) {
			double da = b->wheel[k].alfa-(b->body.alfa+b->dbrake[k]);
			double dw = b->wheel[k].omega-b->body.omega;
			// Damped 0.7 times, as in the NES version (physics.c):
			Mw[k] = -1000*da-100*0.7*dw;
		}
	}
	else {
		normangle( &b->wheel[0].alfa );
		normangle( &b->wheel[1].alfa );
	}
	rvec Fw[2], Fb[2];
	double Mb[2];
	for( int k = 0; k < 2; k++ )
		forces( b, k, i1, j1, &Fw[k], &Fb[k], &Mb[k], Mw[k] );

	// Volts (ugras):
	double oldomega = b->body.omega;
	const double Loket = 12.0, Omegavalt = 3.0, Tol = 0.4*0.25;
	if( b->volt[0] && (volt1 || volt2 || now > b->volt_start[0]+Tol) ) {
		b->body.omega += Loket;
		if( b->body.omega > b->volt_omega[0] ) b->body.omega = b->volt_omega[0];
		if( b->body.omega > 0 ) {
			b->body.omega -= Omegavalt;
			if( b->body.omega < 0 ) b->body.omega = 0;
		}
		b->volt[0] = 0;
	}
	if( b->volt[1] && (volt1 || volt2 || now > b->volt_start[1]+Tol) ) {
		b->body.omega -= Loket;
		if( b->body.omega < b->volt_omega[1] ) b->body.omega = b->volt_omega[1];
		if( b->body.omega < 0 ) {
			b->body.omega += Omegavalt;
			if( b->body.omega > 0 ) b->body.omega = 0;
		}
		b->volt[1] = 0;
	}
	if( volt1 ) {
		b->volt[0] = 1; b->volt_omega[0] = b->body.omega; b->volt_start[0] = now;
		b->body.omega -= Loket;
	}
	if( volt2 ) {
		b->volt[1] = 1; b->volt_omega[1] = b->body.omega; b->volt_start[1] = now;
		b->body.omega += Loket;
	}
	if( volt1 || volt2 ) {
		double dw = b->body.omega-oldomega;
		rvec tang = rot90( sub( b->rider_r, b->body.r ) );
		b->rider_v = add( b->rider_v, mul( tang, dw ) );
	}

	rvec g;
	switch( b->gravity ) {
		case 0: g = V( 0, 1 ); break;
		case 2: g = V( -1, 0 ); break;
		case 3: g = V( 1, 0 ); break;
		default: g = V( 0, -1 ); break;
	}
	rider( b, g, i1, j1, dt );
	integrate( &b->body, add( add( Fb[0], Fb[1] ), mul( g, b->body.m*G ) ),
			   Mb[0]+Mb[1], dt, 0, segs, n );
	for( int k = 0; k < 2; k++ )
		integrate( &b->wheel[k], add( Fw[k], mul( g, b->wheel[k].m*G ) ),
				   Mw[k], dt, 1, segs, n );

	// The head (szamitfejr):
	i1 = V( cos( b->body.alfa ), sin( b->body.alfa ) );
	j1 = rot90( i1 );
	b->head = add( add( b->rider_r, mul( i1, b->turned ? 0.09 : -0.09 ) ),
				   mul( j1, 0.63 ) );
	for( int s = 0; s < n; s++ ) {
		rvec t;
		if( touch( b->head, Head_r, &segs[s], &t ) )
			return 0;
	}
	return 1;
}
