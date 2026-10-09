// Elasto Mania for the SNES: the menus and the levels, as the original game
// goes from one to the other (PLAY.CPP playlevel).
#include <snes.h>
#include "core.h"
#include "snd.h"
#include "ui.h"
#include "game.h"

int main(void) {
	s16 level;
	u16 r;
	u32 time;
	u8 finished;

	consoleInit();
	core_init();
	snd_init();
	game_keys_n = 0;
	ui_intro();
	while( 1 ) {
		ui_main_menu();
		while( 1 ) {
			level = ui_level_menu();
			if( level < 0 )
				break;
			while( 1 ) {
				time = game_play( (u16)level, &finished );
				r = ui_after_play( (u16)level, finished, time );
				if( r == UI_PLAY_NEXT )
					level++;
				else if( r != UI_PLAY_AGAIN )
					break;
			}
		}
	}
	return 0;
}
