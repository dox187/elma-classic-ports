#pragma bank 1
#include <stdint.h>

typedef struct { uint8_t hx, hy; } pose_head_row_t;
typedef struct { uint8_t rest, neg_rest; uint16_t ax, ay, neg_ay; } pose_suspension_row_t;
typedef struct {
    const pose_head_row_t *head;
    const pose_suspension_row_t *suspension;
    int16_t hx, hy, rest;
    uint16_t ax_lo;
    int8_t ax_hi;
    uint16_t ay_lo;
    int8_t ay_hi;
} pose_page_t;
#include "physics_pose_rows.h"

int32_t riding_pose_anchor[4];
int16_t riding_pose_rest[2], riding_pose_trig[2];
