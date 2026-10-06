// Runs physics.S and physics.c (built with its names changed, see the
// Makefile) side by side in the simulator, and compares the bikes after
// each step: they must be the same to the bit.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "physics.h"
#include "simgrid.h"

extern bike_t RBike;
void rph_init( int32_t x, int32_t y );
uint8_t rph_step( uint8_t input );
void rph_turn( void );

static void compare( int step ) {
	const uint8_t* a = (const uint8_t*)&Bike;
	const uint8_t* c = (const uint8_t*)&RBike;
	for( uint16_t i = 0; i < sizeof( bike_t ); i++ )
		if( a[i] != c[i] ) {
			printf( "step %d: byte %u of the bike differs (asm %02x, C %02x)\n", step, i, a[i], c[i] );
			exit( 1 );
		}
}

#define TURN 0xff

int main( void ) {
	ph_init( SIM_START_X, SIM_START_Y );
	rph_init( SIM_START_X, SIM_START_Y );
	compare( -1 );
	// Inputs and the steps they are held:
	static const uint8_t script[][2] = {
		{ 0, 30 }, { IN_GAS, 150 }, { IN_GAS | IN_VOLT_RIGHT, 1 }, { IN_GAS, 60 },
		{ IN_GAS | IN_VOLT_LEFT, 1 }, { IN_GAS, 80 }, { IN_BRAKE, 40 }, { IN_VOLT_LEFT, 1 },
		{ 0, 60 }, { TURN, 1 }, { IN_GAS, 200 }, { IN_BRAKE, 60 }, { IN_GAS, 250 }, { 0, 0 } };
	int step = 0;
	for( int k = 0; script[k][1]; k++ ) {
		if( script[k][0] == TURN ) {
			ph_turn();
			rph_turn();
			continue;
		}
		for( int i = 0; i < script[k][1]; i++, step++ ) {
			uint8_t a = ph_step( script[k][0] ), c = rph_step( script[k][0] );
			if( a != c ) {
				printf( "step %d: asm returned %d, C %d\n", step, a, c );
				return 1;
			}
			compare( step );
		}
	}
	printf( "asm and C the same for %d steps\n", step );
	return 0;
}
