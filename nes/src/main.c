// Elasto Mania for the NES: an MMC3 cartridge of 512 KB PRG-ROM, 256 KB
// CHR-ROM and 8 KB of battery backed PRG-RAM.
#include <mapper.h>
#include <neslib.h>
#include "banks.h"
#include "game.h"
#include "levels.h"
#include "menu.h"
#include "save.h"
#include "sound.h"

MAPPER_PRG_ROM_KB( 512 );
MAPPER_CHR_ROM_KB( 256 );
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
