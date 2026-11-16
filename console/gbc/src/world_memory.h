#ifndef GBC_WORLD_MEMORY_H
#define GBC_WORLD_MEMORY_H
#include <stdint.h>

#ifdef __SDCC
#define WORLD_MEMORY_CALL __sdcccall(0)
#else
#define WORLD_MEMORY_CALL
#endif

/* Scratch SRAM: 4096 little-endian words per 8 KiB RAM bank. Clear enables
 * cartridge RAM; keep it enabled while using get/set. Every call leaves RAM
 * bank zero selected. No persistent save records share this scratch space. */
uint16_t world_lookup_get(uint16_t id) WORLD_MEMORY_CALL;
void world_lookup_set(uint16_t id,uint16_t slot) WORLD_MEMORY_CALL;
void world_lookup_clear(uint16_t count) WORLD_MEMORY_CALL;

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

/* Physical-slot mirror in SRAM bank8, first2048bytes. Each axis wraps32
 * independently; count is0..21 and slots is a WRAM array of little-endian
 * words. RAM must already be enabled. Every call returns RAM bank0.
 * While this mirror is active, pattern lookup IDs must remain below32768. */
void world_slot_strip_get(uint8_t x,uint8_t y,uint8_t vertical,uint8_t count,
                          uint16_t *slots) WORLD_MEMORY_CALL;
void world_slot_strip_set(uint8_t x,uint8_t y,uint8_t vertical,uint8_t count,
                          const uint16_t *slots) WORLD_MEMORY_CALL;

#undef WORLD_MEMORY_CALL
#endif
