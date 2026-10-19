// Exercise the actual PSX decoder with separate guarded rows and a seekable
// stream: padding, refill boundaries, truncation, and adjacent embedded images.
#include "pcx_decode.h"
#include <vector>

static int failures = 0;
#define CHECK(condition) do { if( !(condition) ) { \
	printf( "FAIL PCX line %d: %s\n", __LINE__, #condition ); ++failures; } } while( 0 )

static FILE* stream( const std::vector<unsigned char>& bytes ) {
	FILE* file = tmpfile();
	if( !file ) return NULL;
	fwrite( bytes.data(), 1, bytes.size(), file );
	rewind( file );
	return file;
}

int main() {
	unsigned char a[19], b[19];
	memset( a, 0xee, sizeof(a) ); memset( b, 0xee, sizeof(b) );
	unsigned char* rows[] = { a+8, b+8 };
	FILE* file = stream( { 0xc4, 7, 1, 2, 3, 99, 0xc3, 8, 4, 5, 6, 0xaa } );
	CHECK( file );
	if( !file ) return 2;
	CHECK( psx_pcx_decode( file, rows, 3, 2, 4 ) == 0 );
	CHECK( ftell(file) == 6 );
	CHECK( memcmp( a+8, "\7\7\7", 3 ) == 0 );
	CHECK( memcmp( b+8, "\1\2\3", 3 ) == 0 );
	CHECK( psx_pcx_decode( file, rows, 3, 2, 3 ) == 0 );
	CHECK( ftell(file) == 11 && fgetc(file) == 0xaa );
	CHECK( memcmp( a+8, "\10\10\10", 3 ) == 0 );
	CHECK( memcmp( b+8, "\4\5\6", 3 ) == 0 );
	for( int i = 0; i < 8; ++i ) {
		CHECK( a[i] == 0xee && a[11+i] == 0xee );
		CHECK( b[i] == 0xee && b[11+i] == 0xee );
	}
	fclose(file);

	// A run marker at the last byte of a refill takes its color from the next.
	std::vector<unsigned char> bytes(129, 2);
	bytes[127] = 0xc3; bytes[128] = 9;
	file = stream(bytes);
	unsigned char wide[130], *wide_rows[] = { wide };
	CHECK( psx_pcx_decode( file, wide_rows, 130, 1, 130 ) == 0 );
	CHECK( ftell(file) == 129 && wide[126] == 2 && wide[127] == 9 && wide[129] == 9 );
	fclose(file);
	for( const auto& invalid : std::vector<std::vector<unsigned char>>{
		{}, {0xc0,7}, {0xc5,7}, {0xc4}, {1,2} } ) {
		file = stream(invalid);
		CHECK( psx_pcx_decode( file, rows, 3, 1, 4 ) != 0 );
		fclose(file);
	}
	file = stream({1,2,3});
	CHECK( psx_pcx_decode( file, rows, 3, 1, 2 ) != 0 );
	CHECK( ftell(file) == 0 );
	fclose(file);
	printf( "%s: PCX padding, runs, refill/EOF, guarded rows and embedded stream position\n", failures ? "FAIL" : "PASS" );
	return failures ? 1 : 0;
}
