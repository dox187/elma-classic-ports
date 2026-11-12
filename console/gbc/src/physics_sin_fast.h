#ifndef GBC_PHYSICS_SIN_FAST_H
#define GBC_PHYSICS_SIN_FAST_H
#include <stdint.h>

/* Exact existing Sintab interpolation: full turn 65536, amplitude 16384.
 * Near ROM0, stack ABI0. Requires generated banks 16..19 at 4000 and ROMB1=0.
 * CURRENT_BANK remains the logical caller; physical ROMB0 is restored.
 */
#ifdef __SDCC
int16_t riding_sin16(uint16_t angle) __sdcccall(0);
#else
int16_t riding_sin16(uint16_t angle);
#endif
#endif
