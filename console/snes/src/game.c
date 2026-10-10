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
#define FORGASIDO STEPS( 0.35 )  // the bike turns
#define UGROTUREL STEPS( 0.4 )   // the arm of a volt
// At most this many steps per drawing opportunity. Keep any remaining
// debt: a slow frame must never discard steps or advance the game clock.
#define MAXSTEPS 4

// The buttons of a level are those of Customize controls (save.keys);
// Start is the original's Esc:
#define BTN_ESC   JOY_START

typedef struct {
	s16 forgas_at;
	u8 hatra;
} side_t;

u8* game_keys;
u16 game_keys_n;

static side_t Side_f;
static s16 Steps;
static u32 Best;
extern s16 game_cam_x, game_cam_y;
#define Cam_x game_cam_x
#define Cam_y game_cam_y
// The time in hundredths, counted with the steps (100 a second):
static u32 Hs;
static u16 Hs_frac;
// part() of the durations by the steps elapsed, made at the start:
static u16 Forgas[FORGASIDO+1], Ugras[UGROTUREL+1], Render_alpha[60];
u16 game_phys_drop_count, game_phys_backlog_count, game_phys_backlog_max;

void game_render_reset(void);
void game_render_capture(void);
void game_render_previous(void);
void game_render_begin(u16 alpha);
void game_render_end(void);

static void side_reset( side_t* s, u8 hatra ) {
	s->forgas_at = -1000;
	s->hatra = hatra;
}

// baljobbelintez: 1 if the direction changed.
static u8 side_update( side_t* s, u8 hatra ) {
	if( s->hatra == hatra )
		return 0;
	s->forgas_at = Steps;
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

static void tables( u16 fps ) {
	s16 i;
	for( i = 0; i <= FORGASIDO; i++ )
		Forgas[i] = part( i, FORGASIDO );
	for( i = 0; i <= UGROTUREL; i++ )
		Ugras[i] = part( i, UGROTUREL );
	for( i = 0; i < fps; i++ )
		Render_alpha[i] = (u16)(((u32)(u16)i*256)/fps);
}

// A part of a duration from a table:
static u16 tpart( const u16* t, s16 elapsed, s16 total ) {
	if( elapsed <= 0 )
		return 0;
	if( elapsed >= total )
		return 65535;
	return t[elapsed];
}

// The centered camera uses the same pixel conversion as the map/bike.
void game_camera(u16 level);

static void draw( u16 level, u16 alpha ) {
	game_render_begin( alpha );
	game_camera( level );
	bike_anim.turn = tpart( Forgas, Steps-Side_f.forgas_at, FORGASIDO );
	if( phys_volt_age >= UGROTUREL )
		bike_anim.volt = 0;
	else
		bike_anim.volt = 65535-tpart( Ugras, phys_volt_age, UGROTUREL );
	bike_anim.volt1 = phys_volt1;
	hud_draw( Cam_x, Cam_y, 32768, Hs, Best );
	bike_draw( Cam_x, Cam_y );
	// Animated Objects: No shows their first frame, standing still:
	objects_draw( Cam_x, Cam_y, save.anim_objects ? (u16)Steps : 0 );
	game_render_end();
	// Sprites have first claim on the shared transfer budget. Map work uses
	// the time left after physics, HUD and OAM preparation.
	map_set_camera( Cam_x, Cam_y );
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
	u16 fps, frame_at, now, acc, n, ev, pad, edges, input, quick;
	u8 over = 0, gas = 0, k = 0;
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
	tables( fps );
	game_phys_drop_count = 0;
	game_phys_backlog_count = 0;
	game_phys_backlog_max = 0;
	game_render_reset();
	side_reset( &Side_f, phys_view.turned );
	game_camera( level );
	map_set_camera( Cam_x, Cam_y );
	map_detail = save.detail;
	map_load( level );
	bike_load();
	hud_load( level );
	draw( level, 256 );
	core_queue_reg( 0x2105, 0x01 );   // BGMODE: mode 1
	core_queue_reg( 0x212C, 0x13 );   // TM: BG1 BG2 OBJ
	core_screen_on( 15 );
	// Prepare physics while the initial picture waits for its first NMI.
	core_frame_submit();
	core_pad_take();
	frame_at = core_frame_count;
	acc = 0;

	while( !over ) {
		core_work_begin();
		pad = core_pad;
		edges = core_pad_take();
		if( edges & BTN_ESC ) {
			// Esc ends the level at once (no pause in the original):
			snd_stop();
			core_work_end();
			core_frame_wait();
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
		// Start the next scheduled frame while the prior picture awaits NMI.
		// The pending presentation bounds this lead; no steps are discarded.
		if( (s16)(now-frame_at) <= 0 )
			now = frame_at+1;
		acc += (now-frame_at)*PHYS_HZ;
		frame_at = now;
		n = 0;
		while( acc >= fps ) {
			if( n == MAXSTEPS ) {
				game_phys_backlog_count++;
				if( acc > game_phys_backlog_max )
					game_phys_backlog_max = acc;
				break;
			}
			acc -= fps;
			n++;
			if( game_keys_n ) {
				k = 0;
				if( (u16)Steps < game_keys_n )
					k = game_keys[Steps];
				input = k & (PH_GAS | PH_BRAKE | PH_VOLT_R | PH_VOLT_L);
				gas = k & PH_GAS;
			}
			quick = acc >= fps && n < MAXSTEPS;
			if( !quick ) {
				if( n == 1 )
					game_render_previous();
				else
					game_render_capture();
			}
			ev = phys_step( input | (quick ? PH_QUICK : 0) );
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
			if( k & GAME_TURN )
				phys_turn();
			Steps++;
			Hs_frac += 100;
			while( Hs_frac >= PHYS_HZ ) {
				Hs_frac -= PHYS_HZ;
				Hs++;
			}
		}
		if( over ) {
			// A terminal event can occur on a quick step. Publish its actual
			// final pose, without another simulation step.
			phys_read_view();
			core_frame_wait();
			draw( level, 256 );
			core_work_end();
			core_frame_done();
			break;
		}

		// The turn animation follows the physical direction.
		if( side_update( &Side_f, phys_view.turned ) )
			effect( SND_TURN, SND_VOL_EFFECT );
		// Previous OAM/DMA shadows stay immutable until their NMI consumed them.
		core_frame_wait();
		draw( level, acc < fps ? Render_alpha[acc] : 256 );
		sound( gas );
		core_work_end();
		core_frame_submit();
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
