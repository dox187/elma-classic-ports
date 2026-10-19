
//enum { W_MONO = 1, W_LEFT, W_RIGHT };

class wav {
	void	lefoglal( void ); // size alapjan lefoglal!
public:
	signed short* 	tomb;
	unsigned 	 	size;

			wav( unsigned sizepar );
			// maxamplitudo 0 es 1 kozott valtozik!:
			wav( char* nev, double maxamplitudo,
									int start = -1, int ucsoutani = -1 );
	void    save( char* nev );
	// Manipulalas:

	// Elejere tesz egy loopot a vegebol:
	void loopol( int n );
	// pwav elejet rateszi vegere:
	void vegereilleszt( wav* pwav, int n );
	void hangero( double szorzo );
#ifdef ELMA_PSX
	// The PS1 version keeps the samples as 8-bit codes of a companded scale
	// (mu-law, of the sound's own peak) once they are ready (tomorit):
	// tomb8, with lut giving the 16-bit value of each code; tomb is then
	// NULL. Half the RAM.
	unsigned char* tomb8;
	short* lut;
	void tomorit( void );
	short minta( long i ) { return tomb8 ? lut[tomb8[i]] : tomb[i]; }
	void masol( short* cel, long kezd, long db ) {
		if( !tomb8 ) {
			for( long j = 0; j < db; j++ )
				cel[j] = tomb[kezd+j];
			return;
		}
		const unsigned char* t = tomb8+kezd;
		for( long j = 0; j < db; j++ )
			cel[j] = lut[t[j]];
	}
#endif
};

#ifdef ELMA_PSX
#define WAVMINTA( pwav, i ) ((pwav)->minta( i ))
#else
#define WAVMINTA( pwav, i ) ((pwav)->tomb[i])
#endif


class wav2 {
	short	*tomb, *mtomb;
	uint32_t ulsize, ulfuto; // plow/phigh ennek also/felso szavara mutat
	unsigned short *plow, *phigh;
public:
		wav2( wav* pwav );
	void reset( int fazis = -1 );
	// dt 65536 szoros:
	short getnextsample( long dt );
};

