/* One 16-byte GDMA block. The banked source can be ROM or cartridge RAM.
 * In double speed a sample of STAT mode 0 or 1 leaves at least the entire
 * 160-T mode 2 before VRAM closes, even on the last dot of HBlank/VBlank.
 * The test, launch and hardware transfer take at most 108 T from the start
 * of that STAT read. IRQs are masked throughout this short window. */
#include <gb/gb.h>
#include <stdint.h>

void world_upload_tile(uint16_t bank,uint16_t source,uint16_t pattern) NONBANKED __naked {
    bank; source; pattern;
    __asm
        ; SDCC ABI1 supplies the bank in DE, the source in BC and the
        ; physical pattern on the stack. The caller retains its logical ROM
        ; bank in __current_bank throughout the transfer.
        ld a,d
        ld (#0x3000),a
        ld a,e
        ld (#0x2000),a
        ld a,b
        ldh (#0x51),a
        ld a,c
        ldh (#0x52),a
        ldhl sp,#2
        ld a,(hl+)
        swap a
        ld b,a
        and a,#15
        ldh (#0x53),a
        ld a,b
        and a,#0xf0
        ldh (#0x54),a
        ld a,(hl)
        ; All nonzero high bytes select VBK1, matching pattern >= 256.
        sub a,#1
        sbc a,a
        inc a
        ldh (#0x4f),a
        ldh a,(#0x40)
        rlca
        jr nc,001$
        ldh a,(#0x44)
        sub a,#144
        cp a,#8
        jr nc,002$
001$:
        xor a
        ldh (#0x55),a
        jr 004$
002$:
        di
003$:
        ldh a,(#0x41)
        and a,#2
        jr nz,003$
        xor a
        ldh (#0x55),a
        ei
004$:
        xor a
        ld (#0x3000),a
        ldh (#0x4f),a
        ldh a,(#__current_bank)
        ld (#0x2000),a
        pop hl
        pop af
        jp (hl)
    __endasm;
}
