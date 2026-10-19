#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <psxapi.h>
#include <psxgpu.h>
#include <sys/fcntl.h>

#include "memcard.h"
#include "mclz.h"
#include "../psx_file.h"

/* Card file name: "BA" (the region prefix card browsers expect) and a
 * name of our own that is not the product code of any released game.
 * 20 characters at most. */
#ifndef MEMCARD_SAVE_NAME
#define MEMCARD_SAVE_NAME "BAELMA-00000STATE"
#endif

#define BLOCK_SIZE 8192
#define HEADER_SIZE 512
#define MAX_BLOCKS 15
#define MAX_FILES 4
#define NAME_LEN 16
#define MAGIC 0x534D4C45u /* "ELMS" */
#define EVENT_WAIT_FRAMES 120

typedef struct {
	char name[NAME_LEN];
	uint32_t raw_size;
	uint32_t comp_size;
	uint32_t crc;
	uint8_t* comp;
} entry;

static entry files[MAX_FILES];
static int file_count;
static int cache_valid;
static int last_status = MC_NOT_INIT;
static int last_blocks, last_frames;
static int initialized;
static int formatted; /* the card in the slot passed the directory check */
static int events[2][4]; /* [hw/sw][IOE, ERROR, TIMOUT, NEW] */
static const uint32_t spec[4] = { EvSpIOE, EvSpERROR, EvSpTIMOUT, EvSpNEW };

static const char save_path[] = "bu00:" MEMCARD_SAVE_NAME;

/* ---- little endian helpers ---- */

static void put32(uint8_t* p, uint32_t v)
{
	p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}
static uint32_t get32(const uint8_t* p)
{
	return p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

/* ---- BIOS card events ---- */

static void open_events(void)
{
	int k;
	EnterCriticalSection();
	for (k = 0; k < 4; k++) {
		events[0][k] = OpenEvent(HwCARD, spec[k], EvMdNOINTR, NULL);
		events[1][k] = OpenEvent(SwCARD, spec[k], EvMdNOINTR, NULL);
		EnableEvent(events[0][k]);
		EnableEvent(events[1][k]);
	}
	ExitCriticalSection();
}

static void clear_events(void)
{
	int k;
	for (k = 0; k < 4; k++) {
		TestEvent(events[0][k]);
		TestEvent(events[1][k]);
	}
}

/* Waits for one of the card events; returns 0 IOE, 1 ERROR, 2 TIMOUT,
 * 3 NEW, or -1 when nothing came in time. */
static int wait_event(void)
{
	int frame, k;
	for (frame = 0; frame < EVENT_WAIT_FRAMES; frame++) {
		/* The BIOS reports on the software class; the hardware class is
		 * checked too, as real BIOS versions differ. */
		for (k = 0; k < 4; k++)
			if (TestEvent(events[1][k]) || TestEvent(events[0][k])) return k;
		VSync(0);
	}
	return -1;
}

/* Probes slot 1: MC_OK, MC_NO_CARD or MC_UNFORMATTED. */
static int probe(void)
{
	int attempt, r;
	if (!initialized) return MC_NOT_INIT;
	for (attempt = 0; attempt < 3; attempt++) {
		clear_events();
		if (_card_info(0) == 0) { formatted = 0; return MC_NO_CARD; }
		r = wait_event();
		if (r == 3) { /* a new card was noticed: ask once more, then classify it */
			formatted = 0;
			if (attempt == 0) continue;
			r = 0;
		}
		if (r == 1) { formatted = 0; return MC_UNFORMATTED; } /* card answered badly */
		if (r != 0) { formatted = 0; return MC_NO_CARD; }
		if (formatted) return MC_OK; /* same card as at the last full check */
		clear_events();
		if (_card_load(0) == 0) return MC_NO_CARD;
		r = wait_event();
		if (r == 0) { formatted = 1; return MC_OK; }
		/* ERROR, or NEW again: the directory could not be read. */
		return r == 2 || r < 0 ? MC_NO_CARD : MC_UNFORMATTED;
	}
	return MC_NO_CARD;
}

int memcard_init(void)
{
	if (!initialized) {
		InitCARD(1);
		StartCARD();
		_bu_init();
		open_events();
		initialized = 1;
	}
	return last_status = probe();
}

/* ---- card file layout ---- */

/* 16x16 icon, 4 bits per pixel (low nibble = left pixel): a red apple with a
 * leaf on a transparent background. */
static void make_icon(uint16_t* palette, uint8_t* icon)
{
	/* RGB555: r | g << 5 | b << 10, bit 15 set = opaque. */
	static const uint16_t colors[6] = {
		0x0000,                           /* 0 transparent */
		0x8000 | 20 | 2 << 5 | 2 << 10,   /* 1 dark red rim */
		0x8000 | 28 | 3 << 5 | 3 << 10,   /* 2 red */
		0x8000 | 31 | 14 << 5 | 14 << 10, /* 3 highlight */
		0x8000 | 4 | 20 << 5 | 3 << 10,   /* 4 leaf green */
		0x8000 | 10 | 8 << 5 | 3 << 10,   /* 5 stem brown */
	};
	int x, y, k;
	for (k = 0; k < 16; k++) palette[k] = colors[k < 6 ? k : 0];
	memset(icon, 0, 128);
	for (y = 0; y < 16; y++) {
		for (x = 0; x < 16; x++) {
			int dx2 = 2 * x - 15, dy2 = 2 * (y - 9) + 1;
			int d = dx2 * dx2 + dy2 * dy2; /* apple: circle radius ~6.5 */
			int c = 0;
			if (d <= 13 * 13) {
				c = d > 11 * 11 ? 1 : 2;
				if (dx2 < -2 && dx2 > -8 && dy2 < -2 && dy2 > -8) c = 3;
			}
			if (x == 8 && y >= 1 && y <= 3) c = 5;               /* stem */
			if (y == 2 && x >= 9 && x <= 12) c = 4;              /* leaf */
			if (y == 3 && x >= 9 && x <= 11) c = 4;
			if (y == 1 && x >= 10 && x <= 12) c = 4;
			icon[y * 8 + x / 2] |= (uint8_t)(x & 1 ? c << 4 : c);
		}
	}
}

/* Shift-JIS full width "ELASTO MANIA". */
static void make_title(uint8_t* p)
{
	static const char text[] = "ELASTO MANIA";
	size_t i;
	memset(p, 0, 64);
	for (i = 0; text[i]; i++) {
		if (text[i] == ' ') { p[2 * i] = 0x81; p[2 * i + 1] = 0x40; }
		else { p[2 * i] = 0x82; p[2 * i + 1] = (uint8_t)(0x60 + text[i] - 'A'); }
	}
}

static size_t payload_size(const entry* files, int file_count)
{
	size_t n = 12 + (size_t)file_count * (NAME_LEN + 12);
	int i;
	for (i = 0; i < file_count; i++) n += files[i].comp_size;
	return n;
}

/* Builds the whole save file (header block, payload, zero padding) in a new
 * buffer; returns it and stores the block count, or NULL. */
static uint8_t* build_image(const entry* files, int file_count, int* blocks)
{
	size_t total = HEADER_SIZE + payload_size(files, file_count);
	int nb = (int)((total + BLOCK_SIZE - 1) / BLOCK_SIZE);
	uint8_t* img;
	uint8_t* p;
	uint16_t palette[16];
	int i;
	if (nb > MAX_BLOCKS) return NULL;
	img = (uint8_t*)calloc(1, (size_t)nb * BLOCK_SIZE);
	if (!img) return NULL;
	img[0] = 'S'; img[1] = 'C';
	img[2] = 0x11; /* one static icon frame */
	img[3] = (uint8_t)nb;
	make_title(img + 4);
	make_icon(palette, img + 0x80);
	for (i = 0; i < 16; i++) { img[0x60 + 2 * i] = (uint8_t)palette[i]; img[0x61 + 2 * i] = (uint8_t)(palette[i] >> 8); }

	p = img + HEADER_SIZE;
	put32(p + 0, MAGIC);
	p[4] = 1; p[5] = 0; /* version */
	p[6] = (uint8_t)file_count; p[7] = 0;
	p += 12;
	for (i = 0; i < file_count; i++) {
		memcpy(p, files[i].name, NAME_LEN);
		put32(p + NAME_LEN, files[i].raw_size);
		put32(p + NAME_LEN + 4, files[i].comp_size);
		put32(p + NAME_LEN + 8, files[i].crc);
		p += NAME_LEN + 12;
	}
	for (i = 0; i < file_count; i++) {
		memcpy(p, files[i].comp, files[i].comp_size);
		p += files[i].comp_size;
	}
	put32(img + HEADER_SIZE + 8, mclz_crc32(img + HEADER_SIZE + 12, payload_size(files, file_count) - 12, 0));
	*blocks = nb;
	return img;
}

static void free_cache(void)
{
	int i;
	for (i = 0; i < file_count; i++) { free(files[i].comp); files[i].comp = NULL; }
	file_count = 0;
}

/* Parses a save image; replaces the cache. MC_OK or MC_CORRUPT/MC_NO_MEMORY. */
static int parse_image(const uint8_t* img, size_t size)
{
	const uint8_t* p;
	size_t pay, off;
	int i, n;
	if (size < HEADER_SIZE + 12 || img[0] != 'S' || img[1] != 'C') return MC_CORRUPT;
	p = img + HEADER_SIZE;
	if (get32(p) != MAGIC || p[4] != 1) return MC_CORRUPT;
	n = p[6];
	if (n > MAX_FILES) return MC_CORRUPT;
	pay = 12 + (size_t)n * (NAME_LEN + 12);
	off = pay;
	free_cache();
	for (i = 0; i < n; i++) {
		const uint8_t* e = p + 12 + (size_t)i * (NAME_LEN + 12);
		memcpy(files[i].name, e, NAME_LEN);
		files[i].name[NAME_LEN - 1] = 0;
		files[i].raw_size = get32(e + NAME_LEN);
		files[i].comp_size = get32(e + NAME_LEN + 4);
		files[i].crc = get32(e + NAME_LEN + 8);
		if (files[i].comp_size > size - HEADER_SIZE - off || files[i].raw_size > (1u << 22)) { free_cache(); return MC_CORRUPT; }
		off += files[i].comp_size;
		file_count = i + 1;
	}
	if (mclz_crc32(p + 12, off - 12, 0) != get32(p + 8)) { free_cache(); return MC_CORRUPT; }
	off = pay;
	for (i = 0; i < n; i++) {
		files[i].comp = (uint8_t*)malloc(files[i].comp_size ? files[i].comp_size : 1);
		if (!files[i].comp) { free_cache(); return MC_NO_MEMORY; }
		memcpy(files[i].comp, p + off, files[i].comp_size);
		off += files[i].comp_size;
	}
	return MC_OK;
}

/* ---- card file access ---- */

/* Size in bytes of the save file on the card, or -1 if absent. Also counts
 * the blocks used by other files in *others. */
static int scan_card(int* others)
{
	struct DIRENTRY e;
	struct DIRENTRY* d;
	int size = -1;
	*others = 0;
	d = firstfile("bu00:*", &e);
	while (d) {
		if (!strncmp(d->name, MEMCARD_SAVE_NAME, sizeof(d->name))) size = d->size;
		else *others += (d->size + BLOCK_SIZE - 1) / BLOCK_SIZE;
		d = nextfile(d);
	}
	return size;
}

const char* memcard_message(int s)
{
	switch (s) {
	case MC_OK: return "Saved";
	case MC_NO_CARD: return "No memory card in slot 1";
	case MC_UNFORMATTED: return "Memory card is not formatted";
	case MC_FULL: return "Memory card is full";
	case MC_WRITE_ERROR: return "Memory card write error";
	case MC_NO_SAVE: return "No save on the memory card";
	case MC_CORRUPT: return "Save on the memory card is damaged";
	case MC_NOT_FOUND: return "File not in the save";
	case MC_NO_MEMORY: return "Out of memory";
	case MC_BAD_ARG: return "Nothing to save";
	default: return "Memory card not ready";
	}
}

int memcard_status(void) { return last_status; }
int memcard_last_blocks(void) { return last_blocks; }
int memcard_last_frames(void) { return last_frames; }

/* Reads the save from the card into the cache (once). */
static int load_card(void)
{
	int s, others, size, fd, got;
	uint8_t* buf;
	s = probe();
	if (s != MC_OK) return s;
	size = scan_card(&others);
	if (size < 0) return MC_NO_SAVE;
	if (size <= 0 || size > MAX_BLOCKS * BLOCK_SIZE) return MC_CORRUPT;
	buf = (uint8_t*)malloc((size_t)size);
	if (!buf) return MC_NO_MEMORY;
	fd = open(save_path, FREAD);
	if (fd < 0) { free(buf); return MC_CORRUPT; }
	got = read(fd, buf, (size_t)size);
	close(fd);
	s = got == size ? parse_image(buf, (size_t)size) : MC_CORRUPT;
	free(buf);
	return s;
}

int memcard_load(const char* path)
{
	char name[NAME_LEN + 8];
	int s, i;
	if (!path) return last_status = MC_BAD_ARG;
	if (!cache_valid) {
		s = load_card();
		if (s != MC_OK) return last_status = s;
		cache_valid = 1;
	}
	psx_file_normalize(path, name, NAME_LEN);
	for (i = 0; i < file_count; i++) {
		if (!strcmp(files[i].name, name)) {
			uint8_t* raw = (uint8_t*)malloc(files[i].raw_size ? files[i].raw_size : 1);
			psx_file* f;
			if (!raw) return last_status = MC_NO_MEMORY;
			if (mclz_expand(files[i].comp, files[i].comp_size, raw, files[i].raw_size) ||
			    mclz_crc32(raw, files[i].raw_size, 0) != files[i].crc) {
				free(raw);
				return last_status = MC_CORRUPT;
			}
			f = psx_fopen(path, "wb");
			if (!f || psx_fwrite(raw, 1, files[i].raw_size, f) != files[i].raw_size) {
				if (f) psx_fclose(f);
				free(raw);
				return last_status = MC_NO_MEMORY;
			}
			psx_fclose(f);
			free(raw);
			return last_status = MC_OK;
		}
	}
	return last_status = MC_NOT_FOUND;
}

int memcard_save(const char* path)
{
	char name[NAME_LEN + 8];
	psx_file* f;
	uint8_t* raw = NULL;
	uint8_t* comp = NULL;
	uint8_t* img = NULL;
	long size;
	int s, nb = 0, others, old_size, fd, start = VSync(-1);
	entry list[MAX_FILES];
	entry ne;
	int count, slot;

	if (!path) return last_status = MC_BAD_ARG;
	s = probe();
	if (s != MC_OK) return last_status = s;
	/* Pick up what is on the card first, so that files we did not load this
	 * session are not lost. A damaged save is replaced. */
	if (!cache_valid) {
		s = load_card();
		if (s != MC_OK && s != MC_NO_SAVE && s != MC_CORRUPT) return last_status = s;
		cache_valid = 1;
		s = MC_OK;
	}

	f = psx_fopen(path, "rb");
	if (!f) return last_status = MC_BAD_ARG;
	psx_fseek(f, 0, 2);
	size = psx_ftell(f);
	psx_fseek(f, 0, 0);
	raw = (uint8_t*)malloc(size ? (size_t)size : 1);
	comp = (uint8_t*)malloc(MCLZ_BOUND((size_t)size));
	if (!raw || !comp || (long)psx_fread(raw, 1, (size_t)size, f) != size) {
		psx_fclose(f); free(raw); free(comp);
		return last_status = MC_NO_MEMORY;
	}
	psx_fclose(f);

	psx_file_normalize(path, name, NAME_LEN);
	for (slot = 0; slot < file_count; slot++) if (!strcmp(files[slot].name, name)) break;
	if (slot == MAX_FILES) { free(raw); free(comp); return last_status = MC_BAD_ARG; }

	memset(&ne, 0, sizeof(ne));
	memcpy(ne.name, name, NAME_LEN - 1);
	ne.raw_size = (uint32_t)size;
	ne.crc = mclz_crc32(raw, (size_t)size, 0);
	ne.comp_size = (uint32_t)mclz_compress(raw, (size_t)size, comp);
	ne.comp = (uint8_t*)realloc(comp, ne.comp_size ? ne.comp_size : 1);
	if (!ne.comp) ne.comp = comp;
	comp = ne.comp;
	free(raw);

	memcpy(list, files, sizeof(files));
	list[slot] = ne;
	count = slot == file_count ? file_count + 1 : file_count;

	img = build_image(list, count, &nb);
	if (!img) {
		s = MC_FULL; /* more than 15 blocks of payload */
	} else {
		old_size = scan_card(&others);
		if (others + nb > MAX_BLOCKS) {
			s = MC_FULL;
		} else {
			if (old_size >= 0 && old_size != nb * BLOCK_SIZE) { erase(save_path); old_size = -1; }
			fd = old_size >= 0 ? open(save_path, FWRITE) : open(save_path, FCREATE | (nb << 16));
			if (fd < 0) {
				s = MC_WRITE_ERROR;
			} else {
				if (write(fd, img, (size_t)nb * BLOCK_SIZE) != nb * BLOCK_SIZE) s = MC_WRITE_ERROR;
				close(fd);
			}
		}
	}
	free(img);

	if (s == MC_OK) {
		/* Commit: the new blob replaces the old one in the cache. */
		if (slot < file_count) free(files[slot].comp);
		files[slot] = ne;
		file_count = count;
		last_blocks = nb;
	} else {
		free(comp);
	}
	last_frames = VSync(-1) - start;
	return last_status = s;
}
