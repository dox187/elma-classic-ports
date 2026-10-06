#include "save.h"
#include "levels.h"

#define MAX_LEVELS 64

typedef struct {
	char magic[4];
	uint8_t best[MAX_LEVELS][3];
	uint8_t sum;
} save_t;

// At the end of the PRG-RAM, where it stays from build to build:
#define Save (*(save_t*)0x7f00)

static uint8_t checksum( void ) {
	const uint8_t* p = (const uint8_t*)&Save;
	uint8_t s = 0x5a;
	for( uint16_t i = 0; i < sizeof( save_t )-1; i++ )
		s = (uint8_t)((s << 1) | (s >> 7))+p[i];
	return s;
}

void save_load( void ) {
	if( Save.magic[0] == 'E' && Save.magic[1] == 'L' && Save.magic[2] == 'M' &&
			Save.magic[3] == 'A' && Save.sum == checksum() )
		return;
	Save.magic[0] = 'E';
	Save.magic[1] = 'L';
	Save.magic[2] = 'M';
	Save.magic[3] = 'A';
	for( uint8_t i = 0; i < MAX_LEVELS; i++ )
		Save.best[i][0] = Save.best[i][1] = Save.best[i][2] = 0xff;
	Save.sum = checksum();
}

uint32_t save_best( uint8_t level ) {
	const uint8_t* b = Save.best[level];
	return (uint32_t)b[0] | (uint32_t)b[1] << 8 | (uint32_t)b[2] << 16;
}

uint8_t save_done( uint8_t level ) {
	return save_best( level ) != NO_TIME;
}

uint8_t save_finish( uint8_t level, uint32_t time ) {
	if( time >= save_best( level ) )
		return 0;
	Save.best[level][0] = (uint8_t)time;
	Save.best[level][1] = (uint8_t)(time >> 8);
	Save.best[level][2] = (uint8_t)(time >> 16);
	Save.sum = checksum();
	return 1;
}

uint8_t save_open( uint8_t level ) {
	return level == 0 || save_done( level ) || save_done( level-1 );
}
