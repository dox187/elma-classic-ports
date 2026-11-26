#pragma bank 31
#include "physics_core.h"
#include "physics_math.h"
#include "physics_seat_tables.h"

/* A signed high-byte base includes the seat origin and half-unit bias.
 * The discarded fractions carry exactly when the low byte's rank exceeds
 * this high byte's cutoff. All sums below intentionally narrow to int16. */
#define PRODUCT(kind, axis, high, low) (kind##_base_##axis[high] + whole_##axis[low] \
        + (rank_##axis[low] > kind##_cut_##axis[high]))

static uint16_t ellipse_coordinate(uint16_t n, uint16_t scale, uint16_t bias) {
    /* The unsigned scale represents a negative signed16 coefficient. Adding
     * n to the high word restores the unsigned product, including bias carry. */
    return n + (int16_t)((mul16(n, (int16_t)scale) + bias) >> 16);
}

/* 1 preserves the original position (including its fractional bits).
 * 2 supplies both seat coordinates for rotation back into world space. */
uint8_t riding_seat_general(int16_t *xy) {
    int16_t x = Bike.turned ? -xy[0] : xy[0], y = xy[1];
    uint8_t moved = 1;
    if ((uint16_t)(x - RIDER_LEFT) > RIDING_SEAT_FAST_X - RIDER_LEFT ||
            y < RIDING_SEAT_FAST_Y) {
        uint8_t xl = x, xh = (uint16_t)x >> 8;
        uint8_t yl = y, yh = (uint16_t)y >> 8;
        int16_t under = PRODUCT(seat,y,yh,yl) - PRODUCT(seat,x,xh,xl);
        if (under < 0) {
            uint8_t low = under, high = ((uint16_t)under >> 8) - 128;
            x += PRODUCT(push,x,high,low);
            y -= PRODUCT(push,y,high,low);
            moved = 2;
        }
        if (x < RIDER_LEFT) { x = RIDER_LEFT; moved = 2; }
        if (x > RIDER_RIGHT) { x = RIDER_RIGHT; moved = 2; }
    }
    if (y > RIDER_TOP) { y = RIDER_TOP; moved = 2; }
    if (x > 0 && y > (int16_t)ellipse_height[x]) {
        if (y == RIDER_TOP) {
            y = 256 + ellipse_top_y[x];
            x = ellipse_top_x[x];
        } else {
            uint32_t square = mul16(y,y) + ellipse_square_low[x] +
                    ((uint32_t)ellipse_square_high[x] << 16);
            uint16_t bin = (uint16_t)(square >> 8) - ELLIPSE_FIRST_BIN;
            uint8_t excess = ellipse_root[bin] + ((uint8_t)square > ellipse_cut[bin]);
            if (excess) {
                uint16_t scale = ellipse_scale[excess-1], bias = ellipse_bias[excess-1];
                x = ellipse_coordinate(x, scale, bias);
                y = ellipse_coordinate(y, scale, bias);
            }
        }
        /* A square outside the circle can still have a floor root of
         * RIDER_TOP. Re-rotation must clear its sub-coordinate position. */
        moved = 2;
    }
    if (moved == 2) { xy[0] = x; xy[1] = y; }
    return moved;
}

/* In the frequently reached upper part of the seat, the generated bounds
 * prove positive seat clearance. Only the top plane and ellipse can move the
 * rider. Keep both coordinates in registers through either comparison. */
uint8_t riding_seat_lookup(int16_t *xy) __banked __naked {
    xy;
    __asm
    ldhl sp,#6
    ld a,(hl+)
    ld h,(hl)
    ld l,a
    ld a,(hl+)
    ld c,a
    ld a,(hl+)
    ld b,a
    ld a,(hl+)
    ld e,a
    ld d,(hl)
    bit 7,d
    jr nz,seat_general$
    ld a,d
    cp #>RIDING_SEAT_FAST_Y
    jr c,seat_general$
    jr nz,seat_upper$
    ld a,e
    cp #<RIDING_SEAT_FAST_Y
    jr c,seat_general$
seat_upper$:
    ld a,(#(_Bike+96))
    or a
    jr z,seat_oriented$
    xor a
    sub c
    ld c,a
    sbc a,a
    sub b
    ld b,a
seat_oriented$:
    ld a,b
    or a
    jr z,seat_forward$
    cp #0xfe
    jr c,seat_general$
seat_rear$:
    ld a,#<RIDER_TOP
    cp e
    ld a,#>RIDER_TOP
    sbc d
    jr nc,seat_unchanged$
    ld de,#RIDER_TOP
    jr seat_store$
seat_general$:
    ldhl sp,#6
    ld a,(hl+)
    ld e,a
    ld d,(hl)
    jp _riding_seat_general
seat_unchanged$:
    ld a,#1
    ret
seat_forward$:
    ld a,c
    or a
    jr z,seat_rear$
    cp #(RIDING_SEAT_FAST_X + 1)
    jr nc,seat_general$
    ld a,e
    sub #<RIDER_TOP
    ld a,d
    sbc #>RIDER_TOP
    jr nc,seat_top$
    ld hl,#_upper_height
    add hl,bc
    ld a,e
    sub (hl)
    jr c,seat_unchanged$
    jr z,seat_unchanged$
    dec a
    cp #8
    jr nc,seat_general$
    ld h,b
    ld l,c
    add hl,hl
    add hl,hl
    add hl,hl
    add a,l
    ld l,a
    jr nc,seat_edge$
    inc h
seat_edge$:
    push de
    ld de,#_upper_edge
    add hl,de
    pop de
    ld a,(hl)
    and #15
    ld b,a
    ld a,e
    sub b
    ld e,a
    ld a,d
    sbc #0
    ld d,a
    ld a,(hl)
    swap a
    and #15
    ld b,a
    ld a,c
    sub b
    ld c,a
    ld b,#0
    jr seat_store$
seat_top$:
    ld hl,#_ellipse_top_y
    add hl,bc
    ld e,(hl)
    ld d,#1
    ld hl,#_ellipse_top_x
    add hl,bc
    ld c,(hl)
seat_store$:
    ldhl sp,#6
    ld a,(hl+)
    ld h,(hl)
    ld l,a
    ld (hl),c
    inc hl
    ld (hl),b
    inc hl
    ld (hl),e
    inc hl
    ld (hl),d
    ld a,#2
    ret
    __endasm;
}
