#ifndef PHYSICS_SPRING_TORQUE_H
#define PHYSICS_SPRING_TORQUE_H
#include <stdint.h>
/* Exact floor shift, wrapping32; every signed32 input is supported. */
#ifdef __SDCC
#define SPRING_TORQUE_ABI __sdcccall(0)
#else
#define SPRING_TORQUE_ABI
#endif
int32_t riding_spring_torque32(int32_t gsx,int32_t gsy,int32_t gx,int32_t gy) SPRING_TORQUE_ABI;
#endif
