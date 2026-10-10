// Compact sprite HUD: outlined time/best time and remaining apples.
// OAM 0-11: best/current time; 12-14: LGR apple icon and remaining count.
// Uses OBJ tiles 256-351 and palette 6, CPU math registers during draw.
// No BG3, window registers, level geometry, frame DMA or minimap buffer.
#ifndef HUD_H
#define HUD_H
#include <snes.h>

// In forced blank after phys_level. Level argument retained for compatibility.
void hud_load(u16 level);
// Each display frame. Camera/direction arguments retained for compatibility;
// times are hundredths, best_hs = 0xFFFFFFFF when absent. Reads only
// phys_apples_left; counter shows 00..99 (physics supports up to 64 apples).
void hud_draw(s16 cam_x, s16 cam_y, u16 baljobb, u32 time_hs, u32 best_hs);

// Initialized to 1 at first load, preserved between levels. hud_show_map
// retains its existing symbol/button/SRAM binding and now toggles apples.
extern u8 hud_show_time, hud_show_map;
#endif
