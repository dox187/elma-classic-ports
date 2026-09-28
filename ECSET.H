
class ecset;
struct mdarab;
void betoltecseteket( void );

// Egy iterator class (inkabb cache) ecsethez (foltoz hasznalja oket):
class mdbiter {
	ecset* pecset;
	int xposbent, ybent;
	mdarab* pmd;
public:
	mdbiter( ecset* pecset );
	mdarab* getpmd( int x, int y );
	// Az utoljara visszaadott mdarab elso pixelenek x-e:
	int getxpos( void ) { return xposbent; }
};


// Elso par strukturat be lehetne majd vinni cpp-be:

#define PX_FOLD (1)
#define PX_EG   (NULL)
#define PX_URES (2)

struct mdarab {
	mdarab *pkov;
	int xsize;
	int tavolsag;
	unsigned char* pixelek;
};

#define TOMBBENMDARAB (10000)

struct mdarabtomb {
	mdarab 		tomb[TOMBBENMDARAB];
	mdarabtomb* kovtomb;
};

// Ennel tobb sora nem lehet egy ecsetnek (a sortombok a palya magassagahoz
// igazodnak; eredetileg 12000 volt a fix meretuk):
#define MAXECSETSOR (1000000)

struct darab {
	int xsize;
	unsigned char* pixelek;
};

class ecset {
	friend void betoltecseteket( void );
	friend void segedfv( void );
	friend mdarab* mdbiter::getpmd( int x, int y );

	// madarab allokalas:
	mdarabtomb* elsotomb;
	mdarabtomb* kurtomb;
	int tombbenkov;
	mdarab* newmdarab( void );
	void deletemdarabok( void );

	darab* nagydarabtomb;

	int view;
	vekt2 origo;
	double xsizedb, ysizedb;
	int maxx, sorszam;
	// origo, maxx es sorszam az eredeti 48-as Arany-nyal (kilogna-hoz):
	vekt2 eredetiorigo;
	int eredetimaxx, eredetisorszam;
	// A sortombok sorszam+10 elemuek (lefoglalsortomboket):
	int     sortombmeret;
	mdarab** msorok;
	darab**  sorok;
	// Kulon van ket jatekosnak:
	int*	kurxposok_A; // Eppen hol all mutatohoz tartozo x
	darab** curdarabok_A; // Melyik darab kurrens
	int*	kurxposok_B; // Eppen hol all mutatohoz tartozo x
	darab** curdarabok_B; // Melyik darab kurrens
	void lefoglalsortomboket( void );

	void getorigoandsize( void );
	void addszakasz( vonal* psz );
	// Rovid folddarabokat atalakitja konkret mutatova:
	void foldmutatocsere( void );
	// Egymas utani azonos maszkokat es ureseket lecsereli egy hosszabbra:
	void duplaeliminacio( void );
	void textura2mutato( void );
	void mutatotlanit( void );

	// Ptop kerek-jeinek egesz koordinatait kitolti:
	void kitoltfoodkoordokat( void );

	void levon10000t( void );
	mdarab* beepitegymadarabnyit( mdarab* pmd, unsigned char* ujpixelek,
				  int x1, int ujx1, int ujx2,
				  int ujtavolsag, mdarab* vege, int* pujavege, int fazis );
	void addbytesor( unsigned char* ujpixelek, int ujtavolsag,
								int ujx1, int ujx2, int y, int fazis );
	void addegymaszk( sprite* psp, int index_t, int index_m, int fazis );
	void addspriteok( int fazis );
	void addobjektumok( void ); // Ez most nem view eseten visszter

	void kovetotextura( koveto* pkov, int index, int xo, int yo, int fazis );
	void kiegykovetokep( koveto* pkov, int index, int xo, int yo, int fazis );
	void kikovetokepek( koveto* pkov, int* ytomb, int hossz, int x0, int fazis );
	void addkovetok( int fazis );

	void kiegysor_A( unsigned char* pc, int ye );
	void kiegysor_B( unsigned char* pc, int ye );
	void kiegysor_FF( unsigned char* pc, int ye ); // fekete-feher

	void foltoz( void );

	ecset( int view ); // Ptop es Pszak alapjan
	ecset( ecset* pold ); // Ures sortomboket hoz benne letre
	~ecset( void );
public:
	void getbalalso_int( vekt2 balalso, int* px, int* py );
	// Beallitja Kisordarabszam-ot is ha define-olt (escet.cpp eleje):
	// Az ecseten kivul eso reszre also es view ecset foldet rajzol, felso
	// semmit:
	void kitesz(     int ajatekos, pic8* ppic, vekt2 balalso, int x1, int y1, int x2, int y2 );
	void kiteszview( int ajatekos, pic8* ppic, vekt2 balalso, int x1, int y1, int x2, int y2 );
	// Igaz, ha az eredeti jatek 640x480-as kepe (Arany 48) a motor kozepenek
	// ebben a helyzeteben mar kilogott volna az (also) ecsetbol; ott az
	// eredeti hiba-val kilepett, most a motor meghal (vizsgalat):
	int kilogna( vekt2 motorkozep );

	//void egetkeszit( void );
};

extern ecset* Pecsetalso;
extern ecset* Pecsetfelso;
extern ecset* Pecsetview;

extern int Kisordarabszam;

// Ket kis utility fuggveny (hasznalja oket LGR.CPP):
// Visszaadja hany pixel lyuk szinu x-tol kezdve:
int uresszam( int x, int xsize, unsigned char* sor, unsigned char lyuk );
// Visszaadja hany pixel nem lyuk szinu x-tol kezdve:
int teliszam( int x, int xsize, unsigned char* sor, unsigned char lyuk );

// betoltecseteket ide osszegzi osszes lefoglalt szakaszt:
extern int Osszegszam;

