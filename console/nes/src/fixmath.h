// Fixed point helpers of the physics, shared by the NES build (where they
// are written in assembly, mul.s) and the tests on the host.
#ifndef FIXMATH_H
#define FIXMATH_H

#include <stdint.h>

// A double constant scaled by 2^sh, rounded; folded at compile time:
#define FX( c, sh ) ((int32_t)((c) * (double)(1L << (sh)) + ((c) < 0 ? -0.5 : 0.5)))

static inline int16_t sat16( int32_t a ) {
	if( a > 32767 ) return 32767;
	if( a < -32768 ) return -32768;
	return (int16_t)a;
}

#ifdef __mos__
int32_t mul16( int16_t a, int16_t b );
// a*b/65536, rounded:
int16_t mulhi( int16_t a, int16_t b );
// a*b/16384 and a*b/1024, rounded and saturated:
int16_t mulq14( int16_t a, int16_t b );
int16_t mulq10( int16_t a, int16_t b );
// (ax*bx + ay*by)/16384, rounded and saturated:
int16_t dotq14( int16_t ax, int16_t ay, int16_t bx, int16_t by );
#else
static inline int32_t mul16( int16_t a, int16_t b ) { return (int32_t)a*b; }
static inline int16_t mulhi( int16_t a, int16_t b ) {
	return (int16_t)(((int32_t)a*b + 0x8000) >> 16);
}
static inline int16_t mulq14( int16_t a, int16_t b ) {
	return sat16( ((int32_t)a*b + 0x2000) >> 14 );
}
static inline int16_t mulq10( int16_t a, int16_t b ) {
	return sat16( ((int32_t)a*b + 0x200) >> 10 );
}
static inline int16_t dotq14( int16_t ax, int16_t ay, int16_t bx, int16_t by ) {
	return sat16( ((int32_t)ax*bx + (int32_t)ay*by + 0x2000) >> 14 );
}
#endif

// x times a constant c given as m/2^e (m of 8 bits, e from 1 to 16, see
// physconst.h), rounded and saturated:
#define KMUL( x, c ) kmul( (x), c##_M, c##_E )
static inline int16_t kmul( int16_t x, uint8_t m, uint8_t e ) {
	return sat16( ((int32_t)x*m + (1L << (e-1))) >> e );
}

// Square root of a 32-bit number, rounded down:
uint16_t isqrt32( uint32_t a );

// (x << 14)/l and x*m/d, truncated:
int16_t div14( int16_t x, int16_t l );
int16_t muldiv( int16_t x, int16_t m, int16_t d );

// Sine and cosine of an angle (65536 is a full turn), 16384 is 1:
int16_t fsin( uint16_t a );
int16_t fcos( uint16_t a );

#endif
