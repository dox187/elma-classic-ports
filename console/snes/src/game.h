// Playing a level (game.c).
#ifndef GAME_H
#define GAME_H

#include <snes.h>

// Plays a level from the menus (in forced blank) until the flower, a crash
// or Start (the original's Esc). Returns the time in hundredths and sets
// *finished if the flower was reached; leaves the screen on.
u32 game_play(u16 level, u8* finished);

// A hook for the tests (test/snes_play.c): while game_keys_n is not 0, the
// keys of step i of the physics are game_keys[i] (the PH_* bits, and
// GAME_TURN to turn after the step, as T in test/physcases.txt) instead of
// the joypad's, so that a ride repeats whatever the frames take. The game
// sets game_keys_n to 0.
#define GAME_TURN 0x10
extern u8* game_keys;
extern u16 game_keys_n;
// Diagnostics: steps are never discarded; backlog is retained for the
// next frame. max is measured in the accumulator's 1/fps step units.
extern u16 game_phys_drop_count, game_phys_backlog_count, game_phys_backlog_max;

#endif
