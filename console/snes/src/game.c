// Playing a level, after LEJATSZO.CPP of the original game: the steps of
// the physics, the turn of the bike, the camera, drawing and sound.
#include <snes.h>
#include "core.h"
#include "levels.h"
#include "phys.h"
#include "map.h"
#include "bike.h"
#include "hud.h"
#include "snd.h"
#include "save.h"
#include "game.h"

// The game counts its time in steps of the physics, PHYS_HZ a second of
// the clock; a second of the clock is 0.4368 units of the game's time.
// The durations of the original in steps:
#define STEPS( t ) ((s16)((t)*PHYS_HZ/0.4368+0.5))
#define FORDIDO   STEPS( 0.5 )   // the camera moves over after a turn
#define FORGASIDO STEPS( 0.35 )  // the bike turns
#define UGROTUREL STEPS( 0.4 )   // the arm of a volt
// At most this many steps in a frame; beyond it the game slows down:
#define MAXSTEPS 4

// The buttons of a level are those of Customize controls (save.keys);
// Start is the original's Esc:
#define BTN_ESC   JOY_START

// baljobbvaltozok of the original: the step of the last turn, the step the
// move of the camera counts from, and the direction (hatra).
typedef struct {
	s16 forgas_at, ford_at;
	u8 hatra;
} side_t;

static side_t Side_f, Side_h;
static s16 Steps;
static u32 Best;
static s16 Cam_x, Cam_y;
// The time in hundredths, counted with the steps (100 a second):
static u32 Hs;
static u16 Hs_frac;
// part() of the durations by the steps elapsed, made at the start:
static u16 Ford[FORDIDO+1], Forgas[FORGASIDO+1], Ugras[UGROTUREL+1];

static void side_reset( side_t* s, u8 hatra ) {
	s->forgas_at = -1000;
	s->ford_at = -1000;
	s->hatra = hatra;
}

// baljobbelintez: 1 if the direction changed.
static u8 side_update( side_t* s, u8 hatra ) {
	s16 elapsed;
	if( s->hatra == hatra )
		return 0;
	s->forgas_at = Steps;
	elapsed = Steps-s->ford_at;
	if( elapsed < FORDIDO )
		s->ford_at = Steps+elapsed-FORDIDO;
	else
		s->ford_at = Steps;
	s->hatra = hatra;
	return 1;
}

// A part of a duration as 0..65535 (slow: for the tables):
static u16 part( s16 elapsed, s16 total ) {
	u32 v;
	if( elapsed <= 0 )
		return 0;
	if( elapsed >= total )
		return 65535;
	v = (u32)(u16)elapsed*65535;
	return (u16)(v/(u16)total);
}

static void tables( void ) {
	s16 i;
	for( i = 0; i <= FORDIDO; i++ )
		Ford[i] = part( i, FORDIDO );
	for( i = 0; i <= FORGASIDO; i++ )
		Forgas[i] = part( i, FORGASIDO );
	for( i = 0; i <= UGROTUREL; i++ )
		Ugras[i] = part( i, UGROTUREL );
}

// A part of a duration from a table:
static u16 tpart( const u16* t, s16 elapsed, s16 total ) {
	if( elapsed <= 0 )
		return 0;
	if( elapsed >= total )
		return 65535;
	return t[elapsed];
}

// baljobbszamol, 0..65535 for 0..1:
static u16 side_baljobb( side_t* s ) {
	u16 v = tpart( Ford, Steps-s->ford_at, FORDIDO );
	if( s->hatra )
		return 65535-v;
	return v;
}

// The camera: the left edge of the picture is Mo_bal + baljobb*Mo_dx left
// of the bike's body (15 % of the width, 85 % when baljobb is 1), its
// middle row at the body (KIRAJ320.CPP beallitmereteket, kirakegyjatekost).
#define MO_BAL 38   // 0.15*256
#define MO_DX  179  // 256-2*38.4

// game_math.asm: (a*b) >> 16, and the level pixels of a distance in 16.16
// meters ((d*4915) >> 24, levgeom.py):
u16 game_mulhi(u16 a, u16 b);
u16 game_px(u32 d);

static void camera( u16 level, u16 baljobb ) {
	const level_geom_t* g = &level_geom[level];
	u32 d;
	s16 bx, by;
	d = (u32)(phys_view.body_x-g->org_x);
	bx = (s16)game_px( d );
	d = (u32)(g->org_y-phys_view.body_y);
	by = (s16)game_px( d );
	Cam_x = bx-MO_BAL-(s16)game_mulhi( baljobb, MO_DX );
	Cam_y = by-112;
}

static void draw( u16 level ) {
	u16 baljobb = side_baljobb( &Side_h );
	camera( level, baljobb );
	bike_anim.turn = tpart( Forgas, Steps-Side_f.forgas_at, FORGASIDO );
	if( phys_volt_age >= UGROTUREL )
		bike_anim.volt = 0;
	else
		bike_anim.volt = 65535-tpart( Ugras, phys_volt_age, UGROTUREL );
	bike_anim.volt1 = phys_volt1;
	map_set_camera( Cam_x, Cam_y );
	hud_draw( Cam_x, Cam_y, baljobb, Hs, Best );
	bike_draw( Cam_x, Cam_y );
	// Animated Objects: No shows their first frame, standing still:
	objects_draw( Cam_x, Cam_y, save.anim_objects ? (u16)Steps : 0 );
}

static void sound( u8 gas ) {
	if( save.sound )
		snd_frame( gas, phys_wheel_omega, phys_friction >> 8 );
}

static void effect( u16 id, u16 volume ) {
	if( save.sound )
		snd_effect( id, volume );
}

u32 game_play( u16 level, u8* finished ) {
	u16 fps, frame_at, now, acc, n, ev, pad, edges, input;
	u8 over = 0, gas = 0;
	u32 time = 0;

	*finished = 0;
	fps = snes_50hz ? 50 : 60;
	Best = save_best( level );
	core_screen_off();
	core_oam_clear();
	phys_level( level );
	objects_load( level );
	Steps = 0;
	Hs = 0;
	Hs_frac = 0;
	tables();
	side_reset( &Side_f, phys_view.turned );
	side_reset( &Side_h, phys_view.gravity == 0 ? !phys_view.turned : phys_view.turned );
	camera( level, side_baljobb( &Side_h ) );
	map_set_camera( Cam_x, Cam_y );
	map_detail = save.detail;
	map_load( level );
	bike_load();
	hud_load( level );
	draw( level );
	core_queue_reg( 0x2105, 0x09 );   // BGMODE: mode 1, BG3 on top
	core_queue_reg( 0x212C, 0x17 );   // TM: BG1 BG2 BG3 OBJ
	core_screen_on( 15 );
	core_frame_done();
	core_pad_take();
	frame_at = core_frame_count;
	acc = 0;

	while( !over ) {
		pad = core_pad;
		edges = core_pad_take();
		if( edges & BTN_ESC ) {
			// Esc ends the level at once (no pause in the original):
			snd_stop();
			return 0;
		}
		if( edges & save.keys[KEY_VIEW] )
			hud_show_map = !hud_show_map;
		if( edges & save.keys[KEY_TIME] )
			hud_show_time = !hud_show_time;
		if( edges & save.keys[KEY_TURN] )
			phys_turn();
		gas = (pad & save.keys[KEY_GAS]) ? 1 : 0;
		input = 0;
		if( gas )
			input |= PH_GAS;
		if( pad & save.keys[KEY_BRAKE] )
			input |= PH_BRAKE;
		if( pad & save.keys[KEY_RIGHT] )
			input |= PH_VOLT_R;
		if( pad & save.keys[KEY_LEFT] )
			input |= PH_VOLT_L;

		// The steps due since the last frame, PHYS_HZ a second:
		now = core_frame_count;
		acc += (now-frame_at)*PHYS_HZ;
		frame_at = now;
		n = 0;
		while( acc >= fps ) {
			acc -= fps;
			if( n == MAXSTEPS ) {
				acc = 0;
				break;
			}
			n++;
			ev = phys_step( input );
			if( ev & PH_EAT )
				effect( SND_EAT, SND_VOL_EFFECT );
			if( ev & PH_BUMP )
				effect( SND_BUMP, phys_bump );
			if( ev & PH_VOLT )
				effect( phys_volt1 ? SND_VOLT1 : SND_VOLT2, SND_VOL_EFFECT );
			if( ev & PH_FINISH ) {
				*finished = 1;
				time = Hs;
				over = 1;
				break;
			}
			if( ev & PH_DEAD ) {
				over = 1;
				break;
			}
			Steps++;
			Hs_frac += 100;
			while( Hs_frac >= PHYS_HZ ) {
				Hs_frac -= PHYS_HZ;
				Hs++;
			}
		}
		if( over )
			break;

		// kulsoresz: the turn, the camera after it:
		if( side_update( &Side_f, phys_view.turned ) )
			effect( SND_TURN, SND_VOL_EFFECT );
		side_update( &Side_h, phys_view.gravity == 0 ? !phys_view.turned : phys_view.turned );
		draw( level );
		sound( gas );
		core_frame_done();
	}

	// The last picture stays for a second with the sound of the end:
	effect( *finished ? SND_WIN : SND_DEAD, SND_VOL_END );
	for( n = 0; n < fps; n++ ) {
		sound( 0 );
		core_frame_done();
	}
	snd_stop();
	return time;
}
