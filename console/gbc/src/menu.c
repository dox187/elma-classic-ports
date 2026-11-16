#include "menu.h"
#include <gb/cgb.h>
#include "menu_assets.h"
#include "save.h"
#pragma bank 7
#include "ui_font.h"

void world_level_name(uint8_t index,char *out);

volatile uint8_t menu_screen,menu_selection;
volatile uint8_t menu_player_selection,menu_keyboard_selection;
static uint8_t selected_level,resume_allowed,repeat_key,repeat_timer;
static char name_buffer[32];
static uint8_t row_tiles[20],row_attrs[20];
static uint8_t text_rows[18],next_text_tile;
static uint8_t text_pattern[16];
static char edit_name[SAVE_NAME_MAX+1];
static uint8_t edit_length;
static const uint8_t blank_pattern[16]={0};
static const uint16_t key_palette[]={RGB(31,31,28),RGB(31,31,28),RGB(0,4,0),RGB(0,4,0)};
static const char keyboard_letters[]="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

static void text(uint8_t x,uint8_t y,const char *s,uint8_t width) {
    uint8_t i,left,right,count=width>>1;
    /* Each row reserves its span on first use; later updates keep that width.
     * This permits wide adjacent rows without aliasing the next row's tiles.
     * The largest screen uses fewer than 200 of VRAM bank 1's 256 patterns. */
    if(text_rows[y]==255){text_rows[y]=next_text_tile;next_text_tile+=count;}
    for(i=0;i<count;++i) {
        left=(uint8_t)*s;if(left)++s;
        right=(uint8_t)*s;if(right)++s;
        ui_font_pair(left,right,text_pattern);
        row_tiles[i]=text_rows[y]+i;row_attrs[i]=8;
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
    next_text_tile=0;
    for(i=0;i<18;++i)text_rows[i]=255;
    VBK_REG=0;set_bkg_tiles(0,0,20,18,menu_background_map);
    VBK_REG=1;
    for(i=0;i<20;++i)row_attrs[i]=1;
    for(i=0;i<18;++i)set_bkg_tiles(0,i,20,1,row_attrs);
    VBK_REG=0;
    text(7,0,"ELASTO MANIA",12);
}

static void draw_main_cursor(void) {
    uint8_t i;
    for(i=0;i<4;++i)cursor(5,7+i*2,i==menu_selection);
}

static void player_label(uint8_t x,uint8_t y) {
    uint8_t i;
    char label[21]="PLAYER: ";
    for(i=0;i<SAVE_NAME_MAX && save_names[save_player][i];++i)
        label[8+i]=save_names[save_player][i];
    label[8+i]=0;
    text(x,y,label,20);
}

void menu_format_time(char *label,uint32_t frames) {
    uint32_t centiseconds;
    uint16_t seconds;
    /* Keep both products bounded even when a stored counter is very large.
     * Six clock digits wrap at 100 minutes, as the riding HUD does. */
    centiseconds=((frames/5973UL)%60UL)*10000UL
        +(frames%5973UL)*10000UL/5973UL;
    centiseconds%=600000UL;
    seconds=(uint16_t)(centiseconds/100UL);
    label[0]='0'+seconds/600;label[1]='0'+seconds/60%10;
    label[2]=':';
    label[3]='0'+seconds%60/10;label[4]='0'+seconds%10;
    label[5]='.';
    label[6]='0'+centiseconds%100UL/10;label[7]='0'+centiseconds%10;
}

static void best_label(uint8_t x,uint8_t y) {
    char label[15]="BEST --:--.--";
    uint32_t frames=save_best(save_player,selected_level);
    if(frames)menu_format_time(label+5,frames);
    text(x,y,label,20);
}

static void draw_main(void) {
    char heading[21]="SELECTED LEVEL 00/00";
    begin_screen(MENU_MAIN);
    text(7,2,MENU_VERSION_TEXT,12);
    player_label(5,3);
    heading[15]='0'+(selected_level+1)/10;
    heading[16]='0'+(selected_level+1)%10;
    heading[18]='0'+MENU_LEVEL_COUNT/10;
    heading[19]='0'+MENU_LEVEL_COUNT%10;
    text(5,4,heading,20);
    world_level_name(selected_level,name_buffer);
    text(5,5,name_buffer,20);
    best_label(5,6);
    text(7,7,resume_allowed?"RESUME":"PLAY",20);
    if(resume_allowed)text(7,9,"RESTART",20);
    text(7,resume_allowed?11:9,"LEVEL SELECT",20);
    if(!resume_allowed)text(7,11,"PLAYERS",20);
    text(7,13,"CONTROLS",20);
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
    best_label(2,13);
}

static void open_list(void) {
    begin_screen(MENU_LEVELS);
    player_label(2,3);
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

static void draw_players(void) {
    uint8_t player,i;
    char label[29];
    for(player=0;player<SAVE_PLAYER_COUNT;++player) {
        for(i=0;i<28;++i)label[i]=' ';
        label[28]=0;label[0]='1'+player;
        for(i=0;i<SAVE_NAME_MAX && save_names[player][i];++i)
            label[2+i]=save_names[player][i];
        if(player==save_player) {
            label[16]='A';label[17]='C';label[18]='T';
            label[19]='I';label[20]='V';label[21]='E';
        }
        text(4,5+player*2,label,28);
        cursor(2,5+player*2,player==menu_player_selection);
    }
}

static void open_players(void) {
    begin_screen(MENU_PLAYERS);
    text(6,2,"PLAYERS",16);
    player_label(4,3);
    draw_players();
    text(1,14,"A/START SELECT",36);
    text(1,15,"SELECT RENAME",36);
    text(1,16,"B BACK",36);
    text(1,17,"UP/DOWN PLAYER",36);
    DISPLAY_ON;
}

static void box_patterns(void) {
    static const uint8_t edges[]={9,1,3,8,2,12,4,6};
    uint8_t i,row,bits,edge;
    VBK_REG=0;
    for(i=0;i<8;++i) {
        edge=edges[i];
        for(row=0;row<8;++row) {
            bits=((edge&1) && !row) || ((edge&4) && row==7)?255:0;
            if(edge&8)bits|=128;
            if(edge&2)bits|=1;
            text_pattern[row*2]=text_pattern[row*2+1]=bits;
        }
        set_bkg_data(242+i,1,text_pattern);
    }
}

static void frame(uint8_t x,uint8_t y,uint8_t width,uint8_t height) {
    uint8_t row,col;
    for(col=0;col<width;++col)row_attrs[col]=0;
    for(row=0;row<height;++row) {
        for(col=0;col<width;++col)row_tiles[col]=!row?243:row==height-1?248:241;
        row_tiles[0]=!row?242:row==height-1?247:245;
        row_tiles[width-1]=!row?244:row==height-1?249:246;
        VBK_REG=1;set_bkg_tiles(x,y+row,width,1,row_attrs);
        VBK_REG=0;set_bkg_tiles(x,y+row,width,1,row_tiles);
    }
}

static void name_heading(uint8_t invalid) {
    char heading[21]="PLAYER 1 NAME";
    heading[7]='1'+menu_player_selection;
    text(5,1,invalid?"NAME CANNOT BE BLANK":heading,20);
}

static void draw_name(void) {
    uint8_t i;
    char label[21];
    for(i=0;i<20;++i)label[i]=' ';
    for(i=0;i<edit_length;++i)label[i]=edit_name[i];
    if(edit_length<SAVE_NAME_MAX)label[edit_length]='_';
    label[20]=0;
    text(5,3,label,20);
    name_heading(0);
}

static void key_highlight(uint8_t key,uint8_t active) {
    uint8_t i,x,y,width;
    if(key<36){x=1+(key%9)*2;y=6+(key/9)*2;width=2;}
    else {x=1+(key-36)*6;y=14;width=6;}
    for(i=0;i<width;++i)row_attrs[i]=active?11:8;
    VBK_REG=1;set_bkg_tiles(x,y,width,1,row_attrs);VBK_REG=0;
}

static void open_name(void) {
    uint8_t row,col,i;
    char keys[37];
    for(edit_length=0;edit_length<SAVE_NAME_MAX && save_names[menu_player_selection][edit_length];++edit_length)
        edit_name[edit_length]=save_names[menu_player_selection][edit_length];
    edit_name[edit_length]=0;menu_keyboard_selection=0;
    begin_screen(MENU_NAME);
    frame(4,2,12,3);
    frame(0,5,20,11);
    draw_name();
    for(row=0;row<4;++row) {
        for(i=0;i<36;++i)keys[i]=' ';
        keys[36]=0;
        for(col=0;col<9;++col)keys[col*4+1]=keyboard_letters[row*9+col];
        text(1,6+row*2,keys,36);
    }
    text(1,14,"   SPACE        DEL          OK",36);
    text(0,16,"ARROWS MOVE  A KEY  B DELETE",40);
    text(0,17,"START DONE     SELECT CANCEL",40);
    key_highlight(menu_keyboard_selection,1);
    DISPLAY_ON;
}

static void confirm_name(void) {
    uint8_t i;
    for(i=0;i<edit_length;++i)if(edit_name[i]!=' ') {
        save_name(menu_player_selection,edit_name);
        open_players();
        return;
    }
    name_heading(1);
}

static void delete_letter(void) {
    if(edit_length)edit_name[--edit_length]=0;
    draw_name();
}

static void choose_key(void) {
    uint8_t key=menu_keyboard_selection;
    if(key==38){confirm_name();return;}
    if(key==37){delete_letter();return;}
    if(edit_length<SAVE_NAME_MAX) {
        edit_name[edit_length++]=key==36?' ':keyboard_letters[key];
        edit_name[edit_length]=0;
        draw_name();
    }
}

static void move_key(uint8_t direction) {
    uint8_t key=menu_keyboard_selection,row,col;
    key_highlight(key,0);
    if(key>=36) {
        col=key-36;
        if(direction==J_LEFT)key=col?key-1:38;
        else if(direction==J_RIGHT)key=col<2?key+1:36;
        else key=(direction==J_UP?27:0)+col*3+1;
    } else {
        row=key/9;col=key%9;
        if(direction==J_LEFT)key=col?key-1:key+8;
        else if(direction==J_RIGHT)key=col<8?key+1:key-8;
        else if(direction==J_UP)key=row?key-9:36+col/3;
        else key=row<3?key+9:36+col/3;
    }
    menu_keyboard_selection=key;
    key_highlight(key,1);
}

static void prepare_menu(void) {
    DISPLAY_OFF;HIDE_WIN;HIDE_SPRITES;
    LCDC_REG|=LCDCF_BG8000;
    set_bkg_palette(0,3,menu_palettes);
    set_bkg_palette(3,1,key_palette);
    VBK_REG=0;
    set_bkg_data(64,MENU_BG_PATTERN_COUNT,menu_background);
    set_bkg_data(240,1,menu_cursor);
    set_bkg_data(241,1,blank_pattern);
    box_patterns();
    move_bkg(0,0);
}

void menu_open(uint8_t selected,uint8_t can_resume) BANKED {
    prepare_menu();
    selected_level=selected<MENU_LEVEL_COUNT ? selected : 0;
    resume_allowed=can_resume;menu_selection=0;
    draw_main();
    SHOW_BKG;
}

void menu_result(uint8_t level,uint32_t frames,uint32_t previous_best) BANKED {
    char heading[13]="COURSE 00/00";
    char time[23]="TIME          00:00.00";
    char best[23]="PREVIOUS BEST --:--.--";
    const char *status;
    prepare_menu();
    selected_level=level<MENU_LEVEL_COUNT ? level : 0;
    resume_allowed=0;menu_selection=0;
    begin_screen(MENU_RESULT);
    text(6,2,"LEVEL COMPLETE",16);
    heading[7]='0'+(selected_level+1)/10;
    heading[8]='0'+(selected_level+1)%10;
    heading[10]='0'+MENU_LEVEL_COUNT/10;
    heading[11]='0'+MENU_LEVEL_COUNT%10;
    text(2,4,heading,32);
    world_level_name(selected_level,name_buffer);
    text(2,5,name_buffer,32);
    player_label(2,6);
    frame(1,8,18,6);
    menu_format_time(time+14,frames);
    if(previous_best)menu_format_time(best+14,previous_best);
    text(2,9,time,32);
    text(2,11,best,32);
    if(!previous_best)status="FIRST RECORD";
    else if(frames<previous_best)status="NEW RECORD";
    else if(frames==previous_best)status="BEST MATCHED";
    else status="NO IMPROVEMENT";
    text(2,12,status,32);
    text(2,14,"UP LAST FRAME",32);
    text(2,15,"A NEXT LEVEL",32);
    text(2,16,"START RETRY",32);
    text(2,17,"B/SELECT MENU",32);
    DISPLAY_ON;
    SHOW_BKG;
}

static uint8_t navigation(uint8_t keys,uint8_t pressed) {
    uint8_t direction=0;
    if(keys&J_UP)direction=J_UP;
    else if(keys&J_DOWN)direction=J_DOWN;
    else if((menu_screen==MENU_LEVELS || menu_screen==MENU_NAME) && (keys&J_LEFT))direction=J_LEFT;
    else if((menu_screen==MENU_LEVELS || menu_screen==MENU_NAME) && (keys&J_RIGHT))direction=J_RIGHT;
    if(!direction){repeat_key=repeat_timer=0;return 0;}
    if(direction!=repeat_key || (pressed&direction)) {
        repeat_key=direction;repeat_timer=16;return direction;
    }
    if(repeat_timer){--repeat_timer;return 0;}
    repeat_timer=4;return direction;
}

uint8_t menu_tick(uint8_t keys,uint8_t pressed) BANKED {
    uint8_t direction,old=selected_level,count;
    if(menu_screen==MENU_NAME) {
        if(pressed&J_SELECT)open_players();
        else if(pressed&J_START)confirm_name();
        else if(pressed&J_B)delete_letter();
        else if(pressed&J_A)choose_key();
        else {direction=navigation(keys,pressed);if(direction)move_key(direction);}
        return MENU_NO_ACTION;
    }
    if(pressed&J_B) {
        if(menu_screen!=MENU_MAIN)draw_main();
        else if(resume_allowed)return MENU_RESUME;
        return MENU_NO_ACTION;
    }
    if(menu_screen==MENU_CONTROLS)return MENU_NO_ACTION;
    if(menu_screen==MENU_PLAYERS) {
        if(pressed&J_SELECT)open_name();
        else if(pressed&(J_A|J_START)) {
            save_select(menu_player_selection);
            draw_main();
        } else {
            direction=navigation(keys,pressed);
            if(direction) {
                if(direction==J_UP)menu_player_selection=menu_player_selection?menu_player_selection-1:SAVE_PLAYER_COUNT-1;
                else menu_player_selection=menu_player_selection+1<SAVE_PLAYER_COUNT?menu_player_selection+1:0;
                draw_players();
            }
        }
        return MENU_NO_ACTION;
    }
    if(pressed&(J_A|J_START)) {
        if(menu_screen==MENU_LEVELS)return selected_level;
        if(!menu_selection)return resume_allowed?MENU_RESUME:selected_level;
        if(resume_allowed && menu_selection==1)return MENU_RESTART;
        if(menu_selection==(resume_allowed?2:1))open_list();
        else if(!resume_allowed && menu_selection==2) {
            menu_player_selection=save_player;
            open_players();
        }
        else open_controls();
        return MENU_NO_ACTION;
    }
    direction=navigation(keys,pressed);
    if(!direction)return MENU_NO_ACTION;
    if(menu_screen==MENU_MAIN) {
        count=4;
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
