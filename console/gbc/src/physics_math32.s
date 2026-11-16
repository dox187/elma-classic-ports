; ROM0 bounds for exact signed56 -> shifted/saturated32 conversion.
; Entry s is INT32_MAX >> (16-s), s=0..16; complement gives the
; corresponding negative middle-word bound. No operand bits are discarded
; before the signed range check in physics_math32.c.
    .module riding_math32_bounds
    .area _CODE
_riding_math32_positive_limit::
    .dw 0x7fff,0x0000
    .dw 0xffff,0x0000
    .dw 0xffff,0x0001
    .dw 0xffff,0x0003
    .dw 0xffff,0x0007
    .dw 0xffff,0x000f
    .dw 0xffff,0x001f
    .dw 0xffff,0x003f
    .dw 0xffff,0x007f
    .dw 0xffff,0x00ff
    .dw 0xffff,0x01ff
    .dw 0xffff,0x03ff
    .dw 0xffff,0x07ff
    .dw 0xffff,0x0fff
    .dw 0xffff,0x1fff
    .dw 0xffff,0x3fff
    .dw 0xffff,0x7fff

; Exact narrow torque path: all four rel velocities already sign-extend16.
; Accumulate four COMPLETE signed32 products in signed40 stack storage.
; No intermediate32 overflow and no shared scratch or disabled interrupts.
_riding_torque_narrow32::
 ldhl sp,#2
 ld c,(hl)
 inc hl
 ld b,(hl)
 add sp,#-7
 ldhl sp,#5
 ld (hl),c
 inc hl
 ld (hl),b
 ldhl sp,#0
 xor a
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl),a
 ldhl sp,#5
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld h,d
 ld l,e
 ld bc,#8
 add hl,bc
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld a,l
 add a,#7
 ld l,a
 jr nc,math32_torque_coefficient0
 inc h
math32_torque_coefficient0:
 ld c,(hl)
 inc hl
 ld b,(hl)
 call _riding_mul16_regs
 call math32_add_product
 ldhl sp,#5
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld h,d
 ld l,e
 ld bc,#0
 add hl,bc
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld a,l
 add a,#19
 ld l,a
 jr nc,math32_torque_coefficient1
 inc h
math32_torque_coefficient1:
 ld c,(hl)
 inc hl
 ld b,(hl)
 call _riding_mul16_regs
 call math32_subtract_product
 ldhl sp,#5
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld h,d
 ld l,e
 ld bc,#12
 add hl,bc
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld a,l
 add a,#5
 ld l,a
 jr nc,math32_torque_coefficient2
 inc h
math32_torque_coefficient2:
 ld c,(hl)
 inc hl
 ld b,(hl)
 call _riding_mul16_regs
 call math32_add_product
 ldhl sp,#5
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld h,d
 ld l,e
 ld bc,#4
 add hl,bc
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld a,l
 add a,#17
 ld l,a
 jr nc,math32_torque_coefficient3
 inc h
math32_torque_coefficient3:
 ld c,(hl)
 inc hl
 ld b,(hl)
 call _riding_mul16_regs
 call math32_subtract_product
 ldhl sp,#4
 ld a,(hl)
 or a
 jr z,math32_torque_positive
 bit 7,a
 jr z,math32_torque_positive_overflow
 inc a
 jr nz,math32_torque_negative_overflow
 dec hl
 ld a,(hl)
 cp a,#0xfe
 jr c,math32_torque_negative_overflow
 jr math32_torque_shift
math32_torque_positive:
 dec hl
 ld a,(hl)
 cp a,#2
 jr nc,math32_torque_positive_overflow
math32_torque_shift:
 ldhl sp,#1
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld a,(hl)
 sra a
 rr d
 rr e
 sra a
 rr d
 rr e
 add sp,#7
 ret
math32_torque_positive_overflow:
 ld de,#0x7fff
 add sp,#7
 ret
math32_torque_negative_overflow:
 ld de,#0x8000
 add sp,#7
 ret
math32_add_product:
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
 ld (hl+),a
 bit 7,b
 ld a,#0
 jr z,math32_add_sign
 ld a,#0xff
math32_add_sign:
 adc a,(hl)
 ld (hl),a
 ret
math32_subtract_product:
 ld b,h
 ld c,l
 ldhl sp,#2
 ld a,(hl)
 sub a,e
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
 jr z,math32_subtract_sign
 ld b,#0xff
math32_subtract_sign:
 ld a,(hl)
 sbc a,b
 ld (hl),a
 ret


; Public coefficient dispatch: only mathematically proven signed16 RESULTS
; use old kmul. The linear API always returns a full sign-extended HLDE.
_riding_kmul32::
 ldhl sp,#3
 bit 7,(hl)
 jr nz,math32_kmul_negative
 inc hl
 ld a,(hl+)
 or a,(hl)
 jr nz,math32_kmul_wide
 jr math32_kmul_check_shift
math32_kmul_negative:
 inc hl
 ld a,(hl+)
 and a,(hl)
 inc a
 jr nz,math32_kmul_wide
math32_kmul_check_shift:
 ldhl sp,#7
 ld a,(hl)
 cp a,#8
 jr nc,math32_kmul_narrow
 ld c,a
 ld b,#0
 ld hl,#math32_kmul_bound_bytes
 add hl,bc
 ld b,(hl)
math32_kmul_bound_ready:
 ldhl sp,#2
 ld e,(hl)
 inc hl
 ld d,(hl)
 bit 7,d
 jr z,math32_kmul_magnitude
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
math32_kmul_magnitude:
 ld a,d
 cp a,b
 jr c,math32_kmul_narrow
 jr nz,math32_kmul_wide
 ld a,e
 or a
 jr nz,math32_kmul_wide
math32_kmul_narrow:
 ldhl sp,#6
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#2
 ld e,(hl)
 inc hl
 ld d,(hl)
 push bc
 push de
 call _kmul
 add sp,#4
 ld a,d
 add a,a
 sbc a,a
 ld h,a
 ld l,a
 ret
math32_kmul_wide:
 jp _riding_kmul32_wide
math32_kmul_bound_bytes:
 .db 0,1,2,4,8,16,32,64

; The x16*y16 product plus either rounding constant fits signed32. Preserve
; its whole17..21-bit shifted result; these are NOT the old clamped16 APIs.
_riding_mulq32::
 ldhl sp,#8
 ld a,(hl)
 cp a,#10
 jr z,math32_mulq_check_x
 cp a,#14
 jr nz,math32_mulq_wide
math32_mulq_check_x:
 ldhl sp,#3
 bit 7,(hl)
 jr nz,math32_mulq_negative
 inc hl
 ld a,(hl+)
 or a,(hl)
 jr nz,math32_mulq_wide
 jr math32_mulq_product
math32_mulq_negative:
 inc hl
 ld a,(hl+)
 and a,(hl)
 inc a
 jr nz,math32_mulq_wide
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
math32_mulq_wide:
 jp _riding_mulq32_wide

; Narrow a,b admit every signed16 coefficient. The complete product sum is
; [-2147418112,2147483648]. Its sole signed32 overflow is the four-INT16_MIN
; corner; every other positive sum is <=2^31-32768, so round10/14 also fits.
; Topword8000 is therefore an exact, unambiguous marker for positive2^31.
; Wide a/b and other shifts keep the original49-bit fallback.
_riding_dotq32::
 ldhl sp,#14
 ld a,(hl)
 cp a,#10
 jr z,math32_dot_check_a
 cp a,#14
 jp nz,_riding_dotq32_wide
math32_dot_check_a:
 ldhl sp,#3
 bit 7,(hl)
 jr nz,math32_dot_a_negative
 inc hl
 ld a,(hl+)
 or a,(hl)
 jp nz,_riding_dotq32_wide
 jr math32_dot_a_ok
math32_dot_a_negative:
 inc hl
 ld a,(hl+)
 and a,(hl)
 inc a
 jp nz,_riding_dotq32_wide
math32_dot_a_ok:
 ldhl sp,#7
 bit 7,(hl)
 jr nz,math32_dot_b_negative
 inc hl
 ld a,(hl+)
 or a,(hl)
 jp nz,_riding_dotq32_wide
 jr math32_dot_b_ok
math32_dot_b_negative:
 inc hl
 ld a,(hl+)
 and a,(hl)
 inc a
 jp nz,_riding_dotq32_wide
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

; Generated compile-time entries pass BC=descriptor/page, DE=exponent/m.
; Their original x remains atSP2; all wide x retain the exact generic path.
_riding_coeff32_known::
 ldhl sp,#3
 bit 7,(hl)
 jr nz,math32_coefficient_x_negative
 inc hl
 ld a,(hl+)
 or a,(hl)
 jr nz,math32_coefficient_wide
 jp _riding_coefficients_narrow
math32_coefficient_x_negative:
 inc hl
 ld a,(hl+)
 and a,(hl)
 inc a
 jr z,_riding_coefficients_narrow
math32_coefficient_wide:
 push de
 ldhl sp,#4
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 push bc
 push de
 call _riding_kmul32_wide
 add sp,#6
 ret
;16-bit entry marks bit7 of descriptor; only e<8 requires final16 clamp.
_riding_coefficients_narrow::
 ld a,(#__current_bank)
 push af
 push bc
 ld a,b
 and a,#3
 ; Profile-specific exact tables: 252..255 (4MiB) or 477..480 (8MiB).
 .globl _riding_coefficient_bank_lo
 .globl _riding_coefficient_bank_hi
 add a,#_riding_coefficient_bank_lo
 ld (#0x2000),a
 ld a,#_riding_coefficient_bank_hi
 ld (#0x3000),a
 bit 2,b
 jp nz,math32_coefficient_quotient16
 bit 3,b
 jp nz,math32_coefficient_quotient32
 ; Low quotient, selected by unsigned low byte.
 ldhl sp,#6
 ld l,(hl)
 ld h,#0
 add hl,hl
 ld a,c
 add a,#5
 add a,h
 ld h,a
 ld e,(hl)
 inc hl
 ld d,(hl)
 push de
 ; Prebiased high residue + low residue sets the exact correction carry.
 ldhl sp,#9
 ld l,(hl)
 ld a,c
 add a,#4
 ld h,a
 ld b,(hl)
 ldhl sp,#8
 ld l,(hl)
 ld a,c
 add a,#7
 ld h,a
 ld a,b
 add a,(hl)
 pop de
 ld a,e
 adc a,#0
 ld e,a
 jr nc,math32_coefficient_low_corrected
 inc d
math32_coefficient_low_corrected:
 push de
 ; Full signed32 high quotient. No velocity/result narrowing occurs.
 ldhl sp,#9
 ld l,(hl)
 ld h,#0
 add hl,hl
 add hl,hl
 ld a,c
 add a,h
 ld h,a
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#0
 ld a,e
 add a,(hl)
 ld e,a
 inc hl
 ld a,d
 adc a,(hl)
 ld d,a
 ld a,c
 adc a,#0
 ld c,a
 ld a,b
 adc a,#0
 ld b,a
 add sp,#4
 xor a
 ld (#0x3000),a
 pop af
 ld (#0x2000),a
 ld h,b
 ld l,c
 ret

; Two direct lookups when the exact residue period is1,2 or4.
; For e>=8 the mathematical result fits signed16, then sign-extends32.
math32_coefficient_quotient16:
 swap b
 ld a,b
 and a,#3
 ld b,a
 ldhl sp,#7
 ld l,(hl)
 ld h,#0
 add hl,hl
 ld a,c
 add a,h
 ld h,a
 ld e,(hl)
 inc hl
 ld d,(hl)
 push de
 ldhl sp,#9
 ld a,(hl)
 and a,b
 add a,a
 add a,c
 add a,#2
 ld b,a
 ldhl sp,#8
 ld l,(hl)
 ld h,#0
 add hl,hl
 ld a,b
 add a,h
 ld h,a
 ld e,(hl)
 inc hl
 ld d,(hl)
 ldhl sp,#0
 ld a,e
 add a,(hl)
 ld e,a
 inc hl
 ld a,d
 adc a,(hl)
 ld d,a
 add sp,#4
 xor a
 ld (#0x3000),a
 pop af
 ld (#0x2000),a
 ld a,d
 add a,a
 sbc a,a
 ld h,a
 ld l,a
 ret

; e<8 retains the COMPLETE signed32 high quotient and full32 result.
math32_coefficient_quotient32:
 ldhl sp,#7
 ld l,(hl)
 ld h,#0
 add hl,hl
 add hl,hl
 ld a,c
 add a,h
 ld h,a
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 push bc
 push de
 ldhl sp,#4
 ld c,(hl)
 ldhl sp,#10
 ld l,(hl)
 ld h,#0
 add hl,hl
 ld a,c
 add a,#4
 add a,h
 ld h,a
 ld e,(hl)
 inc hl
 ld d,(hl)
 ldhl sp,#0
 ld a,e
 add a,(hl)
 ld e,a
 inc hl
 ld a,d
 adc a,(hl)
 ld d,a
 inc hl
 ld a,(hl)
 adc a,#0
 ld c,a
 inc hl
 ld a,(hl)
 adc a,#0
 ld b,a
 ldhl sp,#5
 bit 7,(hl)
 jr z,math32_coefficient32_done
 bit 7,b
 jr nz,math32_coefficient16_negative
 ld a,b
 or a,c
 jr nz,math32_coefficient16_positive_overflow
 bit 7,d
 jr z,math32_coefficient32_done
math32_coefficient16_positive_overflow:
 ld de,#0x7fff
 jr math32_coefficient32_done
math32_coefficient16_negative:
 ld a,b
 and a,c
 inc a
 jr nz,math32_coefficient16_negative_overflow
 bit 7,d
 jr nz,math32_coefficient32_done
math32_coefficient16_negative_overflow:
 ld de,#0x8000
math32_coefficient32_done:
 add sp,#6
 xor a
 ld (#0x3000),a
 pop af
 ld (#0x2000),a
 ld h,b
 ld l,c
 ret
