// The physics of the bike in fixed point, after LEPTET.CPP and BEALLIT.CPP
// of the game, stepped at the selected GBC physics rate.
//
// Units:
//   position   int32, 1 m = 2^18 (F); y points up
//   velocity   int32, PH_VS units per m/model-second
//   angle      uint32, a full turn is RIDING_ANGLE_UNITS (2^23 at30Hz,
//              2^24 at60Hz); exporting drops RIDING_ANGLE_SHIFT low bits
//   angular velocity  int32, PH_WS units per rad/model-second
// Short vectors are int16 in u (1 m = 1024) or in r16 (1 m = 16384).
#ifndef GBC_PHYSICS_CORE_H
#define GBC_PHYSICS_CORE_H

#include <stdint.h>
#ifdef __SDCC
#include <gb/gb.h>
#define PH_BANKED BANKED
#else
#define PH_BANKED
#endif
#include "riding_constants.h"

// One step of the physics is this many seconds of the game's time, which
// runs 0.4368 times as fast as the clock (182 ticks a second times 0.0024),
// with PH_RATE steps a second (physconst.h):
#define PH_H (0.4368/PH_RATE)
#define PH_S 262144.0
#define PH_PI 3.14159265358979
#ifndef RIDING_ANGLE_UNITS
#define RIDING_ANGLE_UNITS 16777216L
#define RIDING_ANGLE_SHIFT 8
#endif
#define PH_AN ((double)RIDING_ANGLE_UNITS/(2.0*PH_PI))
// Storage precision is independent of the scheduled integration intervals.
// Legacy profiles used one frame as their velocity unit time.
#ifndef PH_VELOCITY_UNIT_TIME
#define PH_VELOCITY_UNIT_TIME PH_H
#endif
#ifndef PH_ANGULAR_UNIT_TIME
#define PH_ANGULAR_UNIT_TIME PH_H
#endif
#define PH_VS (PH_S*PH_VELOCITY_UNIT_TIME/4.0)
#define PH_WS (PH_AN*PH_ANGULAR_UNIT_TIME/128.0)

#define M_TO_F( m ) ((int32_t)((m)*PH_S))
#define M_TO_U( m ) ((int16_t)((m)*1024.0 + ((m) < 0 ? -0.5 : 0.5)))

typedef struct {
	int32_t rx, ry;
	int32_t vx, vy;
	uint32_t alfa;
	int32_t omega;
} circle_t;
#ifdef __SDCC
/* A scheduled wheel record has the same representation as the arguments
 * of the public banked wheel solver. */
typedef struct {
    circle_t *k;
    int32_t dvx, dvy, tq;
} wheel_input_t;
void riding_move32(circle_t *k) __sdcccall(0);
#endif

enum { GRAV_UP, GRAV_DOWN, GRAV_LEFT, GRAV_RIGHT };

typedef struct {
	circle_t body;
	circle_t wheel[2];  // [0] left (kor2), [1] right (kor4) when not turned
	int32_t rider_x, rider_y;
	int32_t rider_vx, rider_vy;
	int32_t head_x, head_y;
	uint8_t turned;     // facing right (hatra_f)
	uint8_t gravity;
	uint8_t brake_was;
	uint8_t steps;      // completed physics steps, modulo 256
	uint8_t gfrac;      // fraction of the gravity step
	uint32_t dbrake[2];
	uint8_t volt[2];    // steps left of a volt, 0 if none
	int32_t volt_omega[2];
} bike_t;

extern bike_t Bike;
/* Read-only audio observation of the most recent wheel contact query. */
extern uint8_t riding_audio_contact[2], riding_audio_impact[2];
uint8_t riding_touches(int32_t cx,int32_t cy,int16_t rad) PH_BANKED;
// Continuous head path in local u coordinates (1m=1024), before world rebasing.
uint8_t riding_swept_head(int32_t old_x,int32_t old_y,int32_t x,int32_t y) PH_BANKED;
void riding_wheel(circle_t *k,int32_t dvx,int32_t dvy,int32_t tq) PH_BANKED;

// A line of the level, as the platform hands it over: its start in u from
// the origin of the query, its vector to the end in u, its direction (16384
// is 1) and its length in u; then its box, larger by the radius of a wheel,
// as SEG_BOX of its corners, precomputed for a quick first test.
typedef struct {
	int16_t px, py;
	int16_t dx, dy;
	int16_t ex, ey;
	int16_t len;  // low14 length; high bits mark artificial subdivision ends
	uint8_t x0, x1, y0, y1;
} seg_t;

#define SEG_LENGTH(s) ((int16_t)((uint16_t)(s)->len & 0x3fffU))
#define SEG_INTERNAL_START 0x4000U
#define SEG_INTERNAL_END 0x8000U

// A coordinate from the origin of the query (u) in 64 u, plus 128:
#define SEG_BOX( v ) ((uint8_t)(((v) >> 6) + 128))

static inline uint8_t seg_box1( int16_t v ) {
	if( v < -8192 ) return 0;
	if( v > 8191 ) return 255;
	return SEG_BOX( v );
}

// Supplied by the platform: selects the lines of the cell (cx, cy) of the
// grid of 4096 u (seg_cell), those within 0.5 m of it with their start from
// its corner. Dense cells use a 4-bit 1 m subcell selector. The query
// then hands segments over one by one, returning 0 after the last
// one (Seg_cur and Seg_left are the rest of them).
void seg_query(uint8_t cx,uint8_t cy,uint8_t subcell);
const seg_t* seg_next( void );
extern const seg_t* Seg_cur;
extern uint8_t Seg_left;

// The cell of a coordinate in u, 255 outside the grid:
static inline uint8_t seg_cell( int32_t c ) {
	/* Check the upper half before joining the two cell-index nibbles.
	 * This avoids a 12-iteration signed32 shift on each SM83 query.
	 * Coordinates in cell 255 already produce the outside sentinel. */
	uint16_t high = (uint16_t)((uint32_t)c >> 16);
	if( high >= 16 )
		return 255;
	return (uint8_t)(((uint8_t)high << 4) | ((uint8_t)((uint32_t)c >> 8) >> 4));
}

// Inputs of a step:
#define IN_GAS   1
#define IN_BRAKE 2
#define IN_VOLT_RIGHT 4  // clockwise (ugrik1)
#define IN_VOLT_LEFT  8  // counterclockwise (ugrik2)

// The start object is where the left wheel stands (x, y in F):
void ph_init( int32_t x, int32_t y );
#ifdef __SDCC
/* One-use prefix of the next full spring solve. ph_init, ph_turn and
 * level/menu transitions discard it before the normal input path resumes. */
extern uint8_t riding_spring_ready;
void physics_prepare_spring(uint16_t start) PH_BANKED;
#endif
// Returns 0 if the head of the rider hit the ground:
uint8_t ph_step( uint8_t input );
// Turns the bike around (the space key of the game):
void ph_turn( void );

#endif
