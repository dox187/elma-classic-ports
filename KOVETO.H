

#define MAXKOVETOKEPSZAM (100)

// Hany pixel magasan log tul textura (nagyitas nelkul, nagyitva
// Plgr->fuggtoldas):
#define FUGGTOLDAS (20)

class koveto {
public:
	int   kepszam;
	pic8* pkeptomb[MAXKOVETOKEPSZAM];
	int   feltomb[MAXKOVETOKEPSZAM];
	// A kep atlatszo szine (az eredeti kep bal felso pixele, a kicsinyitett
	// kepen az mar mas pixelbol johet):
	unsigned char atlatszotomb[MAXKOVETOKEPSZAM];
	// Ennyit lep a kep a vonalon (nagyitva is a nagyitatlan kep lejtese
	// szorozva, ysize-2*20-1 eredetileg):
	int   lejtestomb[MAXKOVETOKEPSZAM];
	koveto( void );
	~koveto( void );
	void addkep( pic8* ppic, int up, unsigned char atlatszo, int lejtes );
};

// Ez nem hasznal semmit koveto adatokbol, csak Ptop-bol:
int makevonal( gyuru* pgy, int* ytomb, int* phossz, int* px0,
				int maxhely, vekt2* porigo );

void makekoveto( void );

void tesztkoveto( void );


