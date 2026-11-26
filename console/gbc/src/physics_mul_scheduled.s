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
_riding_scale_pages::
row = 0
.rept 256
 .db 0x40 + 2 * (row % 32)
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

.area _CODE_9
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
 jp merge_limit_read
merge_far:
 xor a
 ret

.area _CODE
merge_limit_read:
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

.area _CODE_9
; DE points to nx, ny, length, tx, ty. Only the six tabulated lengths
; publish a point. Other lengths use the original saturated projection.
_riding_contact_point_lookup::
 ld hl,#4
 add hl,de
 ld a,(hl+)
 sub #148
 cp #6
 jr nc,contact_point_miss
 ld b,a
 ld a,(hl)
 dec a
 jr nz,contact_point_miss
 ld a,b
 add a
 add a
 add #>_riding_contact_high
 ld b,a
 jp contact_point_read
contact_point_miss:
 xor a
 ret

.area _CODE
contact_point_read:
 ld a,#28
 ld (#0x2000),a
 call contact_point_components
 ld a,#9
 ld (#0x2000),a
 ld a,#1
 ret

.area _CODE_28
contact_point_components:
 call contact_point_round
 push hl
 call contact_point_round
 ld b,h
 ld c,l
 pop hl
 inc de
 inc de
 ld a,(#_riding_contact_qx)
 sub l
 ld (de),a
 inc de
 ld a,(#_riding_contact_qx+1)
 sbc h
 ld (de),a
 inc de
 ld a,(#_riding_contact_qy)
 sub c
 ld (de),a
 inc de
 ld a,(#_riding_contact_qy+1)
 sbc b
 ld (de),a
 ret
contact_point_round:
 ld a,(de)
 inc de
 rlca
 rlca
 rlca
 ld c,a                        ; low digit within the group, then group bits
 ld a,(de)
 inc de
 ld l,a
 ld h,b
 push de
 ld e,(hl)
 inc h
 ld d,(hl)
 inc h
 bit 5,l
 jr z,contact_point_group
 inc h
contact_point_group:
 ld a,l
 add a
 add a
 add a
 ld l,a
 ld a,c
 and #7
 or l
 ld l,a
 ld a,c
 and #0xf8
 ld c,a
 ld a,(hl)
 ld h,a
 and #7
 ld l,a
 ld a,h
 cp c                           ; last passing digit < queried digit
 ld a,l
 adc e
 ld l,a
 ld a,d
 adc #0
 ld h,a
 pop de
 ret
