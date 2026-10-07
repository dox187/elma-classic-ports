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
	// dobozki (doboz.cpp) can sample a pixel past the picture's edge too
	// (more often on a zoomed engine), and the index ((y<<8)+x) is always
	// 16 bits: allocate the full 64 kB, set to transparent outside the
	// picture:
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
