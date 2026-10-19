// The game core's file functions on the PS1 file layer (psx_file.h): the
// fopen/access of ALL.H and the directory listing of KOZOS.H.
#include "all.h"
#include "psx_file.h"

FILE* elma_fopen( const char* path, const char* mode ) { return psx_fopen( path, mode ); }

int elma_access( const char* path, int ) { return psx_access( path ); }

namespace {
int listing = 0;
char list_dir[64], list_pattern[32];
int list_index = 0;

int next_name( char* filenev ) {
	char name[32];
	while( psx_file_list( list_dir, list_pattern, list_index++, name, sizeof( name ) ) == 0 ) {
		// Like the other platforms, only DOS (8.3) names:
		char base[32];
		strcpy( base, name );
		if( strchr( base, '.' ) )
			*strchr( base, '.' ) = 0;
		if( strlen( name ) > 12 || strlen( base ) > 8 )
			continue;
		strcpy( filenev, name );
		return 0;
	}
	filenev[0] = 0;
	return 1;
}
}

// minta: a DOS pattern such as "lev\\*.lev".
int fifirst( char* minta, char* filenev ) {
	if( listing )
		hiba( "fifirst" );
	listing = 1;
	const char* slash = strrchr( minta, '\\' );
	if( !slash )
		slash = strrchr( minta, '/' );
	int dir_length = slash ? int( slash - minta ) : 0;
	if( dir_length >= int( sizeof( list_dir ) ) )
		dir_length = sizeof( list_dir ) - 1;
	memcpy( list_dir, minta, dir_length );
	list_dir[dir_length] = 0;
	snprintf( list_pattern, sizeof( list_pattern ), "%s", slash ? slash+1 : minta );
	list_index = 0;
	return next_name( filenev );
}

int finext( char* filenev ) {
	if( !listing )
		hiba( "8794t" );
	return next_name( filenev );
}

void ficlose( void ) {
	if( !listing )
		hiba( "908uy6" );
	listing = 0;
}
