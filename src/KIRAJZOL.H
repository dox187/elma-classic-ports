
extern int Voltkilogas; // Csak tesztelesre

// Annak eldontesere, hogy kirajzolando doboz nem log-e ki:
// peldaul: Hatarx1 = 2.0, Hatarx2 = 318.0 (resetkirajzol tolti ki):
extern double   Hatarx1,
				Hatarx2,
				Hatary1,
				Hatary2;

extern int	Cxsize, Cysize; // Belso kep meretei

// The game's picture (lockbackbuffer, m_dd.h) is at most this size; the
// static arrays that depend on the picture's size are sized for this:
#ifdef ELMA_PSX
// The PS1 picture is always 640x480; at the desktop limit the textures,
// widened by this much (lgrfile.cpp), would not fit in its RAM:
#define MAXKEPXSIZE (640)
#define MAXKEPYSIZE (480)
#else
#define MAXKEPXSIZE (4096)
#define MAXKEPYSIZE (2400)
#endif

extern int Kitoltestmegrak;
// Es ennyire toltjuk:
extern int Kitoltestmegrakkezd; 

void novelkepmeret( void );
void csokkentkepmeret( void );

void kirajzol320(
		double t,
		valtozok* pvalt1, valtozok* pvalt2,
		int viewki1, int timeki1,
		int viewki2, int timeki2 );

void forditkepet( pic8* ppic );


