// The time digits and the view box (the map at the bottom of the screen)
// during a level, as the original draws them (DIGIT.CPP, KIRAJ320.CPP
// kiview) at 0.4 of its size; hud.asm, data from tools/gen_hud.py.
//
// The digits are sprites (OAM 0-11, priority 3, OBJ palettes 6 and 7):
// black where the level under a digit is sky, white where it is ground,
// as the original's negative. The view box is BG3 (tiles with the priority
// bit, BG3 on top: BGMODE $09) cut to its width by window 1, its apples in
// it, its frame, flowers and bike sprites (OAM 12-23, priority 3, palette
// 7). It uses: BG3 chr $5000 and map $5400, OBJ tiles 256-383, CGRAM 0-3
// and 224-255, the registers BG3SC, BG34NBA, W34SEL, WH0, WH1, TMW (BG3
// only), CGWSEL and CGADSUB (0: no color math), core_scroll[4..5], DMA
// channel 1 and WMADD/WMDATA during hud_draw, the PPU multiplier.
#ifndef HUD_H
#define HUD_H

#include <snes.h>

// In forced blank, after phys_level(level) (it reads phys_objs): the tiles,
// colors, BG3 map and registers of the HUD.
void hud_load(u16 level);
// Every frame of a level. cam_x, cam_y: the camera (level pixels); baljobb:
// the original's pvalt->baljobbv_h.baljobb, 0..65535; time_hs: the time
// in hundredths; best_hs: the best time of the level, 0xFFFFFFFF if none.
// The bike from phys_view, the apples and flowers from phys_objs,
// phys_apples_left and phys_eaten.
void hud_draw(s16 cam_x, s16 cam_y, u16 baljobb, u32 time_hs, u32 best_hs);

// The original's billtime and billview: 1 shows the time and the view box.
// Both are 1 after the first hud_load and keep their value between levels.
extern u8 hud_show_time, hud_show_map;

#endif
