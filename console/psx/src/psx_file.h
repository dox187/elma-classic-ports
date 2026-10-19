/* A small FILE layer for the PS1 build: PSn00bSDK has no <stdio.h> files.
 *
 * Reading goes through pluggable backends (PCdrv host files during
 * development, the CD later). Files the game writes (state.dat, replays) are
 * kept in RAM for the session; a memory card backend can take them later.
 *
 * Paths are given the DOS way the game uses ("lgr\\default.lgr"); they are
 * turned into upper case with '/' separators ("LGR/DEFAULT.LGR"), the
 * names of an ISO9660 disc, before a backend sees them.
 *
 * Plain C, so that the layer can also be tested on the host
 * (test/core_file_test.c). */
#ifndef ELMA_PSX_FILE_H
#define ELMA_PSX_FILE_H

#include <stdarg.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct psx_file psx_file;

/* A source of read-only files. */
typedef struct psx_file_backend {
	const char* name;
	/* Opens a file for reading. Returns a handle >= 0 and stores the size,
	 * or returns -1 if the file is not there. */
	int (*open)(void* context, const char* path, long* size);
	/* Reads up to n bytes from offset; returns the number read or -1. */
	int (*read)(void* context, int handle, long offset, void* buffer, int n);
	void (*close)(void* context, int handle);
	/* Optional: the index-th file name in directory dir ("" is the root),
	 * upper case, without the directory. Returns 0, or nonzero after the
	 * last one. */
	int (*list)(void* context, const char* dir, int index, char* name, int size);
	void* context;
} psx_file_backend;

/* Backends are asked in the order they were added. At most 4. */
void psx_file_add_backend(const psx_file_backend* backend);
/* Files the game writes stay in RAM up to this many bytes in all (default
 * 512 KB); beyond it writes come up short. */
void psx_file_set_ram_limit(long bytes);
/* Writes to this file are accepted and thrown away (e.g. the statistics
 * text the game exports after every run). At most 8 names. */
void psx_file_discard(const char* path);
/* Bytes held by the files in RAM. */
long psx_file_ram_used(void);

/* "LGR\DEFAULT.LGR" -> "LGR/DEFAULT.LGR". */
void psx_file_normalize(const char* path, char* out, int size);

psx_file* psx_fopen(const char* path, const char* mode);
int psx_fclose(psx_file* f);
size_t psx_fread(void* buffer, size_t size, size_t count, psx_file* f);
size_t psx_fwrite(const void* buffer, size_t size, size_t count, psx_file* f);
int psx_fseek(psx_file* f, long offset, int whence);
long psx_ftell(psx_file* f);
int psx_fgetc(psx_file* f);
char* psx_fgets(char* line, int size, psx_file* f);
int psx_fputc(int c, psx_file* f);
int psx_fputs(const char* text, psx_file* f);
int psx_vfprintf(psx_file* f, const char* format, va_list args);
int psx_fprintf(psx_file* f, const char* format, ...);
int psx_feof(psx_file* f);
int psx_ferror(psx_file* f);
/* 0 if the file can be opened for reading, -1 if not. */
int psx_access(const char* path);
/* Directory listing for the game's fifirst/finext: the index-th name in dir
 * that matches pattern ("*.LEV", "*" or an exact name), from the RAM files
 * and every backend. Returns 0, or nonzero after the last one. */
int psx_file_list(const char* dir, const char* pattern, int index, char* name, int size);

#ifdef __cplusplus
}
#endif

#endif
