// The lines of the ground for the physics: the lines of a cell of the grid
// are copied from the data banks into one of a few caches when the physics
// first asks for them.
#include "segs.h"
#include <mapper.h>
#include "far.h"
#include "physics.h"

#define CACHES 3
#define CACHE_SEGS 80

typedef struct {
	uint8_t cx, cy;
	uint8_t n;
	uint8_t age;
	seg_t s[CACHE_SEGS];
} cache_t;

static cache_t Cache[CACHES] __attribute__((section( ".prg_ram.segs" )));

static uint32_t Segments, Grid, Grid_rows;
static uint8_t Gw, Gh;
static uint8_t Clock;

// The lines of the last query, read by physics.S too:
const seg_t* Seg_cur;
uint8_t Seg_left;

void segs_start( const level_t* lev ) {
	Segments = lev->segments;
	Grid = lev->grid;
	Grid_rows = lev->grid_rows;
	Gw = lev->gw;
	Gh = lev->gh;
	for( uint8_t i = 0; i < CACHES; i++ ) {
		Cache[i].cx = 0xff;
		Cache[i].age = 0;
	}
}

static int32_t u24( const uint8_t* p ) {
	return (int32_t)p[0] | (int32_t)p[1] << 8 | (int32_t)p[2] << 16;
}

static int16_t s16( const uint8_t* p ) {
	return (int16_t)(p[0] | (uint16_t)p[1] << 8);
}

static void load( cache_t* c, uint8_t cx, uint8_t cy ) {
	const uint8_t* p = far_ptr( Grid_rows + 2*(uint16_t)cy );
	uint32_t row = Grid + (p[0] | (uint16_t)p[1] << 8);
	// The lengths of the cells' lists, then the lists:
	p = far_ptr( row );
	uint16_t off = Gw;
	for( uint8_t x = 0; x < cx; x++ )
		off += p[x];
	if( !p[cx] )
		return;
	p += off;
	uint8_t runs = *p++;
	// The runs, read before the bank of the lines replaces them:
	uint16_t start[24];
	uint8_t count[24];
	if( runs > 24 )
		runs = 24;
	for( uint8_t r = 0; r < runs; r++ ) {
		start[r] = p[0] | (uint16_t)p[1] << 8;
		count[r] = p[2];
		p += 3;
	}
	seg_t* s = c->s;
	for( uint8_t r = 0; r < runs; r++ ) {
		for( uint8_t k = 0; k < count[r] && c->n < CACHE_SEGS; k++ ) {
			const uint8_t* q = far_ptr( Segments + 16*(uint32_t)(start[r]+k) );
			s->px = (int16_t)(u24( q )-((int32_t)cx << 12));
			s->py = (int16_t)(u24( q+3 )-((int32_t)cy << 12));
			s->dx = s16( q+6 );
			s->dy = s16( q+8 );
			s->ex = s16( q+10 );
			s->ey = s16( q+12 );
			s->len = s16( q+14 );
			seg_box( s );
			s++;
			c->n++;
		}
	}
}

static void fill( cache_t* c, uint8_t cx, uint8_t cy ) {
	c->cx = cx;
	c->cy = cy;
	c->n = 0;
	// The physics asks from its own bank, which must be there again after:
	uint8_t bank = get_prg_8000();
	load( c, cx, cy );
	set_prg_8000( bank );
}

void seg_query( uint8_t cx, uint8_t cy ) {
	Seg_left = 0;
	if( cx >= Gw || cy >= Gh )
		return;
	Clock++;
	cache_t* best = &Cache[0];
	for( uint8_t i = 0; i < CACHES; i++ ) {
		cache_t* c = &Cache[i];
		if( c->cx == cx && c->cy == cy ) {
			best = c;
			goto found;
		}
		if( (uint8_t)(Clock-c->age) > (uint8_t)(Clock-best->age) )
			best = c;
	}
	fill( best, cx, cy );
found:
	best->age = Clock;
	Seg_cur = best->s;
	Seg_left = best->n;
}

const seg_t* seg_next( void ) {
	if( !Seg_left )
		return 0;
	Seg_left--;
	return Seg_cur++;
}
