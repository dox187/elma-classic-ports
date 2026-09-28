#include	"all.h"

const int Animsize = 40;

anim::anim( pic8* nagykep, char* uzenet_filenev, int meret, int szuro,
			unsigned char* paltomb, int forraskocka ) {
	int i;
	if( meret <= 0 )
		meret = Animsize;
	if( forraskocka <= 0 )
		forraskocka = Animsize;
	frameszam = 0;
	for( i = 0; i < MAXANIMFRAME; i++ )
		ppictomb[i] = NULL;

	if( nagykep->getxsize() % forraskocka ) {
		char tmp[80];
		sprintf( tmp, "Picture xsize must be a multiply of %d!", forraskocka );
		uzenet( tmp, uzenet_filenev );
	}
	frameszam = nagykep->getxsize() / forraskocka;
	if( frameszam < 0 )
		hiba( "uiuiotb" );
	if( frameszam > MAXANIMFRAME ) {
		char tmp[80];
		sprintf( tmp, "Too many frames in picture! Max frame is %d!", (int)MAXANIMFRAME );
		uzenet( tmp, uzenet_filenev );
	}

	for( i = 0; i < frameszam; i++ ) {
		ppictomb[i] = new pic8( forraskocka, forraskocka );
		blt8( ppictomb[i], nagykep, -forraskocka*i, 0 );
		if( meret != forraskocka ) {
			pic8* pnagy = atmeretez_szurovel( ppictomb[i], meret, meret, szuro, paltomb,
											  nagykep->gpixel( 0, 0 ), 0 );
			delete ppictomb[i];
			ppictomb[i] = pnagy;
		}
		forditkepet( ppictomb[i] );
		spriteosit( ppictomb[i], nagykep->gpixel( 0, 0 ) );
	}
}

anim::~anim( void ) {
	frameszam = 0;
	for( int i = 0; i < MAXANIMFRAME; i++ ) {
		if( ppictomb[i] ) {
			delete ppictomb[i];
			ppictomb[i] = NULL;
		}
	}
}

static const double Egyframeido = 0.014;

pic8* anim::getframe( double ido ) {
	int sorszam = ido / Egyframeido;
	int i = sorszam % frameszam;
	return ppictomb[i];
}

pic8* anim::getframebyindex( int index ) {
	if( index < 0 || index >= frameszam )
		hiba( "678673" );
	return ppictomb[index];
}


// Menu sisakjanal egy kis piros vonalat odahuz fole:
void anim::korrigal( void ) {
	for( int i = 0; i < frameszam; i++ ) {
		int x;
		pic8* ujpic = new pic8( Animsize, Animsize+1 );
		unsigned char atlatszo = ppictomb[i]->gpixel( 0, 0 );
		ujpic->fillbox( atlatszo );
		blt8( ujpic, ppictomb[i], 0, 1 );
		// Most behuzzuk vonalat balrol jobb szelig:
		for( x = 0; x < Animsize; x++ ) {
			if( ujpic->gpixel( x, 1 ) != atlatszo ) {
				for( int j = x+4; j < Animsize; j++ )
					ujpic->ppixel( j, 0, ujpic->gpixel( x+3, 1 ) );
				break;
			}
		}
		// Most behuzunk atlatszot jobbrol jobb szelig:
		for( x = Animsize-1; x > 0; x-- ) {
			if( ujpic->gpixel( x, 1 ) != atlatszo ) {
				for( int j = x-3; j < Animsize; j++ )
					ujpic->ppixel( j, 0, atlatszo );
				break;
			}
		}
		spriteosit( ujpic, ujpic->gpixel( 0, 0 ) );
		delete ppictomb[i];
		ppictomb[i] = ujpic;
	}
}
