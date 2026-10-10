// What the physics sources of the original game (VEKT2.CPP, LEPTET.CPP,
// BEALLIT.CPP, UTKOZES.CPP, UTKOZES2.CPP, SZAKASZ.CPP) need from its all.h,
// so that they compile on the host unchanged as the reference of the SNES
// physics (pcphys.cpp has the rest of the game they call).
#ifndef PCPHYS_ALL_H
#define PCPHYS_ALL_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include "vekt2.h"
#include "kor.h"
#include "adatok.h"
#include "beallit.h"
#include "leptet.h"
#include "utkozes.h"
#include "szakasz.h"
#include "utkozes2.h"

void hiba( const char* text1, const char* text2 = NULL, const char* text3 = NULL );
void uzenet( const char* text1, const char* text2 = NULL, const char* text3 = NULL );

extern double K_pi, K_pip2;

#define NEW( a ) new
#define DELETE { delete

enum { WAV_UTODES = 1, WAV_TORES, WAV_SIKER, WAV_EVES, WAV_FORDULAS,
	   WAV_UGRAS1, WAV_UGRAS2 };
void startwavegyujto( int wavazonosito, double hangero, int objszam );

#define MAXKEREK (52)
#define MAXGYURU (300)
enum { T_CEL = 1, T_KAJA, T_HALALOS, T_KEZDO };
enum { KT_NORMAL, KT_UP, KT_DOWN, KT_LEFT, KT_RIGHT };

class kerek {
public:
	vekt2 r;
	int tipus;
	int kajatipus;
	int foodsorszam;
	int aktiv;
};

class gyuru {
public:
	int pontszam;
	vekt2* ponttomb;
	int koveto;
};

class topol {
public:
	gyuru* ptomb[MAXGYURU];
	kerek* kerektomb[MAXKEREK];
	kerek* getptrkerek( int index );
	void killerekelore( void );
	int setallaktiv( motorst* pmot );
};

extern topol* Ptop;

// Only what the game needs of the ground's brush during play: whether the
// bike left it (ECSET.CPP).
class ecset {
public:
	vekt2 eredetiorigo;
	double eredetimaxx, eredetisorszam;
	void getorigoandsize( void );
	int kilogna( vekt2 r );
};

extern ecset* Pecsetalso;
extern int Single, Tag;

#endif
