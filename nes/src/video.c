#include "video.h"
#include <mapper.h>
#include <neslib.h>
#include "chrmap.h"
#include "map.h"
#include "sprites.h"

// Run by the MMC3 IRQ system: at the NMI the background is off and the
// bike's sprites are switched in, after BAR_LINES lines the background is
// on.
static uint8_t Irq_game[] = {
	0xf1, 0x14,          // PPUMASK: sprites only
	0xf9, CHR_SPR_BIKE,  // CHR register 2: the bike's bank
	BAR_LINES-1,
	0xf1, 0x1e,          // PPUMASK: background and sprites
	0xff
};

void frame_begin( void ) {
	oam_clear();
	vram_begin();
}

void frame_end( void ) {
	vram_end();
	set_vram_update( Vram_buf );
	ppu_wait_nmi();
	set_vram_update( 0 );
}

void video_game( uint8_t on ) {
	if( on ) {
#ifdef NO_SPLIT
		return;
#endif
		set_irq_ptr( Irq_game );
		asm volatile( "cli" );
	}
	else
		disable_irq();
}

void video_bike_bank( uint8_t bank ) {
	Irq_game[3] = bank;
}

void spr_text( uint8_t x, uint8_t y, const char* s ) {
	for( ; *s; s++, x += 8 ) {
		uint8_t c = (uint8_t)*s;
		if( c == ' ' || c < 32 || c > 127 )
			continue;
		oam_spr( x, y, Hud_font[c-32], 3 );
	}
}

static uint8_t digits( uint32_t* t, uint16_t unit ) {
	uint8_t n = 0;
	while( *t >= unit ) {
		*t -= unit;
		n++;
	}
	return n;
}

void format_time( uint32_t t, char* s ) {
	// Without dividing by numbers that need the library's long division:
	uint8_t min = digits( &t, 6000 );
	uint8_t sec = digits( &t, 100 );
	uint8_t hund = (uint8_t)t;
	if( min > 99 )
		min = 99;
	s[0] = '0'+min/10;
	s[1] = '0'+min % 10;
	s[2] = ':';
	s[3] = '0'+sec/10;
	s[4] = '0'+sec % 10;
	s[5] = ':';
	s[6] = '0'+hund/10;
	s[7] = '0'+hund % 10;
	s[8] = 0;
}
