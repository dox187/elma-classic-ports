
FILE* qopen( char* nev, char* paramok );
void qclose( FILE* h );
int qseek( FILE *stream, long offset, int whence );

void initqopen( void );

// Igaz, ha elma.res-ben benne van nev nevu file:
int qvan( char* nev );
void becsomagol( void );

