#pragma bank 3
#include "physics_core.h"
#include "physics_angle_rows.h"

/* floor((omega*27007 + fraction + 640) / 1280), modulo 2^32.
 * Since 1280 = 5*256, the high-byte remainders are whole multiples of
 * 256. All four bytes share one floor operation, including negative spins. */
void riding_partial_angle(int16_t fraction) __banked {
    const uint8_t *w = (const uint8_t *)&Bike.body.omega;
    int16_t low = (int16_t)(fraction + 640 + (int16_t)low_remainder[w[0]]);
    uint8_t index = (uint8_t)((low >> 8) + 64 + high_remainder1[w[1]]
                               + high_remainder1[w[2]] + high_remainder3[w[3]]);
    Bike.body.alfa += whole0[w[0]] + whole1[w[1]] + whole2[w[2]] + whole3[w[3]]
                      + (uint32_t)(int32_t)carry_units[index];
}
