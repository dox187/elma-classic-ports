/* Adds what the game core uses beyond PSn00bSDK's <stdlib.h>. */
#ifndef ELMA_PSX_STDLIB_H
#define ELMA_PSX_STDLIB_H

#include_next <stdlib.h>

#ifdef __cplusplus
extern "C" {
#endif

int atoi(const char* text);
long atol(const char* text);
/* There is nothing to return to: shows the exit and stops (psx_platform). */
void exit(int status) __attribute__((noreturn));

#ifdef __cplusplus
}
#endif

#endif
