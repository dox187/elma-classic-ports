#include "w_all.h"


static void semmi( void ) {
		
}

void mv_main( void ) {
	unsigned char* tomb = new unsigned char[768];
	for( int i = 0; i < 256; i++ ) {
			tomb[i*3+0] = i/4;
			tomb[i*3+1] = i/4;
			tomb[i*3+2] = i/4;
	}
	ddpal szurkepal( tomb );
	szurkepal.set();
	while( 1 ) {
		// Kirajzol:
		unsigned char** bufftomb = lockbackbuffer( 1 );
		for( int y = 0; y < 480; y++ )
			for( int x = 0; x < 640; x++ )
				bufftomb[y][x] = x;
		unlockbackbuffer();

		bufftomb = lockfrontbuffer();
		for( int x = 0; x < 400; x++ )
			bufftomb[200][x] = 0;
		unlockfrontbuffer();


		while( 1 ) {			
			int c = mk_getextchar();
			if( c == MK_ESC ) {
				mv_exit();	
			}
			if( c == MK_ENTER ) {
					
			}
		}
	}
}
