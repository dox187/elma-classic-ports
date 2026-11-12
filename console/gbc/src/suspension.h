#ifndef GBC_SUSPENSION_H
#define GBC_SUSPENSION_H
#include <stdint.h>

/* Diagnostic kernel, not a complete bike integrator. Local vectors/velocities
 * use Q10 meters / m/s. Inputs must be bounded to +/- 8 m and +/- 8 m/s.
 * rest is the rotated original axle anchor, displacement = rest-current,
 * relative_v includes the body's angular velocity at the CURRENT axle.
 * No world-coordinate truncation is needed: subtract 32-bit positions first.
 */
typedef struct {
    int16_t rest_x, rest_y, dx, dy, relative_vx, relative_vy;
} suspension_input_t;

typedef struct {
    int16_t wheel_dvx[2], wheel_dvy[2];
    int16_t body_dvx, body_dvy, body_domega;
} suspension_output_t;

void suspension_impulses(const suspension_input_t *axles, suspension_output_t *out);
#endif
