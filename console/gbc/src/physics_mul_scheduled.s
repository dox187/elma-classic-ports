; Signed16 product shared by the scheduled cartridge. Squares up to 4095
; cover radial wheel distances. The general path shares the exact projection
; multiplier, which also handles -32768 and restores the physical ROM bank.
.module riding_mul_scheduled
.area _CODE
_riding_mul16::
 ldhl sp,#2
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
_riding_mul16_regs::
 ld a,d
 cp b
 jr nz,mul_product
 ld a,e
 cp c
 jr nz,mul_product
 ; Take the absolute value only for a table-sized square.
 ld a,d
 add #16
 cp #32
 jp nc,_riding_projection_signed16
 bit 7,d
 jr z,mul_square_index
 xor a
 sub e
 ld e,a
 sbc a,a
 sub d
 ld d,a
 ; -4096 is just outside the table. Its square is 0x01000000.
 bit 4,d
 jr z,mul_square_index
 ld hl,#0x0100
 ld de,#0
 ret
mul_square_index:
 ld a,#28
 ld (#0x2000),a
 ld h,d
 ld l,e
 add hl,hl
 add hl,hl
 set 6,h
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld l,(hl)
 ld h,#0
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret
mul_product:
 ; With either operand byte-sized, route the narrow one into DE to use
 ; a single product row. For wider pairs keep the caller's coefficient.
 ld a,b
 inc a
 cp #2
 jp nc,_riding_projection_signed16
 ld h,b
 ld l,c
 ld b,d
 ld c,e
 ld d,h
 ld e,l
 jp _riding_projection_signed16
