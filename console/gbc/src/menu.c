#include "menu.h"
#include <gb/cgb.h>
#include "menu_assets.h"
#pragma bank 7
#include "ui_font.h"

void world_level_name(uint8_t index,char *out);

volatile uint8_t menu_screen,menu_selection;
static uint8_t selected_level,resume_allowed,repeat_key,repeat_timer;
static char name_buffer[32];
static uint8_t row_tiles[20],row_attrs[20];
static uint8_t text_pattern[16];
static const uint8_t blank_pattern[16]={0};

static void text(uint8_t x,uint8_t y,const char *s,uint8_t width) {
    uint8_t i,left,right,count=width>>1;
    for(i=0;i<count;++i) {
        left=(uint8_t)*s;if(left)++s;
        right=(uint8_t)*s;if(right)++s;
        ui_font_pair(left,right,text_pattern);
        row_tiles[i]=y*10+i;row_attrs[i]=8;
        VBK_REG=1;set_bkg_data(row_tiles[i],1,text_pattern);
    }
    VBK_REG=1;set_bkg_tiles(x,y,count,1,row_attrs);
    VBK_REG=0;set_bkg_tiles(x,y,count,1,row_tiles);
}

static void cursor(uint8_t x,uint8_t y,uint8_t active) {
    uint8_t tile=active?240:241,attribute=active?2:0;
    VBK_REG=1;set_bkg_tiles(x,y,1,1,&attribute);
    VBK_REG=0;set_bkg_tiles(x,y,1,1,&tile);
}

static void begin_screen(uint8_t screen) {
    uint8_t i;
    DISPLAY_OFF;
    menu_screen=screen;repeat_key=repeat_timer=0;
    VBK_REG=0;set_bkg_tiles(0,0,20,18,menu_background_map);
    VBK_REG=1;
    for(i=0;i<20;++i)row_attrs[i]=1;
    for(i=0;i<18;++i)set_bkg_tiles(0,i,20,1,row_attrs);
    VBK_REG=0;
    text(7,0,"ELASTO MANIA",12);
}

static void draw_main_cursor(void) {
    uint8_t i;
    for(i=0;i<(resume_allowed?4:3);++i)cursor(5,7+i*2,i==menu_selection);
}

static void draw_main(void) {
    char heading[21]="SELECTED LEVEL 00/00";
    begin_screen(MENU_MAIN);
    text(7,2,MENU_VERSION_TEXT,12);
    heading[15]='0'+(selected_level+1)/10;
    heading[16]='0'+(selected_level+1)%10;
    heading[18]='0'+MENU_LEVEL_COUNT/10;
    heading[19]='0'+MENU_LEVEL_COUNT%10;
    text(5,4,heading,20);
    world_level_name(selected_level,name_buffer);
    text(5,5,name_buffer,20);
    text(7,7,resume_allowed?"RESUME":"PLAY",20);
    if(resume_allowed)text(7,9,"RESTART",20);
    text(7,resume_allowed?11:9,"LEVEL SELECT",20);
    text(7,resume_allowed?13:11,"CONTROLS",20);
    text(0,15,"A/START SELECT",20);
    if(resume_allowed)text(0,16,"B RESUME",20);
    text(0,17,"UP/DOWN SELECT",20);
    draw_main_cursor();
    DISPLAY_ON;
}

static void draw_list(void) {
    uint8_t page=selected_level/9,first=page*9,row,index;
    char heading[12]="LEVEL 00/00";
    heading[6]='0'+(selected_level+1)/10;
    heading[7]='0'+(selected_level+1)%10;
    heading[9]='0'+MENU_LEVEL_COUNT/10;
    heading[10]='0'+MENU_LEVEL_COUNT%10;
    text(7,2,heading,12);
    for(row=0;row<9;++row) {
        index=first+row;
        if(index<MENU_LEVEL_COUNT) {
            world_level_name(index,name_buffer);
            text(2,4+row,name_buffer,18);
        } else text(2,4+row,"",18);
        cursor(0,4+row,index==selected_level);
    }
}

static void open_list(void) {
    begin_screen(MENU_LEVELS);
    text(0,15,"A/START PLAY",20);
    text(0,16,"B BACK    L/R PAGE",20);
    text(0,17,"UP/DOWN SELECT",20);
    draw_list();
    DISPLAY_ON;
}

static void open_controls(void) {
    begin_screen(MENU_CONTROLS);
    text(8,2,"CONTROLS",8);
    text(2,5,"A          THROTTLE",36);
    text(2,7,"B          BRAKE",36);
    text(2,9,"LEFT/RIGHT ROTATE",36);
    text(2,11,"UP         TURN",36);
    text(2,13,"SELECT     MENU",36);
    text(2,15,"START      RESTART",36);
    text(0,17,"B BACK",20);
    DISPLAY_ON;
}

void menu_open(uint8_t selected,uint8_t can_resume) BANKED {
    DISPLAY_OFF;HIDE_WIN;HIDE_SPRITES;
    selected_level=selected<MENU_LEVEL_COUNT ? selected : 0;
    resume_allowed=can_resume;menu_selection=0;
    LCDC_REG|=LCDCF_BG8000;
    set_bkg_palette(0,3,menu_palettes);
    VBK_REG=0;
    set_bkg_data(64,MENU_BG_PATTERN_COUNT,menu_background);
    set_bkg_data(240,1,menu_cursor);
    set_bkg_data(241,1,blank_pattern);
    move_bkg(0,0);
    draw_main();
    SHOW_BKG;
}

static uint8_t navigation(uint8_t keys,uint8_t pressed) {
    uint8_t direction=0;
    if(keys&J_UP)direction=J_UP;
    else if(keys&J_DOWN)direction=J_DOWN;
    else if(menu_screen==MENU_LEVELS && (keys&J_LEFT))direction=J_LEFT;
    else if(menu_screen==MENU_LEVELS && (keys&J_RIGHT))direction=J_RIGHT;
    if(!direction){repeat_key=repeat_timer=0;return 0;}
    if(direction!=repeat_key || (pressed&direction)) {
        repeat_key=direction;repeat_timer=16;return direction;
    }
    if(repeat_timer){--repeat_timer;return 0;}
    repeat_timer=4;return direction;
}

uint8_t menu_tick(uint8_t keys,uint8_t pressed) BANKED {
    uint8_t direction,old=selected_level,count;
    if(pressed&J_B) {
        if(menu_screen!=MENU_MAIN)draw_main();
        else if(resume_allowed)return MENU_RESUME;
        return MENU_NO_ACTION;
    }
    if(menu_screen==MENU_CONTROLS)return MENU_NO_ACTION;
    if(pressed&(J_A|J_START)) {
        if(menu_screen==MENU_LEVELS)return selected_level;
        if(!menu_selection)return resume_allowed?MENU_RESUME:selected_level;
        if(resume_allowed && menu_selection==1)return MENU_RESTART;
        if(menu_selection==(resume_allowed?2:1))open_list();
        else open_controls();
        return MENU_NO_ACTION;
    }
    direction=navigation(keys,pressed);
    if(!direction)return MENU_NO_ACTION;
    if(menu_screen==MENU_MAIN) {
        count=resume_allowed?4:3;
        if(direction==J_UP)menu_selection=menu_selection?menu_selection-1:count-1;
        else menu_selection=menu_selection+1<count?menu_selection+1:0;
        draw_main_cursor();
    } else {
        if(direction==J_UP)selected_level=selected_level?selected_level-1:MENU_LEVEL_COUNT-1;
        else if(direction==J_DOWN)selected_level=selected_level+1<MENU_LEVEL_COUNT?selected_level+1:0;
        else if(direction==J_LEFT)selected_level=selected_level>=9?selected_level-9:0;
        else selected_level=selected_level+9<MENU_LEVEL_COUNT?selected_level+9:MENU_LEVEL_COUNT-1;
        if(selected_level!=old)draw_list();
    }
    return MENU_NO_ACTION;
}
