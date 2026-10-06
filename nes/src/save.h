// Best times and finished levels, kept in the battery backed PRG-RAM.
#ifndef SAVE_H
#define SAVE_H

#include <stdint.h>

#define NO_TIME 0xffffffu

void save_load( void );
// Best time of a level in hundredths, NO_TIME if not finished:
uint32_t save_best( uint8_t level );
uint8_t save_done( uint8_t level );
// Records a finished level; true if it is a new best time.
uint8_t save_finish( uint8_t level, uint32_t time );
// Levels that may be played: the finished ones and the next one.
uint8_t save_open( uint8_t level );

#endif
