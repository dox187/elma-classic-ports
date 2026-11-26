; Exact signed32 x signed16 arithmetic, ROM0, stack ABI0 return HLDE.
; Products retain all 48 bits; dot and four-term torque sums retain 56.
; Rounding precedes the arithmetic shift; saturation is applied only once.
; Reentrant stack scratch; inherits _riding_mul16_regs bank/IRQ contract.
.module riding_math32_exact
.area _CODE
exact_mulq_general:
 ld a,#1
 jr exact_single_shift
_riding_mulshift32::
 ldhl sp,#8
 ld a,(hl)
 cp #8
 jp z,math32_mulshift8
 cp #6
 jr z,exact_single_six
 cp #10
 jr z,exact_single_ten
 xor a
exact_single_shift:
 ; Seed the signed56 accumulator directly from the signed48 product.
 ; The shift and rounding flag stay on the stack across multiplication.
 push af
 ldhl sp,#8
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#4
 call exact_product
 ld a,b
 add a,a
 sbc a,a
 push af
 inc sp
 push bc
 push hl
 push de
 ldhl sp,#8
 ld c,(hl)
 ldhl sp,#17
 ld b,(hl)
 call exact_finish
 add sp,#9
 ret
exact_single_ten:
 ldhl sp,#6
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#2
 call exact_product
 ld a,#10
 jp exact_reduce48
exact_single_six:
 ldhl sp,#6
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#2
 call exact_product
 ; A signed32 result requires bits 47..37 to extend bit 37.
 ; CPI of the biased word also handles both inclusive boundaries.
 ld a,c
 add #32
 ld a,b
 adc #0
 jp nz,exact_reduce_saturate
 ld a,c
 add #32
 cp #64
 jp nc,exact_reduce_saturate
 ; Product bits 6..37 become bits 0..31. Bits 0..5 drop out.
 ld a,e
 .rept 2
 add a,a
 rl d
 rl l
 rl h
 rl c
 .endm
 ld e,d
 ld d,l
 ld l,h
 ld h,c
 ret
exact_dot_general:
; Seed the signed56 accumulator from the first full signed48 product.
; This is identical to adding it to zero, without the zero fill/add pass.
 ldhl sp,#10
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#2
 call exact_product
 ld a,b
 add a,a
 sbc a,a
 push af
 inc sp
 push bc
 push hl
 push de
 ldhl sp,#19
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#13
 call exact_product
 call exact_add
 ldhl sp,#21
 ld b,(hl)
 ld c,#1
 call exact_finish
 add sp,#7
 ret
; The scheduled cartridge uses its fused four-product damping moment.
 .ifndef RIDING_PROJECTION_TABLES
_riding_torque_input32::
 add sp,#-7
 ldhl sp,#0
 xor a
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl),a
 ldhl sp,#9
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld h,d
 ld l,e
 ld bc,#16
 add hl,bc
 ld c,(hl)
 inc hl
 ld b,(hl)
 ld h,d
 ld l,e
 ld de,#8
 add hl,de
 call exact_product
 call exact_add
 ldhl sp,#9
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld h,d
 ld l,e
 ld bc,#20
 add hl,bc
 ld c,(hl)
 inc hl
 ld b,(hl)
 ld h,d
 ld l,e
 ld de,#0
 add hl,de
 call exact_product
 call exact_sub
 ldhl sp,#9
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld h,d
 ld l,e
 ld bc,#18
 add hl,bc
 ld c,(hl)
 inc hl
 ld b,(hl)
 ld h,d
 ld l,e
 ld de,#12
 add hl,de
 call exact_product
 call exact_add
 ldhl sp,#9
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld h,d
 ld l,e
 ld bc,#22
 add hl,bc
 ld c,(hl)
 inc hl
 ld b,(hl)
 ld h,d
 ld l,e
 ld de,#4
 add hl,de
 call exact_product
 call exact_sub
 ld b,#10
 ld c,#0
 call exact_finish
 add sp,#7
 ret
 .endif
; C selects both byte planes. Each input digit addresses the same
; column in the adjacent low/high pages.
.macro exact_product_row
 .ifdef RIDING_PROJECTION_TABLES
 ld l,c
 ld h,#>_riding_scale_directory
 ld a,(hl)
 ld (#0x2000),a
 inc h
 ld h,(hl)
 .else
 ld a,c
 rlca
 rlca
 rlca
 and a,#7
 add a,#36
 ld (#0x2000),a
 ld a,c
 and a,#31
 add a,a
 or a,#>_physics_scale_planes_36
 ld h,a
 .endif
 ld l,e
 ld e,(hl)
 inc h
 ld a,(hl)
 ld l,d
 ld c,(hl)
 dec h
 add a,(hl)
 ld d,a
 ld l,b
 ld a,c
 adc a,(hl)
 ld c,a
 inc h
 ld a,(hl)
 adc a,#0
 ld b,a
.endm

; HL -> signed32 x, BC = signed16 y. Return BC:HL:DE signed48.
_riding_product32x16_regs::
exact_product:
 ld a,b
 or a,c
 jr nz,exact_product_nonzero
 ld bc,#0
 ld hl,#0
 ld de,#0
 ret
exact_product_nonzero:
 ; Keep the four source bytes in registers. Wider inputs enter the
 ; full kernel with their two signed16 halves already loaded.
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld h,(hl)
 ld l,a
exact_product_digits:
 add a,a
 sbc a,a
 cp a,h
 jp nz,exact_product_full
 xor a,b
 rla
 push af                     ; carry is the sign of the product
 bit 7,l
 jr z,exact_product_x_positive
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ld a,#0
 sbc a,l
 ld l,a
exact_product_x_positive:
 bit 7,b
 jr z,exact_product_y_positive
 xor a
 sub a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
exact_product_y_positive:
 ; Either operand can select a table row. A byte-sized x needs only
 ; one row even when both bytes of y are nonzero.
 ld a,l
 or a,d
 jr z,exact_product_byte_x
 ld a,b
 ld b,l
 or a
 jr z,exact_product_one_row
 cp #3
 jr nc,exact_product_high_table
 dec a
 jr z,exact_product_unit_high
exact_product_double_high:
 ; Double the overlapping byte pairs, retaining the magnitude bit of
 ; -0x800000. The input registers still hold x for the low row.
 ld h,b
 ld l,d
 add hl,hl
 ld l,h
 ld h,#0
 rl h
 push hl
 ld h,d
 ld l,e
 add hl,hl
 push hl
 jr exact_product_low_row
exact_product_high_table:
 .ifdef RIDING_PROJECTION_TABLES
 ; A magnitude below 131072 consists of two arbitrary bytes and a
 ; possible unit at bit 16. Only the two arbitrary digits need ROM rows.
 inc b
 dec b
 jp z,product_low_word
 dec b
 jp z,product_extra_word
 inc b
 .endif
 ; For other coefficients compute the entire upper row, then use the
 ; saved arm and low coefficient to look up the lower row.
 push bc
 push de
 ld c,a
 call exact_product_byte_row
 ; Exchange the high row with its original operands on the stack.
 ldhl sp,#0
 ld a,e
 ld e,(hl)
 ld (hl+),a
 ld a,d
 ld d,(hl)
 ld (hl+),a
 ld a,c
 ld c,(hl)
 ld (hl+),a
 ld a,b
 ld b,(hl)
 ld (hl),a
 jr exact_product_low_row
exact_product_unit_high:
 ld l,b
 ld h,#0
 push hl
 push de
exact_product_low_row:
 exact_product_row
 ; Add the high partial at byte one, propagating both word carries.
 pop hl
 ld a,d
 add a,l
 ld d,a
 ld a,c
 adc a,h
 ld c,a
 pop hl
 ld a,b
 adc a,l
 ld b,a
 ld a,h
 adc a,#0
 ld h,b
 ld l,c
 ld c,a
 ld b,#0
 jr exact_product_byte_sign
exact_product_byte_x:
 ld a,e
 ld e,c
 ld d,b
 ld c,a
 call _riding_mul16u8_unsigned
 jr exact_product_extend
exact_product_one_row:
 call exact_product_byte_row
 ld h,b
 ld l,c
exact_product_extend:
 ld bc,#0
exact_product_byte_sign:
 pop af
 jr nc,exact_product_byte_done
 xor a
 sub a,e
 ld e,a
 ld a,b
 sbc a,d
 ld d,a
 ld a,b
 sbc a,l
 ld l,a
 ld a,b
 sbc a,h
 ld h,a
 ld a,b
 sbc a,c
 ld c,a
 sbc a,a
 ld b,a
exact_product_byte_done:
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret
; B:DE is an unsigned 24-bit magnitude, C selects a row in banks 36..43.
; Return the exact unsigned product in BC:DE, little-endian.
_riding_product24x8_row::
exact_product_byte_row:
 exact_product_row
 ret

exact_product_full:
 push bc
 push hl
 push de
 call _riding_mul16_regs
 ld a,h
 add a,a
 sbc a,a
 ld b,a
 ld c,a
 push bc
 push hl
 push de
 ldhl sp,#8
 ld e,(hl)
 inc hl
 ld d,(hl)
 ldhl sp,#10
 ld c,(hl)
 inc hl
 ld b,(hl)
 call _riding_mul16_regs
 ld b,h
 ld c,l
 ldhl sp,#2
 ld a,(hl)
 add a,e
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld (hl+),a
 ld a,(hl)
 adc a,c
 ld (hl+),a
 ld a,(hl)
 adc a,b
 ld (hl),a
 ldhl sp,#7
 bit 7,(hl)
 jr z,exact_product_done
 ldhl sp,#10
 ld c,(hl)
 inc hl
 ld b,(hl)
 ld a,b
 add a,a
 sbc a,a
 ld d,a
 ldhl sp,#2
 ld a,(hl)
 add a,c
 ld (hl+),a
 ld a,(hl)
 adc a,b
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld (hl),a
exact_product_done:
 pop de
 pop hl
 pop bc
 add sp,#6
 ret
 .ifdef RIDING_PROJECTION_TABLES
product_extra_word:
 ld h,a
 ld l,c                         ; add the whole coefficient at bit 16
 jr product_word_rows
product_low_word:
 ld hl,#0
product_word_rows:
 push hl
 ld b,a
 push bc                        ; original low coefficient for the second row
 .macro product_word_row digit
 ld l,digit
 ld h,#>_riding_scale_directory
 ld a,(hl)
 ld (#0x2000),a
 inc h
 ld h,(hl)
 .endm
 product_word_row b
 ld l,e
 ld c,(hl)
 inc h
 ld a,(hl)
 ld l,d
 ld b,(hl)
 dec h
 add (hl)
 ld h,a
 ld l,c
 ld a,b
 adc #0
 ld b,a                         ; upper row is B:HL, input still in DE
 push hl
 ldhl sp,#2
 ld c,(hl)
 product_word_row c
 ld l,e
 ld e,(hl)
 inc h
 ld a,(hl)
 ld l,d
 ld c,(hl)
 dec h
 add (hl)
 ld d,a
 ld a,c
 adc #0
 ld c,a
 pop hl
 ld a,d
 add l
 ld d,a
 ld a,c
 adc h
 ld l,a
 ld a,b
 adc #0
 ld h,a                         ; unsigned16 times unsigned16 fits in HL:DE
 pop bc
 pop bc
 add hl,bc                      ; possible bit-16 contribution
 ld bc,#0
 rl c
 jp exact_product_byte_sign
 .endif
exact_add:
 push hl
 ldhl sp,#4
 ld a,(hl)
 add a,e
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld (hl+),a
 pop de
 ld a,(hl)
 adc a,e
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld (hl+),a
 ld a,(hl)
 adc a,c
 ld (hl+),a
 ld a,(hl)
 adc a,b
 ld (hl+),a
 bit 7,b
 ld b,#0
 jr z,exact_add_sign
 dec b
exact_add_sign:
 ld a,(hl)
 adc a,b
 ld (hl),a
 ret
 .ifndef RIDING_PROJECTION_TABLES
exact_sub:
 push hl
 ldhl sp,#4
 ld a,(hl)
 sub a,e
 ld (hl+),a
 ld a,(hl)
 sbc a,d
 ld (hl+),a
 pop de
 ld a,(hl)
 sbc a,e
 ld (hl+),a
 ld a,(hl)
 sbc a,d
 ld (hl+),a
 ld a,(hl)
 sbc a,c
 ld (hl+),a
 ld a,(hl)
 sbc a,b
 ld (hl+),a
 bit 7,b
 ld b,#0
 jr z,exact_sub_sign
 dec b
exact_sub_sign:
 ld a,(hl)
 sbc a,b
 ld (hl),a
 ret
 .endif
; B shift 0..16, C rounded boolean. Accumulator at caller SP0.
exact_finish:
 .ifdef RIDING_PROJECTION_TABLES
 ; The general shift operates entirely on stack values and this bank's
 ; rounding constants. Keep fixed ROM for the inner projection kernels.
 ld a,#28
 ld (#0x2000),a
 jp exact_finish_banked
.area _CODE_28
exact_finish_banked:
 .endif
 push bc
 ld a,c
 or a
 jr z,exact_finish_shift
 ld a,b
 dec a
 add a,a
 ld e,a
 ld d,#0
 ld hl,#exact_halves
 add hl,de
 ld e,(hl)
 inc hl
 ld d,(hl)
 ldhl sp,#4
 ld a,(hl)
 add a,e
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld (hl+),a
 ld a,(hl)
 adc a,#0
 ld (hl+),a
 ld a,(hl)
 adc a,#0
 ld (hl+),a
 ld a,(hl)
 adc a,#0
 ld (hl+),a
 ld a,(hl)
 adc a,#0
 ld (hl+),a
 ld a,(hl)
 adc a,#0
 ld (hl),a
exact_finish_shift:
 ldhl sp,#1
 ld a,(hl)
 cp a,#10
 jr z,exact_finish_physical
 cp a,#14
 jr z,exact_finish_physical
 ldhl sp,#1
 ld a,(hl)
 and a,#7
 ld b,a
 jr z,exact_finish_check
exact_finish_shift_loop:
 ldhl sp,#10
 sra (hl)
 dec hl
 rr (hl)
 dec hl
 rr (hl)
 dec hl
 rr (hl)
 dec hl
 rr (hl)
 dec hl
 rr (hl)
 dec hl
 rr (hl)

 dec b
 jr nz,exact_finish_shift_loop
exact_finish_check:
 ldhl sp,#1
 ld a,(hl)
 srl a
 srl a
 srl a
 ld c,a
 ld b,#0
 ldhl sp,#7
 add hl,bc
 ld a,(hl)
 add a,a
 sbc a,a
 ld d,a
 ld a,#3
 sub a,c
 ld b,a
exact_finish_check_loop:
 inc hl
 ld a,(hl)
 cp a,d
 jr nz,exact_finish_saturate
 dec b
 jr nz,exact_finish_check_loop
 ld b,#0
 ldhl sp,#4
 add hl,bc
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 jr exact_finish_return
exact_finish_saturate:
 ldhl sp,#10
 bit 7,(hl)
 ld hl,#0x7fff
 ld de,#0xffff
 jr z,exact_finish_return
 ld hl,#0x8000
 ld de,#0
exact_finish_return:
 add sp,#2
 .ifdef RIDING_PROJECTION_TABLES
 jp math32_projection_restore
 .else
 ret
 .endif
 ; Q10/Q14: validate the seventh accumulator byte before register reduction.
exact_finish_physical:
 ldhl sp,#9
 ld a,(hl+)
 add a,a
 sbc a,a
 cp a,(hl)
 jp nz,exact_finish_saturate
 ldhl sp,#1
 ld a,(hl)
 push af
 ldhl sp,#6
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 push bc
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 pop hl
 pop af
 add sp,#2
 .ifdef RIDING_PROJECTION_TABLES
 call exact_reduce48
 jp math32_projection_restore
.area _CODE
 .else
 jp exact_reduce48
 .endif
; A=10/14, BC:HL:DE signed48. Discarded product bits never affect rounding.
exact_reduce48:
 cp a,#14
 jr z,exact_reduce14
 ld a,b
 sra a
 jr z,exact_reduce10_ok
 inc a
 jr nz,exact_reduce_saturate
exact_reduce10_ok:
 sra b
 rr c
 rr h
 rr l
 rr d
 sra b
 rr c
 rr h
 rr l
 rr d
 ld e,d
 ld d,l
 ld l,h
 ld h,c
 ret
exact_reduce14:
 ld a,b
 add a,#32
 cp a,#64
 jr nc,exact_reduce_saturate
 ld a,d
 add a,a
 rl l
 rl h
 rl c
 rl b
 add a,a
 rl l
 rl h
 rl c
 rl b
 ld e,l
 ld d,h
 ld l,c
 ld h,b
 ret
exact_reduce_saturate:
 bit 7,b
 ld hl,#0x7fff
 ld de,#0xffff
 ret z
 ld hl,#0x8000
 ld de,#0
 ret
math32_round_product14:
 ld a,d
 add a,#32
 ld d,a
 jr nc,exact_reduce14
 inc hl
 ld a,h
 or a,l
 jr nz,exact_reduce14
 inc bc
 jr exact_reduce14

 .ifdef RIDING_PROJECTION_TABLES
.area _CODE_28
 .endif
exact_halves:
 .dw 1,2,4,8,16,32,64,128,256,512,1024,2048,4096,8192,16384,32768
.area _CODE


; Physical Q14 entries take pointers into caller-owned RAM. The same
; arithmetic serves the public stack ABI and the native riding callers.
_riding_mulq32::
 ldhl sp,#8
 ld a,(hl)
 cp a,#14
 jr nz,math32_mulq_other
 ldhl sp,#6
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#2
; HL -> x32, BC = signed Q14 coefficient. Result HLDE.
_riding_mulq14_regs::
 ld a,c
 or a
 jr nz,math32_mulq14_check_zero
 ld a,b
 and a,#127
 cp a,#64
 ld a,b
 jp z,math32_axis_return
 or a
 jr z,math32_axis_zero
math32_mulq14_check_zero:
 call math32_projection_product
 jr math32_round_product14
math32_axis_zero:
 ld hl,#0
 ld de,#0
 ret

math32_mulq_other:
 cp a,#10
 jp nz,exact_mulq_general
 ldhl sp,#6
 ld a,(hl+)
 or a
 jr nz,math32_mulq_check_x
 ld a,(hl)
 or a
 jr z,math32_axis_zero
 ldhl sp,#2
 cp a,#4
 jp z,math32_axis_return
 cp a,#252
 jp z,math32_axis_return
math32_mulq_check_x:
 ldhl sp,#3
 bit 7,(hl)
 jr nz,math32_mulq_negative
 inc hl
 ld a,(hl+)
 or a,(hl)
 jr nz,math32_mulq_physical_jump
 jr math32_mulq_product
math32_mulq_negative:
 inc hl
 ld a,(hl+)
 and a,(hl)
 inc a
 jr nz,math32_mulq_physical_jump
math32_mulq_product:
 ldhl sp,#6
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#2
 ld e,(hl)
 inc hl
 ld d,(hl)
 call _riding_mul16_regs
 jp math32_round10
math32_mulq_physical_jump:
 ldhl sp,#6
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#2
 call exact_product
 ld a,d
 add a,#2
 ld d,a
 jr nc,math32_mulq_reduce10
 inc hl
 ld a,h
 or a,l
 jr nz,math32_mulq_reduce10
 inc bc
math32_mulq_reduce10:
 ld a,#10
 jp exact_reduce48

_riding_dotq32::
 ldhl sp,#14
 ld a,(hl)
 cp a,#14
 jp nz,math32_dot_other
 ldhl sp,#2
 ld d,h
 ld e,l
 ldhl sp,#10
; DE -> consecutive signed32 components, HL -> two signed16 coefficients.
_riding_dotq14_regs::
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 or a,c
 jr nz,math32_dot14_first
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ld hl,#4
 add hl,de
 jp _riding_mulq14_regs
math32_dot14_first:
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 or a,h
 jr nz,math32_dot14_pair
 ld h,d
 ld l,e
 jp _riding_mulq14_regs
math32_dot14_pair:
 .ifdef RIDING_PROJECTION_TABLES
 ; (-1, k/16384) projects to round(y*k/16384) - x exactly.
 ld a,b
 and #127
 cp #64
 jr nz,math32_dot_check_second
 ld a,c
 or a
 jr nz,math32_dot_check_second
 bit 7,b
 jr z,math32_dot_first_positive
 ld a,h
 inc a
 jr nz,math32_dot_first_unit
 ld a,l
 cp #195
 jp z,math32_dot_shallow
 cp #247
 jp z,math32_dot_shallow
math32_dot_first_unit:
 ; The other coefficient strictly inside (-1,1) ensures its rounded
 ; product fits signed32 before the exact unit coordinate is subtracted.
 ld a,h
 add #63
 cp #127
 jr nc,math32_dot14_general
 ld b,h
 ld c,l
 push de
 ld hl,#4
 add hl,de
 jr math32_dot_unit_term
math32_dot_first_positive:
 ; An integral first component commutes with the Q14 rounding bias.
 ; Preserve the full two-product path if the other term can saturate alone.
 ld a,h
 add #63
 cp #127
 jr nc,math32_dot14_general
 ld b,h
 ld c,l
 push de
 ld hl,#4
 add hl,de
 jr math32_dot_add_unit
math32_dot_check_second:
 ld a,h
 and #127
 cp #64
 jr nz,math32_dot14_general
 ld a,l
 or a
 jr nz,math32_dot14_general
 ld a,b
 add #63
 cp #127
 jr nc,math32_dot14_general
 bit 7,h
 jr z,math32_dot_add_second
 ld hl,#4
 add hl,de
 push hl
 ld h,d
 ld l,e
math32_dot_unit_term:
 call _riding_mulq14_regs
 ld b,h
 ld c,l
 pop hl
 ld a,e
 sub (hl)
 ld e,a
 inc hl
 ld a,d
 sbc (hl)
 ld d,a
 inc hl
 ld a,c
 sbc (hl)
 ld c,a
 inc hl
 jp math32_dot_sub_high
math32_dot_add_second:
 ; Round the non-unit term once, then add the unscaled coordinate.
 ; The strict coefficient bound above keeps that term within signed32.
 ld hl,#4
 add hl,de
 push hl
 ld h,d
 ld l,e
math32_dot_add_unit:
 call _riding_mulq14_regs
 ld b,h
 ld c,l
 pop hl
 ld a,e
 add (hl)
 ld e,a
 inc hl
 ld a,d
 adc (hl)
 ld d,a
 inc hl
 ld a,c
 adc (hl)
 ld c,a
 inc hl
 ld a,b
 adc (hl)
 ld h,(hl)
 ld l,a
 xor b
 bit 7,a
 jr z,math32_dot_add_done
 ; Equal input signs with a changed result sign imply saturation.
 ld a,h
 xor b
 bit 7,a
 jp z,exact_reduce_saturate
math32_dot_add_done:
 ld h,l
 ld l,c
 ret
math32_dot14_general:
 .endif
 push hl
 ld hl,#4
 add hl,de
 push hl
 ld h,d
 ld l,e
 call math32_projection_product
 push bc
 push hl
 push de
 ldhl sp,#8
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call math32_projection_product
 ; Add both complete products. Byte 0 contributes its carry to byte 1.
 push hl
 ldhl sp,#2
 ld a,(hl+)
 add a,e
 ld a,(hl)
 adc a,d
 ld (hl+),a
 pop de
 ld a,(hl+)
 adc a,e
 ld e,a
 ld a,(hl+)
 adc a,d
 ld d,a
 ld a,(hl+)
 adc a,c
 ld c,a
 ld a,(hl)
 adc a,b
 ld b,a
 ldhl sp,#1
 ld a,(hl)
 ld h,d
 ld l,e
 ld d,a
 add sp,#10
 ; Sum range is [-2^47 + 65536, 2^47]. Only the upper endpoint
 ; can have bits 47..16 equal to 0x80000000. It saturates positive.
 ld a,b
 cp a,#128
 jp nz,math32_round_product14
 ld a,c
 or a,h
 or a,l
 jp nz,math32_round_product14
 ld hl,#0x7fff
 ld de,#0xffff
 ret

 .ifdef RIDING_PROJECTION_TABLES
math32_dot_shallow:
 ld c,l                      ; low byte of -61 or -9
 push de                     ; first vector component
 ld hl,#4
 add hl,de
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 add a,a
 sbc a,a
 cp (hl)
 jr nz,math32_dot_shallow_wide
 inc hl
 cp (hl)
 jr nz,math32_dot_shallow_wide
 ld hl,#_riding_shallow_dot_61
 ld a,c
 cp #195
 jr z,math32_dot_shallow_row
 ld hl,#_riding_shallow_dot_9
math32_dot_shallow_row:
 ld c,d
 ld b,#0
 add hl,bc
 ld a,#4
 ld (#0x2000),a
 ld d,(hl)
 inc h                       ; low-byte threshold is 256 bytes after quotient
 ld a,(hl)
 cp e
 ld a,d
 sbc a,#0
 ld e,a
 add a,a
 sbc a,a
 ld b,a                      ; sign of the rounded, signed-byte product
 ld a,(#__current_bank)
 ld (#0x2000),a
 pop hl
 ld a,e
 sub (hl)
 ld e,a
 inc hl
 ld a,b
 sbc (hl)
 ld d,a
 inc hl
 ld a,b
 sbc (hl)
 ld c,a
 inc hl
math32_dot_sub_high:
 ld a,b
 sbc (hl)
 ld h,(hl)                   ; sign of x
 ld l,a
 xor b
 bit 7,a
 jr z,math32_dot_shallow_done
 ld a,h
 xor b                       ; only opposite operand signs can overflow
 bit 7,a
 jp nz,exact_reduce_saturate
math32_dot_shallow_done:
 ld h,l
 ld l,c
 ret
math32_dot_shallow_wide:
 pop de
 ld l,c
 ld h,#255
 ld bc,#0xc000
 jp math32_dot_first_unit
 .endif

; Signed16 components need at most two 16-by-8 table rows. Keep the
; full signed48 product contract for mixed-width vectors and cancellation.
_riding_projection_product_regs::
math32_projection_product:
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld a,d
 add a,a
 sbc a,a
 cp a,(hl)
 jp nz,math32_projection_wide
 inc hl
 cp a,(hl)
 dec hl
 jp nz,math32_projection_wide
 .ifdef RIDING_PROJECTION_TABLES
 ; Geometry callers can enter here after verifying the signed16 width.
_riding_projection_signed16::
 .endif
 ld a,d
 or a
 jp z,math32_projection_byte
 inc a                           ; OR cleared carry for the narrow table ABI
 jp z,math32_projection_negbyte
math32_projection_narrow_other:
 .ifdef RIDING_PROJECTION_TABLES
 ; Coefficients with byte magnitude need at most one product row. Common
 ; unit normals have an exact signed shift, including -32768 * -16384.
 ld a,c
 or a
 jr nz,math32_short_coefficient
 ld a,b
 and #127
 cp #64
 jr z,math32_unit_coefficient
math32_short_coefficient:
 ld a,b
 or a
 jr z,math32_positive_coefficient
 inc a
 jr nz,math32_projection_lookup
 ld a,c
 or a
 jr z,math32_projection_lookup  ; -256 uses the general signed-word reader
 ld l,c
 ld b,d
 ld c,e
 ld e,l
 jp math32_projection_negbyte
math32_positive_coefficient:
 ld a,c
 or a
 jp z,math32_projection_zero
 bit 7,d
 jp z,math32_projection_positive
 jp math32_projection_negative

math32_unit_coefficient:
 bit 7,b
 jr z,math32_unit_positive
 ; Carry is the seventeenth bit of -x. This entry has nonzero x.
 ld a,d
 push af
 xor a
 sub e
 ld l,a
 sbc a,a
 sub d
 ld h,a
 pop af
 cpl
 rlca
 jr math32_unit_shift
math32_unit_positive:
 ld h,d
 ld l,e
 ld a,d
 rlca
math32_unit_shift:
 ld d,#0
 rr h
 rr l
 rr d
 sra h
 rr l
 rr d
 ld e,#0
 ld a,h
 add a,a
 sbc a,a
 ld b,a
 ld c,a
 jp math32_projection_restore
math32_projection_lookup:
_riding_projection_read_directory::
 push af                        ; width flag
 call _riding_map_projection_row
 jr nz,math32_lookup_miss
 pop af
 jp _riding_projection_fetch

; BC is the signed coefficient, DE is preserved. Z returns the encoded
; row page in H with its bank mapped. A miss leaves BC and the mapping intact.
_riding_map_projection_row::
 ld h,#>_riding_projection_hash
 ld l,b
 bit 7,b
 jr nz,math32_lookup_negative
 ld a,(hl)
 add c
 ld l,a
 inc h
 ld a,(hl)
 cp b
 ret nz
 ld b,#0
 jr math32_lookup_map
math32_lookup_negative:
 ; With a nonzero low byte, -y has high byte ~B. Its two table
 ; displacements are complementary, so ~(C + displacement) gives
 ; the positive magnitude's slot without changing BC.
 ld a,c
 or a
 jr z,math32_lookup_negative_word
 add (hl)
 cpl
 ld l,a
 inc h
 ld a,(hl)
 cpl
 cp b
 ret nz
 ld b,#128
 jr math32_lookup_map
math32_lookup_negative_word:
 ; At an exact multiple of 256 the magnitude's high byte is -B.
 xor a
 sub b
 ld l,a
 ld a,(hl)
 ld l,a
 inc h
 ld a,(hl)
 add b
 ret nz
 ld b,#128
math32_lookup_map:
 inc h
 ld a,(hl)
 ld (#0x2000),a
 bit 7,a
 jr z,math32_lookup_page
 ld a,#1
 ld (#0x3000),a
math32_lookup_page:
 inc h
 ld a,(hl)
 xor b
 ld h,a
 xor a
 ret

math32_lookup_miss:
 pop af
 jp c,math32_projection_full_fallback
 .endif
 .ifdef RIDING_PROJECTION_TABLES
 ; Multiply both bytes of X by the unchanged Y register pair. The
 ; high-byte row starts one byte later. Keep its carries in HRAM while
 ; selecting the low-byte row. No interrupt handler uses this workspace.
 push de
 ld a,d
 dec a
 jr nz,projection_cross_high
 ld d,c                         ; 1 * unsigned Y
 ld a,b
 ldh (#projection_cross_middle),a
 xor a
 jr projection_cross_high_ready
projection_cross_high:
 product_word_row d
 ld l,c
 ld d,(hl)                      ; byte 1 of the high partial product
 inc h
 ld a,(hl)
 ld l,b
 dec h
 add (hl)
 ldh (#projection_cross_middle),a
 inc h
 ld a,(hl)
 adc #0
projection_cross_high_ready:
 ldh (#projection_cross_upper),a
 product_word_row e
 ld l,c
 ld e,(hl)                      ; output byte 0
 inc h
 ld a,(hl)
 ld l,b
 dec h
 add (hl)
 ldh (#projection_cross_low),a
 inc h
 ld a,(hl)
 adc #0
 ld h,a
 ldh a,(#projection_cross_low)
 add d
 ld d,a                         ; output byte 1
 ldh a,(#projection_cross_middle)
 adc h
 ld l,a
 ldh a,(#projection_cross_upper)
 adc #0
 ld h,a
 ; Convert the unsigned high word to the signed product's high word.
 push hl
 ldhl sp,#3
 bit 7,(hl)
 pop hl
 jr z,projection_cross_y
 ld a,l
 sub c
 ld l,a
 ld a,h
 sbc b
 ld h,a
projection_cross_y:
 bit 7,b
 pop bc
 jr z,projection_cross_done
 ld a,l
 sub c
 ld l,a
 ld a,h
 sbc b
 ld h,a
projection_cross_done:
 ld a,h
 add a
 sbc a
 ld b,a
 ld c,a
 jp math32_projection_restore
.area _HRAM
projection_cross_low: .ds 1
projection_cross_middle: .ds 1
projection_cross_upper: .ds 1
.area _CODE
 .else
 ; Compute the unsigned product. If x or y is negative, subtract the
 ; opposite operand from its upper word to recover signed x*y modulo 2^32.
 push bc
 push de
 ld a,e
 ld e,c
 ld d,b
 ld c,a
 call _riding_mul16u8_unsigned
 push hl
 push de
 ldhl sp,#6
 ld e,(hl)
 inc hl
 ld d,(hl)
 ldhl sp,#5
 ld c,(hl)
 call _riding_mul16u8_unsigned
 ld b,l
 ld c,d
 pop hl
 ld a,h
 add a,e
 ld d,a
 ld e,l
 pop hl
 ld a,l
 adc a,c
 ld c,a
 ld a,b
 adc a,#0
 ld b,a
 ldhl sp,#3
 bit 7,(hl)
 pop hl
 jr z,math32_projection_high_y
 ld a,c
 sub a,l
 ld c,a
 ld a,b
 sbc a,h
 ld b,a
math32_projection_high_y:
 bit 7,h
 pop hl
 jr z,math32_projection_sign
 ld a,c
 sub a,l
 ld c,a
 ld a,b
 sbc a,h
 ld b,a
math32_projection_sign:
 ld h,b
 ld l,c
 ld a,b
 add a,a
 sbc a,a
 ld b,a
 ld c,a
 jp math32_projection_restore
 .endif

math32_projection_wide:
 .ifdef RIDING_PROJECTION_TABLES
 ; For a unit normal the complete signed48 product is x shifted left
 ; fourteen places. Keep bit 32 of -INT32_MIN for the first right shift.
 ld a,c
 or a
 jr nz,math32_wide_lookup
 ld a,b
 and #127
 cp #64
 jr nz,math32_wide_lookup
 ld a,b
 ld c,(hl)
 inc hl
 ld b,(hl)
 ld h,d
 ld l,e
 bit 7,a
 jr z,math32_wide_unit_positive
 ld a,b
 push af
 xor a
 sub l
 ld l,a
 ld a,#0
 sbc h
 ld h,a
 ld a,#0
 sbc c
 ld c,a
 ld a,#0
 sbc b
 ld b,a
 pop af
 cpl
 jr math32_wide_unit_shift
math32_wide_unit_positive:
 ld a,b
math32_wide_unit_shift:
 rlca
 ld d,#0
 rr b
 rr c
 rr h
 rr l
 rr d
 sra b
 rr c
 rr h
 rr l
 rr d
 ld e,#0
 jp math32_projection_restore
math32_wide_lookup:
 ; HL points to the high word. Keep it across the coefficient check.
 push hl
 scf
 jp math32_projection_lookup
math32_projection_full_fallback:
 ; A fixed-ROM hash miss leaves the caller bank mapped.
 pop hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 jp exact_product_digits
 .else
 dec hl
 dec hl
 jp exact_product_nonzero
 .endif

; A signed x in [-255,-1] needs one unsigned byte multiply. Negate
; the coefficient first. Its original sign also handles -(-32768).
math32_projection_negbyte:
 ld a,e
 or a
 jp z,math32_projection_narrow_other   ; -256 uses the normal signed16 path
 cpl
 inc a
 push af
 xor a
 sub c
 ld e,a
 sbc a,a
 sub b
 ld d,a
 pop af
 ld c,a
 bit 7,b
 jr nz,math32_projection_positive
 ld a,d
 or e
 jr z,math32_projection_zero
 jr math32_projection_negative

math32_projection_byte:
 ld a,e
 or a
 jr z,math32_projection_zero
 ld e,c
 ld d,b
 ld c,a
 bit 7,d
 jr nz,math32_projection_negative
math32_projection_positive:
 call _riding_mul16u8_unsigned
 ld bc,#0
 jr math32_projection_restore
math32_projection_negative:
 push bc
 call _riding_mul16u8_unsigned
 pop bc
 ld a,l
 sub a,c
 ld l,a
 ld h,#255
 ld bc,#0xffff
 .ifdef RIDING_PROJECTION_TABLES
_riding_projection_hit::
 xor a
 ld (#0x3000),a
 .endif
math32_projection_restore:
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret
 .ifdef RIDING_PROJECTION_TABLES
_riding_projection_negate48::
 xor a
 sub e
 ld e,a
 ld a,#0
 sbc d
 ld d,a
 ld a,#0
 sbc l
 ld l,a
 ld a,#0
 sbc h
 ld h,a
 ld a,#0
 sbc c
 ld c,a
 ld a,#0
 sbc b
 ld b,a
 ret
 .endif
math32_projection_zero:
 ld bc,#0
 jp math32_axis_zero

math32_dot_other:
 cp a,#10
 jp nz,exact_dot_general
 ld d,#4
 ldhl sp,#10
 ld a,(hl+)
 or a
 jr nz,math32_dot_check_a
 ld c,(hl)
 inc hl
 ld a,(hl+)
 or a
 jr nz,math32_dot_check_a
 ld b,(hl)
 ld a,c
 or a
 jr nz,math32_dot_axis_a
 ld a,b
 cp a,d
 jr z,math32_dot_axis_b_return
 add a,d
 jr nz,math32_dot_check_a
 ld a,#128
math32_dot_axis_b_return:
 ldhl sp,#6
 jp math32_axis_return
math32_dot_axis_a:
 ld a,b
 or a
 jr nz,math32_dot_check_a
 ld a,c
 cp a,d
 jr z,math32_dot_axis_a_return
 add a,d
 jr nz,math32_dot_check_a
 ld a,#128
math32_dot_axis_a_return:
 ldhl sp,#2
 jp math32_axis_return
math32_dot_check_a:
 ldhl sp,#3
 bit 7,(hl)
 jr nz,math32_dot_a_negative
 inc hl
 ld a,(hl+)
 or a,(hl)
 jp nz,exact_dot_general
 jr math32_dot_a_ok
math32_dot_a_negative:
 inc hl
 ld a,(hl+)
 and a,(hl)
 inc a
 jp nz,exact_dot_general
math32_dot_a_ok:
 ldhl sp,#7
 bit 7,(hl)
 jr nz,math32_dot_b_negative
 inc hl
 ld a,(hl+)
 or a,(hl)
 jp nz,exact_dot_general
 jr math32_dot_b_ok
math32_dot_b_negative:
 inc hl
 ld a,(hl+)
 and a,(hl)
 inc a
 jp nz,exact_dot_general
math32_dot_b_ok:
 ldhl sp,#10
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#2
 ld e,(hl)
 inc hl
 ld d,(hl)
 call _riding_mul16_regs
 push hl
 push de
 ldhl sp,#16
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#10
 ld e,(hl)
 inc hl
 ld d,(hl)
 call _riding_mul16_regs
 ld b,h
 ld c,l
 ldhl sp,#0
 ld a,e
 add a,(hl)
 ld e,a
 inc hl
 ld a,d
 adc a,(hl)
 ld d,a
 inc hl
 ld a,c
 adc a,(hl)
 ld c,a
 inc hl
 ld a,b
 adc a,(hl)
 ld b,a
 ld h,b
 ld l,c
 add sp,#4
 ld a,h
 cp a,#0x80
 jr nz,math32_round10
 ld a,l
 or a
 jr nz,math32_round10
 ; Four INT16_MIN operands produce +2^31, the sole narrow sum overflow.
 ld de,#0
 ld hl,#32
 ret

math32_round10:
 ld a,d
 add a,#2
 ld e,a
 jr nc,math32_shift10
 inc hl
math32_shift10:
 ld d,l
 ld a,h
 sra a
 rr d
 rr e
 sra a
 rr d
 rr e
 ld l,a
 add a,a
 sbc a,a
 ld h,a
 ret

; The unrounded Q8 case is an exact byte extraction after signed48 multiply.
math32_mulshift8:
 ldhl sp,#6
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#2
 call exact_product
 ld a,c
 add a,a
 sbc a,a
 cp a,b
 jp nz,exact_reduce_saturate
 ld e,d
 ld d,l
 ld l,h
 ld h,c
 ret

; Exact +/- unit coefficient: load signed32, negate with INT32_MIN saturation.
; HL points to x; bit7 of A selects negation.
math32_axis_return:
 rlca
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld h,(hl)
 ld l,c
 ret nc
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ld a,#0
 sbc a,l
 ld l,a
 ld a,#0
 sbc a,h
 ld h,a
 cp a,#128
 ret nz
 ld a,l
 or a,d
 or a,e
 ret nz
 ld hl,#0x7fff
 ld de,#0xffff
 ret
