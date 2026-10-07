#include	"w_all.h"


// Ha igaz, alulrol indul y (kirajz320 allitja igazba):
int Locky0_alul = 0; 


void ddfinish( void )
{
}


void ddinit( void ) {
}

static unsigned char* Mutbuffer[480];
static int Mutbuffervan = 0;

unsigned char** lockbackbuffer( int fizikai ) {
	fizikai++;

	if( !Mutbuffervan ) {
		Mutbuffervan = 1;
		for( int i = 0; i < 480; i++ ) {
			Mutbuffer[i] = new unsigned char[640];	
		}
	}
	return Mutbuffer;
}

void unlockbackbuffer( void ) {
}


unsigned char** lockfrontbuffer( void ) {
	if( !Mutbuffervan ) {
		Mutbuffervan = 1;
		for( int i = 0; i < 480; i++ ) {
			Mutbuffer[i] = new unsigned char[640];	
		}
	}
	return Mutbuffer;
}

void unlockfrontbuffer( void ) {
}


// PALETTA:

//	LPDIRECTDRAWPALETTE pddpal;
ddpal::ddpal( unsigned char* tomb ) {
}

ddpal::~ddpal( void ) {
}

void ddpal::set( void ) {
}


