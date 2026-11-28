#ifndef GBC_BIKE_RENDER16_H
#define GBC_BIKE_RENDER16_H
#include "bike_render.h"

/* Alternative GLOBAL 8x16 OBJ mode. Do not link both renderers. Game setup
 * selects SPRITES_8x16. The HUD uses bank 1 patterns 236..255 with signed
 * BG addressing and 220..239 with unsigned BG addressing. An opaque
 * priority window covers the lower halves of sprites crossing the HUD edge.
 */
#undef BIKE_OBJECT_OAM_BASE
#undef BIKE_VRAM_COUNT
#undef BIKE_HEAD_BACK_TILE
#define BIKE_OBJECT_OAM_BASE 13
#define BIKE_VRAM_COUNT 28
#ifdef WORLD_SIGNED_BG
#undef BIKE_VRAM_FIRST
#define BIKE_VRAM_FIRST 64
#undef BIKE_HEAD_TILE
#define BIKE_BODY_TILE 64
#define BIKE_WHEEL_TILE 80
#define BIKE_HEAD_TILE 88
#define BIKE_HEAD_BACK_TILE 90
#define BIKE_WHEEL_EXTRA_TILE 116
#define BIKE_HEAD_RESIDENT_TILE 92
#define BIKE_HEAD_RESIDENT_COUNT 12
#else
#define BIKE_BODY_TILE 192
#define BIKE_WHEEL_TILE 208
#define BIKE_HEAD_BACK_TILE 218
#define BIKE_WHEEL_EXTRA_TILE 244
#endif
#ifdef RIDING_PAIRED_MASKS
extern const uint8_t riding_wheel_tiles[8];
#endif
#endif
