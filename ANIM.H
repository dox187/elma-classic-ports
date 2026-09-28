
#define MAXANIMFRAME (1000)
extern const int Animsize;

class anim {
public:
	int frameszam;
	pic8* ppictomb[MAXANIMFRAME];

	// Meg is forditja kepet. A nagykep Animsize szeles kepkockait meret
	// mereture nagyitja (0: marad Animsize):
	anim( pic8* nagykep, char* uzenet_filenev, int meret = 0 );
	~anim( void );
	pic8* getframe( double ido );
	pic8* getframebyindex( int index );

	// Menu sisakjanal egy kis piros vonalat odahuz fole:
	void korrigal( void );
};