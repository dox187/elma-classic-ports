// A stand-in for the physics while testing the rest on the NES: the bike
// flies where the pad points it (gas up, brake down, volts left and right).
#include "../src/physics.h"

bike_t Bike;

void ph_init( int32_t x, int32_t y ) {
	uint8_t* p = (uint8_t*)&Bike;
	for( uint16_t i = 0; i < sizeof( bike_t ); i++ )
		p[i] = 0;
	Bike.body.rx = x+M_TO_F( 0.85 );
	Bike.body.ry = y+M_TO_F( 1.6 );
}

void ph_turn( void ) {
	Bike.turned = !Bike.turned;
}

static int32_t Vx, Vy;

uint8_t ph_step( uint8_t input ) {
	if( input & IN_GAS ) Vy += 400;
	if( input & IN_BRAKE ) Vy -= 400;
	if( input & IN_VOLT_LEFT ) Vx -= 6000;
	if( input & IN_VOLT_RIGHT ) Vx += 6000;
	Vx -= Vx >> 5;
	Vy -= Vy >> 5;
	Bike.body.rx += Vx;
	Bike.body.ry += Vy;
	Bike.body.alfa += 1ul << 16;
	for( uint8_t k = 0; k < 2; k++ ) {
		Bike.wheel[k].rx = Bike.body.rx+(k ? M_TO_F( 0.85 ) : -M_TO_F( 0.85 ));
		Bike.wheel[k].ry = Bike.body.ry-M_TO_F( 0.6 );
		Bike.wheel[k].alfa += 1ul << 18;
	}
	Bike.rider_x = Bike.body.rx;
	Bike.rider_y = Bike.body.ry+M_TO_F( 0.44 );
	Bike.head_x = Bike.rider_x;
	Bike.head_y = Bike.rider_y+M_TO_F( 0.63 );
	return 1;
}
