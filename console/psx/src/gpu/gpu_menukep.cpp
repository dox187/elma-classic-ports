// The menus' drawing (MENUKEP.CPP of the core) for the PlayStation version.
// The same pictures as the original, but a menu frame only redraws what
// moved: the rectangles of the balls and the helmet of the previous frame are
// restored from the background, the new ones drawn straight into the front
// buffer, and only those rectangles are sent to VRAM (gv_menu_dirty). The
// rows of a ball are computed with integers instead of a sqrt per row in
// software floating point. Everything else is the original code.
#include "gpu/gpu_video.h"
#include	"all.h"

pic8* Buffsima = NULL;
pic8* Buffgolyo = NULL;

int Menuxsize = 640, Menuysize = 480, Menueltolasx = 0, Menueltolasy = 0;
int Menueredeti = 0;

static pic8 *Kisnevsima = NULL, *Kisnevgolyo = NULL;
abc8* Pmenuabc = NULL;
anim* Psisak = NULL;

static pic8 *Vegetile1 = NULL, *Vegetile2 = NULL;

ddpal* Pmenupal = NULL;
unsigned char Menupaltomb[768];

/*void retusal( pic8* ppic ) {
	int xsize = ppic->getxsize();
	int ysize = ppic->getysize();
	for( int y = 0; y < ysize; y++ ) {
		for( int x = 0; x < xsize; x++ ) {
			unsigned szin = ppic->gpixel( x, y );
			if( szin == 2 )
				ppic->ppixel( x, y, 30 );
		}
	}
} */

void initmenukep1( void ) {
	if( Buffsima )
		hiba( "initmenukep1-ben Buffsima!" );
	Buffsima = new pic8( 640, 480 );
	Buffgolyo = new pic8( 640, 480 );
	Kisnevsima = new pic8( "szoveg1.pcx" ); //retusal( Kisnevsima );
	Kisnevgolyo = new pic8( "szoveg2.pcx" ); //retusal( Kisnevgolyo );
	Pmenuabc = new abc8( "menu.abc" );
	Pmenuabc->settav( 2 );

	pic8* sisaktmp = new pic8( "sisak.pcx" );
	forditkepet( sisaktmp );
	Psisak = new anim( sisaktmp, "sisak.pcx" );
	delete sisaktmp; sisaktmp = NULL;
	Psisak->korrigal();

	Vegetile1 = new pic8( "ures1b.pcx" );
	Vegetile2 = new pic8( "ures2b.pcx" );

	initgolyo();
}

void initmenukep2( void ) {
	if( Pmenupal )
		hiba( "initmenukep2-ben Pmenupal!" );
	pcxtopal( "intro.pcx", &Pmenupal ); // O new-ik egy ddpal-t
	pcxtopal( "intro.pcx", Menupaltomb );
	menumeretbeallit();
}

static pic8* Tmpbuffer = NULL; // Temporary

void golyofalak( int xsize, int ysize ); // golyutk.cpp

int menumeretbeallit( void ) {
	int xsize = 640, ysize = 480;
	if( !Menueredeti )
		dd_menumeret( &xsize, &ysize );
	if( xsize < 640 )
		xsize = 640;
	if( ysize < 480 )
		ysize = 480;
	if( xsize == Menuxsize && ysize == Menuysize )
		return 0;
	Menuxsize = xsize;
	Menuysize = ysize;
	Menueltolasx = (Menuxsize-640)/2;
	Menueltolasy = (Menuysize-480)/2;
	delete Buffsima;
	delete Buffgolyo;
	Buffsima = new pic8( Menuxsize, Menuysize );
	Buffgolyo = new pic8( Menuxsize, Menuysize );
	if( Tmpbuffer ) {
		delete Tmpbuffer;
		Tmpbuffer = new pic8( Menuxsize, Menuysize );
	}
	golyofalak( Menuxsize, Menuysize );
	golyomeret( Menuxsize, Menuysize );
	frontbuffermeret( Menuxsize, Menuysize );
	return 1;
}

void tilevaltas( void ) {
	for( int y = 0; y < Kisnevsima->getysize(); y += Vegetile1->getysize() ) {
		for( int x = 0; x < Kisnevsima->getxsize(); x += Vegetile1->getxsize() ) {
			blt8( Kisnevsima, Vegetile1, x, y );
			blt8( Kisnevgolyo, Vegetile2, x, y );
		}
	}
}

// The rows grow on demand (the original took MAXSZOVEGSOR at once): there
// is room for SOROK_MIN rows, or for the power of two above elemszam.
static const int SOROK_MIN = 16;

szoveglista::szoveglista( void ) {
	sisakx = sisaky = -100;

	elemszam = 0;
	ervenyes = 0;
	sorok = new egyszovsor[SOROK_MIN];
	if( !sorok )
		hiba( "Memoria!" );
}

szoveglista::~szoveglista( void ) {
	if( !sorok )
		hiba( "szoveglista::~szoveglista !sorok!" );
	delete sorok;
	sorok = NULL;
}

void szoveglista::addszoveg( char* text, int x, int y ) {
	if( strlen( text ) > 100 )
		hiba( "89ygui" );
	if( elemszam >= MAXSZOVEGSOR-1 )
		hiba( "849yptgp8" );
	if( elemszam >= SOROK_MIN && !(elemszam & (elemszam-1)) ) {
		// Full: twice the room.
		egyszovsor* uj = new egyszovsor[2*elemszam];
		if( !uj )
			hiba( "Memoria!" );
		memcpy( uj, sorok, elemszam*sizeof( egyszovsor ) );
		delete[] sorok;
		sorok = uj;
	}
	strcpy( sorok[elemszam].text, text );
	sorok[elemszam].x = x;
	sorok[elemszam].y = y;
	sorok[elemszam].kozep = 0;
	elemszam++;
	ervenyes = 0;
}

void szoveglista::addszoveg_kozep( char* text, int x, int y ) {
	addszoveg( text, x-Pmenuabc->len( text )/2, y );
	sorok[elemszam-1].kozep = 1;
}

void szoveglista::setsisak( int x, int y ) {
	sisakx = x;
	sisaky = y;
}

void szoveglista::clear( void ) {
	if( elemszam > SOROK_MIN ) {
		delete[] sorok;
		sorok = new egyszovsor[SOROK_MIN];
		if( !sorok )
			hiba( "Memoria!" );
	}
	elemszam = 0;
	ervenyes = 0;
}


static int Scrolly1 = 0; // Ennel kiseb x-ek helyere sotet zoldet rak kirazgolyo
static unsigned char Introhatter = 254;
static unsigned char* Zoldsor = NULL;
static unsigned char* Hattersor = NULL;

// Integer square root of a 32-bit number.
static unsigned gyok32( unsigned n ) {
	unsigned eredmeny = 0, bit = 1u << 30;
	while( bit > n )
		bit >>= 2;
	while( bit ) {
		if( n >= eredmeny + bit ) {
			n -= eredmeny + bit;
			eredmeny = (eredmeny >> 1) + bit;
		}
		else
			eredmeny >>= 1;
		bit >>= 2;
	}
	return eredmeny;
}

// The rectangle a ball was drawn in (inclusive), x1 > x2 if none:
struct golyoterulet {
	int x1, y1, x2, y2;
};

// The half widths of a ball's rows, by radius (8 fraction bits): row k
// from the middle is dx[k] wide on both sides; rows narrower than half a
// pixel are left out, as originally.
struct golyosorok {
	int r8;
	int sorszam;
	int dx[160];
};
static golyosorok Sortablak[8];
static int Sortablaszam = 0;

static const golyosorok* sortabla( int r8 ) {
	for( int i = 0; i < Sortablaszam; i++ )
		if( Sortablak[i].r8 == r8 )
			return &Sortablak[i];
	golyosorok* t = &Sortablak[Sortablaszam < 8 ? Sortablaszam++ : 7];
	t->r8 = r8;
	t->sorszam = 0;
	const int r2 = r8*r8;
	for( int k = 0; k < 160; k++ ) {
		const int dx2 = r2 - (k << 8)*(k << 8);
		if( dx2 < 32768 ) // dx < 0.5
			break;
		t->dx[k] = gyok32( dx2 );
		t->sorszam = k+1;
	}
	return t;
}

// Draws a ball of forras into cel (Tmpbuffer originally). Fixed point with
// 8 fraction bits; the middle row is the one nearest to the centre (the
// original's rows are the same but for a rounding at the ends).
static golyoterulet kirajzgolyo_fx( int xo8, int yo8, int r8, pic8* forras, pic8* cel ) {
	golyoterulet ter = { 1, 1, 0, 0 };
	if( !Zoldsor ) {
		Zoldsor = new unsigned char[MAXKEPXSIZE];
		Hattersor = new unsigned char[MAXKEPXSIZE];
		for( int i = 0; i < MAXKEPXSIZE; i++ ) {
			Zoldsor[i] = 248;
			Hattersor[i] = Introhatter;
		}
	}
	const golyosorok* t = sortabla( r8 );
	const int yc = (yo8 + 128) >> 8;
	for( int k = -(t->sorszam-1); k < t->sorszam; k++ ) {
		const int y = yc + k;
		if( y < 0 || y >= Menuysize )
			continue;
		const int dx8 = t->dx[k < 0 ? -k : k];
		// Truncated toward zero, as the conversion of a double:
		const int a = xo8-dx8, b = xo8+dx8;
		int x1 = a >= 0 ? a >> 8 : -((-a) >> 8);
		int x2 = b >= 0 ? b >> 8 : -((-b) >> 8);
		if( x1 < 0 )
			x1 = 0;
		if( x1 > Menuxsize-1 )
			x1 = Menuxsize-1;
		if( x2 < 0 )
			x2 = 0;
		if( x2 > Menuxsize-1 )
			x2 = Menuxsize-1;
		if( x1 >= x2 )
			continue;
		unsigned char* dest = cel->getptr( y ) + x1;
		unsigned char* source;
		if( y < Scrolly1 ) {
			if( forras == Buffgolyo )
				source = Zoldsor;
			else
				source = Hattersor;
		}
		else
			source = forras->getptr( y ) + x1;
		BYTECOPY( dest, source, x2-x1+1 );

		if( ter.x1 > ter.x2 ) {
			ter.x1 = x1;
			ter.x2 = x2;
			ter.y1 = ter.y2 = y;
		}
		if( x1 < ter.x1 )
			ter.x1 = x1;
		if( x2 > ter.x2 )
			ter.x2 = x2;
		ter.y2 = y;
	}
	return ter;
}

static golyoterulet kirajzgolyo( vekt2 g, double r, pic8* forras, pic8* cel ) {
	if( Nincsfal ) {
		if( g.x < -500.0 || g.x > 1500.0 ||
			g.y < -500.0 || g.y > 1500.0 ) {
			golyoterulet ter = { 1, 1, 0, 0 };
			return ter;
		}
	}
	return kirajzgolyo_fx( int( g.x*256.0 ), int( g.y*256.0 ), int( r*256.0 ), forras, cel );
}

// sin and cos of an angle, 14 fraction bits (from a table of a quarter
// period), for the small balls:
static int16_t* Szinusztabla = NULL;
static void szinkoszinusz( double alfa, int* sn, int* cs ) {
	if( !Szinusztabla ) {
		Szinusztabla = new int16_t[1025];
		for( int i = 0; i <= 1024; i++ )
			Szinusztabla[i] = int16_t( sin( i*(K_pi*0.5/1024.0) )*16384.0 + 0.5 );
	}
	int i = int( alfa*(4096.0/(2.0*K_pi)) );
	i &= 4095;
	const int negyed = i >> 10, j = i & 1023;
	int s1 = 0, c1 = 0;
	switch( negyed ) {
		case 0: s1 = Szinusztabla[j]; c1 = Szinusztabla[1024-j]; break;
		case 1: s1 = Szinusztabla[1024-j]; c1 = -Szinusztabla[j]; break;
		case 2: s1 = -Szinusztabla[j]; c1 = -Szinusztabla[1024-j]; break;
		case 3: s1 = -Szinusztabla[1024-j]; c1 = Szinusztabla[j]; break;
	}
	*sn = s1;
	*cs = c1;
}

#ifdef ELMA_CLI
// Menu betuinek fuggoleges kozepe a sor tetejehez kepest:
static int menufontkozep( void ) {
	static int kozep = -1;
	if( kozep >= 0 )
		return kozep;
	int felso = 1000, also = -1000;
	for( int c = 'A'; c <= 'Z'; c++ ) {
		if( !Pmenuabc->ppsprite[c] )
			continue;
		int y1 = Pmenuabc->ytomb[c];
		int y2 = y1 + Pmenuabc->ppsprite[c]->getysize();
		if( y1 < felso )
			felso = y1;
		if( y2 > also )
			also = y2;
	}
	kozep = also > felso ? (felso+also)/2 : 12;
	return kozep;
}
#endif

static double Regiido = 0.0;
static double Elsostabilido = 0.0; // Scroll befejezesekor

// The rectangles drawn into the front buffer by the previous menu frame:
// one for each ball (with its two small balls), the last one the helmet's;
// and the menu serial (gv_menu_serial) after it.
const int MAXTERULET = 16;
static golyoterulet Elozoteruletek[MAXTERULET];
static int Elozoervenyes = 0;
static uint32_t Elozosorozat = 0;

static void egyesit( golyoterulet* a, golyoterulet b ) {
	if( b.x1 > b.x2 )
		return;
	if( a->x1 > a->x2 ) {
		*a = b;
		return;
	}
	if( b.x1 < a->x1 )
		a->x1 = b.x1;
	if( b.y1 < a->y1 )
		a->y1 = b.y1;
	if( b.x2 > a->x2 )
		a->x2 = b.x2;
	if( b.y2 > a->y2 )
		a->y2 = b.y2;
}

// Into the picture (empty if outside):
static void vagas( golyoterulet* t ) {
	if( t->x1 > t->x2 )
		return;
	if( t->x1 < 0 )
		t->x1 = 0;
	if( t->y1 < 0 )
		t->y1 = 0;
	if( t->x2 > Menuxsize-1 )
		t->x2 = Menuxsize-1;
	if( t->y2 > Menuysize-1 )
		t->y2 = Menuysize-1;
	if( t->x1 > t->x2 || t->y1 > t->y2 ) {
		t->x1 = t->y1 = 1;
		t->x2 = t->y2 = 0;
	}
}

static int Kezdoanimjon = 1;

// The tests make so many internal levels selectable (test/gpu_compare_test):
extern "C" volatile int gpu_test_levels;
volatile int gpu_test_levels = 0;

void szoveglista::kirajzol( int nemkellgolyo,
							pic8* rarakkep1, pic8* rarakkep2,
							pic8* rarakkep3, pic8* rarakkep4 ) {
	if( gpu_test_levels > 0 && State ) {
		for( int i = 0; i < MAXJATEKOS; i++ )
			if( State->jatekosok[i].sikerespalyakszama < gpu_test_levels-1 )
				State->jatekosok[i].sikerespalyakszama = gpu_test_levels-1;
	}
	// Kirakjuk hatteret:
	if( menumeretbeallit() )
		ervenyes = 0;
	if( Kezdoanimjon && !Pintro )
		Kezdoanimjon = 0;
	// Only the intro animation draws into it:
	if( !Tmpbuffer && Kezdoanimjon ) // Ideiglenes
		Tmpbuffer = new pic8( Menuxsize, Menuysize );
	#ifdef ELMA_CLI
		// Terminalban nincs bevezeto animacio:
		Kezdoanimjon = 0;
	#endif

	if( !ervenyes && !Kezdoanimjon ) {
		// Ujrarajzoljuk hatterkepeket:
		ervenyes = 1;
		Elozoervenyes = 0;
		int y = -47;
		int paros = 0;
		int kezdox = 0;
		while( y < Menuysize ) {
			int x = kezdox;
			kezdox += 110;
			while( x > 0 )
				x -= Kisnevsima->getxsize();
			paros = !paros;
			while( x < Menuxsize ) {
				blt8( Buffsima, Kisnevsima, x, y );
				blt8( Buffgolyo, Kisnevgolyo, x, y );
				x += Kisnevsima->getxsize();
			}
			y += Kisnevsima->getysize();
		}

		// Menu lemezre mentese:
		//Buffsima->save( "menu.pcx", Menupaltomb );
		//hiba( "Menu kimentve!" );

		// Rairjuk szovegeket vagy kepet:
		if( rarakkep4 ) {
			blt8( Buffsima, rarakkep1, Menueltolasx, Menueltolasy );
			blt8( Buffsima, rarakkep2, Menueltolasx, Menueltolasy+120 );
			blt8( Buffsima, rarakkep3, Menueltolasx, Menueltolasy+240 );
			blt8( Buffsima, rarakkep4, Menueltolasx, Menueltolasy+360 );

			blt8( Buffgolyo, rarakkep1, Menueltolasx, Menueltolasy );
			blt8( Buffgolyo, rarakkep2, Menueltolasx, Menueltolasy+120 );
			blt8( Buffgolyo, rarakkep3, Menueltolasx, Menueltolasy+240 );
			blt8( Buffgolyo, rarakkep4, Menueltolasx, Menueltolasy+360 );
		}
		else {
			#ifndef ELMA_CLI // Terminalban szovegkent irjuk ki oket
			for( int i = 0; i < elemszam; i++ ) {
				Pmenuabc->write( Buffsima, sorok[i].x+Menueltolasx, sorok[i].y+Menueltolasy,
									sorok[i].text );
				Pmenuabc->write( Buffgolyo, sorok[i].x+Menueltolasx, sorok[i].y+Menueltolasy,
									sorok[i].text );
			}
			#endif
		}

		// Ha kell logokep, azt itt rarajzoljuk:
		/*if( logokep ) {
			static int elsologo = 1;
			if( !elsologo )
				hiba( "8989654" );
			elsologo = 0;

			pic8* ppiclogo = new pic8( "intro.pcx" );
			spriteosit( ppiclogo );
			blt8( Buffsima, ppiclogo );
			blt8( Buffgolyo, ppiclogo );
			delete ppiclogo; ppiclogo = NULL;
		} */
	}

	double ujido = mv_stopperido();
	if( Kezdoanimjon ) {
		Pmenupal->set();
		while( 1 ) {
			/*if( mk_kbhit() ) {
				int c = mk_getextchar();
				if( c == MK_ESC )
					return;
			}*/
			if( !kirajzolanim( ujido ) ) {
				Kezdoanimjon = 0;
				Regiido = ujido;
				return;
			}

			ujido = mv_stopperido();
			Elsostabilido = ujido;
			Kezdoanimjon = 0;
		}
	}

	double dt;
	if( ujido < Elsostabilido + 10.0 ) 
		dt = 0.0000000000001;
	else {
		dt = ujido-Regiido;
		Elsostabilido = -100.0;
	}

	Regiido = ujido;
	if( dt < 0.0 )
		dt = 0.001;

	dt *= 3.6;
	if( dt > 100.0 )
		dt = 100.0;

	const uint32_t ido0 = gv_clock();
	leptetgolyo( dt ); // 12.0 volt regebben
	const uint32_t ido1 = gv_clock();
	gv_prof[GV_PROF_MENU_STEP] += ido1 - ido0;

	// The picture is drawn straight into the front buffer. If it still
	// holds the previous menu frame (nothing else was shown since), only the
	// rectangles of the previous balls (their two small balls are inside) and
	// helmet are restored from the background:
	unsigned char** sorok_front = lockfrontbuffer();
	pic8 front( Menuxsize, Menuysize, sorok_front );
	int reszleges = Elozoervenyes && Elozosorozat == gv_menu_serial();
	if( reszleges ) {
		for( int i = 0; i < MAXTERULET; i++ ) {
			golyoterulet* t = &Elozoteruletek[i];
			if( t->x1 <= t->x2 )
				blt8( &front, Buffsima, t->x1, t->y1, t->x1, t->y1, t->x2, t->y2 );
		}
	}
	else
		blt8( &front, Buffsima );
	golyoterulet uj[MAXTERULET];
	for( int i = 0; i < MAXTERULET; i++ ) {
		uj[i].x1 = uj[i].y1 = 1;
		uj[i].x2 = uj[i].y2 = 0;
	}

	for( int i = 0; i < Ngolyok && i < MAXTERULET-1; i++ ) {
		if( nemkellgolyo || !State->animatedmenus )
			break;

		if( Nincsfal && (Golyok[i].rmostani.x < -500.0 || Golyok[i].rmostani.x > 1500.0 ||
						 Golyok[i].rmostani.y < -500.0 || Golyok[i].rmostani.y > 1500.0) )
			continue;
		const int xo8 = int( Golyok[i].rmostani.x*256.0 );
		const int yo8 = int( Golyok[i].rmostani.y*256.0 );
		const int r8 = int( Golyok[i].sug*256.0 );
		uj[i] = kirajzgolyo_fx( xo8, yo8, r8, Buffgolyo, &front );

		// The two small ones at half the radius from the middle:
		int sn, cs;
		szinkoszinusz( Golyok[i].alfamostani, &sn, &cs );
		const int dx8 = (r8/2*cs) >> 14, dy8 = (r8/2*sn) >> 14;
		const int r8kicsi = int( Golyok[i].sug*0.25*256.0 );
		egyesit( &uj[i], kirajzgolyo_fx( xo8+dx8, yo8+dy8, r8kicsi, Buffsima, &front ) );
		egyesit( &uj[i], kirajzgolyo_fx( xo8-dx8, yo8-dy8, r8kicsi, Buffsima, &front ) );
	}
	if( !nemkellgolyo ) {
		pic8* sisakframe = NULL;
		if( State->animatedmenus )
			sisakframe = Psisak->getframe( ujido*0.0024 );
		else
			sisakframe = Psisak->getframebyindex( 25 );

		// (-100 is off screen, it stays there too:)
		int x = sisakx+Menueltolasx-20, y = sisaky+Menueltolasy-7;
		if( sisakx == -100 && sisaky == -100 )
			x = sisakx-20, y = sisaky-7;
		blt8( &front, sisakframe, x, y );
		golyoterulet t = { x, y, x+sisakframe->getxsize()-1, y+sisakframe->getysize()-1 };
		uj[MAXTERULET-1] = t;
	}

	// What changed: the old and the new place of each, as one rectangle if
	// they overlap.
	for( int i = 0; i < MAXTERULET; i++ ) {
		vagas( &uj[i] );
		if( reszleges ) {
			golyoterulet* r = &Elozoteruletek[i];
			const int regi = r->x1 <= r->x2, ujvan = uj[i].x1 <= uj[i].x2;
			if( regi && ujvan && r->x1 <= uj[i].x2 && uj[i].x1 <= r->x2 && r->y1 <= uj[i].y2 &&
				uj[i].y1 <= r->y2 ) {
				golyoterulet e = *r;
				egyesit( &e, uj[i] );
				gv_menu_dirty( e.x1, e.y1, e.x2, e.y2 );
			}
			else {
				if( regi )
					gv_menu_dirty( r->x1, r->y1, r->x2, r->y2 );
				if( ujvan )
					gv_menu_dirty( uj[i].x1, uj[i].y1, uj[i].x2, uj[i].y2 );
			}
		}
		Elozoteruletek[i] = uj[i];
	}
	if( reszleges )
		gv_menu_partial();
	gv_prof[GV_PROF_MENU_DRAW] += gv_clock() - ido1;
	unlockfrontbuffer();
	Elozoervenyes = 1;
	Elozosorozat = gv_menu_serial();

	// The intro animation was the last user of the temporary picture:
	if( Tmpbuffer && !Kezdoanimjon ) {
		delete Tmpbuffer;
		Tmpbuffer = NULL;
	}
}

static int Elsokiranim = 1;
// Teljes olvassa be es elso kiirloading szabaditja fel:
extern pic8* Pintro = NULL;

static double Animkezdete = 0.0;

// Hamis ha animnak mar vege:
int szoveglista::kirajzolanim( double ido ) {
	int i;
	if( Elsokiranim ) {
		leptetgolyo( 0.000000001 );
		Elsokiranim = 0;
		Animkezdete = ido;

		// Berajzoljuk hatterkepeket:
		int y = -47;
		int paros = 0;
		int kezdox = 0;
		while( y < Menuysize ) {
			int x = kezdox;
			kezdox += 110;
			while( x > 0 )
				x -= Kisnevsima->getxsize();
			paros = !paros;
			while( x < Menuxsize ) {
				blt8( Buffsima, Kisnevsima, x, y );
				blt8( Buffgolyo, Kisnevgolyo, x, y );
				x += Kisnevsima->getxsize();
			}
			y += Kisnevsima->getysize();
		}
		// Most egyszer kirakunk minden elemet kepre hogy
		// ne akadjon meg elso lejatszas kozben:
		Tmpbuffer->fillbox( Introhatter );
		blt8( Tmpbuffer, Buffsima, 0, 0 );

		Scrolly1 = 0;
		double yeltolas = 0.0;
		for( i = 0; i < Ngolyok; i++ ) {
			if( !State->animatedmenus )
				break;

			Golyok[i].rmostani.y += yeltolas;

			kirajzgolyo( Golyok[i].rmostani, Golyok[i].sug, Buffgolyo, Tmpbuffer );

			vekt2 diff( Golyok[i].sug*0.5*cos( Golyok[i].alfamostani ),
						Golyok[i].sug*0.5*sin( Golyok[i].alfamostani ) );
			kirajzgolyo( Golyok[i].rmostani + diff,
						Golyok[i].sug*0.25, Buffsima, Tmpbuffer );
			kirajzgolyo( Golyok[i].rmostani - diff,
						Golyok[i].sug*0.25, Buffsima, Tmpbuffer );

			Golyok[i].rmostani.y -= yeltolas;
		}

		// Rairjuk szovegeket:
		for( i = 0; i < elemszam; i++ )
			Pmenuabc->write( Tmpbuffer, sorok[i].x+Menueltolasx, sorok[i].y+Menueltolasy,
								sorok[i].text );

		pic8* sisakframe = NULL;
		sisakframe = Psisak->getframebyindex( 25 );
		blt8( Tmpbuffer, sisakframe, sisakx+Menueltolasx-20, sisaky+Menueltolasy-7 );
		blt8( Tmpbuffer, Pintro, Menueltolasx, Menueltolasy );
		// Idaig tartott minden elem kirakasa egyszer
	}

	ido -= Animkezdete;

	// Travel the full menu height in the original 480-row duration, even
	// when the menu fills a high-resolution display.
	int frame = ido*2.3*(Menuysize/480.0);
	//int framex = ido*2.3*(640.0/480.0);

	/*if( frame < 480 ) {
		// Kirakjuk legordulo hatteret:
		Tmpbuffer->fillbox( Introhatter );
		blt8( Tmpbuffer, Buffsima, 0, frame-480 );
		blt8( Tmpbuffer, Pintro );
		bltfront( Tmpbuffer );
		return 1;
	}

	frame -= 480;*/

	// The menu image rises from below (from Menuysize height), the intro
	// image moves down off it:
	if( frame >= Menuysize ) {
		Scrolly1 = 0;
		return 0;
	}

	// Most mar masodik animaciot rajzoljuk:
	//blt8( Tmpbuffer, Buffsima );

	Tmpbuffer->fillbox( Introhatter );
	blt8( Tmpbuffer, Buffsima, 0, Menuysize-frame );

	Scrolly1 = Menuysize-frame;
	double yeltolas = frame-double(Menuysize);
	for( int i = 0; i < Ngolyok; i++ ) {
		if( !State->animatedmenus )
			break;

		Golyok[i].rmostani.y += yeltolas;

		kirajzgolyo( Golyok[i].rmostani, Golyok[i].sug, Buffgolyo, Tmpbuffer );

		vekt2 diff( Golyok[i].sug*0.5*cos( Golyok[i].alfamostani ),
					Golyok[i].sug*0.5*sin( Golyok[i].alfamostani ) );
		kirajzgolyo( Golyok[i].rmostani + diff,
					Golyok[i].sug*0.25, Buffsima, Tmpbuffer );
		kirajzgolyo( Golyok[i].rmostani - diff,
					Golyok[i].sug*0.25, Buffsima, Tmpbuffer );

		Golyok[i].rmostani.y -= yeltolas;
	}

	// Rairjuk szovegeket:
	for( i = 0; i < elemszam; i++ )
		Pmenuabc->write( Tmpbuffer, sorok[i].x+Menueltolasx, sorok[i].y+Menueltolasy+frame-Menuysize,
							sorok[i].text );

	// Rarakjuk sisakot:
	pic8* sisakframe = NULL;
	if( State->animatedmenus )
		sisakframe = Psisak->getframe( ido*0.0024 );
	else
		sisakframe = Psisak->getframebyindex( 25 );

	blt8( Tmpbuffer, sisakframe, sisakx+Menueltolasx-20, sisaky+Menueltolasy-7-(Menuysize-1)+frame );

	blt8( Tmpbuffer, Pintro, Menueltolasx, Menueltolasy+frame );
	//blt8( Tmpbuffer, Pintro, framex, 0, 0, 0, 639, 206 );
	//blt8( Tmpbuffer, Pintro, -framex, 206, 0, 206, 639, 479 );
	bltfront( Tmpbuffer );
	return 1;
}

#define MAXHIBASORHOSSZ (34)
typedef char hibasor[MAXHIBASORHOSSZ+4];
#define MAXHIBASOR (10)
static hibasor Hibasortomb[MAXHIBASOR];

void grafikushiba( char* text1, char* text2, char* text3 ) {
	// Kirajzoljuk hatteret Buffsima-ba:
	menumeretbeallit();
	int y = 0;
	int paros = 0;
	while( y < Menuysize ) {
		int x = 0;
		if( paros )
			x -= Kisnevsima->getxsize()/2;
		paros = !paros;
		while( x < Menuxsize ) {
			blt8( Buffsima, Kisnevsima, x, y );
			x += Kisnevsima->getxsize();
		}
		y += Kisnevsima->getysize();
	}

	int sorszam = 0;
	int i;
	for( i = 0; i < 3; i++ ) {
		char* text = text1;
		if( i == 1 )
			text = text2;
		if( i == 2 )
			text = text3;
		if( !text )
			break;

		while( 1 ) {
			if( sorszam >= MAXHIBASOR )
				break;
			if( strlen( text ) <= MAXHIBASORHOSSZ ) {
				// Siman belefer:
				strcpy( Hibasortomb[sorszam], text );
				sorszam++;
				break;
			}
			// Tul hosszu sor, le kell vagni belole:
			int j = MAXHIBASORHOSSZ;
			while( j > 0 ) {
				if( text[j] == ' ' )
					break;

				j--;
			}
			if( j <= 0 ) {
				// Nem talalt szovegben space-t:
				char c = text[MAXHIBASORHOSSZ];
				text[MAXHIBASORHOSSZ] = 0;	
				strcpy( Hibasortomb[sorszam], text );
				sorszam++;
				text[MAXHIBASORHOSSZ] = c;
				text += MAXHIBASORHOSSZ;	
			}
			else {
				char c = text[j];
				text[j] = 0;	
				strcpy( Hibasortomb[sorszam], text );
				sorszam++;
				text[j] = c;
				text += j;
				while( text[j] == ' ' )
					text++;
			}
		}
	}

	// Rairjuk szovegeket:
	for( i = 0; i < sorszam; i++ ) {
		int y = Menuysize/2-20-sorszam*(40/2)+i*40;
		Pmenuabc->writekozep( Buffsima, Menuxsize/2, y, Hibasortomb[i] );
	}
	// Kirakjuk:
	bltfront( Buffsima );
	if( Pmenupal )
		Pmenupal->set();
}

void menuproba( void ) {
	szoveglista szl;
	szl.addszoveg( "ABCDEFGH", 100, 100 );
	szl.addszoveg( "abcdefgh", 100, 200 );
	Pmenupal->set();
	while( 1 ) {
		if( mk_kbhit() )
			hiba( "Vege!" );
		szl.kirajzol();
	}
}




/*void szoveglista::kirajzol( int nemkellgolyo ) {
	if( !ervenyes ) {
		// Ujrarajzoljuk hatterkepeket:
		ervenyes = 1;
		int y = 0;
		int paros = 0;
		while( y < 480 ) {
			int x = 0;
			if( paros )
				x -= Kisnevsima->getxsize()/2;
			paros = !paros;
			while( x < 640 ) {
				blt8( Buffsima, Kisnevsima, x, y );
				blt8( Buffgolyo, Kisnevgolyo, x, y );
				x += Kisnevsima->getxsize();
			}
			y += Kisnevsima->getysize();
		}
		// Rairjuk szovegeket:
		for( int i = 0; i < elemszam; i++ ) {
			Pmenuabc->write( Buffsima, sorok[i].x, sorok[i].y,
								sorok[i].text );
			Pmenuabc->write( Buffgolyo, sorok[i].x, sorok[i].y,
								sorok[i].text );
		}
	}

	double ujido = mv_stopperido();
	double dt = ujido-Regiido;
	Regiido = ujido;
	if( dt < 0.0 )
		dt = 0.001;

	dt *= 3.6;
	if( dt > 100.0 )
		dt = 100.0;

	leptetgolyo( dt ); // 12.0 volt regebben

	// Kirakjuk hatteret:
	if( !Tmpbuffer ) // Ideiglenes
		Tmpbuffer = new pic8( 640, 480 );

	blt8( Tmpbuffer, Buffsima );

	for( int i = 0; i < Ngolyok; i++ ) {
		if( nemkellgolyo || !State->animatedmenus )
			break;

		kirajzgolyo( Golyok[i].rmostani, Golyok[i].sug, Buffgolyo, Tmpbuffer );

		vekt2 diff( Golyok[i].sug*0.5*cos( Golyok[i].alfamostani ),
					Golyok[i].sug*0.5*sin( Golyok[i].alfamostani ) );
		kirajzgolyo( Golyok[i].rmostani + diff,
					Golyok[i].sug*0.25, Buffsima, Tmpbuffer );
		kirajzgolyo( Golyok[i].rmostani - diff,
					Golyok[i].sug*0.25, Buffsima, Tmpbuffer );
	}
	if( !nemkellgolyo ) {
		pic8* sisakframe = NULL;
		if( State->animatedmenus )
			sisakframe = Psisak->getframe( ujido*0.0024 );
		else
			sisakframe = Psisak->getframebyindex( 25 );

		blt8( Tmpbuffer, sisakframe, sisakx-20, sisaky-7 );
	}

	bltfront( Tmpbuffer );
} */
