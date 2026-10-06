// Playing a level.
//
// The physics takes a step for each frame of the NMI's count, and a frame
// is drawn after a step when the last one went out: when the steps take
// longer, fewer frames are drawn, and more than a few frames behind the
// game slows down.
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
// Objects farther than this from the body in x or y are not checked (map
// pixels, 16 a meter), and from a wheel or the head:
#define NEAR_PX 48
#define TOUCH_PX 14
// A volt only 0.4 s of game time after the last one (Ugroturelem):
#define VOLT_WAIT ((uint8_t)(0.4/PH_H + 0.5))
// Hundredths of a second in a step: 1 and this many 65536ths:
#define TIME_FRAC ((uint16_t)((100.0/PH_RATE-1.0)*65536.0 + 0.5))
// Steps at most behind the frames before the game slows down:
#define MAX_BEHIND 3
// The sprites of a frame at most, so that Oam_n does not wrap:
#define OAM_FULL 252

typedef struct {
	uint8_t type, grav, active;
	int32_t x, y;        // u
	int16_t px, py;      // map pixels, y up
} obj_t;

static obj_t Obj[MAX_OBJ] __attribute__((section( ".prg_ram.objects" )));
static uint8_t Nobj, Apples_left, Apples;
static uint32_t Time;
static uint16_t Tfrac;
// The time as shown: minutes, seconds and hundredths in decimal digits:
static uint8_t Digits[6];
static uint8_t Volt_wait;
static uint8_t Pad, Pad_old;
static uint8_t Frame;
// The frame count of the NMI up to which the steps were counted, the steps
// due in 60ths (PH_HZ a frame), and the steps since the last frame drawn:
static uint8_t Clock, Skipped;
static uint16_t Due;
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
	obj_t* o = Obj;
	for( uint8_t i = 0; i < Nobj; i++, p += 8, o++ ) {
		o->type = p[0];
		o->grav = p[1];
		o->x = u24( p+2 );
		o->y = u24( p+5 );
		o->px = (int16_t)(o->x >> 6);
		o->py = (int16_t)(o->y >> 6);
		o->active = o->type != T_START;
		if( o->type == T_APPLE )
			Apples++;
	}
	Apples_left = Apples;
}

// Map pixels of a position in F (y down):
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
	// The split off first: its table, run at each NMI, would turn the
	// sprites back on while the screen is written.
	video_game( 0 );
	ppu_off();
	sprites_off();
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
	for( uint8_t i = 0; i < 6; i++ )
		Digits[i] = 0;
	Volt_wait = 0;
	Frame = 0;
	// The size of the map first, which bounds the camera:
	map_level( &Level );
	camera( 1 );
	vram_adr( NAMETABLE_A );
	vram_fill( 0, 0x800 );
	map_start();
	scroll( (uint16_t)Cam_x & 511, (uint16_t)Cam_y % 240 );
	frame_begin();
	ppu_on_all();
	video_game( 1 );
	Clock = FRAME_CNT1;
	Due = 0;
}

// Adds n hundredths to the time shown, up to 99:59:99.
static void add_time( uint8_t n ) {
	uint8_t* d = Digits;
	d[5] += n;
	if( d[5] < 10 )
		return;
	d[5] -= 10;
	if( ++d[4] < 10 )
		return;
	d[4] = 0;
	if( ++d[3] < 10 )
		return;
	d[3] = 0;
	if( ++d[2] < 6 )
		return;
	d[2] = 0;
	if( ++d[1] < 10 )
		return;
	d[1] = 0;
	if( ++d[0] < 10 )
		return;
	for( uint8_t i = 0; i < 6; i++ )
		d[i] = i == 2 ? 5 : 9;
}

// The wheels and the head, in u and in map pixels, for touch_objects (not
// on the stack, which is slow):
static int32_t Px[3], Py[3];
static int16_t Qx[3], Qy[3];

// 0 if the bike died, 1 if it reached the flower, 2 if nothing happened.
static uint8_t touch_objects( void ) {
	int16_t bpx = (int16_t)(Bike.body.rx >> 14), bpy = (int16_t)(Bike.body.ry >> 14);
	uint8_t points = 0;
	obj_t* o = Obj;
	for( uint8_t i = Nobj; i; i--, o++ ) {
		if( !o->active )
			continue;
		int16_t dx = o->px-bpx, dy = o->py-bpy;
		if( dx > NEAR_PX || dx < -NEAR_PX || dy > NEAR_PX || dy < -NEAR_PX )
			continue;
		if( !points ) {
			Px[0] = Bike.wheel[0].rx >> 8;
			Py[0] = Bike.wheel[0].ry >> 8;
			Px[1] = Bike.wheel[1].rx >> 8;
			Py[1] = Bike.wheel[1].ry >> 8;
			Px[2] = Bike.head_x >> 8;
			Py[2] = Bike.head_y >> 8;
			for( uint8_t k = 0; k < 3; k++ ) {
				Qx[k] = (int16_t)(Px[k] >> 6);
				Qy[k] = (int16_t)(Py[k] >> 6);
			}
			points = 1;
		}
		for( uint8_t k = 0; k < 3; k++ ) {
			// Within TOUCH_PX in x and y first (0.8 m is 12.8 pixels):
			int16_t ex = o->px-Qx[k], ey = o->py-Qy[k];
			if( ex > TOUCH_PX || ex < -TOUCH_PX || ey > TOUCH_PX || ey < -TOUCH_PX )
				continue;
			ex = (int16_t)(o->x-Px[k]);
			ey = (int16_t)(o->y-Py[k]);
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

// --- Drawing ----------------------------------------------------------------

// A sprite at a position on the screen that may be off it:
static void sprite( int16_t x, int16_t y, uint8_t tile, uint8_t attr ) {
	if( x < 0 || x > 255 || y < BAR_LINES-8 || y > 231 )
		return;
	spr( (uint8_t)x, (uint8_t)(y-1), tile, attr );
}

// Four tiles around x, y:
static void sprite16( int16_t x, int16_t y, const uint8_t* t, uint8_t attr ) {
	if( x >= 8 && x <= 247 && y >= BAR_LINES && y <= 231 ) {
		uint8_t sx = (uint8_t)x-8, sy = (uint8_t)y-9;
		spr( sx, sy, t[0], attr );
		spr( sx+8, sy, t[1], attr );
		spr( sx, sy+8, t[2], attr );
		spr( sx+8, sy+8, t[3], attr );
		return;
	}
	sprite( x-8, y-8, t[0], attr );
	sprite( x, y-8, t[1], attr );
	sprite( x-8, y, t[2], attr );
	sprite( x, y, t[3], attr );
}

// The sprites of m (their number, then x, y and tile of each) around x, y,
// mirrored if flip. Their offsets are from -24 to 16 (gfx.py): nearer the
// edges each one is checked.
static void metasprite( int16_t x, int16_t y, const int8_t* m, uint8_t attr, uint8_t flip ) {
	uint8_t n = (uint8_t)*m++;
	if( x >= 24 && x <= 239 && y >= BAR_LINES-8+24 && y <= 231-16 ) {
		uint8_t sy = (uint8_t)y-1;
		uint8_t i = Oam_n;
		if( flip ) {
			uint8_t sx = (uint8_t)x-8;
			for( ; n; n--, m += 3 ) {
				OAM_BUF[i] = sy+(uint8_t)m[1];
				OAM_BUF[i+1] = (uint8_t)m[2];
				OAM_BUF[i+2] = attr;
				OAM_BUF[i+3] = sx-(uint8_t)m[0];
				i += 4;
			}
		}
		else {
			uint8_t sx = (uint8_t)x;
			for( ; n; n--, m += 3 ) {
				OAM_BUF[i] = sy+(uint8_t)m[1];
				OAM_BUF[i+1] = (uint8_t)m[2];
				OAM_BUF[i+2] = attr;
				OAM_BUF[i+3] = sx+(uint8_t)m[0];
				i += 4;
			}
		}
		Oam_n = i;
		return;
	}
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
	obj_t* o = Obj;
	for( uint8_t i = Nobj; i; i--, o++ ) {
		if( !o->active || Oam_n > OAM_FULL-16 )
			continue;
		int16_t x = o->px-Cam_x;
		if( x < -8 || x > 264 )
			continue;
		int16_t y = (int16_t)Map_h-o->py-Cam_y;
		if( y < 0 || y > 248 )
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

#define DIGIT( d ) (Hud_font['0'-32]+(d))

// The lines of the time and the messages, and of the apples left, within
// the part of the picture a television surely shows (16 lines from the top
// and the bottom); as OAM coordinates, a line less:
#define HUD_TOP (16-1)
#define HUD_BOTTOM (240-16-8-8-1)

static void draw_hud( const char* msg ) {
	if( msg )
		spr_text( 128-4*(uint8_t)__builtin_strlen( msg ), HUD_TOP, msg );
	else {
		static const uint8_t X[6] = { 96, 104, 120, 128, 144, 152 };
		for( uint8_t i = 0; i < 6; i++ )
			spr( X[i], HUD_TOP, DIGIT( Digits[i] ), 3 );
		spr( 112, HUD_TOP, Hud_font[':'-32], 3 );
		spr( 136, HUD_TOP, Hud_font[':'-32], 3 );
	}
	if( Apples_left ) {
		uint8_t tens = 0, n = Apples_left;
		while( n >= 10 ) {
			n -= 10;
			tens++;
		}
		spr( 208, HUD_BOTTOM-1, Hud_font['@'-32], 2 );
		if( tens )
			spr( 220, HUD_BOTTOM, DIGIT( tens ), 3 );
		spr( 228, HUD_BOTTOM, DIGIT( n ), 3 );
	}
}

// Draws a frame of the game and hands it to the NMI.
static void draw( const char* msg ) {
	camera( 0 );
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
	frame_show();
	Frame++;
}

// The same, waiting until it is shown.
static void draw_wait( const char* msg ) {
	draw( msg );
	while( !frame_ready() )
		;
}

static uint8_t pressed( uint8_t b ) {
	return (Pad & b) && !(Pad_old & b);
}

// The first pad, read once: without samples of the DPCM channel, which may
// spoil a read, neslib's pad_poll reading it again is not needed.
static void read_pad( void ) {
	Pad_old = Pad;
	volatile uint8_t* port = (volatile uint8_t*)0x4016;
	*port = 1;
	*port = 0;
	uint8_t b = 0;
	for( uint8_t i = 0; i < 8; i++ )
		b = (uint8_t)(b << 1) | (*port & 1);
	Pad = b;
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
		draw_wait( k ? lines[k] : msg );
	}
}

static uint8_t outside( void ) {
	int32_t x = Bike.body.rx, y = Bike.body.ry;
	return x < 0 || y < 0 || (x >> 14) >= (int32_t)Map_w || (y >> 14) >= (int32_t)Map_h;
}

enum { STEP_ON, STEP_DEAD, STEP_WON, STEP_QUIT, STEP_RESTART };

// A step of the game: the pad, the physics, the objects and the time.
static uint8_t step( void ) {
	read_pad();
	if( pressed( PAD_START ) ) {
		snd_engine( 0, 0 );
		for( ;; ) {
			read_pad();
			if( pressed( PAD_START ) )
				break;
			if( pressed( PAD_SELECT ) )
				return STEP_QUIT;
			draw_wait( "PAUSE" );
		}
		Clock = FRAME_CNT1;
		Due = 0;
	}
	if( pressed( PAD_SELECT ) )
		return STEP_RESTART;
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
	uint8_t n = 1;
	uint16_t f = Tfrac;
	Tfrac += TIME_FRAC;
	if( Tfrac < f )
		n = 2;
	Time += n;
	add_time( n );
	snd_engine( in & IN_GAS, Bike.wheel[Bike.turned ? 0 : 1].omega );
	if( result == 0 )
		return STEP_DEAD;
	if( result == 1 )
		return STEP_WON;
	return STEP_ON;
}

uint8_t game_play( void ) {
	start_level();
	Pad = Pad_old = 0xff;
	for( ;; ) {
		for( uint8_t now = FRAME_CNT1; Clock != now; Clock++ ) {
			Due += PH_HZ;
			// A loop, mostly once: not a multiplication by the library.
			asm volatile( "" );
		}
		if( Due < 60 )
			continue;
		if( Due > MAX_BEHIND*60 )
			Due = MAX_BEHIND*60;
		Due -= 60;
		switch( step() ) {
			case STEP_QUIT:
				return GAME_QUIT;
			case STEP_RESTART:
				start_level();
				continue;
			case STEP_DEAD:
				snd_engine( 0, 0 );
				snd_death();
				if( ask( "DEAD" ) ) {
					start_level();
					continue;
				}
				return GAME_QUIT;
			case STEP_WON:
				snd_engine( 0, 0 );
				snd_win();
				Game_time = Time;
				for( uint8_t i = 0; i < 60; i++ )
					draw_wait( "FINISHED" );
				return GAME_WON;
		}
		// A frame when the last one went out; while catching up with more
		// than a step, after every other step:
		if( frame_ready() && (Due < 60 || ++Skipped > 1) ) {
			draw( 0 );
			Skipped = 0;
		}
	}
}
