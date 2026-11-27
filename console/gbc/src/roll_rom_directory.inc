.globl ground_projection_bank
.globl slope_descriptor
.globl near_page
; A bank and both entry points are used only after verifying all four tangent bytes.
rom_slope_find::
 ldhl sp,#0
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
rom_slope_find_regs::
 ld a,c
 xor e
 ld l,a
 xor b
 and #1
 add #0x42
 ld h,a
 ld a,l
 rlca
 rlca
 rlca
 xor d
 ld l,a
rom_slope_probe:
 ld a,(hl)
 or a
 jp z,rom_slope_miss
 push hl
 inc h
 inc h
 ld a,(hl)
 cp e
 jr nz,rom_slope_next
 inc h
 inc h
 ld a,(hl)
 cp d
 jr nz,rom_slope_next
 inc h
 inc h
 ld a,(hl)
 cp c
 jr nz,rom_slope_next
 inc h
 inc h
 ld a,(hl)
 cp b
 jr nz,rom_slope_next
 pop hl
 ld a,(hl)
 ldh (#ground_projection_bank),a
 ld a,h
 add #10
 ld h,a
 ld a,(hl)
 add a
 ld l,a
 ld h,#>rom_slope_output_addresses
 ld a,(hl+)
 ldh (#slope_descriptor),a
 ld a,(hl)
 ldh (#slope_descriptor+1),a
 dec l
 set 3,l
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,#4
 ldh (#near_page),a
 ldh a,(#ground_projection_bank)
 jp rom_slope_map
rom_slope_next:
 pop hl
 inc l
 jr nz,rom_slope_probe
 ld a,h
 xor #1
 ld h,a
 jr rom_slope_probe
 .bndry 256
rom_slope_output_addresses::
 .dw rom_slope_project_0,rom_slope_project_1,rom_slope_project_2,rom_slope_project_3
 .dw rom_slope_inputs_0,rom_slope_inputs_1,rom_slope_inputs_2,rom_slope_inputs_3
