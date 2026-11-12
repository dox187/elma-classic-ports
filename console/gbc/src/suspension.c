/* LEPTET.CPP erokszamitasa: Drsugar == Drtang makes the spring isotropic.
 * Compute K*displacement and Sr*relative_v directly, retaining both original
 * body torques. Drive torque reactions, collision, rider and integration are
 * deliberately outside this first measured kernel.
 */
#include "suspension.h"
#include "physics_constants.h"
#include "mul16.h"

static int16_t clamp16(int32_t x) {
    if (x > 32767) return 32767;
    if (x < -32768L) return -32768;
    return (int16_t)x;
}

static int16_t scale(int16_t x, int16_t factor) {
    return clamp16((gbc_mul16(x, factor) + 2048) >> 12);
}

static int32_t cross(int16_t x, int16_t y, int16_t fx, int16_t fy) {
    return (gbc_mul16(x, fy) - gbc_mul16(y, fx)) >> 10;
}

void suspension_impulses(const suspension_input_t *axles, suspension_output_t *out) {
    uint8_t i;
    int16_t sx, sy, fx, fy;
    int32_t body_x = 0, body_y = 0, torque = 0;
    for (i = 0; i < 2; ++i, ++axles) {
        sx = scale(axles->dx, SPRING_W);
        sy = scale(axles->dy, SPRING_W);
        fx = scale(axles->relative_vx, DAMPING_W);
        fy = scale(axles->relative_vy, DAMPING_W);
        out->wheel_dvx[i] = clamp16((int32_t)sx + fx);
        out->wheel_dvy[i] = clamp16((int32_t)sy + fy);
        body_x -= scale(axles->dx, SPRING_B) + scale(axles->relative_vx, DAMPING_B);
        body_y -= scale(axles->dy, SPRING_B) + scale(axles->relative_vy, DAMPING_B);
        torque -= cross(axles->rest_x, axles->rest_y, sx, sy);
        torque -= cross(axles->rest_x - axles->dx, axles->rest_y - axles->dy, fx, fy);
    }
    out->body_dvx = clamp16(body_x);
    out->body_dvy = clamp16(body_y);
    out->body_domega = clamp16((torque * WHEEL_MASS_OVER_INERTIA + 2048) >> 12);
}
