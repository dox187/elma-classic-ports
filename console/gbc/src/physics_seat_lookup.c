#pragma bank 31
#include "physics_core.h"
#include "riding_constants.h"
#include "physics_seat_tables.h"

/* 0 leaves xy intact for the general solver. 1 certifies an unchanged
 * position. 2 supplies corrected seat coordinates for the world rotation. */
uint8_t riding_seat_lookup(int16_t *xy) __banked {
    int16_t x = Bike.turned ? -xy[0] : xy[0];
    int16_t y = xy[1];
    if (x < -512 || x >= 512 || (uint16_t)y >= 768) return 0;
    int16_t under = seat_row[y] - seat_column[x + 512];
    uint8_t moved = 1;
    if (under < 0) {
        uint16_t index = (uint16_t)~under;
        x += seat_push_x[index];
        y -= seat_push_y[index];
        moved = 2;
    }
    if (y > RIDER_TOP) { y = RIDER_TOP; moved = 2; }
    if (x < RIDER_LEFT) { x = RIDER_LEFT; moved = 2; }
    if (x > RIDER_RIGHT) { x = RIDER_RIGHT; moved = 2; }
    if (x > 0 && y > ellipse_height[x]) {
        if (y == RIDER_TOP) {
            y = ellipse_top_y[x];
            x = ellipse_top_x[x];
        } else {
            uint16_t offset = y - ellipse_height[x] - 1;
            if (offset >= 16) return 0;
            uint8_t delta = ellipse_edge[((uint16_t)x << 4) + offset];
            x -= delta >> 4;
            y -= delta & 15;
        }
        /* The original compares the square before taking the floor root.
         * Even a zero correction must rotate back and clear low position bits. */
        moved = 2;
    }
    if (moved == 2) { xy[0] = x; xy[1] = y; }
    return moved;
}
