// Sounds on the APU: the engine on the first pulse channel, effects on the
// second and on the noise channel.
#ifndef SOUND_H
#define SOUND_H

#include <stdint.h>

void snd_init( void );
// Called every step, with the gas and the angular velocity of the driven
// (rear) wheel: the engine sounds only with the gas, its pitch set by the
// wheel alone.
void snd_engine( uint8_t gas, int16_t omega );
void snd_apple( void );
void snd_volt( void );
void snd_turn( void );
void snd_death( void );
void snd_win( void );

#endif
