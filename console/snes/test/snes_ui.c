// Test ROM of the menus and the saving: the flow of the game (ui.h) with a
// stand-in for the levels. A "level" is a dark blue screen: A finishes it
// in the time of 12.34 s plus 1 s for each X pressed before, Start or B
// ends it unfinished (the original's Esc, or a crash).
#include <snes.h>
#include "core.h"
#include "ui.h"
#include "save.h"

#define REG(a) (*(vuint8*)(a))

u16 test_level;                 // the level played (PEEK)
u16 test_result;                // the last result of ui_after_play
u16 test_plays;                 // levels played

static const u8 level_pal[2] = { 0x00, 0x28 };

// The stand-in of a level: returns 1 if finished, the time in *hs.
static u8 play(u16 level, u32* hs) {
	u16 p;
	u32 t = 1234;
	test_level = level;
	test_plays++;
	core_screen_off();
	core_cgram_now(0, level_pal, 2);
	REG(0x212C) = 0;
	core_screen_on(15);
	core_pad_take();
	while( 1 ) {
		core_frame_done();
		p = core_pad_take();
		if( p & JOY_X )
			t += 100;
		if( p & JOY_A ) {
			*hs = t;
			break;
		}
		if( p & (JOY_START | JOY_B) ) {
			*hs = 0;
			break;
		}
	}
	core_screen_off();
	ui_invalidate();
	return *hs != 0;
}

int main(void) {
	s16 level;
	u32 hs;
	u8 fin;
	consoleInit();
	core_init();
	ui_intro();
	while( 1 ) {
		ui_main_menu();
		while( (level = ui_level_menu()) >= 0 ) {
			while( 1 ) {
				fin = play(level, &hs);
				test_result = ui_after_play(level, fin, hs);
				if( test_result == UI_PLAY_NEXT )
					level++;
				else if( test_result != UI_PLAY_AGAIN )
					break;
			}
		}
	}
	return 0;
}
