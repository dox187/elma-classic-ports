/* Check in-place realloc accounting without replacing the host's allocator.
 * Blocks stay large enough for the free-list pointers of a 64-bit host. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct {
    size_t total, heap, stack, alloc, alloc_max;
} HeapUsage;

#define malloc test_malloc
#define calloc test_calloc
#define realloc test_realloc
#define free test_free
#define sbrk test_sbrk
#include "../src/mem/psx_mem.c"

static union { uint64_t align; uint8_t bytes[4096]; } arena;

int main(void) {
    InitHeap(arena.bytes, sizeof(arena.bytes));
    uint8_t* a = malloc(128);
    assert(a);
    memset(a, 0x5a, 128);
    assert(realloc(a, 256) == a);
    assert(psx_mem_stats.blocks == 1 && psx_mem_stats.allocated == 264);
    for (int i = 0; i < 128; ++i) assert(a[i] == 0x5a);
    free(a);
    assert(psx_mem_stats.blocks == 0 && psx_mem_stats.allocated == 0);

    InitHeap(arena.bytes, sizeof(arena.bytes));
    a = malloc(128);
    void* gap = malloc(512);
    void* upper = malloc(128);
    assert(a && gap && upper);
    free(gap);
    assert(realloc(a, 256) == a);
    assert(psx_mem_stats.blocks == 2 && psx_mem_stats.allocated == 400);
    free(a);
    free(upper);
    assert(psx_mem_stats.blocks == 0 && psx_mem_stats.allocated == 0);
    puts("PASS: in-place realloc preserves the live block count");
    return 0;
}
