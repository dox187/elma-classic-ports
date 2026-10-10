// The C description of the physics (test/phys_spec.c) as a library for the
// scripts of the tests (test/finish_search.py, through ctypes): a level, its
// steps with the keys of test/play.py --steps, and the state saved and
// restored.
#include <stdio.h>
#include <string.h>
#include "phys_spec.h"

#define TURN 0x10       // GAME_TURN of src/game.h: a turn after the step

static uint8_t Blob[65536];

typedef struct {
	ps_state_t s;
	ps_obj_t obj[52];
} pp_state_t;

// The level data of tools/gen_phys.py (build/gen/phys/levNN.bin); 0 if read.
int pp_level( const char* path ) {
	FILE* f = fopen( path, "rb" );
	if( !f )
		return -1;
	fread( Blob, 1, sizeof Blob, f );
	fclose( f );
	ps_level( Blob );
	return 0;
}

int pp_state_size( void ) {
	return (int)sizeof( pp_state_t );
}

void pp_save( pp_state_t* p ) {
	p->s = PS;
	memcpy( p->obj, PS_obj, sizeof PS_obj );
}

void pp_load( const pp_state_t* p ) {
	PS = p->s;
	memcpy( PS_obj, p->obj, sizeof PS_obj );
}

// Runs n steps with the keys; stops after a step that ends the level. Returns
// the steps run, *ev the events of the steps or-ed together.
int pp_run( const uint8_t* keys, int n, uint16_t* ev ) {
	uint16_t e = 0;
	int i;
	for( i = 0; i < n; i++ ) {
		uint16_t s = ps_step( keys[i] & (PH_GAS | PH_BRAKE | PH_VOLT_R | PH_VOLT_L) );
		e |= s;
		if( s & (PH_DEAD | PH_FINISH) ) {
			i++;
			break;
		}
		if( keys[i] & TURN )
			ps_turn();
	}
	*ev = e;
	return i;
}

// The body (x, y in P, velocities in V, the angle in W), the head, and the
// apples still to eat.
void pp_view( int32_t* out ) {
	out[0] = PS.c[0].rx;
	out[1] = PS.c[0].ry;
	out[2] = PS.c[0].vx;
	out[3] = PS.c[0].vy;
	out[4] = PS.c[0].a;
	out[5] = PS.head_x;
	out[6] = PS.head_y;
	out[7] = PS_apples_needed-PS.apples;
	out[8] = PS.turned;
}
