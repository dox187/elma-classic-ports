// The frame loop of the program (core.asm): the main loop prepares a frame
// (the OAM shadow, queued DMA transfers, scroll and register values), then
// core_frame_done hands it to the NMI, which writes it in the vertical blank.
#ifndef CORE_H
#define CORE_H

#include <snes.h>

// Entries of the DMA queue of a frame and of the queue of register writes:
#define DMAQ_MAX 48
#define REGQ_MAX 32
#define DMAQ_ENTRY_COST 96
#define DMAQ_COST_MAX 5000

// VRAM during a level (word addresses):
#define VRAM_BG1_CHR  0x0000  // ground: 704 tiles of 4 bits
#define VRAM_BG2_MAP  0x2C00  // sky: 32x32
#define VRAM_BG2_CHR  0x3000  // sky: 512 tiles of 4 bits
#define VRAM_BG3_CHR  0x5000  // map view: 128 tiles of 2 bits
#define VRAM_BG3_MAP  0x5400  // 32x32
#define VRAM_BG1_MAP  0x5800  // 64x32
#define VRAM_OBJ      0x6000  // sprites: 512 tiles of 4 bits (two tables)

// Joypad buttons (core_pad):
#define JOY_R      0x0010
#define JOY_L      0x0020
#define JOY_X      0x0040
#define JOY_A      0x0080
#define JOY_RIGHT  0x0100
#define JOY_LEFT   0x0200
#define JOY_DOWN   0x0400
#define JOY_UP     0x0800
#define JOY_START  0x1000
#define JOY_SELECT 0x2000
#define JOY_Y      0x4000
#define JOY_B      0x8000

extern u16 core_frame_count;   // NMIs since the start
extern u16 core_lag_count;     // NMIs that found no frame ready
extern u16 core_frame_lines;   // 262 NTSC, 312 PAL
extern u16 core_dma_overruns;  // published queues above the safe DMA cost
extern u16 core_pad;           // buttons held
extern u16 core_dmaq_bytes;    // bytes queued for the next frame
extern u16 core_scroll[6];     // BG1H BG1V BG2H BG2V BG3H BG3V, from the next frame
extern u8 core_oam[544];       // the OAM, written at every frame

// After consoleInit, in forced blank: clears the queues and the OAM shadow,
// turns on the NMI and the joypad.
void core_init(void);
// All sprites of the shadow below the screen.
void core_oam_clear(void);
// Publish without waiting, then wait before reusing any queued OAM/DMA data.
// Physics can run while the preceding frame waits for its NMI.
void core_frame_submit(void);
void core_frame_wait(void);
// Blocking form used by menus, component tests and terminal pictures.
void core_frame_done(void);
// A shared deadline for preparing a gameplay frame, ending at the next
// NMI. Optional for standalone component tests and forced-blank loading.
void core_work_begin(void);
void core_work_end(void);
// Assembly callers: A16 = scanlines reserved for the caller's remaining
// work; JSL returns carry set if that deadline has passed. Keeps X/Y/D/DB.
// core_dma_left returns remaining DMA queue cost in A16 and tcc__r0.
u16 core_dma_left(void);
// Waits n NMIs.
void core_wait_frames(u16 n);
// The buttons pressed since the last call.
u16 core_pad_take(void);
// DMA at the next frame; src must stay valid until then. 0 if the queue is
// full. vram32 writes a column of a tilemap (the address grows by 32).
u16 core_queue_vram(u16 vaddr, const void* src, u16 size);
u16 core_queue_vram32(u16 vaddr, const void* src, u16 size);
u16 core_queue_cgram(u16 color, const void* src, u16 size);
// Writes an 8-bit register ($21xx, $42xx) at the next frame.
void core_queue_reg(u16 reg, u16 value);
// Right away, only in forced blank:
void core_vram_now(u16 vaddr, const void* src, u16 size);
void core_vram_fill_now(u16 vaddr, u16 value, u16 words);
void core_cgram_now(u16 color, const void* src, u16 size);
// Forced blank right away, or the screen on from the next frame (0-15).
void core_screen_off(void);
void core_screen_on(u16 brightness);

#endif
