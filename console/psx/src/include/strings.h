/* Adds the case-insensitive comparisons to PSn00bSDK's <strings.h>. */
#ifndef ELMA_PSX_STRINGS_H
#define ELMA_PSX_STRINGS_H

#include_next <strings.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

int strcasecmp(const char* a, const char* b);
int strncasecmp(const char* a, const char* b, size_t n);

#ifdef __cplusplus
}
#endif

#endif
