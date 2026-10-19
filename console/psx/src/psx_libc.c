/* The C library functions that the game core needs and PSn00bSDK lacks: the
 * standard FILE names over psx_file.c, access(), case-insensitive string
 * comparison and atoi. */
#include <ctype.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <strings.h>
#include <unistd.h>

#include "psx_file.h"

FILE* fopen(const char* path, const char* mode) { return psx_fopen(path, mode); }
int fclose(FILE* f) { return psx_fclose(f); }
size_t fread(void* buffer, size_t size, size_t count, FILE* f) {
	return psx_fread(buffer, size, count, f);
}
size_t fwrite(const void* buffer, size_t size, size_t count, FILE* f) {
	return psx_fwrite(buffer, size, count, f);
}
int fseek(FILE* f, long offset, int whence) { return psx_fseek(f, offset, whence); }
long ftell(FILE* f) { return psx_ftell(f); }
int fgetc(FILE* f) { return psx_fgetc(f); }
char* fgets(char* line, int size, FILE* f) { return psx_fgets(line, size, f); }
int fputc(int c, FILE* f) { return psx_fputc(c, f); }
int fputs(const char* text, FILE* f) { return psx_fputs(text, f); }
int vfprintf(FILE* f, const char* format, va_list args) { return psx_vfprintf(f, format, args); }
int fprintf(FILE* f, const char* format, ...) {
	va_list args;
	va_start(args, format);
	const int n = psx_vfprintf(f, format, args);
	va_end(args);
	return n;
}
int feof(FILE* f) { return psx_feof(f); }
int ferror(FILE* f) { return psx_ferror(f); }

/* Every file can be written (into RAM), so only reading needs checking. */
int access(const char* path, int mode) {
	(void)mode;
	return psx_access(path);
}

int strncasecmp(const char* a, const char* b, size_t n) {
	for (; n; n--, a++, b++) {
		const int ca = tolower((unsigned char)*a), cb = tolower((unsigned char)*b);
		if (ca != cb) return ca - cb;
		if (!ca) break;
	}
	return 0;
}

int strcasecmp(const char* a, const char* b) { return strncasecmp(a, b, (size_t)-1); }

long atol(const char* text) { return strtol(text, NULL, 10); }
int atoi(const char* text) { return (int)strtol(text, NULL, 10); }
