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
    riding_audio_contact[0]=riding_audio_contact[1]=0;
    riding_audio_impact[0]=riding_audio_impact[1]=0;
#if defined(RIDING_PC_SCHEDULE)
    riding_subphase=0;
#endif
    ph_init((x-physics_level_origin_x)*4L,(y-physics_level_origin_y)*4L);
    gbc_bike.alive=1;export_state();
}

#if defined(RIDING_PC_SCHEDULE)
#ifdef __SDCC
#include <stddef.h>
typedef char bounds_descriptor_layout[offsetof(physics_level_desc_t,grid_exit_x)==24 &&
    offsetof(physics_level_desc_t,brush_y1)==44 ? 1 : -1];
uint8_t wheels_in_grid(void);
uint8_t head_body_in_level(void);
#else
#define BEFORE(a,b) ((a)<(b))

static uint8_t wheels_in_grid(void) {
    return BEFORE(Bike.wheel[0].rx,riding_level.grid_exit_x)
        && BEFORE(Bike.wheel[0].ry,riding_level.grid_exit_y)
        && BEFORE(Bike.wheel[1].rx,riding_level.grid_exit_x)
        && BEFORE(Bike.wheel[1].ry,riding_level.grid_exit_y);
}

static uint8_t head_body_in_level(void) {
    return BEFORE(Bike.head_x,riding_level.grid_exit_x) && BEFORE(Bike.head_y,riding_level.grid_exit_y)
        && !BEFORE(Bike.body.rx,riding_level.brush_x0) && BEFORE(Bike.body.rx,riding_level.brush_x1)
        && !BEFORE(Bike.body.ry,riding_level.brush_y0) && BEFORE(Bike.body.ry,riding_level.brush_y1);
}
#endif
#endif

void physics_step(uint8_t input) GBC_BANKED {
    uint8_t in=0;
    if(!gbc_bike.alive)return;
    if(input&GBC_GAS)in|=IN_GAS;
    if(input&GBC_BRAKE)in|=IN_BRAKE;
    if(input&GBC_ROTATE_LEFT)in|=IN_VOLT_LEFT;
    if(input&GBC_ROTATE_RIGHT)in|=IN_VOLT_RIGHT;
#if defined(RIDING_PC_SCHEDULE)
    /* LEJATSZO caps each integration interval at .0055 model seconds.
     * Gas/brake stay held; the accepted volt is a single impulse. Keep
     * impacts from every interval for the once-per-frame audio observer. */
    uint8_t impact0=0,impact1=0;
    for(uint8_t sub=0;sub<3;++sub) {
        riding_subphase=(sub==2);
        /* BEALLIT queries the wheels before moving them. VIZSGALAT checks
         * the resulting head in that same grid and the body against the
         * original 640x480 brush. Finish the interval even on a grid exit. */
        uint8_t wheels_inside=wheels_in_grid();
        gbc_bike.alive=ph_step(in) && wheels_inside && head_body_in_level();
        impact0|=riding_audio_impact[0];
        impact1|=riding_audio_impact[1];
        if(!gbc_bike.alive)break;
        in&=IN_GAS|IN_BRAKE;
    }
    riding_audio_impact[0]=impact0;riding_audio_impact[1]=impact1;
#else
    gbc_bike.alive=ph_step(in);
#endif
    export_state();
}

void physics_turn(void) GBC_BANKED {
    ph_turn();export_state();
}

uint8_t physics_select_level(uint8_t index) GBC_BANKED {
#ifdef __SDCC
    riding_spring_ready=0;
#endif
    return physics_collision_select(index);
}

void physics_reset_current(void) GBC_BANKED {
    if(physics_level_index==255)physics_collision_select(0);
    physics_reset(physics_level_start_x,physics_level_start_y);
}

void physics_set_gravity(uint8_t resource_direction) GBC_BANKED {
    if(resource_direction>=1 && resource_direction<=4)Bike.gravity=resource_direction-1;
}
