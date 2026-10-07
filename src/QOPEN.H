
FILE* qopen( char* nev, char* paramok );
void qclose( FILE* h );
int qseek( FILE *stream, long offset, int whence );

void initqopen( void );

// True if the file named nev is in elma.res:
int qvan( char* nev );
void becsomagol( void );

