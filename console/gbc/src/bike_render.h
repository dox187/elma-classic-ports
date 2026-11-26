#ifndef GBC_BIKE_RENDER_H
#define GBC_BIKE_RENDER_H
#include <stdint.h>
#include "runtime.h"

/* Screen coordinates, origin top-left, Y down; the caller transforms the
 * original Q16.16 world poses using the current camera and 12 pixels/meter. */
typedef struct {
    int16_t body_x, body_y, rider_x, rider_y, head_x, head_y;
    int16_t wheel_x[2], wheel_y[2];
} bike_screen_t;

#define BIKE_OBJECT_OAM_BASE 25
#define BIKE_VRAM_FIRST 192
#define BIKE_VRAM_COUNT 25
#define BIKE_HEAD_TILE 216
#define BIKE_HEAD_BACK_TILE 245

void bike_render_init(void);
void bike_render_hide(void);
/* Call immediately after vsync, before camera/map work, to upload changed
 * patterns during VBlank. draw() also prepares when used on its own. */
void bike_render_prepare(const gbc_bike_t *bike);
#ifdef RIDING_BANKED_DRAW
#define BIKE_DRAW_CALL GBC_BANKED
#else
#define BIKE_DRAW_CALL
#endif
void bike_render_draw(const gbc_bike_t *bike, const bike_screen_t *screen) BIKE_DRAW_CALL;

#endif
