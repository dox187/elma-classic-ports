#ifndef GBC_PHYSICS_FORCE_H
#define GBC_PHYSICS_FORCE_H
#include <stdint.h>

#ifdef __SDCC
#define RIDING_FORCE_CALL __sdcccall(0)
#else
#define RIDING_FORCE_CALL
#endif

/* Accumulate complete Q24 forces without repeating 64-bit shifts.
 * Each axis receives at most six signed32 unit terms, with at most four
 * nonzero fractions in [-2^23,2^23). Finish rounds ties toward positive
 * infinity and keeps the exact residual in [-10*2^24,10*2^24). */
void riding_force_begin(void) RIDING_FORCE_CALL;
void riding_force_sub(uint8_t axis,int32_t units,int32_t fraction) RIDING_FORCE_CALL;
int32_t riding_force_finish(uint8_t axis) RIDING_FORCE_CALL;
#undef RIDING_FORCE_CALL
#endif
