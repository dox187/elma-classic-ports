// Video output of the PlayStation version, see gpu_video.h.
#include <hwregs_c.h>
#include <psxapi.h>
#include <psxetc.h>
#include <psxgpu.h>
#include <string.h>

#include "gpu_video.h"

extern "C" uint32_t gv_prof[GV_PROF_COUNT];
uint32_t gv_prof[GV_PROF_COUNT];
void (*gv_game_mode_hook)() = 0;

namespace {

enum Mode { MODE_NONE, MODE_MENU, MODE_GAME };
Mode mode = MODE_NONE;

// --- Menu mode -----------------------------------------------------------

// The staging rows are 256 texels (128 cells) wide, so they stay out of
// the textures' strip (gpu_lgr.cpp) and a piece is one sprite. Its two
// halves are used in turn, so a piece can be sent while the previous one is
// drawn.
const int STAGE_Y = 480, STAGE_ROWS = 16, STAGE_W = 256;
const int MENU_CLUT_X = GV_MENU_CLUT_X, MENU_CLUT_Y = GV_MENU_CLUT_Y;

uint32_t menu_serial = 1;
bool menu_valid = false;  // the display shows the core's last picture
bool menu_clut_loaded = false;

struct dirty_rect {
	int16_t x1, y1, x2, y2;
};
const int MAX_DIRTY = 48;
dirty_rect dirty[MAX_DIRTY];
int dirty_count = 0;
bool dirty_overflow = false;
bool dirty_partial = false;

// One band of a rectangle: its rows (when narrower than the picture) and the
// primitives that draw it from the staging rows.
// (The SDK's LoadImage sends whole blocks of 16 words: zero words, GPU
// no-ops, follow a piece.)
uint32_t band_pixels[2][STAGE_W * STAGE_ROWS / 4 + 16];
struct band_prims {
	DR_AREA area;
	DR_OFFSET offset;
	DR_TPAGE tpage;
	SPRT sprite;
};
band_prims bands[2];
int band_turn = 0;

void enter_menu_mode() {
	DrawSync(0);
	DISPENV disp;
	SetDefDispEnv(&disp, 0, 0, GV_MENU_W, GV_MENU_H);
	disp.isinter = 1;
	PutDispEnv(&disp);
	mode = MODE_MENU;
	menu_valid = false;
	menu_clut_loaded = false;
	menu_serial++;
}

// Sends rows y..y+h-1, columns x1..x2 (a multiple of 4 pixels from x1, at
// most 256 columns, at most STAGE_ROWS rows) of the picture.
void present_band(const unsigned char* pixels, int x1, int x2, int y, int h) {
	const int w = x2 - x1 + 1;
	const int turn = band_turn;
	band_turn ^= 1;
	// The half of the staging rows, the pixels and the primitives of this
	// turn were last used two pieces ago; everything sent until then must be
	// drawn.
	if (turn == 0) DrawSync(0);
	unsigned char* out = (unsigned char*)band_pixels[turn];
	for (int row = 0; row < h; ++row) memcpy(out + row * w, pixels + (y + row) * GV_MENU_W + x1, w);
	memset(out + h * w, 0, 64);
	const int stage_y = STAGE_Y + turn * STAGE_ROWS;
	RECT r = {0, (int16_t)stage_y, (int16_t)(w / 2), (int16_t)h};
	LoadImage(&r, band_pixels[turn]);

	band_prims* band = &bands[turn];
	setDrawAreaXY(&band->area, 0, 0, GV_MENU_W - 1, GV_MENU_H - 1);
	setDrawOffset(&band->offset, 0, 0);
	// Drawing to the displayed field is allowed (interlace):
	setDrawTPage(&band->tpage, 1, 0, getTPage(1, 0, 0, stage_y));
	SPRT* sp = &band->sprite;
	setSprt(sp);
	setShadeTex(sp, 1);
	setRGB0(sp, 128, 128, 128);
	setXY0(sp, x1, y);
	setUV0(sp, 0, stage_y & 255);
	setWH(sp, w, h);
	sp->clut = getClut(MENU_CLUT_X, MENU_CLUT_Y);
	catPrim(&band->area, &band->offset);
	catPrim(&band->offset, &band->tpage);
	catPrim(&band->tpage, sp);
	termPrim(sp);
	DrawOTag((const uint32_t*)&band->area);
}

void present_rect(const unsigned char* pixels, int x1, int y1, int x2, int y2) {
	if (x1 < 0) x1 = 0;
	if (y1 < 0) y1 = 0;
	if (x2 > GV_MENU_W - 1) x2 = GV_MENU_W - 1;
	if (y2 > GV_MENU_H - 1) y2 = GV_MENU_H - 1;
	// Whole cells, an even number of them (LoadImage drops an odd halfword):
	x1 &= ~3;
	x2 |= 3;
	if (x2 > GV_MENU_W - 1) x2 = GV_MENU_W - 1;
	if (x1 > x2 || y1 > y2) return;
	for (int y = y1; y <= y2; y += STAGE_ROWS) {
		const int h = y2 - y + 1 < STAGE_ROWS ? y2 - y + 1 : STAGE_ROWS;
		for (int x = x1; x <= x2; x += STAGE_W) {
			const int xe = x + STAGE_W - 1 < x2 ? x + STAGE_W - 1 : x2;
			present_band(pixels, x, xe, y, h);
		}
	}
}

// --- Game mode -------------------------------------------------------------

const int FB_COUNT = 3;
const int FB_X[FB_COUNT] = {0, 320, 0}, FB_Y[FB_COUNT] = {0, 0, 240};

// The frame buffer to show at the next vertical blank (-1: none), and the
// one on the display.
volatile int show_request = -1;
volatile int shown = 0;
volatile uint32_t vblanks = 0;
uint32_t last_end_vblank = 0;

// Two command lists: one is drawn by the GPU while the next is built.
// (A frame of the game view takes 2500-3500 words.)
const int PRIM_WORDS = 8 * 1024;
uint32_t prim_buffers[2][PRIM_WORDS];
uint32_t scratch[64];
int prim_index = 0;
uint32_t* prim_cur = 0;
uint32_t* prim_end = 0;
uint32_t* prim_last = 0;
uint32_t prim_used = 0, prim_overflows = 0;

struct list_head {
	DR_AREA area;
	DR_OFFSET offset;
	DR_STP stp;
};

int drawing_fb = 1;     // the frame buffer of the frame being built
int pending_fb = -1;    // queued for the GPU, shown after the next frame
gv_finish_fn pending_finish = 0;
void* pending_data = 0;

void enter_game_mode() {
	DrawSync(0);
	DISPENV disp;
	SetDefDispEnv(&disp, FB_X[0], FB_Y[0], GV_GAME_W, GV_GAME_H);
	disp.isinter = 0;
	show_request = -1;
	PutDispEnv(&disp);
	shown = 0;
	// The first frames show black until the first picture is ready:
	static FILL clear[2];
	for (int i = 0; i < 2; ++i) {
		setFill(&clear[i]);
		setRGB0(&clear[i], 0, 0, 0);
		clear[i].x0 = 0;
		clear[i].y0 = (uint16_t)(i * 240);
		clear[i].w = 640;
		clear[i].h = 240;
	}
	catPrim(&clear[0], &clear[1]);
	termPrim(&clear[1]);
	DrawOTag((const uint32_t*)&clear[0]);
	DrawSync(0);
	pending_fb = -1;
	drawing_fb = 1;
	mode = MODE_GAME;
	if (gv_game_mode_hook) gv_game_mode_hook();
}

void show_at_vblank(int fb) {
	show_request = fb;
}

} // namespace

// Called by the vertical blank interrupt (psx_platform.cpp): the display
// start moves to the requested frame buffer. One GP1 write, so it does not
// disturb the main program's GPU commands.
void gv_vblank() {
	vblanks++;
	const int fb = show_request;
	if (fb >= 0) {
		GPU_GP1 = 0x05000000 | FB_X[fb] | (FB_Y[fb] << 10);
		shown = fb;
		show_request = -1;
	}
}

void gv_init() {
	mode = MODE_NONE;
}

namespace {
volatile uint32_t clock_high = 0;
void clock_overflow() { clock_high += 0x10000; }
}

void gv_clock_init() {
	// System clock / 8, an interrupt at 0xffff, again and again:
	TIMER_CTRL(2) = 0x0260;
	InterruptCallback(IRQ_TIMER2, clock_overflow);
}

uint32_t gv_clock() {
	uint32_t high, low;
	do {
		high = clock_high;
		low = TIMER_VALUE(2) & 0xffff;
	} while (high != clock_high);
	return high | low;
}

void gv_stop() { DrawSync(0); }

void gv_menu_dirty(int x1, int y1, int x2, int y2) {
	if (x1 > x2 || y1 > y2) return;
	if (dirty_count == MAX_DIRTY) {
		dirty_overflow = true;
		return;
	}
	dirty[dirty_count].x1 = (int16_t)x1;
	dirty[dirty_count].y1 = (int16_t)y1;
	dirty[dirty_count].x2 = (int16_t)x2;
	dirty[dirty_count].y2 = (int16_t)y2;
	dirty_count++;
}

uint32_t gv_menu_serial() { return menu_serial; }

void gv_menu_partial() { dirty_partial = true; }

void gv_menu_invalidate() {
	menu_valid = false;
	menu_serial++;
}

void gv_menu_present(const unsigned char* pixels, const uint16_t* clut, bool clut_changed) {
	const uint32_t t0 = gv_clock();
	if (mode != MODE_MENU) enter_menu_mode();
	if (clut_changed || !menu_clut_loaded) {
		DrawSync(0);
		RECT r = {MENU_CLUT_X, MENU_CLUT_Y, 256, 1};
		LoadImage(&r, (const uint32_t*)clut);
		menu_clut_loaded = true;
	}
	long area = 0;
	for (int i = 0; i < dirty_count; ++i)
		area += (long)(dirty[i].x2 - dirty[i].x1 + 1) * (dirty[i].y2 - dirty[i].y1 + 1);
	if (!menu_valid || !dirty_partial || dirty_overflow || area > (long)GV_MENU_W * GV_MENU_H / 2) {
		present_rect(pixels, 0, 0, GV_MENU_W - 1, GV_MENU_H - 1);
		// Someone else's picture (or a big change): the menus redraw all.
		if (!dirty_partial) menu_serial++;
	} else {
		for (int i = 0; i < dirty_count; ++i)
			present_rect(pixels, dirty[i].x1, dirty[i].y1, dirty[i].x2, dirty[i].y2);
	}
	// The core draws the next picture into the same memory:
	DrawSync(0);
	menu_valid = true;
	dirty_count = 0;
	dirty_overflow = false;
	dirty_partial = false;
	gv_prof[GV_PROF_MENU] += gv_clock() - t0;
}

void gv_game_begin(int* fb_x, int* fb_y) {
	if (mode != MODE_GAME) enter_game_mode();
	// Not the frame buffer queued before nor the one on the display (a
	// requested change may still wait for its vertical blank):
	int fb = (drawing_fb + 1) % FB_COUNT;
	if (fb == pending_fb) fb = (fb + 1) % FB_COUNT;
	drawing_fb = fb;
	prim_index ^= 1;
	prim_cur = prim_buffers[prim_index];
	prim_end = prim_cur + PRIM_WORDS;
	list_head* head = (list_head*)prim_cur;
	prim_cur += sizeof(list_head) / 4;
	setDrawAreaXY(&head->area, FB_X[fb], FB_Y[fb], FB_X[fb] + GV_GAME_W - 1, FB_Y[fb] + GV_GAME_H - 1);
	setDrawOffset(&head->offset, FB_X[fb], FB_Y[fb]);
	setDrawStp(&head->stp, 0, 0);
	catPrim(&head->area, &head->offset);
	catPrim(&head->offset, &head->stp);
	prim_last = (uint32_t*)&head->stp;
	*fb_x = FB_X[fb];
	*fb_y = FB_Y[fb];
}

uint32_t* gv_prim_words(int words) {
	if (prim_cur + words > prim_end) {
		prim_overflows++;
		return scratch;
	}
	uint32_t* p = prim_cur;
	prim_cur += words;
	catPrim(prim_last, p);
	prim_last = p;
	return p;
}

void gv_game_end(gv_finish_fn finish, void* data) {
	const uint32_t t0 = gv_clock();
	termPrim(prim_last);
	prim_used = (uint32_t)(prim_cur - prim_buffers[prim_index]);

	// The previous frame: wait for its picture, let the caller finish it,
	// then show it.
	DrawSync(0);
	const uint32_t t1 = gv_clock();
	gv_prof[GV_PROF_GPU_WAIT] += t1 - t0;
	if (pending_fb >= 0) {
		if (pending_finish) {
			pending_finish(FB_X[pending_fb], FB_Y[pending_fb], pending_data);
			DrawSync(0);
		}
		// Not faster than the display:
		while (vblanks == last_end_vblank) {
		}
		last_end_vblank = vblanks;
		show_at_vblank(pending_fb);
	}
	// The frame buffer of this frame must not be on the display:
	while (shown == drawing_fb) {
	}
	DrawOTag(prim_buffers[prim_index]);
	pending_fb = drawing_fb;
	pending_finish = finish;
	pending_data = data;
	gv_prof[GV_PROF_PRESENT] += gv_clock() - t0;
}

void gv_prim_stats(uint32_t* used, uint32_t* capacity, uint32_t* overflows) {
	*used = prim_used;
	*capacity = PRIM_WORDS;
	*overflows = prim_overflows;
}

bool gv_in_game_mode() { return mode == MODE_GAME; }
