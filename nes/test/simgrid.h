// The lines of a level for the tests in the simulator (simlines.h), handed
// over like the grid of the NES does: those within 0.5 m of the cell, from
// a few cells kept.
#include "simlines.h"

typedef struct {
	int32_t px, py;
	int16_t dx, dy, ex, ey, len;
} line_t;

static const line_t Lines[] = { SIM_LINES };
#define NLINES (sizeof( Lines )/sizeof( Lines[0] ))

const seg_t* Seg_cur;
uint8_t Seg_left;

// A few cells of lines, taken in turn:
#define CELLS 4
#define CELL_LINES (NLINES < 255 ? NLINES : 255)
static seg_t Cell[CELLS][CELL_LINES];
static uint8_t Cell_x[CELLS] = { 255, 255, 255, 255 }, Cell_y[CELLS], Cell_n[CELLS];
static uint8_t Cell_next;

void seg_query( uint8_t cx, uint8_t cy ) {
	Seg_left = 0;
	if( cx == 255 || cy == 255 )
		return;
	uint8_t c = 0;
	while( c < CELLS && (Cell_x[c] != cx || Cell_y[c] != cy) )
		c++;
	if( c == CELLS ) {
		c = Cell_next;
		Cell_next = (Cell_next+1) % CELLS;
		int32_t ox = (int32_t)cx << 12, oy = (int32_t)cy << 12;
		Cell_x[c] = cx;
		Cell_y[c] = cy;
		Cell_n[c] = 0;
		for( uint16_t i = 0; i < NLINES && Cell_n[c] < CELL_LINES; i++ ) {
			const line_t* l = &Lines[i];
			int32_t x0 = l->px, x1 = l->px+l->dx, y0 = l->py, y1 = l->py+l->dy;
			if( x0 > x1 ) { int32_t t = x0; x0 = x1; x1 = t; }
			if( y0 > y1 ) { int32_t t = y0; y0 = y1; y1 = t; }
			if( x1 < ox-512 || x0 > ox+4096+512 || y1 < oy-512 || y0 > oy+4096+512 )
				continue;
			seg_t* s = &Cell[c][Cell_n[c]++];
			s->px = (int16_t)(l->px-ox);
			s->py = (int16_t)(l->py-oy);
			s->dx = l->dx;
			s->dy = l->dy;
			s->ex = l->ex;
			s->ey = l->ey;
			s->len = l->len;
			seg_box( s );
		}
	}
	Seg_cur = Cell[c];
	Seg_left = Cell_n[c];
}

const seg_t* seg_next( void ) {
	if( !Seg_left )
		return 0;
	Seg_left--;
	return Seg_cur++;
}
