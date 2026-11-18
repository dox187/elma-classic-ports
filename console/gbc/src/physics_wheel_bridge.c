#ifdef __SDCC
#pragma bank 9
#include <stddef.h>
#include "physics_core.h"
#include "physics_math.h"
#include "physics_math32.h"
typedef char wheel_native_layout[sizeof(circle_t)==22 && offsetof(circle_t,vx)==8 && offsetof(circle_t,vy)==12 && offsetof(circle_t,omega)==20 && ELSZ>=1 && ELSZ<=256?1:-1];
const uint8_t riding_supports_threshold=(uint8_t)(1-ELSZ);
int16_t riding_wheel_free_coeff(int16_t x) __sdcccall(0) {return KMUL(x,C_FREE);}
int32_t riding_wheel_roll_t(int32_t x) __sdcccall(0) {return Q24_MUL(x,C_ROLL_T);}
int32_t riding_wheel_roll_dv(int32_t x) __sdcccall(0) {return Q24_MUL(x,C_ROLL_DV);}
int32_t riding_wheel_roll_w(int32_t x) __sdcccall(0) {return Q24_MUL(x,C_ROLL_W);}
void riding_wheel_move(circle_t *k) __sdcccall(0) {
 k->alfa+=phase_move(k->omega,7);
 k->rx+=phase_advance(k->vx,2,k==&Bike.body?0:k==&Bike.wheel[0]?2:4);
 k->ry+=phase_advance(k->vy,2,k==&Bike.body?1:k==&Bike.wheel[0]?3:5);
}
#endif
