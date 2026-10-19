// Bounded scanline decoder for the PSX PCX loader. No image allocation.
#pragma once

#include <stdio.h>
#include <string.h>

struct psx_pcx_reader {
	FILE* file;
	unsigned char bytes[128];
	int at, length;
	int next() {
		if( at == length ) {
			length = fread( bytes, 1, sizeof( bytes ), file );
			at = 0;
			if( !length ) return -1;
		}
		return bytes[at++];
	}
};

// Starts after the 128-byte header. Padding is consumed but never drawn.
// Preserve the exact end of the encoded rows for sequential embedded PCX.
// Returns zero on success; malformed, truncated or unseekable input fails.
static inline int psx_pcx_decode( FILE* file, unsigned char* const* rows,
								int width, int height, int stride ) {
	if( width <= 0 || height <= 0 || stride < width ) return -1;
	psx_pcx_reader input;
	input.file = file;
	input.at = input.length = 0;
	for( int y = 0; y < height; ++y ) {
		int x = 0;
		while( x < stride ) {
			int color = input.next(), count = 1;
			if( color < 0 ) return -1;
			if( (color & 0xc0) == 0xc0 ) {
				count = color & 0x3f;
				if( !count || count > stride-x ) return -1;
				color = input.next();
				if( color < 0 ) return -1;
			}
			if( x < width ) {
				const int visible = count < width-x ? count : width-x;
				if( visible == 1 ) rows[y][x] = color;
				else memset( rows[y]+x, color, visible );
			}
			x += count;
		}
	}
	if( input.at < input.length && fseek( file, input.at-input.length, SEEK_CUR ) ) return -1;
	return 0;
}
