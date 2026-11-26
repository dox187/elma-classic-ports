; The two integer torques and their centered fractional remainders enter
; the same signed Q24 accumulator. Subtract both unrounded products first,
; then round exactly once. All temporaries below have been consumed by the
; linear suspension solve before this angular stage begins.
.area _CODE
ss_word_torque::
 ld a,#1
 ld (#0x2000),a
 call ss_word_torque_pair
 ld a,#8
 ld (#0x2000),a
 ret

.area _CODE_1
; Add an unsigned low-digit product to a signed high-digit product shifted
; by one byte. The damping product fits signed 32 bits, the spring signed 40.
.macro torque_raw name,source,dest,width,?selected
 ld a,(#_riding_subphase)
 or a
 ld a,#>_torque_'name'_0
 jr z,selected
 ld a,#>_torque_'name'_1
selected:
 ld h,a
 add #width
 ld d,a
 ld a,(#source)
 ld l,a
 ld a,(#source+1)
 ld e,a
 ld a,(hl)
 ld (#dest),a
 .irp digit,1,2
 inc h
 ld a,(de)
 .ifeq digit-1
 add (hl)
 .else
 adc (hl)
 .endif
 ld (#dest+digit),a
 inc d
 .endm
 .ifeq width-4
 inc h
 ld a,(de)
 adc (hl)
 ld (#dest+3),a
 inc d
 .endif
 ld a,(de)
 adc #0
 ld (#dest+width),a
.endm

ss_word_torque_pair:
 torque_raw C_SPRING_T,ss_coarse,ss_moment,4
 torque_raw C_FRIC_T,ss_tr,ss_force_products,3
 ; Leave the same public Q24 fraction and saturation flag as the final
 ; damping multiplication. Raw and centered fractions share their low 24 bits.
 ldh a,(ss_force_products)
 ldh (#_q24_fraction),a
 ldh a,(ss_force_products+1)
 ldh (#_q24_fraction+1),a
 ldh a,(ss_force_products+2)
 ldh (#_q24_fraction+2),a
 add a
 sbc a,a
 ldh (#_q24_fraction+3),a
 xor a
 ldh (#_q24_saturated),a
 ; Residual - spring, five little-endian bytes in place.
 ld hl,#ss_moment
 .irp digit,0,1,2,3,4
 .ifeq digit-4
 ld a,(#_angular_residual+3)
 .else
 ld a,(#_angular_residual+digit)
 .endif
 .ifeq digit
 sub (hl)
 .else
 sbc (hl)
 .endif
 ld (hl+),a
 .endm
 ; Subtract damping, retain the signed low 24 bits as next residual
 ; and sign-extend the rounded integer impulse.
 ldh a,(ss_force_products+3)
 add a
 sbc a,a
 ld b,a
 ld hl,#ss_force_products
 .irp digit,0,1,2
 ld a,(#ss_moment+digit)
 .ifeq digit
 sub (hl)
 .else
 sbc (hl)
 .endif
 ld (#_riding_suspension_state+48+digit),a
 inc hl
 .endm
 ld c,a
 ld a,(#ss_moment+3)
 sbc (hl)
 ld e,a
 ld a,(#ss_moment+4)
 sbc b
 ld d,a
 ld a,c
 add a
 ld a,#0
 sbc a,a
 ld (#_riding_suspension_state+51),a
 ld hl,#_riding_suspension_state+44
 ld a,e
 adc #0
 ld (hl+),a
 ld a,d
 adc #0
 ld (hl+),a
 add a
 sbc a,a
 ld (hl+),a
 ld (hl),a
 ret
