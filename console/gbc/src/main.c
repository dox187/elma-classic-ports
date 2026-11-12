/* Graphics/data milestone. Camera controls deliberately do not move a bike. */
#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
#include "assets.h"

uint16_t camera_x, camera_y;
volatile uint16_t viewer_frames;
volatile uint8_t viewer_ready, viewer_overruns;
static uint8_t hidden, flipped;
static uint8_t previous;
static uint8_t strip_tiles[21], strip_attrs[21];

static const uint16_t status_palette[] = {RGB_BLACK, RGB_WHITE, RGB_WHITE, RGB_WHITE};
/* blank, V, I, E, W: a persistent VIEW label distinguishes this from gameplay. */
static const uint8_t status_tiles[] = {
    0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
    0,0,0x44,0,0x44,0,0x44,0,0x28,0,0x10,0,0,0,0,0,
    0,0,0x38,0,0x10,0,0x10,0,0x10,0,0x38,0,0,0,0,0,
    0,0,0x38,0,0x20,0,0x38,0,0x20,0,0x38,0,0,0,0,0,
    0,0,0x44,0,0x44,0,0x54,0,0x54,0,0x28,0,0,0,0,0
};

static void load_strip(uint16_t tx, uint16_t ty, uint8_t vertical, uint8_t count) {
    const world_chunk_t *chunk;
    uint16_t local;
    uint16_t x = tx, y = ty;
    uint8_t i;
    for (i = 0; i < count; ++i) {
        strip_tiles[i] = strip_attrs[i] = 0;
        if (x < WORLD_WIDTH / 8 && y < WORLD_HEIGHT / 8) {
            chunk = &world_chunks[(y >> 4) * WORLD_CHUNKS_X + (x >> 5)];
            local = (y & 15) * 32 + (x & 31);
            SWITCH_ROM(chunk->bank);
            strip_attrs[i] = chunk->data[512 + local];
            strip_tiles[i] = chunk->data[local];
        }
        if (vertical) ++y; else ++x;
    }
    VBK_REG = 1;
    set_bkg_tiles(tx & 31, ty & 31, vertical ? 1 : count, vertical ? count : 1, strip_attrs);
    VBK_REG = 0;
    set_bkg_tiles(tx & 31, ty & 31, vertical ? 1 : count, vertical ? count : 1, strip_tiles);
}

static void fill_view(void) {
    uint16_t y, left = camera_x >> 3, top = camera_y >> 3;
    for (y = top; y < top + 19; ++y)
        load_strip(left, y, 0, 21);
}

static void update_view(uint16_t old_x, uint16_t old_y) {
    uint16_t edge, left = camera_x >> 3, top = camera_y >> 3;
    if ((old_x >> 3) != left) {
        edge = camera_x > old_x ? left + 20 : left;
        load_strip(edge, top, 1, 19);
    }
    if ((old_y >> 3) != top) {
        edge = camera_y > old_y ? top + 18 : top;
        load_strip(left, edge, 0, 21);
    }
}

static void draw_bike(void) {
    uint8_t row, col, sprite = 0;
    int16_t x, y;
    for (row = 0; row < 4; ++row) {
        for (col = 0; col < 4; ++col, ++sprite) {
            x = (int16_t)BIKE_X - (int16_t)camera_x - 16 + (flipped ? 3-col : col) * 8;
            y = (int16_t)BIKE_Y - (int16_t)camera_y - 16 + row * 8;
            set_sprite_tile(sprite, 232 + sprite);
            set_sprite_prop(sprite, S_BANK | (flipped ? S_FLIPX : 0));
            if (hidden || x < -7 || x >= 160 || y < -7 || y >= 136)
                move_sprite(sprite, 0, 0);
            else move_sprite(sprite, x + 8, y + 16);
        }
    }
}

static void draw_objects(void) {
    uint8_t i, row, col, sprite = 16, tile, palette;
    int16_t x, y;
    for (i = 16; i < 40; ++i) move_sprite(i, 0, 0);
    for (i = 0; i < OBJECT_COUNT && sprite <= 36; ++i) {
        x = (int16_t)level_objects[i].x - (int16_t)camera_x - 8;
        y = (int16_t)level_objects[i].y - (int16_t)camera_y - 8;
        if (x < -15 || x >= 160 || y < -15 || y >= 136) continue;
        palette = level_objects[i].kind == 2 ? 1 : 2;
        tile = palette == 1 ? 248 : 252;
        for (row = 0; row < 2; ++row)
            for (col = 0; col < 2; ++col, ++sprite) {
                set_sprite_tile(sprite, tile + row * 2 + col);
                set_sprite_prop(sprite, S_BANK | palette);
                move_sprite(sprite, x + col * 8 + 8, y + row * 8 + 16);
            }
    }
}

static void reset_camera(void) {
#if BIKE_X > 80
    camera_x = BIKE_X - 80;
#else
    camera_x = 0;
#endif
#if BIKE_Y > 68
    camera_y = BIKE_Y - 68;
#else
    camera_y = 0;
#endif
#if BIKE_X - 80 > WORLD_WIDTH - 160
    camera_x = WORLD_WIDTH - 160;
#endif
#if BIKE_Y - 68 > WORLD_HEIGHT - 144
    camera_y = WORLD_HEIGHT - 144;
#endif
}

void main(void) {
    uint8_t keys, pressed, step, i, tile;
    uint16_t old_x, old_y, started;
    DISPLAY_OFF;
    cpu_fast();
    LCDC_REG |= LCDCF_BG8000;
    set_bkg_palette(0, 7, bg_palette);
    set_bkg_palette(7, 1, status_palette);
    set_sprite_palette(0, 1, bike_palette);
    set_sprite_palette(1, 2, object_palette);
    SWITCH_ROM(1);
    VBK_REG = 0;
#if WORLD_PATTERN_COUNT >= 256
    set_bkg_data(0, 128, world_patterns);
    set_bkg_data(128, 128, world_patterns + 2048);
#else
    set_bkg_data(0, WORLD_PATTERN_COUNT, world_patterns);
#endif
    VBK_REG = 1;
#if WORLD_PATTERN_COUNT > 256
    set_bkg_data(0, (uint8_t)(WORLD_PATTERN_COUNT - 256), world_patterns + 4096);
#endif
    set_sprite_data(232, 16, bike_tiles);
    set_sprite_data(248, 8, object_tiles);
    set_bkg_data(224, 5, status_tiles);
    for (i = 0; i < 20; ++i) {
        tile = 15; /* bank 1, palette 7 */
        set_win_tiles(i, 0, 1, 1, &tile);
    }
    VBK_REG = 0;
    for (i = 0; i < 20; ++i) {
        tile = i >= 8 && i < 12 ? 225 + i - 8 : 224;
        set_win_tiles(i, 0, 1, 1, &tile);
    }
    reset_camera();
    fill_view();
    move_bkg((uint8_t)camera_x, (uint8_t)camera_y);
    move_win(7, 136);
    draw_bike();
    draw_objects();
    SPRITES_8x8;
    SHOW_BKG;
    SHOW_WIN;
    SHOW_SPRITES;
    DISPLAY_ON;
    viewer_ready = 1;
    while (1) {
        vsync();
        __critical { started = sys_time; }
        keys = joypad();
        pressed = keys & ~previous;
        previous = keys;
        step = keys & J_A ? 4 : 2;
        old_x = camera_x;
        old_y = camera_y;
        if (keys & J_LEFT) camera_x = camera_x < step ? 0 : camera_x - step;
        if (keys & J_RIGHT) camera_x += step;
        if (keys & J_UP) camera_y = camera_y < step ? 0 : camera_y - step;
        if (keys & J_DOWN) camera_y += step;
        if (camera_x > WORLD_WIDTH - 160) camera_x = WORLD_WIDTH - 160;
        if (camera_y > WORLD_HEIGHT - 144) camera_y = WORLD_HEIGHT - 144;
        if (pressed & J_B) flipped ^= 1;
        if (pressed & J_SELECT) hidden ^= 1;
        if (pressed & J_START) {
            viewer_ready = 0;
            DISPLAY_OFF;
            reset_camera();
            fill_view();
            DISPLAY_ON;
            viewer_ready = 1;
        } else update_view(old_x, old_y);
        move_bkg((uint8_t)camera_x, (uint8_t)camera_y);
        draw_bike();
        draw_objects();
        ++viewer_frames;
        if (!(pressed & J_START)) {
            __critical {
                if (sys_time != started && viewer_overruns != 255) ++viewer_overruns;
            }
        }
    }
}
