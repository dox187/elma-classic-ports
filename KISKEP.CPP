#include	"all.h"

kiskep::kiskep( char* pic8nev, pic8* ppic ) {
	tomb = NULL;
	if( !ppic ) {
		{ ppic = NEW(pic8*) pic8( pic8nev ); }
	}

	lyuk = ppic->gpixel( 0, 0 );

	xsize = ppic->getxsize();
	ysize = ppic->getysize();
	if( xsize > 255 || ysize > 255 )
		hiba( "kiskepben size > 255!" );
	hossz = ysize*256l;
	// dobozki (doboz.cpp) a kep szelen tul is mintavetelezhet egy-egy
	// pixelt (nagyitott motoron gyakrabban), az index ((y<<8)+x) mindig
	// 16 bites: a teljes 64 kB-ot lefoglaljuk, a kepen kivul atlatszora:
	{ tomb = NEW(unsigned char*) unsigned char[65536u]; }
	if( !tomb )
		uzenet( "memory!" );
	memset( tomb, lyuk, 65536u );
	for( int y = 0; y < ysize; y++ )
		for( int x = 0; x < xsize; x++ )
			tomb[y*256+x] = ppic->gpixel( x, y );

	DELETE ppic; }
}

kiskep::~kiskep( void ) {
	if( tomb )
		DELETE tomb; }
}
