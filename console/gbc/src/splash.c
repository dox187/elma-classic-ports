#include "splash.h"
#include <gb/cgb.h>
#include "splash_assets.h"
#pragma bank 2

volatile uint8_t splash_active;

void splash_show(void) BANKED {
    uint8_t previous,keys;
    DISPLAY_OFF;
    HIDE_WIN;
    HIDE_SPRITES;
    LCDC_REG=(LCDC_REG&~LCDCF_BG9C00)|LCDCF_BG8000;
    set_bkg_palette(0,8,splash_palettes);
    VBK_REG=0;
    set_bkg_data(0,SPLASH_TILE_COUNT0,splash_tiles0);
#if SPLASH_TILE_COUNT1
    VBK_REG=1;
    set_bkg_data(0,SPLASH_TILE_COUNT1,splash_tiles1);
#endif
    VBK_REG=1;
    set_bkg_tiles(0,0,20,18,splash_attributes);
    VBK_REG=0;
    set_bkg_tiles(0,0,20,18,splash_map);
    move_bkg(0,0);
    previous=joypad();
    SHOW_BKG;
    DISPLAY_ON;
    splash_active=1;
    do {
        vsync();
        keys=joypad();
        if((keys&~previous)&(J_A|J_START)) {
            splash_active=0;
            return;
        }
        previous=keys;
    } while(1);
}
