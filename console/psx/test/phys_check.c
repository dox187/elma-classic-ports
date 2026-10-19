// The same run of the fixed point physics (src/phys/fixphys.c) on the host
// and on the PlayStation: a bike on a bumpy test track built here, with
// gas, brake, volts, turns and the short last steps of a frame loop, and a
// checksum of the whole state after every step. test/phys_test.py --ps1
// compares the two; equal checksums mean that the host fidelity test
// (test/phys_host.cpp) shows what the PlayStation computes.
//
// On the PlayStation the result is in phys_check_result, which
// test/phys_check.lua reads from RAM; on the host it is printed.
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "fixphys.h"

#define STEPS 4000
#define CHECK_MAGIC 0x50485953u   // "PHYS"

typedef struct {
	volatile uint32_t magic;      // CHECK_MAGIC when done
	volatile uint32_t sum;        // FNV-1a of the states
	volatile uint32_t steps;
	volatile uint32_t events;     // head contacts + object hits
	volatile int32_t body_x, body_y;   // the body at the end (mm)
} check_result;

check_result phys_check_result;

// The test track: a closed polygon, y up (points in m).
static const double Track[][2] = {
	{ -2, 0 }, { 4, 0 }, { 6, 0.6 }, { 7, 0.2 }, { 9, 1.4 }, { 10, 1.1 },
	{ 12, 1.6 }, { 13.5, 0.3 }, { 16, 0.3 }, { 16.5, 0.8 }, { 18, 0.4 },
	{ 22, 2.5 }, { 25, 2.5 }, { 25, 12 }, { -2, 12 },
};
#define NPOINTS ((int)(sizeof Track/sizeof Track[0]))

static fx_line Lines[NPOINTS];
static uint32_t Rows[16+1];
static uint16_t Cells[65*16];
static uint16_t List[64*16*NPOINTS];
static int Apple_aktiv = 1, Killer_aktiv = 1;
static fx_obj Objs[2];

static uint32_t Sum = 2166136261u;

static void add32( uint32_t v ) {
	for( int i = 0; i < 4; i++ ) {
		Sum ^= (v >> (8*i)) & 0xff;
		Sum *= 16777619u;
	}
}

static void add64( int64_t v ) {
	add32( (uint32_t)v );
	add32( (uint32_t)((uint64_t)v >> 32) );
}

static void level( fx_level* lev ) {
	memset( lev, 0, sizeof( *lev ) );
	double minx = 1e9, miny = 1e9;
	for( int i = 0; i < NPOINTS; i++ ) {
		const double* a = Track[i];
		const double* b = Track[(i+1) % NPOINTS];
		double vx = b[0]-a[0], vy = b[1]-a[1];
		double h = sqrt( vx*vx+vy*vy );
		double ex = vx*(1/h), ey = vy*(1/h);
		fx_line* l = &Lines[i];
		l->p.x = fx_d2q( a[0], 40 );
		l->p.y = fx_d2q( a[1], 40 );
		l->e.x = fx_d2q( a[0]+ex*h, 40 );
		l->e.y = fx_d2q( a[1]+ey*h, 40 );
		l->len = fx_d2q( h, 40 );
		l->ux = (int32_t)fx_d2q( ex, 30 );
		l->uy = (int32_t)fx_d2q( ey, 30 );
		l->lx = (int32_t)fx_d2q( ex*1073741824.0-l->ux, 31 );
		l->ly = (int32_t)fx_d2q( ey*1073741824.0-l->uy, 31 );
		if( a[0] < minx ) minx = a[0];
		if( a[1] < miny ) miny = a[1];
	}
	lev->lines = Lines;
#ifdef ELMA_PSX
	static fx_line* chunks[] = { Lines };
	lev->line_chunks = chunks;
#endif
	lev->nlines = NPOINTS;
	lev->xdim = 64;
	lev->ydim = 16;
	lev->origo.x = fx_d2q( minx-6, 40 );
	lev->origo.y = fx_d2q( miny-6, 40 );
	// Every cell has every line (the order of the lists is all that matters
	// for the test):
	uint32_t n = 0;
	for( int y = 0; y < 16; y++ ) {
		Rows[y] = n;
		for( int x = 0; x <= 64; x++ )
			Cells[65*y+x] = (uint16_t)(x*NPOINTS);
		for( int x = 0; x < 64; x++ )
			for( int i = 0; i < NPOINTS; i++ )
				List[n++] = (uint16_t)i;
	}
	Rows[16] = n;
	lev->row = Rows;
	lev->cell = Cells;
	lev->list = List;
#ifdef ELMA_PSX
	static uint16_t* List_rows[16];
	for( int y = 0; y < 16; ++y )
		List_rows[y] = List+Rows[y];
	lev->list_rows = List_rows;
#endif
	Objs[0].r.x = fx_d2q( 14.5, 40 );
	Objs[0].r.y = fx_d2q( 0.9, 40 );
	Objs[0].aktiv = &Apple_aktiv;
	Objs[0].tipus = 2;
	Objs[1].r.x = fx_d2q( 23.5, 40 );
	Objs[1].r.y = fx_d2q( 4.5, 40 );
	Objs[1].aktiv = &Killer_aktiv;
	Objs[1].tipus = 3;
	lev->objs = Objs;
	lev->nobjs = 2;
	lev->kill_x1 = lev->kill_y1 = fx_d2q( -100, 40 );
	lev->kill_x2 = lev->kill_y2 = fx_d2q( 100, 40 );
}

// The bike of initmotor (ADATOK.CPP) with its front wheel at x, y:
static void bike( fx_bike* b, double x, double y ) {
	static const double r[4][2] = { { 2.75, 3.6 }, { 1.9, 3.0 }, { 3.6, 3.0 }, { 2.75, 4.04 } };
	memset( b, 0, sizeof( *b ) );
	double dx = x-r[1][0], dy = y-r[1][1];
	for( int i = 0; i < 3; i++ ) {
		b->k[i].r.x = fx_d2q( r[i][0]+dx, 40 );
		b->k[i].r.y = fx_d2q( r[i][1]+dy, 40 );
	}
	b->vr.x = fx_d2q( r[3][0]+dx, 40 );
	b->vr.y = fx_d2q( r[3][1]+dy, 40 );
	b->ugras1kezd = b->ugras2kezd = -1.0;
	b->kezdoomega1 = b->kezdoomega2 = fx_d2q( -1.0, 40 );
}

static void params( fx_param* p ) {
	fx_input in;
	in.drsugar = 10000.0;
	in.sr = 1000.0;
	in.g = 10.0;
	in.belsosav = 0.005;
	in.elszakad = 0.01;
	in.merge = 0.1;
	in.fejsugar = 0.238;
	in.objsugar = 0.4;
	in.ugroturelem = 0.4;
	in.kord2x = 1.9-2.75;
	in.kord2y = 3.0-3.6;
	in.kord4x = 3.6-2.75;
	in.kord4y = 3.0-3.6;
	in.kord5y = 4.04-3.6;
	in.pi = 3.141592;
	in.kor_m[0] = 200;
	in.kor_m[1] = in.kor_m[2] = 10;
	in.kor_theta[0] = 200.0*0.55*0.55;
	in.kor_theta[1] = in.kor_theta[2] = 0.32;
	in.kor_sugar[0] = 0.3;
	in.kor_sugar[1] = in.kor_sugar[2] = 0.4;
	double avx = 0.14-(-0.35), avy = 0.36-(0.13);
	double l = sqrt( avy*avy+avx*avx );
	in.avn_x = -avy*(1/l);
	in.avn_y = avx*(1/l);
	fx_params( p, &in );
}

static void run( void ) {
	static fx_level lev;
	static fx_param p;
	static fx_bike b;
	fx_init();
	level( &lev );
	params( &p );
	bike( &b, 0.5, 0.45 );
	int hatra = 0, gravity = 1, events = 0;
	double eddig = 0, cel = 0, utolsougras = -100;
	int steps = 0;
	while( steps < STEPS ) {
		cel += 0.4368/27;   // a frame of a game running at 27 fps
		while( eddig <= cel-0.000001 && steps < STEPS ) {
			double dt = 0.0055;
			if( eddig+dt > cel )
				dt = cel-eddig;
			int phase = steps % 900;
			int gaz = phase < 600 || phase >= 760;
			int fek = phase >= 640 && phase < 700;
			int ugrik1 = 0, ugrik2 = 0;
			if( eddig > utolsougras+0.4 && (phase == 300 || phase == 820) ) {
				ugrik1 = phase == 300;
				ugrik2 = phase == 820;
				utolsougras = eddig;
			}
			fx_leptet( &b, &lev, &p, eddig, dt, gaz, fek, ugrik1, ugrik2, hatra, gravity );
			int head = fx_fejutkozik( &b, &lev, &p );
			int obj = fx_utkozikesprite( &lev, &p, b.k[1].r, p.sugar[1], 0 );
			events += head+(obj >= 0);
			if( obj == 0 )
				Apple_aktiv = 0;
			for( int i = 0; i < 3; i++ ) {
				add64( b.k[i].r.x );
				add64( b.k[i].r.y );
				add64( b.k[i].v.x );
				add64( b.k[i].v.y );
				add64( b.k[i].a );
				add64( b.k[i].w );
			}
			add64( b.vr.x );
			add64( b.vr.y );
			add64( b.vv.x );
			add64( b.vv.y );
			add64( b.fej.x );
			add64( b.fej.y );
			add64( b.maxsurl );
			add32( (uint32_t)(b.nbump*16+head*4+(obj+1)) );
			eddig += dt;
			steps++;
		}
		// The turn key, at the end of a frame:
		if( steps % 1200 < 20 && steps > 20 ) {
			hatra = !hatra;
			fx_szamitfejr( &b, hatra );
		}
	}
	phys_check_result.sum = Sum;
	phys_check_result.steps = (uint32_t)steps;
	phys_check_result.events = (uint32_t)events;
	phys_check_result.body_x = (int32_t)(fx_q2d( b.k[0].r.x, 40 )*1000);
	phys_check_result.body_y = (int32_t)(fx_q2d( b.k[0].r.y, 40 )*1000);
	phys_check_result.magic = CHECK_MAGIC;
}

#ifndef ELMA_PSX
// The engine sound value against the double expression of LEJATSZO.CPP:
static double frekvencia_error( void ) {
	double worst = 0;
	for( int i = -300000; i <= 300000; i++ ) {
		double omega = i*0.004321;
		double f = fabs( omega )*0.025;
		if( f > 30.0 )
			f = 30.0;
		double want = 2.0-exp( -f );
		double got = fx_q2d( fx_motorfrekvencia( fx_d2q( omega, 40 ) ), 31 );
		if( fabs( got-want ) > worst )
			worst = fabs( got-want );
	}
	return worst;
}
#endif

int main( void ) {
	run();
#ifndef ELMA_PSX
	printf( "motorfrekvencia: largest error %.3g\n", frekvencia_error() );
#endif
	printf( "physcheck: sum %08x steps %u events %u body %d %d mm\n",
			(unsigned)phys_check_result.sum, (unsigned)phys_check_result.steps,
			(unsigned)phys_check_result.events, (int)phys_check_result.body_x,
			(int)phys_check_result.body_y );
#ifdef ELMA_PSX
	for( ;; )
		;
#endif
	return 0;
}
