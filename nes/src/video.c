#include "video.h"
#include <mapper.h>
#include <neslib.h>
#include "chrmap.h"
#include "map.h"
#include "sprites.h"

// The sprites for the OAM DMA of neslib's NMI. Its DMA comes with its oam_
// functions, which are not used here: the reference below brings it in. The
// buffer is defined in assembly, as the page must be whole.
asm( ".section .aligned,\"aw\",@nobits\n"
	 ".globl OAM_BUF\n"
	 ".p2align 8\n"
	 "OAM_BUF:\n"
	 "\t.zero 256\n"
	 ".set oam_dma_of_neslib, oam_update_nmi\n" );
uint8_t Oam_n;
// The sprites of the last frame shown, hidden in the next if unused:
static uint8_t Oam_last;

// Run by the MMC3 IRQ system: at the NMI the background is off and the
// bike's sprites are switched in, after BAR_LINES lines the background is
// on.
__attribute__((used)) uint8_t Irq_game[] = {
	0xf1, 0x14,          // PPUMASK: sprites only
	0xf9, CHR_SPR_BIKE,  // CHR register 2: the bike's bank
	BAR_LINES-1,
	0xf1, 0x1e,          // PPUMASK: background and sprites
	0xff
};

// The bike's bank for the frame handed over, which the NMI puts into
// Irq_game as it shows the frame (between the sprites and the palette of
// neslib's NMI):
__attribute__((used)) uint8_t Bike_bank = CHR_SPR_BIKE;
asm( ".section .nmi.057,\"axR\",@progbits\n"
	 "\tlda Bike_bank\n"
	 "\tsta Irq_game+3\n" );

void sprites_off( void ) {
	for( uint8_t i = 0; i < 64; i++ )
		OAM_BUF[i*4] = 0xff;
	Oam_last = 0;
}

void frame_begin( void ) {
	Oam_n = 0;
	vram_begin();
}

void frame_show( void ) {
	uint8_t n = Oam_n;
	for( uint8_t i = n; i < Oam_last; i += 4 )
		OAM_BUF[i] = 0xff;
	Oam_last = n;
	vram_end();
	set_vram_update( Vram_buf );
	VRAM_UPDATE = 1;
}

void frame_end( void ) {
	frame_show();
	while( VRAM_UPDATE )
		;
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
	Bike_bank = bank;
}

void spr_text( uint8_t x, uint8_t y, const char* s ) {
	for( ; *s; s++, x += 8 ) {
		uint8_t c = (uint8_t)*s;
		if( c == ' ' || c < 32 || c > 127 )
			continue;
		spr( x, y, Hud_font[c-32], 3 );
	}
}

static uint8_t digits( uint32_t* t, uint16_t unit ) {
	uint8_t n = 0;
	while( *t >= unit ) {
		*t -= unit;
		n++;
		// Kept as a loop: as a division it would take the library's long
		// division.
		asm volatile( "" ::: "memory" );
	}
	return n;
}

void format_time( uint32_t t, char* s ) {
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
