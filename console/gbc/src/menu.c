#include "menu.h"
#include <gb/cgb.h>
#include "menu_assets.h"
#pragma bank 7

void world_level_name(uint8_t index,char *out);

static uint8_t selected_level,resume_allowed,repeat_key,repeat_timer;
static char name_buffer[32];
static uint8_t row_tiles[20],row_attrs[20];

static uint8_t glyph(uint8_t c) {
    if(c>='a' && c<='z')c-='a'-'A';
    return c>=32 && c<=95 ? c-32 : 0;
}

static void text(uint8_t x,uint8_t y,const char *s,uint8_t width) {
    uint8_t i,c;
    for(i=0;i<width;++i) {
        c=(uint8_t)*s;
        row_tiles[i]=glyph(c);row_attrs[i]=0;
        if(c)++s;
    }
    VBK_REG=1;set_bkg_tiles(x,y,width,1,row_attrs);
    VBK_REG=0;set_bkg_tiles(x,y,width,1,row_tiles);
}

static void draw_list(void) {
    uint8_t page=selected_level/9,first=page*9,row,index,i;
    char heading[12]="LEVEL 00/00";
    heading[6]='0'+(selected_level+1)/10;
    heading[7]='0'+(selected_level+1)%10;
    heading[9]='0'+MENU_LEVEL_COUNT/10;
    heading[10]='0'+MENU_LEVEL_COUNT%10;
    text(4,2,heading,12);
    for(row=0;row<9;++row) {
        index=first+row;
        for(i=0;i<20;++i){row_tiles[i]=0;row_attrs[i]=0;}
        if(index<MENU_LEVEL_COUNT) {
            world_level_name(index,name_buffer);
            for(i=0;i<18 && name_buffer[i];++i)row_tiles[2+i]=glyph((uint8_t)name_buffer[i]);
            if(index==selected_level){row_tiles[0]=240;row_attrs[0]=2;}
        }
        VBK_REG=1;set_bkg_tiles(0,4+row,20,1,row_attrs);
        VBK_REG=0;set_bkg_tiles(0,4+row,20,1,row_tiles);
    }
}

void menu_open(uint8_t selected,uint8_t can_resume) BANKED {
    uint8_t i;
    DISPLAY_OFF;HIDE_WIN;HIDE_SPRITES;
    selected_level=selected<MENU_LEVEL_COUNT ? selected : 0;
    resume_allowed=can_resume;
    repeat_key=repeat_timer=0;
    LCDC_REG|=LCDCF_BG8000;
    set_bkg_palette(0,3,menu_palettes);
    VBK_REG=0;
    set_bkg_data(0,64,menu_font);
    set_bkg_data(64,MENU_BG_PATTERN_COUNT,menu_background);
    set_bkg_data(240,1,menu_cursor);
    set_bkg_tiles(0,0,20,18,menu_background_map);
    VBK_REG=1;
    for(i=0;i<20;++i)row_attrs[i]=1;
    for(i=0;i<18;++i)set_bkg_tiles(0,i,20,1,row_attrs);
    VBK_REG=0;move_bkg(0,0);
    text(4,0,"ELASTO MANIA",12);
    text(0,15,"A/START PLAY",20);
    text(0,16,resume_allowed ? "B RESUME   L/R PAGE" : "L/R PAGE",20);
    text(0,17,"UP/DOWN SELECT",20);
    draw_list();
    SHOW_BKG;DISPLAY_ON;
}

uint8_t menu_tick(uint8_t keys,uint8_t pressed) BANKED {
    uint8_t direction=0,fire=0,old=selected_level;
    if(pressed&(J_A|J_START))return selected_level;
    if(resume_allowed && (pressed&J_B))return MENU_RESUME;
    if(keys&J_UP)direction=J_UP;
    else if(keys&J_DOWN)direction=J_DOWN;
    else if(keys&J_LEFT)direction=J_LEFT;
    else if(keys&J_RIGHT)direction=J_RIGHT;
    if(!direction){repeat_key=repeat_timer=0;return MENU_NO_ACTION;}
    if(direction!=repeat_key || (pressed&direction)) {
        repeat_key=direction;repeat_timer=16;fire=1;
    } else if(repeat_timer)--repeat_timer;
    else {repeat_timer=4;fire=1;}
    if(!fire)return MENU_NO_ACTION;
    if(direction==J_UP)selected_level=selected_level ? selected_level-1 : MENU_LEVEL_COUNT-1;
    else if(direction==J_DOWN)selected_level=selected_level+1<MENU_LEVEL_COUNT ? selected_level+1 : 0;
    else if(direction==J_LEFT)selected_level=selected_level>=9 ? selected_level-9 : 0;
    else selected_level=selected_level+9<MENU_LEVEL_COUNT ? selected_level+9 : MENU_LEVEL_COUNT-1;
    if(selected_level!=old)draw_list();
    return MENU_NO_ACTION;
}
