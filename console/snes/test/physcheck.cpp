// Runs the fixed point physics of the SNES version (phys_spec.c) next to the
// physics of the original game (pcphys/) with the same keys, and tells how
// far apart the bikes get over time and when the events come.
//
//   physcheck GEN_DIR LEVDUMP_DIR LEVEL "SCRIPT" [-t DT] [-v] [-s N] [-1 N]
//   physcheck GEN_DIR LEVDUMP_DIR -f CASES [-t DT]
//
// GEN_DIR is build/gen (phys/levNN.bin), LEVDUMP_DIR the output of
// test/levdump.py. A script is items of keys and a count of steps of the
// SNES (1/PHYS_HZ s): G gas, B brake, R right volt, L left volt, N nothing,
// T turn (after the first step of the item), e.g. "G200 NT1 G150 R1 G60".
// The original takes steps of DT (default the same, 0.4368/PHYS_HZ) with
// the same keys at the same times. -v prints every step, -s N a line every
// N steps (default PHYS_HZ/4); -1 N runs the original and, for the 20 steps
// up to step N, also one step of the SNES physics from its state each time
// (how the velocities change in one step). With -f, each line of CASES is
// "LEVEL SCRIPT" (# comments) and a line of summary is printed for each.
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <string>
#include <vector>
#include "phys_spec.h"
#include "phys_const.h"
#include "pcphys/pcphys.h"

struct item { int in, turn, n; };

static std::vector<item> parse( const char* p ) {
	std::vector<item> out;
	while( *p ) {
		while( *p == ' ' || *p == '\t' ) p++;
		if( !*p || *p == '\n' ) break;
		item it = { 0, 0, 0 };
		while( *p && strchr( "GBRLTN", *p ) ) {
			switch( *p ) {
				case 'G': it.in |= PH_GAS; break;
				case 'B': it.in |= PH_BRAKE; break;
				case 'R': it.in |= PH_VOLT_R; break;
				case 'L': it.in |= PH_VOLT_L; break;
				case 'T': it.turn = 1; break;
			}
			p++;
		}
		it.n = (int)strtol( p, (char**)&p, 10 );
		if( it.n <= 0 ) it.n = 1;
		out.push_back( it );
	}
	return out;
}

static double fa( int32_t a ) { return a/268435456.0; }
static double fp( int32_t p ) { return p/65536.0; }

static double angdiff( double a, double b ) {
	double d = fmod( a-b, 2*M_PI );
	if( d > M_PI ) d -= 2*M_PI;
	if( d < -M_PI ) d += 2*M_PI;
	return d;
}

// The state of the original in the units of the SNES:
static void sync( double dt ) {
	pc_state s;
	pc_get( &s );
	for( int k = 0; k < 3; k++ ) {
		PS.c[k].rx = (int32_t)lround( s.c[k].r.x*65536 );
		PS.c[k].ry = (int32_t)lround( s.c[k].r.y*65536 );
		PS.c[k].vx = (int32_t)lround( s.c[k].v.x*dt*16777216 );
		PS.c[k].vy = (int32_t)lround( s.c[k].v.y*dt*16777216 );
		double a = fmod( s.c[k].alfa, 2*M_PI );
		if( a >= M_PI ) a -= 2*M_PI;
		if( a < -M_PI ) a += 2*M_PI;
		PS.c[k].a = (int32_t)lround( a*268435456 );
		PS.c[k].w = (int32_t)lround( s.c[k].omega*dt*268435456 );
	}
	PS.rider_x = (int32_t)lround( s.rider_r.x*65536 );
	PS.rider_y = (int32_t)lround( s.rider_r.y*65536 );
	PS.rider_vx = (int32_t)lround( s.rider_v.x*dt*16777216 );
	PS.rider_vy = (int32_t)lround( s.rider_v.y*dt*16777216 );
	PS.turned = (uint8_t)s.turned;
	PS.gravity = (uint8_t)s.gravity;
	PS.roll[0].on = PS.roll[1].on = 0;
}

// One step of both from the same state: how the velocities change.
static void onestep( int in, double dt ) {
	pc_state s0, s1;
	pc_get( &s0 );
	sync( dt );
	ps_state_t p0 = PS;
	pc_step( in, dt );
	ps_step( (uint16_t)in );
	pc_get( &s1 );
	const char* nm[3] = { "body", "kor2", "kor4" };
	for( int k = 0; k < 3; k++ ) {
		double dvx = (s1.c[k].v.x-s0.c[k].v.x)*dt*16777216, dvy = (s1.c[k].v.y-s0.c[k].v.y)*dt*16777216;
		double dw = (s1.c[k].omega-s0.c[k].omega)*dt*268435456;
		printf( "   %s dv orig %10.1f %10.1f snes %10d %10d | dw orig %11.0f snes %11d | dr %6.0f %6.0f\n", nm[k],
			dvx, dvy, PS.c[k].vx-p0.c[k].vx, PS.c[k].vy-p0.c[k].vy, dw, PS.c[k].w-p0.c[k].w,
			PS.c[k].rx-s1.c[k].r.x*65536, PS.c[k].ry-s1.c[k].r.y*65536 );
	}
	double dvx = (s1.rider_v.x-s0.rider_v.x)*dt*16777216, dvy = (s1.rider_v.y-s0.rider_v.y)*dt*16777216;
	printf( "   rider dv orig %10.1f %10.1f snes %10d %10d | dr %6.0f %6.0f head %6.0f %6.0f\n", dvx, dvy,
		PS.rider_vx-p0.rider_vx, PS.rider_vy-p0.rider_vy,
		PS.rider_x-s1.rider_r.x*65536, PS.rider_y-s1.rider_r.y*65536,
		PS.head_x-s1.head.x*65536, PS.head_y-s1.head.y*65536 );
}

static std::string evname( int ev ) {
	std::string s;
	if( ev & PH_DEAD ) s += "dead ";
	if( ev & PH_FINISH ) s += "finish ";
	if( ev & PH_EAT ) s += "eat ";
	if( ev & PH_BUMP ) s += "bump ";
	return s;
}

static uint8_t Blob[65536];

static int load( const char* gen, const char* levdump, int lev ) {
	char path[512];
	snprintf( path, sizeof path, "%s/phys/lev%02d.bin", gen, lev );
	FILE* f = fopen( path, "rb" );
	if( !f ) { perror( path ); return 0; }
	fread( Blob, 1, sizeof Blob, f );
	fclose( f );
	snprintf( path, sizeof path, "%s/lev%02d.txt", levdump, lev );
	if( !pc_load( path ) ) { fprintf( stderr, "%s: cannot load\n", path ); return 0; }
	ps_level( Blob );
	return 1;
}

struct result {
	double t1cm, t10cm;         // when the bodies got 0.01 and 0.1 m apart (-1: never)
	double maxd[3];             // the largest distance in the first 1, 2 and 5 s
	std::string sev, pev;       // events with times
	double send, pend;          // end of the run (dead, finish) or -1
};

// verbose: 0 summary only, 1 lines every 'every' steps, 2 every step.
static result run( const std::vector<item>& script, double pcdt, int verbose, int every, int one ) {
	double dt = 0.4368/PHYS_HZ;
	std::vector<int> keys, turns;
	for( const item& it : script )
		for( int j = 0; j < it.n; j++ ) {
			keys.push_back( it.in );
			turns.push_back( it.turn && j == 0 );
		}
	int nsteps = (int)keys.size();
	result r = { -1, -1, { 0, 0, 0 }, "", "", -1, -1 };
	if( one >= 0 ) {
		for( int i = 0; i < nsteps && i <= one; i++ ) {
			if( i >= one-20 ) {
				printf( "step %d keys %d\n", i, keys[i] );
				onestep( keys[i], dt );
			}
			else
				pc_step( keys[i], dt );
			if( turns[i] ) pc_turn();
		}
		return r;
	}
	int sstop = 0, pstop = 0, pdone = 0;
	double tpc = 0;
	char buf[128];
	if( verbose )
		printf( "  time   body x (snes/orig)      body y (snes/orig)    angle d   wheels d   pos d\n" );
	for( int i = 0; i < nsteps; i++ ) {
		double t = (i+1)*dt;
		if( !sstop ) {
			int ev = ps_step( (uint16_t)keys[i] );
			if( turns[i] ) ps_turn();
			if( ev & (PH_EAT | PH_DEAD | PH_FINISH) ) {
				snprintf( buf, sizeof buf, "%s%.3f ", evname( ev & ~PH_BUMP ).c_str(), t );
				r.sev += buf;
				if( verbose )
					printf( "  snes  %7.3f s step %5d: %s\n", t, i, evname( ev ).c_str() );
			}
			if( ev & (PH_DEAD | PH_FINISH) ) {
				sstop = 1;
				r.send = t;
			}
		}
		// The original up to the same time, with the keys of this step:
		while( !pstop && tpc < t-1e-9 ) {
			int ev = pc_step( keys[i], pcdt );
			tpc += pcdt;
			pdone++;
			if( turns[i] && tpc >= t-pcdt*0.5 ) pc_turn();
			if( ev & (PH_EAT | PH_DEAD | PH_FINISH) ) {
				snprintf( buf, sizeof buf, "%s%.3f ", evname( ev & ~PH_BUMP ).c_str(), tpc );
				r.pev += buf;
				if( verbose )
					printf( "  orig  %7.3f s step %5d: %s\n", tpc, pdone-1, evname( ev ).c_str() );
			}
			if( ev & (PH_DEAD | PH_FINISH) ) {
				pstop = 1;
				r.pend = tpc;
			}
		}
		if( !sstop && !pstop ) {
			pc_state s;
			pc_get( &s );
			double bx = fp( PS.c[0].rx ), by = fp( PS.c[0].ry );
			double d = hypot( bx-s.c[0].r.x, by-s.c[0].r.y );
			for( int k = 0; k < 3; k++ )
				if( t <= (k == 0 ? 1 : k == 1 ? 2 : 5)+1e-9 && d > r.maxd[k] )
					r.maxd[k] = d;
			if( d >= 0.01 && r.t1cm < 0 ) r.t1cm = t;
			if( d >= 0.1 && r.t10cm < 0 ) r.t10cm = t;
			if( verbose > 1 || (verbose && (i+1) % every == 0) ) {
				double wd = 0;
				for( int k = 1; k < 3; k++ )
					wd = fmax( wd, hypot( fp( PS.c[k].rx )-s.c[k].r.x, fp( PS.c[k].ry )-s.c[k].r.y ) );
				double ad = angdiff( fa( PS.c[0].a ), s.c[0].alfa );
				printf( "%7.3f %9.4f %9.4f  %9.4f %9.4f  %8.4f %8.4f %8.4f\n", t, bx, s.c[0].r.x, by,
						s.c[0].r.y, ad, wd, d );
			}
		}
		if( sstop && pstop ) break;
	}
	return r;
}

static void summary( int lev, const char* script, const result& r ) {
	printf( "level %2d  %-40s 1cm %6.2f 10cm %6.2f  max %.3f/%.3f/%.3f m\n", lev, script, r.t1cm, r.t10cm,
			r.maxd[0], r.maxd[1], r.maxd[2] );
	printf( "          snes: %s\n          orig: %s\n", r.sev.empty() ? "-" : r.sev.c_str(),
			r.pev.empty() ? "-" : r.pev.c_str() );
}

int main( int argc, char** argv ) {
	if( argc < 5 ) {
		fprintf( stderr, "usage: physcheck GEN_DIR LEVDUMP_DIR LEVEL SCRIPT [-t DT] [-v] [-s N] [-1 N]\n"
						 "       physcheck GEN_DIR LEVDUMP_DIR -f CASES [-t DT]\n" );
		return 2;
	}
	double pcdt = 0.4368/PHYS_HZ;
	int verbose = 1, every = PHYS_HZ/4, one = -1;
	for( int i = 5; i < argc; i++ ) {
		if( !strcmp( argv[i], "-t" ) && i+1 < argc ) pcdt = atof( argv[++i] );
		else if( !strcmp( argv[i], "-v" ) ) verbose = 2;
		else if( !strcmp( argv[i], "-s" ) && i+1 < argc ) every = atoi( argv[++i] );
		else if( !strcmp( argv[i], "-1" ) && i+1 < argc ) one = atoi( argv[++i] );
	}
	if( !strcmp( argv[3], "-f" ) ) {
		FILE* f = fopen( argv[4], "r" );
		if( !f ) { perror( argv[4] ); return 2; }
		char line[1024];
		printf( "original steps of %.6f, SNES %d steps a second\n", pcdt, PHYS_HZ );
		while( fgets( line, sizeof line, f ) ) {
			char* p = line;
			while( *p == ' ' ) p++;
			if( *p == '#' || *p == '\n' || !*p ) continue;
			int lev = (int)strtol( p, &p, 10 );
			while( *p == ' ' ) p++;
			p[strcspn( p, "\n" )] = 0;
			if( !load( argv[1], argv[2], lev ) ) return 2;
			summary( lev, p, run( parse( p ), pcdt, 0, every, -1 ) );
		}
		fclose( f );
		return 0;
	}
	int lev = atoi( argv[3] );
	if( !load( argv[1], argv[2], lev ) ) return 2;
	result r = run( parse( argv[4] ), pcdt, verbose, every, one );
	if( one < 0 )
		summary( lev, argv[4], r );
	return 0;
}
