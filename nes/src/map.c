#include "map.h"
#include <neslib.h>
#include "far.h"

int16_t Cam_x, Cam_y;
uint16_t Map_w, Map_h;

static uint16_t Cols, Rows;     // the map in tiles
static uint32_t Map, Columns;
// The loaded window: columns Col0..Col0+32, rows Row0+1..Row0+30.
static int16_t Col0, Row0;

// A cursor in a column of the map: the byte of its run and the row within.
typedef struct {
	const uint8_t* p;
	uint8_t off;
} cursor_t;

// For each loaded column (by x & 63): the bank of its data, and cursors at
// the first and the last loaded row.
#define PRG_RAM __attribute__((section( ".prg_ram.map" )))
static uint8_t Cbank[64] PRG_RAM;
static cursor_t Top[64] PRG_RAM, Bot[64] PRG_RAM;

static const uint8_t Runlen[16] = { 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 20, 24, 32, 48, 64 };

static uint8_t entry_len( uint8_t b ) {
	return b >= 224 ? Runlen[b & 15] : 1;
}

static uint8_t entry_tile( uint8_t b ) {
	return b >= 240 ? 1 : b >= 224 ? 0 : b;
}

static void advance( cursor_t* c ) {
	if( ++c->off >= entry_len( *c->p ) ) {
		c->p++;
		c->off = 0;
	}
}

static void retreat( cursor_t* c ) {
	if( c->off ) {
		c->off--;
		return;
	}
	c->p--;
	c->off = entry_len( *c->p )-1;
}

// --- The buffer of the nametable updates -------------------------------

uint8_t Vram_buf[96];
static uint8_t Vram_n;

void vram_begin( void ) {
	Vram_n = 0;
	Vram_buf[0] = NT_UPD_EOF;
}

void vram_end( void ) {
	Vram_buf[Vram_n] = NT_UPD_EOF;
}

static uint16_t nt_addr( uint16_t x, uint16_t y ) {
	return ((x & 32) ? NAMETABLE_B : NAMETABLE_A) + (y % 30)*32 + (x & 31);
}

static uint8_t* vram_run( uint16_t adr, uint8_t flags, uint8_t len ) {
	uint8_t* p = &Vram_buf[Vram_n];
	p[0] = (uint8_t)(adr >> 8) | flags;
	p[1] = (uint8_t)adr;
	p[2] = len;
	Vram_n += 3+len;
	return p+3;
}

// --- Columns and rows -----------------------------------------------------

static uint8_t Line[33];

// Loads column x for the rows of the window into Line, with its cursors.
static void load_column( int16_t x ) {
	uint8_t s = x & 63;
	if( x < 0 || x >= (int16_t)Cols ) {
		for( uint8_t i = 0; i < 30; i++ )
			Line[i] = 1;
		Cbank[s] = 0xff;
		return;
	}
	const uint8_t* col = far_ptr( Columns + 2*(uint16_t)x );
	uint16_t start = col[0] | (uint16_t)col[1] << 8;
	uint32_t lin = Map + start;
	cursor_t c;
	c.p = far_ptr( lin );
	Cbank[s] = (uint8_t)(lin >> 13);
	c.off = 0;
	int16_t row = 0, first = Row0+1;
	while( row + entry_len( *c.p ) <= first ) {
		row += entry_len( *c.p );
		c.p++;
	}
	c.off = (uint8_t)(first-row);
	Top[s] = c;
	for( uint8_t i = 0; i < 30; i++ ) {
		if( first+i >= (int16_t)Rows ) {
			Line[i] = 1;
			continue;
		}
		Line[i] = entry_tile( *c.p );
		Bot[s] = c;
		if( i < 29 )
			advance( &c );
	}
}

// Writes Line as column x of the window into the update buffer.
static void put_column( int16_t x ) {
	uint16_t y = Row0+1;
	uint8_t first = y % 30;
	uint8_t n1 = 30-first;
	uint8_t* p = vram_run( nt_addr( x, y ), NT_UPD_VERT, n1 );
	for( uint8_t i = 0; i < n1; i++ )
		p[i] = Line[i];
	if( n1 < 30 ) {
		p = vram_run( nt_addr( x, y+n1 ), NT_UPD_VERT, 30-n1 );
		for( uint8_t i = n1; i < 30; i++ )
			p[i-n1] = Line[i];
	}
}

// Writes Line as row y of the window into the update buffer.
static void put_row( int16_t y ) {
	int16_t x = Col0;
	uint8_t i = 0;
	while( i < 33 ) {
		uint8_t n = 32-(x & 31);
		if( n > 33-i )
			n = 33-i;
		uint8_t* p = vram_run( nt_addr( x, y ), NT_UPD_HORZ, n );
		for( uint8_t k = 0; k < n; k++ )
			p[k] = Line[i+k];
		i += n;
		x += n;
	}
}

// Moves the cursors of the window's columns down a row and returns the
// tiles of the new last row in Line.
static void rows_down( void ) {
	int16_t y = Row0+31;
	for( uint8_t i = 0; i < 33; i++ ) {
		uint8_t s = (Col0+i) & 63;
		Line[i] = 1;
		if( Cbank[s] == 0xff )
			continue;
		far_ptr( (uint32_t)Cbank[s] << 13 );
		advance( &Top[s] );
		// Below the map the last cursor stays on its last row:
		if( y < (int16_t)Rows ) {
			advance( &Bot[s] );
			Line[i] = entry_tile( *Bot[s].p );
		}
	}
}

// Moves the cursors up a row and returns the tiles of the new first row.
static void rows_up( void ) {
	int16_t y = Row0;
	for( uint8_t i = 0; i < 33; i++ ) {
		uint8_t s = (Col0+i) & 63;
		if( Cbank[s] == 0xff ) {
			Line[i] = 1;
			continue;
		}
		far_ptr( (uint32_t)Cbank[s] << 13 );
		retreat( &Top[s] );
		if( y+30 < (int16_t)Rows )
			retreat( &Bot[s] );
		Line[i] = entry_tile( *Top[s].p );
	}
}

void map_start( const level_t* lev ) {
	Cols = lev->w;
	Rows = lev->h;
	Map = lev->map;
	Columns = lev->columns;
	Map_w = Cols*8;
	Map_h = Rows*8;
	Col0 = Cam_x >> 3;
	Row0 = Cam_y >> 3;
	for( int16_t x = Col0; x < Col0+33; x++ ) {
		load_column( x );
		uint16_t y = Row0+1;
		for( uint8_t i = 0; i < 30; i++, y++ ) {
			vram_adr( nt_addr( x, y ) );
			vram_put( Line[i] );
		}
	}
}

void map_scroll( void ) {
	int16_t c = Cam_x >> 3, r = Cam_y >> 3;
	if( c > Col0 ) {
		load_column( Col0+33 );
		put_column( Col0+33 );
		Col0++;
	}
	else if( c < Col0 ) {
		Col0--;
		load_column( Col0 );
		put_column( Col0 );
	}
	if( r > Row0 ) {
		rows_down();
		Row0++;
		put_row( Row0+30 );
	}
	else if( r < Row0 ) {
		rows_up();
		Row0--;
		put_row( Row0+1 );
	}
}
