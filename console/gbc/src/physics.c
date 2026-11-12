/* Platform state export for the complete original-derived fixed-point core. */
#include "runtime.h"
#include "physics_core.h"
#include "riding_level.h"
#ifdef __SDCC
#pragma bank 8
const uint8_t physics_export_angle_shift=RIDING_ANGLE_SHIFT;
#endif

gbc_bike_t gbc_bike;
void physics_collision_reset(void);
uint8_t physics_collision_select(uint8_t index);

#ifdef __SDCC
void physics_export_state_fast(void);
#define export_state physics_export_state_fast
#else
static void pose(gbc_pose_t *p,const circle_t *c) {
    p->x=(c->rx>>2)+physics_level_origin_x;
    p->y=(c->ry>>2)+physics_level_origin_y;
    p->angle=(uint16_t)(c->alfa>>RIDING_ANGLE_SHIFT);
}

static void export_state(void) {
    int32_t rider_x=Bike.rider_x,rider_y=Bike.rider_y;
    if(Bike.steps&1){rider_x-=Bike.rider_vx*4L;rider_y-=Bike.rider_vy*4L;}
    pose(&gbc_bike.body,&Bike.body);
    pose(&gbc_bike.wheel[0],&Bike.wheel[0]);
    pose(&gbc_bike.wheel[1],&Bike.wheel[1]);
    gbc_bike.rider.x=(rider_x>>2)+physics_level_origin_x;
    gbc_bike.rider.y=(rider_y>>2)+physics_level_origin_y;
    gbc_bike.rider.angle=gbc_bike.body.angle;
    gbc_bike.head.x=(Bike.head_x>>2)+physics_level_origin_x;
    gbc_bike.head.y=(Bike.head_y>>2)+physics_level_origin_y;
    gbc_bike.head.angle=gbc_bike.body.angle;
    gbc_bike.turned=Bike.turned;
}

#endif

void physics_reset(int32_t x,int32_t y) GBC_BANKED {
    if(physics_level_index==255)physics_collision_select(0);
    physics_collision_reset();
    ph_init((x-physics_level_origin_x)*4L,(y-physics_level_origin_y)*4L);
    gbc_bike.alive=1;export_state();
}

void physics_step(uint8_t input) GBC_BANKED {
    uint8_t in=0;
    if(!gbc_bike.alive)return;
    if(input&GBC_GAS)in|=IN_GAS;
    if(input&GBC_BRAKE)in|=IN_BRAKE;
    if(input&GBC_ROTATE_LEFT)in|=IN_VOLT_LEFT;
    if(input&GBC_ROTATE_RIGHT)in|=IN_VOLT_RIGHT;
    gbc_bike.alive=ph_step(in);export_state();
}

void physics_turn(void) GBC_BANKED {
    ph_turn();export_state();
}

uint8_t physics_select_level(uint8_t index) GBC_BANKED {
    return physics_collision_select(index);
}

void physics_reset_current(void) GBC_BANKED {
    if(physics_level_index==255)physics_collision_select(0);
    physics_reset(physics_level_start_x,physics_level_start_y);
}

void physics_set_gravity(uint8_t resource_direction) GBC_BANKED {
    if(resource_direction>=1 && resource_direction<=4)Bike.gravity=resource_direction-1;
}
