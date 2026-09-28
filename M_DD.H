// m_dd.h
 
class pic8;
class palyaleiro;
class recorder;

class ddpal {
	friend void lassufizre( pic8* ppic, ddpal* ppal );
public:
	#ifdef W_95
		void* pddpal;
	#else
		unsigned char* tomb;
	#endif

	ddpal( unsigned char* tomb );
	~ddpal( void );
	void set( void );
};

// Ha igaz, alulrol indul y (kirajz320 allitja igazba):
extern int Locky0_alul; 

// A jatek kepe (kirajzol320) sajat xsize*ysize meretu kep, a lockbackbuffer
// ysize sormutatot ad vissza (Locky0_alul eseten forditva). A menuk, dialogusok
// es az editor kepe (lockfrontbuffer) mindig 640x480-as es megmarad ket
// rajzolas kozott.
unsigned char** lockbackbuffer( int fizikai );
void unlockbackbuffer( void ); // Ki is teszi
// A kovetkezo lockbackbuffer altal adott kep merete, lockolt allapotban a
// lockolte. Csak ket kep kozott valtozhat, legalabb 640x480, legfeljebb
// MAXKEPXSIZE*MAXKEPYSIZE (kirajzol.h):
void backbuffersize( int* xsize, int* ysize );

unsigned char** lockfrontbuffer( void );
void unlockfrontbuffer( void );

// Kep nagyitasanak modja az ablakban, Options menuben allithato. NULL-t ad
// vissza, ha a platformon nem allithato (terminal, SDL 1.2):
const char* dd_scale_name( void );
void dd_next_scale( void ); // Kovetkezo modra valt es elmenti

// Jatek kepenek oldalaranya (kepernyoe vagy 4:3), Options menuben allithato,
// a kovetkezo kephez ervenyes. NULL-t ad vissza, ha a platformon nem
// allithato (terminal, SDL 1.2):
const char* dd_aspect_name( void );
void dd_next_aspect( void ); // Masikra valt es elmenti


