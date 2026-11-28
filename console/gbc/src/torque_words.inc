; The two integer torques and their centered fractional remainders enter
; the same signed Q24 accumulator. Subtract both unrounded products first,
; then round exactly once. All temporaries below have been consumed by the
; linear suspension solve before this angular stage begins.
.area _CODE
ss_word_torque::
 ld b,#0
ss_extended_torque:
 ld a,#1
 ld (#0x2000),a
 call ss_word_torque_pair
 ld a,#8
 ld (#0x2000),a
 ret

.area _CODE_1
ss_torque_spring = ss_force_products+7
; Add an unsigned low-digit product to a signed high-digit product shifted
; by one byte. The low damping word fits signed32 and the spring fits signed40.
.macro torque_raw source,dest,width
 ld a,h
 add #width
 ld d,a
 ld a,(#source)
 ld l,a
 ld a,(#source+1)
 ld e,a
 ld a,(hl)
 ldh (#dest),a
 .irp digit,1,2
 inc h
 ld a,(de)
 .ifeq digit-1
 add (hl)
 .else
 adc (hl)
 .endif
 ldh (#dest+digit),a
 inc d
 .endm
 .ifeq width-4
 inc h
 ld a,(de)
 adc (hl)
 ldh (#dest+3),a
 inc d
 .endif
 ld a,(de)
 adc #0
 ldh (#dest+width),a
.endm

ss_word_torque_pair:
 ld h,#>_torque_C_SPRING_T_0
 ld c,#>_torque_C_FRIC_T_0
 ld a,(#_riding_subphase)
 or a
 jr z,ss_torque_pages
 ld h,#>_torque_C_SPRING_T_1
 ld c,#>_torque_C_FRIC_T_1
ss_torque_pages:
 torque_raw ss_coarse,ss_torque_spring,4
 ld h,c
 torque_raw ss_tr,_q24_fraction,3
 ; K times the coefficient enters at bit 16 of the signed low-word product.
 ; DE still addresses its last signed damping plane.
 ld c,b
 add a
 sbc a
 ld b,a
 ld a,c
 or a
 jr z,ss_damping_extended
 ld l,c
 ld h,d
 dec h
 dec h
 ldh a,(_q24_fraction+2)
 add (hl)
 ldh (_q24_fraction+2),a
 inc h
 ldh a,(_q24_fraction+3)
 adc (hl)
 ldh (_q24_fraction+3),a
 inc h
 ld a,b
 adc (hl)
 ld b,a
ss_damping_extended:
 ; Residual - spring, five little-endian bytes in place.
 ld hl,#ss_torque_spring
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
 ld hl,#_q24_fraction
 .irp digit,0,1,2
 ldh a,(#ss_torque_spring+digit)
 .ifeq digit
 sub (hl)
 .else
 sbc (hl)
 .endif
 ld (#_riding_suspension_state+48+digit),a
 inc hl
 .endm
 ld c,a
 ldh a,(#ss_torque_spring+3)
 sbc (hl)
 ld e,a
 ldh a,(#ss_torque_spring+4)
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
 ; Publish the centered damping fraction after consuming its fourth raw byte.
 ldh a,(#_q24_fraction+2)
 add a
 sbc a
 ldh (#_q24_fraction+3),a
 xor a
 ldh (#_q24_saturated),a
 ret
