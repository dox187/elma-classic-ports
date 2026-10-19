// Platform layer of the PlayStation version, the counterpart of
// desktop/F_CLI/CLI_PLATFORM.CPP and desktop/F_SDL/SDL_PLATFORM.CPP.
//
// Video (gpu/gpu_video.h): the menus and the other screens of the core are
// one 640x480 8-bit picture, as in the terminal version; its changed parts
// are sent to VRAM and drawn with the game's palette onto a 640x480
// interlaced display. The game view is drawn by the GPU (gpu/gpu_draw.cpp)
// on a 320x240 display, unless the build uses the software renderer
// (ELMA_PSX_GPU off), whose picture is shown like the menus.
//
// Time: scan lines counted by root counter 1 (about 15734 a second on
// NTSC), summed up at every vertical blank.
//
// Pad: pad 1 through the BIOS driver; the buttons press the keys of the
// player's controls and send the menu keys, like the handheld version.
// The SDK's headers come first: <psxapi.h> defines SEEK_SET as an enum.
#include <hwregs_c.h>
#include <psxapi.h>
#include <psxetc.h>
#include <psxgpu.h>
#include <psxpad.h>

#include "all.h"
#include "psx_file.h"
#include "gpu/gpu_video.h"
#ifdef ELMA_PSX_PCDRV
#include "psx_pcdrv.h"
#else
#include "cd/cdfile.h"
#include "cd/cdtrack.h"
#endif

int Win_95 = 1;
int Margrafikus = 0;
int Locky0_alul = 0;

// Read by the emulator tests (test/core_boot_test.lua) through the symbol
// map. Keep the layout.
struct psx_debug_state {
	uint32_t magic;          // "ELMA" once main has started
	uint32_t presents;       // frames shown
	uint32_t game_frames;    // frames of the game view (bottom-up lock)
	uint32_t menu_chars;     // menu keys sent by the pad
	int32_t bike_x_mm;       // Pmot1->kor1.r, millimeters
	int32_t bike_y_mm;
	uint32_t heap_used;      // bytes allocated
	uint32_t heap_max;
	uint32_t fps_x100;       // frames a second over the last 5 seconds
	uint32_t errors;         // hiba() calls
	uint32_t ram_files;      // bytes in the RAM file store
	uint32_t ram_8mb;        // 1 if the 8 MB development RAM was found
};
extern "C" {
psx_debug_state psx_debug;
}

namespace {

const int W = 640, H = 480;

// The picture of the core (menus and other screens), top row first. It is
// in RAM only while such screens are drawn: it is given back while an LGR
// is loaded and while the game view (drawn by the GPU) is on
// (gv_menu_picture_free), in small pieces of CHUNK_ROWS rows, so that it
// fits into the heap again however it was cut up meanwhile.
const int CHUNK_ROWS = 8;
const int CHUNKS = (H + CHUNK_ROWS - 1) / CHUNK_ROWS;
unsigned char* chunks[CHUNKS];
unsigned char* rows_top[H];
unsigned char* rows[H];
bool locked = false;

// The palette in VRAM format; bit 15 keeps color 0 from being transparent.
uint32_t clut_words[128];
uint16_t* const clut = reinterpret_cast<uint16_t*>(clut_words);
bool clut_dirty = true;

// Scan line clock:
const long LINES_PER_SECOND = 15734;
volatile uint32_t line_total = 0;
volatile uint16_t line_last = 0;
volatile uint32_t vblank_count = 0;
uint32_t stopper_start = 0;

// Pad states, sampled at every vertical blank so that a short press is not
// lost while the game draws a slow frame; events() applies them in order.
uint8_t pad_buffers[2][34];
volatile uint16_t pad_queue[32];
volatile uint32_t pad_queue_head = 0, pad_queue_tail = 0;
uint16_t pad_sampled = 0;

void sample_pad() {
	// BIOS pad buffer: [0] 0 when a pad answered, [2..3] buttons, active low.
	uint16_t buttons = 0;
	if (pad_buffers[0][0] == 0) buttons = (uint16_t)~(pad_buffers[0][2] | pad_buffers[0][3] << 8);
	if (buttons == pad_sampled || pad_queue_head - pad_queue_tail >= 32) return;
	pad_queue[pad_queue_head % 32] = buttons;
	pad_queue_head++;
	pad_sampled = buttons;
}

void vblank_callback() {
	gv_vblank();
	sample_pad();
	const uint16_t now = (uint16_t)TIMER_VALUE(1);
	uint16_t lines = (uint16_t)(now - line_last);
	// Without the counter (some emulators) a field is about 262 lines:
	if (lines == 0) lines = 262;
	line_total += lines;
	line_last = now;
	vblank_count++;
}

uint32_t lines_now() {
	uint32_t total;
	uint16_t last, now;
	do {
		total = line_total;
		last = line_last;
		now = (uint16_t)TIMER_VALUE(1);
	} while (total != line_total);
	// The counter runs on, so this is exact even if a vertical blank is
	// still waiting to be counted:
	return total + (uint16_t)(now - last);
}

// 6 bits per color, as a VGA card takes them.
uint16_t vga_to_vram(const unsigned char* c) {
	return (uint16_t)(0x8000 | (c[0] >> 1) | (c[1] >> 1) << 5 | (c[2] >> 1) << 10);
}

uint32_t last_present_vblank = 0;
uint32_t fps_start_vblank = 0, fps_frames = 0;

void update_debug() {
	HeapUsage usage;
	GetHeapUsage(&usage);
	psx_debug.heap_used = usage.alloc;
	psx_debug.heap_max = usage.alloc_max;
	psx_debug.ram_files = (uint32_t)psx_file_ram_used();
	if (Pmot1) {
		psx_debug.bike_x_mm = (int32_t)(Pmot1->kor1.r.x * 1000.0);
		psx_debug.bike_y_mm = (int32_t)(Pmot1->kor1.r.y * 1000.0);
	}
}

void events();

uint32_t prof_start[GV_PROF_COUNT];

// The frame rate and where the time went, every 5 seconds.
void count_frame() {
	psx_debug.presents++;
	fps_frames++;
	const uint32_t vblanks = vblank_count - fps_start_vblank;
	if (vblanks >= 300) {
		psx_debug.fps_x100 = fps_frames * 6000 / vblanks;
		printf("elma: %u.%02u fps, heap %u KB (max %u KB)\n", psx_debug.fps_x100 / 100,
		       psx_debug.fps_x100 % 100, psx_debug.heap_used / 1024, psx_debug.heap_max / 1024);
		// (The measuring clock over the same 5 seconds, a check:)
		static uint32_t clock_start = 0;
		const uint32_t clock_now = gv_clock();
		printf("elma: clock %u ticks in %u vblanks\n", (unsigned)(clock_now - clock_start), (unsigned)vblanks);
		clock_start = clock_now;
		// Milliseconds a frame:
		static const char* const names[GV_PROF_COUNT] = {"frame", "draw", "present", "gpu-wait", "menu",
		                                                          "menu-step", "menu-draw", "debug"};
		printf("elma: ms/frame");
		for (int i = 0; i < GV_PROF_COUNT; ++i) {
			const uint32_t lines = gv_prof[i] - prof_start[i];
			prof_start[i] = gv_prof[i];
			const uint32_t tenths = lines / (GV_CLOCK_HZ / 10000) / fps_frames;
			if (lines) printf(" %s %u.%u", names[i], (unsigned)(tenths / 10), (unsigned)(tenths % 10));
		}
		printf("\n");
		fps_frames = 0;
		fps_start_vblank = vblank_count;
	}
	const uint32_t t0 = gv_clock();
	update_debug();
	events();
	gv_prof[GV_PROF_DEBUG] += gv_clock() - t0;
}

void present() {
	// Not faster than the display:
	if (VSync(-1) == (int)last_present_vblank) VSync(0);
	last_present_vblank = VSync(-1);

	gv_menu_present(rows_top, clut, clut_dirty);
	clut_dirty = false;
	count_frame();
}

// Pad buttons (bits of psxpad.h) and what they do, as in the handheld
// version: a control of the player (pressing its key) and a menu key.
enum Control { NO_CONTROL, GAS, BRAKE, ROTATE_LEFT, ROTATE_RIGHT, TURN, VIEW, TIME, LEAVE };
struct button_action {
	uint16_t bit;
	Control control;
	int menu;
};
const button_action actions[] = {
	{PAD_UP, GAS, MK_UP},
	{PAD_DOWN, BRAKE, MK_DOWN},
	{PAD_LEFT, ROTATE_LEFT, MK_LEFT},
	{PAD_RIGHT, ROTATE_RIGHT, MK_RIGHT},
	{PAD_CROSS, GAS, MK_ENTER},
	{PAD_CIRCLE, BRAKE, MK_ESC},
	{PAD_SQUARE, TURN, 0},
	{PAD_TRIANGLE, VIEW, 0},
	{PAD_L1, TIME, MK_PGUP},
	{PAD_R1, TURN, MK_PGDOWN},
	{PAD_SELECT, LEAVE, MK_ESC},
	{PAD_START, NO_CONTROL, MK_ENTER},
};
const int ACTION_COUNT = sizeof(actions) / sizeof(actions[0]);
int action_key[ACTION_COUNT];
unsigned char key_count[256]; // pad buttons holding each key
uint16_t pad_down = 0;

int chars[16];
int char_head = 0, char_count = 0;

void push_char(int c) {
	if (char_count == 16) return;
	chars[(char_head + char_count++) % 16] = c;
	psx_debug.menu_chars++;
}

int control_key(Control control) {
	if (control == LEAVE) return DIK_ESCAPE;
	if (!State) return 0;
	const jatekosopciok& player = State->opciok1;
	switch (control) {
	case GAS: return player.billgaz;
	case BRAKE: return player.billfek;
	case ROTATE_LEFT: return player.billugras2;
	case ROTATE_RIGHT: return player.billugras1;
	case TURN: return player.billfordul;
	case VIEW: return player.billview;
	case TIME: return player.billtime;
	default: return 0;
	}
}

void apply_buttons(uint16_t buttons) {
	const uint16_t changed = buttons ^ pad_down;
	if (!changed) return;
	for (int i = 0; i < ACTION_COUNT; ++i) {
		if (!(changed & actions[i].bit)) continue;
		if (buttons & actions[i].bit) {
			const int key = control_key(actions[i].control);
			action_key[i] = key > 0 && key < 256 ? key : 0;
			if (action_key[i]) ++key_count[action_key[i]];
			if (actions[i].menu) push_char(actions[i].menu);
		} else {
			if (action_key[i]) --key_count[action_key[i]];
			action_key[i] = 0;
		}
	}
	pad_down = buttons;
}

void events() {
	while (pad_queue_tail != pad_queue_head) {
		apply_buttons(pad_queue[pad_queue_tail % 32]);
		pad_queue_tail++;
	}
}

// The error screen: the lines in the debug font until X or Start (wait) or
// for good.
void message_screen(const char* title, char* a, char* b, char* c, bool wait) {
	printf("elma: %s\n", title);
	if (a) printf("elma:   %s\n", a);
	if (b) printf("elma:   %s\n", b);
	if (c) printf("elma:   %s\n", c);
	if (!Margrafikus) return;
	// Over the last menu picture (a black one if it is not in RAM):
	gv_menu_present(chunks[0] ? rows_top : NULL, clut, true);
	FntLoad(GV_FONT_X, GV_FONT_Y);
	const int font = FntOpen(32, 32, W - 64, H - 64, 1, 1024);
	const uint16_t start = pad_down;
	while (true) {
		FntPrint(font, "%s\n\n", title);
		if (a) FntPrint(font, "%s\n", a);
		if (b) FntPrint(font, "%s\n", b);
		if (c) FntPrint(font, "%s\n", c);
		if (wait) FntPrint(font, "\nPress X or START");
		FntFlush(font);
		DrawSync(0);
		VSync(0);
		events();
		if (wait && (pad_down & ~start & (PAD_CROSS | PAD_START))) break;
	}
	// The next present draws the whole picture again:
	char_count = 0;
	gv_menu_invalidate();
}

int in_error = 0;

bool has_8mb() {
	// With 2 MB the RAM repeats every 2 MB; with the 8 MB of development
	// units and the emulator option it does not.
	static volatile uint32_t probe;
	volatile uint32_t* alias = (volatile uint32_t*)((uintptr_t)&probe + 0x600000);
	probe = 0x12345678;
	*alias = 0x55aa55aa;
	return probe == 0x12345678 && *alias == 0x55aa55aa;
}

// Calls fn with the stack at top; fn does not return.
__attribute__((noreturn)) void run_on_stack(void (*fn)(), uint32_t top) {
	__asm__ volatile("move $sp, %0\n\tjalr %1\n\tnop\n" : : "r"(top), "r"(fn) : "memory", "ra");
	__builtin_unreachable();
}

}

uint32_t gv_lines() { return lines_now(); }

void gv_frame_done(bool game_view) {
	if (game_view) psx_debug.game_frames++;
	count_frame();
}

extern "C" char _end[];
void game_main();

// The stack (the game needs about 4 KB, test/mem_test.py):
const uint32_t STACK_SIZE = 16 * 1024;

int main(int, char**) {
	psx_debug.magic = 0x454C4D41; // "ELMA"
	printf("elma: PlayStation version starting\n");
	if (has_8mb()) {
		// The stack moves to the top of the 8 MB and the heap takes all the
		// rest from the end of the program. Nothing has been allocated yet.
		psx_debug.ram_8mb = 1;
		const uint32_t start = ((uint32_t)_end + 15) & ~15u;
		const uint32_t stack_top = 0x80800000 - 16;
		InitHeap((void*)start, stack_top - STACK_SIZE - start);
		run_on_stack(game_main, stack_top);
	}
	// The SDK lets the heap grow up to the stack at the top of the 2 MB;
	// keep STACK_SIZE for the stack.
	const uint32_t start = ((uint32_t)_end + 15) & ~15u;
	InitHeap((void*)start, 0x80200000 - STACK_SIZE - start);
	game_main();
	return 0;
}

namespace { bool graph_reset = false; }

void ddinit() {
	if (!graph_reset) ResetGraph(0);
	graph_reset = true;
	SetVideoMode(MODE_NTSC);
	gv_init();

	// Root counter 1 counts scan lines (clock source: horizontal blank):
	TIMER_CTRL(1) = 0x0100;
	line_last = (uint16_t)TIMER_VALUE(1);
	VSyncCallback(vblank_callback);
	gv_clock_init();

	InitPAD(pad_buffers[0], 34, pad_buffers[1], 34);
	StartPAD();
	ChangeClearPAD(0);

	SetDispMask(1);
	Margrafikus = 1;
}

void ddfinish() { gv_stop(); }

void gv_menu_picture_ensure() {
	if (chunks[0]) return;
	for (int c = 0; c < CHUNKS; ++c) {
		const int n = H - c * CHUNK_ROWS < CHUNK_ROWS ? H - c * CHUNK_ROWS : CHUNK_ROWS;
		chunks[c] = (unsigned char*)malloc(n * W);
		// After a game of a big level the room is made by the level's
		// pictures for the GPU, which are made again for the next game:
		if (!chunks[c] && gv_level_release()) chunks[c] = (unsigned char*)malloc(n * W);
		if (!chunks[c]) {
			HeapUsage usage;
			GetHeapUsage(&usage);
			printf("elma: out of memory: the picture of the menus, %d of %d pieces made, %u allocated\n", c, CHUNKS,
			       (unsigned)usage.alloc);
			hiba((char*)"Out of memory:", (char*)"the picture of the menus");
		}
		memset(chunks[c], 0, n * W);
		for (int r = 0; r < n; ++r) rows_top[c * CHUNK_ROWS + r] = chunks[c] + r * W;
	}
	// What the display shows is not this picture:
	gv_menu_invalidate();
}

void gv_menu_picture_free() {
	if (locked || !chunks[0]) return;
	for (int c = 0; c < CHUNKS; ++c) {
		free(chunks[c]);
		chunks[c] = 0;
	}
	memset(rows_top, 0, sizeof(rows_top));
}

unsigned char** gv_menu_rows() {
	gv_menu_picture_ensure();
	return rows_top;
}

unsigned char** lockbackbuffer(int) {
	if (locked) hiba((char*)"framebuffer already locked");
	gv_menu_picture_ensure();
	locked = true;
	if (Locky0_alul) psx_debug.game_frames++;
	for (int y = 0; y < H; ++y) rows[Locky0_alul ? H - 1 - y : y] = rows_top[y];
	return rows;
}
void unlockbackbuffer() {
	locked = false;
	present();
}
void backbuffersize(int* w, int* h) { *w = W; *h = H; }
unsigned char** lockfrontbuffer() { return lockbackbuffer(0); }
void unlockfrontbuffer() { unlockbackbuffer(); }

ddpal::ddpal(unsigned char* colors) {
	uint16_t* value = new uint16_t[256];
	for (int i = 0; i < 256; ++i) value[i] = vga_to_vram(colors + i * 3);
	pddpal = value;
}
ddpal::~ddpal() { delete[] static_cast<uint16_t*>(pddpal); }
void ddpal::set() {
	memcpy(clut, pddpal, 512);
	clut_dirty = true;
}

// The picture is not scaled; the menus are the original 640x480.
const char* dd_scale_name() { return NULL; }
void dd_next_scale() {}
const char* dd_aspect_name() { return NULL; }
void dd_next_aspect() {}
void dd_menumeret(int* w, int* h) { *w = W; *h = H; }
void frontbuffermeret(int, int) {}
const char* dd_resolution_name() { return NULL; }
void dd_next_resolution() {}
namespace { bool center_bike = true; }
int dd_center_bike() { return center_bike; }
const char* dd_center_bike_name() { return center_bike ? "Yes" : "No"; }
void dd_next_center_bike() { center_bike = !center_bike; }
// The original size of the bike, no zoom:
double dd_zoom() { return 1.0; }
void dd_set_zoom(double) {}
int dd_zoom_textures() { return 1; }
int dd_zoom_grass() { return 1; }
int dd_zoom_key(int) { return 0; }
const char* dd_zoom_name() { return NULL; }
void dd_next_zoom() {}
const char* dd_zoom_textures_name() { return NULL; }
int dd_texture_filter() { return SZURO_LEGKOZELEBBI; }
const char* dd_texture_filter_name() { return NULL; }
void dd_next_texture_filter() {}
void dd_next_zoom_textures() {}

void mk_init() {
	memset(key_count, 0, sizeof(key_count));
	memset(action_key, 0, sizeof(action_key));
	char_count = 0;
}
int mk_getextchar() {
	while (!char_count) {
		mv_check();
		VSync(0);
	}
	const int c = chars[char_head];
	char_head = (char_head + 1) % 16;
	char_count--;
	return c;
}
void mk_emptychar() {
	events();
	char_count = 0;
}
int mk_kbhit() {
	events();
	return char_count != 0;
}
int mk_getstate(int code) {
	events();
	return code >= 0 && code < 256 && key_count[code] ? 0x80 : 0;
}
int controlaltnyomva() { return 0; }

void di_reset_state(state_s* state) {
	state->opciok1.billgaz = DIK_UP; state->opciok1.billfek = DIK_DOWN;
	state->opciok1.billugras1 = DIK_RIGHT; state->opciok1.billugras2 = DIK_LEFT;
	state->opciok1.billfordul = DIK_SPACE; state->opciok1.billview = DIK_V;
	state->opciok1.billtime = DIK_T; state->opciok1.billshowkep = DIK_1;
	state->opciok2.billgaz = DIK_NUMPAD5; state->opciok2.billfek = DIK_NUMPAD2;
	state->opciok2.billugras1 = DIK_NUMPAD3; state->opciok2.billugras2 = DIK_NUMPAD1;
	state->opciok2.billfordul = DIK_NUMPAD0; state->opciok2.billview = DIK_B;
	state->opciok2.billtime = DIK_Y; state->opciok2.billshowkep = DIK_2;
	state->billplussz = DIK_EQUALS; state->billminusz = DIK_MINUS; state->billsnap = DIK_I;
}

char* kodtobillnev(int code) {
	static char name[16];
	static const struct { int code; const char* name; } names[] = {
		{DIK_UP, "Up"}, {DIK_DOWN, "Down"}, {DIK_LEFT, "Left"}, {DIK_RIGHT, "Right"},
		{DIK_SPACE, "Space"}, {DIK_ESCAPE, "Esc"}, {DIK_RETURN, "Enter"},
	};
	for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); ++i)
		if (names[i].code == code) return (char*)names[i].name;
	snprintf(name, sizeof(name), "Key %02X", code);
	return name;
}

void mv_check(int) {
	hang();
	events();
}
// The tests (test/gpu_compare_test.lua) stop the game's clock with this, so
// that the same state can be drawn more than once:
extern "C" volatile int gpu_test_freeze;
volatile int gpu_test_freeze = 0;
namespace {
uint32_t frozen_at = 0;
bool frozen = false;
uint32_t stopper_lines() {
	const uint32_t now = lines_now();
	if (gpu_test_freeze) {
		if (!frozen) frozen_at = now;
		frozen = true;
		return frozen_at;
	}
	if (frozen) {
		stopper_start += now - frozen_at;
		frozen = false;
	}
	return now;
}
}

void mv_startstopper() { stopper_start = stopper_lines(); }
// The time between the two calls moves the start of the stopper on.
void mv_pausestopper(int pause) {
	static bool paused = false;
	static uint32_t pause_start = 0;
	const uint32_t now = stopper_lines();
	if (pause && !paused) pause_start = now;
	if (!pause && paused) stopper_start += now - pause_start;
	paused = pause != 0;
}
// 182 ticks a second, as the PC timer of the original.
double mv_stopperido() { return (double)(stopper_lines() - stopper_start) * (182.0 / LINES_PER_SECOND); }
void getbiostort(unsigned short* bios, unsigned short* fraction) {
	const uint32_t lines = lines_now();
	*bios = (unsigned short)(lines >> 16);
	*fraction = (unsigned short)lines;
}
int s_random(int max) { return max > 0 ? rand() % max : 0; }

extern "C" time_t time(time_t* t) {
	const time_t seconds = (time_t)(lines_now() / LINES_PER_SECOND);
	if (t) *t = seconds;
	return seconds;
}
extern "C" clock_t clock(void) { return (clock_t)((uint64_t)lines_now() * 1000 / LINES_PER_SECOND); }

// There is no mouse (the editor is not in the menu).
void getmou(int* x, int* y) { *x = *y = 0; }
void setmou(int, int) {}
int getbutbmou() { return 0; }
int getbutjmou() { return 0; }

extern "C" void exit(int status) {
	printf("elma: exit %d\n", status);
	DrawSync(0);
	while (true) VSync(0);
}

void hiba(char* a, char* b, char* c) {
	psx_debug.errors++;
	if (!in_error++) message_screen("Sorry, internal error.", a, b, c, false);
	exit(1);
}

void uzenet(char* a, char* b, char* c) {
	if (in_error) return;
	message_screen("Elasto Mania", a, b, c, true);
}

// The game does not check every allocation; running out of memory would
// write through NULL into the BIOS area, so it stops with a message instead.
// Live bytes are counted per calling place (8 bytes more per block) and
// listed then, as a map of what takes the RAM.
namespace {
struct alloc_site {
	void* caller;
	uint32_t bytes, blocks;
};
alloc_site alloc_sites[256];
const uint32_t ALLOC_HEADER = 8;

int alloc_site_index(void* caller) {
	for (int i = 0; i < 255; ++i) {
		if (alloc_sites[i].caller == caller) return i;
		if (!alloc_sites[i].caller) {
			alloc_sites[i].caller = caller;
			return i;
		}
	}
	return 255; // everything else
}

void print_alloc_sites() {
	printf("elma: live heap by calling place (bytes, blocks):\n");
	for (int i = 0; i < 256; ++i)
		if (alloc_sites[i].bytes >= 16 * 1024)
			printf("elma:   %p %u %u\n", alloc_sites[i].caller, (unsigned)alloc_sites[i].bytes,
			       (unsigned)alloc_sites[i].blocks);
}

void* allocate(size_t size, void* caller) {
	uint32_t* p = (uint32_t*)malloc(size + ALLOC_HEADER);
	if (!p) {
		HeapUsage usage;
		GetHeapUsage(&usage);
		printf("elma: out of memory: %u bytes for %p, %u allocated\n", (unsigned)size, caller,
		       (unsigned)usage.alloc);
		print_alloc_sites();
		static char text[48];
		snprintf(text, sizeof(text), "%u bytes", (unsigned)size);
		hiba((char*)"Out of memory:", text);
	}
#ifdef ELMA_PSX_LOG_ALLOC
	if (size >= ELMA_PSX_LOG_ALLOC) printf("elma: alloc %u for %p\n", (unsigned)size, caller);
#endif
	const int site = alloc_site_index(caller);
	alloc_sites[site].bytes += size;
	alloc_sites[site].blocks++;
	p[0] = size;
	p[1] = site;
	return p + 2;
}

void release(void* block) {
	if (!block) return;
	uint32_t* p = (uint32_t*)block - 2;
	alloc_sites[p[1]].bytes -= p[0];
	alloc_sites[p[1]].blocks--;
	free(p);
}
}

void* operator new(size_t size) { return allocate(size, __builtin_return_address(0)); }
void* operator new[](size_t size) { return allocate(size, __builtin_return_address(0)); }
void operator delete(void* p) { release(p); }
void operator delete[](void* p) { release(p); }
void operator delete(void* p, size_t) { release(p); }
void operator delete[](void* p, size_t) { release(p); }

void mv_exit(char*) {
	ddfinish();
	exit(0);
}

void game_main() {
#ifdef ELMA_PSX_PCDRV
	if (psx_pcdrv_add_backend() == 0) printf("elma: reading files through PCdrv\n");
#else
	// The game data is on the second track of the disc, or else on the
	// first one with the program. The CD library needs the GPU's interrupt
	// setup first.
	ResetGraph(0);
	graph_reset = true;
	static cdtrack_vol volume;
	static cdfile_ctx cd_context;
	static psx_file_backend cd_backend;
	if (cdtrack_init() != 0) printf("elma: no CD drive\n");
	else if (cdtrack_mount_data2(&volume) == ISO_OK || cdtrack_mount(&volume, 1) == ISO_OK) {
		printf("elma: reading files from track %d of the disc\n", volume.track);
		cdfile_init(&cd_context, &volume.iso, &cd_backend);
		psx_file_add_backend(&cd_backend);
	} else
		printf("elma: no data track on the disc\n");
#endif
	// The statistics text is written after every run; nobody reads it here.
	psx_file_discard("stats.txt");
	// Without this file mv_main checks for 10 MB of free memory (as the PC
	// version did) by allocating it:
	psx_fclose(psx_fopen("nemmem.inf", "wb"));
	void initqopen(); void initmenukep1(); void initmenukep2();
	initqopen(); mk_init(); initmenukep1();
	ddinit(); initmenukep2(); mv_main();
	exit(0);
}
