#ifndef GBC_BIKE_RENDER16_H
#define GBC_BIKE_RENDER16_H
#include "bike_render.h"

/* Alternative GLOBAL 8x16 OBJ mode. Do not link both renderers. Game setup
 * must select SPRITES_8x16 and reserve HUD bank1 tiles 220..243. An opaque
 * priority window covers the lower halves of sprites crossing the HUD edge.
 */
#undef BIKE_OBJECT_OAM_BASE
#undef BIKE_VRAM_COUNT
#undef BIKE_HEAD_BACK_TILE
#define BIKE_OBJECT_OAM_BASE 13
#define BIKE_VRAM_COUNT 28
#define BIKE_HEAD_BACK_TILE 218
#define BIKE_WHEEL_EXTRA_TILE 244
#ifdef RIDING_PAIRED_MASKS
extern const uint8_t riding_wheel_tiles[8];
#endif
#endif
