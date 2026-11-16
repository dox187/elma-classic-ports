; Forward ZX0 v2 decompressor for ROM -> cartridge SRAM scenery blocks.
; GBDK ABI1: DE = compressed source, BC = destination; clobbers AF/BC/DE/HL.
; Interrupts may remain enabled. The interrupt handlers do not call this
; routine; one private HRAM byte retains its bit buffer.
;
; Based on the ZX0 standard decoder, Copyright (c) 2021, Einar Saukas.
; All rights reserved. Redistribution terms and disclaimer are retained in
; console/gbc/licenses/ZX0.txt.
;
; Keep the last offset on the stack and load it directly for each match,
; avoiding the standard SM83 decoder's two emulated EX (SP),HL sequences.
.module world_zx0

.area _HRAM
world_zx0_bits:
 .ds 1

.area _CODE
_zx0_decompress::
 ld h,d
 ld l,e
 ld d,b
 ld e,c
 ld bc,#65535
 push bc
 inc bc
 ld a,#128
world_zx0_literals:
 add a,a
 jr nz,world_zx0_literal_ready
 ld a,(hl+)
 rla
world_zx0_literal_ready:
 jr nc,world_zx0_literal_long
 ; Most literal runs contain one byte. C can retain the bit buffer here.
 ld c,a
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,c
 ld c,#0
world_zx0_literal_done:
 add a,a
 jr c,world_zx0_new_offset
 call world_zx0_elias
world_zx0_match:
 ldh (#world_zx0_bits),a
 push hl
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 add hl,de
 call world_zx0_copy
 pop hl
 ldh a,(#world_zx0_bits)
 add a,a
 jr nc,world_zx0_literals
world_zx0_new_offset:
 pop bc
 ld c,#254
 call world_zx0_elias_loop
 inc c
 ret z
 ld b,c
 ld c,(hl)
 inc hl
 rr b
 rr c
 push bc
 ld bc,#1
 call nc,world_zx0_elias_backtrack
 inc bc
 jr world_zx0_match

world_zx0_literal_long:
 ld bc,#1
 call world_zx0_elias_backtrack
 ldh (#world_zx0_bits),a
 call world_zx0_copy
 ldh a,(#world_zx0_bits)
 jr world_zx0_literal_done

; The sentinel refills before the stop/data pair, so its data bit cannot
; require a second refill. BC is zero before ordinary length decoding.
world_zx0_elias:
 inc c
world_zx0_elias_loop:
 add a,a
 jr nz,world_zx0_elias_ready
 ld a,(hl+)
 rla
world_zx0_elias_ready:
 ret c
world_zx0_elias_backtrack:
 add a,a
 rl c
 rl b
 jr world_zx0_elias_loop

; Copy a positive BC byte count, including overlapping matches. Return BC=0.
world_zx0_copy:
 srl b
 rr c
 inc b
 inc c
 jr c,world_zx0_copy_one
 jr world_zx0_copy_test
world_zx0_copy_two:
 ld a,(hl+)
 ld (de),a
 inc de
world_zx0_copy_one:
 ld a,(hl+)
 ld (de),a
 inc de
world_zx0_copy_test:
 dec c
 jr nz,world_zx0_copy_two
 dec b
 jr nz,world_zx0_copy_two
 ret
