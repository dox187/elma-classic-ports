// The title, the list of the levels and the results of a level, in a bank
// of their own with the table of the levels, called with banked_call.
#include "menu.h"
#include <mapper.h>
#include <neslib.h>
#include "chrmap.h"
#include "game.h"
#include "levels.h"
#include "save.h"
#include "sprites.h"
#include "video.h"

#pragma clang section text=".prg_rom_60.text" rodata=".prg_rom_60.rodata"

#define PAGE 20

uint8_t Menu_level, Menu_best, Menu_choice;

static const uint8_t Pal_menu[32] = {
	0x0f, 0x00, 0x16, 0x30,  0x0f, 0x00, 0x16, 0x30,
	0x0f, 0x00, 0x16, 0x30,  0x0f, 0x00, 0x16, 0x30,
	0x0f, 0x0f, 0x16, 0x3d,  0x0f, 0x0f, 0x12, 0x30,
	0x0f, 0x16, 0x2a, 0x38,  0x0f, 0x00, 0x16, 0x30,
};

static uint8_t Pad, Pad_old;

static void read_pad( void ) {
	Pad_old = Pad;
	Pad = pad_poll( 0 );
}

static uint8_t pressed( uint8_t b ) {
	return (Pad & b) && !(Pad_old & b);
}

// Starts drawing a screen of the menus (rendering off).
static void screen( void ) {
	ppu_off();
	video_game( 0 );
	sprites_off();
	set_chr_mode_0( CHR_BG_MENU );
	set_chr_mode_1( CHR_BG_MENU+2 );
	set_chr_mode_4( CHR_SPR_HUD );
	pal_all( Pal_menu );
	scroll( 0, 0 );
	vram_adr( NAMETABLE_A );
	vram_fill( ' ', 960 );
	vram_fill( 0, 64 );
	Pad = Pad_old = 0xff;
}

static void show( void ) {
	frame_begin();
	ppu_on_all();
	frame_end();
}

// Text at a column and row; dim is added to the codes of the letters.
static void text( uint8_t x, uint8_t y, const char* s, uint8_t dim ) {
	vram_adr( NTADR_A( x, y ) );
	for( ; *s; s++ ) {
		uint8_t c = (uint8_t)*s;
		if( c >= 'a' && c <= 'z' )
			c -= 32;
		if( c < 32 || c > 95 )
			c = '?';
		vram_put( c == ' ' ? c : c+dim );
	}
}

static uint8_t length( const char* s ) {
	uint8_t n = 0;
	while( s[n] )
		n++;
	return n;
}

static void center( uint8_t y, const char* s ) {
	text( (uint8_t)(16-length( s )/2), y, s, 0 );
}

static void big( uint8_t x, uint8_t y, const char* s ) {
	static const char letters[] = "ELASTOMNI";
	for( ; *s; s++, x += 2 ) {
		uint8_t t = 0;
		for( uint8_t i = 0; letters[i]; i++ )
			if( letters[i] == *s )
				t = TITLE_E+4*i;
		if( !t )
			continue;
		vram_adr( NTADR_A( x, y ) );
		vram_put( t );
		vram_put( t+1 );
		vram_adr( NTADR_A( x, y+1 ) );
		vram_put( t+2 );
		vram_put( t+3 );
	}
}

static void frame_box( uint8_t x0, uint8_t y0, uint8_t x1, uint8_t y1 ) {
	vram_adr( NTADR_A( x0, y0 ) );
	vram_put( MENU_FRAME );
	for( uint8_t x = x0+1; x < x1; x++ )
		vram_put( MENU_FRAME+1 );
	vram_put( MENU_FRAME+2 );
	for( uint8_t y = y0+1; y < y1; y++ ) {
		vram_adr( NTADR_A( x0, y ) );
		vram_put( MENU_FRAME+3 );
		vram_adr( NTADR_A( x1, y ) );
		vram_put( MENU_FRAME+3 );
	}
	vram_adr( NTADR_A( x0, y1 ) );
	vram_put( MENU_FRAME+4 );
	for( uint8_t x = x0+1; x < x1; x++ )
		vram_put( MENU_FRAME+1 );
	vram_put( MENU_FRAME+5 );
}

void menu_title( void ) {
	screen();
	frame_box( 1, 2, 30, 27 );
	big( 10, 6, "ELASTO" );
	big( 11, 9, "MANIA" );
	center( 13, "NES DEMAKE" );
	center( 22, "ORIGINAL GAME (C) 2000" );
	center( 23, "BALAZS ROZSA" );
	center( 25, "UNOFFICIAL FAN MADE PORT" );
	show();
	for( uint8_t f = 0;; f++ ) {
		read_pad();
		if( pressed( PAD_START ) || pressed( PAD_A ) )
			return;
		frame_begin();
		if( f & 32 )
			spr_text( 84, 136, "PRESS START" );
		frame_end();
	}
}

static void level_row( uint8_t level, uint8_t y ) {
	char s[32];
	uint8_t open = save_open( level );
	uint8_t n = level+1;
	s[0] = '0'+n/10;
	s[1] = '0'+n % 10;
	s[2] = 0;
	text( 2, y, s, open ? 0 : MENU_DIM );
	const char* name = Levels[level].name;
	uint8_t i = 0;
	for( ; name[i] && i < 18; i++ )
		s[i] = name[i];
	s[i] = 0;
	text( 5, y, s, open ? 0 : MENU_DIM );
	uint32_t t = save_best( level );
	if( t != NO_TIME ) {
		format_time( t, s );
		text( 23, y, s, 0 );
	}
}

static void level_page( uint8_t page ) {
	screen();
	center( 1, "SELECT A LEVEL" );
	for( uint8_t i = 0; i < PAGE; i++ ) {
		uint8_t level = page*PAGE+i;
		if( level >= Level_count )
			break;
		level_row( level, 4+i );
	}
	center( 26, "A: PLAY   B: TITLE" );
	show();
}

static void choose( uint8_t level ) {
	Menu_level = level;
	Level = Levels[level];
}

void menu_levels( void ) {
	uint8_t level = Menu_level;
	uint8_t page = level/PAGE;
	level_page( page );
	for( uint8_t f = 0;; f++ ) {
		read_pad();
		uint8_t moved = level;
		if( pressed( PAD_DOWN ) && level+1 < Level_count )
			level++;
		if( pressed( PAD_UP ) && level > 0 )
			level--;
		if( pressed( PAD_RIGHT ) )
			level = level+PAGE < Level_count ? level+PAGE : Level_count-1;
		if( pressed( PAD_LEFT ) )
			level = level >= PAGE ? level-PAGE : 0;
		if( level/PAGE != page ) {
			page = level/PAGE;
			level_page( page );
		}
		if( (pressed( PAD_A ) || pressed( PAD_START )) && save_open( level ) ) {
			choose( level );
			Menu_choice = 1;
			return;
		}
		if( pressed( PAD_B ) ) {
			Menu_choice = 0;
			return;
		}
		(void)moved;
		frame_begin();
		if( f & 16 || moved != level )
			spr( 4, (uint8_t)(8*(4+level % PAGE)-1), Hud_font['>'-32], 3 );
		frame_end();
	}
}

void menu_result( void ) {
	uint8_t level = Menu_level, best = Menu_best;
	uint32_t time = Game_time;
	char s[9];
	screen();
	frame_box( 1, 4, 30, 24 );
	center( 7, Levels[level].name );
	center( 10, "FINISHED!" );
	format_time( time, s );
	text( 9, 13, "TIME", 0 );
	text( 15, 13, s, 0 );
	format_time( save_best( level ), s );
	text( 9, 15, "BEST", 0 );
	text( 15, 15, s, 0 );
	if( best )
		center( 18, "NEW BEST TIME!" );
	center( 21, level+1 < Level_count ? "A: NEXT   B: LEVELS" : "B: LEVELS" );
	show();
	for( ;; ) {
		read_pad();
		if( (pressed( PAD_A ) || pressed( PAD_START )) && level+1 < Level_count ) {
			choose( level+1 );
			Menu_choice = 1;
			return;
		}
		if( pressed( PAD_B ) ) {
			Menu_choice = 0;
			return;
		}
		frame_begin();
		frame_end();
	}
}
