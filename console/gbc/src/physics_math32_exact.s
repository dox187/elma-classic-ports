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
 ldhl sp,#17
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#9
 call exact_product
 call exact_add
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
 sra a
 sra a
 sra a
 sra a
 sra a
 jr z,exact_reduce14_ok
 inc a
 jr nz,exact_reduce_saturate
exact_reduce14_ok:
 sla d
 rl l
 rl h
 rl c
 rl b
 sla d
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
; Signed32 operands outside signed16 take the complete signed48 product,
; round in registers, and share the exact saturated physical reductions.
math32_mulq_physical:
 ldhl sp,#6
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#2
 call exact_product
 push hl
 ldhl sp,#10
 ld a,(hl)
 pop hl
 cp a,#14
 jr z,math32_mulq_physical14
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
math32_mulq_physical14:
 ld a,d
 add a,#32
 ld d,a
 jr nc,math32_mulq_reduce14
 inc hl
 ld a,h
 or a,l
 jr nz,math32_mulq_reduce14
 inc bc
math32_mulq_reduce14:
 ld a,#14
 jp exact_reduce48

exact_halves:
 .dw 1,2,4,8,16,32,64,128,256,512,1024,2048,4096,8192,16384,32768


; Q10/Q14 narrow reductions retain full signed32 outputs.
_riding_mulq32::
 ldhl sp,#8
 ld a,(hl)
 cp a,#10
 jr z,math32_mulq_axis10
 cp a,#14
 jr nz,math32_mulq_wide
 ld d,#64
 jr math32_mulq_axis
math32_mulq_axis10:
 ld d,#4
math32_mulq_axis:
 ldhl sp,#6
 ld a,(hl+)
 or a
 jr nz,math32_mulq_check_x
 ld a,(hl)
 or a
 jr z,math32_axis_zero
 cp a,d
 jr z,math32_mulq_axis_return
 add a,d
 jr nz,math32_mulq_check_x
 ld a,#128
math32_mulq_axis_return:
 ldhl sp,#2
 jp math32_axis_return
math32_axis_zero:
 ld hl,#0
 ld de,#0
 ret
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
 push hl
 ldhl sp,#10
 ld a,(hl)
 pop hl
 cp a,#10
 jp z,math32_round10
 jp math32_round14
math32_mulq_physical_jump:
 jp math32_mulq_physical
math32_mulq_wide:
 jp exact_mulq_general
_riding_dotq32::
 ldhl sp,#14
 ld a,(hl)
 cp a,#10
 jr z,math32_dot_axis10
 cp a,#14
 jp nz,exact_dot_general
 ld d,#64
 jr math32_dot_axis
math32_dot_axis10:
 ld d,#4
math32_dot_axis:
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
 push hl
 ldhl sp,#16
 ld a,(hl)
 pop hl
 ld b,a
 ld a,h
 cp a,#0x80
 jr nz,math32_dot_regular_sum
 ld a,l
 or a
 jr nz,math32_dot_regular_sum
 ld de,#0
 ld hl,#2
 ld a,b
 cp a,#14
 ret z
 ld hl,#32
 ret
math32_dot_regular_sum:
 ld a,b
 cp a,#10
 jp z,math32_round10
 jp math32_round14

math32_round10:
 ld a,d
 add a,#2
 ld d,a
 jr nc,math32_shift10
 inc hl
math32_shift10:
 ld b,h
 sla d
 rl l
 rl h
 sla d
 rl l
 rl h
 sla d
 rl l
 rl h
 sla d
 rl l
 rl h
 sla d
 rl l
 rl h
 sla d
 rl l
 rl h
 ld e,l
 ld d,h
 ld a,b
 sra a
 sra a
 ld l,a
 add a,a
 sbc a,a
 ld h,a
 ret
math32_round14:
 ld a,d
 add a,#32
 ld d,a
 jr nc,math32_shift14
 inc hl
math32_shift14:
 ld b,h
 sla d
 rl l
 rl h
 sla d
 rl l
 rl h
 ld e,l
 ld d,h
 ld a,b
 sra a
 sra a
 sra a
 sra a
 sra a
 sra a
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
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld h,(hl)
 ld l,c
 bit 7,a
 ret z
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
