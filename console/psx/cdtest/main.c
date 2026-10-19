/*
 * Disc test of the PS1 side: mounts the game-data track, lists LEV/,
 * verifies every file against the manifest SUMS.TXT (CRC-32 of each file,
 * written by tools/mkdisc.py --manifest) and tries the track-1 fallback and
 * the psx_file backend. Progress goes to the TTY; the result is kept in
 * the global cdtest_state for the Lua check (test/cd_test.lua).
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <psxapi.h>
#include <psxgpu.h>
#include <psxcd.h>

#include "../src/cd/cdtrack.h"
#include "../src/cd/cdfile.h"

#define CDTEST_MAGIC 0x43445354u /* "CDST" */

/* Read by the test harness. Keep the layout stable (all words). */
typedef struct {
	volatile uint32_t magic;
	volatile uint32_t done;         /* 1 when the run is over */
	volatile uint32_t pass;         /* number of passed checks */
	volatile uint32_t fail;         /* number of failed checks */
	volatile uint32_t track;        /* mounted data track */
	volatile uint32_t base;         /* iso.base (exact start LBA) */
	volatile uint32_t track_base;   /* LBA the TOC gave */
	volatile uint32_t mount_frames; /* vblanks used by the mount of the data track */
	volatile uint32_t list_frames;  /* vblanks used by listing LEV/ */
	volatile uint32_t lev_count;    /* entries in LEV/ */
	volatile uint32_t files_ok;     /* manifest files that matched */
	volatile uint32_t bytes_read;   /* bytes verified */
	volatile uint32_t verify_frames;/* vblanks used by the verification */
	volatile uint32_t t1_ok;        /* track 1 fallback mount worked */
	volatile uint32_t backend_ok;   /* psx_file backend checks passed */
	volatile uint32_t toc_base2;    /* GetTD(2) as an LBA, 0xFFFFFFFF if unavailable */
	volatile uint32_t mount_err;    /* result code of the data track mount */
	volatile uint32_t probe_lba;    /* where a failed mount's probe found "CD001" (0 = nowhere) */
} CdTestState;

CdTestState cdtest_state;

static cdtrack_vol vol;
static cdtrack_vol vol1;
static uint32_t chunk[4096]; /* 16 KB, word aligned */
static uint32_t crc_table[256];

static void check(int ok, const char *what)
{
	if (ok) {
		cdtest_state.pass++;
	} else {
		cdtest_state.fail++;
		printf("CDTEST FAIL: %s\n", what);
	}
}

static void make_crc_table(void)
{
	int i, k;
	for (i = 0; i < 256; i++) {
		uint32_t c = (uint32_t)i;
		for (k = 0; k < 8; k++)
			c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
		crc_table[i] = c;
	}
}

static uint32_t crc_update(uint32_t crc, const uint8_t *p, uint32_t n)
{
	while (n--)
		crc = crc_table[(crc ^ *p++) & 0xFF] ^ (crc >> 8);
	return crc;
}

static uint32_t parse_hex(const char **s)
{
	uint32_t v = 0;
	for (;; (*s)++) {
		char c = **s;
		if (c >= '0' && c <= '9') v = v * 16 + (uint32_t)(c - '0');
		else if (c >= 'A' && c <= 'F') v = v * 16 + (uint32_t)(c - 'A' + 10);
		else if (c >= 'a' && c <= 'f') v = v * 16 + (uint32_t)(c - 'a' + 10);
		else break;
	}
	return v;
}

static uint32_t parse_dec(const char **s)
{
	uint32_t v = 0;
	while (**s >= '0' && **s <= '9')
		v = v * 10 + (uint32_t)(*(*s)++ - '0');
	return v;
}

/* CRC-32 (zlib) of a whole file, read in 16 KB pieces. */
static int file_crc(iso_vol *v, const iso_entry *e, uint32_t *crc_out)
{
	uint32_t crc = 0xFFFFFFFFu, off = 0;
	while (off < e->size) {
		int32_t n = iso_read(v, e, off, sizeof chunk, chunk);
		if (n <= 0)
			return -1;
		crc = crc_update(crc, (const uint8_t *)chunk, (uint32_t)n);
		off += (uint32_t)n;
		cdtest_state.bytes_read += (uint32_t)n;
	}
	*crc_out = crc ^ 0xFFFFFFFFu;
	return 0;
}

static void verify_manifest(iso_vol *v)
{
	iso_entry e;
	char *text, *line;
	uint32_t t0 = (uint32_t)VSync(-1);
	int r = iso_find(v, "SUMS.TXT", &e);

	check(r == ISO_OK, "SUMS.TXT present");
	if (r != ISO_OK)
		return;
	text = (char *)malloc(e.size + 1);
	check(text && iso_read(v, &e, 0, e.size, text) == (int32_t)e.size, "read SUMS.TXT");
	if (!text)
		return;
	text[e.size] = 0;
	for (line = text; *line;) {
		const char *p = line;
		uint32_t crc, size, got;
		iso_entry f;
		char path[64];
		int n = 0;
		crc = parse_hex(&p);
		while (*p == ' ') p++;
		size = parse_dec(&p);
		while (*p == ' ') p++;
		while (*p && *p != '\n' && n < 63)
			path[n++] = *p++;
		path[n] = 0;
		while (*p && *p != '\n') p++;
		if (*p == '\n') p++;
		line = (char *)p;
		if (!n)
			continue;
		if (iso_find(v, path, &f) != ISO_OK || f.size != size) {
			printf("CDTEST FAIL: %s missing or wrong size\n", path);
			cdtest_state.fail++;
			continue;
		}
		if (file_crc(v, &f, &got) != 0 || got != crc) {
			printf("CDTEST FAIL: %s crc %08x want %08x\n", path, (unsigned)got, (unsigned)crc);
			cdtest_state.fail++;
			continue;
		}
		cdtest_state.pass++;
		cdtest_state.files_ok++;
	}
	free(text);
	cdtest_state.verify_frames = (uint32_t)VSync(-1) - t0;
}

static void list_lev(iso_vol *v)
{
	iso_dir d;
	iso_entry e;
	uint32_t t0 = (uint32_t)VSync(-1);
	uint32_t count = 0, total = 0;
	int r = iso_opendir(v, "LEV", &d);

	check(r == ISO_OK, "open LEV/");
	if (r != ISO_OK)
		return;
	while (iso_readdir(v, &d, &e) > 0) {
		if (count < 3)
			printf("  LEV/%s %u bytes\n", e.name, (unsigned)e.size);
		count++;
		total += e.size;
	}
	cdtest_state.list_frames = (uint32_t)VSync(-1) - t0;
	cdtest_state.lev_count = count;
	printf("LEV/: %u entries, %u bytes\n", (unsigned)count, (unsigned)total);
	check(count > 0, "LEV/ is not empty");
}

/* The psx_file layer on top of the disc. */
static void test_backend(iso_vol *v)
{
	static cdfile_ctx ctx;
	static psx_file_backend backend;
	char name[32];
	int n = 0, ok_before = (int)cdtest_state.pass, fail_before = (int)cdtest_state.fail;
	iso_entry e;
	psx_file *f;

	cdfile_init(&ctx, v, &backend);
	psx_file_add_backend(&backend);
	/* index-by-index listing equals the directory */
	while (psx_file_list("lev", "*.LEV", n, name, sizeof name) == 0)
		n++;
	check((uint32_t)n == cdtest_state.lev_count, "psx_file_list counts LEV/*.LEV");
	if (n > 0) {
		check(psx_file_list("LEV", "*", 0, name, sizeof name) == 0, "psx_file_list first");
		if (iso_find(v, "LEV", &e) == ISO_OK) {
			iso_dir d;
			iso_entry first;
			check(iso_opendir_entry(v, &e, &d) == ISO_OK && iso_readdir(v, &d, &first) > 0 &&
			      strcmp(first.name, name) == 0, "listing order equals the directory");
		}
		/* open a file (size >= 16) the way the game does, with a DOS path */
		{
			char path[64];
			uint8_t head[16], again[16];
			iso_entry fe;
			int i;
			for (i = 0; i < n; i++) {
				psx_file_list("lev", "*.LEV", i, name, sizeof name);
				sprintf(path, "lev\\%s", name);
				if (iso_find(v, path, &fe) == ISO_OK && fe.size >= 16)
					break;
			}
			check(i < n, "a LEV file of at least 16 bytes");
			f = i < n ? psx_fopen(path, "rb") : NULL;
			check(f != NULL, "psx_fopen LEV file");
			if (f) {
				check(psx_fread(head, 1, sizeof head, f) == sizeof head, "psx_fread");
				check(iso_read(v, &fe, 0, sizeof again, again) == 16 &&
				      memcmp(again, head, 16) == 0, "bytes match");
				check(psx_fseek(f, 3, SEEK_SET) == 0 && psx_fgetc(f) == head[3], "seek + fgetc");
				psx_fclose(f);
			}
		}
	}
	check(psx_fopen("lev\\nonexistent.lev", "rb") == NULL, "missing file");
	check(psx_access("SUMS.TXT") == 0, "psx_access");
	if ((int)cdtest_state.fail == fail_before && (int)cdtest_state.pass > ok_before)
		cdtest_state.backend_ok = 1;
}

int main(int argc, const char **argv)
{
	int first = 0, last = 0, r;
	uint32_t t0;

	ResetGraph(0);
	SetVideoMode(MODE_NTSC);
	SetDispMask(1);
	cdtest_state.magic = CDTEST_MAGIC;
	make_crc_table();
	printf("CDTEST start\n");

	check(cdtrack_init() == 0, "CdInit");
	check(cdtrack_tracks(&first, &last) == 0, "GetTN");
	printf("tracks %d..%d\n", first, last);
	{
		int t;
		for (t = first; t <= last && t <= 4; t++)
			printf("  track %d: TOC start LBA %d\n", t, cdtrack_track_base(t));
		cdtest_state.toc_base2 = (uint32_t)cdtrack_track_base(2);
	}
	check(last >= 2, "disc has a second track");

	t0 = (uint32_t)VSync(-1);
	r = cdtrack_mount_data2(&vol);
	cdtest_state.mount_frames = (uint32_t)VSync(-1) - t0;
	cdtest_state.mount_err = (uint32_t)r;
	printf("mount data track: %d (track %d, toc base %d, start %u)\n", r, vol.track,
	       vol.track_base, (unsigned)vol.iso.base);
	check(r == ISO_OK, "mount the data track");
	if (r != ISO_OK) {
		/* diagnostics: what does the drive return around the TOC start? */
		int lba, base2 = (int)cdtest_state.toc_base2;
		for (lba = base2 - 20; lba < base2 + 40; lba += 4) {
			uint32_t secbuf[512];
			uint32_t f0 = (uint32_t)VSync(-1);
			int rr;
			memset(secbuf, 0xAA, sizeof secbuf); /* 0xAA left = no data was transferred */
			rr = cdtrack_read(0, (uint32_t)lba, 1, secbuf);
			uint8_t *b = (uint8_t *)secbuf;
			printf("probe LBA %d (%+d): %s %02x%02x%02x%02x%02x%02x %uf\n", lba, lba - base2,
			       rr == 0 ? "ok" : "FAIL", b[0], b[1], b[2], b[3], b[4], b[5],
			       (unsigned)VSync(-1) - f0);
		}
	}
	if (r == ISO_OK) {
		cdtest_state.track = (uint32_t)vol.track;
		cdtest_state.base = vol.iso.base;
		cdtest_state.track_base = (uint32_t)vol.track_base;
		check(vol.track == 2, "data is on track 2");
		list_lev(&vol.iso);
		{
			iso_entry e;
			check(iso_find(&vol.iso, "nope.lev", &e) == ISO_ERR_NOT_FOUND, "missing file reports NOT_FOUND");
		}
		verify_manifest(&vol.iso);
		test_backend(&vol.iso);
	}

	/* fallback: the ISO volume of the boot track */
	r = cdtrack_mount(&vol1, 1);
	{
		iso_entry e;
		check(r == ISO_OK && iso_find(&vol1.iso, "SYSTEM.CNF", &e) == ISO_OK &&
		      iso_find(&vol1.iso, "ELMA.EXE", &e) == ISO_OK, "track 1 fallback mount");
		cdtest_state.t1_ok = (r == ISO_OK);
	}

	printf("CDTEST %s: pass=%u fail=%u files=%u bytes=%u mount=%uf list=%uf verify=%uf\n",
	       cdtest_state.fail ? "FAIL" : "PASS", (unsigned)cdtest_state.pass,
	       (unsigned)cdtest_state.fail, (unsigned)cdtest_state.files_ok,
	       (unsigned)cdtest_state.bytes_read, (unsigned)cdtest_state.mount_frames,
	       (unsigned)cdtest_state.list_frames, (unsigned)cdtest_state.verify_frames);
	cdtest_state.done = 1;
	for (;;)
		VSync(0);
	return 0;
}
