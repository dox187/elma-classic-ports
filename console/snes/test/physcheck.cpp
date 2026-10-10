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

struct item { int in, turn, n, warp; };   // warp: -2 none, -1 out, else an object

static std::vector<item> parse( const char* p ) {
	std::vector<item> out;
	while( *p ) {
		while( *p == ' ' || *p == '\t' ) p++;
		if( !*p || *p == '\n' ) break;
		item it = { 0, 0, 0, -2 };
		if( *p == 'W' || *p == 'X' ) {
			int leave = *p == 'X';
			p++;
			it.warp = (int)strtol( p, (char**)&p, 10 );
			if( leave )
				it.warp = -1;
			out.push_back( it );
			continue;
		}
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
	double maxd[3];             // largest distance in first1,2,5 original engine-time units
	std::string sev, pev;       // events with times
	double send, pend;          // end of the run (dead, finish) or -1
};

// A warp item: the front wheel (kor2) of both bikes onto object obj, or with
// obj < 0 both 2000 m to the right (as test/physdump.c does it).
static void warp( int obj ) {
	int32_t dx = 0x07D00000, dy = 0;
	if( obj >= 0 ) {
		dx = PS_obj[obj].x-PS.c[1].rx;
		dy = PS_obj[obj].y-PS.c[1].ry;
	}
	for( int i = 0; i < 3; i++ ) {
		PS.c[i].rx += dx;
		PS.c[i].ry += dy;
	}
	PS.rider_x += dx;
	PS.rider_y += dy;
	PS.head_x += dx;
	PS.head_y += dy;
	pc_state s;
	pc_get( &s );
	double px = 2000, py = 0;
	if( obj >= 0 ) {
		px = fp( PS_obj[obj].x )-s.c[1].r.x;
		py = fp( PS_obj[obj].y )-s.c[1].r.y;
	}
	for( int i = 0; i < 3; i++ ) {
		s.c[i].r.x += px;
		s.c[i].r.y += py;
	}
	s.rider_r.x += px;
	s.rider_r.y += py;
	s.head.x += px;
	s.head.y += py;
	pc_set( &s );
}

// verbose: 0 summary only, 1 lines every 'every' steps, 2 every step.
static result run( const std::vector<item>& script, double pcdt, int verbose, int every, int one ) {
	double dt = 0.4368/PHYS_HZ;
	std::vector<int> keys, turns, warps;
	for( const item& it : script ) {
		if( it.warp != -2 ) {
			warps.resize( keys.size()+1, -2 );
			warps[keys.size()] = it.warp;
			continue;
		}
		for( int j = 0; j < it.n; j++ ) {
			keys.push_back( it.in );
			turns.push_back( it.turn && j == 0 );
		}
	}
	int nsteps = (int)keys.size();
	warps.resize( nsteps+1, -2 );
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
		printf( "game time body x (snes/orig)      body y (snes/orig)    angle d   wheels d   pos d\n" );
	for( int i = 0; i < nsteps; i++ ) {
		double t = (i+1)*dt;
		if( warps[i] != -2 )
			warp( warps[i] );
		if( !sstop ) {
			int ev = ps_step( (uint16_t)keys[i] );
			if( turns[i] ) ps_turn();
			if( ev & (PH_EAT | PH_DEAD | PH_FINISH) ) {
				snprintf( buf, sizeof buf, "%s%.3f ", evname( ev & ~PH_BUMP ).c_str(), t );
				r.sev += buf;
				if( verbose )
					printf( "  snes  %7.3f game units step %5d: %s\n", t, i, evname( ev ).c_str() );
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
					printf( "  orig  %7.3f game units step %5d: %s\n", tpc, pdone-1, evname( ev ).c_str() );
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

// Full matched-time evidence, intended for test/fidelity_check.py. This path
// changes neither solver: cap each PC substep at the original loop's target,
// apply turns after a nonterminal sample, and retain a stopped engine's state
// while the other continues so terminal disagreement cannot disappear.
static void trace_state( int step, int key, int turn, int sev, int pev,
                         int sstop, int pstop, double dt, double tpc ) {
    pc_state pc;
    pc_get( &pc );
    double sn[24], original[24];
    int n = 0;
    for( int k = 0; k < 3; k++ ) {
        sn[n] = fp( PS.c[k].rx ); original[n++] = pc.c[k].r.x;
        sn[n] = fp( PS.c[k].ry ); original[n++] = pc.c[k].r.y;
        sn[n] = PS.c[k].vx / (16777216.0 * dt) * 0.4368; original[n++] = pc.c[k].v.x * 0.4368;
        sn[n] = PS.c[k].vy / (16777216.0 * dt) * 0.4368; original[n++] = pc.c[k].v.y * 0.4368;
        sn[n] = fa( PS.c[k].a ); original[n++] = pc.c[k].alfa;
        sn[n] = PS.c[k].w / (268435456.0 * dt) * 0.4368; original[n++] = pc.c[k].omega * 0.4368;
    }
    sn[n] = fp( PS.rider_x ); original[n++] = pc.rider_r.x;
    sn[n] = fp( PS.rider_y ); original[n++] = pc.rider_r.y;
    sn[n] = PS.rider_vx / (16777216.0 * dt) * 0.4368; original[n++] = pc.rider_v.x * 0.4368;
    sn[n] = PS.rider_vy / (16777216.0 * dt) * 0.4368; original[n++] = pc.rider_v.y * 0.4368;
    sn[n] = fp( PS.head_x ); original[n++] = pc.head.x;
    sn[n] = fp( PS.head_y ); original[n++] = pc.head.y;
    printf("{\"step\":%d,\"key\":%d,\"turn\":%d,\"pc_time_game\":%.17g,\"snes_event\":%d,\"pc_event\":%d,\"snes_stopped\":%d,\"pc_stopped\":%d,\"snes\":[",
           step, key, turn, tpc, sev, pev, sstop, pstop);
    for( int i = 0; i < n; i++ ) printf("%s%.17g", i ? "," : "", sn[i]);
    printf("],\"pc\":[");
    for( int i = 0; i < n; i++ ) printf("%s%.17g", i ? "," : "", original[i]);
    printf("],\"snes_discrete\":[%d,%d,%d],\"pc_discrete\":[%d,%d,%d],\"snes_objects\":[", PS.turned, PS.gravity, PS.apples, pc.turned, pc.gravity, pc.apples);
    for( int i = 0; i < PS_nobjs; i++ ) printf("%s%d", i ? "," : "", PS_obj[i].active);
    printf("],\"pc_objects\":[");
    for( int i = 0; i < pc_nobjs; i++ ) printf("%s%d", i ? "," : "", pc_obj_active[i]);
    uint8_t raw[PS_DUMP_SIZE]; ps_dump(raw);
    printf("],\"snes_raw\":\"");
    for( int i = 0; i < PS_DUMP_SIZE; i++ ) printf("%02x", raw[i]);
    printf("\",\"snes_apple_object\":%d,\"pc_apple_object\":%d}\n", (sev & PH_EAT) ? PS_eaten : -1, (pev & PH_EAT) ? pc_eaten : -1);
}

static void trace_run( const std::vector<item>& script, double cap ) {
    const double dt = 0.4368 / PHYS_HZ;
    std::vector<int> keys, turns, warps;
    for( const item& it : script ) {
        if( it.warp != -2 ) {
            warps.resize(keys.size() + 1, -2); warps[keys.size()] = it.warp;
        } else for( int j = 0; j < it.n; j++ ) {
            keys.push_back(it.in); turns.push_back(it.turn && j == 0);
        }
    }
    warps.resize(keys.size() + 1, -2);
    int sstop = 0, pstop = 0;
    double tpc = 0;
    trace_state(0, 0, 0, 0, 0, 0, 0, dt, 0);
    for( size_t i = 0; i < keys.size(); i++ ) {
        const double target = (i + 1) * dt;
        if( warps[i] != -2 ) warp(warps[i]);
        int sev = 0, pev = 0;
        if( !sstop ) {
            sev = ps_step((uint16_t)keys[i]);
            sstop = (sev & (PH_DEAD | PH_FINISH)) != 0;
            if( turns[i] && !sstop ) ps_turn();
        }
        const bool matched = fabs(cap - dt) < 1e-15;
        bool matched_pending = matched;
        while( !pstop && (matched ? matched_pending : tpc < target - 1e-12) ) {
            // One PC step per input sample in matched mode. Comparing the
            // accumulated double clock with i*dt eventually adds an extra
            // whole step (first seen at sample3187), despite the tiny epsilon.
            double pc_dt = matched ? dt : fmin(cap, target - tpc);
            matched_pending = false;
            int ev = pc_step(keys[i], pc_dt);
            tpc = pc_time;
            pev |= ev;
            pstop = (ev & (PH_DEAD | PH_FINISH)) != 0;
        }
        if( turns[i] && !pstop ) pc_turn();
        trace_state((int)i + 1, keys[i], turns[i], sev, pev, sstop, pstop, dt, tpc);
        if( sstop && pstop ) break;
    }
}

int main( int argc, char** argv ) {
	if( argc < 5 ) {
		fprintf( stderr, "usage: physcheck GEN_DIR LEVDUMP_DIR LEVEL SCRIPT [-t DT] [-v] [-s N] [-1 N]\n"
						 "       physcheck GEN_DIR LEVDUMP_DIR -f CASES [-t DT]\n" );
		return 2;
	}
	double pcdt = 0.4368/PHYS_HZ;
	int verbose = 1, every = PHYS_HZ/4, one = -1;
	bool trace_json = false;
	for( int i = 5; i < argc; i++ ) {
		if( !strcmp( argv[i], "--trace-json" ) ) trace_json = true;
		else if( !strcmp( argv[i], "-t" ) && i+1 < argc ) pcdt = atof( argv[++i] );
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
	if( trace_json ) {
		if( pcdt <= 0 ) return 2;
		trace_run(parse(argv[4]), pcdt);
		return 0;
	}
	result r = run( parse( argv[4] ), pcdt, verbose, every, one );
	if( one < 0 )
		summary( lev, argv[4], r );
	return 0;
}
