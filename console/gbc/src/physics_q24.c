#include <stdint.h>
#include "riding_constants.h"
#include "physics_q24.h"
#include "physics_spring_torque.h"
#include "physics_math.h"
#ifdef __SDCC
const uint8_t riding_move_index=Q24_MOVE,riding_angle_index=Q24_ANGLE;
int32_t riding_rider_s_wide(int32_t v) __sdcccall(0) {return Q24_MUL(v,C_RIDER_S);}
int32_t riding_rider_f_wide(int32_t v) __sdcccall(0) {return Q24_MUL(v,C_RIDER_F);}
int16_t riding_coeff16_C_H_X(int16_t v) __sdcccall(0) {return sat16(Q24_MUL(v,C_H_X));}
int16_t riding_coeff16_C_H_Y(int16_t v) __sdcccall(0) {return sat16(Q24_MUL(v,C_H_Y));}
int32_t riding_coeff32_C_BRAKE_A(int32_t v) __sdcccall(0) {return Q24_MUL(v,C_BRAKE_A);}
int32_t riding_coeff32_C_BRAKE_W(int32_t v) __sdcccall(0) {return Q24_MUL(v,C_BRAKE_W);}
int32_t riding_coeff32_C_BRAKE_GW(int32_t v) __sdcccall(0) {return Q24_MUL(v,C_BRAKE_GW);}
int16_t riding_coeff16_C_BRAKE_W(int16_t v) __sdcccall(0) {return sat16(Q24_MUL(v,C_BRAKE_W));}
int16_t riding_coeff16_C_BRAKE_GW(int16_t v) __sdcccall(0) {return sat16(Q24_MUL(v,C_BRAKE_GW));}

#else
int32_t q24_fraction;
uint8_t q24_saturated;
int32_t q24_hostmul(int32_t value,int32_t coefficient) {
 int64_t raw=(int64_t)value*coefficient,rounded=(raw+(1L<<23))>>24;
 q24_saturated=rounded>INT32_MAX || rounded<INT32_MIN;
 if(q24_saturated){q24_fraction=0;return rounded<0?INT32_MIN:INT32_MAX;}
 q24_fraction=(int32_t)(raw-rounded*(1L<<24));return (int32_t)rounded;
}
int32_t riding_spring_torque32(int32_t gsx,int32_t gsy,int32_t gx,int32_t gy) {
 uint64_t raw=(uint64_t)((int64_t)gsx*gy)-(uint64_t)((int64_t)gsy*gx);
 return (int32_t)(raw>>12);
}
#endif
