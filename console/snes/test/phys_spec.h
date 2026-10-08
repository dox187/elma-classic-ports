// The physics of the SNES version in C, on the host: the description of what
// src/phys.asm computes, to the bit (test/physcheck compares it with the
// original game, test/snes_phys.c with the assembly in an emulator).
//
// Units (docs/physics.md): positions P = 1/65536 m, velocities V = 1/2^24 m
// a step, angles and angular velocities W = 1/2^28 rad (a step), torques
// T = 1/16 Nm, unit vectors Q14 (16384 = 1).
#ifndef PHYS_SPEC_H
#define PHYS_SPEC_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Input bits and events, as in src/phys.h:
#define PH_GAS     1
#define PH_BRAKE   2
#define PH_VOLT_R  4
#define PH_VOLT_L  8
#define PH_DEAD    1
#define PH_FINISH  2
#define PH_EAT     4
#define PH_BUMP    8
#define PH_VOLT    16

typedef struct {
	int32_t rx, ry;     // P
	int32_t vx, vy;     // V
	int32_t a;          // W, from -pi to pi
	int32_t w;          // W a step
} ps_circle_t;

// A wheel that rolled in the last step: the normal of its contact (Q14)
// and its speed along the ground (V).
typedef struct {
	int32_t s;
	int16_t nx, ny;
	uint8_t on, pad;
} ps_roll_t;

// The state that carries over from step to step, in the order of the
// assembly's (and of the dumps of test/snes_phys.c):
typedef struct {
	ps_circle_t c[3];       // kor1 (body), kor2, kor4
	int32_t rider_x, rider_y, rider_vx, rider_vy;
	int32_t head_x, head_y;
	int32_t defl[2];        // brake: turn of kor2, kor4 against the body since the brake (2^-20 rad)
	int32_t volt_w[2];      // kezdoomega1, 2 (W a step)
	ps_roll_t roll[2];
	uint8_t volt_on[2];     // ugrasban1, 2
	uint8_t volt_t[2];      // steps since the volt started
	uint8_t last_volt;      // steps since the last volt (255 at most)
	uint8_t turned;         // hatra_f
	uint8_t gravity;        // gravirany: 0 up, 1 down, 2 left, 3 right
	uint8_t brake_was;      // voltfek
	uint8_t volt1;          // ugras1volt: the last volt was PH_VOLT_R
	uint8_t apples;         // eaten (kajaszam)
} ps_state_t;

typedef struct {
	uint8_t type, anim, gravity, active;
	int32_t x, y;
} ps_obj_t;

extern ps_state_t PS;
extern ps_obj_t PS_obj[52];
extern uint16_t PS_nobjs, PS_apples_needed;
extern uint16_t PS_eaten, PS_bump, PS_friction, PS_wheel_omega;

// The level data of tools/gen_phys.py (build/gen/phys/levNN.bin):
void ps_level( const uint8_t* blob );
uint16_t ps_step( uint16_t input );
void ps_turn( void );
// The angle of the view: 65536 a turn.
uint16_t ps_angle16( int32_t a );
// The state as the direct page of the assembly has it (PS_DUMP_SIZE bytes):
#define PS_DUMP_SIZE 142
void ps_dump( uint8_t* out );
void ps_trig_dump( uint8_t* out );

#ifdef __cplusplus
}
#endif

#endif
