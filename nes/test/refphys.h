// The physics of the original game in double precision, for comparing the
// fixed point physics of the NES version with it. It follows LEPTET.CPP,
// BEALLIT.CPP and UTKOZES.CPP of the game.
#ifndef REFPHYS_H
#define REFPHYS_H

typedef struct { double x, y; } rvec;

typedef struct {
	double alfa, omega, r_, m, theta;
	rvec r, v;
} rcircle;

typedef struct {
	rcircle body, wheel[2]; // wheel[0] is kor2 (left), wheel[1] kor4 (right)
	rvec rider_r, rider_v, head;
	int turned;  // hatra_f
	int gravity; // 0 up, 1 down, 2 left, 3 right
	int brake_was;
	double dbrake[2];
	int volt[2];
	double volt_start[2], volt_omega[2];
} rbike;

typedef struct { rvec r, v; } rseg;

void ref_init( rbike* b, double startx, double starty );
// Returns 0 if the bike died (its head hit the ground).
int ref_step( rbike* b, const rseg* segs, int nsegs, double now, double dt,
			  int gas, int brake, int volt_right, int volt_left );

#endif
