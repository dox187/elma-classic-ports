#include <gb/gb.h>
#include <gb/cgb.h>
#include "bike_render16.h"
#include "riding_assets.h"
#include "world_memory.h"
#pragma bank 4

static const uint8_t blank_head_half[16]={0};

void bike_render16_init_sprites(void) BANKED {
    uint8_t i;
    /* Every head frame has a transparent lower half. Initialize both buffers
     * while the LCD is off. Only their upper tiles change during play. */
    VBK_REG=1;
#ifdef RIDING_PAIRED_MASKS
    if(riding_wheel_tiles[0]) {
        uint8_t phase,previous,pattern[64];
        for(phase=0;phase<8;++phase) {
            for(previous=0;previous<phase;++previous)
                if(riding_wheel_tiles[previous]==riding_wheel_tiles[phase])break;
            if(previous!=phase)continue;
            world_far_copy(13,riding_wheels+(uint16_t)phase*64,pattern,sizeof(pattern));
            set_sprite_data(riding_wheel_tiles[phase],4,pattern);
        }
    }
#endif
#ifdef RIDING_BODY_TRANSFERS
    /* Twelve pairs fit between the streamed heads and the third wheel phase. */
    for(i=0;i<BIKE_HEAD_RESIDENT_COUNT;++i) {
        uint8_t pixels[16];
        uint8_t head=(i+124)&127, tile=BIKE_HEAD_RESIDENT_TILE+2*i;
        world_far_copy(13,riding_heads+(uint16_t)head*16,pixels,sizeof(pixels));
        set_sprite_data(tile,1,pixels);
        set_sprite_data(tile+1,1,blank_head_half);
    }
#endif
    set_sprite_data((uint8_t)(BIKE_HEAD_TILE+1),1,blank_head_half);
    set_sprite_data((uint8_t)(BIKE_HEAD_BACK_TILE+1),1,blank_head_half);
    VBK_REG=0;
    set_sprite_palette(0,1,riding_body_palette);
    set_sprite_palette(3,1,riding_wheel_palette);
    set_sprite_palette(4,1,riding_head_palette);
    for(i=0;i<8;++i) {
        shadow_OAM[i].tile=BIKE_BODY_TILE+i*2;
        shadow_OAM[i].prop=S_BANK;
    }
    for(i=8;i<12;++i) {
        shadow_OAM[i].tile=BIKE_WHEEL_TILE+(i-8)*2;
        shadow_OAM[i].prop=S_BANK|3;
    }
    shadow_OAM[12].tile=BIKE_HEAD_TILE;
    shadow_OAM[12].prop=S_BANK|4;
}
