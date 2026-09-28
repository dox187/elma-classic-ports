// gyujtem.h

// Later (e.g. Steam) releases have further level collections in elma.res.
// Their levels stay in elma.res, so they cannot be edited. We store their
// times and the players' progress in this file, because state.dat has no
// room for them, and both the original and the Steam release read the
// state.dat format:
#define GYUJTEMENYSTATE "state-elma-ports.dat"

// True if there are level collections in elma.res:
int vannakgyujtemenyek( void );
// topol and recorder get the collections' levels with a name similar to the
// internal levels (QWQST001.LEV). True if nev is such a name:
int gyujtemenypalya( char* nev );
// The level's name in elma.res (e.g. stolen01.lev):
void gyujtemenyresnev( char* nev, char* resnev );
// A collection level's times from GYUJTEMENYSTATE (topol reads them here),
// and saving them (saveidok calls this after idoelintezes); belyeg is the
// level's stamp, we do not use times of a level with a different stamp:
void gyujtemenyidok( char* nev, long belyeg, palyaidok* pidok );
void mentgyujtemenyidok( char* nev, long belyeg, palyaidok* pidok );
// Play menu with collections (internal and external levels are also
// selected here):
void gyujtemenymenu( void );
