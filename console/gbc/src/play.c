/* Riding runtime. Original geometry is independent from the tile artwork. */
#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "runtime.h"
#include "bike_render16.h"
#include "riding_constants.h"
#include "world.h"
#include "menu.h"
#include "physics_core.h"
#include "splash.h"
#include "audio.h"
#include "save.h"
#include "result.h"
#ifdef WORLD_SIGNED_BG
#define HUD_FIRST_TILE 236
#define HUD_CLOCK_PAGE 0x8f
#else
#define HUD_FIRST_TILE 220
#define HUD_CLOCK_PAGE 0x8e
#endif

#pragma bank 5

#ifndef GAME_FRAME_INTERVAL
#define GAME_FRAME_INTERVAL 2
#endif
#if PH_HZ != 30 && PH_HZ != 60
#error Select the 30 or 60 Hz riding profile.
#endif
#if SAVE_LEVEL_COUNT != LEVEL_COUNT
#error Update the save format for the course catalogue.
#endif

const uint8_t game_step_interval=60/PH_HZ;
const uint8_t game_present_interval=GAME_FRAME_INTERVAL;
const uint8_t game_physics_hz=PH_HZ;
const uint8_t game_physics_state_bytes=sizeof(bike_t);
const uint8_t game_sprite_height=16;
const uint8_t game_head_oam_index=12;
const uint8_t game_object_oam_base=BIKE_OBJECT_OAM_BASE;
#define GAME_PHYSICS_STEPS (PH_HZ*GAME_FRAME_INTERVAL/60)
/* LEJATSZO.CPP accepts held volt keys after Ugroturelem=0.4 model seconds.
 * Its clock runs at 0.4368 model seconds per displayed second. Round up to
 * the first physics step strictly beyond the original threshold. */
#define GAME_VOLT_WAIT_STEPS ((uint8_t)(0.4/PH_H)+1U)
const uint8_t game_volt_wait_steps=GAME_VOLT_WAIT_STEPS;

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
volatile uint32_t game_previous_best;
volatile uint8_t game_player_index,game_new_record;
uint16_t game_camera_x, game_camera_y;
uint8_t game_object_active[LEVEL_OBJECT_MAX];
static uint8_t objects_empty_valid,objects_empty_apples;
/* Cache small coarse candidate sets; larger sets retain the full scan. */
static uint8_t objects_near_count,objects_near[4];
/* Shared exclusion proof for objects outside the ordered candidate list. */
uint16_t gbc_objects_empty_bounds[4];
static uint8_t previous, last_hud_state,result_details;
static uint8_t volt_wait,objects_valid,objects_apples,objects_used,object_phase;
static uint8_t visible_objects[LEVEL_OBJECT_MAX],visible_count;
/* Camera clipping changes at object.x-167 / object.x+8 and at
 * object.y-143 / object.y+8. Track those boundaries modulo 256, using
 * one cumulative four-bit count per axis. A presentation can move at
 * most eight pixels on each axis, so a crossing cannot wrap a count. */
static uint8_t visibility_regions[256],objects_region_x,objects_region_y;

static void build_visibility_regions(void) {
    const game_object_t *object;
    uint8_t i,x_count=0,y_count=0;
    memset(visibility_regions,0,sizeof(visibility_regions));
    for(i=0,object=level_objects;i<OBJECT_COUNT;++i,++object) {
        visibility_regions[(uint8_t)(object->x-167)]|=1;
        visibility_regions[(uint8_t)(object->x+8)]|=1;
        visibility_regions[(uint8_t)(object->y-143)]|=16;
        visibility_regions[(uint8_t)(object->y+8)]|=16;
    }
    i=0;
    do {
        uint8_t edges=visibility_regions[i];
        x_count+=edges&1;
        y_count+=edges&16;
        visibility_regions[i]=(x_count&15)|y_count;
    } while(++i);
}

static bike_screen_t screen;
static int16_t body_world[2],next_camera_x,next_camera_y;
static uint16_t camera_limit_x,camera_limit_y;
enum { CAMERA_UNPREPARED, CAMERA_PROJECTED, CAMERA_SAME_TILE };
static uint8_t camera_prepared;
#define body_world_x body_world[0]
#define body_world_y body_world[1]
static uint16_t clock_fraction;
static uint8_t clock_minutes,clock_seconds_tens,clock_seconds_ones,clock_centiseconds;
static const uint16_t hud_palette[] = {RGB_BLACK, RGB_BLACK, RGB_WHITE, RGB_WHITE};
#include "ui_font.h"
#include "clock_font.h"
/* Each HUD cell owns a pattern; upload only character pairs that changed. */
static uint8_t hud_characters[40],hud_pattern[16];
static uint8_t hud_apples,hud_minutes,hud_seconds_tens_digit,hud_seconds_ones_digit,hud_centiseconds;
const uint8_t game_hud_font_advance=4;

void gbc_video_body_world(int16_t *dest) __sdcccall(0);

static void project_camera(uint8_t jump) {
    int16_t x,y;
    gbc_video_body_world(body_world);
    x=body_world_x-80;y=body_world_y-68;
    if(x<0)x=0;
    if(y<0)y=0;
    if(x>camera_limit_x)x=camera_limit_x;
    if(y>camera_limit_y)y=camera_limit_y;
    if(!jump) {
        if(x>(int16_t)game_camera_x+8)x=game_camera_x+8;
        if(x<(int16_t)game_camera_x-8)x=game_camera_x-8;
        if(y>(int16_t)game_camera_y+8)y=game_camera_y+8;
        if(y<(int16_t)game_camera_y-8)y=game_camera_y-8;
    }
    next_camera_x=x;next_camera_y=y;
}

static void position_camera(uint8_t jump) {
    if(jump || !camera_prepared)project_camera(jump);
    game_camera_x=next_camera_x;game_camera_y=next_camera_y;
    camera_prepared=CAMERA_UNPREPARED;
}

void gbc_video_sprite_screen(bike_screen_t *dest) __sdcccall(0);

static void bike_screen(void) {
    screen.body_x=body_world_x-game_camera_x;
    screen.body_y=body_world_y-game_camera_y;
    gbc_video_sprite_screen(&screen);
}

void gbc_video_object16(uint8_t sprite,uint8_t x,uint8_t y,uint8_t tile,uint8_t prop) __sdcccall(0);
uint8_t gbc_objects_draw(const uint8_t *visible,uint8_t visible_count,uint8_t phase,uint8_t count,uint8_t right_first) __sdcccall(0);
#ifndef OBJECTS_VISIBLE_C_REFERENCE
typedef char objects_visible_layout[
    sizeof(game_object_t)==14 && offsetof(game_object_t,x)==0 &&
    offsetof(game_object_t,y)==2 && offsetof(world_level_t,object_count)==32 &&
    LEVEL_OBJECT_MAX<=64 ? 1 : -1];
uint8_t gbc_objects_visible(uint8_t *ids) __sdcccall(0);
#endif

static void draw_objects(void) {
    uint8_t i,n,sprite,x_key=(uint8_t)game_camera_x,y_key=(uint8_t)game_camera_y;
    /* The last eight pixels use the exact low byte as their key. A step
     * cannot cross a 256-pixel wrap between two ordinary nibble keys. */
    if(x_key<248)x_key=visibility_regions[x_key]&15;
    if(y_key<248)y_key=visibility_regions[y_key]&240;
#ifdef OBJECTS_VISIBLE_C_REFERENCE
    int16_t x,y;
    const game_object_t *object;
#endif
    if(!objects_valid || objects_region_x!=x_key || objects_region_y!=y_key
       || objects_apples!=game_apples_left) {
        objects_valid=1;objects_region_x=x_key;objects_region_y=y_key;
        objects_apples=game_apples_left;visible_count=0;
#ifdef OBJECTS_VISIBLE_C_REFERENCE
        for(i=0,object=level_objects;i<OBJECT_COUNT;++i,++object) {
            if(!game_object_active[i])continue;
            x=(int16_t)object->x-game_camera_x-8;
            y=(int16_t)object->y-game_camera_y-8;
            if(x>=-15 && x<160 && y>=-15 && y<136)visible_objects[visible_count++]=i;
        }
#else
        visible_count=gbc_objects_visible(visible_objects);
#endif
    }
    sprite=BIKE_OBJECT_OAM_BASE;
    if(visible_count) {
        n=visible_count>13?13:visible_count;
        if(object_phase>=visible_count)object_phase=0;
        sprite=gbc_objects_draw(visible_objects,visible_count,object_phase,n,game_frames&1);
        if(visible_count>1) {
            object_phase+=visible_count>n?n:1;
            if(object_phase>=visible_count)object_phase-=visible_count;
        }
    } else {
        object_phase=0;
    }
    for(i=sprite;i<objects_used;++i)move_sprite(i,0,0);
    objects_used=sprite;
}

/* Original inclusive radii: wheel819u, head653u. The near bank5 helper
 * preserves wrapping deltas and signed floor shifts, using exact products. */
uint8_t gbc_object_touch(const gbc_pose_t *pose,const game_object_t *obj,uint8_t head) __sdcccall(0);
void gbc_objects_bounds(uint16_t *bounds) __sdcccall(0);
uint8_t gbc_object_near(const game_object_t *obj,const uint16_t *bounds) __sdcccall(0);

static void objects_near_add(uint8_t i) {
    if(objects_near_count<sizeof(objects_near))objects_near[objects_near_count++]=i;
    else objects_empty_valid=0;
}

static void check_objects_near(const uint16_t *bounds) {
    uint8_t i,n,hit;
    const game_object_t *object;
    n=0;i=0;
    while(1) {
        if(objects_empty_apples==game_apples_left) {
            if(n==objects_near_count)break;
            i=objects_near[n++];
        } else {
            /* Continue every remaining original ID after an apple changes
             * flower eligibility in the middle of this scan. */
            objects_empty_valid=0;
            if(++i>=OBJECT_COUNT)break;
        }
        object=level_objects+i;
        if(!game_object_active[i] || (object->kind==1 && game_apples_left))continue;
        /* Keep the coarse rejection even for cached candidates: the
         * exact touch helper deliberately uses wrapping deltas. */
        if(!gbc_object_near(object,bounds)) {
            /* Clipping now proves this tail candidate excluded as well. */
            if(objects_empty_valid && n==objects_near_count) {--objects_near_count;break;}
            continue;
        }
        hit=gbc_object_touch(&gbc_bike.wheel[0],object,0)
            || gbc_object_touch(&gbc_bike.wheel[1],object,0)
            || gbc_object_touch(&gbc_bike.head,object,1);
        if(!hit)continue;
        if(object->kind==2) {
            game_object_active[i]=0;
            if(game_apples_left)--game_apples_left;
            if(object->gravity)physics_set_gravity(object->gravity);
            audio_effect(FX_APPLE);
        } else if(object->kind==1 && !game_apples_left)game_state=FINISHED;
        else if(object->kind==3){gbc_bike.alive=0;game_state=DEAD;audio_effect(FX_CRASH);}
    }
}

static void check_objects(void) {
    uint8_t i,hit,use_bounds;
    uint16_t bounds[4];
    const game_object_t *object;
    gbc_objects_bounds(bounds);
    /* The sparse-course touch predicate wraps signed world coordinates.
     * Clipping is equivalent away from the seam. At either signed extreme,
     * keep checking sparse objects against each circle directly. */
    use_bounds=OBJECT_COUNT>4 || (bounds[0] && bounds[1]!=65535U &&
                                  bounds[2] && bounds[3]!=65535U);
    if(use_bounds) {
        /* Active flags only clear between starts. Excluded objects stay out
         * while the bike rectangle remains inside this clipped proof. */
        if(objects_empty_valid && objects_empty_apples==game_apples_left
           && bounds[0]>=gbc_objects_empty_bounds[0] && bounds[1]<=gbc_objects_empty_bounds[1]
           && bounds[2]>=gbc_objects_empty_bounds[2] && bounds[3]<=gbc_objects_empty_bounds[3]) {
            if(objects_near_count)check_objects_near(bounds);
            goto objects_checked;
        }
        gbc_objects_empty_bounds[0]=gbc_objects_empty_bounds[2]=0;
        gbc_objects_empty_bounds[1]=gbc_objects_empty_bounds[3]=65535U;
    }
    objects_empty_valid=use_bounds;objects_empty_apples=game_apples_left;
    objects_near_count=0;
    for(i=0,object=level_objects;i<OBJECT_COUNT;++i,++object) {
        if(!game_object_active[i] || (object->kind==1 && game_apples_left))continue;
        if(use_bounds) {
            if(!gbc_object_near(object,bounds))continue;
            if(objects_empty_valid)objects_near_add(i);
        }
        hit=gbc_object_touch(&gbc_bike.wheel[0],object,0)
            || gbc_object_touch(&gbc_bike.wheel[1],object,0)
            || gbc_object_touch(&gbc_bike.head,object,1);
        if(!hit)continue;
        if(object->kind==2) {
            objects_empty_valid=0;
            game_object_active[i]=0;
            if(game_apples_left)--game_apples_left;
            if(object->gravity)physics_set_gravity(object->gravity);
            audio_effect(FX_APPLE);
        } else if(object->kind==1 && !game_apples_left)game_state=FINISHED;
        else if(object->kind==3){gbc_bike.alive=0;game_state=DEAD;audio_effect(FX_CRASH);}
    }
    /* Earlier flowers may have been skipped before the last apple unlocked
     * them. Do not publish that incomplete candidate set for the next call. */
    if(objects_empty_apples!=game_apples_left)objects_empty_valid=0;
objects_checked:
    if(game_state==FINISHED) {
        audio_update(0,0,0,0);
        game_previous_best=save_best(game_player_index,game_level_index);
        game_new_record=save_record(game_player_index,game_level_index,game_time_frames);
    }
}

uint8_t gbc_bike_bounded(void) __sdcccall(0);

static void clock_tick(void) {
    /* Advance by the same display-time units per completed physics step.
     * The whole centiseconds are constant, with at most one fractional carry. */
    uint8_t increment=(10000U*(60/PH_HZ))/5973U;
    clock_fraction+=(10000U*(60/PH_HZ))%5973U;
    if(clock_fraction>=5973U) {
        clock_fraction-=5973U;
        ++increment;
    }
    clock_centiseconds+=increment;
    if(clock_centiseconds<100)return;
    clock_centiseconds-=100;
    if(++clock_seconds_ones<10)return;
    clock_seconds_ones=0;
    if(++clock_seconds_tens<6)return;
    clock_seconds_tens=0;
    if(++clock_minutes==100)clock_minutes=0;
}

static void hud_text(const char *text,uint8_t first,uint8_t width) {
    uint8_t i,left,right;
    first>>=1;width=(width>>1)+first;
    for(i=first;i<width;++i) {
        left=(uint8_t)*text;if(left)++text;
        right=(uint8_t)*text;if(right)++text;
        if(left==hud_characters[i*2] && right==hud_characters[i*2+1])continue;
        hud_characters[i*2]=left;hud_characters[i*2+1]=right;
        ui_font_pair(left,right,hud_pattern);
        VBK_REG=1;set_bkg_data(HUD_FIRST_TILE+i,1,hud_pattern);
    }
    VBK_REG=0;
}

/* The HUD uses one opaque low plane and three blank rows for every glyph
 * pair. Within an initialized cell, only five high-plane bytes can change. */
static void draw_clock(void) __naked {
    __asm
        .macro clock_cell value,previous,patterns,offset,next
        ld a,(#value)
        ld hl,#previous
        cp (hl)
        jr z,next
        ld (hl),a
        ld de,#(patterns+3)
        ld c,#offset
        call clock_upload_rows
next:
        .endm
        ld a,#1
        ldh (#0x4f),a
        clock_cell _clock_centiseconds,_hud_centiseconds,_hud_digit_pairs,0xf3,clock_after_centiseconds
        clock_cell _clock_seconds_ones,_hud_seconds_ones_digit,_hud_seconds_ones,0xe3,clock_after_seconds_ones
        clock_cell _clock_seconds_tens,_hud_seconds_tens_digit,_hud_seconds_tens,0xd3,clock_after_seconds_tens
        clock_cell _clock_minutes,_hud_minutes,_hud_digit_pairs,0xc3,clock_after_minutes
        xor a
        ldh (#0x4f),a
        ret
clock_upload_rows:
        ld l,a
        ld h,#0
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,de
        ; Four clock cells start at byte C0 of the selected HUD page.
        ld d,#HUD_CLOCK_PAGE
        ld e,c
        ; Preload two rows. From a mode 0/1 STAT read through the final
        ; write takes at most 148 T, inside the 160-T double-speed mode 2
        ; that follows even the last accessible dot. E stays in this tile.
        ld a,(hl+)
        inc hl
        ld b,a
        ld a,(hl+)
        inc hl
        ld c,a
        di
clock_glyph_window:
        ldh a,(#0x41)
        and a,#2
        jr nz,clock_glyph_window
        ld a,b
        ld (de),a
        inc e
        inc e
        ld a,c
        ld (de),a
        inc e
        inc e
        .rept 2
        ld a,(hl+)
        inc hl
        ld (de),a
        inc e
        inc e
        .endm
        ld a,(hl)
        ld (de),a
        ei
        ret
    __endasm;
}

static void draw_hud(void) {
    uint8_t changed=last_hud_state!=game_state;
    last_hud_state=game_state;
    if(game_state==DEAD){hud_text("CRASH A/START RETRY B/SELECT MENU",0,40);return;}
    if(game_state==FINISHED)return;
    if(game_state==PAUSED){hud_text("PAUSED SELECT",0,40);return;}
    if(changed)hud_text("A:00                      TIME  00:00.00",0,40);
    if(hud_apples!=game_apples_left) {
        char apples[5]="A:00";
        hud_apples=game_apples_left;
        apples[2]='0'+game_apples_left/10;apples[3]='0'+game_apples_left%10;
        hud_text(apples,0,4);
    }
    draw_clock();
}

static void video_init(void) {
    uint8_t i,col,attribute=143;
#ifdef WORLD_SIGNED_BG
    LCDC_REG&=~LCDCF_BG8000;
#else
    LCDC_REG|=LCDCF_BG8000;
#endif
    world_game_assets();set_bkg_palette(7,1,hud_palette);
    ui_font_pair(0,0,hud_pattern);
    VBK_REG=1;
    for(i=0;i<20;++i)set_bkg_data(HUD_FIRST_TILE+i,1,hud_pattern);
    for(i=0;i<40;++i)hud_characters[i]=0;
    hud_apples=hud_minutes=hud_seconds_tens_digit=hud_seconds_ones_digit=hud_centiseconds=255;
    for(col=0;col<20;++col) {
        VBK_REG=1;set_win_tiles(col,0,1,1,&attribute);
        i=HUD_FIRST_TILE+col;VBK_REG=0;set_win_tiles(col,0,1,1,&i);
    }
    VBK_REG=0;move_win(7,136);
    bike_render_init();SPRITES_8x16;SHOW_BKG;SHOW_WIN;SHOW_SPRITES;
}

static void restore_game(void) {
    game_ready=0;DISPLAY_OFF;
    camera_prepared=CAMERA_UNPREPARED;objects_valid=0;objects_used=40;
    video_init();world_begin(game_camera_x,game_camera_y);
    gbc_video_body_world(body_world);
    bike_screen();bike_render_draw(&gbc_bike,&screen);draw_objects();draw_hud();
    DISPLAY_ON;game_ready=1;
}

static void start_game(void) {
    uint8_t i;
    audio_init();
    game_ready=0;DISPLAY_OFF;
    world_select(game_level_index);
    camera_limit_x=WORLD_WIDTH-160;camera_limit_y=WORLD_HEIGHT-144;
    physics_select_level(game_level_index);physics_reset_current();
    build_visibility_regions();
    objects_empty_valid=0;
    game_state=RIDING;game_apples_left=0;game_time_frames=0;clock_fraction=0;volt_wait=0;
    game_player_index=save_player;game_new_record=0;game_previous_best=0;
    last_hud_state=255;object_phase=0;result_details=0;
    clock_minutes=clock_seconds_tens=clock_seconds_ones=clock_centiseconds=0;
    for(i=0;i<OBJECT_COUNT;++i) {
        game_object_active[i]=1;
        if(level_objects[i].kind==2)++game_apples_left;
    }
    position_camera(1);restore_game();
}

void game_present(void) {
    uint16_t old_x=game_camera_x,old_y=game_camera_y;
#ifdef WORLD_SIGNED_BG
    uint8_t fine_scroll=camera_prepared==CAMERA_SAME_TILE;
#endif
    if(game_state==FINISHED && last_hud_state==FINISHED)return;
    bike_render_prepare(&gbc_bike);
    position_camera(0);
#ifdef WORLD_SIGNED_BG
    /* The prediction was made from this published tile. Its prepared scenery
     * stays hidden until a tile crossing. Reset and restore clear the hint. */
    if(fine_scroll)move_bkg((uint8_t)game_camera_x,(uint8_t)game_camera_y);
    else
#endif
        world_scroll(old_x,old_y,game_camera_x,game_camera_y);
    bike_screen();bike_render_draw(&gbc_bike,&screen);draw_objects();
    if(game_state==FINISHED) {
        game_ready=0;
        result_overlay(game_time_frames,game_previous_best);
        /* Save writes and LCD-off uploads cannot service effect timing.
         * Start the finish sound once its frozen result is fully visible. */
        audio_effect(FX_FINISH);
        last_hud_state=FINISHED;game_ready=1;
        return;
    }
    /* Publish the clock with every riding frame using changed glyph pairs.
     * Death text needs only one publication. */
    if(game_state==RIDING || last_hud_state!=game_state)draw_hud();
}

/* Within one tile, old and new pixel phases determine the time to cross its
 * edge. Rank the exact distance/speed fractions; equal ranks mean a diagonal.
 * Moving right uses (8-old)/(new-old), moving left (1+old)/(old-new).
 * Rows are the old phase, columns the new phase. 255 means no crossing. */
static const uint8_t crossing_rank[8][8]={
    {255,  21,  17,  14,  11,   8,   5,   1},
    {11, 255,  20,  16,  12,  10,   6,   2},
    {7,  15, 255,  19,  15,  11,   7,   3},
    {5,  11,  17, 255,  18,  13,   9,   4},
    {4,   9,  13,  18, 255,  17,  11,   5},
    {3,   7,  11,  15,  19, 255,  15,   7},
    {2,   6,  10,  12,  16,  20, 255,  11},
    {1,   5,   8,  11,  14,  17,  21, 255},
};

static uint8_t prediction_rank(uint16_t from,uint16_t to,uint16_t limit) {
    if(from==to)return 255;
    if(to>from ? (from|7U)>=limit : from<8)return 255;
    return crossing_rank[from&7][to&7];
}

/* Predict the next tile from the camera's pixel phase without moving the
 * published view. Rank 11 reaches its edge in two updates from the old
 * position. A more distant strip can use time left after suspension. */
static void prepare_next_view(uint16_t start,uint8_t late) {
    uint16_t changed,x,y;
    uint8_t same_tile;
    project_camera(0);
    x=next_camera_x;y=next_camera_y;
    changed=(x^game_camera_x)|(y^game_camera_y);
    same_tile=changed<8U;
    camera_prepared=same_tile?CAMERA_SAME_TILE:CAMERA_PROJECTED;
    if(changed && same_tile) {
        uint8_t tx=prediction_rank(game_camera_x,x,camera_limit_x);
        uint8_t ty=prediction_rank(game_camera_y,y,camera_limit_y);
        if(tx==255 && ty==255)changed=0;
        else {
            if(tx<=ty)x=x>game_camera_x?(game_camera_x|7U)+1:(game_camera_x&~7U)-1;
            if(ty<=tx)y=y>game_camera_y?(game_camera_y|7U)+1:(game_camera_y&~7U)-1;
#if defined(RIDING_PC_SCHEDULE) && GAME_FRAME_INTERVAL == 2
            if(late || (tx>11 && ty>11)) {
                uint8_t line;
                physics_prepare_spring(start);
                line=LY_REG;
                if(line<108 || line>=144)world_prepare(game_camera_x,game_camera_y,x,y,start);
                return;
            }
#endif
        }
    }
    if(changed)world_prepare(game_camera_x,game_camera_y,x,y,start);
#if defined(RIDING_PC_SCHEDULE) && GAME_FRAME_INTERVAL == 2
    physics_prepare_spring(start);
#else
    (void)late;
#endif
}

static void game_loop(void) BANKED;

void game_wait_first_frame(uint16_t start) NONBANKED {
    uint16_t now;
    do {
        __critical {
            now=sys_time;
            if(IF_REG&VBL_IFLAG)++now;
            if(now==start) {
                /* NOP also absorbs the IME-off HALT bug if an enabled
                 * interrupt becomes pending after the atomic check. */
                __asm halt
                      nop __endasm;
            }
        }
    } while(now==start);
}

void main(void) NONBANKED {
    game_loop();
}

static void game_loop(void) BANKED {
    uint8_t keys,pressed,input,substep,action,line;
    uint16_t start,now;
    uint16_t speed;
    DISPLAY_OFF;cpu_fast();game_state=MENU;game_level_index=0;
    save_init();audio_init();splash_show();
    menu_open(0,0);previous=joypad();game_ready=1;
    while(1) {
        vsync();__critical {start=sys_time;}
        keys=joypad();pressed=keys&~previous;previous=keys;
        speed=0;
        if((keys&J_A) && game_state==RIDING) {
            int32_t omega=Bike.turned?Bike.wheel[0].omega:Bike.wheel[1].omega;
            if(omega>32767L || omega< -32767L)speed=32768U;
            else if(omega<0)speed=0U-(uint16_t)omega;
            else speed=(uint16_t)omega;
        }
        audio_update(game_state==RIDING,keys&J_A,keys&J_B,speed);
        if(game_state==MENU || game_state==PAUSED) {
            if(pressed)audio_effect(FX_MENU);
            if(game_state==PAUSED && (pressed&J_SELECT))action=MENU_RESUME;
            else action=menu_tick(keys,pressed);
            if(action<LEVEL_COUNT){game_level_index=action;start_game();}
            else if(action==MENU_RESTART)start_game();
            else if(action==MENU_RESUME){game_state=RIDING;last_hud_state=255;restore_game();}
            ++game_frames;continue;
        }
        if((pressed&J_START) || (game_state==DEAD && (pressed&J_A))) {
            start_game();++game_frames;continue;
        }
        if(pressed&J_SELECT || ((game_state==DEAD || game_state==FINISHED) && (pressed&J_B))) {
            action=game_state==RIDING;
#ifdef RIDING_PC_SCHEDULE
            riding_spring_ready=0;
#endif
            game_state=action?PAUSED:MENU;
            audio_update(0,0,0,0);audio_effect(FX_MENU);
            menu_open(game_level_index,action);++game_frames;continue;
        }
        if(game_state==FINISHED && (pressed&J_A)) {
            if(++game_level_index==LEVEL_COUNT)game_level_index=0;
            start_game();++game_frames;continue;
        }
        if(game_state==FINISHED && (pressed&J_UP)) {
            action=last_hud_state!=FINISHED;
            if(result_details) {
                restore_game();game_ready=0;
                result_overlay(game_time_frames,game_previous_best);
            } else {
                game_ready=0;
                menu_result(game_level_index,game_time_frames,game_previous_best);
            }
            if(action)audio_effect(FX_FINISH);
            result_details=!result_details;last_hud_state=FINISHED;game_ready=1;
            ++game_frames;continue;
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
                    if(keys&J_LEFT)input|=GBC_ROTATE_LEFT;
                    if(keys&J_RIGHT)input|=GBC_ROTATE_RIGHT;
                    if(input&(GBC_ROTATE_LEFT|GBC_ROTATE_RIGHT))volt_wait=GAME_VOLT_WAIT_STEPS;
                }
                physics_step(input);++game_steps;game_time_frames+=60/PH_HZ;
                clock_tick();
                if(!gbc_bike.alive || !gbc_bike_bounded()){gbc_bike.alive=0;game_state=DEAD;audio_effect(FX_CRASH);}
                else check_objects();
                input&=GBC_GAS|GBC_BRAKE;
            }
        }
        if(game_state!=RIDING)audio_update(0,0,0,0);
        if(game_state==RIDING) {
            __critical {now=sys_time;line=LY_REG;if(IF_REG&VBL_IFLAG)++now;}
            if(now==start || ((uint16_t)(now-start)==1 && (line<108 || line>=144)))
                prepare_next_view(start,0);
            /* An overrun still waits for VBlank before sampling input.
             * Use that time with a new preparation deadline and keep the
             * original start for update timing. */
            else if(line<108 || line>=144)
                prepare_next_view(now-1,1);
#if defined(RIDING_PC_SCHEDULE) && GAME_FRAME_INTERVAL == 2
            /* A short tail can still fit the guarded geometry stage after
             * the last safe starting line for scenery. */
            else if(line<138)
                physics_prepare_spring(now-1);
#endif
        }
        ++game_frames;
        __critical {
            now=sys_time;
            if(IF_REG&VBL_IFLAG)++now;
            if((uint16_t)(now-start)>=GAME_FRAME_INTERVAL && game_overruns!=65535)++game_overruns;
        }
        while((uint16_t)(now-start)<GAME_FRAME_INTERVAL-1) {
            game_wait_first_frame(start);__critical {now=sys_time;}
        }
    }
}
