#ifndef GBC_PHYSICS_MATH32_H
#define GBC_PHYSICS_MATH32_H
#include <stdint.h>
#ifdef __SDCC
#define MATH32_ABI __sdcccall(0)
#else
#define MATH32_ABI
#endif

/* Exact signed wide products and arithmetic shifts. Rounded forms add a
 * positive half unit before shifting, including for negative operands.
 * shift/e ranges are 1..16 except mulshift32, which also permits zero.
 * Only the final result is saturated to signed32, never to signed16.
 */
int32_t riding_kmul32(int32_t x,uint8_t m,uint8_t e) MATH32_ABI;
int32_t riding_mulq32(int32_t x,int16_t y,uint8_t shift) MATH32_ABI;
int32_t riding_mulshift32(int32_t x,int16_t y,uint8_t shift) MATH32_ABI;
int32_t riding_dotq32(int32_t a,int32_t b,int16_t c,int16_t d,uint8_t shift) MATH32_ABI;
#if defined(__SDCC) && defined(RIDING_COEFFICIENT_LOOKUP)
#include "physics_coefficient_calls.h"
#define KMUL32(x,c) riding_coeff32_##c((x))
#else
#define KMUL32(x,c) riding_kmul32((x),c##_M,c##_E)
#endif

typedef struct {
    int32_t relx[2],rely[2];
    int16_t kx[2],ky[2];
} riding_torque32_t;
/* Four complete products are summed before >>10 and intentional angular16
 * clamping. The 24-byte input layout is identical on host and SM83.
 */
int16_t riding_torque_input32(const riding_torque32_t *t) MATH32_ABI;
#endif
