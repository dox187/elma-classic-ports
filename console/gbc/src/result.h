#ifndef GBC_RESULT_H
#define GBC_RESULT_H
#include <gb/gb.h>
#include <stdint.h>

/* Publish a three-row window over the frozen gameplay image. Gameplay must
 * already use unsigned tile addressing, separate BG/window maps and palette 7.
 * Rebuild game assets/cache before rendering the world again. */
void result_overlay(uint32_t frames,uint32_t previous_best) BANKED;
#endif
