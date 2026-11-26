#pragma bank 1
#include <stdint.h>

typedef uint8_t pose_hot_row_t[8];
typedef struct {
    const uint8_t *head;
    const uint8_t *suspension;
    int16_t hx, hy, rest;
    uint16_t ax_lo;
    int8_t ax_hi;
    uint16_t ay_lo;
    int8_t ay_hi;
} pose_page_t;
#include "physics_pose_rows.h"

int32_t riding_pose_anchor[4];
int16_t riding_pose_rest[2], riding_pose_trig[2];
