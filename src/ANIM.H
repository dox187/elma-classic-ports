
#define MAXANIMFRAME (1000)
extern const int Animsize;

class anim {
public:
	int frameszam;
	pic8* ppictomb[MAXANIMFRAME];

	// Also flips the picture. Zooms the Animsize wide frames of nagykep to
	// the size meret (0: stays Animsize):
	// meret: size of the frames when zoomed (0: original), resized with szuro
	// and the LGR palette paltomb (szuro.h). forraskocka: size of the frames in
	// nagykep (0: 40; in LGR13 the height of the picture, a higher resolution):
	anim( pic8* nagykep, char* uzenet_filenev, int meret = 0,
		  int szuro = SZURO_LEGKOZELEBBI, unsigned char* paltomb = NULL,
		  int forraskocka = 0 );
	~anim( void );
	pic8* getframe( double ido );
	pic8* getframebyindex( int index );

	// Menu sisakjanal egy kis piros vonalat odahuz fole:
	void korrigal( void );
};