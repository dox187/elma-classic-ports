/* The heap of the PlayStation version (psx_mem.c): malloc, calloc, realloc
 * and free, with InitHeap and GetHeapUsage of the SDK, in place of the
 * SDK's allocator (whose functions are weak). Statistics for the tests. */
#ifndef PSX_MEM_H
#define PSX_MEM_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Read (and the *_max fields reset) by test/mem_test.lua through the symbol
 * map. Keep the layout. Byte counts include the 8-byte block headers. */
typedef struct {
	uint32_t magic;          /* "MEMS" */
	uint32_t start, limit;   /* the heap's address range */
	uint32_t top;            /* end of the highest block */
	uint32_t allocated;      /* bytes in used blocks */
	uint32_t allocated_max;
	uint32_t top_max;        /* high-water of top */
	uint32_t free;           /* bytes in free blocks below top */
	uint32_t blocks;         /* used blocks */
	uint32_t failed;         /* allocations that did not fit */
	/* At the last high-water of top: */
	uint32_t peak_allocated, peak_free, peak_largest_free;
} psx_mem_stats_t;

extern psx_mem_stats_t psx_mem_stats;

#ifdef __cplusplus
}
#endif

#endif
