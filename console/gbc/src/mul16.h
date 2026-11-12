#ifndef GBC_MUL16_H
#define GBC_MUL16_H
#include <stdint.h>
#ifdef __SDCC
int32_t gbc_mul16(int16_t a, int16_t b) __sdcccall(0);
#else
static inline int32_t gbc_mul16(int16_t a, int16_t b) { return (int32_t)a*b; }
#endif
#endif
