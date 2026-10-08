// The physics of the bike and the objects of a level (phys.asm), after
// LEPTET.CPP, BEALLIT.CPP, UTKOZES*.CPP of the original game and the object
// handling of its game loop (LEJATSZO.CPP), in fixed point; test/phys_spec.c
// describes it to the bit. PHYS_HZ steps a second of real time.
//
// Positions: meters, y up, 16.16 fixed point; angles: 65536 a turn,
// counterclockwise.
#ifndef PHYS_H
#define PHYS_H

#include <snes.h>
#include "phys_hz.h"        // PHYS_HZ (build option, 80 by default)

// Input bits of a step: the keys as they are held.
#define PH_GAS     1
#define PH_BRAKE   2
#define PH_VOLT_R  4   // ugrik1 of the PC (the "right volt" key, clockwise)
#define PH_VOLT_L  8   // ugrik2 (counterclockwise)
// A quick step: the physics only, without phys_view, phys_friction and
// phys_wheel_omega (they keep the values of the last full step; the other
// outputs are made). For all but the last step of a frame.
#define PH_QUICK   0x100
// Events returned by phys_step:
#define PH_DEAD    1   // head hit, killer, or left the level
#define PH_FINISH  2   // flower touched with all apples eaten (wins over a
                       // killer touched in the same step, as in the PC)
#define PH_EAT     4   // an apple was eaten (phys_eaten = its object index)
#define PH_BUMP    8   // a hard hit (phys_bump = volume 0..255), PC WAV_UTODES
#define PH_VOLT    16  // a volt started (phys_volt1: which, as ugras1volt)

typedef struct {
	s32 body_x, body_y;        // kor1.r
	u16 body_a;                // kor1.alfa
	s32 wheel_x[2], wheel_y[2];// [0] kor2, [1] kor4 (as the PC numbers them)
	u16 wheel_a[2];            // kor2.alfa, kor4.alfa
	s32 rider_x, rider_y;      // vezetor
	s32 head_x, head_y;        // fejr
	u8 turned;                 // hatra_f
	u8 gravity;                // gravirany: 0 up, 1 down, 2 left, 3 right
} bike_view_t;

// Object table of the level in the order the PC keeps it (after killerekelore):
typedef struct {
	u8 type;      // 1 flower, 2 apple, 3 killer, 4 start
	u8 anim;      // qfood picture index (apples)
	u8 gravity;   // apple gravity change, 0 none 1 up 2 down 3 left 4 right
	u8 active;    // apples: 1 until eaten (the start is 0)
	s32 x, y;     // 16.16 meters
} phys_obj_t;

// Loads a level: objects all active, bike at the start, the clock at 0.
void phys_level(u16 level);
// One step of the physics and the object checks (vizsgalat). Takes the volt
// keys as they are held: a volt starts when one is held and the last volt
// was at least 0.4 game seconds ago (Ugroturelem of belsoresz), so the game
// passes the buttons as they are. Returns PH_* events. After PH_DEAD or
// PH_FINISH the level is over: the game stops stepping. The time of the
// level is the number of steps before the step that finished it.
u16  phys_step(u16 input);
// The turn key (hatra_f toggle + szamitfejr), on the press, not when dead.
void phys_turn(void);

extern bike_view_t phys_view;    // the bike after the last step
extern phys_obj_t phys_objs[];   // objects of the level
extern u16 phys_nobjs;
extern u16 phys_apples_left;     // apples still needed for the flower
extern u16 phys_eaten;           // the last apple eaten (with several in a step, the last)
extern u16 phys_bump;            // the hardest hit of the step, 0..253 (volume * 256)
// |omega| of the driven wheel (kor4, or kor2 when turned) in 1/256 rad/s,
// at most 65535; the PC's engine pitch is 2 - exp(-0.025 |omega|):
extern u16 phys_wheel_omega;
// The PC's Maxsurlodas (kiszamolsurlodast), the friction sound: 65535 = 1.0
// (the PC caps it there):
extern u16 phys_friction;
extern u8 phys_volt_age;         // steps since the last volt, 255 at most (bike_anim.volt)
extern u8 phys_volt1;            // the last volt was PH_VOLT_R (bike_anim.volt1)

#endif
