#pragma bank 1
#include "physics_core.h"
#include "physics_sin_fast.h"

typedef struct { uint8_t hx, hy; uint16_t rest, ax, ay; } pose_row_t;
typedef struct { int16_t hx, hy, rest; int32_t ax, ay; } pose_values_t;
typedef struct { const pose_row_t *row; const pose_values_t *base; } pose_page_t;
#include "physics_pose_rows.h"

int32_t riding_pose_anchor[4];
int16_t riding_pose_rest[2];
pose_values_t riding_pose_cosine, riding_pose_sine;
int16_t riding_pose_trig[2];
extern uint16_t riding_pose_phase;
void riding_scaled_trig(int16_t trig, pose_values_t *out) __sdcccall(0);

void riding_refresh_geometry(void) __banked {
    int16_t cs = riding_sin16(riding_pose_phase + 16384u);
    int16_t sn = riding_sin16(riding_pose_phase);
    riding_pose_trig[0] = cs;
    riding_pose_trig[1] = sn;
    riding_scaled_trig(cs, &riding_pose_cosine);
    riding_scaled_trig(sn, &riding_pose_sine);
    riding_pose_rest[0] = -riding_pose_sine.rest;
    riding_pose_rest[1] = riding_pose_cosine.rest;
    riding_pose_anchor[0] = riding_pose_sine.ay - riding_pose_cosine.ax;
    riding_pose_anchor[1] = riding_pose_sine.ay + riding_pose_cosine.ax;
    riding_pose_anchor[2] = -riding_pose_sine.ax - riding_pose_cosine.ay;
    riding_pose_anchor[3] = riding_pose_sine.ax - riding_pose_cosine.ay;
}
