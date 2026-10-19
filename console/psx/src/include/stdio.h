/* PSn00bSDK's <stdio.h> has printf and sprintf but no files; the FILE
 * functions of the PS1 build come from psx_file.c (see psx_file.h). */
#ifndef ELMA_PSX_STDIO_H
#define ELMA_PSX_STDIO_H

#include_next <stdio.h>
#include <stdarg.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct psx_file FILE;

#ifndef EOF
#define EOF (-1)
#endif
/* <psxapi.h> has these as an enum of the BIOS file functions: include it
 * before this header where both are needed. */
#ifndef SEEK_SET
#define SEEK_SET 0
#define SEEK_CUR 1
#define SEEK_END 2
#endif

FILE* fopen(const char* path, const char* mode);
int fclose(FILE* f);
size_t fread(void* buffer, size_t size, size_t count, FILE* f);
size_t fwrite(const void* buffer, size_t size, size_t count, FILE* f);
int fseek(FILE* f, long offset, int whence);
long ftell(FILE* f);
int fgetc(FILE* f);
char* fgets(char* line, int size, FILE* f);
int fputc(int c, FILE* f);
int fputs(const char* text, FILE* f);
int fprintf(FILE* f, const char* format, ...);
int vfprintf(FILE* f, const char* format, va_list args);
int feof(FILE* f);
int ferror(FILE* f);

#ifdef __cplusplus
}
#endif

#endif
