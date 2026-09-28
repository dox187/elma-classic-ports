
void play( void );
// List of internal levels, with kulsovel its first row is External File:
void belsopalyak( int kulsovel );

// A jelenleg beolvasott palyan jatszik vissza:
// Csak afterplay menu replay-ebol szabad hasznalni:
// Azt a nevet kerik, amit topol::topol kap:
// Ezenlegjobbido beallitasahoz kell neki:
void replayjelenlegi( char* filenev );

// Vagy level == -1 es belyeg != 0 es filenev == NULL,
// vagy level >= 0 < 100 es belyeg = 0 es filenev == NULL,
// vagy level == -1 es belyeg = 0 es filenev ervenyes,
// Hamis eseten nem sikerult betolteni palyat (rec filehoz nincs lev):
//int palyabe( int level, unsigned long belyeg = 0, char* filenev = NULL );

// belyeg == 0 eseten internal level file:
void saveplay( long belyeg );

void idoelintezes( long ido, char* valasz, int level, char* filenev );
// 0-ESC, 1-this level, 2-next level, 3-skip level
// If filenev is not NULL, it is an external file, and then with kovetkezovan
// (for collection levels) there is also a Play next:
int afterplay( int level, int nextdefault, char* idoeredmeny, char* filenev,
			   int kovetkezovan = 0 );

void kiirloading( void );
