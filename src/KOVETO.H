

#define MAXKOVETOKEPSZAM (100)

// How many pixels a texture sticks out above (without zoom; when zoomed,
// Plgr->fuggtoldas):
#define FUGGTOLDAS (20)

class koveto {
public:
	int   kepszam;
	pic8* pkeptomb[MAXKOVETOKEPSZAM];
	int   feltomb[MAXKOVETOKEPSZAM];
	// The picture's transparent color (the original picture's top-left pixel;
	// on the shrunk picture it may already come from a different pixel):
	unsigned char atlatszotomb[MAXKOVETOKEPSZAM];
	// How much the picture steps along the line (even zoomed, the unzoomed
	// picture's slope times the zoom; originally ysize-2*20-1):
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


