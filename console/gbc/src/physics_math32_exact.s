; Exact signed32 x signed16 arithmetic, ROM0, stack ABI0 return HLDE.
; Products retain all 48 bits; dot and four-term torque sums retain 56.
; Rounding precedes the arithmetic shift; saturation is applied only once.
; Reentrant stack scratch; inherits _riding_mul16_regs bank/IRQ contract.
.module riding_math32_exact
.area _CODE
exact_mulq_general:
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
 ldhl sp,#13
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#9
 call exact_product
 call exact_add
 ldhl sp,#15
 ld b,(hl)
 ld c,#1
 call exact_finish
 add sp,#7
 ret
_riding_mulshift32::
 ldhl sp,#8
 ld a,(hl)
 cp a,#8
 jp z,math32_mulshift8
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
 ldhl sp,#13
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#9
 call exact_product
 call exact_add
 ldhl sp,#15
 ld b,(hl)
 ld c,#0
 call exact_finish
 add sp,#7
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
 ; Physical Q18 arms and velocities usually fit three magnitude bytes.
 ; Multiply by one or two rows of the existing unsigned byte table. Each
 ; row is selected once for all three input bytes, and ROMB0 is restored
 ; once for the complete product. Wider multiplicands use the full kernel.
 inc hl
 inc hl
 ld a,(hl+)
 ld e,a
 add a,a
 sbc a,a
 cp a,(hl)
 jp nz,exact_product_wide
 xor a,b
 push af
 dec hl
 dec hl
 ld d,(hl)
 dec hl
 ld a,(hl)
 ld h,e
 ld e,a
 bit 7,h
 jr z,exact_product_x_positive
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ld a,#0
 sbc a,h
 ld h,a
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
 ld a,b
 ld b,h
 or a
 jr z,exact_product_one_row
 push bc
 push de
 ld c,a
 call exact_product_byte_row
 push bc
 push de
 ldhl sp,#4
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 call exact_product_byte_row
 ; Add the high row shifted by one byte to the low row.
 ldhl sp,#0
 ld a,d
 add a,(hl)
 ld d,a
 inc hl
 ld a,c
 adc a,(hl)
 ld c,a
 inc hl
 ld a,b
 adc a,(hl)
 ld b,a
 inc hl
 ld a,(hl)
 adc a,#0
 ld h,b
 ld l,c
 ld c,a
 ld b,#0
 add sp,#8
 jr exact_product_byte_sign
exact_product_one_row:
 call exact_product_byte_row
 ld h,b
 ld l,c
 ld bc,#0
exact_product_byte_sign:
 pop af
 bit 7,a
 jr z,exact_product_byte_done
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
 ld a,#0
 sbc a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
exact_product_byte_done:
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret
exact_product_wide:
 dec hl
 dec hl
 dec hl
 jp exact_product_full

; B:DE is an unsigned 24-bit magnitude, C selects a row in banks 36..43.
; Return the exact unsigned product in BC:DE, little-endian.
_riding_product24x8_row::
exact_product_byte_row:
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
 ld l,e
 ld e,(hl)
 inc h
 ld a,(hl)
 ld l,d
 dec h
 add a,(hl)
 ld d,a
 inc h
 ld a,(hl)
 adc a,#0
 ld l,b
 dec h
 add a,(hl)
 ld c,a
 inc h
 ld a,(hl)
 adc a,#0
 ld b,a
 ret

exact_product_full:
 push bc
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
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
 ; A sign-extended low half already gave the complete product.
 ldhl sp,#7
 bit 7,(hl)
 jr nz,exact_product_negative_low
 inc hl
 ld a,(hl+)
 or a,(hl)
 jr z,exact_product_done
 jr exact_product_high
exact_product_negative_low:
 inc hl
 ld a,(hl+)
 and a,(hl)
 inc a
 jr z,exact_product_done
exact_product_high:
 ldhl sp,#8
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld a,d
 or a,e
 jr z,exact_product_correction
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
exact_product_correction:
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
; B shift 0..16, C rounded boolean. Accumulator at caller SP0.
exact_finish:
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
 add sp,#2
 ret
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
 ret
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
 jp exact_reduce48
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

exact_halves:
 .dw 1,2,4,8,16,32,64,128,256,512,1024,2048,4096,8192,16384,32768


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
 jr nz,math32_projection_wide
 inc hl
 cp a,(hl)
 dec hl
 jr nz,math32_projection_wide
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
math32_projection_lookup:
 push af
 ld a,b
 rrca
 rrca
 sub c
 add a,#<_riding_projection_directory
 ld l,a
 ld a,#>_riding_projection_directory
 adc a,#0
 ld h,a
 ld a,(hl)
 cp b
 jr nz,math32_lookup_miss
 inc h
 ld a,(hl)
 or a
 jr z,math32_lookup_miss
 ld (#0x2000),a
 ld a,#1
 ld (#0x3000),a
 inc h
 ld h,(hl)
 pop af
 jp _riding_projection_fetch
math32_lookup_miss:
 pop af
 jp c,math32_projection_full_fallback
 .endif
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
 jr math32_projection_restore

math32_projection_wide:
 .ifdef RIDING_PROJECTION_TABLES
 ; HL points to the high word. Keep it across the coefficient check.
 push hl
 scf
 jp math32_projection_lookup
math32_projection_full_fallback:
 pop hl
 .endif
 dec hl
 dec hl
 jp exact_product_nonzero

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
