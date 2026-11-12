#ifndef GBC_RUNTIME_H
#define GBC_RUNTIME_H
#include <stdint.h>
#ifdef __SDCC
#include <gb/gb.h>
#define GBC_BANKED BANKED
#else
#define GBC_BANKED
#endif

/* Original world: Q16.16 meters, Y up. One full turn is 65536 units. */
typedef struct { int32_t x, y; uint16_t angle; } gbc_pose_t;
typedef struct {
    gbc_pose_t body, wheel[2], rider, head;
    uint8_t alive, turned;
} gbc_bike_t;
extern gbc_bike_t gbc_bike;

#define GBC_GAS 1
#define GBC_BRAKE 2
#define GBC_ROTATE_LEFT 4
#define GBC_ROTATE_RIGHT 8

void physics_reset(int32_t start_x, int32_t start_y) GBC_BANKED;
void physics_step(uint8_t input) GBC_BANKED;
void physics_turn(void) GBC_BANKED;
uint8_t physics_select_level(uint8_t index) GBC_BANKED;
void physics_reset_current(void) GBC_BANKED;
void physics_set_gravity(uint8_t resource_direction) GBC_BANKED;
extern int32_t physics_level_start_x,physics_level_start_y;
extern int32_t physics_level_origin_x,physics_level_origin_y;
extern uint8_t physics_level_index;
#endif
