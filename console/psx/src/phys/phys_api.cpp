// The functions of LEPTET.CPP (LEPTET.H) on the PlayStation: the steps with
// the fixed point physics (phys_glue.cpp), szamitfejr (replays and the turn
// key) and elsomegoltemasodikat (two players) as in the original, on the
// double fields of motorst. BEALLIT.CPP, UTKOZES.CPP and UTKOZES2.CPP are
// only called from LEPTET.CPP and are left out with it (phys.cmake).
#include "all.h"
#include "phys_glue.h"
#include "fixphys.h"

void resetleptet( motorst* pmot ) {
	fxg_resetleptet( pmot );
}

void leptet( motorst* pmot, double most, double dt, int gaz, int fek,
			 int ugrik1, int ugrik2 ) {
	fxg_leptet( pmot, most, dt, gaz, fek, ugrik1, ugrik2 );
}

int vizsgalat( motorst* pmot ) {
	return fxg_vizsgalat( pmot );
}

double kiszamolsurlodast( void ) {
	return fxg_kiszamolsurlodast();
}

// LEJATSZO.CPP belsoresz: the engine sound value of the step,
// 2 - exp( -min( |omega|*0.025, 30 ) ), in fixed point.
double psx_motorfrekvencia( double omega ) {
	return fx_q2d( fx_motorfrekvencia( fx_d2q( omega, 40 ) ), 31 );
}

void szamitfejr( motorst* pmot ) {
	vekt2 i( cos( pmot->kor1.alfa ), sin( pmot->kor1.alfa ) );
	vekt2 j = forgatas90fokkal( i );

	if( pmot->hatra_f )
		pmot->fejr = pmot->vezetor + i*0.09 + j*0.63;
	else
		pmot->fejr = pmot->vezetor - i*0.09 + j*0.63;
}

int elsomegoltemasodikat( motorst* pmot1, motorst* pmot2 ) {
	if( absnegyzet( pmot2->fejr - pmot1->kor2.r ) < Fejkerektavnegyzet )
		return 1;
	if( absnegyzet( pmot2->fejr - pmot1->kor4.r ) < Fejkerektavnegyzet )
		return 1;
	return 0;
}
