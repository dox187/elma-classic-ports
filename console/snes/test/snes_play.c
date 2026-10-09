// The test ROM of a whole level: plays the level play_level as the game
// does (game_play), without the menus, so that a script of buttons
// (test/play.py) starts at the first frame of the level. It waits for
// play_go to become $5AA5 (RAM starts at random), then plays; the results
// go to play_done, play_finished and play_time. With play_keys_n set, the
// keys of the steps of the physics come from play_keys (game_keys of
// game.h) instead of the joypad.
#include <snes.h>
#include "core.h"
#include "snd.h"
#include "save.h"
#include "game.h"

volatile u16 play_go, play_level, play_done, play_finished, play_keys_n;
volatile u32 play_time;
u8 play_keys[16384];

int main(void) {
	u8 finished;
	consoleInit();
	core_init();
	snd_init();
	save_load();
	play_done = 0;
	while( play_go != 0x5AA5 )
		core_frame_done();
	game_keys = play_keys;
	game_keys_n = play_keys_n;
	play_time = game_play( play_level, &finished );
	play_finished = finished;
	play_done = 1;
	while( 1 )
		core_frame_done();
	return 0;
}
