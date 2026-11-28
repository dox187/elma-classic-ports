.module normal_sram
; SRAM0 A000..A7FF contains scenery IDs and the object certificates. The
; map begins at B000; A800..AA51 is the directory (297 banked row pointers).
; Scratch SRAM1..3 are available only with signed-background graphics.
normal_directory = 0xa800
.area _DATA
normal_sram_ready:: .ds 1
normal_high_digits: .ds 1
.area _CODE_13
; Expand all reciprocal rows once when selecting the first signed-background
; course. Source, table directory and scratch banks are internal to this cart.
normal_sram_init::
 ld a,#10
 ld (#0),a
 xor a
 ld (#0x4000),a
 ld hl,#594
 push hl
 ld hl,#normal_directory
 push hl
 ld hl,#_riding_normal_rsqrt
 push hl
 ld hl,#9
 push hl
 call _world_far_copy
 add sp,#8
 ld hl,#normal_directory
 ld de,#0xa000
 ld a,#1
 ld (#normal_sram_ready),a
 ld a,#16
 ld (#normal_high_digits),a
build_product_row:
 ; Read the coefficient from SRAM0 before replacing it with its directory
 ; entry. Each row begins at a multiple of four, so its bank fits the low bits.
 ld c,(hl)
 ld a,(#normal_sram_ready)
 or e
 ld (hl+),a
 ld b,(hl)
 ld (hl),d
 inc hl
 push hl
 ld a,(#normal_sram_ready)
 ld (#0x4000),a
 ld a,e
 add #30
 ld e,a
 push de
 ld hl,#0
 ld a,(#normal_high_digits)
 inc a
build_raw:
 push af
 ld a,l
 ld (de),a
 inc e
 ld a,h
 ld (de),a
 inc de
 add hl,bc
 pop af
 dec a
 jr nz,build_raw
 pop hl
 push de
 ; Raw zero shares its word with fractional zero. Copy the next fifteen
 ; raw products into reversed slots, divided by sixteen and rounded down.
 ld e,l
 ld d,h
 dec e
 dec e
 inc l
 inc l
 ld b,#15
build_floor:
 ld a,(hl+)
 swap a
 and #15
 ld c,a
 ld a,(hl)
 swap a
 and #240
 or c
 ld (de),a
 inc e
 ld a,(hl+)
 swap a
 and #15
 ld (de),a
 dec e
 dec e
 dec e
 dec b
 jr nz,build_floor
 pop de
 pop hl
 xor a
 ld (#0x4000),a
 ld a,h
 cp #>(normal_directory+594)
 jr nz,build_more
 ld a,l
 cp #<(normal_directory+594)
 ret z
build_more:
 ld a,h
 cp #>(normal_directory+192)
 jr nz,build_next
 ld a,l
 cp #<(normal_directory+192)
 jr nz,build_next
 ld a,#26
 ld (#normal_high_digits),a
build_next:
 ld a,e
 cp #252
 jr nz,build_page
 ld e,#0
 inc d
build_page:
 ld a,d
 cp #192
 jp nz,build_product_row
 ld a,(#normal_sram_ready)
 inc a
 ld (#normal_sram_ready),a
 ld de,#0xa000
 jp build_product_row

normal_sram_axes::
 ld hl,#normal_directory
 add hl,bc
 ld a,(hl+)
 ld h,(hl)
 ld c,a
 and #252
 ld b,a
 ld a,c
 and #3
 ld (#0x4000),a
normal_sram_mapped::
 ld a,(#normal_cache_key)
 ld e,a
 ld a,(#normal_cache_key+1)
 ld d,a
 call normal_sram_axis
 ld a,e
 ld (#normal_cache_value),a
 ld a,d
 ld (#normal_cache_value+1),a
 ld a,(#normal_cache_key+2)
 ld e,a
 ld a,(#normal_cache_key+3)
 ld d,a
 call normal_sram_axis
 ld a,e
 ld (#normal_cache_value+2),a
 ld a,d
 ld (#normal_cache_value+3),a
 xor a
 ld (#0x4000),a
 ret

; Page H and row base B survive both axes. For x=16*h+l, the signed
; result is h*r + floor(l*r/16). Every shipped physical coordinate fits.
normal_sram_axis:
 ld a,e
 cpl
 and #15
 add a
 add b
 ld l,a
 ld a,(hl+)
 ld c,a
 ld a,e
 swap a
 and #15
 ld e,a
 ld a,d
 swap a
 and #240
 or e
 bit 7,d
 ld d,(hl)
 jr nz,product_sub
 add a
 add b
 add #30
 ld l,a
 ld a,(hl+)
 add c
 ld e,a
 ld a,(hl)
 adc d
 ld d,a
 ret
product_sub:
 cpl
 inc a
 add a
 add b
 add #30
 ld l,a
 ld a,c
 sub (hl)
 ld e,a
 inc l
 ld a,d
 sbc (hl)
 ld d,a
 ret
