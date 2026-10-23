#include	"all.h"
#include "LE_STRUCT.H"

void wav::lefoglal( void ) {
	if( size > 1000000 )
		hiba( "wav::alloc-ban size > 1000000!" );
	{ tomb = NEW(signed short*) signed short[size]; }
	if( !tomb )
		uzenet( "wav::alloc-ban memory!" );
}

#ifdef ELMA_PSX
// tomb[i] *= szorzo for every sample, with 16 fraction bits (the result
// truncated toward zero, as the conversion of the double):
static void szorzas( signed short* tomb, unsigned size, double szorzo ) {
	const int32_t f = int32_t( szorzo*65536.0 );
	for( unsigned i = 0; i < size; i++ ) {
		int64_t v = int64_t( tomb[i] )*f;
		if( v < 0 )
			v += 65535;
		tomb[i] = (signed short)( v >> 16 );
	}
}
#endif

wav::wav( unsigned sizepar ) {
	tomb = NULL;
#ifdef ELMA_PSX
	tomb8 = NULL;
	lut = NULL;
#endif
	size = sizepar;
	lefoglal();
}

static void nevwavtest( char* nev ) {
	int i = strlen( nev ) - 1;
	while( i > 0 ) {
		if( nev[i] == '.' ) {
			// Most ponton all:
			if( strcmpi( ".wav", &nev[i] ) == 0 )
				return;
			else
				hiba( "nevrawtest-ben nincs .raw!" );
		}
		i--;
	}
	hiba( "nevwavtest-ben nincs .wav!" );
}


// A file fejlece 44 byte, ezert 32 bites mezok kellenek
// (64 bites rendszeren long 8 byte):
struct wavheader {
	char riff[4];
	int32_t hossz1;
	char wave[4];
	// format:
	char fmt[4];
	int32_t miez1;
	short mod; // 1 -> 8bit uncompressed
	short channel; // 1 -> mono, 2 -> stereo
	unsigned short frekvencia;
	short miez2, miez3, miez4;
	int32_t nemkene;
	// audio data:
	char data[4];
	int32_t hossz;
};

static_assert(sizeof(wavheader)==44,"Legacy WAV header layout changed");
inline void elma_swap(wavheader& p) { elma_swap(p.hossz1);elma_swap(p.miez1);elma_swap(p.mod);elma_swap(p.channel);elma_swap(p.frekvencia);elma_swap(p.miez2);elma_swap(p.miez3);elma_swap(p.miez4);elma_swap(p.nemkene);elma_swap(p.hossz); }

wav::wav( char* nev, double maxamplitudo, int start, int ucsoutani ) {
	tomb = NULL;
#ifdef ELMA_PSX
	tomb8 = NULL;
	lut = NULL;
#endif
	nevwavtest( nev );
	// Lemeri file hosszat:
	FILE* h = qopen( nev, "rb" );
	if( !h )
		hiba( "Nem tudta megnyitni file-t: ", nev );

	wavheader header;
	int negyvennegy = 44;
	if( sizeof( wavheader ) != negyvennegy )
		hiba( "sizeof( wavheader ) != 44!" );

	if( elma_read( &header, 1, 44, h ) != 44 )
		hiba( "Nem sikerult beolvasni wav-ot!" );

	long hossz = header.hossz;
	int bit16 = 1;

	// Reszlet eldontese:
	int reszlet = 1;
	if( ucsoutani <= 0 )
		reszlet = 0;
	int reszhossz = ucsoutani-start;
	if( !reszlet ) {
		start = 0;
		if( bit16 )
			reszhossz = hossz/2;
		else
			reszhossz = hossz;
	}

	if( header.channel != 1 )
		hiba( "Wav file nem mono!: ", nev );

	if( bit16 ) {
		// 16 bites uncompressed:
		if( hossz%2 )
			hiba( "16 bites wav-nal nem paros byteszam! (abcd)" );
		size = reszhossz;
		if( start+reszhossz > hossz/2 )
			hiba( "Reszlet kilog wav-bol!" );
		lefoglal();
		qseek( h, start*2, SEEK_CUR );
		if( elma_read( tomb, 1, size*2, h ) != size*2 )
			hiba( "Nem sikerult beolvasni wav-ot!: ", nev );
	}
	else {
		// 8 bites uncompressed:
		if( reszlet )
			hiba( "8 bitre meg nincs megirva reszlet!" );
		size = hossz;
		lefoglal();
		if( elma_read( tomb, 1, hossz, h ) != hossz )
			hiba( "Nem sikerult beolvasni wav-ot!: ", nev );
		unsigned char* bytetomb = (unsigned char*)tomb;
		for( int i = size-1; i >= 0; i-- ) {
			tomb[i] = short((((short)(bytetomb[i]))-128)<<8);
		}
	}

	qclose( h );

	// Megkeresi maximalis amplitudot:
	int maxamp = 1;
	for( int i = 0; i < size; i++ ) {
		if( tomb[i] > 0 ) {
			if( tomb[i] > maxamp )
				maxamp = tomb[i];
		}
		else {
			if( -tomb[i] > maxamp )
				maxamp = -tomb[i];
		}
	}
	// Kiszamolja szorzot:
	double szorzo = 32000.0*maxamplitudo/double(maxamp);
#ifdef ELMA_PSX
	// (In fixed point: a multiplication of doubles a sample took the PS1
	// seconds at the first start of the sound.)
	szorzas( tomb, size, szorzo );
#else
	for( int i = 0; i < size; i++ ) {
		tomb[i] *= szorzo;
	}
#endif
}

#ifdef ELMA_PSX
// G.711 mu-law of a 16-bit sample (the exponent from a table of the top
// bits), and back:
static unsigned char Mulawkitevo[256];

static unsigned char mulaw( int minta ) {
	int elojel = 0;
	if( minta < 0 ) {
		elojel = 0x80;
		minta = -minta;
	}
	if( minta > 32635 )
		minta = 32635;
	minta += 0x84;
	const int kitevo = Mulawkitevo[(minta >> 7) & 0xff];
	const int mantissza = (minta >> (kitevo+3)) & 0x0f;
	return (unsigned char)~(elojel | (kitevo << 4) | mantissza);
}

static int mulawvissza( unsigned char kod ) {
	kod = (unsigned char)~kod;
	const int kitevo = (kod >> 4) & 7;
	const int minta = (((kod & 0x0f) << 3) + 0x84 << kitevo) - 0x84;
	return (kod & 0x80) ? -minta : minta;
}

void wav::tomorit( void ) {
	if( tomb8 || !tomb )
		return;
	if( !Mulawkitevo[255] ) {
		for( int i = 0; i < 256; i++ ) {
			int k = 0;
			while( k < 7 && (i >> (k+1)) )
				k++;
			Mulawkitevo[i] = (unsigned char)k;
		}
	}
	long maxamp = 1;
	for( unsigned i = 0; i < size; i++ ) {
		const long a = tomb[i] < 0 ? -long( tomb[i] ) : tomb[i];
		if( a > maxamp )
			maxamp = a;
	}
	// The scale reaches the sound's peak (32124, the largest mu-law value):
	lut = new short[256];
	tomb8 = new unsigned char[size ? size : 1];
	if( !lut || !tomb8 )
		uzenet( "wav::tomorit-ban memory!" );
	for( int k = 0; k < 256; k++ )
		lut[k] = short( long( mulawvissza( (unsigned char)k ) )*maxamp/32124 );
	// The codes of the top 12 bits of a 16-bit sample (made once):
	static unsigned char* kodok = NULL;
	if( !kodok ) {
		kodok = new unsigned char[4096];
		for( int k = 0; k < 4096; k++ )
			kodok[k] = mulaw( (k << 4) - 32768 + 8 );
	}
	// (15 fraction bits: |tomb| <= maxamp keeps the product within 31 bits.)
	const long szorzo = (32124l << 15)/maxamp;
	for( unsigned i = 0; i < size; i++ ) {
		const long v = (long( tomb[i] )*szorzo) >> 15;
		tomb8[i] = kodok[(v + 32768) >> 4];
	}
	DELETE[] tomb; }
	tomb = NULL;
}
#endif

void wav::save( char* nev ) {
	nevwavtest( nev );
	// Lemeri file hosszat:
	FILE* h = fopen( nev, "wb" );
	if( !h )
		hiba( "Nem tudta megnyitni file-t: ", nev );
	if( elma_write( tomb, 1, size*2, h ) != size*2 )
			hiba( "Nem sikerult irni wav-ot wav::save-ben!" );
	fclose( h );
}


// Elejere tesz egy loopot a vegebol, amit aztan le is vag:
void wav::loopol( int n ) {
	if( n >= size )
		hiba( "n >= size!" );
	for( int i = 0; i < n; i++ ) {
		double arany = ((double)i)/n;
		tomb[i] = arany*tomb[i] + (1-arany)*tomb[size-n+i];
	}
	size -= n;
}

// pwav elejet rateszi vegere:
void wav::vegereilleszt( wav* pwav, int n ) {
	if( n >= size )
		hiba( "n >= size!" );
	if( n >= pwav->size )
		hiba( "n >= pwav->size!" );
	for( int i = 0; i < n; i++ ) {
		double arany = ((double)i)/n;
		tomb[size-n+i] = (1-arany)*tomb[i] + arany*pwav->tomb[i];
	}
}

void wav::hangero( double szorzo ) {
#ifdef ELMA_PSX
	szorzas( tomb, size, szorzo );
#else
	for( int i = 0; i < size; i++ ) {
		tomb[i] *= szorzo;
	}
#endif
}

// WAV2 !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

//short* tomb, mtomb;
wav2::wav2( wav* pwav ) {
	mtomb = NULL;
	tomb = pwav->tomb;
	#ifndef WATCOM
		hiba( "wav2 csak Watcom alatt mukodik!" );
	#endif
	if( pwav->size > 64000 )
		hiba( "wav2-ben size > 64000!" );
	{ mtomb = NEW(short*) short[pwav->size]; }
	if( !mtomb )
		uzenet( "memory" );
	for( int i = 0; i < pwav->size-1; i++ )
		mtomb[i] = tomb[i+1]-tomb[i];
	mtomb[pwav->size-1] = tomb[0]-tomb[pwav->size-1];
	ulsize = ((unsigned long)pwav->size)*65536;
	ulfuto = 0;
}

void wav2::reset( int fazis ) {
	if( fazis < 0 )
		ulfuto = 0;
	else
		ulfuto = fazis*65536;
}

// dt 65536 szoros:
short wav2::getnextsample( long dt ) {
	ulfuto += dt;
	if( ulfuto >= ulsize )
		ulfuto -= ulsize;
	const unsigned high = ulfuto >> 16;
	const unsigned low = ulfuto & 65535u;
	return tomb[high] + ((int32_t(mtomb[high])*int32_t(low))>>16);
}

