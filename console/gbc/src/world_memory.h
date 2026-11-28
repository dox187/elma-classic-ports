#ifndef GBC_WORLD_MEMORY_H
#define GBC_WORLD_MEMORY_H
#include <stdint.h>

#ifdef __SDCC
#define WORLD_MEMORY_CALL __sdcccall(0)
#else
#define WORLD_MEMORY_CALL
#endif

/* On the signed 8 MiB cart, SRAM0 A000..A56F belongs to scenery.
 * The two object-membership pages end at A7FF. The 297 radial product row
 * pointers occupy A800..AA51, below the B000 map mirror. */
#define WORLD_OBJECT_X_REGIONS 0xa600
#define WORLD_OBJECT_Y_REGIONS 0xa700

/* Compact SRAM bank0 lookup: 1024 bucket heads at A000-A7FF and 444
 * slot-indexed {id,next} entries at A800-AEEF. IDs span all 16 bits; slots
 * are 0..443 or FFFF to remove an ID. Remove a slot's previous ID before
 * reusing it. get returns FFFF for an absent ID. Clear ignores count and
 * resets the fixed table, enabling RAM. Keep RAM enabled for get/set.
 * Every call leaves RAM bank0 selected; AEF0 onward survives. Banks1..3
 * survive in this default mode; raw_clear explicitly selects their use. */
uint16_t world_lookup_get(uint16_t id) WORLD_MEMORY_CALL;
void world_lookup_set(uint16_t id,uint16_t slot) WORLD_MEMORY_CALL;
/* Acquisition-only insertion: id must be absent and slot's old binding
 * removed. Skip the redundant absence search; mapping order is private. */
void world_lookup_insert_absent(uint16_t id,uint16_t slot) WORLD_MEMORY_CALL;
void world_lookup_clear(uint16_t count) WORLD_MEMORY_CALL;
/* Raw only: use SRAM1..3 for exact IDs0..12287 when count<=12288,
 * otherwise select the normal linked table. Invalid direct IDs are absent. */
void world_lookup_raw_clear(uint16_t count) WORLD_MEMORY_CALL;

/* ROM0 helper for MBC5 banks 0..511. Source may be fixed ROM below 0x4000
 * or lie within the selected 0x4000..0x7fff window; a copy must not cross
 * either window's end. Split such reads at bank boundaries. Interrupts stay
 * enabled; interrupt handlers must stay in ROM0 and avoid bank switches.
 * On return ROMB1 is zero and ROMB0/CURRENT_BANK equal the prior low bank. */
void world_far_copy(uint16_t bank,const uint8_t *source,uint8_t *dest,
                    uint16_t length) WORLD_MEMORY_CALL;
/* Strided source reads for one tile-map row/column. Count zero is a no-op;
 * every addressed source byte must remain within the selected ROM window. */
void world_far_gather(uint16_t bank,const uint8_t *source,uint8_t *dest,
                      uint8_t count,uint8_t stride) WORLD_MEMORY_CALL;

/* Read a decoded scenery strip from scratch SRAM, restoring RAM bank zero. */
void world_sram_gather(uint8_t bank,const uint8_t *source,uint8_t *dest,
                       uint8_t count,uint8_t stride) WORLD_MEMORY_CALL;

/* Physical-slot mirror in SRAM bank0, B000-B7FF. Each axis wraps32
 * independently; count is0..21 and slots is a WRAM array of little-endian
 * words. RAM must already be enabled. Every call returns RAM bank0. */
void world_slot_strip_get(uint8_t x,uint8_t y,uint8_t vertical,uint8_t count,
                          uint16_t *slots) WORLD_MEMORY_CALL;
void world_slot_strip_set(uint8_t x,uint8_t y,uint8_t vertical,uint8_t count,
                          const uint16_t *slots) WORLD_MEMORY_CALL;

#undef WORLD_MEMORY_CALL
#endif
