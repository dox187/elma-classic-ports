#include "result.h"
#include <gb/cgb.h>
#include "menu.h"
#include "bike_render16.h"
#pragma bank 7
#include "ui_font.h"

static uint8_t used_patterns[64],text_pattern[16];
static uint8_t next_hud_tile;
static uint16_t next_world_tile;

static void protect_background(void) {
    volatile uint8_t *map=(volatile uint8_t *)
        ((LCDC_REG&LCDCF_BG9C00)?0x9c00U:0x9800U);
    volatile uint8_t *cell;
    uint8_t row,col,tile,attribute;
    uint8_t left=SCX_REG>>3,top=SCY_REG>>3;
    uint8_t columns=20+((SCX_REG&7)!=0);
    uint8_t rows=15+((SCY_REG&7)!=0);
    for(row=0;row<64;++row)used_patterns[row]=0;
    /* Include partial edge tiles and both wraps of the 32x32 BG map. The
     * attributes select the physical VRAM bank independently for each tile. */
    for(row=0;row<rows;++row) {
        for(col=0;col<columns;++col) {
            cell=map+((uint16_t)((top+row)&31)<<5)+((left+col)&31);
            VBK_REG=0;tile=*cell;
            VBK_REG=1;attribute=*cell;
            used_patterns[(tile>>3)+((attribute&8)?32:0)]
                |=(uint8_t)(1U<<(tile&7));
        }
    }
}

static uint16_t text_tile(void) {
    uint16_t tile;
    /* Reuse the riding HUD first. At most 21x16=336 scenery patterns
     * remain visible above the panel. Both layouts leave at least 108
     * additional eligible slots for the remaining text cells. */
#ifdef WORLD_SIGNED_BG
    if(next_hud_tile<20)return 492U+next_hud_tile++;
#else
    if(next_hud_tile<BIKE_WHEEL_EXTRA_TILE)return 256U+next_hud_tile++;
#endif
    do {
        tile=next_world_tile++;
#ifndef WORLD_SIGNED_BG
        if(next_world_tile==252)next_world_tile=256;
#endif
    } while(used_patterns[tile>>3]&(uint8_t)(1U<<(tile&7)));
    return tile;
}

static void draw_row(volatile uint8_t *map,const char *text) {
    uint8_t col,left,right,bank;
    uint16_t tile;
    for(col=0;col<20;++col) {
        left=(uint8_t)*text;if(left)++text;
        right=(uint8_t)*text;if(right)++text;
        tile=text_tile();bank=tile>>8;
        ui_font_pair(left,right,text_pattern);
        VBK_REG=bank;set_bkg_data((uint8_t)tile,1,text_pattern);
        VBK_REG=0;map[col]=(uint8_t)tile;
        /* The font has opaque black padding; priority hides sprites only
         * beneath the panel, leaving their data and positions untouched. */
        VBK_REG=1;map[col]=0x87|(bank<<3);
    }
}

void result_overlay(uint32_t frames,uint32_t previous_best) BANKED {
    volatile uint8_t *window;
    uint8_t i=15,old_vbk=VBK_REG;
    char time[41]="TIME 00:00.00  ";
    char previous[14]="PREV --:--.--";
    const char *status;
    if(!previous_best)status="FIRST RECORD";
    else if(frames<previous_best)status="NEW RECORD";
    else if(frames==previous_best)status="BEST MATCHED";
    else status="NO IMPROVEMENT";
    menu_format_time(time+5,frames);
    if(previous_best)menu_format_time(previous+5,previous_best);
    while(*status)time[i++]=*status++;
    time[i]=0;

    DISPLAY_OFF;
    protect_background();
#ifdef WORLD_SIGNED_BG
    next_hud_tile=0;
#else
    next_hud_tile=220;
#endif
    next_world_tile=0;
    window=(volatile uint8_t *)
        ((LCDC_REG&LCDCF_WIN9C00)?0x9c00U:0x9800U);
    draw_row(window,time);
    draw_row(window+32,previous);
    draw_row(window+64,"A:NEXT START:RETRY B/SELECT:MENU UP:INFO");
    VBK_REG=old_vbk;
    move_win(7,120);
    SHOW_WIN;
    DISPLAY_ON;
}
