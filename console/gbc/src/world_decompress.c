#include <gb/gb.h>
#include <gbdk/zx0decompress.h>

/* Decode one bounded block into the scenery scratch area. Interrupt handlers
 * remain in ROM0 and do not access cartridge RAM or switch ROM banks. */
void world_decompress(uint16_t bank,uint16_t source,uint8_t ram_bank,uint16_t dest) NONBANKED {
    uint8_t previous=CURRENT_BANK;
    SWITCH_ROM_MBC5_8M(bank);
    rRAMB=ram_bank;
    zx0_decompress((void *)source,(void *)dest);
    rRAMB=0;
    rROMB1=0;SWITCH_ROM(previous);
}
