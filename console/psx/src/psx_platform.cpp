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
#include <new>

#include "all.h"
#include "psx_file.h"
#include "psx_controls.h"
#include "gpu/gpu_video.h"
#include "memcard/psx_memcard_glue.h"
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
	uint32_t stopper_x1000;  // mv_stopperido() * 1000 (182 ticks a second)
	uint32_t vblanks;        // vertical blanks since the start
	uint32_t video_pal;      // 1 in PAL (50 Hz), 0 in NTSC (59.94 Hz)
};
extern "C" {
psx_debug_state psx_debug;
}

// Transition timestamps and selector state for emulator regressions. Separate
// from psx_debug so existing readers keep their original layout.
struct psx_transition_state {
	uint32_t finishes, finish_vblank, ready_vblank, selected_vblank, resumed_vblank;
	int32_t choice;
	uint32_t count, selected, active;
};
extern "C" {
volatile psx_transition_state psx_transition_debug;
}

namespace {

const int W = 640, H = 480;

// The picture of the core (menus and other screens), top row first. It is
// in RAM only while such screens are drawn: it is given back while an LGR
// is loaded and while the game view (drawn by the GPU) is on
// (gv_menu_picture_free), in small pieces of CHUNK_ROWS rows, so that it
// fits into the heap again however it was cut up meanwhile.
// Dense external levels can leave enough free RAM in holes smaller than
// eight rows. Four-row pieces let the menus use those holes on return.
const int CHUNK_ROWS = 4;
const int CHUNKS = (H + CHUNK_ROWS - 1) / CHUNK_ROWS;
unsigned char* chunks[CHUNKS];
unsigned char* rows_top[H];
unsigned char* rows[H];
bool locked = false;

// The palette in VRAM format; bit 15 keeps color 0 from being transparent.
uint32_t clut_words[128];
uint16_t* const clut = reinterpret_cast<uint16_t*>(clut_words);
bool clut_dirty = true;

// The game's clock: root counter 2 (gpu_video.h) counts the system clock / 8,
// 4233600 a second, on NTSC and PAL consoles alike (the same crystal; the
// video itself runs at 59.94 or 50 fields a second, which the game's time
// must not follow). It is 32 bits wide and added up to 64 bits at every
// vertical blank, so that no wrap is lost.
volatile uint64_t clock_total = 0;
volatile uint32_t clock_prev = 0;
volatile uint32_t vblank_count = 0;
uint64_t stopper_start = 0;
bool video_pal = false;

// Pad states, sampled at every vertical blank so that a short press is not
// lost while the game draws a slow frame; events() applies them in order.
uint8_t pad_buffers[2][34];
volatile uint32_t pad_queue[32]; // pad 1 in the low half, pad 2 in the high half
volatile uint32_t pad_queue_head = 0, pad_queue_tail = 0;
uint32_t pad_sampled = 0;

void sample_pad() {
	// BIOS pad buffer: [0] 0 when a pad answered, [2..3] buttons, active low.
	uint32_t buttons = 0;
	for (int pad = 0; pad < 2; ++pad)
		if (pad_buffers[pad][0] == 0)
			buttons |= (uint32_t)(uint16_t)~(pad_buffers[pad][2] | pad_buffers[pad][3] << 8) << (16 * pad);
	if (buttons == pad_sampled || pad_queue_head - pad_queue_tail >= 32) return;
	pad_queue[pad_queue_head % 32] = buttons;
	pad_queue_head++;
	pad_sampled = buttons;
}

void vblank_callback() {
	gv_vblank();
	sample_pad();
	// (While interrupts are held back the counter's upper half may be
	// behind for a moment: the clock then waits for the next call.)
	const uint32_t now = gv_clock();
	const int32_t passed = (int32_t)(now - clock_prev);
	if (passed > 0) {
		clock_total += (uint32_t)passed;
		clock_prev = now;
	}
	vblank_count++;
}

// Clock ticks since the start; exact even if a vertical blank is still
// waiting to be counted.
uint64_t clock_ticks() {
	uint64_t total;
	uint32_t prev, now;
	do {
		total = clock_total;
		prev = clock_prev;
		now = gv_clock();
	} while (total != clock_total);
	const int32_t passed = (int32_t)(now - prev);
	return total + (passed > 0 ? (uint32_t)passed : 0);
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
	psx_debug.stopper_x1000 = (uint32_t)(mv_stopperido() * 1000.0);
	psx_debug.vblanks = vblank_count;
	psx_debug.video_pal = video_pal;
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
		psx_debug.fps_x100 = fps_frames * (video_pal ? 5000 : 5994) / vblanks;
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

// Menu buttons stay fixed. Gameplay reads each player's saved physical
// button masks independently, so rebinding an action changes the pad itself.
struct button_action {
	uint16_t bit;
	int menu;
};
const button_action actions[] = {
	{PAD_UP, MK_UP}, {PAD_DOWN, MK_DOWN},
	{PAD_LEFT, MK_LEFT}, {PAD_RIGHT, MK_RIGHT},
	{PAD_CROSS, MK_ENTER}, {PAD_CIRCLE, MK_ESC},
	{PAD_L1, MK_PGUP}, {PAD_R1, MK_PGDOWN},
	{PAD_SELECT, MK_ESC}, {PAD_START, MK_ENTER},
};
const int ACTION_COUNT = sizeof(actions) / sizeof(actions[0]);
unsigned char key_count[256]; // fixed leave key and legacy debug-key injection
uint16_t pad_down = 0;   // buttons of pad 1
uint16_t pad2_down = 0;  // buttons of pad 2: the controls of player B, no menu keys

const uint32_t CONTROL_TAG = 0x50580000;
const uint16_t CONTROL_BUTTONS = PAD_UP | PAD_DOWN | PAD_LEFT | PAD_RIGHT |
	PAD_CROSS | PAD_CIRCLE | PAD_SQUARE | PAD_TRIANGLE | PAD_L1 | PAD_R1 |
	PAD_L2 | PAD_R2 | PAD_START;
const uint16_t default_controls[PSX_CONTROL_COUNT] = {
	PAD_UP | PAD_CROSS, PAD_DOWN | PAD_CIRCLE, PAD_LEFT | PAD_L2,
	PAD_RIGHT | PAD_L2, PAD_SQUARE | PAD_R1, PAD_TRIANGLE, PAD_L1, PAD_R2
};
struct control_button { uint16_t mask; const char* name; };
const control_button control_buttons[] = {
	{0, "Unassigned"}, {PAD_UP, "Up"}, {PAD_DOWN, "Down"},
	{PAD_LEFT, "Left"}, {PAD_RIGHT, "Right"}, {PAD_CROSS, "Cross"},
	{PAD_CIRCLE, "Circle"}, {PAD_SQUARE, "Square"}, {PAD_TRIANGLE, "Triangle"},
	{PAD_L1, "L1"}, {PAD_R1, "R1"}, {PAD_L2, "L2"}, {PAD_R2, "R2"},
	{PAD_START, "Start"}
};

int* control_field(state_s* state, int player, int action) {
	if (!state || player < 0 || player > 1) return NULL;
	jatekosopciok& keys = player ? state->opciok2 : state->opciok1;
	switch (action) {
	case PSX_THROTTLE: return &keys.billgaz;
	case PSX_BRAKE: return &keys.billfek;
	case PSX_ROTATE_LEFT: return &keys.billugras2;
	case PSX_ROTATE_RIGHT: return &keys.billugras1;
	case PSX_TURN: return &keys.billfordul;
	case PSX_NAVIGATOR: return &keys.billview;
	case PSX_TIME: return &keys.billtime;
	case PSX_SHOW_HIDE: return &keys.billshowkep;
	default: return NULL;
	}
}

int control_key(int player, uint16_t mask) {
	return (int)(CONTROL_TAG | (uint32_t)player << 16 | (mask & CONTROL_BUTTONS));
}

bool reset_controls(state_s* state) {
	bool changed = false;
	for (int player = 0; player < 2; ++player)
		for (int action = 0; action < PSX_CONTROL_COUNT; ++action) {
			int* field = control_field(state, player, action);
			const int key = control_key(player, default_controls[action]);
			if (field && *field != key) { *field = key; changed = true; }
		}
	return changed;
}

int chars[16];
int char_head = 0, char_count = 0;

void push_char(int c) {
	if (char_count == 16) return;
	// The selected submenu may allocate its rows before drawing again.
	if (c == MK_ENTER || c == MK_ESC) gv_menu_cache_free();
	chars[(char_head + char_count++) % 16] = c;
	psx_debug.menu_chars++;
}

void apply_buttons(int pad, uint16_t buttons) {
	uint16_t& down = pad ? pad2_down : pad_down;
	const uint16_t changed = buttons ^ down;
	if (!changed) return;
	if (changed & PAD_SELECT)
		key_count[DIK_ESCAPE] += (buttons & PAD_SELECT) ? 1 : -1;
	if (!pad)
		for (int i = 0; i < ACTION_COUNT; ++i)
			if ((changed & buttons & actions[i].bit) && actions[i].menu)
				push_char(actions[i].menu);
	down = buttons;
}

// Holding Up or Down repeats the menu key (long lists, the letters of a name):
// after a third of a second, then 15 times a second, and only when the menu
// has taken the last one, so that nothing is left to run on after the release.
void repeat_keys() {
	static uint32_t next_vblank = 0;
	static uint16_t held = 0;
	const uint16_t now = pad_down & (PAD_UP | PAD_DOWN);
	if (!now) {
		held = 0;
		return;
	}
	const uint32_t hz = video_pal ? 50 : 60;
	if (now != held) {
		held = now;
		next_vblank = vblank_count + hz / 3;
		return;
	}
	if ((int32_t)(vblank_count - next_vblank) < 0 || char_count) return;
	push_char((now & PAD_UP) ? MK_UP : MK_DOWN);
	next_vblank = vblank_count + hz / 15;
}

void events() {
	while (pad_queue_tail != pad_queue_head) {
		const uint32_t both = pad_queue[pad_queue_tail % 32];
		apply_buttons(0, (uint16_t)both);
		apply_buttons(1, (uint16_t)(both >> 16));
		pad_queue_tail++;
	}
	repeat_keys();
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
	const char* const lines[] = {title, "", a, b, c, wait ? "\nPress X or START" : NULL};
	gv_notice(32, 32, W - 64, H - 64, lines, sizeof(lines) / sizeof(lines[0]));
	uint16_t blocked = pad_down;
	while (true) {
		VSync(0);
		events();
		// A confirm held on entry must be released first, including the X
		// that closed the previous message in a sequence of warnings.
		blocked &= pad_down;
		if (wait && (pad_down & ~blocked & (PAD_CROSS | PAD_START))) break;
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

// Scan lines since the start, for the header of gpu_video.h (at the rate of
// the video mode set up in ddinit):
uint32_t gv_lines() { return (uint32_t)(clock_ticks() * (video_pal ? 15625 : 15734) / GV_CLOCK_HZ); }

int psx_control_binding(int player, int action) {
	int* field = control_field(State, player, action);
	return field ? *field : 0;
}

int psx_control_button_count() { return sizeof(control_buttons) / sizeof(control_buttons[0]); }

const char* psx_control_button_name(int index) {
	return index >= 0 && index < psx_control_button_count() ? control_buttons[index].name : "Unassigned";
}

int psx_control_key(int player, int button_index) {
	if (player < 0 || player > 1 || button_index < 0 || button_index >= psx_control_button_count()) return 0;
	return control_key(player, control_buttons[button_index].mask);
}

const char* psx_control_name(int binding) {
	static char text[96];
	char* out = text;
	const char* end = text + sizeof(text) - 1;
	const uint16_t mask = binding & CONTROL_BUTTONS;
	if (!mask) return "Unassigned";
	for (int i = 1; i < psx_control_button_count(); ++i) {
		if (!(mask & control_buttons[i].mask)) continue;
		if (out != text && out < end) *out++ = '/';
		const char* name = control_buttons[i].name;
		while (*name && out < end) *out++ = *name++;
	}
	*out = 0;
	return text;
}

bool psx_control_assign(int player, int action, int binding) {
	int* field = control_field(State, player, action);
	if (!field) return false;
	const uint16_t mask = binding & CONTROL_BUTTONS;
	const int key = control_key(player, mask);
	if (*field == key) return false;
	// A newly chosen button belongs to this action. Keep unaffected aliases
	// and the other player's entire layout.
	for (int i = 0; i < PSX_CONTROL_COUNT; ++i) {
		if (i == action) continue;
		int* other = control_field(State, player, i);
		*other = control_key(player, (uint16_t)*other & ~mask);
	}
	*field = key;
	return true;
}

bool psx_controls_reset() { return reset_controls(State); }

void psx_controls_normalize() {
	// Older PSX cards used keyboard codes. Translate the former button
	// families while preserving current-format masks and unassigned actions.
	const int legacy[2][PSX_CONTROL_COUNT] = {
		{DIK_UP, DIK_DOWN, DIK_LEFT, DIK_RIGHT, DIK_SPACE, DIK_V, DIK_T, DIK_1},
		{DIK_NUMPAD5, DIK_NUMPAD2, DIK_NUMPAD1, DIK_NUMPAD3, DIK_NUMPAD0, DIK_B, DIK_Y, DIK_2}
	};
	for (int player = 0; player < 2; ++player)
		for (int action = 0; action < PSX_CONTROL_COUNT; ++action) {
			int* field = control_field(State, player, action);
			if (!field) continue;
			uint16_t mask = default_controls[action];
			if (((uint32_t)*field & 0xffff0000u) == (CONTROL_TAG | (uint32_t)player << 16))
				mask = (uint16_t)*field & CONTROL_BUTTONS;
			else if (!*field)
				mask = 0;
			else
				for (int old = 0; old < PSX_CONTROL_COUNT; ++old)
					if (*field == legacy[player][old]) { mask = default_controls[old]; break; }
			*field = control_key(player, mask);
		}
}

// Available before the disc and menu assets, using only the resident font.
void psx_boot_loading(const char* stage) {
	if (!Margrafikus) return;
	char heading[64];
	sprintf(heading, "Loading Elasto Mania v%s", ELMA_PSX_VERSION);
	const char* const lines[] = {heading, "", stage};
	gv_notice(112, 188, 416, 104, lines, 3);
	VSync(0);
	printf("elma: startup: %s\n", stage);
}

// Loading can release the menu's RAM picture. Draw directly in VRAM with
// the resident font, so the current stage stays visible without allocating.
void psx_loading_stage(const char* level, const char* stage) {
	if (!Margrafikus) return;
	const char* const lines[] = {"Loading level", level ? level : "", "", stage};
	gv_notice(120, 196, 400, 88, lines, sizeof(lines) / sizeof(lines[0]));
	VSync(0);
	printf("elma: loading %s: %s\n", level ? level : "", stage);
}

void psx_transition_mark(int phase) {
	if (phase == 1) {
		psx_transition_debug.finishes++;
		psx_transition_debug.finish_vblank = vblank_count;
		psx_transition_debug.ready_vblank = 0;
		psx_transition_debug.selected_vblank = 0;
		psx_transition_debug.resumed_vblank = 0;
	} else if (phase == 2) {
		psx_transition_debug.ready_vblank = vblank_count;
	} else if (phase == 3) {
		psx_transition_debug.resumed_vblank = vblank_count;
	} else if (phase == 4) {
		psx_transition_debug.selected_vblank = vblank_count;
		psx_transition_debug.resumed_vblank = 0;
	}
}

int psx_quick_choose(const char* title, const char* const* details, int detail_count,
		const char* const* choices, int count, int selected) {
	if (count < 1 || count > 5) return -1;
	if (selected < 0 || selected >= count) selected = 0;
	if (detail_count > 3) detail_count = 3;
	char text[16][37];
	const char* lines[16];
	int line_count = 0;
	auto copy = [](char* out, const char* in, int limit) {
		int i = 0;
		while (i < limit && in[i]) { out[i] = in[i]; ++i; }
		out[i] = 0;
	};
	auto add = [&](const char* line) {
		if (line_count == 16) return;
		if (!line) line = "";
		// The software menu uses this prefix to select its result color.
		// Compare explicitly: the SDK strncmp treats an empty input as equal.
		const char* prefix = "*$$^&|@";
		int matched = 0;
		while (matched < 7 && line[matched] == prefix[matched]) ++matched;
		if (matched == 7) line += 7;
		// The SDK formatter does not implement string precision correctly.
		copy(text[line_count], line, 36);
		lines[line_count] = text[line_count];
		++line_count;
	};
	add(title);
	add("");
	for (int i = 0; i < detail_count; ++i) add(details[i]);
	add("");
	const int choice_line = line_count;
	for (int i = 0; i < count; ++i) add("");
	add("");
	add("UP/DOWN: Choose  X/START: Select");
	add("CIRCLE/SELECT: Level menu");
	auto draw = [&]() {
		for (int i = 0; i < count; ++i) {
			char* row = text[choice_line + i];
			row[0] = i == selected ? '>' : ' ';
			row[1] = ' ';
			copy(row + 2, choices[i], 33);
		}
		gv_quick_notice(lines, line_count);
		gv_frame_done(false);
	};
	psx_transition_debug.count = count;
	psx_transition_debug.selected = selected;
	draw();
	// Successful runs may need a real card save. Keep the compact screen
	// visible, then repaint over its Saving notice before accepting input.
	psx_memcard_poll();
	draw();
	mk_emptychar();
	uint16_t blocked = pad_down;
	uint32_t serial = gv_menu_serial();
	psx_transition_debug.active = 1;
	psx_transition_mark(2);
	for (;;) {
		VSync(0);
		events();
		blocked &= pad_down;
		psx_memcard_poll();
		bool changed = serial != gv_menu_serial();
		int result = -2;
		while (char_count) {
			const int c = chars[char_head];
			char_head = (char_head + 1) % 16;
			--char_count;
			if (c == MK_UP && !(blocked & PAD_UP)) {
				selected = (selected + count - 1) % count;
				changed = true;
			} else if (c == MK_DOWN && !(blocked & PAD_DOWN)) {
				selected = (selected + 1) % count;
				changed = true;
			} else if (c == MK_ENTER && (pad_down & ~blocked & (PAD_CROSS | PAD_START))) {
				result = selected;
				break;
			} else if (c == MK_ESC && (pad_down & ~blocked & (PAD_CIRCLE | PAD_SELECT))) {
				result = -1;
				break;
			}
		}
		if (result != -2) {
			char_count = 0;
			psx_transition_debug.active = 0;
			psx_transition_debug.choice = result;
			psx_transition_mark(4);
			return result;
		}
		if (changed) {
			psx_transition_debug.selected = selected;
			draw();
			serial = gv_menu_serial();
		}
	}
}

void gv_frame_done(bool game_view) {
	if (game_view) {
		psx_debug.game_frames++;
		if (psx_transition_debug.selected_vblank && !psx_transition_debug.resumed_vblank)
			psx_transition_mark(3);
	}
	count_frame();
}

extern "C" char _end[];
void game_main();

// The stack (the game needs about 4 KB, test/mem_test.py):
const uint32_t STACK_SIZE = 16 * 1024;

int main(int, char**) {
	psx_debug.magic = 0x454C4D41; // "ELMA"
	printf("elma: PlayStation port v%s starting\n", ELMA_PSX_VERSION);
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

// Set by the emulator tests before ddinit: 1 NTSC, 2 PAL, 0 the console's own.
extern "C" volatile int psx_video_force;
volatile int psx_video_force = 0;
namespace { bool graph_reset = false; }

void ddinit() {
	if (!graph_reset) ResetGraph(0);
	graph_reset = true;
	// The console's own video mode: the BIOS sets the GPU to the mode of its
	// region and ResetGraph keeps it, so a PAL console gets 50 Hz and an NTSC
	// one 60 Hz (the emulator tests may force one, psx_video_force).
	int pal = GetVideoMode() == MODE_PAL;
	if (psx_video_force) pal = psx_video_force == 2;
	video_pal = pal != 0;
	SetVideoMode(video_pal ? MODE_PAL : MODE_NTSC);
	printf("elma: video mode %s\n", video_pal ? "PAL, 50 Hz" : "NTSC, 60 Hz");
	gv_init();

	gv_clock_init();
	clock_prev = gv_clock();
	// No BIOS pad data is valid until its driver starts. Early loading
	// notices already wait on VBlank, which also samples these buffers.
	memset(pad_buffers, 0xff, sizeof(pad_buffers));
	VSyncCallback(vblank_callback);
	gv_menu_present(NULL, clut, true);
	SetDispMask(1);
	Margrafikus = 1;
	psx_boot_loading("Initializing controllers and memory card...");

	InitPAD(pad_buffers[0], 34, pad_buffers[1], 34);
	// The card driver sits between the two (memcard.h):
	psx_memcard_init();
	StartPAD();
	ChangeClearPAD(0);

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
	char_count = 0;
}
int mk_getextchar() {
	while (!char_count) {
		psx_memcard_poll();
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
	psx_memcard_poll();
	events();
	return char_count != 0;
}
int mk_getstate(int code) {
	events();
	if (((uint32_t)code & 0xfffe0000u) == CONTROL_TAG) {
		const uint16_t buttons = code & 0x10000 ? pad2_down : pad_down;
		return (buttons & code & CONTROL_BUTTONS) ? 0x80 : 0;
	}
	return code >= 0 && code < 256 && key_count[code] ? 0x80 : 0;
}
int controlaltnyomva() { return 0; }

void di_reset_state(state_s* state) {
	reset_controls(state);
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
// The tests (test/gpu_compare_test.lua, test/mc_game_test.lua) stop the
// game's clock with gpu_test_freeze, so that the same state can be drawn
// more than once; while it is stopped they move it on by the ticks they put
// in gpu_test_clock_add, which makes the game's steps whole ones.
extern "C" volatile int gpu_test_freeze;
volatile int gpu_test_freeze = 0;
extern "C" volatile uint32_t gpu_test_clock_add;
volatile uint32_t gpu_test_clock_add = 0;
namespace {
uint64_t frozen_at = 0;
bool frozen = false;
uint64_t stopper_ticks() {
	const uint64_t now = clock_ticks();
	if (gpu_test_freeze) {
		if (!frozen) frozen_at = now;
		frozen = true;
		return frozen_at + gpu_test_clock_add;
	}
	if (frozen) {
		stopper_start += now - (frozen_at + gpu_test_clock_add);
		frozen = false;
	}
	return now;
}
}

void mv_startstopper() { stopper_start = stopper_ticks(); }
// The time between the two calls moves the start of the stopper on.
void mv_pausestopper(int pause) {
	static bool paused = false;
	static uint64_t pause_start = 0;
	const uint64_t now = stopper_ticks();
	if (pause && !paused) pause_start = now;
	if (!pause && paused) stopper_start += now - pause_start;
	paused = pause != 0;
}
// 182 ticks a second, as the PC timer of the original.
double mv_stopperido() { return (double)(stopper_ticks() - stopper_start) * 182.0 / GV_CLOCK_HZ; }
void getbiostort(unsigned short* bios, unsigned short* fraction) {
	const uint32_t ticks = (uint32_t)clock_ticks();
	*bios = (unsigned short)(ticks >> 16);
	*fraction = (unsigned short)ticks;
}
int s_random(int max) { return max > 0 ? rand() % max : 0; }

extern "C" time_t time(time_t* t) {
	const time_t seconds = (time_t)(clock_ticks() / GV_CLOCK_HZ);
	if (t) *t = seconds;
	return seconds;
}
extern "C" clock_t clock(void) { return (clock_t)(clock_ticks() * 1000 / GV_CLOCK_HZ); }

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
	printf("elma: internal error: %.160s %.160s %.160s\n", a ? a : "", b ? b : "", c ? c : "");
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

void* allocate(size_t size, void* caller, bool fatal = true) {
	uint32_t* p = (uint32_t*)malloc(size + ALLOC_HEADER);
	if (!p) {
		if (!fatal) return NULL;
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
void* operator new[](size_t size, const std::nothrow_t&) noexcept {
	return allocate(size, __builtin_return_address(0), false);
}
void operator delete(void* p) { release(p); }
void operator delete[](void* p) { release(p); }
void operator delete[](void* p, const std::nothrow_t&) noexcept { release(p); }
void operator delete(void* p, size_t) { release(p); }
void operator delete[](void* p, size_t) { release(p); }

void mv_exit(char*) {
	// The last changes of state.dat go to the card:
	psx_memcard_poll(true);
	ddfinish();
	exit(0);
}

void game_main() {
	mk_init();
	ddinit();
	psx_boot_loading("Reading game disc...");
#ifdef ELMA_PSX_PCDRV
	if (psx_pcdrv_add_backend() == 0) printf("elma: reading files through PCdrv\n");
#else
	// The game data is on the second track of the disc, or else on the
	// first one with the program. Video and interrupts are already ready.
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
	psx_boot_loading("Reading game resources...");
	initqopen();
	psx_boot_loading("Loading menu graphics...");
	initmenukep1();
	psx_boot_loading("Preparing menus...");
	initmenukep2(); mv_main();
	exit(0);
}
