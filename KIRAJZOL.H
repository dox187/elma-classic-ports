
extern int Voltkilogas; // Csak tesztelesre

// Annak eldontesere, hogy kirajzolando doboz nem log-e ki:
// peldaul: Hatarx1 = 2.0, Hatarx2 = 318.0 (resetkirajzol tolti ki):
extern double   Hatarx1,
				Hatarx2,
				Hatary1,
				Hatary2;

extern int	Cxsize, Cysize; // Belso kep meretei

// A jatek kepe (lockbackbuffer, m_dd.h) legfeljebb ekkora; ehhez vannak
// meretezve a kep meretetol fuggo statikus tombok:
#define MAXKEPXSIZE (4096)
#define MAXKEPYSIZE (2400)

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


