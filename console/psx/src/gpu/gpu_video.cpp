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

// Two command lists: one is drawn by the GPU while the next is built.
// (A frame of the game view takes 2500-3500 words.) The menu mode builds
// its lists in them too.
const int PRIM_WORDS = 8 * 1024;
uint32_t prim_buffers[2][PRIM_WORDS];

// --- Menu mode -----------------------------------------------------------

// The changed rectangles of the core's 8-bit picture are sent in pieces of
// at most 256x16 pixels: each piece is copied into a command list as a
// transfer to the staging rows (they are 256 texels, 128 cells, wide, so
// they stay out of the textures' strip of gpu_lgr.cpp), followed by the
// sprite that draws it with the palette. A list goes to the GPU when full
// or at the end of a present, while the next one is built in the other
// buffer; nothing waits for the GPU to finish a present.
const int STAGE_Y = 480, STAGE_ROWS = 32, STAGE_W = 256;
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

// The menu command list being built (ml_start NULL: none) and the buffers
// the GPU may still read.
uint32_t* ml_start = 0;
uint32_t* ml_cur = 0;
uint32_t* ml_end = 0;
uint32_t* ml_last = 0;
int ml_index = 0;
bool ml_busy[2] = {false, false};

void ml_wait() {
	DrawSync(0);
	ml_busy[0] = ml_busy[1] = false;
}

void ml_begin() {
	if (ml_busy[ml_index]) ml_wait();
	ml_start = ml_cur = prim_buffers[ml_index];
	ml_end = ml_start + PRIM_WORDS;
	DR_AREA* area = (DR_AREA*)ml_cur;
	ml_cur += sizeof(DR_AREA) / 4;
	DR_OFFSET* offset = (DR_OFFSET*)ml_cur;
	ml_cur += sizeof(DR_OFFSET) / 4;
	setDrawAreaXY(area, 0, 0, GV_MENU_W - 1, GV_MENU_H - 1);
	setDrawOffset(offset, 0, 0);
	catPrim(area, offset);
	ml_last = (uint32_t*)offset;
}

// A packet of the given size in words (its tag included), linked after the
// last one.
uint32_t* ml_packet(int words) {
	uint32_t* p = ml_cur;
	ml_cur += words;
	catPrim(ml_last, p);
	ml_last = p;
	return p;
}

void ml_send() {
	if (!ml_start) return;
	termPrim(ml_last);
	DrawOTag(ml_start);
	ml_busy[ml_index] = true;
	ml_index ^= 1;
	ml_start = 0;
}

// Rows y..y+h-1, columns x1..x2 (from a multiple of 4 pixels, a multiple
// of 4 wide, at most 256 columns, at most STAGE_ROWS rows) of the picture.
void present_band(unsigned char* const* rows, int x1, int x2, int y, int h) {
	const int w = x2 - x1 + 1;
	const int words = w * h / 4;
	// The transfer (its command, place and size, then the pixels) in
	// packets of at most 255 words, the cache flush, the texture page, the
	// sprite:
	const int need = 3 + words + (3 + words) / 255 + 1 + 2 + 2 + sizeof(SPRT) / 4 + 4;
	if (ml_start && ml_cur + need > ml_end) ml_send();
	if (!ml_start) ml_begin();
	int left = 3 + words;  // words of the transfer still to place
	int room = left < 255 ? left : 255;
	uint32_t* o = ml_packet(1 + room);
	setlen(o, room);
	o++;
	o[0] = 0xA0000000;
	o[1] = ((uint32_t)STAGE_Y << 16) | 0;
	o[2] = ((uint32_t)h << 16) | (uint32_t)(w / 2);
	o += 3;
	room -= 3;
	left -= 3;
	for (int j = 0; j < h; ++j) {
		const uint32_t* in = (const uint32_t*)(rows[y + j] + x1);
		int n = w / 4;
		while (n > 0) {
			if (!room) {
				room = left < 255 ? left : 255;
				o = ml_packet(1 + room);
				setlen(o, room);
				o++;
			}
			const int k = n < room ? n : room;
			memcpy(o, in, k * 4);
			o += k;
			in += k;
			n -= k;
			room -= k;
			left -= k;
		}
	}
	// The texture cache may hold the staging rows' old texels:
	uint32_t* flush = ml_packet(2);
	setlen(flush, 1);
	flush[1] = 0x01000000;
	DR_TPAGE* tpage = (DR_TPAGE*)ml_packet(sizeof(DR_TPAGE) / 4);
	// Drawing to the displayed field is allowed (interlace):
	setDrawTPage(tpage, 1, 0, getTPage(1, 0, 0, STAGE_Y));
	SPRT* sp = (SPRT*)ml_packet(sizeof(SPRT) / 4);
	setSprt(sp);
	setShadeTex(sp, 1);
	setRGB0(sp, 128, 128, 128);
	setXY0(sp, x1, y);
	setUV0(sp, 0, STAGE_Y & 255);
	setWH(sp, w, h);
	sp->clut = getClut(MENU_CLUT_X, MENU_CLUT_Y);
}

void present_rect(unsigned char* const* rows, int x1, int y1, int x2, int y2) {
	if (x1 < 0) x1 = 0;
	if (y1 < 0) y1 = 0;
	if (x2 > GV_MENU_W - 1) x2 = GV_MENU_W - 1;
	if (y2 > GV_MENU_H - 1) y2 = GV_MENU_H - 1;
	// Whole words of the picture:
	x1 &= ~3;
	x2 |= 3;
	if (x2 > GV_MENU_W - 1) x2 = GV_MENU_W - 1;
	if (x1 > x2 || y1 > y2) return;
	for (int y = y1; y <= y2; y += STAGE_ROWS) {
		const int h = y2 - y + 1 < STAGE_ROWS ? y2 - y + 1 : STAGE_ROWS;
		for (int x = x1; x <= x2; x += STAGE_W) {
			const int xe = x + STAGE_W - 1 < x2 ? x + STAGE_W - 1 : x2;
			present_band(rows, x, xe, y, h);
		}
	}
}

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
	ml_start = 0;
	ml_busy[0] = ml_busy[1] = false;
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
	// The core's 8-bit picture is not drawn in the game:
	gv_menu_picture_free();
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

void gv_stop() {
	DrawSync(0);
	ml_busy[0] = ml_busy[1] = false;
}

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

void gv_menu_present(unsigned char* const* rows, const uint16_t* clut, bool clut_changed) {
	const uint32_t t0 = gv_clock();
	if (mode != MODE_MENU) enter_menu_mode();
	if (clut_changed || !menu_clut_loaded) {
		ml_wait();
		RECT r = {MENU_CLUT_X, MENU_CLUT_Y, 256, 1};
		LoadImage(&r, (const uint32_t*)clut);
		menu_clut_loaded = true;
	}
	if (!rows) {
		// No picture: black.
		ml_wait();
		FILL* fill = (FILL*)prim_buffers[0];
		setFill(fill);
		setRGB0(fill, 0, 0, 0);
		setXY0(fill, 0, 0);
		setWH(fill, GV_MENU_W, GV_MENU_H);
		termPrim(fill);
		DrawOTag((const uint32_t*)fill);
		DrawSync(0);
		menu_valid = false;
		menu_serial++;
		dirty_count = 0;
		dirty_overflow = false;
		dirty_partial = false;
		gv_prof[GV_PROF_MENU] += gv_clock() - t0;
		return;
	}
	long area = 0;
	for (int i = 0; i < dirty_count; ++i)
		area += (long)(dirty[i].x2 - dirty[i].x1 + 1) * (dirty[i].y2 - dirty[i].y1 + 1);
	if (!menu_valid || !dirty_partial || dirty_overflow || area > (long)GV_MENU_W * GV_MENU_H / 2) {
		present_rect(rows, 0, 0, GV_MENU_W - 1, GV_MENU_H - 1);
		// Someone else's picture (or a big change): the menus redraw all.
		if (!dirty_partial) menu_serial++;
	} else {
		for (int i = 0; i < dirty_count; ++i)
			present_rect(rows, dirty[i].x1, dirty[i].y1, dirty[i].x2, dirty[i].y2);
	}
	ml_send();
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
