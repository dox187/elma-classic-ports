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
	unsigned meret = 65536u;
	#ifdef ELMA_PSX
		// The PS1 version has no zoom and too little RAM for 64 kB each:
		// only the picture's rows, as in the original game.
		meret = unsigned(hossz);
	#endif
	{ tomb = NEW(unsigned char*) unsigned char[meret]; }
	if( !tomb )
		uzenet( "memory!" );
	memset( tomb, lyuk, meret );
	for( int y = 0; y < ysize; y++ )
		for( int x = 0; x < xsize; x++ )
			tomb[y*256+x] = ppic->gpixel( x, y );

	DELETE ppic; }
}

kiskep::~kiskep( void ) {
	if( tomb )
		DELETE tomb; }
}
