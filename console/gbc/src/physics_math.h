// Fixed-point helpers: exact SM83 arithmetic kernels and independent host
// reference implementations for trajectory and integer-vector comparisons.
#ifndef GBC_PHYSICS_MATH_H
#define GBC_PHYSICS_MATH_H

#include <stdint.h>

#include "riding_constants.h"
#include "physics_q24.h"

// Arithmetic byte drop; native code moves register bytes instead of8 shifts.
#ifdef __SDCC
int32_t riding_sra8(int32_t x);
#else
#define riding_sra8(x) ((x)>>8)
#endif

// A double constant scaled by 2^sh, rounded; folded at compile time:
#define FX( c, sh ) ((int32_t)((c) * (double)(1L << (sh)) + ((c) < 0 ? -0.5 : 0.5)))

int16_t sat16(int32_t a);
#ifdef __SDCC
int32_t riding_mul16(int16_t a,int16_t b) __sdcccall(0);
#else
static inline int32_t riding_mul16(int16_t a,int16_t b) {return (int32_t)a*b;}
#endif
#define mul16(a,b) riding_mul16((a),(b))
int16_t mulhi(int16_t a,int16_t b);
int16_t mulq14(int16_t a,int16_t b);
int16_t mulq10(int16_t a,int16_t b);
int16_t dotq14(int16_t a,int16_t b,int16_t c,int16_t d);
#if defined(__SDCC) && defined(RIDING_COEFFICIENT_LOOKUP)
#include "physics_coefficient_calls.h"
#define KMUL(x,c) riding_coeff16_##c((x))
#else
#define KMUL(x,c) sat16(Q24_MUL((x),c))
#endif
#ifdef __SDCC
int16_t kmul(int16_t x,uint8_t m,uint8_t e) __sdcccall(0);
#else
int16_t kmul(int16_t x,uint8_t m,uint8_t e);
#endif

// Square root of a 32-bit number, rounded down:
uint16_t isqrt32( uint32_t a );
// Exact floor(sqrt(a)), for 0<=a<2^20. Rider and deep-contact lengths
// satisfy this tighter bound and avoid the general 32-bit square root.
#ifdef __SDCC
uint16_t riding_isqrt20(uint32_t a) __sdcccall(0);
#else
uint16_t riding_isqrt20(uint32_t a);
#endif

// Exact positive division when n/d fits uint16, d!=0. The rider ellipse
// uses it only with x,y>0, n<=RIDER_TOP^2 and d>RIDER_TOP.
#ifdef __SDCC
uint16_t riding_div_u32_u16(uint32_t n,uint16_t d) __sdcccall(0);
#else
uint16_t riding_div_u32_u16(uint32_t n,uint16_t d);
#endif

// (x << 14)/l and x*m/d, truncated:
int16_t div14( int16_t x, int16_t l );
int16_t muldiv( int16_t x, int16_t m, int16_t d );

// Sine and cosine of an angle (65536 is a full turn), 16384 is 1:
int16_t fsin( uint16_t a );
int16_t fcos( uint16_t a );

#endif
