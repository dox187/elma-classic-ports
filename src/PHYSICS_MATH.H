#ifndef ELMA_PHYSICS_MATH_H
#define ELMA_PHYSICS_MATH_H

// Only explicit Classic x87 builds use instruction-compatible endpoints.
// Keep the ordinary SDL build's math calls and compiler behavior unchanged.
#ifdef ELMA_CLASSIC_X87
#include "elma_x87.h"
#define ELMA_PHYSICS_SIN elma_x87_sin
#define ELMA_PHYSICS_COS elma_x87_cos
#else
#define ELMA_PHYSICS_SIN sin
#define ELMA_PHYSICS_COS cos
#endif

#endif
