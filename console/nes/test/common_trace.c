// Host hooks for the NES trace adapter. Use the ROM's segment decoder
// with the converted level data in a flat address space.
#include "far.h"
#include "physics.h"
#include "segs.h"

static const uint8_t* Level_data;
static uint16_t Map_w, Map_h;
static uint8_t Volt_wait;

const uint8_t* far_ptr(uint32_t address) {
    return Level_data + address;
}

void trace_start(const uint8_t* data, uint32_t rows, uint32_t grid,
                 uint8_t gw, uint8_t gh, uint16_t w, uint16_t h,
                 int32_t sx, int32_t sy) {
    const level_t level = {
        .segments = 0, .grid_rows = rows, .grid = grid, .gw = gw, .gh = gh,
    };
    Level_data = data;
    Map_w = w;
    Map_h = h;
    Volt_wait = 0;
    segs_start(&level);
    ph_init(sx * 256, sy * 256);
}

uint8_t trace_step(uint8_t mask) {
    uint8_t input = mask & (IN_GAS | IN_BRAKE);
    // Mirror game.c's held-pad repeat and left priority.
    if (Volt_wait)
        Volt_wait--;
    else if (mask & 12) {
        input |= (mask & 4) ? IN_VOLT_LEFT : IN_VOLT_RIGHT;
        Volt_wait = (uint8_t)(0.4 / PH_H + 0.5);
    }
    return ph_step(input) && Bike.body.rx >= 0 && Bike.body.ry >= 0 &&
           (Bike.body.rx >> 14) < Map_w && (Bike.body.ry >> 14) < Map_h;
}

void trace_state(int32_t* state) {
    state[0] = Bike.body.rx;
    state[1] = Bike.body.ry;
    state[2] = (int32_t)Bike.body.alfa;
    state[3] = Bike.wheel[0].rx >> 8;
    state[4] = Bike.wheel[0].ry >> 8;
    state[5] = Bike.wheel[1].rx >> 8;
    state[6] = Bike.wheel[1].ry >> 8;
    state[7] = Bike.head_x >> 8;
    state[8] = Bike.head_y >> 8;
}

void trace_gravity(uint8_t gravity) {
    static const uint8_t direction[] = {GRAV_UP, GRAV_DOWN, GRAV_LEFT, GRAV_RIGHT};
    if (gravity >= 1 && gravity <= 4)
        Bike.gravity = direction[gravity - 1];
}
