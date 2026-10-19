/* The heap of the PlayStation version, in place of the SDK's malloc.c (all
 * of whose functions are weak symbols).
 *
 * The SDK's allocator keeps every block in one list and puts a new block in
 * the first gap between two blocks that is big enough; malloc and free walk
 * that list, and each block has 16 bytes of header. After the many
 * temporaries of a level load the first gaps that fit are often in the
 * wrong place, and the heap grows further than the game needs.
 *
 * Here the blocks lie one after the other from the start of the heap up to
 * top, each with an 8-byte header: its size (bit 0: in use) and the size of
 * the block below it. Free blocks are joined with free neighbours at once
 * and kept in a list of their own; a free block that reaches top lowers top
 * instead. malloc takes the smallest free block that is big enough (the
 * lowest of equal ones), else it extends top; free does not search. calloc
 * always clears the block. Not interrupt safe, like the SDK's. */
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>

#include "psx_mem.h"

#define HEADER 8u
#define MIN_BLOCK 16u
#define USED 1u

typedef struct block {
	uint32_t size;       /* bytes with the header; bit 0: in use */
	uint32_t prev_size;  /* the size of the block below, 0 for the first */
	/* Free blocks only: */
	struct block* next;
	struct block* prev;
} block;

psx_mem_stats_t psx_mem_stats;

static uint8_t* heap_start;
static uint8_t* heap_top;
static uint8_t* heap_limit;
static block* free_list;
static block* last;  /* the highest block, NULL if none */

static uint32_t size_of(const block* b) { return b->size & ~USED; }
static block* below(block* b) { return (block*)((uint8_t*)b - b->prev_size); }

static void list_add(block* b) {
	b->prev = NULL;
	b->next = free_list;
	if (free_list) free_list->prev = b;
	free_list = b;
	psx_mem_stats.free += b->size;
}

static void list_remove(block* b) {
	if (b->prev) b->prev->next = b->next;
	else free_list = b->next;
	if (b->next) b->next->prev = b->prev;
	psx_mem_stats.free -= b->size;
}

/* The size of b changed: the block above learns it. */
static void set_size(block* b, uint32_t size, uint32_t used) {
	b->size = size | used;
	uint8_t* end = (uint8_t*)b + size;
	if (end < heap_top) ((block*)end)->prev_size = size;
}

static uint32_t largest_listed(void) {
	uint32_t largest = 0;
	for (block* b = free_list; b; b = b->next)
		if (b->size > largest) largest = b->size;
	return largest;
}

static void moved_top(void) {
	psx_mem_stats.top = (uint32_t)heap_top;
	if (psx_mem_stats.top > psx_mem_stats.top_max) {
		psx_mem_stats.top_max = psx_mem_stats.top;
		psx_mem_stats.peak_allocated = psx_mem_stats.allocated;
		psx_mem_stats.peak_free = psx_mem_stats.free;
		psx_mem_stats.peak_largest_free = largest_listed();
	}
}

static void count_used(uint32_t size) {
	psx_mem_stats.allocated += size;
	psx_mem_stats.blocks++;
	if (psx_mem_stats.allocated > psx_mem_stats.allocated_max)
		psx_mem_stats.allocated_max = psx_mem_stats.allocated;
}

/* A free block (not listed) from b up: joined with the free blocks above
 * and below, then listed, or given back to top. */
static void release(block* b, uint32_t size) {
	uint8_t* end = (uint8_t*)b + size;
	if (end < heap_top) {
		block* a = (block*)end;
		if (!(a->size & USED)) {
			list_remove(a);
			size += a->size;
		}
	}
	if (b->prev_size) {
		block* p = below(b);
		if (!(p->size & USED)) {
			list_remove(p);
			size += p->size;
			b = p;
		}
	}
	if ((uint8_t*)b + size >= heap_top) {
		/* The block below b is in use (or there is none): */
		heap_top = (uint8_t*)b;
		last = b->prev_size ? below(b) : NULL;
		psx_mem_stats.top = (uint32_t)heap_top;
		return;
	}
	set_size(b, size, 0);
	list_add(b);
}

/* Bytes of the block for size bytes of data; 0 if impossible. */
static uint32_t block_size(size_t size) {
	if (size > 0x7ffffff0u) return 0;
	uint32_t need = ((uint32_t)size + HEADER + 7u) & ~7u;
	return need < MIN_BLOCK ? MIN_BLOCK : need;
}

/* Cuts b (in use, of its size) to need bytes; the rest is freed. */
static void trim(block* b, uint32_t need) {
	uint32_t size = size_of(b);
	if (size - need < MIN_BLOCK) return;
	set_size(b, need, USED);
	block* rest = (block*)((uint8_t*)b + need);
	rest->prev_size = need;
	psx_mem_stats.allocated -= size - need;
	release(rest, size - need);
}

void InitHeap(void* addr, size_t size) {
	uint8_t* start = (uint8_t*)(((uintptr_t)addr + 7u) & ~(uintptr_t)7u);
	heap_start = heap_top = start;
	heap_limit = (uint8_t*)(((uintptr_t)addr + size) & ~(uintptr_t)7u);
	free_list = NULL;
	last = NULL;
	memset(&psx_mem_stats, 0, sizeof(psx_mem_stats));
	psx_mem_stats.magic = 0x534D454Du; /* "MEMS" */
	psx_mem_stats.start = (uint32_t)heap_start;
	psx_mem_stats.limit = (uint32_t)heap_limit;
	psx_mem_stats.top = psx_mem_stats.top_max = (uint32_t)heap_top;
}

void* malloc(size_t size) {
	uint32_t need = block_size(size);
	if (!need || !heap_start) return NULL;

	block* best = NULL;
	for (block* b = free_list; b; b = b->next) {
		if (b->size < need) continue;
		if (!best || b->size < best->size || (b->size == best->size && b < best)) best = b;
		if (b->size == need) break;
	}
	if (best) {
		list_remove(best);
		set_size(best, best->size, USED);
		count_used(size_of(best));
		trim(best, need);
		return (uint8_t*)best + HEADER;
	}

	if ((uint32_t)(heap_limit - heap_top) < need) {
		psx_mem_stats.failed++;
		return NULL;
	}
	block* b = (block*)heap_top;
	b->prev_size = last ? size_of(last) : 0;
	b->size = need | USED;
	last = b;
	heap_top += need;
	count_used(need);
	moved_top();
	return (uint8_t*)b + HEADER;
}

void free(void* ptr) {
	if (!ptr) return;
	block* b = (block*)((uint8_t*)ptr - HEADER);
	uint32_t size = size_of(b);
	psx_mem_stats.allocated -= size;
	psx_mem_stats.blocks--;
	release(b, size);
}

void* calloc(size_t num, size_t size) {
	if (size && num > 0xffffffffu / size) return NULL;
	void* p = malloc(num * size);
	if (p) memset(p, 0, num * size);
	return p;
}

void* realloc(void* ptr, size_t size) {
	if (!ptr) return malloc(size);
	if (!size) {
		free(ptr);
		return NULL;
	}
	uint32_t need = block_size(size);
	if (!need) return NULL;
	block* b = (block*)((uint8_t*)ptr - HEADER);
	uint32_t have = size_of(b);
	if (need <= have) {
		trim(b, need);
		return ptr;
	}
	uint8_t* end = (uint8_t*)b + have;
	if (end == heap_top && (uint32_t)(heap_limit - (uint8_t*)b) >= need) {
		/* The highest block grows into the free space above: */
		b->size = need | USED;
		heap_top = (uint8_t*)b + need;
		count_used(need - have);
		moved_top();
		return ptr;
	}
	if (end < heap_top) {
		block* a = (block*)end;
		if (!(a->size & USED) && have + a->size >= need) {
			list_remove(a);
			set_size(b, have + a->size, USED);
			if (last == a) last = b;
			count_used(a->size);
			trim(b, need);
			return ptr;
		}
	}
	void* p = malloc(size);
	if (!p) return NULL;
	memcpy(p, ptr, have - HEADER);
	free(ptr);
	return p;
}

/* The SDK's other heap functions. Nothing may take memory past the blocks,
 * so sbrk always fails. */
void* sbrk(ptrdiff_t incr) {
	(void)incr;
	return NULL;
}

void TrackHeapUsage(ptrdiff_t alloc_incr) { (void)alloc_incr; }

void GetHeapUsage(HeapUsage* usage) {
	usage->total = (size_t)(heap_limit - heap_start);
	usage->heap = (size_t)(heap_top - heap_start);
	usage->stack = (size_t)(heap_limit - heap_top);
	usage->alloc = psx_mem_stats.allocated;
	usage->alloc_max = psx_mem_stats.allocated_max;
}
