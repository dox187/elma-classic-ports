// Elasto Mania for the NES: an MMC3 cartridge of 512 KB PRG-ROM, 256 KB
// CHR-ROM and 8 KB of battery backed PRG-RAM, of 128 and 128 KB for the
// shareware version (banks.h).
#include <mapper.h>
#include <neslib.h>
#include "banks.h"
#include "game.h"
#include "levels.h"
#include "menu.h"
#include "save.h"
#include "sound.h"

// The sizes of banks.h, expanded before the macros of the SDK quote them:
#define CART( prg, chr ) MAPPER_PRG_ROM_KB( prg ); MAPPER_CHR_ROM_KB( chr )
CART( PRG_ROM_KB, CHR_ROM_KB );
#ifdef PAL_BUILD
INES_TIMING_RP2C07;
#else
INES_TIMING_RP2C02;
#endif
MAPPER_PRG_NVRAM_KB( 8 );
MAPPER_USE_BATTERY;
MAPPER_USE_VERTICAL_MIRRORING;

int main( void ) {
	set_wram_mode( WRAM_ON );
	set_mirroring( MIRROR_VERTICAL );
	// Sprites from the second pattern table, which the MMC3 counts the
	// lines with:
	bank_spr( 1 );
	bank_bg( 0 );
	snd_init();
	save_load();
	for( ;; ) {
		banked_call( MENU_BANK, menu_title );
		for( ;; ) {
			banked_call( MENU_BANK, menu_levels );
			if( !Menu_choice )
				break;
			while( game_play() == GAME_WON ) {
				Menu_best = save_finish( Menu_level, Game_time );
				banked_call( MENU_BANK, menu_result );
				if( !Menu_choice )
					break;
			}
		}
	}
}
