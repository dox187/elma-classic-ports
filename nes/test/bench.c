// Cycles of a step of physics.S in the simulator, still, with gas and with
// the brake (with the lines handed over by simgrid.h, which takes time of
// its own when the bike enters a cell).
#include <stdint.h>
#include <stdio.h>
#include <time.h>
#include "physics.h"
#include "simgrid.h"

static unsigned long steps( uint8_t input, int n ) {
	unsigned long t = clock();
	for( int i = 0; i < n; i++ )
		ph_step( input );
	return (clock()-t)/n;
}

int main( void ) {
	ph_init( SIM_START_X, SIM_START_Y );
	unsigned long still = steps( 0, 200 );
	unsigned long gas = steps( IN_GAS, 200 );
	unsigned long brake = steps( IN_BRAKE, 100 );
	printf( "cycles a step: still %lu, gas %lu, brake %lu\n", still, gas, brake );
	return 0;
}
