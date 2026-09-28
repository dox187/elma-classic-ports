#include	"all.h"

static int Vonalvizhossz, Vonalfugghossz;

static int Digdx, Kozdx, Koztesdx;

static int Digitxsize, Digitysize;

static int Ketpx, Ketpy1, Ketpy2;

static pic8* Ppic8 = NULL;
static unsigned char* Lookup = NULL;

const double Idod2lszorzo = 100.0/(182.0*0.0024);

static void kikettospont( int x, int y ) {
	Ppic8->vizszegmens_look( x+Ketpx, y+Ketpy1, 2, Lookup );
	Ppic8->vizszegmens_look( x+Ketpx, y+Ketpy1+1, 2, Lookup );

	Ppic8->vizszegmens_look( x+Ketpx, y+Ketpy2, 2, Lookup );
	Ppic8->vizszegmens_look( x+Ketpx, y+Ketpy2+1, 2, Lookup );
}

static void kiszegmens( int szam, int x, int y ) {
	switch( szam ) {
		case 0:
			Ppic8->fuggszegmens_look( x,
									  y+1,
									  Vonalfugghossz, Lookup );
			break;
		case 1:
			Ppic8->fuggszegmens_look( x+Vonalvizhossz+1,
								  y+1,
								  Vonalfugghossz, Lookup );
			break;
		case 2:
			Ppic8->fuggszegmens_look( x,
								  y+Vonalfugghossz+2,
								  Vonalfugghossz, Lookup );
			break;
		case 3:
			Ppic8->fuggszegmens_look( x+Vonalvizhossz+1,
								  y+Vonalfugghossz+2,
								  Vonalfugghossz, Lookup );
			break;
		case 4:
			Ppic8->vizszegmens_look( x+1,
								 y,
								 Vonalvizhossz, Lookup );
			break;
		case 5:
			Ppic8->vizszegmens_look( x+1,
								 y+Vonalfugghossz+1,
								 Vonalvizhossz, Lookup );
			break;
		case 6:
			Ppic8->vizszegmens_look( x+1,
								 y+Vonalfugghossz+Vonalfugghossz+2,
								 Vonalvizhossz, Lookup );
			break;
		default:
			hiba( "kiszegmens-ben szegmens out of range!" );
			break;
	}
}

static void kiegydigit( int c, int x, int y ) {
	switch( c ) {
		case '0':
			kiszegmens( 4, x, y );
			kiszegmens( 0, x, y );
			kiszegmens( 1, x, y );
			kiszegmens( 2, x, y );
			kiszegmens( 3, x, y );
			kiszegmens( 6, x, y );
			break;
		case '1':
			kiszegmens( 1, x, y );
			kiszegmens( 3, x, y );
			break;
		case '2':
			kiszegmens( 4, x, y );
			kiszegmens( 0, x, y );
			kiszegmens( 5, x, y );
			kiszegmens( 3, x, y );
			kiszegmens( 6, x, y );
			break;
		case '3':
			kiszegmens( 4, x, y );
			kiszegmens( 1, x, y );
			kiszegmens( 5, x, y );
			kiszegmens( 3, x, y );
			kiszegmens( 6, x, y );
			break;
		case '4':
			kiszegmens( 1, x, y );
			kiszegmens( 5, x, y );
			kiszegmens( 2, x, y );
			kiszegmens( 3, x, y );
			break;
		case '5':
			kiszegmens( 4, x, y );
			kiszegmens( 1, x, y );
			kiszegmens( 5, x, y );
			kiszegmens( 2, x, y );
			kiszegmens( 6, x, y );
			break;
		case '6':
			kiszegmens( 4, x, y );
			kiszegmens( 0, x, y );
			kiszegmens( 1, x, y );
			kiszegmens( 5, x, y );
			kiszegmens( 2, x, y );
			kiszegmens( 6, x, y );
			break;
		case '7':
			kiszegmens( 1, x, y );
			kiszegmens( 3, x, y );
			kiszegmens( 6, x, y );
			break;
		case '8':
			kiszegmens( 4, x, y );
			kiszegmens( 0, x, y );
			kiszegmens( 1, x, y );
			kiszegmens( 5, x, y );
			kiszegmens( 2, x, y );
			kiszegmens( 3, x, y );
			kiszegmens( 6, x, y );
			break;
		case '9':
			kiszegmens( 4, x, y );
			kiszegmens( 1, x, y );
			kiszegmens( 5, x, y );
			kiszegmens( 2, x, y );
			kiszegmens( 3, x, y );
			kiszegmens( 6, x, y );
			break;
		default:
			hiba( "kiegydigit-ben c out of range!" );
	}
}

static void kiegyszam( char* time, int x, int y ) {
	kiegydigit( time[0], x, y );
	x += Digdx;
	kiegydigit( time[1], x, y );
	kikettospont( x, y );
	x += Kozdx;
	kiegydigit( time[3], x, y );
	x += Digdx;
	kiegydigit( time[4], x, y );
	kikettospont( x, y );
	x += Kozdx;
	kiegydigit( time[6], x, y );
	x += Digdx;
	kiegydigit( time[7], x, y );
}

void kidigit( char* time1, double fogoido, double time2d, pic8* ppic8,
					int kepxsize, int kepysize, int teljesxsize ) {

	Ppic8 = ppic8;
	Lookup = Plgr->idonegtomb;

	// The times are always 28 pixel from the picture's edge at full size
	// (like on a 640-wide picture), proportionally closer on a shrunk picture:
	double kepmeretx = double(kepxsize)/teljesxsize;
	double kepmerety = kepysize/480.0;

	//unsigned char szin1 = Plgr->idoszin1;
	//unsigned char szin2 = Plgr->idoszin2;

	int xtav = 28*kepmeretx;
	int x = xtav;
	int y = 420*kepmerety;

	Vonalvizhossz = 10*kepmerety,
	Vonalfugghossz = 16*kepmerety;

	Digdx = 16*kepmerety,
	Kozdx = 24*kepmerety,
	Koztesdx = 364*kepmeretx;

	Digitxsize = Digdx*7+Kozdx*4+Koztesdx,
	Digitysize = 2*Vonalfugghossz+5;

	Ketpx  = 17*kepmerety;
	Ketpy1 = 9*kepmerety;
	Ketpy2 = 23*kepmerety;

	long l2 = time2d*Idod2lszorzo;
	char time2[20];
	ido2string( l2, time2 );

	#ifdef ELMA_CLI
	// Terminalban az idok szovegkent kerulnek a kep fole:
	unsigned char* sor = ppic8->getptr( y + Digitysize/2 );
	if( time1[0] != 0 )
		cli_text_at_pixel( sor + x, time1, CLI_ALIGN_LEFT, CLI_COLOR_TIME );
	cli_text_at_pixel( sor + kepxsize-1 - xtav, time2, CLI_ALIGN_RIGHT,
					   CLI_COLOR_TIME );
	if( fogoido >= 0 ) {
		long lf = fogoido*Idod2lszorzo;
		char fogo[20];
		ido2string( lf, fogo );
		cli_text_at_pixel( sor + kepxsize/2, fogo, CLI_ALIGN_CENTER,
						   CLI_COLOR_TIME );
	}
	return;
	#endif

	// Elso:
	int xelso = x;
	if( time1[0] != 0 )
		kiegyszam( time1, xelso, y );

	x += Digdx*3+Kozdx*2;

	x += Koztesdx;
	x = kepxsize - (xtav + Digdx*3+Kozdx*3);

	// Masodik:
	kiegyszam( time2, x, y );

	// Kirakjuk meg kozepre fogoido-t is:
	if( fogoido >= 0 ) {
		long lf = fogoido*Idod2lszorzo;
		char fogo[20];
		ido2string( lf, fogo );
		kiegyszam( fogo, (xelso+x)>>1, y );
	}
}


