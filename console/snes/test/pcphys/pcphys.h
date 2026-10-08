// The physics of the original game on the host, in double precision: its
// own sources (LEPTET.CPP, BEALLIT.CPP, UTKOZES.CPP, UTKOZES2.CPP,
// SZAKASZ.CPP, VEKT2.CPP) with the parts of the game loop that drive them
// (LEJATSZO.CPP belsoresz, TOPOL.CPP, ADATOK.CPP), for comparing the SNES
// physics with it.
#ifndef PCPHYS_H
#define PCPHYS_H

#ifdef __cplusplus
extern "C" {
#endif

typedef struct { double x, y; } pc_vec;

typedef struct {
	pc_vec r, v;
	double alfa, omega;
} pc_circle;

typedef struct {
	pc_circle c[3];          // kor1 (body), kor2, kor4
	pc_vec rider_r, rider_v; // vezetor, vezetov
	pc_vec head;             // fejr
	int turned;              // hatra_f
	int gravity;             // gravirany
	int apples;              // kajaszam
} pc_state;

// Loads a level written by test/levdump.py. 0 if it fails.
int pc_load( const char* path );
// The bike at the start, the objects active, the clock at 0.
void pc_reset( void );
// One step of dt (the game takes 0.0055) with the input bits of phys.h
// (PH_GAS, PH_BRAKE, PH_VOLT_R, PH_VOLT_L, held keys): the volt timing of
// belsoresz, leptet, vizsgalat and the objects. Returns the PH_* events.
int pc_step( int input, double dt );
// The turn key (hatra_f and szamitfejr, kulsoresz).
void pc_turn( void );
void pc_get( pc_state* s );
void pc_set( const pc_state* s );

extern double pc_friction;   // kiszamolsurlodast of the last step
extern double pc_bump;       // the largest WAV_UTODES volume of the last step
extern int pc_eaten;         // the last apple eaten (object index)
extern int pc_nobjs;
extern int pc_obj_type[52], pc_obj_active[52];
extern double pc_time;       // eddig

#ifdef __cplusplus
}
#endif

#endif
