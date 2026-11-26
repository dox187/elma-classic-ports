; Signed16 product shared by the scheduled cartridge. Squares up to 4095
; cover radial wheel distances. The general path shares the exact projection
; multiplier, which also handles -32768 and restores the physical ROM bank.
.module riding_mul_scheduled
.area _CODE
; Each coefficient selects one physical bank. The lower five bits select
; a pair of adjacent product planes in that bank.
_riding_scale_directory::
row = 0
.rept 256
 .db 36 + row/32
 row = row + 1
.endm
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
 ld h,#>_riding_small_squares
 ld l,e
 ld e,(hl)
 ld a,d
 add a
 add #>_riding_square_rows
 ld h,a
 ld d,(hl)
 inc h
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

; The wheel endpoint caller in bank 9 has already bounded both coordinates
; to [-409,409]. Read both squares with one bank change.
_riding_endpoint_squared::
 ld a,#28
 ld (#0x2000),a
 call endpoint_squared
 ld a,#9
 ld (#0x2000),a
 ret

.area _CODE_28
endpoint_squared:
 call endpoint_square
 push de
 push af
 ld d,b
 ld e,c
 call endpoint_square
 ld h,a
 pop bc
 ld l,b
 pop bc
 ld a,c
 add e
 ld c,a
 ld a,b
 adc d
 ld b,a
 ld a,l
 adc h
 ld e,a
 ld d,#0
 ret
endpoint_square:
 ld h,#>_riding_small_squares
 ld l,e
 ld e,(hl)
 ld a,d
 add #2
 and #3
 add a
 add #>_riding_endpoint_square_rows
 ld h,a
 ld d,(hl)
 inc h
 ld a,(hl)
 ret

.area _CODE
; Signed X in DE and Y in BC. The table contains the largest absolute Y
; strictly inside the original merge circle for each absolute X.
_riding_merge_close::
 ld a,d
 or a
 ld a,e
 jr z,merge_abs_x
 inc d
 jr nz,merge_far
 cpl
 inc a
 jr z,merge_far                ; -256 must not wrap to zero
merge_abs_x:
 ld l,a
 cp #102
 jr nc,merge_far
 ld a,b
 or a
 ld a,c
 jr z,merge_abs_y
 inc b
 jr nz,merge_far
 cpl
 inc a
 jr z,merge_far                ; -256
merge_abs_y:
 ld c,a
 ld h,#>_riding_merge_limit
 ld a,#28
 ld (#0x2000),a
 ld a,(hl)
 cp c
 ld a,#9
 ld (#0x2000),a
 sbc a,a
 inc a
 ret
merge_far:
 xor a
 ret
