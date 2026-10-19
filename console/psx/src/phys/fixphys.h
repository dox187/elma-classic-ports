// Fixed point physics of the bike for the PlayStation: the computation of
// leptet, beallit, beallitvezeto, talppontkereses and the head and object
// tests of vizsgalat (LEPTET.CPP, BEALLIT.CPP, UTKOZES.CPP, UTKOZES2.CPP of
// the original game) in integer arithmetic for the 32-bit MIPS R3000, which
// has no floating point unit.
//
// Number formats (all values in the units of the original: m, m/s, rad,
// rad/s, N, Nm):
//   state and forces   int64_t Q40 (value * 2^40): positions, velocities,
//                      angles (not wrapped), angular velocities, forces,
//                      torques. 64-bit additions are cheap on the R3000.
//   directions         int32_t Q30: sin/cos, unit vectors (+-1 exact).
//   constants          fx_kq: a 31-bit mantissa and a shift, so that a Q40
//                      value times a constant costs two 32x32->64 mult.
// Products of two state values truncate one of them to 32 bits (Q30 for
// lengths below 2 m, which are all the relative vectors of the bike).
//
// The code is plain integer C and gives the same bits on the host (the
// fidelity test, test/phys_host.cpp) and on the PlayStation. Only the
// tables and the constants are made with double arithmetic (+ - * / and
// sqrt, which IEEE 754 rounds the same everywhere).
#ifndef FIXPHYS_H
#define FIXPHYS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct { int64_t x, y; } fx_vec;

// A constant: m * 2^-s, with 2^30 <= |m| < 2^31 (or m == 0).
typedef struct { int32_t m, s; } fx_kq;

// A circle of the bike (kor): position, velocity, angle, angular velocity.
typedef struct {
	fx_vec r, v;
	int64_t a, w;
} fx_kor;

// The state of a bike between steps.
typedef struct {
	fx_kor k[3];         // kor1 (body), kor2 (front wheel), kor4 (rear wheel)
	int64_t aw;          // the angle of the body wrapped between -pi and pi,
	                     // for sin and cos
	fx_vec vr, vv;       // vezetor, vezetov (the rider)
	fx_vec fej;          // fejr (the head), computed by each step
	int voltfek;
	int64_t dfek2, dfek4;
	int ugrasban1, ugrasban2;
	double ugras1kezd, ugras2kezd;
	int64_t kezdoomega1, kezdoomega2;
	// Outputs of the last step:
	int64_t maxsurl;     // Maxsurlodas (Q40)
	int racs;            // a test was too far right or up from the level
	int nbump;           // WAV_UTODES events of the step, in order
	int64_t bump[8];     // the speed of each into the ground (Q40 m/s)
} fx_bike;

// A line of the level (vonal), positions Q40, direction Q30 with the rest
// of it (u - ux/2^30) in Q61.
typedef struct {
	fx_vec p, e;         // start, end (p + egyseg*hossz)
	int64_t len;         // hossz
	int32_t ux, uy;      // egyseg
	int32_t lx, ly;      // the rest of egyseg
} fx_line;

typedef struct {
	fx_vec r;
	const int* aktiv;    // kerek::aktiv of the level (changes in the game)
	int tipus;
} fx_obj;

typedef struct {
	fx_line* lines;
	int nlines;
	// The grid of szakaszok (cells of 1 m): the lines of cell (x, y) are
	// list[cell[y*xdim+x]] .. list[cell[y*xdim+x+1]-1], in the order of the
	// original's lists.
	uint32_t* cell;
	uint16_t* list;
	int xdim, ydim;
	fx_vec origo;
	fx_obj* objs;
	int nobjs;
	// ecset::kilogna: the bike dies with its body outside these:
	int64_t kill_x1, kill_x2, kill_y1, kill_y2;
} fx_level;

// The constants of the original (ADATOK.CPP initadatok, initmotor and the
// numbers in the physics sources), made by fx_params().
typedef struct {
	int32_t kord2x, kord2y, kord4x, kord4y, kord5y;     // Q30
	fx_kq drsugar, sr, drsugar5, sr3;
	int64_t gm[3];                  // m*G of the circles
	fx_kq inv_m[3], inv_theta[3];   // 1/m, 1/theta
	int64_t theta2;                 // theta of the wheels (Q56)
	fx_kq m2;                       // m of the wheels
	int64_t sugar[3];               // radius of the circles
	fx_kq sugar2k, inv_sugar2;      // the same and 1/radius
	int64_t sugar2_62;              // (radius of the wheels)^2 (Q62)
	int64_t belso;                  // sugar - Belsosav of the wheels
	int64_t elszakad;               // Elszakadasisebhat
	int64_t merge2;                 // Talppontegybeolvadasitav^2 (Q60)
	int64_t merge;                  // Talppontegybeolvadasitav
	int64_t fejsugar;
	int64_t fejsugar2;              // Q62
	int64_t objsugar;               // Objektumsugar
	double ugroturelem;
	int64_t pi, twopi;              // K_pi of the original and twice it
	// vezeto_hatarolas:
	int64_t ar_x, ar_y, felhat, balhat, jobbhat;
	int32_t avn_x, avn_y;           // avnormegys (Q30)
	fx_kq rxszorzo, tavmax;
	int64_t tavmax2;                // Q60
	// Cache of the step length:
	int32_t dt_m, dt_s;
	fx_kq dt, dt_m1[3], dt_theta[3];
} fx_param;

// Exact conversions: round( d * 2^q ) and x * 2^-q to the nearest double.
int64_t fx_d2q( double d, int q );
double fx_q2d( int64_t x, int q );
fx_kq fx_kq_of( double d );

// The tables (once).
void fx_init( void );
// The constants of the original, as doubles (ADATOK.CPP globals, the
// circles of a bike after initmotor, K_pi, avnormegys of BEALLIT.CPP):
typedef struct {
	double drsugar, sr, g, belsosav, elszakad, merge, fejsugar, objsugar;
	double ugroturelem, kord2x, kord2y, kord4x, kord4y, kord5y, pi;
	double kor_m[3], kor_theta[3], kor_sugar[3];
	double avn_x, avn_y;
} fx_input;
void fx_params( fx_param* p, const fx_input* in );

// leptet: one step of dt (a double of the game loop, usually 0.0055).
void fx_leptet( fx_bike* b, const fx_level* lev, fx_param* p, double most, double dt,
				int gaz, int fek, int ugrik1, int ugrik2, int hatra_f, int gravirany );
// szamitfejr from the state:
void fx_szamitfejr( fx_bike* b, int hatra_f );
// talppontkereses for the head: true if it touches the ground.
int fx_fejutkozik( fx_bike* b, const fx_level* lev, const fx_param* p );
// utkozikesprite: the first active object a circle at r of radius sugar
// touches (-1 none); with skipcel the flowers are left out (Flag Tag).
int fx_utkozikesprite( const fx_level* lev, const fx_param* p, fx_vec r, int64_t sugar,
					   int skipcel );
// ecset::kilogna:
int fx_kilogna( const fx_level* lev, fx_vec r );
// 2 - exp( -min( |omega|*0.025, 30 ) ) (Q31) of an angular velocity (Q40),
// the engine sound value of LEJATSZO.CPP.
int64_t fx_motorfrekvencia( int64_t omega );
// An angle wrapped between -pi and pi (aw of the body from its a).
int64_t fx_wrap( int64_t a );

#ifdef __cplusplus
}
#endif

#endif
