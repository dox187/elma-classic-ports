#ifndef GAME_H
#define GAME_H

#include <stdint.h>

enum { GAME_QUIT, GAME_WON };

// The time of the last finished level, in hundredths:
extern uint32_t Game_time;

// Plays Level until it is finished or left.
uint8_t game_play( void );

#endif
