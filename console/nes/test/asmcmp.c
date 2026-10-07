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

// Brake deflection is accumulated, including complete turns. Exercise
// both signs at the old half-turn boundary, rounding boundaries, torque
// saturation and 32-bit angle rollover with opposing damping.
static void brake_boundaries( void ) {
	static const uint32_t delta[] = {
		0, 0x100, 0x7fffff, 0x800000, 0x800001,
		0xffffff, 0x1000000, 0x1800000, 0x3000000,
		0x7fffffff, 0x80000000, 0xffffffff
	};
	for( unsigned i = 0; i < sizeof(delta)/sizeof(delta[0]); i++ ) {
		ph_init( SIM_START_X, SIM_START_Y );
		Bike.brake_was = IN_BRAKE;
		Bike.body.alfa = 0xfedc1234UL;
		Bike.wheel[0].alfa = Bike.body.alfa+delta[i];
		Bike.wheel[1].alfa = Bike.body.alfa-delta[i];
		Bike.wheel[0].omega = i & 1 ? 12000 : -12000;
		Bike.wheel[1].omega = -Bike.wheel[0].omega;
		RBike = Bike;
		uint8_t a = ph_step( IN_BRAKE ), c = rph_step( IN_BRAKE );
		if( a != c ) exit( 1 );
		compare( 10000+i );
	}
	printf( "asm and C the same at 12 brake angle boundaries\n" );
}

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
	brake_boundaries();
	return 0;
}
