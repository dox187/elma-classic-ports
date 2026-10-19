/*
 * Deterministic test signal shared by the host test and the PS1 sound test:
 * two triangle waves and a little noise, integer arithmetic only, so the
 * encoded stream is identical on the PC and on the PS1.
 */

#ifndef SOUND_SIGNAL_H
#define SOUND_SIGNAL_H

#include <stdint.h>

static inline int16_t sound_signal(uint32_t n)
{
	const int32_t a = (int32_t)(n % 100);
	const int32_t b = (int32_t)(n % 37);
	const int32_t tri_a = (a < 50 ? a : 100 - a) * 360 - 9000;
	const int32_t tri_b = (b < 19 ? b : 37 - b) * 440 - 4000;
	uint32_t x = n * 2654435761u;
	x ^= x >> 15;
	const int32_t noise = (int32_t)(x & 511) - 256;
	return (int16_t)(tri_a + tri_b + noise);
}

#endif
