
// Ezt mv_main elott meghivja es grafikus hibakiirashoz
// kell beolvasni peldaul abc-t es hatteret (teljes.cpp-ben):
//void initmenukep1( void );
//void initmenukep2( void );

void grafikushiba( char* text1, char* text2 = NULL, char* text3 = NULL );

extern pic8* Buffsima;
extern pic8* Buffgolyo;

// The size of the menus' image (Buffsima and Buffgolyo are this size too)
// and the offset of the menus designed for 640x480, so they end up centered:
extern int Menuxsize, Menuysize, Menueltolasx, Menueltolasy;
// True means the menus' image is 640x480 (editor):
extern int Menueredeti;
// Sets the menus' size per the platform's suggestion (or Menueredeti),
// returns true if it changed (then it needs to be redrawn):
int menumeretbeallit( void );

extern abc8* Pmenuabc;

extern ddpal* Pmenupal;
extern unsigned char Menupaltomb[768];

struct egyszovsor {
	char text[102];
	int x, y;
	int kozep; // addszoveg_kozep-pel kerult be (terminalos kiirashoz)
};

// On a tall menu image, lists can have more rows too (valaszt2), with a
// title and tabs:
#define MAXSZOVEGSOR (300)

class szoveglista {
	int sisakx, sisaky;

	egyszovsor* sorok;
	int elemszam;
	int ervenyes;
public:
	szoveglista( void );
	~szoveglista( void );
	void addszoveg( char* text, int x, int y );
	void addszoveg_kozep( char* text, int x, int y );
	void setsisak( int x, int y );
	void clear( void );
	void kirajzol( int nemkellgolyo = 0,
				   pic8* rarakkep1 = NULL, pic8* rarakkep2 = NULL,
				   pic8* rarakkep3 = NULL, pic8* rarakkep4 = NULL );
	int  kirajzolanim( double ido );
};

// Letorli Elasto Mania feliratot hatterkeprol:
void tilevaltas( void );

// Teljes olvassa be es elso kiirloading szabaditja fel:
extern pic8* Pintro;

