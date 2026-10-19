/*
 * Memory card test of the PS1 side. The harness (test/mc_test.py, with
 * test/mc_test.lua) sets `mctest_state.op` and `.kind` after boot and reads
 * the results back. Operations (op):
 *   1 save: build a file from `kind`, memcard_save() it (and a small second
 *     file); 2 load: memcard_load() both files and compare them; 3 init only.
 * Kinds: 0 an empty state.dat (the game's cipher over zeros), 1 a used one
 * (cipher over sparse pseudo-random data), 2 the real state.dat given
 * through PCdrv (the harness passes its CRC and size).
 * Progress goes to the TTY; the result is kept in the global mctest_state.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <psxapi.h>
#include <psxgpu.h>
#include <psxpad.h>

#include "../src/memcard/memcard.h"
#include "../src/memcard/mclz.h"
#include "../src/psx_file.h"
#include "../src/psx_pcdrv.h"

#define MCTEST_MAGIC 0x4D435354u /* "MCST" */
#define STATE_SIZE 67910
#define SETTINGS_SIZE 40

/* Read and written by the test harness. Keep the layout stable (all words). */
typedef struct {
	volatile uint32_t magic;
	volatile uint32_t op;           /* set by the harness: 1 save, 2 load, 3 init only */
	volatile uint32_t kind;         /* set by the harness */
	volatile uint32_t expect_crc;   /* set by the harness for kind 2 */
	volatile uint32_t expect_len;   /* set by the harness for kind 2 */
	volatile uint32_t done;         /* 1 when the operation is over */
	volatile uint32_t init_status;  /* memcard_init() */
	volatile uint32_t status;       /* status of the save / load */
	volatile uint32_t status2;      /* status for the second file */
	volatile uint32_t data_ok;      /* load: both files identical to the expected data */
	volatile uint32_t crc;          /* CRC of state.dat after the operation */
	volatile uint32_t len;
	volatile uint32_t blocks;       /* blocks used by the last save */
	volatile uint32_t frames;       /* vblanks the last save blocked */
	volatile uint32_t ticks;        /* RCnt-free measure: VSync(-1) at the end of the op */
	volatile uint32_t comp_bytes;   /* compressed size of state.dat (host-side estimate) */
} McTestState;

McTestState mctest_state;

static uint8_t data[STATE_SIZE];
static uint8_t settings[SETTINGS_SIZE];

/* The game's cipher (src/STATE.CPP titkoswrite), applied per segment. */
static void cipher(uint8_t* p, int n)
{
	short a = 23, b = 9782, c = 3391;
	int i;
	for (i = 0; i < n; i++) {
		p[i] ^= (uint8_t)a;
		a %= c;
		b += a * c;
		a = 31 * b + c;
	}
}

static void make_state(int kind)
{
	static const int segs[] = { 4, 61000, 4400, 4, 800, 800, 4, 4, 4, 4, 4, 4, 4, 4, 40, 40, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4 };
	uint32_t s = 777;
	int i, off = 0;
	memset(data, 0, sizeof(data));
	if (kind == 1) {
		for (i = 0; i < STATE_SIZE; i++) {
			s = s * 1664525u + 1013904223u;
			if ((s >> 24) < 18) data[i] = (uint8_t)(s >> 8);
		}
	}
	for (i = 0; i < (int)(sizeof(segs) / sizeof(segs[0])) && off < STATE_SIZE; i++) {
		int n = segs[i];
		if (off + n > STATE_SIZE || i == (int)(sizeof(segs) / sizeof(segs[0])) - 1) n = STATE_SIZE - off;
		cipher(data + off, n);
		off += n;
	}
	for (i = 0; i < SETTINGS_SIZE; i++) settings[i] = (uint8_t)(i * 7 + kind);
}

static int put_file(const char* path, const void* buf, int n)
{
	psx_file* f = psx_fopen(path, "wb");
	int ok;
	if (!f) return 0;
	ok = (int)psx_fwrite(buf, 1, (size_t)n, f) == n;
	psx_fclose(f);
	return ok;
}

/* Reads a RAM or backend file fully into buf; returns its size or -1. */
static int get_file(const char* path, uint8_t* buf, int max)
{
	psx_file* f = psx_fopen(path, "rb");
	int n;
	if (!f) return -1;
	n = (int)psx_fread(buf, 1, (size_t)max, f);
	psx_fclose(f);
	return n;
}

static void init_all(void)
{
	static uint8_t pad_buffers[2][34];
	ResetGraph(0);
	/* The same order as the game: pad driver first, then the card. */
	InitPAD(pad_buffers[0], 34, pad_buffers[1], 34);
	mctest_state.init_status = (uint32_t)memcard_init();
	StartPAD();
	ChangeClearPAD(0);
}

int main(void)
{
	static uint8_t back[STATE_SIZE + 16];
	uint32_t start;
	int n;

	mctest_state.magic = MCTEST_MAGIC;
	init_all();
	printf("mctest: init status %d\n", (int)mctest_state.init_status);

	while (!mctest_state.op) VSync(0);
	start = (uint32_t)VSync(-1);

	if (mctest_state.op == 1) {
		if (mctest_state.kind == 2) {
			/* The real file comes from the host: read it through PCdrv. */
			/* PCdrv is only touched here: without a host directory the emulator halts. */
			psx_pcdrv_add_backend();
			n = get_file("STATE.DAT", data, STATE_SIZE);
			if (n < 0) { mctest_state.status = 99; mctest_state.done = 1; while (1) VSync(0); }
			put_file("state.dat", data, n);
			mctest_state.len = (uint32_t)n;
			mctest_state.crc = mclz_crc32(data, (size_t)n, 0);
			{
				static uint8_t c[MCLZ_BOUND(STATE_SIZE)];
				mctest_state.comp_bytes = (uint32_t)mclz_compress(data, (size_t)n, c);
			}
			for (n = 0; n < SETTINGS_SIZE; n++) settings[n] = (uint8_t)(n * 7 + 2);
		} else {
			static uint8_t c[MCLZ_BOUND(STATE_SIZE)];
			make_state((int)mctest_state.kind);
			put_file("state.dat", data, STATE_SIZE);
			mctest_state.len = STATE_SIZE;
			mctest_state.crc = mclz_crc32(data, STATE_SIZE, 0);
			mctest_state.comp_bytes = (uint32_t)mclz_compress(data, STATE_SIZE, c);
		}
		put_file("settings.dat", settings, SETTINGS_SIZE);
		mctest_state.status = (uint32_t)memcard_save("state.dat");
		mctest_state.blocks = (uint32_t)memcard_last_blocks();
		mctest_state.frames = (uint32_t)memcard_last_frames();
		/* A second save with a different file is the multi-file path. */
		mctest_state.status2 = (uint32_t)memcard_save("settings.dat");
		printf("mctest: save status %d (%s) blocks %d frames %d\n", (int)mctest_state.status,
		       memcard_message((int)mctest_state.status), (int)mctest_state.blocks, (int)mctest_state.frames);
	} else if (mctest_state.op == 2) {
		for (n = 0; n < SETTINGS_SIZE; n++) settings[n] = (uint8_t)(n * 7 + (int)mctest_state.kind);
		mctest_state.status = (uint32_t)memcard_load("state.dat");
		mctest_state.status2 = (uint32_t)memcard_load("settings.dat");
		mctest_state.frames = (uint32_t)(VSync(-1) - (int)start);
		n = get_file("state.dat", back, STATE_SIZE + 16);
		mctest_state.len = n < 0 ? 0 : (uint32_t)n;
		mctest_state.crc = n < 0 ? 0 : mclz_crc32(back, (size_t)n, 0);
		if (mctest_state.kind == 2) {
			mctest_state.data_ok = mctest_state.status == MC_OK && mctest_state.crc == mctest_state.expect_crc &&
			                       mctest_state.len == mctest_state.expect_len;
		} else {
			make_state((int)mctest_state.kind);
			mctest_state.data_ok = mctest_state.status == MC_OK && n == STATE_SIZE && !memcmp(back, data, STATE_SIZE);
		}
		n = get_file("settings.dat", back, SETTINGS_SIZE + 1);
		if (mctest_state.status2 != MC_OK || n != SETTINGS_SIZE || memcmp(back, settings, SETTINGS_SIZE)) mctest_state.data_ok = 0;
		printf("mctest: load status %d/%d data_ok %d\n", (int)mctest_state.status, (int)mctest_state.status2, (int)mctest_state.data_ok);
	}
	mctest_state.ticks = (uint32_t)VSync(-1);
	mctest_state.done = 1;
	while (1) VSync(0);
	return 0;
}
