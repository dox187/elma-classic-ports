#ifdef __SDCC
#pragma bank 9
#include <stddef.h>
#include "physics_core.h"
#include "physics_math.h"
#include "physics_math32.h"
typedef char wheel_native_layout[sizeof(circle_t)==24 &&
    offsetof(circle_t,rx)==0 && offsetof(circle_t,ry)==4 &&
    offsetof(circle_t,vx)==8 && offsetof(circle_t,vy)==12 &&
    offsetof(circle_t,alfa)==16 && offsetof(circle_t,omega)==20 &&
    offsetof(bike_t,body)==0 && offsetof(bike_t,wheel)==24 &&
    ELSZ>=1 && ELSZ<=256?1:-1];
const uint8_t riding_supports_threshold=(uint8_t)(1-ELSZ);
int32_t riding_wheel_roll_t(int32_t x) __sdcccall(0) {return Q24_MUL(x,C_ROLL_T);}
int32_t riding_wheel_roll_dv(int32_t x) __sdcccall(0) {return Q24_MUL(x,C_ROLL_DV);}
int32_t riding_wheel_roll_w(int32_t x) __sdcccall(0) {return Q24_MUL(x,C_ROLL_W);}
#endif
