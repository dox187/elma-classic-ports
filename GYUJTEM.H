// gyujtem.h

// A kesobbi (pl. Steam-es) kiadasok elma.res-eben tovabbi palyagyujtemenyek
// is vannak. Palyaik elma.res-ben maradnak, igy nem szerkeszthetok. Idoiket
// es a jatekosok haladasat ebben a file-ban taroljuk, mert state.dat-ban
// nincs nekik hely, es state.dat formatumat az eredeti es a Steam-es jatek
// is olvassa:
#define GYUJTEMENYSTATE "state-elma-ports.dat"

// Igaz, ha elma.res-ben vannak palyagyujtemenyek:
int vannakgyujtemenyek( void );
// A gyujtemenyek palyait a belso palyakhoz hasonlo nevvel (QWQST001.LEV)
// kapja topol es recorder. Igaz, ha nev ilyen:
int gyujtemenypalya( char* nev );
// A palya elma.res-beli neve (pl. stolen01.lev):
void gyujtemenyresnev( char* nev, char* resnev );
// Gyujtemeny palyajanak idoi GYUJTEMENYSTATE-bol (topol ide olvassa be), es
// mentese (idoelintezes utan saveidok hivja); belyeg a palya belyege, mas
// belyegu palya idoit nem hasznaljuk:
void gyujtemenyidok( char* nev, long belyeg, palyaidok* pidok );
void mentgyujtemenyidok( char* nev, long belyeg, palyaidok* pidok );
// Play menu gyujtemenyekkel (belso es kulso palyak is itt valaszthatok):
void gyujtemenymenu( void );
