/* Riding runtime. Original geometry is independent from the tile artwork. */
#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
#include "runtime.h"
#include "bike_render16.h"
#include "riding_constants.h"
#include "world.h"
#include "menu.h"
#pragma bank 5

#ifndef GAME_FRAME_INTERVAL
#define GAME_FRAME_INTERVAL 2
#endif
#if PH_HZ != 30 && PH_HZ != 60
#error Select the 30 or 60 Hz riding profile.
#endif

const uint8_t game_step_interval=60/PH_HZ;
const uint8_t game_present_interval=GAME_FRAME_INTERVAL;
const uint8_t game_physics_hz=PH_HZ;
const uint8_t game_sprite_height=16;
const uint8_t game_head_oam_index=12;
const uint8_t game_object_oam_base=BIKE_OBJECT_OAM_BASE;
#define GAME_PHYSICS_STEPS (PH_HZ*GAME_FRAME_INTERVAL/60)

#undef WORLD_WIDTH
#undef WORLD_HEIGHT
#undef WORLD_ORIGIN_X_FP
#undef WORLD_ORIGIN_Y_FP
#undef OBJECT_COUNT
#define WORLD_WIDTH (game_world.width)
#define WORLD_HEIGHT (game_world.height)
#define WORLD_ORIGIN_X_FP (game_world.origin_x)
#define WORLD_ORIGIN_Y_FP (game_world.origin_y)
#define OBJECT_COUNT (game_world.object_count)
#define level_objects game_objects

#define RIDING 0
#define DEAD 1
#define FINISHED 2
#define PAUSED 3
#define MENU 4

volatile uint8_t game_state, game_apples_left, game_ready,game_level_index;
volatile uint16_t game_frames, game_steps, game_overruns;
volatile uint32_t game_time_frames;
uint16_t game_camera_x, game_camera_y;
uint8_t game_object_active[LEVEL_OBJECT_MAX];
static uint8_t previous, hud_counter, last_hud_state;
static uint8_t volt_wait,objects_valid,objects_apples,objects_used,object_phase;
static uint8_t visible_objects[LEVEL_OBJECT_MAX],visible_count;
static uint16_t objects_camera_x,objects_camera_y;
static uint8_t tiles[21], attrs[21];
static bike_screen_t screen;
static int16_t body_world[2];
#define body_world_x body_world[0]
#define body_world_y body_world[1]
static uint16_t clock_fraction;
static uint8_t clock_digits[6];
static const uint16_t hud_palette[] = {RGB_BLACK, RGB_BLACK, RGB_WHITE, RGB_WHITE};
/* 28 small glyphs fit the bank1 space between bike parts and object patterns. */
static const uint8_t glyph_tile[128] = {
    220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,
    220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,
    220,220,220,220,220,220,220,220,220,220,220,220,220,220,232,220,
    221,222,223,224,225,226,227,228,229,230,231,220,220,220,220,220,
    220,233,220,234,246,235,236,220,237,238,220,220,239,220,240,220,
    241,220,242,243,244,245,220,220,220,247,220,220,220,220,220,220,
    220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,
    220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,220,
};
static const uint8_t glyphs[][7] = {
    {0,0,0,0,0,0,0},
    {14,17,19,21,25,17,14},{4,12,4,4,4,4,14},{14,17,1,2,4,8,31},
    {30,1,1,14,1,1,30},{2,6,10,18,31,2,2},{31,16,16,30,1,1,30},
    {6,8,16,30,17,17,14},{31,1,2,4,8,8,8},{14,17,17,14,17,17,14},
    {14,17,17,15,1,2,12},{0,4,4,0,4,4,0},{0,0,0,0,0,4,4},
    {14,17,17,31,17,17,17},{14,17,16,16,16,17,14},
    {31,16,16,30,16,16,31},{31,16,16,30,16,16,16},
    {17,17,17,31,17,17,17},{14,4,4,4,4,4,14},{16,16,16,16,16,16,31},
    {17,25,25,21,19,19,17},{30,17,17,30,16,16,16},{30,17,17,30,20,18,17},
    {15,16,16,14,1,1,30},{31,4,4,4,4,4,4},{17,17,17,17,17,17,14},
    {30,17,17,17,17,17,30},{17,17,10,4,4,4,4}
};

void gbc_video_body_world(int16_t *dest) __sdcccall(0);

static void position_camera(uint8_t jump) {
    int16_t x,y;
    gbc_video_body_world(body_world);
    x=body_world_x-80;y=body_world_y-68;
    if(x<0)x=0;
    if(y<0)y=0;
    if(x>WORLD_WIDTH-160)x=WORLD_WIDTH-160;
    if(y>WORLD_HEIGHT-144)y=WORLD_HEIGHT-144;
    if(!jump) {
        if(x>(int16_t)game_camera_x+8)x=game_camera_x+8;
        if(x<(int16_t)game_camera_x-8)x=game_camera_x-8;
        if(y>(int16_t)game_camera_y+8)y=game_camera_y+8;
        if(y<(int16_t)game_camera_y-8)y=game_camera_y-8;
    }
    game_camera_x=x;game_camera_y=y;
}

void gbc_video_parts_screen(bike_screen_t *dest) __sdcccall(0);

static void bike_screen(void) {
    screen.body_x=body_world_x-game_camera_x;
    screen.body_y=body_world_y-game_camera_y;
    gbc_video_parts_screen(&screen);
}

void gbc_video_object16(uint8_t sprite,uint8_t x,uint8_t y,uint8_t tile,uint8_t prop) __sdcccall(0);
uint8_t gbc_objects_draw(const uint8_t *visible,uint8_t visible_count,uint8_t phase,uint8_t count,uint8_t right_first) __sdcccall(0);

static void draw_objects(void) {
    uint8_t i,n,sprite;
    int16_t x,y;
    const game_object_t *object;
    if(!objects_valid || objects_camera_x!=game_camera_x || objects_camera_y!=game_camera_y
       || objects_apples!=game_apples_left) {
        objects_valid=1;objects_camera_x=game_camera_x;objects_camera_y=game_camera_y;
        objects_apples=game_apples_left;visible_count=0;
        for(i=0,object=level_objects;i<OBJECT_COUNT;++i,++object) {
            if(!game_object_active[i])continue;
            x=(int16_t)object->x-game_camera_x-8;
            y=(int16_t)object->y-game_camera_y-8;
            if(x>=-15 && x<160 && y>=-15 && y<136)visible_objects[visible_count++]=i;
        }
    }
    n=visible_count>13?13:visible_count;
    if(object_phase>=visible_count)object_phase=0;
    sprite=gbc_objects_draw(visible_objects,visible_count,object_phase,n,game_frames&1);
    if(visible_count>1) {
        object_phase+=visible_count>n?n:1;
        if(object_phase>=visible_count)object_phase-=visible_count;
    }
    for(i=sprite;i<objects_used;++i)move_sprite(i,0,0);
    objects_used=sprite;
}

/* Original inclusive radii: wheel819u, head653u. The near bank5 helper
 * preserves wrapping deltas and signed floor shifts, using exact products. */
uint8_t gbc_object_touch(const gbc_pose_t *pose,const game_object_t *obj,uint8_t head) __sdcccall(0);
void gbc_objects_bounds(uint16_t *bounds) __sdcccall(0);
uint8_t gbc_object_near(const game_object_t *obj,const uint16_t *bounds) __sdcccall(0);

static void check_objects(void) BANKED {
    uint8_t i,hit,use_bounds=OBJECT_COUNT>4;
    uint16_t bounds[4];
    const game_object_t *object;
    /* Every collision radius is below one meter. Its object's integer
     * coordinate must lie within the three physical circles' integer bounds
     * expanded by one. Dense courses avoid three full tests per distant item. */
    if(use_bounds)gbc_objects_bounds(bounds);
    for(i=0,object=level_objects;i<OBJECT_COUNT;++i,++object) {
        if(!game_object_active[i] || (object->kind==1 && game_apples_left))continue;
        if(use_bounds && !gbc_object_near(object,bounds))continue;
        hit=gbc_object_touch(&gbc_bike.wheel[0],object,0)
            || gbc_object_touch(&gbc_bike.wheel[1],object,0)
            || gbc_object_touch(&gbc_bike.head,object,1);
        if(!hit)continue;
        if(object->kind==2) {
            game_object_active[i]=0;
            if(game_apples_left)--game_apples_left;
            if(object->gravity)physics_set_gravity(object->gravity);
        } else if(object->kind==1 && !game_apples_left)game_state=FINISHED;
        else if(object->kind==3){gbc_bike.alive=0;game_state=DEAD;}
    }
}

uint8_t gbc_bike_bounded(void) __sdcccall(0);

static void clock_tick(void) BANKED {
    uint8_t i;
    clock_fraction+=10000;
    while(clock_fraction>=5973) {
        clock_fraction-=5973;
        for(i=6;i;--i) {
            if(++clock_digits[i-1] < (i==3?6:10))break;
            clock_digits[i-1]=0;
        }
    }
}

static void hud_text(const char *text,uint8_t width) {
    uint8_t i,c;
    for(i=0;i<width;++i) {
        c=(uint8_t)*text;
        tiles[i]=c<128?glyph_tile[c]:220;
        if(c)++text;
    }
    VBK_REG=0;
    set_win_tiles(0,0,width,1,tiles);
}

static void draw_hud(void) {
    uint8_t i,width=last_hud_state==game_state?12:20;
    last_hud_state=game_state;
    if(game_state==DEAD){hud_text("CRASH START RETRY",20);return;}
    if(game_state==FINISHED){hud_text("FINISHED START RETRY",20);return;}
    if(game_state==PAUSED){hud_text("PAUSED SELECT",20);return;}
    /* Normal HUD uses fixed glyphs and six BCD digits: no text scan. */
    tiles[0]=233;tiles[1]=231;tiles[2]=game_apples_left>=10?221+game_apples_left/10:220;tiles[3]=221+game_apples_left%10;
    tiles[4]=221+clock_digits[0];tiles[5]=221+clock_digits[1];tiles[6]=231;
    tiles[7]=221+clock_digits[2];tiles[8]=221+clock_digits[3];tiles[9]=232;
    tiles[10]=221+clock_digits[4];tiles[11]=221+clock_digits[5];
    for(i=12;i<width;++i)tiles[i]=220;
    VBK_REG=0;set_win_tiles(0,0,width,1,tiles);
}

static void video_init(void) {
    uint8_t i,row,col,attribute=143;
    LCDC_REG|=LCDCF_BG8000;
    world_game_assets();set_bkg_palette(7,1,hud_palette);
    VBK_REG=1;
    for(i=0;i<sizeof(glyphs)/7;++i) {
        for(row=0;row<8;++row) {
            tiles[row*2]=255;tiles[row*2+1]=(row<7?glyphs[i][row]<<1:0);
        }
        set_bkg_data(220+i,1,tiles);
    }
    VBK_REG=1;
    for(col=0;col<20;++col)set_win_tiles(col,0,1,1,&attribute);
    VBK_REG=0;move_win(7,136);
    bike_render_init();SPRITES_8x16;SHOW_BKG;SHOW_WIN;SHOW_SPRITES;
}

static void restore_game(void) BANKED {
    game_ready=0;DISPLAY_OFF;
    objects_valid=0;objects_used=40;
    video_init();world_begin(game_camera_x,game_camera_y);
    gbc_video_body_world(body_world);
    bike_screen();bike_render_draw(&gbc_bike,&screen);draw_objects();draw_hud();
    DISPLAY_ON;game_ready=1;
}

static void start_game(void) BANKED {
    uint8_t i;
    game_ready=0;DISPLAY_OFF;
    world_select(game_level_index);physics_select_level(game_level_index);physics_reset_current();
    game_state=RIDING;game_apples_left=0;game_time_frames=0;clock_fraction=0;volt_wait=0;
    last_hud_state=255;hud_counter=0;object_phase=0;
    for(i=0;i<6;++i)clock_digits[i]=0;
    for(i=0;i<OBJECT_COUNT;++i) {
        game_object_active[i]=1;
        if(level_objects[i].kind==2)++game_apples_left;
    }
    position_camera(1);restore_game();
}

void game_present(void) BANKED {
    uint16_t old_x=game_camera_x,old_y=game_camera_y;
    bike_render_prepare(&gbc_bike);
    position_camera(0);world_scroll(old_x,old_y,game_camera_x,game_camera_y);
    bike_screen();bike_render_draw(&gbc_bike,&screen);draw_objects();
    if(last_hud_state!=game_state || ++hud_counter>=6){hud_counter=0;draw_hud();}
}

/* The next presentation uses the state just computed by physics. Prepare only
 * its offscreen map cells during otherwise idle time; camera publication keeps
 * the existing presentation/input schedule. */
static void prepare_next_view(uint16_t start) BANKED {
    int16_t body[2],x,y;
    uint8_t ahead_x,ahead_y,dx,dy,tx,ty;
    gbc_video_body_world(body);x=body[0]-80;y=body[1]-68;
    if(x<0)x=0;
    if(y<0)y=0;
    if(x>WORLD_WIDTH-160)x=WORLD_WIDTH-160;
    if(y>WORLD_HEIGHT-144)y=WORLD_HEIGHT-144;
    if(x>(int16_t)game_camera_x+8)x=game_camera_x+8;
    if(x<(int16_t)game_camera_x-8)x=game_camera_x-8;
    if(y>(int16_t)game_camera_y+8)y=game_camera_y+8;
    if(y<(int16_t)game_camera_y-8)y=game_camera_y-8;
    if((x>>3)==(game_camera_x>>3) && (y>>3)==(game_camera_y>>3)) {
        /* Fine scrolling leaves the same ring cells visible. Prepare the
         * next tile in the current direction while those cells stay pinned. */
        ahead_x=(x>(int16_t)game_camera_x && (game_camera_x&~7U)+8<=WORLD_WIDTH-160)
            || (x<(int16_t)game_camera_x && game_camera_x>=8);
        ahead_y=(y>(int16_t)game_camera_y && (game_camera_y&~7U)+8<=WORLD_HEIGHT-144)
            || (y<(int16_t)game_camera_y && game_camera_y>=8);
        if(ahead_x && ahead_y) {
            dx=x>(int16_t)game_camera_x?x-game_camera_x:game_camera_x-x;
            dy=y>(int16_t)game_camera_y?y-game_camera_y:game_camera_y-y;
            tx=x>(int16_t)game_camera_x?8-(game_camera_x&7):1+(game_camera_x&7);
            ty=y>(int16_t)game_camera_y?8-(game_camera_y&7):1+(game_camera_y&7);
            /* Prefer the boundary reached first at the current pixel rate.
             * A diagonal guess is useful when both boundaries coincide. */
            tx*=dy;ty*=dx;
            if(tx<ty)ahead_y=0;
            else if(tx>ty)ahead_x=0;
        }
        if(ahead_x && x>(int16_t)game_camera_x)
            x=(game_camera_x&~7U)+8;
        else if(ahead_x)
            x=(game_camera_x&~7U)-1;
        if(ahead_y && y>(int16_t)game_camera_y)
            y=(game_camera_y&~7U)+8;
        else if(ahead_y)
            y=(game_camera_y&~7U)-1;
    }
    if((x>>3)!=(game_camera_x>>3) || (y>>3)!=(game_camera_y>>3))
        world_prepare(game_camera_x,game_camera_y,(uint16_t)x,(uint16_t)y,start);
}

void main(void) NONBANKED {
    uint8_t keys,pressed,input,substep,tick,action,line;
    uint16_t start,now;
    DISPLAY_OFF;cpu_fast();game_state=MENU;game_level_index=0;
    menu_open(0,0);game_ready=1;
    while(1) {
        vsync();__critical {start=sys_time;}
        keys=joypad();pressed=keys&~previous;previous=keys;
        if(game_state==MENU || game_state==PAUSED) {
            if(game_state==PAUSED && (pressed&J_SELECT))action=MENU_RESUME;
            else action=menu_tick(keys,pressed);
            if(action<LEVEL_COUNT){game_level_index=action;start_game();}
            else if(action==MENU_RESUME){game_state=RIDING;last_hud_state=255;restore_game();}
            ++game_frames;continue;
        }
        if(pressed&J_START){start_game();++game_frames;continue;}
        if(pressed&J_SELECT || ((game_state==DEAD || game_state==FINISHED) && (pressed&J_B))) {
            action=game_state==RIDING;
            game_state=action?PAUSED:MENU;
            menu_open(game_level_index,action);++game_frames;continue;
        }
        if(game_state==FINISHED && (pressed&J_A)) {
            if(++game_level_index==LEVEL_COUNT)game_level_index=0;
            start_game();++game_frames;continue;
        }
        game_present();
        if(game_state==RIDING) {
            if(pressed&J_UP)physics_turn();
            input=0;
            if(keys&J_A)input|=GBC_GAS;
            if(keys&J_B)input|=GBC_BRAKE;
            for(substep=0;substep<GAME_PHYSICS_STEPS && game_state==RIDING;++substep) {
                if(volt_wait)--volt_wait;
                if(!substep && !volt_wait) {
                    if(pressed&J_LEFT)input|=GBC_ROTATE_LEFT;
                    if(pressed&J_RIGHT)input|=GBC_ROTATE_RIGHT;
                    if(input&(GBC_ROTATE_LEFT|GBC_ROTATE_RIGHT))volt_wait=(55*PH_HZ+59)/60;
                }
                physics_step(input);++game_steps;game_time_frames+=60/PH_HZ;
                for(tick=0;tick<60/PH_HZ;++tick)clock_tick();
                if(!gbc_bike.alive || !gbc_bike_bounded()){gbc_bike.alive=0;game_state=DEAD;}
                else check_objects();
                input&=GBC_GAS|GBC_BRAKE;
            }
        }
        if(game_state==RIDING) {
            __critical {now=sys_time;line=LY_REG;if(IF_REG&VBL_IFLAG)++now;}
            if(now==start || ((uint16_t)(now-start)==1 && (line<108 || line>=144)))
                prepare_next_view(start);
        }
        ++game_frames;
        __critical {
            now=sys_time;
            if(IF_REG&VBL_IFLAG)++now;
            if((uint16_t)(now-start)>=GAME_FRAME_INTERVAL && game_overruns!=65535)++game_overruns;
        }
        while((uint16_t)(now-start)<GAME_FRAME_INTERVAL-1) {
            vsync();__critical {now=sys_time;}
        }
    }
}
