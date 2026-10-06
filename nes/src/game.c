// Playing a level.
#include "game.h"
#include <mapper.h>
#include <neslib.h>
#include "chrmap.h"
#include "far.h"
#include "fixmath.h"
#include "map.h"
#include "physics.h"
#include "segs.h"
#include "sound.h"
#include "sprites.h"
#include "video.h"

enum { T_FLOWER = 1, T_APPLE, T_KILLER, T_START };

#define MAX_OBJ 52
// Object radius plus wheel and head radius, squared, in u:
#define TOUCH_WHEEL ((int32_t)M_TO_U( 0.8 )*M_TO_U( 0.8 ))
#define TOUCH_HEAD ((int32_t)M_TO_U( 0.638 )*M_TO_U( 0.638 ))
// Objects farther than this from the body in x or y are not checked:
#define NEAR_U M_TO_U( 3.0 )
// A volt only 0.4 s of game time after the last one (Ugroturelem):
#define VOLT_WAIT ((uint8_t)(0.4/PH_H + 0.5))
// Hundredths of a second in a step: 1 and this many 65536ths:
#define TIME_FRAC ((uint16_t)((100.0/60.0988-1.0)*65536.0 + 0.5))

typedef struct {
	uint8_t type, grav, active;
	int32_t x, y;
} obj_t;

static obj_t Obj[MAX_OBJ] __attribute__((section( ".prg_ram.objects" )));
static uint8_t Nobj, Apples_left, Apples;
static uint32_t Time;
static uint16_t Tfrac;
static uint8_t Volt_wait;
static uint8_t Pad, Pad_old;
static uint8_t Frame;
level_t Level;

uint32_t Game_time;

static const uint8_t Pal_game[32] = {
	0x21, 0x07, 0x17, 0x2a,  0x21, 0x07, 0x17, 0x2a,
	0x21, 0x07, 0x17, 0x2a,  0x21, 0x07, 0x17, 0x2a,
	0x21, 0x0f, 0x16, 0x3d,  0x21, 0x0f, 0x12, 0x30,
	0x21, 0x16, 0x2a, 0x38,  0x21, 0x0f, 0x16, 0x30,
};

static int32_t u24( const uint8_t* p ) {
	return (int32_t)p[0] | (int32_t)p[1] << 8 | (int32_t)p[2] << 16;
}

static void load_objects( void ) {
	const uint8_t* p = far_ptr( Level.objects );
	Nobj = *p++;
	if( Nobj > MAX_OBJ )
		Nobj = MAX_OBJ;
	Apples = 0;
	for( uint8_t i = 0; i < Nobj; i++, p += 8 ) {
		obj_t* o = &Obj[i];
		o->type = p[0];
		o->grav = p[1];
		o->x = u24( p+2 );
		o->y = u24( p+5 );
		o->active = o->type != T_START;
		if( o->type == T_APPLE )
			Apples++;
	}
	Apples_left = Apples;
}

// Map pixels of a position in F:
static int16_t map_x( int32_t f ) {
	return (int16_t)(f >> 14);
}

static int16_t map_y( int32_t f ) {
	return (int16_t)Map_h-(int16_t)(f >> 14);
}

static void camera( uint8_t jump ) {
	int16_t x = map_x( Bike.body.rx )-128;
	int16_t y = map_y( Bike.body.ry )-128;
	int16_t maxx = (int16_t)Map_w-256, maxy = (int16_t)Map_h-240;
	if( x > maxx ) x = maxx;
	if( y > maxy ) y = maxy;
	if( x < 0 ) x = 0;
	if( y < 0 ) y = 0;
	if( !jump ) {
		// At most 8 pixels a frame, what the map can load:
		if( x > Cam_x+8 ) x = Cam_x+8;
		if( x < Cam_x-8 ) x = Cam_x-8;
		if( y > Cam_y+8 ) y = Cam_y+8;
		if( y < Cam_y-8 ) y = Cam_y-8;
	}
	Cam_x = x;
	Cam_y = y;
}

static void start_level( void ) {
	ppu_off();
	video_game( 0 );
	set_chr_mode_0( CHR_BG_COMMON );
	set_chr_mode_1( Level.chr );
	set_chr_mode_3( CHR_SPR_MISC );
	set_chr_mode_4( CHR_SPR_HUD );
	pal_all( Pal_game );
	load_objects();
	segs_start( &Level );
	ph_init( Level.start_x << 8, Level.start_y << 8 );
	Time = 0;
	Tfrac = 0;
	Volt_wait = 0;
	Frame = 0;
	camera( 1 );
	vram_adr( NAMETABLE_A );
	vram_fill( 0, 0x800 );
	map_start( &Level );
	scroll( (uint16_t)Cam_x & 511, (uint16_t)Cam_y % 240 );
	frame_begin();
	ppu_on_all();
	video_game( 1 );
}

// 0 if the bike died, 1 if it reached the flower, 2 if nothing happened.
static uint8_t touch_objects( void ) {
	int32_t bx = Bike.body.rx >> 8, by = Bike.body.ry >> 8;
	int32_t px[3], py[3];
	px[0] = Bike.wheel[0].rx >> 8;
	py[0] = Bike.wheel[0].ry >> 8;
	px[1] = Bike.wheel[1].rx >> 8;
	py[1] = Bike.wheel[1].ry >> 8;
	px[2] = Bike.head_x >> 8;
	py[2] = Bike.head_y >> 8;
	for( uint8_t i = 0; i < Nobj; i++ ) {
		obj_t* o = &Obj[i];
		if( !o->active )
			continue;
		int32_t dx = o->x-bx, dy = o->y-by;
		if( dx > NEAR_U || dx < -NEAR_U || dy > NEAR_U || dy < -NEAR_U )
			continue;
		for( uint8_t k = 0; k < 3; k++ ) {
			int16_t ex = (int16_t)(o->x-px[k]), ey = (int16_t)(o->y-py[k]);
			int32_t d2 = mul16( ex, ex )+mul16( ey, ey );
			if( d2 >= (k == 2 ? TOUCH_HEAD : TOUCH_WHEEL) )
				continue;
			if( o->type == T_KILLER )
				return 0;
			if( o->type == T_APPLE ) {
				o->active = 0;
				Apples_left--;
				switch( o->grav ) {
					case 1: Bike.gravity = GRAV_UP; break;
					case 2: Bike.gravity = GRAV_DOWN; break;
					case 3: Bike.gravity = GRAV_LEFT; break;
					case 4: Bike.gravity = GRAV_RIGHT; break;
				}
				snd_apple();
				break;
			}
			if( o->type == T_FLOWER && !Apples_left )
				return 1;
		}
	}
	return 2;
}

static void sprite( int16_t x, int16_t y, uint8_t tile, uint8_t attr ) {
	if( x < 0 || x > 255 || y < BAR_LINES-8 || y > 231 )
		return;
	oam_spr( (uint8_t)x, (uint8_t)(y-1), tile, attr );
}

static void sprite16( int16_t x, int16_t y, const uint8_t* t, uint8_t attr ) {
	sprite( x-8, y-8, t[0], attr );
	sprite( x, y-8, t[1], attr );
	sprite( x-8, y, t[2], attr );
	sprite( x, y, t[3], attr );
}

static void metasprite( int16_t x, int16_t y, const int8_t* m, uint8_t attr, uint8_t flip ) {
	uint8_t n = (uint8_t)*m++;
	for( ; n; n--, m += 3 ) {
		int16_t sx = flip ? x-m[0]-8 : x+m[0];
		sprite( sx, y+m[1], (uint8_t)m[2], attr );
	}
}

static void draw_bike( void ) {
	int16_t bx = map_x( Bike.body.rx )-Cam_x, by = map_y( Bike.body.ry )-Cam_y;
	uint8_t a = (uint8_t)((Bike.body.alfa + (1ul << 17)) >> 18) & 63;
	uint8_t flip = Bike.turned;
	if( flip )
		a = (64-a) & 63;
	video_bike_bank( CHR_SPR_BIKE+a );
	uint8_t attr = flip ? OAM_FLIP_H : 0;
	const int8_t* base = (const int8_t*)far_ptr( Bike_meta );
	const uint8_t* t = (const uint8_t*)base+4*a;
	metasprite( bx, by, base+(t[0] | (uint16_t)t[1] << 8), attr, flip );
	metasprite( map_x( Bike.rider_x )-Cam_x, map_y( Bike.rider_y )-Cam_y,
				base+(t[2] | (uint16_t)t[3] << 8), attr | 1, flip );
}

static void draw_wheels( void ) {
	for( uint8_t k = 0; k < 2; k++ ) {
		circle_t* w = &Bike.wheel[k];
		uint8_t f = (uint8_t)(w->alfa >> 19) & 7;
		sprite16( map_x( w->rx )-Cam_x, map_y( w->ry )-Cam_y, &Wheel_tiles[f*4], 0 );
	}
}

static void draw_objects( void ) {
	for( uint8_t i = 0; i < Nobj; i++ ) {
		obj_t* o = &Obj[i];
		if( !o->active )
			continue;
		int16_t x = (int16_t)(o->x >> 6)-Cam_x;
		int16_t y = (int16_t)Map_h-(int16_t)(o->y >> 6)-Cam_y;
		if( x < -8 || x > 264 || y < 0 || y > 248 )
			continue;
		switch( o->type ) {
			case T_APPLE:
				sprite16( x, y, Apple_tiles, 2 );
				break;
			case T_FLOWER:
				sprite16( x, y, Flower_tiles, 2 );
				break;
			case T_KILLER:
				sprite16( x, y, &Killer_tiles[((Frame >> 3) & 3)*4], 3 );
				break;
		}
	}
}

static void draw_hud( const char* msg ) {
	char s[9];
	if( msg )
		spr_text( 128-4*(uint8_t)__builtin_strlen( msg ), 4, msg );
	else {
		format_time( Time, s );
		spr_text( 96, 4, s );
	}
	if( Apples_left ) {
		oam_spr( 216, 219, Hud_font['@'-32], 2 );
		s[0] = Apples_left >= 10 ? '0'+Apples_left/10 : ' ';
		s[1] = '0'+Apples_left % 10;
		s[2] = 0;
		spr_text( 228, 220, s );
	}
}

static void draw( const char* msg ) {
	frame_begin();
	draw_hud( msg );
	if( Frame & 1 ) {
		draw_objects();
		draw_wheels();
		draw_bike();
	}
	else {
		draw_bike();
		draw_wheels();
		draw_objects();
	}
	map_scroll();
	scroll( (uint16_t)Cam_x & 511, (uint16_t)Cam_y % 240 );
	frame_end();
	Frame++;
}

static uint8_t pressed( uint8_t b ) {
	return (Pad & b) && !(Pad_old & b);
}

static void read_pad( void ) {
	Pad_old = Pad;
	Pad = pad_poll( 0 );
}

// Waits for A (1) or B (0), showing a message.
static uint8_t ask( const char* msg ) {
	for( ;; ) {
		read_pad();
		if( pressed( PAD_A ) || pressed( PAD_START ) )
			return 1;
		if( pressed( PAD_B ) || pressed( PAD_SELECT ) )
			return 0;
		static const char* const lines[3] = { 0, "A:AGAIN", "B:MENU" };
		uint8_t k = (Frame >> 6) % 3;
		draw( k ? lines[k] : msg );
	}
}

static uint8_t outside( void ) {
	int32_t x = Bike.body.rx, y = Bike.body.ry;
	return x < 0 || y < 0 || (x >> 14) >= (int32_t)Map_w || (y >> 14) >= (int32_t)Map_h;
}

uint8_t game_play( void ) {
	start_level();
	Pad = Pad_old = 0xff;
	for( ;; ) {
		read_pad();
		if( pressed( PAD_START ) ) {
			snd_engine( 0, 0 );
			for( ;; ) {
				read_pad();
				if( pressed( PAD_START ) )
					break;
				if( pressed( PAD_SELECT ) )
					return GAME_QUIT;
				draw( "PAUSE" );
			}
		}
		if( pressed( PAD_SELECT ) ) {
			start_level();
			continue;
		}
		uint8_t in = 0;
		if( Pad & (PAD_UP | PAD_B) )
			in |= IN_GAS;
		if( Pad & PAD_DOWN )
			in |= IN_BRAKE;
		if( Volt_wait )
			Volt_wait--;
		else if( Pad & (PAD_LEFT | PAD_RIGHT) ) {
			in |= (Pad & PAD_LEFT) ? IN_VOLT_LEFT : IN_VOLT_RIGHT;
			Volt_wait = VOLT_WAIT;
			snd_volt();
		}
		if( pressed( PAD_A ) ) {
			ph_turn();
			snd_turn();
		}
		uint8_t alive = ph_step( in );
		uint8_t result = 2;
		if( !alive || outside() )
			result = 0;
		else
			result = touch_objects();
		Time++;
		uint16_t f = Tfrac;
		Tfrac += TIME_FRAC;
		if( Tfrac < f )
			Time++;
		snd_engine( in & IN_GAS, Bike.wheel[Bike.turned ? 0 : 1].omega );
		camera( 0 );
		if( result == 0 ) {
			snd_engine( 0, 0 );
			snd_death();
			if( ask( "DEAD" ) ) {
				start_level();
				continue;
			}
			return GAME_QUIT;
		}
		if( result == 1 ) {
			snd_engine( 0, 0 );
			snd_win();
			Game_time = Time;
			for( uint8_t i = 0; i < 60; i++ )
				draw( "FINISHED" );
			return GAME_WON;
		}
		draw( 0 );
	}
}
