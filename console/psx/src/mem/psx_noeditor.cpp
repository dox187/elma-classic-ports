// The level editor is not in the PlayStation version (its menu entry is
// hidden, ELMA_HANDHELD), and mem.cmake leaves its files out. This file
// keeps what the rest of the game uses from EDITUJ.CPP, copied unchanged:
// the level pointer, the small fonts, the editor palette (the dialogs use
// it) and the mouse pointer of the dialogs. Compiled as the core is.
#include	"all.h"

topol* Ptop = NULL;

abc8 *Pabc1 = NULL, *Pabc2 = NULL;

int Valtozott = 0;

unsigned char Hatterindex = 3;

ddpal* Pal_editor = NULL;
static unsigned char Pal_editor_byteok[768];

void seteditorpal( void ) {
	unsigned char* pal = Pal_editor_byteok;
	// Paletta elso 64 szine menu szinek,
	// Masodik 64 szin truecolor tabla
	// Masodik 128 szin eger szine:

	// Lenullazzuk:
	int i;
	for( i = 0; i < 768; i++ )
		pal[i] = 128;

	pal[ 0+0] =   0; pal[ 0+1] =   0; pal[ 0+2] =   0; //  0.
	pal[ 3+0] = 122; pal[ 3+1] = 131; pal[ 3+2] = 181; //  1.
	pal[ 6+0] =  48; pal[ 6+1] =  56; pal[ 6+2] = 107; //  2.
	pal[ 9+0] = 171; pal[ 9+1] = 146; pal[ 9+2] = 142; //  3.
	pal[12+0] = 252; pal[12+1] = 218; pal[12+2] = 213; //  4.
	pal[15+0] =   0; pal[15+1] =   0; pal[15+2] =   0; //  5.
	pal[18+0] = 213; pal[18+1] = 148; pal[18+2] = 139; //  6.
	pal[21+0] = 223; pal[21+1] = 209; pal[21+2] = 206; //  7.
	pal[24+0] = 198; pal[24+1] = 202; pal[24+2] = 231; //  8.
	pal[27+0] = 255; pal[27+1] = 255; pal[27+2] = 255; //  9.
	pal[30+0] = 180; pal[30+1] = 120; pal[30+2] = 110; //  10.
	pal[39*3+0] = 0; pal[39*3+1] = 0; pal[39*3+2] = 0; //  39.
	pal[59*3+0] = 0; pal[59*3+1] = 0; pal[59*3+2] = 0; //  59. Kisabc
	pal[62*3+0] = 255; pal[62*3+1] = 255; pal[62*3+2] = 255; //  62. Kisabc

	// Kitoltjuk trucolor paletta szineit:
	for( i = 0; i < 64; i++ ) {
		int r = i>>4;
		int g = (i>>2) & 3;
		int b = i & 3;
		pal[(64+i)*3+0] = (unsigned char)(r*64 + 8);
		pal[(64+i)*3+1] = (unsigned char)(g*64 + 8);
		pal[(64+i)*3+2] = (unsigned char)(b*64 + 8);
	}

	// Kitoltjuk eger szineket:
	for( i = 0; i < 128; i++ ) {
		if( pal[3*i] + pal[3*i+1] + pal[3*i+2] >= 384 ) {
			pal[3*(i+128)] = pal[3*(i+128)+1] = pal[3*(i+128)+2] = 0;
		}
		else {
			pal[3*(i+128)] = pal[3*(i+128)+1] = pal[3*(i+128)+2] = 255;
		}
	}

	for( i = 0; i < 768; i++ )
		pal[i] /= 4;

	if( Pal_editor )
		hiba( "uvcguyew" );
	Pal_editor = new ddpal( pal );
}

static int Egerkint = 0;

int Moux = 0, Mouy = 0, Kozelvan = 0;

static void elintezegymousepixelt( int x , int y ) {
	if( x < 0 || y < 0 || x > 639 || y > 479 )
		return;
	unsigned char szin = Buffsima->gpixel( x, y );
	szin += 128;
	Buffsima->ppixel( x, y, szin );
	ppixelfront( x, y, szin );
}

static void egeretrajzolja( void ) {
	/*if( Tool == T_MOVE && !Pgy && !Pker && !Psp && Kurzornegyzet ) {
		//hiba( "Most itt van benn!" );
		vekt2 r = konv( Moux, Mouy );
		double x1 = r.x;
		double y1 = r.y;
		double x2 = x1+640.0/Arany;
		double y2 = y1+480.0/Arany;
		vonalrajz( vekt2( x1, y1 ), vekt2( x1, y2 ), 0 );
		vonalrajz( vekt2( x1, y2 ), vekt2( x2, y2 ), 0 );
		vonalrajz( vekt2( x2, y2 ), vekt2( x2, y1 ), 0 );
		vonalrajz( vekt2( x2, y1 ), vekt2( x1, y1 ), 0 );
		return;
	} */

	// Lockolunk is:
	lockfrontbuffer_pic();
	int sugar = 4;
	for( int i = -sugar; i <= sugar; i++ ) {
		if( Kozelvan ) {
			elintezegymousepixelt( Moux+i, Mouy+i );
			if( i != 0 )
				elintezegymousepixelt( Moux+i, Mouy-i );
		}
		else {
			elintezegymousepixelt( Moux+i, Mouy );
			if( i != 0 )
				elintezegymousepixelt( Moux, Mouy+i );
		}
	}
	unlockfrontbuffer_pic();
}

// Egeret leveszi kepernyorol:
void push( void ) {
	if( !Egerkint )
		hiba( "push-ban !Egerkint!" );
	Egerkint = 0;

	egeretrajzolja();
}

// Egeret felteszi kepernyore:
void pop( void ) {
	if( Egerkint )
		hiba( "pop-ban Egerkint!" );
	Egerkint = 1;

	egeretrajzolja();
}

static int Kellredrawegesz = 0;
void invalidateegesz( void ) {
	Kellredrawegesz = 1;
}

// The menu entry is hidden; nothing to do.
void editor( void ) {
}
