/* One aligned background pattern, directly from its MBC5 ROM bank.
 * VRAM is accessible during modes 0..2. Wait for a fresh mode 0 or mode 2
 * window with interrupts masked: the single 64-T-cycle block plus polling
 * latency fits mode 2's 160 double-speed T-cycles (and the longer mode 0).
 * https://gbdev.io/pandocs/CGB_Registers.html#lcd-vram-dma-transfers
 */
#include <gb/gb.h>
#include <gb/cgb.h>
#include <stdint.h>
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

void world_upload_tile(uint16_t bank,uint16_t source,uint16_t pattern) NONBANKED {
    uint8_t previous=CURRENT_BANK;
    uint16_t destination=0x8000U+((pattern&255)<<4);
    SWITCH_ROM_MBC5_8M(bank);
    VBK_REG=pattern>=256;
    HDMA1_REG=source>>8;HDMA2_REG=(uint8_t)source;
    HDMA3_REG=destination>>8;HDMA4_REG=(uint8_t)destination;
    if(!(LCDC_REG&LCDCF_ON) || (LY_REG>=144 && LY_REG<=151))HDMA5_REG=0;
    else {
        __critical {
            __asm
            ldh a,(#0x41)
            and a,#2
            jr z,001$
000$:
            ldh a,(#0x41)
            and a,#2
            jr nz,000$
            xor a
            ldh (#0x55),a
            jr 003$
001$:
            ldh a,(#0x41)
            and a,#2
            jr z,001$
            xor a
            ldh (#0x55),a
003$:
            __endasm;
        }
    }
    rROMB1=0;SWITCH_ROM(previous);VBK_REG=0;
}
