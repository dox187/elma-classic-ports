

extern double K_pi;
extern double K_pip2;
extern double K_2pi;

#ifdef ELMA_POSIX
#define _fstrnicmp strncasecmp
#elif defined(W_95)
#define _fstrnicmp _strnicmp
#endif

typedef char finame[20];
int fifirst( char* minta, char* filenev );
int finext( char* filenev );
void ficlose( void );

// Kezikonzolon nincs billentyuzet, ezert a neveket nyilakkal is be lehet
// irni: fel/le lepteti az utolso betut, jobbra uj betut kezd, balra torol.
// Igazzal ter vissza, ha c ilyen nyil volt:
int nyilasbetu( char* nev, int* phossz, int maxhossz, int c );
