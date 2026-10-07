#include "sound.h"
#include <nes.h>
#include "fixmath.h"
#include "physconst.h"

#define APU_REG ((volatile uint8_t*)0x4000)

// The clock of the CPU, which the periods of the APU count:
#ifdef PAL_BUILD
#define CPU_HZ 1662607.0
#else
#define CPU_HZ 1789773.0
#endif
// Frames of NTSC in frames of the TV system:
#define FRAMES( n ) ((uint8_t)(((n)*PH_FPS+30)/60))

// The pitch of the engine rises with the driven wheel from 60 Hz at rest
// to 360 Hz at WHEEL_MAXW, in ENGINE_STEPS steps with the period
// interpolated between them: periods of the pulse channel,
// CPU_HZ/16/(period+1) Hz.
#define ENGINE_STEPS 128
#define ENGINE_PERIOD( i ) ((uint16_t)(CPU_HZ/16/(60.0+300.0*(i)/ENGINE_STEPS)-0.5))
#define P4( i ) ENGINE_PERIOD( i ), ENGINE_PERIOD( i+1 ), ENGINE_PERIOD( i+2 ), ENGINE_PERIOD( i+3 )
#define P16( i ) P4( i ), P4( i+4 ), P4( i+8 ), P4( i+12 )
#define P64( i ) P16( i ), P16( i+16 ), P16( i+32 ), P16( i+48 )
static const uint16_t Engine_period[ENGINE_STEPS+1] = {
	P64( 0 ), P64( 64 ), ENGINE_PERIOD( ENGINE_STEPS )
};
// 256ths of a step for 256 units of the angular velocity:
#define ENGINE_SCALE ((int16_t)(ENGINE_STEPS*65536L/WHEEL_MAXW))

// An effect: notes of (period, frames), period 0 ends it.
typedef struct {
	uint16_t period;
	uint8_t frames;
} note_t;

// A note of a period and frames of NTSC, in those of the TV system:
#define NOTE( p, n ) { (uint16_t)(((p)+1)*CPU_HZ/1789773.0-0.5), FRAMES( n ) }

static const note_t Fx_apple[] = {
	NOTE( 0x0d5, 3 ), NOTE( 0x0a9, 3 ), NOTE( 0x08e, 5 ), { 0, 0 }
};
static const note_t Fx_volt[] = { NOTE( 0x1c0, 2 ), NOTE( 0x160, 2 ), { 0, 0 } };
static const note_t Fx_turn[] = { NOTE( 0x0fe, 3 ), { 0, 0 } };
static const note_t Fx_win[] = {
	NOTE( 0x1ab, 6 ), NOTE( 0x153, 6 ), NOTE( 0x11d, 6 ), NOTE( 0x0d5, 12 ),
	NOTE( 0x11d, 6 ), NOTE( 0x0d5, 18 ), { 0, 0 }
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

void snd_frame( void ) {
	fx_step();
	if( Noise_left ) {
		Noise_left--;
		if( !Noise_left )
			APU_REG[0x0c] = 0x30;
	}
}

void snd_stop( void ) {
	APU_REG[0x00] = 0x30;
	APU_REG[0x04] = 0x30;
	APU_REG[0x0c] = 0x30;
	Engine_hi = 0xff;
	Fx = 0;
	Noise_left = 0;
}

void snd_engine( uint8_t gas, int16_t omega ) {
	if( !gas ) {
		APU_REG[0x00] = 0x30;
		Engine_hi = 0xff;
		return;
	}
	uint16_t w = omega < 0 ? -(uint16_t)omega : (uint16_t)omega;
	uint16_t period = Engine_period[ENGINE_STEPS];
	if( w < WHEEL_MAXW ) {
		uint16_t x = (uint16_t)(mul16( (int16_t)w, ENGINE_SCALE ) >> 8);
		const uint16_t* p = &Engine_period[x >> 8];
		period = p[0]-(uint16_t)(mul16( (int16_t)(p[0]-p[1]), x & 0xff ) >> 8);
	}
	APU_REG[0x00] = 0x76;
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
	Noise_left = FRAMES( 40 );
}

void snd_win( void ) {
	APU_REG[0x00] = 0x30;
	play( Fx_win );
}
