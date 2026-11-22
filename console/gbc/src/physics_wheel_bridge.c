#ifdef __SDCC
#pragma bank 9
#include <stddef.h>
#include "physics_core.h"
#include "riding_constants.h"
typedef char wheel_native_layout[sizeof(circle_t)==24 &&
    offsetof(circle_t,rx)==0 && offsetof(circle_t,ry)==4 &&
    offsetof(circle_t,vx)==8 && offsetof(circle_t,vy)==12 &&
    offsetof(circle_t,alfa)==16 && offsetof(circle_t,omega)==20 &&
    offsetof(bike_t,body)==0 && offsetof(bike_t,wheel)==24 &&
    ELSZ>=1 && ELSZ<=256?1:-1];
typedef char wheel_impact_range[(int32_t)(2.0*PH_VS)>=1 && (int32_t)(2.0*PH_VS)<=65535 ? 1 : -1];
const uint16_t riding_impact_low=(uint16_t)(-(int32_t)(2.0*PH_VS));
const uint8_t riding_supports_threshold=(uint8_t)(1-ELSZ);
#endif
