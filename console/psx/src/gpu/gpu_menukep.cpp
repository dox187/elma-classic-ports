// The menus' drawing (MENUKEP.CPP of the core) for the PlayStation version.
// The same pictures as the original, but a menu frame only redraws what
// moved: the rectangles of the balls and the helmet of the previous frame are
// restored from the background, the new ones drawn straight into the front
// buffer, and only those rectangles are sent to VRAM (gv_menu_dirty). The
// rows of a ball are computed with integers instead of a sqrt per row in
// software floating point.
//
// Memory: the original kept the two menu backgrounds as 640x480 pictures
// (Buffsima: the plain tiles with the texts on them, Buffgolyo: the tiles
// seen in the balls with the same texts) and drew every frame into a third
// one (Tmpbuffer), 900 KB in all. Here any part of either background is
// made again when it is needed, from the two tile pictures and the text
// list (hatterreszlet), and everything is drawn straight into the core's
// picture. Buffsima is that picture itself, so the dialogs of the core,
// which draw onto Buffsima, draw onto the current menu picture; Buffgolyo
// does not exist.
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
	// The core's picture (gv_menu_rows), as Buffsima:
	Buffsima = new pic8( GV_MENU_W, GV_MENU_H, gv_menu_rows() );
	Buffgolyo = NULL;
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

// The tiles of the backgrounds (90 KB) are only needed by the menus: they
// are given back while an LGR is read (gv_menu_images_free) and read again
// when a menu is drawn next.
static void tilebetolt( void ) {
	if( Kisnevsima )
		return;
	// After a game of a big level the room may have to be made by the
	// level's pictures for the GPU (made again for the next game):
	// Else the picture is made again after them (it is in small pieces).
	for( int lepes = 0; lepes < 2; lepes++ ) {
		// (Room for a tile and for reading its file, 75 KB, at once.)
		void* proba1 = malloc( 80*1024 );
		void* proba2 = malloc( 400*114 + 4096 );
		free( proba1 );
		free( proba2 );
		if( proba1 && proba2 )
			break;
		if( !gv_level_release() || lepes )
			gv_menu_picture_free();
	}
	Kisnevsima = new pic8( "szoveg1.pcx" );
	Kisnevgolyo = new pic8( "szoveg2.pcx" );
}

void gv_menu_images_free( void ) {
	delete Kisnevsima;
	delete Kisnevgolyo;
	Kisnevsima = Kisnevgolyo = NULL;
}

void initmenukep2( void ) {
	if( Pmenupal )
		hiba( "initmenukep2-ben Pmenupal!" );
	pcxtopal( "intro.pcx", &Pmenupal ); // O new-ik egy ddpal-t
	pcxtopal( "intro.pcx", Menupaltomb );
	menumeretbeallit();
}

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
	// (The picture is always 640x480 here, dd_menumeret.)
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
// The rows above Scrolly1 in a ball, as the original's Zoldsor:
static const unsigned char Zoldszin = 248;

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

// --- The two backgrounds, made from their parts ------------------------------

enum { HATTER_SIMA = 0, HATTER_GOLYO = 1 };

// What the backgrounds show: the texts of the list being drawn, with their
// widths (from its last full redraw), or its four pictures; Hszoveg 0: the
// tiles only (the intro animation).
static egyszovsor* Hsorok = NULL;
static int Hszam = 0;
static int Hszel[MAXSZOVEGSOR];
static pic8* Hkepek[4] = { NULL, NULL, NULL, NULL };
static int Hszoveg = 1;
static szoveglista* Hlista = NULL;

// The rows of the menu font relative to the y of a text, of all letters:
static int Betufelso = 0, Betualso = 0, Betusorok = 0;

static void hatterszelessegek( void ) {
	if( !Betusorok ) {
		Betusorok = 1;
		Betufelso = 1000;
		Betualso = -1000;
		for( int c = 0; c < 256; c++ ) {
			pic8* betu = Pmenuabc->ppsprite[c];
			if( !betu )
				continue;
			const int y1 = Pmenuabc->ytomb[c], y2 = y1 + betu->getysize();
			if( y1 < Betufelso )
				Betufelso = y1;
			if( y2 > Betualso )
				Betualso = y2;
		}
		if( Betufelso > Betualso )
			Betufelso = Betualso = 0;
	}
	for( int i = 0; i < Hszam && i < MAXSZOVEGSOR; i++ )
		Hszel[i] = Pmenuabc->len( Hsorok[i].text );
}

// Whether text i of the list may have pixels in the rectangle (a pixel of
// margin):
static int szovegbenne( int i, int rx, int ry, int w, int h ) {
	const int x = Hsorok[i].x + Menueltolasx, y = Hsorok[i].y + Menueltolasy;
	return y + Betualso >= ry && y + Betufelso <= ry + h &&
		   x + Hszel[i] >= rx && x - 1 <= rx + w;
}

// Whether anything but tiles is in the rectangle of the backgrounds:
static int vanszoveg( int rx, int ry, int w, int h ) {
	if( !Hszoveg )
		return 0;
	if( Hkepek[3] )
		return 1;
	for( int i = 0; i < Hszam && i < MAXSZOVEGSOR; i++ )
		if( szovegbenne( i, rx, ry, w, h ) )
			return 1;
	return 0;
}

// Pmenuabc->write( nezet, x, y, text ) (ABC8.CPP), but only the letters
// with pixels in the view (w x h) are drawn: clipping a letter costs as
// much as drawing it.
static void szovegiras( pic8* nezet, int x, int y, const char* text, int w, int h ) {
	for( ; *text; text++ ) {
		const int index = (unsigned char)*text;
		if( index == ' ' ) {
			x += 10; // Spacehossz_menu
			continue;
		}
		pic8* betu = Pmenuabc->ppsprite[index];
		if( !betu )
			continue;
		const int by = y + Pmenuabc->ytomb[index];
		if( x < w && x + betu->getxsize() > 0 && by < h && by + betu->getysize() > 0 )
			blt8( nezet, betu, x, by );
		x += Pmenuabc->tav + betu->getxsize();
	}
}

// Makes the part (rx, ry), w x h of a background (as the original drew it
// into Buffsima or Buffgolyo) into the rows sorok: sorok[j] is row ry+j from
// column rx. The rows of tiles start at y = -47, each 110 pixels further
// right than the one above; on them the four pictures or (szoveggel) the
// texts of the menu.
static void hatterreszlet( int golyos, int szoveggel, unsigned char** sorok, int rx, int ry,
						   int w, int h ) {
	if( w <= 0 || h <= 0 )
		return;
	pic8* tile = golyos ? Kisnevgolyo : Kisnevsima;
	const int tw = Kisnevsima->getxsize(), th = Kisnevsima->getysize();
	for( int j = 0; j < h; j++ ) {
		const int y = ry + j + 47;
		const int sor = y / th;
		const unsigned char* forras = tile->getptr( y - sor*th );
		int u = (rx - 110*sor) % tw;
		if( u < 0 )
			u += tw;
		unsigned char* cel = sorok[j];
		int n = w;
		while( n > 0 ) {
			int db = tw - u;
			if( db > n )
				db = n;
			memcpy( cel, forras + u, db );
			cel += db;
			n -= db;
			u = 0;
		}
	}
	if( !szoveggel || !Hszoveg )
		return;
	pic8 nezet( w, h, sorok );
	if( Hkepek[3] ) {
		for( int k = 0; k < 4; k++ )
			blt8( &nezet, Hkepek[k], Menueltolasx-rx, Menueltolasy+120*k-ry );
		return;
	}
	#ifndef ELMA_CLI // Terminalban szovegkent irjuk ki oket
	for( int i = 0; i < Hszam && i < MAXSZOVEGSOR; i++ )
		if( szovegbenne( i, rx, ry, w, h ) )
			szovegiras( &nezet, Hsorok[i].x+Menueltolasx-rx, Hsorok[i].y+Menueltolasy-ry,
						Hsorok[i].text, w, h );
	#endif
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

// The background of a ball with texts in it is made here first:
static unsigned char* Munka = NULL;
static int Munkameret = 0;

// Draws a ball of a background (HATTER_SIMA, HATTER_GOLYO) into cel.
// Fixed point with 8 fraction bits; the middle row is the one nearest to
// the centre (the original's rows are the same but for a rounding at the
// ends).
static golyoterulet kirajzgolyo_fx( int xo8, int yo8, int r8, int golyos, pic8* cel ) {
	golyoterulet ter = { 1, 1, 0, 0 };
	const golyosorok* t = sortabla( r8 );
	const int yc = (yo8 + 128) >> 8;
	// The rows (clipped) and their rectangle:
	static int16_t sorx1[2*160], sorx2[2*160];
	const int k0 = -(t->sorszam-1);
	for( int k = k0; k < t->sorszam; k++ ) {
		const int y = yc + k;
		sorx1[k-k0] = 1;
		sorx2[k-k0] = 0;
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
		sorx1[k-k0] = (int16_t)x1;
		sorx2[k-k0] = (int16_t)x2;
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
	if( ter.x1 > ter.x2 )
		return ter;

	// Only tiles under it: its rows straight from them; else its rectangle
	// of the background is made first.
	const int w = ter.x2-ter.x1+1, h = ter.y2-ter.y1+1;
	static unsigned char* munkasorok[2*160];
	const int szoveg = vanszoveg( ter.x1, ter.y1, w, h );
	if( szoveg ) {
		if( Munkameret < w*h ) {
			delete[] Munka;
			Munkameret = w*h;
			Munka = new unsigned char[Munkameret];
		}
		for( int j = 0; j < h; j++ )
			munkasorok[j] = Munka + j*w;
		hatterreszlet( golyos, 1, munkasorok, ter.x1, ter.y1, w, h );
	}
	for( int k = k0; k < t->sorszam; k++ ) {
		const int x1 = sorx1[k-k0], x2 = sorx2[k-k0];
		if( x1 > x2 )
			continue;
		const int y = yc + k;
		unsigned char* dest = cel->getptr( y ) + x1;
		if( y < Scrolly1 )
			memset( dest, golyos ? Zoldszin : Introhatter, x2-x1+1 );
		else if( szoveg )
			memcpy( dest, munkasorok[y-ter.y1] + (x1-ter.x1), x2-x1+1 );
		else
			hatterreszlet( golyos, 0, &dest, x1, y, x2-x1+1, 1 );
	}
	return ter;
}

static golyoterulet kirajzgolyo( vekt2 g, double r, int golyos, pic8* cel ) {
	if( Nincsfal ) {
		if( g.x < -500.0 || g.x > 1500.0 ||
			g.y < -500.0 || g.y > 1500.0 ) {
			golyoterulet ter = { 1, 1, 0, 0 };
			return ter;
		}
	}
	return kirajzgolyo_fx( int( g.x*256.0 ), int( g.y*256.0 ), int( r*256.0 ), golyos, cel );
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

// --- A menu frame by what changed --------------------------------------------
//
// The balls are windows onto the ball background, the small balls onto the
// plain one, both fixed on the screen: a pixel of the picture only changes
// if the background it shows changes (a ball moved over it or away), or the
// helmet was there. So a frame only draws, row by row, the pieces whose
// background differs from the previous frame's (kepkeszit), from the
// backgrounds' parts (irsor).

// A circle of a frame: its background and, for each of its rows y1..y2 on
// the picture, the columns x1..x2 drawn (x1 > x2: none), as kirajzgolyo_fx
// draws them.
struct golyokor {
	int golyos;
	int golyo;     // the ball (index of Golyok) it belongs to
	int keret;     // the frame (Mostani when it was made)
	int sorrend;   // drawing order in its frame
	int bx1, bx2;  // its columns
	int cx, cy, r; // centre and radius (pixels, rounded up)
	int y1, y2;
	int16_t* x1;
	int16_t* x2;
};
const int MAXKOR = 3*(MAXTERULET-1);
const int MAXKORSOR = 1280;
// Two frames in turn: this frame's circles (Korok[Mostani]) and the
// previous frame's (the other ones):
static golyokor Korok[2][MAXKOR];
static int Korszam[2] = { 0, 0 };
static int16_t Korsorok[2][2*MAXKORSOR];
static int Korsorszam[2] = { 0, 0 };
static int Mostani = 0;
// The helmet's rectangle on the previous frame (x1 > x2: none):
static golyoterulet Regisisak = { 1, 1, 0, 0 };

// This frame's circles start.
static void ujkorok( void ) {
	Mostani = !Mostani;
	Korszam[Mostani] = 0;
	Korsorszam[Mostani] = 0;
}

// Adds a circle of this frame (as kirajzgolyo_fx draws it); returns its
// rectangle.
static golyoterulet ujkor( int xo8, int yo8, int r8, int golyos, int golyo ) {
	golyoterulet ter = { 1, 1, 0, 0 };
	if( Korszam[Mostani] == MAXKOR )
		return ter;
	const golyosorok* t = sortabla( r8 );
	const int s = t->sorszam;
	const int yc = (yo8 + 128) >> 8;
	int y1 = yc - (s-1), y2 = yc + (s-1);
	if( y1 < 0 )
		y1 = 0;
	if( y2 > Menuysize-1 )
		y2 = Menuysize-1;
	const int sorok = y2-y1+1;
	if( s <= 0 || sorok <= 0 || Korsorszam[Mostani] + sorok > MAXKORSOR )
		return ter;
	golyokor* k = &Korok[Mostani][Korszam[Mostani]++];
	k->golyos = golyos;
	k->golyo = golyo;
	k->cx = xo8 >> 8;
	k->cy = yc;
	k->r = (r8 >> 8) + 1;
	k->keret = Mostani;
	k->sorrend = Korszam[Mostani]-1;
	k->y1 = y1;
	k->y2 = y2;
	k->x1 = &Korsorok[Mostani][2*Korsorszam[Mostani]];
	k->x2 = k->x1 + sorok;
	Korsorszam[Mostani] += sorok;
	// Truncated toward zero, as the conversion of a double; the rectangle
	// from the widest row on the picture afterwards.
	const int xmax = Menuxsize-1;
	int16_t* o1 = k->x1;
	int16_t* o2 = k->x2;
	int ux1 = xmax+1, ux2 = -1, uy1 = -1, uy2 = -1;
	for( int y = y1; y <= y2; y++, o1++, o2++ ) {
		const int kk = y - yc;
		const int dx8 = t->dx[kk < 0 ? -kk : kk];
		const int a = xo8-dx8, b = xo8+dx8;
		int u = a >> 8, v = b >> 8;
		if( a < 0 && (a & 255) )
			u++;
		if( b < 0 && (b & 255) )
			v++;
		if( u < 0 )
			u = 0;
		if( v > xmax )
			v = xmax;
		if( u > xmax )
			u = xmax;
		if( v < 0 )
			v = 0;
		if( u >= v ) {
			*o1 = 1;
			*o2 = 0;
			continue;
		}
		*o1 = (int16_t)u;
		*o2 = (int16_t)v;
		if( uy1 < 0 )
			uy1 = y;
		uy2 = y;
		if( u < ux1 )
			ux1 = u;
		if( v > ux2 )
			ux2 = v;
	}
	if( uy1 >= 0 ) {
		ter.x1 = ux1;
		ter.x2 = ux2;
		ter.y1 = uy1;
		ter.y2 = uy2;
	}
	k->bx1 = ter.x1 <= ter.x2 ? ter.x1 : 0;
	k->bx2 = ter.x1 <= ter.x2 ? ter.x2 : -1;
	return ter;
}

// The texts on each row (an index list per row) and their letters (where,
// which, how big), made at a full redraw; Sorvonaltelt: too many, the
// general way is used.
const int MAXSORVONAL = 6000;
static int16_t Sorvonalkezd[GV_MENU_H+1];
static int16_t* Sorvonalak = NULL;
static int Sorvonalmeret = 0;
static int Sorvonaltelt = 1;
struct betuhely {
	int16_t x, y, w, h;   // its rectangle on the picture
	int16_t index;
};
static betuhely* Betuk = NULL;
static int Betukmeret = 0;
static int Betukezd[MAXSZOVEGSOR+1];
// The texts' pixels as runs (x1, x2) on each row, sorted: the same on both
// backgrounds, so they never change (but where the helmet was). Szovegfutas
// NULL: too many, the letters are always drawn.
const int MAXSZOVEGFUTAS = 16384;
static int16_t* Szovegfutas = NULL;
static int Szovegfutasmeret = 0;
static int Szovegfutaskezd[GV_MENU_H+1];
static int16_t Szovegfutasdb[GV_MENU_H];
// The columns of each row's text pixels (x1 > x2: none), all of the row
// when the texts are drawn the general way:
static int16_t Szovegx1[GV_MENU_H], Szovegx2[GV_MENU_H];

static void szovegxtorol( int mind ) {
	for( int y = 0; y < GV_MENU_H; y++ ) {
		Szovegx1[y] = (int16_t)(mind ? 0 : 32767);
		Szovegx2[y] = (int16_t)(mind ? GV_MENU_W-1 : -1);
	}
}
static uint16_t* Betusorkezd[256];

static void szovegfutasok( void ) {
	const int n = Hszam < MAXSZOVEGSOR ? Hszam : MAXSZOVEGSOR;
	int db[GV_MENU_H];
	memset( db, 0, sizeof( db ) );
	int osszes = 0;
	for( int pass = 0; pass < 2; pass++ ) {
		for( int i = 0; i < Betukezd[n]; i++ ) {
			const betuhely* b = &Betuk[i];
			pic8* betu = Pmenuabc->ppsprite[b->index];
			if( !Betusorkezd[b->index] )
				continue;
			for( int r = 0; r < b->h; r++ ) {
				const int y = b->y + r;
				if( y < 0 || y >= Menuysize )
					continue;
				const unsigned char* rle = betu->getsprite() + Betusorkezd[b->index][r];
				int sx = 0;
				while( sx < b->w ) {
					const int hossz = rle[1];
					if( rle[0] == 'K' && hossz > 0 ) {
						if( pass == 0 )
							db[y]++;
						else {
							int16_t* f = &Szovegfutas[2*(Szovegfutaskezd[y] + db[y]++)];
							f[0] = (int16_t)(b->x + sx);
							f[1] = (int16_t)(b->x + sx + hossz - 1);
						}
					}
					sx += hossz;
					rle += 2;
				}
			}
		}
		if( pass == 0 ) {
			for( int y = 0; y < Menuysize; y++ ) {
				Szovegfutaskezd[y] = osszes;
				osszes += db[y];
				db[y] = 0;
			}
			Szovegfutaskezd[Menuysize] = osszes;
			if( osszes > MAXSZOVEGFUTAS ) {
				szovegxtorol( 1 );
				delete[] Szovegfutas;
				Szovegfutas = NULL;
				Szovegfutasmeret = 0;
				return;
			}
			if( Szovegfutasmeret < osszes || !Szovegfutas ) {
				delete[] Szovegfutas;
				Szovegfutasmeret = osszes > 256 ? osszes : 256;
				Szovegfutas = new int16_t[2*Szovegfutasmeret];
			}
		}
	}
	// Each row sorted, overlapping or touching runs joined:
	for( int y = 0; y < Menuysize; y++ ) {
		int16_t* f = &Szovegfutas[2*Szovegfutaskezd[y]];
		const int k = Szovegfutaskezd[y+1] - Szovegfutaskezd[y];
		for( int i = 1; i < k; i++ ) {
			const int16_t a = f[2*i], b = f[2*i+1];
			int j = i;
			while( j > 0 && f[2*j-2] > a ) {
				f[2*j] = f[2*j-2];
				f[2*j+1] = f[2*j-1];
				j--;
			}
			f[2*j] = a;
			f[2*j+1] = b;
		}
		int m = 0;
		for( int i = 0; i < k; i++ ) {
			if( m && f[2*i] <= f[2*m-1]+1 ) {
				if( f[2*i+1] > f[2*m-1] )
					f[2*m-1] = f[2*i+1];
				continue;
			}
			f[2*m] = f[2*i];
			f[2*m+1] = f[2*i+1];
			m++;
		}
		Szovegfutasdb[y] = (int16_t)m;
		Szovegx1[y] = (int16_t)(m ? f[0] : 32767);
		Szovegx2[y] = (int16_t)(m ? f[2*m-1] : -1);
	}
}

static void sorvonalak( void ) {
	const int n = Hszam < MAXSZOVEGSOR ? Hszam : MAXSZOVEGSOR;
	// The letters, placed as abc8::write places them:
	int osszes = 0;
	for( int i = 0; i < n; i++ )
		osszes += strlen( Hsorok[i].text );
	if( Betukmeret < osszes ) {
		delete[] Betuk;
		Betukmeret = osszes;
		Betuk = new betuhely[Betukmeret];
	}
	int db = 0;
	for( int i = 0; i < n; i++ ) {
		Betukezd[i] = db;
		int x = Hsorok[i].x + Menueltolasx;
		const int y = Hsorok[i].y + Menueltolasy;
		for( const char* c = Hsorok[i].text; *c; c++ ) {
			const int index = (unsigned char)*c;
			if( index == ' ' ) {
				x += 10; // Spacehossz_menu
				continue;
			}
			pic8* betu = Pmenuabc->ppsprite[index];
			if( !betu )
				continue;
			betuhely* b = &Betuk[db++];
			b->x = (int16_t)x;
			b->y = (int16_t)(y + Pmenuabc->ytomb[index]);
			b->w = (int16_t)betu->getxsize();
			b->h = (int16_t)betu->getysize();
			b->index = (int16_t)index;
			x += Pmenuabc->tav + betu->getxsize();
		}
	}
	Betukezd[n] = db;

	// The rows of each text:
	int sordb[GV_MENU_H];
	memset( sordb, 0, sizeof( sordb ) );
	osszes = 0;
	for( int pass = 0; pass < 2; pass++ ) {
		for( int i = 0; i < n; i++ ) {
			const int y = Hsorok[i].y + Menueltolasy;
			int y1 = y + Betufelso, y2 = y + Betualso - 1;
			if( y1 < 0 )
				y1 = 0;
			if( y2 > Menuysize-1 )
				y2 = Menuysize-1;
			for( int sor = y1; sor <= y2; sor++ ) {
				if( pass == 0 )
					sordb[sor]++;
				else
					Sorvonalak[Sorvonalkezd[sor] + sordb[sor]++] = (int16_t)i;
			}
		}
		if( pass == 0 ) {
			for( int sor = 0; sor < Menuysize; sor++ ) {
				Sorvonalkezd[sor] = (int16_t)osszes;
				osszes += sordb[sor];
				sordb[sor] = 0;
			}
			Sorvonalkezd[Menuysize] = (int16_t)osszes;
			Sorvonaltelt = osszes > MAXSORVONAL;
			if( Sorvonaltelt )
				return;
			if( Sorvonalmeret < osszes || !Sorvonalak ) {
				delete[] Sorvonalak;
				Sorvonalmeret = osszes > 64 ? osszes : 64;
				Sorvonalak = new int16_t[Sorvonalmeret];
			}
		}
	}
}

// Where each row of each letter of the menu font begins in its sprite
// data, so a row of a letter is drawn without going through the rows above.
static uint16_t* Betusortomb = NULL;

static void betusorok( void ) {
	if( Betusortomb )
		return;
	int osszes = 0;
	for( int c = 0; c < 256; c++ )
		if( Pmenuabc->ppsprite[c] && Pmenuabc->ppsprite[c]->getsprite() )
			osszes += Pmenuabc->ppsprite[c]->getysize();
	Betusortomb = new uint16_t[osszes ? osszes : 1];
	uint16_t* p = Betusortomb;
	for( int c = 0; c < 256; c++ ) {
		pic8* betu = Pmenuabc->ppsprite[c];
		Betusorkezd[c] = NULL;
		if( !betu || !betu->getsprite() )
			continue;
		Betusorkezd[c] = p;
		const unsigned char* rle = betu->getsprite();
		unsigned i = 0;
		for( int y = 0; y < betu->getysize(); y++ ) {
			*p++ = (uint16_t)i;
			int x = 0;
			while( x < betu->getxsize() && i+1 < betu->getspritehossz() ) {
				x += rle[i+1];
				i += 2;
			}
		}
	}
}

// A row of the tiles of both backgrounds, and the tile column at x = 0:
struct sortile {
	const unsigned char* forras[2];
	int alap, tw;
};

// A copy of a few bytes: 4 at a time (unaligned loads and stores), then
// the rest.
struct __attribute__((packed)) negybajt {
	uint32_t v;
};
static inline void masol( unsigned char* cel, const unsigned char* forras, int n ) {
	if( n >= 32 ) {
		memcpy( cel, forras, n );
		return;
	}
	for( ; n >= 4; n -= 4, cel += 4, forras += 4 )
		((negybajt*)cel)->v = ((const negybajt*)forras)->v;
	while( n-- > 0 )
		*cel++ = *forras++;
}

// Columns x1..x2 of a row of tiles into sor (the picture's row).
static void tilesor( const unsigned char* forras, int alap, int tw, int x1, int x2, unsigned char* sor ) {
	int u = x1 + alap;
	while( u >= tw )
		u -= tw;
	unsigned char* cel = sor + x1;
	int n = x2-x1+1;
	while( n > 0 ) {
		int db = tw - u;
		if( db > n )
			db = n;
		masol( cel, forras + u, db );
		cel += db;
		n -= db;
		u = 0;
	}
}

// Row y of the background golyos, columns x1..x2, into sor (the picture's
// row): the tiles and on them the texts' letters (or the pictures). Not
// szoveggel: the texts' pixels are on the picture already, only the tiles
// between them are drawn.
static void irsor( int golyos, int y, int x1, int x2, unsigned char* sor, const sortile* st,
				   int szoveggel ) {
	const unsigned char* forras = st->forras[golyos];
	if( !szoveggel && Hszoveg && Szovegfutas && !Hkepek[3] ) {
		const int16_t* f = &Szovegfutas[2*Szovegfutaskezd[y]];
		const int16_t* fv = f + 2*Szovegfutasdb[y];
		int x = x1;
		for( ; f < fv && f[0] <= x2; f += 2 ) {
			if( f[1] < x )
				continue;
			if( f[0] > x )
				tilesor( forras, st->alap, st->tw, x, f[0]-1, sor );
			x = f[1]+1;
		}
		if( x <= x2 )
			tilesor( forras, st->alap, st->tw, x, x2, sor );
		return;
	}
	tilesor( forras, st->alap, st->tw, x1, x2, sor );
	if( !Hszoveg )
		return;
	if( Hkepek[3] || Sorvonaltelt ) {
		// (Rare: the general way.)
		unsigned char* reszlet = sor + x1;
		hatterreszlet( golyos, 1, &reszlet, x1, y, x2-x1+1, 1 );
		return;
	}
	for( int j = Sorvonalkezd[y]; j < Sorvonalkezd[y+1]; j++ ) {
		const int i = Sorvonalak[j];
		const betuhely* b = &Betuk[Betukezd[i]];
		const betuhely* bveg = &Betuk[Betukezd[i+1]];
		for( ; b < bveg && b->x <= x2; b++ ) {
			const int r = y - b->y;
			if( r < 0 || r >= b->h || b->x + b->w <= x1 )
				continue;
			// The drawn runs of the letter's row r:
			pic8* betu = Pmenuabc->ppsprite[b->index];
			const unsigned char* rle = betu->getsprite() + Betusorkezd[b->index][r];
			const unsigned char* px = betu->getptr( r ) - b->x;
			int sx = b->x;
			const int sveg = b->x + b->w;
			while( sx < sveg && sx <= x2 ) {
				const int db = rle[1];
				if( rle[0] == 'K' ) {
					int a = sx, v = sx + db - 1;
					if( a < x1 )
						a = x1;
					if( v > x2 )
						v = x2;
					if( a <= v )
						masol( sor + a, px + a, v-a+1 );
				}
				sx += db;
				rle += 2;
			}
		}
	}
}

// A row being drawn: its tiles of both backgrounds, the tile column at
// x = 0, the picture's row.
struct rajzsor {
	const unsigned char* forras[2];
	int alap, tw, y;
	unsigned char* sor;
};

// Columns a..b of the background l on the row: the tiles between the
// texts' pixels (they are on the picture already), or with szoveggel the
// tiles and the texts.
static void sorresz( const rajzsor* r, int l, int a, int b, int szoveggel ) {
	if( a > b )
		return;
	if( szoveggel || !Szovegfutas || !Hszoveg || Hkepek[3] ) {
		sortile st;
		st.forras[0] = r->forras[0];
		st.forras[1] = r->forras[1];
		st.alap = r->alap;
		st.tw = r->tw;
		irsor( l, r->y, a, b, r->sor, &st, szoveggel );
		return;
	}
	const unsigned char* forras = r->forras[l];
	const int16_t* f = &Szovegfutas[2*Szovegfutaskezd[r->y]];
	const int16_t* fv = f + 2*Szovegfutasdb[r->y];
	{
		// The first run not left of a:
		int lo = 0, hi = (int)(fv - f) / 2;
		while( lo < hi ) {
			const int mid = (lo + hi) >> 1;
			if( f[2*mid+1] < a )
				lo = mid+1;
			else
				hi = mid;
		}
		f += 2*lo;
	}
	while( 1 ) {
		// The next text run in a..b:
		int c = b+1;
		while( f < fv && f[1] < a )
			f += 2;
		if( f < fv && f[0] <= b )
			c = f[0];
		if( c > a ) {
			// Tiles a..c-1:
			int u = a + r->alap;
			while( u >= r->tw )
				u -= r->tw;
			unsigned char* cel = r->sor + a;
			int n = c - a;
			while( n > 0 ) {
				int db = r->tw - u;
				if( db > n )
					db = n;
				n -= db;
				masol( cel, forras + u, db );
				cel += db;
				u = 0;
			}
		}
		if( c > b )
			return;
		a = f[1]+1;
		f += 2;
		if( a > b )
			return;
	}
}

// The pieces of the circles on a row: columns, background, which frame,
// drawing order, ball.
struct sordarab {
	int16_t x1, x2;
	uint8_t l, regi;
	int16_t sorrend;
	int16_t golyo;
};

// The general way for pieces that overlap: their ends cut the columns
// into intervals; in each, the background is that of the last piece (in
// drawing order) over it, of each frame.
static void altalanos( const rajzsor* r, const sordarab* const* d, int n ) {
	int16_t vegek[4*MAXKOR+2];
	int nveg = 0;
	for( int i = 0; i < n; i++ )
		for( int v = 0; v < 2; v++ ) {
			const int16_t e = (int16_t)(v ? d[i]->x2+1 : d[i]->x1);
			int j = nveg++;
			while( j > 0 && vegek[j-1] > e ) {
				vegek[j] = vegek[j-1];
				j--;
			}
			vegek[j] = e;
		}
	int futx = 0, futveg = -1, futl = 0;
	for( int k = 0; k+1 < nveg; k++ ) {
		const int x = vegek[k], veg = vegek[k+1]-1;
		if( x > veg )
			continue;
		int ujl = HATTER_SIMA, regil = HATTER_SIMA, ujs = -1, regis = -1;
		for( int i = 0; i < n; i++ )
			if( d[i]->x1 <= x && x <= d[i]->x2 ) {
				if( d[i]->regi ) {
					if( d[i]->sorrend > regis )
						regis = d[i]->sorrend, regil = d[i]->l;
				}
				else if( d[i]->sorrend > ujs )
					ujs = d[i]->sorrend, ujl = d[i]->l;
			}
		if( ujl == regil )
			continue;
		if( futveg == x-1 && futl == ujl ) {
			futveg = veg;
			continue;
		}
		if( futveg >= futx )
			sorresz( r, futl, futx, futveg, 0 );
		futx = x;
		futveg = veg;
		futl = ujl;
	}
	if( futveg >= futx )
		sorresz( r, futl, futx, futveg, 0 );
}

// The tiles' row and the column phase at row y: forras[l] + alap + x is
// the tile pixel of column x while x + alap < tw.
struct tilesor_allapot {
	int trow, alap;
};
static inline void tilekezd( tilesor_allapot* t, int y, int tw, int th ) {
	t->trow = y + 47;
	const int tsor = t->trow / th;
	t->trow -= tsor*th;
	t->alap = (-110*tsor) % tw;
	if( t->alap < 0 )
		t->alap += tw;
}
static inline void tilelep( tilesor_allapot* t, int tw, int th ) {
	if( ++t->trow == th ) {
		t->trow = 0;
		t->alap -= 110;
		if( t->alap < 0 )
			t->alap += tw;
	}
}

// Columns a..b of background l on the row being made (r and tw in scope):
// at once where the piece is beside the row's text and does not cross the
// end of the tiles' period.
#define DARAB( l, a, b ) do { \
		const int sr_a = (a), sr_b = (b); \
		if( sr_a <= sr_b ) { \
			int sr_u = sr_a + r.alap; \
			if( sr_u >= tw ) \
				sr_u -= tw; \
			if( sr_u >= tw ) \
				sr_u -= tw; \
			if( (sr_b < Szovegx1[r.y] || sr_a > Szovegx2[r.y]) && sr_u + (sr_b - sr_a) < tw ) \
				masol( r.sor + sr_a, r.forras[l] + sr_u, sr_b - sr_a + 1 ); \
			else \
				sorresz( &r, (l), sr_a, sr_b, 0 ); \
		} \
	} while( 0 )


// The rows of a ball's big circles (see kepkeszit).
static void egygolyo_nagy( unsigned char** sorok, const golyokor* ob, const golyokor* ub, int tw, int th ) {
	int y1 = 1000, y2 = -1;
	if( ob ) {
		y1 = ob->y1;
		y2 = ob->y2;
	}
	if( ub ) {
		if( ub->y1 < y1 )
			y1 = ub->y1;
		if( ub->y2 > y2 )
			y2 = ub->y2;
	}
	if( y1 > y2 )
		return;
	tilesor_allapot t;
	tilekezd( &t, y1, tw, th );
	rajzsor r;
	r.tw = tw;
	unsigned char* const* tsima = Kisnevsima->sormuttomb;
	unsigned char* const* tgolyo = Kisnevgolyo->sormuttomb;
	for( int y = y1; y <= y2; y++, tilelep( &t, tw, th ) ) {
		int oa = 1, obb = 0, ua = 1, ubb = 0;
		if( ob && y >= ob->y1 && y <= ob->y2 ) {
			oa = ob->x1[y-ob->y1];
			obb = ob->x2[y-ob->y1];
		}
		if( ub && y >= ub->y1 && y <= ub->y2 ) {
			ua = ub->x1[y-ub->y1];
			ubb = ub->x2[y-ub->y1];
		}
		if( oa == ua && obb == ubb )
			continue;
		r.forras[HATTER_SIMA] = tsima[t.trow];
		r.forras[HATTER_GOLYO] = tgolyo[t.trow];
		r.alap = t.alap;
		r.y = y;
		r.sor = sorok[y];
		if( oa <= obb && ua <= ubb ) {
			if( obb < ua || ubb < oa ) {
				DARAB( HATTER_SIMA, oa, obb );
				DARAB( HATTER_GOLYO, ua, ubb );
			}
			else {
				if( ua < oa )
					DARAB( HATTER_GOLYO, ua, oa-1 );
				else
					DARAB( HATTER_SIMA, oa, ua-1 );
				if( ubb > obb )
					DARAB( HATTER_GOLYO, obb+1, ubb );
				else
					DARAB( HATTER_SIMA, ubb+1, obb );
			}
		}
		else if( oa <= obb )
			DARAB( HATTER_SIMA, oa, obb );
		else
			DARAB( HATTER_GOLYO, ua, ubb );
	}
}

// The rows of a ball's small circles: the old ones inside the new big
// circle (ub) back to the ball background, then the new ones.
static void egygolyo_kicsik( unsigned char** sorok, const golyokor* ub, const golyokor* const* os,
							 const golyokor* const* us, int tw, int th ) {
	const golyokor* k[4] = { os[0], os[1], us[0], us[1] };
	int y1 = 1000, y2 = -1;
	for( int i = 0; i < 4; i++ )
		if( k[i] ) {
			if( k[i]->y1 < y1 )
				y1 = k[i]->y1;
			if( k[i]->y2 > y2 )
				y2 = k[i]->y2;
		}
	if( y1 > y2 )
		return;
	tilesor_allapot t;
	tilekezd( &t, y1, tw, th );
	rajzsor r;
	r.tw = tw;
	unsigned char* const* tsima = Kisnevsima->sormuttomb;
	unsigned char* const* tgolyo = Kisnevgolyo->sormuttomb;
	for( int y = y1; y <= y2; y++, tilelep( &t, tw, th ) ) {
		r.forras[HATTER_SIMA] = tsima[t.trow];
		r.forras[HATTER_GOLYO] = tgolyo[t.trow];
		r.alap = t.alap;
		r.y = y;
		r.sor = sorok[y];
		int ua = 1, ubb = 0;
		if( ub && y >= ub->y1 && y <= ub->y2 ) {
			ua = ub->x1[y-ub->y1];
			ubb = ub->x2[y-ub->y1];
		}
		for( int i = 0; i < 4; i++ ) {
			const golyokor* kk = k[i];
			if( !kk || y < kk->y1 || y > kk->y2 )
				continue;
			int a = kk->x1[y-kk->y1], b = kk->x2[y-kk->y1];
			if( i < 2 ) {
				// (Outside the new big circle it is plain both ways.)
				if( a < ua )
					a = ua;
				if( b > ubb )
					b = ubb;
				DARAB( HATTER_GOLYO, a, b );
			}
			else
				DARAB( HATTER_SIMA, a, b );
		}
	}
}

// Whether a big circle of one ball meets one of the other (with a pixel to
// spare):
static int nagykorok_metszik( const golyokor* const* ka, int na, const golyokor* const* kb, int nb ) {
	for( int i = 0; i < na; i++ ) {
		if( ka[i]->golyos != HATTER_GOLYO )
			continue;
		for( int j = 0; j < nb; j++ ) {
			if( kb[j]->golyos != HATTER_GOLYO )
				continue;
			const int dx = ka[i]->cx - kb[j]->cx, dy = ka[i]->cy - kb[j]->cy;
			const int rr = ka[i]->r + kb[j]->r + 1;
			if( dx*dx + dy*dy <= rr*rr )
				return 1;
		}
	}
	return 0;
}

// The frame: the pieces whose background differs from the previous
// frame's are drawn again, ball by ball (or together for balls whose places
// overlap), and where the previous helmet was everything (with the texts);
// mindig: the whole picture (the previous frame is not on it).
static void kepkeszit( pic8* cel, int mindig ) {
	const int tw = Kisnevsima->getxsize(), th = Kisnevsima->getysize();
	rajzsor r;
	r.tw = tw;

	// The balls: their circles of both frames, rows, rectangle; balls whose
	// rectangles overlap form a group (csoport: its first ball).
	struct golyoadat {
		const golyokor* k[6];
		int nk, y1, y2, x1, x2, csoport;
	};
	golyoadat golyok[MAXTERULET];
	for( int g = 0; g < MAXTERULET; g++ ) {
		golyok[g].nk = 0;
		golyok[g].csoport = g;
	}
	for( int f = 0; f < 2; f++ ) {
		if( mindig && f == 0 )
			continue;
		const int keret = f ? Mostani : !Mostani;
		for( int i = 0; i < Korszam[keret]; i++ ) {
			const golyokor* k = &Korok[keret][i];
			golyoadat* g = &golyok[k->golyo];
			if( g->nk == 6 )
				continue;
			if( !g->nk ) {
				g->y1 = k->y1, g->y2 = k->y2, g->x1 = k->bx1, g->x2 = k->bx2;
			}
			else {
				if( k->y1 < g->y1 ) g->y1 = k->y1;
				if( k->y2 > g->y2 ) g->y2 = k->y2;
				if( k->bx1 < g->x1 ) g->x1 = k->bx1;
				if( k->bx2 > g->x2 ) g->x2 = k->bx2;
			}
			g->k[g->nk++] = k;
		}
	}
	// (Balls whose big circles of either frame meet; the small ones are
	// inside them.)
	int egyutt = 0;
	for( int a = 0; a < MAXTERULET; a++ )
		for( int b = a+1; b < MAXTERULET; b++ ) {
			const golyoadat *ga = &golyok[a], *gb = &golyok[b];
			if( !ga->nk || !gb->nk || ga->csoport == gb->csoport )
				continue;
			if( ga->x1 <= gb->x2 && gb->x1 <= ga->x2 && ga->y1 <= gb->y2 && gb->y1 <= ga->y2 &&
				nagykorok_metszik( ga->k, ga->nk, gb->k, gb->nk ) ) {
				egyutt = 1;
				const int c = gb->csoport;
				for( int g = 0; g < MAXTERULET; g++ )
					if( golyok[g].csoport == c )
						golyok[g].csoport = ga->csoport;
			}
		}

	unsigned char** sorok = cel->sormuttomb;
	for( int g = 0; g < MAXTERULET && !mindig; g++ ) {
		if( !golyok[g].nk || golyok[g].csoport != g )
			continue;
		int y1 = golyok[g].y1, y2 = golyok[g].y2, tobb = 0;
		for( int g2 = g+1; g2 < MAXTERULET && egyutt; g2++ )
			if( golyok[g2].nk && golyok[g2].csoport == g ) {
				tobb = 1;
				if( golyok[g2].y1 < y1 ) y1 = golyok[g2].y1;
				if( golyok[g2].y2 > y2 ) y2 = golyok[g2].y2;
			}
		// The tiles' row at y1, then row by row:
		int trow = y1 + 47, tsor = trow / th;
		trow -= tsor*th;
		int alap = (-110*tsor) % tw;
		if( alap < 0 )
			alap += tw;
		if( tobb ) {
			// Balls whose places overlap: the general way.
			const golyokor* k[6*MAXTERULET];
			int nk = 0;
			for( int g2 = g; g2 < MAXTERULET; g2++ )
				if( golyok[g2].nk && golyok[g2].csoport == g )
					for( int i = 0; i < golyok[g2].nk; i++ )
						k[nk++] = golyok[g2].k[i];
			for( int y = y1; y <= y2; y++ ) {
				r.forras[HATTER_SIMA] = Kisnevsima->getptr( trow );
				r.forras[HATTER_GOLYO] = Kisnevgolyo->getptr( trow );
				r.alap = alap;
				r.y = y;
				r.sor = sorok[y];
				if( ++trow == th ) {
					trow = 0;
					alap -= 110;
					if( alap < 0 )
						alap += tw;
				}
				sordarab d[6*MAXTERULET];
				const sordarab* dp[6*MAXTERULET];
				int nd = 0;
				for( int i = 0; i < nk; i++ ) {
					const golyokor* kk = k[i];
					if( y < kk->y1 || y > kk->y2 )
						continue;
					const int a = kk->x1[y-kk->y1], b = kk->x2[y-kk->y1];
					if( a > b )
						continue;
					sordarab* p = &d[nd];
					p->x1 = (int16_t)a;
					p->x2 = (int16_t)b;
					p->l = (uint8_t)kk->golyos;
					p->regi = kk->keret != Mostani;
					p->sorrend = (int16_t)kk->sorrend;
					dp[nd++] = p;
				}
				if( nd )
					altalanos( &r, dp, nd );
			}
			continue;
		}
		// One ball: its big circle of each frame (ob, ub) shows the ball
		// background, its small ones (inside it) the plain one. What was
		// only in the old big circle becomes plain, what is only in the new
		// one the ball background (egygolyo_nagy); then where an old small
		// circle was inside the new big one the ball background, and the
		// new small circles plain (egygolyo_kicsik).
		const golyokor *ob = NULL, *ub = NULL, *os[2] = { NULL, NULL }, *us[2] = { NULL, NULL };
		for( int i = 0; i < golyok[g].nk; i++ ) {
			const golyokor* kk = golyok[g].k[i];
			const int regi = kk->keret != Mostani;
			if( kk->golyos == HATTER_GOLYO ) {
				if( regi )
					ob = kk;
				else
					ub = kk;
			}
			else if( regi )
				os[os[0] ? 1 : 0] = kk;
			else
				us[us[0] ? 1 : 0] = kk;
		}
		egygolyo_nagy( sorok, ob, ub, tw, th );
		egygolyo_kicsik( sorok, ub, os, us, tw, th );
	}

	// The previous helmet's place (or everything), whole: the background
	// of the last new circle over each column.
	golyoterulet h = Regisisak;
	if( mindig ) {
		h.x1 = h.y1 = 0;
		h.x2 = Menuxsize-1;
		h.y2 = Menuysize-1;
	}
	vagas( &h );
	if( h.x1 > h.x2 )
		return;
	const golyokor* ujak = Korok[Mostani];
	const int nuj = Korszam[Mostani];
	for( int y = h.y1; y <= h.y2; y++ ) {
		const int ty = y + 47;
		const int tsor = ty / th;
		r.forras[HATTER_SIMA] = Kisnevsima->getptr( ty - tsor*th );
		r.forras[HATTER_GOLYO] = Kisnevgolyo->getptr( ty - tsor*th );
		r.alap = (-110*tsor) % tw;
		if( r.alap < 0 )
			r.alap += tw;
		r.y = y;
		r.sor = cel->getptr( y );
		int x = h.x1;
		while( x <= h.x2 ) {
			int l = HATTER_SIMA, veg = h.x2;
			for( int i = 0; i < nuj; i++ ) {
				const golyokor* kk = &ujak[i];
				if( y < kk->y1 || y > kk->y2 )
					continue;
				const int a = kk->x1[y-kk->y1], b = kk->x2[y-kk->y1];
				if( a > b )
					continue;
				if( a <= x && x <= b ) {
					l = kk->golyos;  // (the last one is on top)
					if( b < veg )
						veg = b;
				}
				else if( a > x && a-1 < veg )
					veg = a-1;
			}
			sorresz( &r, l, x, veg, 1 );
			x = veg+1;
		}
	}
}

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
	tilebetolt();
	// Kirakjuk hatteret:
	if( menumeretbeallit() )
		ervenyes = 0;
	if( Kezdoanimjon && !Pintro )
		Kezdoanimjon = 0;
	#ifdef ELMA_CLI
		// Terminalban nincs bevezeto animacio:
		Kezdoanimjon = 0;
	#endif

	// What the backgrounds show (the pictures instead of the texts, as
	// originally only if all four are given):
	Hsorok = sorok;
	Hszam = elemszam;
	Hszoveg = 1;
	Hkepek[0] = rarakkep4 ? rarakkep1 : NULL;
	Hkepek[1] = rarakkep4 ? rarakkep2 : NULL;
	Hkepek[2] = rarakkep4 ? rarakkep3 : NULL;
	Hkepek[3] = rarakkep4;
	// Another list than the last one drawn (whose texts may still be on the
	// picture) is drawn whole, too:
	if( (!ervenyes || Hlista != this) && !Kezdoanimjon ) {
		ervenyes = 1;
		Elozoervenyes = 0;
		Hlista = this;
		hatterszelessegek();
		betusorok();
		sorvonalak();
		szovegfutasok();
		if( Hkepek[3] || Sorvonaltelt )
			szovegxtorol( 1 );
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
				// The intro picture is not needed any more (originally
				// the first loading screen freed it):
				delete Pintro;
				Pintro = NULL;
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
	// holds the previous menu frame (nothing else was shown since), only
	// what changed since is drawn (kepkeszit):
	unsigned char** sorok_front = lockfrontbuffer();
	pic8 front( Menuxsize, Menuysize, sorok_front );
	int reszleges = Elozoervenyes && Elozosorozat == gv_menu_serial();
	golyoterulet uj[MAXTERULET];
	for( int i = 0; i < MAXTERULET; i++ ) {
		uj[i].x1 = uj[i].y1 = 1;
		uj[i].x2 = uj[i].y2 = 0;
	}

	ujkorok();
	for( int i = 0; i < Ngolyok && i < MAXTERULET-1; i++ ) {
		if( nemkellgolyo || !State->animatedmenus )
			break;

		if( Nincsfal && (Golyok[i].rmostani.x < -500.0 || Golyok[i].rmostani.x > 1500.0 ||
						 Golyok[i].rmostani.y < -500.0 || Golyok[i].rmostani.y > 1500.0) )
			continue;
		const int xo8 = int( Golyok[i].rmostani.x*256.0 );
		const int yo8 = int( Golyok[i].rmostani.y*256.0 );
		const int r8 = int( Golyok[i].sug*256.0 );
		uj[i] = ujkor( xo8, yo8, r8, HATTER_GOLYO, i );

		// The two small ones at half the radius from the middle:
		int sn, cs;
		szinkoszinusz( Golyok[i].alfamostani, &sn, &cs );
		const int dx8 = (r8/2*cs) >> 14, dy8 = (r8/2*sn) >> 14;
		const int r8kicsi = int( Golyok[i].sug*0.25*256.0 );
		egyesit( &uj[i], ujkor( xo8+dx8, yo8+dy8, r8kicsi, HATTER_SIMA, i ) );
		egyesit( &uj[i], ujkor( xo8-dx8, yo8-dy8, r8kicsi, HATTER_SIMA, i ) );
	}
	kepkeszit( &front, !reszleges );
	Regisisak.x1 = Regisisak.y1 = 1;
	Regisisak.x2 = Regisisak.y2 = 0;
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
		Regisisak = t;
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
		// (The original drew a frame here once, so that the first one of
		// the animation would not be late.)
	}

	ido -= Animkezdete;

	// Travel the full menu height in the original 480-row duration, even
	// when the menu fills a high-resolution display.
	int frame = ido*2.3*(Menuysize/480.0);

	// The menu image rises from below (from Menuysize height), the intro
	// image moves down off it:
	if( frame >= Menuysize ) {
		Scrolly1 = 0;
		return 0;
	}
	if( frame < 0 )
		frame = 0;

	// Straight into the front buffer; the backgrounds are the tiles only
	// here (the texts move on top):
	unsigned char** sorok_front = lockfrontbuffer();
	pic8 front( Menuxsize, Menuysize, sorok_front );
	Hszoveg = 0;

	Scrolly1 = Menuysize-frame;
	if( Scrolly1 > 0 )
		front.fillbox( 0, 0, Menuxsize-1, Scrolly1-1, Introhatter );
	// The plain background from its top row, Scrolly1 lower:
	hatterreszlet( HATTER_SIMA, 0, sorok_front + Scrolly1, 0, 0, Menuxsize, frame );

	double yeltolas = frame-double(Menuysize);
	for( int i = 0; i < Ngolyok; i++ ) {
		if( !State->animatedmenus )
			break;

		Golyok[i].rmostani.y += yeltolas;

		kirajzgolyo( Golyok[i].rmostani, Golyok[i].sug, HATTER_GOLYO, &front );

		vekt2 diff( Golyok[i].sug*0.5*cos( Golyok[i].alfamostani ),
					Golyok[i].sug*0.5*sin( Golyok[i].alfamostani ) );
		kirajzgolyo( Golyok[i].rmostani + diff,
					Golyok[i].sug*0.25, HATTER_SIMA, &front );
		kirajzgolyo( Golyok[i].rmostani - diff,
					Golyok[i].sug*0.25, HATTER_SIMA, &front );

		Golyok[i].rmostani.y -= yeltolas;
	}
	Hszoveg = 1;

	// Rairjuk szovegeket:
	for( i = 0; i < elemszam; i++ )
		Pmenuabc->write( &front, sorok[i].x+Menueltolasx, sorok[i].y+Menueltolasy+frame-Menuysize,
							sorok[i].text );

	// Rarakjuk sisakot:
	pic8* sisakframe = NULL;
	if( State->animatedmenus )
		sisakframe = Psisak->getframe( ido*0.0024 );
	else
		sisakframe = Psisak->getframebyindex( 25 );

	blt8( &front, sisakframe, sisakx+Menueltolasx-20, sisaky+Menueltolasy-7-(Menuysize-1)+frame );

	blt8( &front, Pintro, Menueltolasx, Menueltolasy+frame );
	// The whole picture is sent:
	unlockfrontbuffer();
	return 1;
}

#define MAXHIBASORHOSSZ (34)
typedef char hibasor[MAXHIBASORHOSSZ+4];
#define MAXHIBASOR (10)
static hibasor Hibasortomb[MAXHIBASOR];

void grafikushiba( char* text1, char* text2, char* text3 ) {
	gv_menu_picture_ensure();
	tilebetolt();
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
