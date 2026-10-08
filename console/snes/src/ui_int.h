// Shared by the parts of the menus (ui.c, ui_menu.c, ui_balls.c,
// ui_text.asm).
#ifndef UI_INT_H
#define UI_INT_H

#include <snes.h>
#include "core.h"
#include "ui_data.h"

// VRAM of the menus (word addresses):
#define UIV_BG_CHR    0x0000    // background, 4 bits (BG2)
#define UIV_TEXT_MAP  0x1C00    // text (BG3)
#define UIV_INTRO_CHR 0x2000    // intro picture, 4 bits (BG1)
#define UIV_INTRO_MAP 0x3C00
#define UIV_TEXT_CHR  0x4000    // the canvas, 2 bits, 32 columns of 28 tiles
#define UIV_BG_MAP    0x5C00
#define UIV_OBJ       0x6000    // sprites: helmet, balls

// The menus are made for 640x480; the screen shows them on a picture of
// 640x560, 40 pixels lower (Menueltolasy), scaled by 0.4.
#define UI_SHIFT_Y    40
#define UI_ROWS       28        // rows of tiles of the canvas
#define UI_COLS       32        // columns of tiles of the canvas (the screen)
#define UI_CANVAS_STRIDE 512    // bytes of a column of tiles in the canvas
#define UI_CANVAS_PAD 32        // bytes above its first row

// Keys of the menus (ui_keys):
#define K_UP     0x01
#define K_DOWN   0x02
#define K_LEFT   0x04
#define K_RIGHT  0x08
#define K_ENTER  0x10
#define K_ESC    0x20
#define K_PGUP   0x40
#define K_PGDN   0x80
#define K_ANY    0xFF

// Rows of a list (the original's Rubrikak, Rubrikak_tab):
#define UI_ITEMS    64
#define UI_ITEM_LEN 44
#define UI_TAB_LEN  20
extern char ui_items[UI_ITEMS][UI_ITEM_LEN];
extern char ui_tabs[UI_ITEMS][UI_TAB_LEN];

// Other texts of a list (preszovegek), y of the 640x480 menus:
#define UI_EXTRAS   12
typedef struct {
	s16 x, y;
	u8 center;
	char text[48];
} ui_extra_t;
extern ui_extra_t ui_extra[UI_EXTRAS];
extern u8 ui_nextra;

// A list to choose from (valaszt2), coordinates of the 640x480 menus:
typedef struct {
	char title[64];             // cim
	s16 x0, y0, dy;             // the rows
	s16 x0_tab;                 // the second column (tabs)
	s16 cimy;                   // the title
	u8 egykepen;                // rows on a screen of 480
	u8 esc;                     // B leaves (escelheto)
	u8 tabs;
	s16 kur;                    // the row chosen
	u16 n;                      // rows
} ui_list_t;

// ui_text.asm:
extern u8 ui_canvas[];
extern u8 ui_row_used[];
extern u8 ui_col_used[];
void ui_canvas_clear(void);
void ui_canvas_clear_all(void);
u16 ui_text_draw(u16 xpc, u16 y, const char* s);

// ui_menu.c:
extern u8 ui_ready;             // the VRAM holds the menus
extern u8 ui_balls_on;          // balls are drawn (not on Loading)
extern u8 ui_pal;               // a PAL console: 50 frames a second
void ui_reset(void);
void ui_enter(void);
void ui_leave(void);
void ui_begin(void);
void ui_end(void);
void ui_text(s16 x, s16 y, const char* s);
void ui_text_center(s16 x, s16 y, const char* s);
u16 ui_text_len(const char* s);
s16 ui_y(s16 y);
void ui_helmet(s16 x, s16 y);
void ui_helmet_off(void);
void ui_frame(void);
void ui_intro_screen(void);
u16 ui_keys(void);
u16 ui_wait(u16 keys);
s16 ui_choose(ui_list_t* l);
void ui_list_init(ui_list_t* l, const char* title, s16 x0, s16 y0, s16 dy, u8 egykepen);
void ui_strcpy(char* d, const char* s);
void ui_strcat(char* d, const char* s);
void ui_itoa(u16 v, char* d);

// ui_balls.c:
void ui_balls_init(u16 seed);
void ui_balls_step(u16 frames);
void ui_balls_draw(s16 dy);
void ui_balls_hide(void);
void ui_balls_upload(void);
void ui_balls_vram_reset(void);

#endif
