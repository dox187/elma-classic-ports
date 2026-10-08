// The log of test/snes_phys.c, made on the host with the C description of
// the physics (test/phys_spec.c), for test/physrom.py to compare.
//
//   physdump GEN_DIR CASES LOG [FULL_CASE FULL_OUT [FULL_FROM]]
//
// LOG gets 6 bytes a step (events, two Fletcher sums of the state);
// FULL_OUT the whole state of the steps of case FULL_CASE from its step
// FULL_FROM on (220 bytes each, at most 160, before a turn of the step), as
// the Lua of test/physrom.py reads them from the ROM.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "phys_spec.h"

#define PHYS_STATE PS_DUMP_SIZE
#define PHYS_DUMP 220

static uint16_t Sa, Sb;

static void sum( const uint8_t* p, int n ) {
	while( n-- ) {
		Sa += *p++;
		Sb += Sa;
	}
}

static void put16( uint8_t* p, uint16_t v ) {
	p[0] = (uint8_t)v;
	p[1] = (uint8_t)(v >> 8);
}

static void put32( uint8_t* p, int32_t v ) {
	for( int i = 0; i < 4; i++ )
		p[i] = (uint8_t)((uint32_t)v >> 8*i);
}

// The outputs as the ROM has them: phys_view (52 bytes with padding), then
// bump, eaten, friction, wheel_omega, apples_left, volt_age, volt1.
static void outputs( uint8_t* view, uint8_t* rest ) {
	memset( view, 0, 52 );
	put32( view, PS.c[0].rx );
	put32( view+4, PS.c[0].ry );
	put16( view+8, ps_angle16( PS.c[0].a ) );
	put32( view+12, PS.c[1].rx );
	put32( view+16, PS.c[2].rx );
	put32( view+20, PS.c[1].ry );
	put32( view+24, PS.c[2].ry );
	put16( view+28, ps_angle16( PS.c[1].a ) );
	put16( view+30, ps_angle16( PS.c[2].a ) );
	put32( view+32, PS.rider_x );
	put32( view+36, PS.rider_y );
	put32( view+40, PS.head_x );
	put32( view+44, PS.head_y );
	view[48] = PS.turned;
	view[49] = PS.gravity;
	put16( rest, PS_bump );
	put16( rest+2, PS_eaten );
	put16( rest+4, PS_friction );
	put16( rest+6, PS_wheel_omega );
	put16( rest+8, (uint16_t)(PS_apples_needed-PS.apples) );
	rest[10] = PS.last_volt;
	rest[11] = PS.volt1;
}

static uint8_t Blob[65536];

int main( int argc, char** argv ) {
	if( argc < 4 ) {
		fprintf( stderr, "usage: physdump GEN_DIR CASES LOG [FULL_CASE FULL_OUT]\n" );
		return 2;
	}
	int fullcase = argc > 5 ? atoi( argv[4] ) : -1;
	int fullfrom = argc > 6 ? atoi( argv[6] ) : 0;
	FILE* cases = fopen( argv[2], "r" );
	FILE* log = fopen( argv[3], "wb" );
	FILE* full = argc > 5 ? fopen( argv[5], "wb" ) : NULL;
	if( !cases || !log ) {
		perror( "physdump" );
		return 2;
	}
	char line[4096];
	int c = 0;
	while( fgets( line, sizeof line, cases ) ) {
		char* p = line;
		while( *p == ' ' ) p++;
		if( *p == '#' || *p == '\n' || !*p )
			continue;
		int lev = (int)strtol( p, &p, 10 );
		char path[512];
		snprintf( path, sizeof path, "%s/phys/lev%02d.bin", argv[1], lev );
		FILE* f = fopen( path, "rb" );
		if( !f ) {
			perror( path );
			return 2;
		}
		fread( Blob, 1, sizeof Blob, f );
		fclose( f );
		ps_level( Blob );
		int nfull = 0, k = 0;
		uint16_t ev = 0;
		while( *p && !(ev & (PH_DEAD | PH_FINISH)) ) {
			while( *p == ' ' || *p == '\t' ) p++;
			if( !*p || *p == '\n' )
				break;
			int in = 0, turn = 0;
			while( *p && strchr( "GBRLTN", *p ) ) {
				switch( *p ) {
					case 'G': in |= PH_GAS; break;
					case 'B': in |= PH_BRAKE; break;
					case 'R': in |= PH_VOLT_R; break;
					case 'L': in |= PH_VOLT_L; break;
					case 'T': turn = 1; break;
				}
				p++;
			}
			int n = (int)strtol( p, &p, 10 );
			if( n <= 0 ) n = 1;
			for( int j = 0; j < n; j++ ) {
				ev = ps_step( (uint16_t)in );
				uint8_t st[PHYS_DUMP];
				if( c == fullcase && full && k >= fullfrom && nfull < 160 ) {
					memset( st, 0, sizeof st );
					ps_dump( st );
					outputs( st+PHYS_STATE, st+PHYS_STATE+52 );
					put16( st+PHYS_STATE+64, ev );
					ps_trig_dump( st+208 );
					fwrite( st, 1, PHYS_DUMP, full );
					nfull++;
				}
				k++;
				if( turn && j == 0 )
					ps_turn();
				memset( st, 0, sizeof st );
				ps_dump( st );
				outputs( st+PHYS_STATE, st+PHYS_STATE+52 );
				Sa = Sb = 0;
				sum( st, PHYS_STATE );
				sum( st+PHYS_STATE, 10 );
				sum( st+PHYS_STATE+12, 38 );
				sum( st+PHYS_STATE+52, 12 );
				uint8_t rec[6];
				put16( rec, ev );
				put16( rec+2, Sa );
				put16( rec+4, Sb );
				fwrite( rec, 1, 6, log );
				if( ev & (PH_DEAD | PH_FINISH) )
					break;
			}
		}
		c++;
	}
	fclose( log );
	if( full )
		fclose( full );
	return 0;
}
