
#define MAXANIMFRAME (1000)
extern const int Animsize;

class anim {
public:
	int frameszam;
	pic8* ppictomb[MAXANIMFRAME];

	// Meg is forditja kepet. A nagykep Animsize szeles kepkockait meret
	// mereture nagyitja (0: marad Animsize):
	// meret: a kepkockak merete nagyitva (0: eredeti), szuro-vel es az LGR
	// paltomb palettajaval nagyitva (szuro.h):
	anim( pic8* nagykep, char* uzenet_filenev, int meret = 0,
		  int szuro = SZURO_LEGKOZELEBBI, unsigned char* paltomb = NULL );
	~anim( void );
	pic8* getframe( double ido );
	pic8* getframebyindex( int index );

	// Menu sisakjanal egy kis piros vonalat odahuz fole:
	void korrigal( void );
};