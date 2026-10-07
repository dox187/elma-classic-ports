#include	"all.h"

double K_pi = 3.141592;
double K_pip2 = K_pi*0.5;
double K_2pi = K_pi*2.0;

void k_memcpy( void *dest, const void *src, size_t n ) {
	//inkremental();
	memcpy( dest, src, n );
}

static int  Fiben = 0;

#ifdef ELMA_POSIX

#include <glob.h>

static glob_t Figlob;
static size_t Fiindex = 0;
static int Figlobvalid = 0;

static int ficopy( char* filenev ) {
	while( Fiindex < Figlob.gl_pathc ) {
		const char* path = Figlob.gl_pathv[Fiindex++];
		const char* name = strrchr( path, '/' );
		name = name ? name+1 : path;
		char tmpnev[20];
		if( strlen( name ) > 12 )
			continue;
		strcpy( tmpnev, name );
		if( strstr( tmpnev, "." ) )
			*strstr( tmpnev, "." ) = 0;
		if( strlen( tmpnev ) > 8 )
			continue;
		strcpy( filenev, name );
		return 0;
	}
	filenev[0] = 0;
	return 1;
}

int fifirst( char* minta, char* filenev ) {
	if( Fiben )
		hiba( "fifirst" );
	Fiben = 1;
	// Windows-hoz hasonloan kis/nagybetutol fuggetlenul keresunk,
	// ezert minden betut [xX] alakban adunk at glob-nak:
	char pattern[1024];
	int j = 0;
	for( const char* p = minta; *p && j < (int)sizeof(pattern)-5; ++p ) {
		if( *p == '\\' )
			pattern[j++] = '/';
		else if( isalpha( (unsigned char)*p ) ) {
			pattern[j++] = '[';
			pattern[j++] = (char)tolower( (unsigned char)*p );
			pattern[j++] = (char)toupper( (unsigned char)*p );
			pattern[j++] = ']';
		}
		else
			pattern[j++] = *p;
	}
	pattern[j] = 0;
	Fiindex = 0;
	Figlobvalid = glob( pattern, 0, NULL, &Figlob ) == 0;
	if( !Figlobvalid ) {
		filenev[0] = 0;
		return 1;
	}
	return ficopy( filenev );
}

int finext( char* filenev ) {
	if( !Fiben )
		hiba( "8794t" );
	return ficopy( filenev );
}

void ficlose( void ) {
	if( !Fiben )
		hiba( "908uy6" );
	if( Figlobvalid )
		globfree( &Figlob );
	Figlobvalid = 0;
	Fiben = 0;
}

// A jatek Windows-hoz hasonloan kis/nagybetutol fuggetlenul nevezi meg
// file-jait (elma.res, lgr\default.lgr). Kis/nagybetu erzekeny
// file-rendszeren a nem letezo utvonal-elemeket kis/nagybetutol
// fuggetlenul keressuk meg; talalat nelkul az eredeti nev marad, igy uj
// file is letrehozhato. Innentol az igazi fopen es access kell:

#include <dirent.h>

#undef fopen
#undef access

static void utvonalhozfuz( const char* dir, const char* nev,
						   char* ki, int meret ) {
	int dirhossz = strlen( dir );
	if( dirhossz == 0 )
		snprintf( ki, meret, "%s", nev );
	else if( dir[dirhossz-1] == '/' )
		snprintf( ki, meret, "%s%s", dir, nev );
	else
		snprintf( ki, meret, "%s/%s", dir, nev );
}

static void native_path( const char* path, char* ki, int meret ) {
	char utvonal[1024];
	int n = 0;
	for( const char* p = path; *p && n < (int)sizeof(utvonal)-1; ++p )
		utvonal[n++] = *p == '\\' ? '/' : *p;
	utvonal[n] = 0;
	snprintf( ki, meret, "%s", utvonal );
	if( n == 0 || access( utvonal, F_OK ) == 0 )
		return;

	char kesz[1024] = "";
	const char* kezdet = utvonal;
	if( *kezdet == '/' ) {
		strcpy( kesz, "/" );
		kezdet++;
	}
	while( *kezdet ) {
		const char* vege = strchr( kezdet, '/' );
		int nevhossz = vege ? int(vege-kezdet) : int(strlen( kezdet ));
		char nev[256];
		if( nevhossz > 255 )
			nevhossz = 255;
		memcpy( nev, kezdet, nevhossz );
		nev[nevhossz] = 0;

		char jelolt[1024];
		utvonalhozfuz( kesz, nev, jelolt, sizeof( jelolt ) );
		if( nevhossz > 0 && access( jelolt, F_OK ) != 0 ) {
			DIR* dir = opendir( kesz[0] ? kesz : "." );
			if( dir ) {
				dirent* elem;
				while( (elem = readdir( dir )) != NULL ) {
					if( strcasecmp( elem->d_name, nev ) == 0 ) {
						utvonalhozfuz( kesz, elem->d_name, jelolt,
									   sizeof( jelolt ) );
						break;
					}
				}
				closedir( dir );
			}
		}
		strcpy( kesz, jelolt );
		if( !vege )
			break;
		kezdet = vege+1;
	}
	snprintf( ki, meret, "%s", kesz );
}

FILE* elma_fopen( const char* path, const char* mode ) {
	char nativ[1024];
	native_path( path, nativ, sizeof( nativ ) );
	return fopen( nativ, mode );
}

int elma_access( const char* path, int mode ) {
	char nativ[1024];
	native_path( path, nativ, sizeof( nativ ) );
	return access( nativ, mode );
}

#elif defined(W_95)

/*struct _finddata_t c_file;
    long hFile;

    // Find first .c file in current directory 
    if( (hFile = _findfirst( "*.c", &c_file )) == -1L )
       printf( "No *.c files in current directory!\n" );
   else
   {
            printf( "Listing of .c files\n\n" );
            printf( "\nRDO HID SYS ARC  FILE         DATE %25c SIZE\n", ' ' );
            printf( "--- --- --- ---  ----         ---- %25c ----\n", ' ' );
            printf( ( c_file.attrib & _A_RDONLY ) ? " Y  " : " N  " );
            printf( ( c_file.attrib & _A_SYSTEM ) ? " Y  " : " N  " );
            printf( ( c_file.attrib & _A_HIDDEN ) ? " Y  " : " N  " );
            printf( ( c_file.attrib & _A_ARCH )   ? " Y  " : " N  " );
            printf( " %-12s %.24s  %9ld\n",
               c_file.name, ctime( &( c_file.time_write ) ), c_file.size );

            // Find the rest of the .c files 
            while( _findnext( hFile, &c_file ) == 0 )
            {
                printf( ( c_file.attrib & _A_RDONLY ) ? " Y  " : " N  " );
                printf( ( c_file.attrib & _A_SYSTEM ) ? " Y  " : " N  " );
                printf( ( c_file.attrib & _A_HIDDEN ) ? " Y  " : " N  " );
                printf( ( c_file.attrib & _A_ARCH )   ? " Y  " : " N  " );
                printf( " %-12s %.24s  %9ld\n",
                   c_file.name, ctime( &( c_file.time_write ) ), c_file.size );
            }

       _findclose( hFile )
*/



static long Fihandler = -1;

// WINDOWS-os

int fifirst( char* minta, char* filenev ) {
	if( Fiben || Fihandler != -1L )
		hiba( "fifirst" );
	Fiben = 1;

	filenev[0];
	struct _finddata_t c_file;
	Fihandler = _findfirst( minta, &c_file );
	if( Fihandler == -1 )
		return 1;

	// Megvizsgaljuk nem tul hosszu-e nev:
	if( strlen( c_file.name ) <= 12 ) {
		char tmpnev[20];
		strcpy( tmpnev, c_file.name );
		// Levagjuk vegerol kiterjesztest:
		if(  strstr( tmpnev, "." ) )
			*strstr( tmpnev, "." ) = 0;
		if( strlen( tmpnev ) <= 8 ) {
			strcpy( filenev, c_file.name );
			return 0;
		}
	}
	// Tul hosszu volt nev, tehat nezzuk tovabb:
	return finext( filenev );
}

// WINDOWS-os

int finext( char* filenev ) {
	if( !Fiben || Fihandler == -1L )
		hiba( "8794t" );

	filenev[0] = 0;

	while( 1 ) {
		struct _finddata_t c_file;
		if( _findnext( Fihandler, &c_file ) != 0 )
			return 1;

		// Megvizsgaljuk nem tul hosszu-e nev:
		if( strlen( c_file.name ) > 12 )
			continue; // Tul hosszu nev

		char tmpnev[20];
		strcpy( tmpnev, c_file.name );
		// Levagjuk vegerol kiterjesztest:
		if(  strstr( tmpnev, "." ) )
			*strstr( tmpnev, "." ) = 0;
		if( strlen( tmpnev ) > 8 )
			continue; // Tul hosszu nev

		// Nev rendben van:
		strcpy( filenev, c_file.name );
		return 0;
	}
}

// WINDOWS-os

void ficlose( void ) {
	if( !Fiben )
		hiba( "908uy6" );
	Fiben = 0;
	if( Fihandler != -1L ) {
		_findclose( Fihandler );
		Fihandler = -1L;
	}
}

#else

// DOS-os

static find_t Ffblk;

int fifirst( char* minta, char* filenev ) {
	if( Fiben )
		hiba( "fifirst" );
	Fiben = 1;
	int done = _dos_findfirst( minta, _A_NORMAL, &Ffblk );

	filenev[0] = 0;
	if( !done ) {
		if( strlen( Ffblk.name ) > 12 )
			hiba( "89tt38ju" );
		strcpy( filenev, Ffblk.name );
	}

	return done;
}

// DOS-os

int finext( char* filenev ) {
	if( !Fiben )
		hiba( "8794t" );
	int done = _dos_findnext( &Ffblk );

	filenev[0] = 0;
	if( !done ) {
		if( strlen( Ffblk.name ) > 12 )
			hiba( "89tt38ju" );
		strcpy( filenev, Ffblk.name );
	}

	return done;
}

// DOS-os

void ficlose( void ) {
	if( !Fiben )
		hiba( "908uy6" );
	Fiben = 0;
}

#endif


static char Nyilasbetuk[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

int nyilasbetu( char* nev, int* phossz, int maxhossz, int c ) {
	if( c != MK_UP && c != MK_DOWN && c != MK_LEFT && c != MK_RIGHT )
		return 0;
	int i = *phossz;
	if( c == MK_LEFT ) {
		if( i > 0 )
			i--;
	}
	else if( i == 0 || c == MK_RIGHT ) {
		// Uj betu:
		if( i < maxhossz ) {
			nev[i] = 'A';
			i++;
		}
	}
	else {
		// Utolso betu leptetese:
		int betuszam = strlen( Nyilasbetuk );
		char* p = strchr( Nyilasbetuk, toupper( (unsigned char)nev[i-1] ) );
		int sorszam = p ? int(p-Nyilasbetuk) : 0;
		if( c == MK_UP )
			sorszam++;
		else
			sorszam += betuszam-1;
		nev[i-1] = Nyilasbetuk[sorszam%betuszam];
	}
	nev[i] = 0;
	*phossz = i;
	return 1;
}
