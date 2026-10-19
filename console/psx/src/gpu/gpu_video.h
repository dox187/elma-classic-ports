// Video output of the PlayStation version: display modes, the VRAM map and
// the GPU command lists. Used by psx_platform.cpp (menus and other 8-bit
// pictures of the core), gpu_menukep.cpp (menus by changed rectangles) and
// gpu_draw.cpp (the game view).
//
// The game view is 320x240 progressive, half the original's 640x480 in both
// directions: the same part of the world is seen, the pixels are four times
// as large. 640x480 interlaced would need two 640x480 frame buffers for a
// steady picture (all of VRAM); 640x240 leaves too little VRAM for the LGR's
// graphics. At 320x240 three frame buffers (the GPU draws one while one is
// shown and the next is built) and every picture of the LGR fit, so nothing
// of the LGR has to stay in RAM. The menus keep the original 640x480 picture
// (interlaced).
//
// VRAM map, 16-bit cells of the 1024x512 VRAM:
//
//   menu mode, 640x480 interlaced, single buffered:
//     (0,0)-(639,479)     the displayed picture
//     (0,480)-(127,511)   8-bit staging rows: changed rectangles of the
//                         core's 8-bit picture go through here, 256x32
//                         pixels at a time (one after the other in a
//                         command list), and are drawn with its palette
//                         onto the display
//     (640,511)           that palette (CLUT), kept out of the textures
//   game mode, 320x240 progressive, triple buffered:
//     (0,0) (320,0) (0,240)  the three frame buffers
//     (320,240)-(639,479)    CLUTs of the textures, made again whenever the
//                            game mode starts (gpu_lgr.cpp)
//   both modes:
//     (640,0)-(1023,510)  textures of the LGR (gpu_lgr.cpp), uploaded once
//     (128,480)-(639,511) per LGR; neither mode draws there, so they survive
//                         the menus (but for the debug font's corner,
//                         (960,448)-(1023,511))
#pragma once

#include <stdint.h>

// The core's 8-bit picture is 640x480 in the menus.
const int GV_MENU_W = 640, GV_MENU_H = 480;
// The game view: half the original 640x480 in both directions, so the same
// part of the world is seen.
const int GV_GAME_W = 320, GV_GAME_H = 240;

// Where the LGR textures may go (gpu_lgr.cpp): cells x 640..1023.
const int GV_TEX_X = 640;
// The debug font of the error screen (FntLoad) is kept in this corner of the
// texture area, so an error message does not destroy textures; the menu
// palette in the last row of the texture area.
const int GV_FONT_X = 960, GV_FONT_Y = 448;
const int GV_MENU_CLUT_X = 640, GV_MENU_CLUT_Y = 511;
// Game mode: the textures' CLUTs from here (x 320..639, rows 240..479).
const int GV_GAME_DATA_X = 320, GV_GAME_DATA_Y = 240;

// --- Menu mode -----------------------------------------------------------

// Presents the core's 640x480 8-bit picture (its rows) with its palette
// (256 VRAM colors). Only the rectangles given by gv_menu_dirty since the
// last call are sent, or the whole picture if there were none, or if the
// display was showing something else. rows NULL: a black picture.
void gv_menu_present(unsigned char* const* rows, const uint16_t* clut, bool clut_changed);
// The rows of the core's 640x480 8-bit picture (psx_platform.cpp), top row
// first: the menus draw straight into it (gpu_menukep.cpp). The array stays
// the same; the picture is only in RAM between gv_menu_picture_ensure (also
// done by gv_menu_rows and the locks of the picture) and
// gv_menu_picture_free (an LGR is loaded, the game view starts).
unsigned char** gv_menu_rows();
void gv_menu_picture_ensure();
void gv_menu_picture_free();
// The menus' tile pictures are given back until a menu is drawn again
// (gpu_menukep.cpp, while an LGR is read).
void gv_menu_images_free();
// Marks a rectangle of the picture (inclusive coordinates) for the next
// gv_menu_present.
void gv_menu_dirty(int x1, int y1, int x2, int y2);
// The next gv_menu_present sends only the marked rectangles, none if there
// are none (the display still shows the rest).
void gv_menu_partial();
// Increases whenever the menu picture on the display may differ from the
// core's picture outside the marked rectangles (a mode change, a full
// present); gpu_menukep.cpp redraws everything when it changes.
uint32_t gv_menu_serial();
// The display no longer shows the core's picture (error screen): the next
// gv_menu_present sends all of it.
void gv_menu_invalidate();

// --- Game mode -------------------------------------------------------------

// Starts a game frame: switches to the game mode if needed and opens a new
// command list. Returns the VRAM x, y of the frame buffer it will be drawn
// into (the drawing area and offset are already set to it).
void gv_game_begin(int* fb_x, int* fb_y);
// Space for a primitive of the given size in 32-bit words, appended to the
// list in drawing order (the caller sets its length and code). On overflow
// it returns a scratch area that is not drawn.
uint32_t* gv_prim_words(int words);
template <class T> inline T* gv_prim() { return (T*)gv_prim_words(sizeof(T) / 4); }
// Closes the list and queues it. The previous frame is finished first:
// finish(fb_x, fb_y, data) runs when its picture is complete and may read it
// back and draw more into it (the timer), then it is shown at the next
// vertical blank.
typedef void (*gv_finish_fn)(int fb_x, int fb_y, void* data);
void gv_game_end(gv_finish_fn finish, void* data);
// Words used by the last frame's list, the capacity, overflows so far.
void gv_prim_stats(uint32_t* used, uint32_t* capacity, uint32_t* overflows);
// True while the game mode is on (its textures and CLUTs are in VRAM).
bool gv_in_game_mode();
// Called when the game mode starts (CLUTs are rebuilt by gpu_lgr.cpp).
extern void (*gv_game_mode_hook)();

// --- Both --------------------------------------------------------------------

// The pictures of the level for the GPU (gpu_level.cpp) are given back when
// the RAM is needed in the menus after a game (false: nothing to give), and
// made again when the game view is drawn next.
bool gv_level_release();
// All of the level's data for the GPU is given back (a level is loaded).
void gv_level_free();

void gv_init();
// Waits until the GPU is idle and leaves the display as it is (error screen).
void gv_stop();
// From the vertical blank interrupt.
void gv_vblank();
// psx_platform.cpp: scan lines since the start (about 15734 a second), and
// the bookkeeping after every presented picture (frame rate, pad).
uint32_t gv_lines();
void gv_frame_done(bool game_view);
// A clock for measuring: root counter 2 at an eighth of the system clock
// (4233600 a second), made 32 bits wide by its overflow interrupt.
const uint32_t GV_CLOCK_HZ = 4233600;
void gv_clock_init();
uint32_t gv_clock();
// Sums of gv_clock ticks spent in parts of the program, printed with the
// frame rate (psx_platform.cpp) and readable by the tests.
enum {
	GV_PROF_FRAME,       // between two presents of a game frame
	GV_PROF_DRAW,        // building the game view's command list
	GV_PROF_PRESENT,     // presenting (waiting for the GPU included)
	GV_PROF_GPU_WAIT,    // waiting for the GPU to finish a frame
	GV_PROF_MENU,        // presenting a menu picture
	GV_PROF_MENU_STEP,   // the menu balls' movement (leptetgolyo)
	GV_PROF_MENU_DRAW,   // drawing a menu frame (gpu_menukep.cpp)
	GV_PROF_DEBUG,       // the bookkeeping after a frame (psx_platform.cpp)
	GV_PROF_COUNT
};
extern "C" uint32_t gv_prof[GV_PROF_COUNT];
