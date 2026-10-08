// Test ROM of the sounds. First a fixed sequence (about 23 s): the start of
// the engine and its idle, the gas with the wheel speeding up, the idle
// again, the gas at a steady speed, the friction rising and falling, every
// effect one by one, seven hits at once (five play), a stop and a new
// start. Then the buttons: B gas (the wheel speeds up while it is held),
// UP friction, A apple, Y hit, X turn, L and R volt, SELECT flower, START
// death, START+SELECT stop. The backdrop shows the part of the sequence.
#include <snes.h>
#include "core.h"
#include "snd.h"

// The frames of the sequence:
#define T_GAS1    90
#define T_IDLE2   270
#define T_GAS2    390
#define T_FRIC    510
#define T_FRICTOP 600
#define T_FRICEND 690
#define T_EFFECTS 700
#define T_BURST   1100
#define T_STOP    1160
#define T_AGAIN   1220
#define T_STOP2   1300
#define T_MANUAL  1320

static const u16 Colors[6] = {
	0x0000, 0x001F, 0x03E0, 0x7C00, 0x03FF, 0x7FFF
};

static u16 Color;
static u16 Frame;
static u16 Omega;

// Marks the return from snd_frame for the measurements (test/snd_cpu.lua).
void snd_test_mark(void) {
}

static void backdrop(u16 c) {
	if( c != Color ) {
		Color = c;
		core_queue_cgram(0, &Colors[c], 2);
	}
}

// The effects of the sequence, one every 50 frames:
static const u16 Ids[8] = { SND_EAT, SND_BUMP, SND_BUMP, SND_TURN,
	SND_VOLT1, SND_VOLT2, SND_WIN, SND_DEAD };
static const u16 Vols[8] = { SND_VOL_EFFECT, 64, 250, SND_VOL_EFFECT,
	SND_VOL_EFFECT, SND_VOL_EFFECT, SND_VOL_END, SND_VOL_END };

// The effect of the sequence at frame f, 0 if none.
static u16 effect_at(u16 f, u16* vol) {
	u16 k;
	if( f < T_EFFECTS || f >= T_EFFECTS+8*50 )
		return 0;
	f -= T_EFFECTS;
	if( f%50 )
		return 0;
	k = f/50;
	*vol = Vols[k];
	return Ids[k];
}

static void sequence(void) {
	u16 gas = 0, fric = 0, id, vol, i;
	if( Frame < T_GAS1 ) {
		backdrop(0);
		Omega = 0;
	}
	else if( Frame < T_IDLE2 ) {
		// The wheel from 0 to 200 rad a time unit in 3 s:
		backdrop(1);
		gas = 1;
		Omega = (Frame-T_GAS1)*284;
	}
	else if( Frame < T_GAS2 ) {
		backdrop(0);
		Omega = 0;
	}
	else if( Frame < T_FRIC ) {
		backdrop(1);
		gas = 1;
		Omega = 50*256;
	}
	else if( Frame < T_FRICEND ) {
		// The friction up to 1.25 and back:
		backdrop(2);
		Omega = 0;
		if( Frame < T_FRICTOP )
			fric = (Frame-T_FRIC)*4;
		else
			fric = (T_FRICEND-Frame)*4;
	}
	else
		backdrop(3);
	if( Frame >= T_STOP && Frame < T_AGAIN ) {
		if( Frame == T_STOP )
			snd_stop();
		return;
	}
	if( Frame >= T_STOP2 ) {
		if( Frame == T_STOP2 )
			snd_stop();
		return;
	}
	snd_frame(gas, Omega, fric);
	snd_test_mark();
	id = effect_at(Frame, &vol);
	if( id )
		snd_effect(id, vol);
	if( Frame == T_BURST ) {
		for( i = 0; i < 7; i++ )
			snd_effect(SND_BUMP, 200);
	}
}

static void manual(void) {
	u16 pad = core_pad, edges = core_pad_take();
	u8 gas = (pad & JOY_B) != 0;
	if( (pad & (JOY_START|JOY_SELECT)) == (JOY_START|JOY_SELECT) ) {
		snd_stop();
		backdrop(5);
		return;
	}
	if( gas ) {
		if( Omega < 60000 )
			Omega += 200;
	}
	else if( Omega >= 400 )
		Omega -= 400;
	else
		Omega = 0;
	backdrop(gas ? 1 : 4);
	snd_frame(gas, Omega, (pad & JOY_UP) ? 256 : 0);
	if( edges & JOY_A )
		snd_effect(SND_EAT, SND_VOL_EFFECT);
	if( edges & JOY_Y )
		snd_effect(SND_BUMP, 200);
	if( edges & JOY_X )
		snd_effect(SND_TURN, SND_VOL_EFFECT);
	if( edges & JOY_L )
		snd_effect(SND_VOLT1, SND_VOL_EFFECT);
	if( edges & JOY_R )
		snd_effect(SND_VOLT2, SND_VOL_EFFECT);
	if( (edges & JOY_SELECT) && !(pad & JOY_START) )
		snd_effect(SND_WIN, SND_VOL_END);
	if( (edges & JOY_START) && !(pad & JOY_SELECT) )
		snd_effect(SND_DEAD, SND_VOL_END);
}

int main(void) {
	consoleInit();
	core_init();
	snd_init();
	Color = 0xFFFF;
	backdrop(0);
	core_screen_on(15);
	core_pad_take();
	Frame = 0;
	while( 1 ) {
		if( Frame < T_MANUAL )
			sequence();
		else
			manual();
		core_frame_done();
		Frame++;
	}
	return 0;
}
