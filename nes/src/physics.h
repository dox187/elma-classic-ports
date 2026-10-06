// The physics of the bike in fixed point, after LEPTET.CPP and BEALLIT.CPP
// of the game, stepped once per frame.
//
// Units:
//   position   int32, 1 m = 2^18 (F); y points up
//   velocity   int16, 4 F per step (VU)
//   angle      uint32, a full turn is 2^24 (only the low 24 bits count)
//   angular velocity  int16, 128 angle units per step (WU)
// Short vectors are int16 in u (1 m = 1024) or in r16 (1 m = 16384).
#ifndef PHYSICS_H
#define PHYSICS_H

#include <stdint.h>

// One step of the physics is this many seconds of the game's time, which
// runs 0.4368 times as fast as the clock (182 ticks a second times 0.0024):
// one frame of NTSC.
#define PH_H (0.4368/60.0988)
#define PH_S 262144.0
#define PH_PI 3.14159265358979
#define PH_AN (16777216.0/(2.0*PH_PI))
// Velocity units per m/s and angular velocity units per rad/s:
#define PH_VS (PH_S*PH_H/4.0)
#define PH_WS (PH_AN*PH_H/128.0)

#define M_TO_F( m ) ((int32_t)((m)*PH_S))
#define M_TO_U( m ) ((int16_t)((m)*1024.0 + ((m) < 0 ? -0.5 : 0.5)))

typedef struct {
	int32_t rx, ry;
	int16_t vx, vy;
	uint32_t alfa;
	int16_t omega;
} circle_t;

enum { GRAV_UP, GRAV_DOWN, GRAV_LEFT, GRAV_RIGHT };

typedef struct {
	circle_t body;
	circle_t wheel[2];  // [0] left (kor2), [1] right (kor4) when not turned
	int32_t rider_x, rider_y;
	int16_t rider_vx, rider_vy;
	int32_t head_x, head_y;
	uint8_t turned;     // facing right (hatra_f)
	uint8_t gravity;
	uint8_t brake_was;
	uint8_t steps;      // counts the steps, the rider moves every other one
	uint8_t gfrac;      // fraction of the gravity step
	uint32_t dbrake[2];
	uint8_t volt[2];    // steps left of a volt, 0 if none
	int16_t volt_omega[2];
} bike_t;

extern bike_t Bike;

// A line of the level, as the platform hands it over: its start in u from
// the origin of the query, its vector to the end in u, its direction (16384
// is 1) and its length in u.
typedef struct {
	int16_t px, py;
	int16_t dx, dy;
	int16_t ex, ey;
	int16_t len;
} seg_t;

// Supplied by the platform: selects the lines near a point (in u), at most
// 8 m from the point and from Seg_ox, Seg_oy, then hands them over one by
// one, returning 0 after the last one (Seg_cur and Seg_left are the rest of
// them).
void seg_query( int32_t x, int32_t y );
const seg_t* seg_next( void );
extern int32_t Seg_ox, Seg_oy;
extern const seg_t* Seg_cur;
extern uint8_t Seg_left;

// Inputs of a step:
#define IN_GAS   1
#define IN_BRAKE 2
#define IN_VOLT_RIGHT 4  // clockwise (ugrik1)
#define IN_VOLT_LEFT  8  // counterclockwise (ugrik2)

// The start object is where the left wheel stands (x, y in F):
void ph_init( int32_t x, int32_t y );
// Returns 0 if the head of the rider hit the ground:
uint8_t ph_step( uint8_t input );
// Turns the bike around (the space key of the game):
void ph_turn( void );

#endif
