#include "sound.h"
#include <nes.h>
#include "fixmath.h"
#include "physconst.h"

#define APU_REG ((volatile uint8_t*)0x4000)

// The engine's periods at rest and at WHEEL_MAXW, and the fall of the
// period for 65536ths of WHEEL_MAXW:
#define ENGINE_LOW 930
#define ENGINE_HIGH 250
#define ENGINE_SLOPE ((int16_t)((ENGINE_LOW-ENGINE_HIGH)*65536L/WHEEL_MAXW))

// An effect: notes of (period, frames), period 0 ends it.
typedef struct {
	uint16_t period;
	uint8_t frames;
} note_t;

static const note_t Fx_apple[] = { { 0x0d5, 3 }, { 0x0a9, 3 }, { 0x08e, 5 }, { 0, 0 } };
static const note_t Fx_volt[] = { { 0x1c0, 2 }, { 0x160, 2 }, { 0, 0 } };
static const note_t Fx_turn[] = { { 0x0fe, 3 }, { 0, 0 } };
static const note_t Fx_win[] = {
	{ 0x1ab, 6 }, { 0x153, 6 }, { 0x11d, 6 }, { 0x0d5, 12 },
	{ 0x11d, 6 }, { 0x0d5, 18 }, { 0, 0 }
};

static const note_t* Fx;
static uint8_t Fx_left;
static uint8_t Noise_left;
static uint8_t Engine_hi = 0xff;

void snd_init( void ) {
	APU_REG[0x15] = 0x0b;   // pulse 1, pulse 2, noise
	APU_REG[0x17] = 0x40;
	APU_REG[0x01] = 0x08;   // no sweeps
	APU_REG[0x05] = 0x08;
	APU_REG[0x00] = 0x30;
	APU_REG[0x04] = 0x30;
	APU_REG[0x0c] = 0x30;
}

static void play( const note_t* fx ) {
	Fx = fx;
	Fx_left = 0;
}

static void fx_step( void ) {
	if( !Fx )
		return;
	if( Fx_left ) {
		Fx_left--;
		return;
	}
	if( !Fx->period ) {
		APU_REG[0x04] = 0x30;
		Fx = 0;
		return;
	}
	APU_REG[0x04] = 0xb8;
	APU_REG[0x06] = (uint8_t)Fx->period;
	APU_REG[0x07] = (uint8_t)(Fx->period >> 8) | 0x08;
	Fx_left = Fx->frames-1;
	Fx++;
}

void snd_engine( uint8_t gas, int16_t omega ) {
	fx_step();
	if( Noise_left ) {
		Noise_left--;
		if( !Noise_left )
			APU_REG[0x0c] = 0x30;
	}
	if( omega < 0 )
		omega = -omega;
	if( !gas && omega < 64 && Engine_hi == 0xfe ) {
		return;
	}
	// The pitch rises with the wheel, as the game's engine sound: from
	// about 120 Hz to about 450 Hz at the highest speed of the driven
	// wheel (periods of the pulse channel, 1789773/16/(period+1) Hz).
	int16_t period = ENGINE_LOW;
	if( omega >= WHEEL_MAXW )
		period = ENGINE_HIGH;
	else
		period -= (int16_t)(mul16( omega, ENGINE_SLOPE ) >> 16);
	APU_REG[0x00] = gas ? 0x76 : 0x73;
	APU_REG[0x02] = (uint8_t)period;
	uint8_t hi = (uint8_t)(period >> 8);
	if( hi != Engine_hi ) {
		Engine_hi = hi;
		APU_REG[0x03] = hi | 0x08;
	}
}

void snd_apple( void ) {
	play( Fx_apple );
}

void snd_volt( void ) {
	if( !Fx )
		play( Fx_volt );
}

void snd_turn( void ) {
	if( !Fx )
		play( Fx_turn );
}

void snd_death( void ) {
	APU_REG[0x00] = 0x30;
	APU_REG[0x0c] = 0x0f;   // a decaying noise
	APU_REG[0x0e] = 0x0c;
	APU_REG[0x0f] = 0x18;
	Noise_left = 40;
}

void snd_win( void ) {
	APU_REG[0x00] = 0x30;
	play( Fx_win );
}
