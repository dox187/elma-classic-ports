// Playing a level (game.c).
#ifndef GAME_H
#define GAME_H

#include <snes.h>

// Plays a level from the menus (in forced blank) until the flower, a crash
// or Start (the original's Esc). Returns the time in hundredths and sets
// *finished if the flower was reached; leaves the screen on.
u32 game_play(u16 level, u8* finished);

#endif
