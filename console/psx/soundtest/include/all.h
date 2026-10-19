/* Minimal stand-in for the game's all.h, so that src/sound/psx_sound.cpp can
 * be built and tested without the game core. */
#ifndef SOUNDTEST_ALL_H
#define SOUNDTEST_ALL_H

#include <stddef.h>

extern int Hangenabled;
extern int Mute;
void hiba(char* text, const char* more = 0);

#endif
