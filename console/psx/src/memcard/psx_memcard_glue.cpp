// Memory card saves in the game: the glue between the core and memcard.c.
//
// The core writes its files (state.dat: best times, players, options) into
// the RAM file layer. This file keeps them on the memory card:
//
//   psx_memcard_restore()  at boot, before the core reads state.dat;
//   psx_state_saved()      the core has written state.dat (a flag, nothing
//                          else: a card write blocks for about 3 seconds);
//   psx_memcard_poll()     from the menu's input waiting (mk_kbhit,
//                          mk_getextchar): writes the card when the flag is
//                          set, never while a level is on the screen (the
//                          BIOS card calls also take over the pad bus).
//
// While it writes the screen shows "Saving...", and a card problem is shown
// for a few seconds (with the debug font, as the core's message screens).
#include <hwregs_c.h>
#include <psxetc.h>
#include <psxgpu.h>
#include <stdint.h>
#include <stdio.h>

#include "gpu/gpu_video.h"
#include "memcard/memcard.h"
#include "sound/spu_stream.h"

// Read (and the dirty flag written) by the emulator tests through the symbol
// map. Keep the layout.
struct psx_memcard_state {
	uint32_t magic;       // "MCRD" once psx_memcard_restore has run
	uint32_t saves;       // card saves tried since the start
	int32_t last_status;  // memcard.h status of the last save
	uint32_t dirty;       // bit 0: state.dat, bit 1: the collection times were written since the last card save
	int32_t boot_status;  // status of the load at boot
};
extern "C" {
psx_memcard_state psx_memcard_debug;
}

namespace {

// The files of the game that are kept on the card, and the dirty bit of each:
// the state (players, best times, options) and the times of the collections
// of external levels.
const char* const FILES[] = {"state.dat", "state-elma-ports.dat"};
const int FILE_COUNT = sizeof(FILES) / sizeof(FILES[0]);

psx_memcard_state& debug = psx_memcard_debug;
bool busy = false;        // inside poll: the message screen must not start a save
unsigned shown = 0;       // statuses (bit each) shown already since the last good save
int boot_status = MC_OK;  // the load problem still to be shown

// The game clock's interrupt (root counter 2, every 15 ms, gpu_video.cpp)
// and the sound's (SPU, spu_stream.c) disturb the BIOS card transfers (in
// PCSX-Redux a save fails with either), so both are held back while the card
// is used. The clock and the sound miss those few seconds, which no menu
// cares about.
struct card_interrupts_off {
	uint16_t mask;
	int spu_irq;
	card_interrupts_off() {
		mask = IRQ_MASK;
		IRQ_MASK = mask & ~((1 << IRQ_TIMER2) | (1 << IRQ_SPU));
		// The SPU latches its own IRQ until its enable bit is cleared.
		// Masking only the CPU IRQ can leave that source asserted forever.
		spu_irq = spu_stream_pause_irq();
	}
	~card_interrupts_off() {
		IRQ_STAT = (uint16_t)~((1 << IRQ_TIMER2) | (1 << IRQ_SPU));
		spu_stream_resume_irq(spu_irq);
		IRQ_MASK = mask;
	}
};

// A note over the menu picture, sharing the allocation-free debug font
// with message screens. It stays for `vblanks` vertical blanks (0: until
// the picture is drawn again).
void note(const char* line1, const char* line2, int vblanks) {
	const char* const lines[] = {line1, line2};
	gv_notice(120, 200, 400, 80, lines, 2);
	// The note is on the display after the next vertical blank:
	VSync(0);
	VSync(0);
	for (int i = 0; i < vblanks; ++i) VSync(0);
}

// Shows a card problem for a few seconds. One that stays (no card, a card
// that is not formatted or full) is only said once: every save of the game
// would ask again. A good save makes the card worth a message again. It
// never waits for a button: the game goes on (and the automatic tests with
// it), the best times of this session just are not kept.
void problem(int status, const char* what) {
	if (status == MC_NO_CARD || status == MC_UNFORMATTED || status == MC_FULL) {
		if (shown & (1u << status)) return;
		shown |= 1u << status;
	}
	note(memcard_message(status), what, 240);
	gv_menu_invalidate();
}

}

void psx_memcard_init() {
	card_interrupts_off hold;
	memcard_init();
}

void psx_memcard_restore() {
	int status = MC_OK;
	for (int i = 0; i < FILE_COUNT; ++i) {
		card_interrupts_off hold;
		const int s = memcard_load(FILES[i]);
		// A file that is not in the save yet is no problem; otherwise the
		// card has no save, or none that can be read, for the other files too:
		if (s != MC_OK && s != MC_NOT_FOUND) {
			status = s;
			break;
		}
	}
	debug.magic = 0x4443524D;
	debug.boot_status = status;
	printf("elma: memory card: %s\n", memcard_message(status));
	// Nothing to restore is normal (no card, a new card); a damaged or
	// unreadable save is shown at the first menu:
	if (status == MC_CORRUPT || status == MC_UNFORMATTED) boot_status = status;
}

void psx_state_saved() { debug.dirty |= 1; }
void psx_collection_saved() { debug.dirty |= 2; }

void psx_memcard_poll(bool leaving) {
	if (busy || (!debug.dirty && boot_status == MC_OK)) return;
	// A level (or a replay) is running: wait for a menu. The program is
	// leaving for good: the card is written whatever is on the screen.
	if (gv_in_game_mode() && !leaving) return;
	busy = true;
	if (boot_status != MC_OK) {
		const int status = boot_status;
		boot_status = MC_OK;
		problem(status, "The best times are not loaded.");
	}
	if (debug.dirty) {
		const uint32_t dirty = debug.dirty;
		debug.dirty = 0;
		note("Saving...", NULL, 0);
		// The notice is already in VRAM. Give the save's temporary raw and
		// compressed buffers the menu's RAM picture; the next draw rebuilds it.
		gv_menu_picture_free();
		int status = MC_OK;
		for (int i = 0; i < FILE_COUNT && status == MC_OK; ++i) {
			if (!(dirty & (1u << i))) continue;
			card_interrupts_off hold;
			status = memcard_save(FILES[i]);
			debug.saves++;
			debug.last_status = status;
			printf("elma: memory card save %s: %s (%d blocks, %d frames)\n", FILES[i],
			       memcard_message(status), memcard_last_blocks(), memcard_last_frames());
		}
		// The note is no longer wanted; the next present draws the menu again:
		gv_menu_invalidate();
		if (status == MC_OK) shown = 0;
		else problem(status, "The best times are not saved.");
	}
	busy = false;
}
