/* Host test of the PS1 FILE layer (src/psx_file.c) with a backend that reads
 * a host directory, the way the PCdrv backend reads the host through the
 * emulator. Usage: core_file_test <scratch directory> */
#define _POSIX_C_SOURCE 200809L
#include "psx_file.h"

#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int failures = 0;
#define CHECK(x)                                                         \
	do {                                                                 \
		if (!(x)) {                                                      \
			printf("FAIL line %d: %s\n", __LINE__, #x);                  \
			failures++;                                                  \
		}                                                                \
	} while (0)

static char root[512];
static int reads = 0;

static int host_open(void* context, const char* path, long* size) {
	(void)context;
	char full[1024];
	snprintf(full, sizeof(full), "%s/%s", root, path);
	const int fd = open(full, O_RDONLY);
	if (fd < 0) return -1;
	struct stat st;
	fstat(fd, &st);
	*size = (long)st.st_size;
	return fd;
}

static int host_read(void* context, int handle, long offset, void* buffer, int n) {
	(void)context;
	reads++;
	return (int)pread(handle, buffer, (size_t)n, offset);
}

static void host_close(void* context, int handle) {
	(void)context;
	close(handle);
}

static int host_list(void* context, const char* dir, int index, char* name, int size) {
	(void)context;
	char full[1024];
	snprintf(full, sizeof(full), "%s/%s", root, dir);
	DIR* d = opendir(full);
	if (!d) return 1;
	struct dirent* e;
	int i = 0;
	while ((e = readdir(d)) != NULL) {
		if (e->d_name[0] == '.') continue;
		if (i++ == index) {
			snprintf(name, (size_t)size, "%s", e->d_name);
			closedir(d);
			return 0;
		}
	}
	closedir(d);
	return 1;
}

static void write_host(const char* path, const void* data, size_t n) {
	char full[1024];
	snprintf(full, sizeof(full), "%s/%s", root, path);
	FILE* h = fopen(full, "wb");
	fwrite(data, 1, n, h);
	fclose(h);
}

int main(int argc, char** argv) {
	if (argc < 2) return 2;
	snprintf(root, sizeof(root), "%s", argv[1]);
	char dir[1024];
	mkdir(root, 0755);
	snprintf(dir, sizeof(dir), "%s/LEV", root);
	mkdir(dir, 0755);

	/* A 10000 byte file of known bytes, a text file and two levels. */
	static unsigned char big[10000];
	for (int i = 0; i < (int)sizeof(big); i++) big[i] = (unsigned char)(i * 7 + i / 256);
	write_host("ELMA.RES", big, sizeof(big));
	const char text[] = "first line\nsecond\r\nlast";
	write_host("TEXT.TXT", text, strlen(text));
	write_host("LEV/QWQUU001.LEV", "a", 1);
	write_host("LEV/MY.LEV", "b", 1);
	write_host("LEV/NOTES.TXT", "c", 1);

	psx_file_backend host = {"host", host_open, host_read, host_close, host_list, NULL};
	psx_file_add_backend(&host);

	char path[64];
	psx_file_normalize(".\\lgr\\default.lgr", path, sizeof(path));
	CHECK(strcmp(path, "LGR/DEFAULT.LGR") == 0);

	CHECK(psx_fopen("missing.dat", "rb") == NULL);
	CHECK(psx_access("elma.res") == 0);
	CHECK(psx_access("nothere") == -1);

	/* Reads of every size from every place give the file's bytes. */
	psx_file* f = psx_fopen("elma.res", "rb");
	CHECK(f != NULL);
	static unsigned char got[10000];
	const long positions[] = {0, 1, 2047, 2048, 2049, 4095, 6000, 9999};
	const long lengths[] = {1, 4, 100, 2047, 2048, 2049, 5000};
	for (unsigned p = 0; p < sizeof(positions) / sizeof(positions[0]); p++) {
		for (unsigned l = 0; l < sizeof(lengths) / sizeof(lengths[0]); l++) {
			long want = lengths[l];
			if (positions[p] + want > (long)sizeof(big)) want = (long)sizeof(big) - positions[p];
			CHECK(psx_fseek(f, positions[p], SEEK_SET) == 0);
			CHECK(psx_fread(got, 1, (size_t)want, f) == (size_t)want);
			CHECK(memcmp(got, big + positions[p], (size_t)want) == 0);
			CHECK(psx_ftell(f) == positions[p] + want);
		}
	}
	/* Past the end: a short count of whole items. */
	CHECK(psx_fseek(f, -10, SEEK_END) == 0);
	CHECK(psx_ftell(f) == 9990);
	CHECK(psx_fread(got, 4, 3, f) == 2);
	CHECK(psx_feof(f));
	CHECK(psx_fseek(f, 4, SEEK_SET) == 0);
	CHECK(psx_fseek(f, 4, SEEK_CUR) == 0);
	CHECK(psx_ftell(f) == 8);
	/* Sequential small reads use the buffer instead of the backend. */
	reads = 0;
	CHECK(psx_fseek(f, 0, SEEK_SET) == 0);
	for (int i = 0; i < 2048; i++) CHECK(psx_fgetc(f) == big[i]);
	CHECK(reads <= 1);
	CHECK(psx_fwrite("x", 1, 1, f) == 0);
	psx_fclose(f);

	/* Text lines keep their line ends, as on the desktop Linux builds. */
	f = psx_fopen("text.txt", "rt");
	char line[100];
	CHECK(psx_fgets(line, sizeof(line), f) && strcmp(line, "first line\n") == 0);
	CHECK(psx_fgets(line, sizeof(line), f) && strcmp(line, "second\r\n") == 0);
	CHECK(psx_fgets(line, 3, f) && strcmp(line, "la") == 0);
	CHECK(psx_fgets(line, sizeof(line), f) && strcmp(line, "st") == 0);
	CHECK(psx_fgets(line, sizeof(line), f) == NULL);
	psx_fclose(f);

	/* Backend files cannot be changed; written files live in RAM. */
	CHECK(psx_fopen("elma.res", "r+b") == NULL);
	f = psx_fopen("state.dat", "wb");
	CHECK(f != NULL);
	CHECK(psx_fwrite(big, 1, 5000, f) == 5000);
	CHECK(psx_fprintf(f, "%d %s", 42, "end") == 6);
	psx_fclose(f);
	f = psx_fopen("STATE.DAT", "rb");
	CHECK(f != NULL);
	CHECK(psx_fread(got, 1, 6000, f) == 5006);
	CHECK(memcmp(got, big, 5000) == 0 && memcmp(got + 5000, "42 end", 6) == 0);
	psx_fclose(f);
	f = psx_fopen("state.dat", "at");
	CHECK(psx_fputs("!", f) == 0);
	psx_fclose(f);
	f = psx_fopen("state.dat", "rb");
	CHECK(psx_fseek(f, 0, SEEK_END) == 0 && psx_ftell(f) == 5007);
	psx_fclose(f);
	f = psx_fopen("state.dat", "wb");
	psx_fclose(f);
	f = psx_fopen("state.dat", "rb");
	CHECK(psx_fread(got, 1, 1, f) == 0);
	psx_fclose(f);

	/* Big RAM files are kept packed while no file is open on them (the
	 * packer, src/memcard/mclz.c, is linked in, as in the game). */
	{
		static unsigned char text[20000], back[20001];
		for (int i = 0; i < (int)sizeof(text); i++) text[i] = (unsigned char)"elasto mania "[i % 13];
		const long before = psx_file_ram_used();
		f = psx_fopen("pack\\text.txt", "wb");
		CHECK(psx_fwrite(text, 1, sizeof(text), f) == sizeof(text));
		psx_fclose(f);
		CHECK(psx_file_ram_used() - before < 2000);
		CHECK(psx_access("pack\\text.txt") == 0);
		f = psx_fopen("pack\\text.txt", "ab");
		CHECK(psx_fputs("!", f) == 0);
		psx_fclose(f);
		f = psx_fopen("pack\\text.txt", "rb");
		CHECK(psx_fread(back, 1, sizeof(back), f) == sizeof(back));
		CHECK(memcmp(back, text, sizeof(text)) == 0 && back[sizeof(text)] == '!');
		psx_fclose(f);
		CHECK(psx_file_ram_used() - before < 2000);
		f = psx_fopen("pack\\text.txt", "wb");
		psx_fclose(f);
		CHECK(psx_file_ram_used() == before);
	}

	/* The RAM limit makes writes come up short instead of failing hard. */
	psx_file_set_ram_limit(psx_file_ram_used() + 3000);
	f = psx_fopen("rec\\big.rec", "wb");
	CHECK(psx_fwrite(big, 1, 2000, f) == 2000);
	CHECK(psx_fwrite(big, 1, 2000, f) < 2000);
	CHECK(psx_ferror(f));
	psx_fclose(f);
	psx_file_set_ram_limit(512 * 1024);

	/* Discarded files take writes and read back as missing. */
	psx_file_discard("stats.txt");
	f = psx_fopen("stats.txt", "wt");
	CHECK(f != NULL && psx_fprintf(f, "%s\n", "times") == 6);
	psx_fclose(f);
	CHECK(psx_access("stats.txt") == -1);

	/* Listing merges the RAM files with the backend's. */
	f = psx_fopen("lev\\new.lev", "wb");
	psx_fputs("n", f);
	psx_fclose(f);
	int count = 0, found_new = 0, found_my = 0;
	char name[32];
	for (int i = 0; psx_file_list("lev", "*.lev", i, name, sizeof(name)) == 0; i++) {
		count++;
		found_new |= strcmp(name, "NEW.LEV") == 0;
		found_my |= strcmp(name, "MY.LEV") == 0;
	}
	CHECK(count == 3 && found_new && found_my);
	/* Listing again, or out of order, starts over correctly. */
	int again = 0;
	for (int i = 0; psx_file_list("lev", "*.lev", i, name, sizeof(name)) == 0; i++) again++;
	CHECK(again == 3);
	char second[32];
	CHECK(psx_file_list("lev", "*.lev", 1, second, sizeof(second)) == 0);
	CHECK(psx_file_list("lev", "*.lev", 0, name, sizeof(name)) == 0 && strcmp(name, second) != 0);
	CHECK(psx_file_list("lev", "*.lev", 1, name, sizeof(name)) == 0 && strcmp(name, second) == 0);
	CHECK(psx_file_list("lev", "*.rec", 0, name, sizeof(name)) != 0);
	CHECK(psx_file_list("rec", "*.rec", 0, name, sizeof(name)) == 0 &&
	      strcmp(name, "BIG.REC") == 0);

	printf("%s (%d failures)\n", failures ? "FAIL" : "PASS", failures);
	return failures ? 1 : 0;
}
