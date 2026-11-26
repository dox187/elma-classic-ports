#include <gb/gb.h>
#include <gb/cgb.h>
#include "bike_render16.h"
#include "riding_assets.h"
#pragma bank 4

static const uint8_t blank_head_half[16]={0};

void bike_render16_init_sprites(void) BANKED {
    uint8_t i;
    /* Every head frame has a transparent lower half. Initialize both buffers
     * while the LCD is off. Only their upper tiles change during play. */
    VBK_REG=1;
    set_sprite_data((uint8_t)(BIKE_HEAD_TILE+1),1,blank_head_half);
    set_sprite_data((uint8_t)(BIKE_HEAD_BACK_TILE+1),1,blank_head_half);
    VBK_REG=0;
    set_sprite_palette(0,1,riding_body_palette);
    set_sprite_palette(3,1,riding_wheel_palette);
    set_sprite_palette(4,1,riding_head_palette);
    for(i=0;i<8;++i) {
        shadow_OAM[i].tile=192+i*2;
        shadow_OAM[i].prop=S_BANK;
    }
    for(i=8;i<12;++i) {
        shadow_OAM[i].tile=208+(i-8)*2;
        shadow_OAM[i].prop=S_BANK|3;
    }
    shadow_OAM[12].tile=BIKE_HEAD_TILE;
    shadow_OAM[12].prop=S_BANK|4;
}
