#ifndef PHYSICS_Q24_H
#define PHYSICS_Q24_H
#include <stdint.h>
extern int32_t q24_fraction;
extern uint8_t q24_saturated;
#ifdef __SDCC
#include "physics_q24_coefficients.h"
#define Q24_MUL(x,c) q24_apply((x),q24_index_##c[riding_subphase])
#else
int32_t q24_hostmul(int32_t value,int32_t coefficient);
#define q24_apply(x,c) q24_hostmul((x),(c))
#define Q24_MUL(x,c) q24_hostmul((x),q24_##c[riding_subphase])
#define Q24_ANCHOR_X 228170138L
#define Q24_ANCHOR_Y 161061274L
#endif
#endif
