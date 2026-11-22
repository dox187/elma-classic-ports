; Damping uses full Q18 arms. The reciprocal reaction uses rounded Q10 arms.
; Each force coefficient bank supplies four Q24 products. The wheels receive
; rounded impulses while the body retains their signed fractions. Both wheels
; contribute before the complete spring and damping moments are narrowed.
.module physics_suspension_scheduled
.area _DATA
ss_damping: .ds 32                 ; relx[2], rely[2], arm_x[2], arm_y[2]
ss_spin_mid: .ds 16
ss_spin_top: .ds 16
ss_product_upper: .ds 2
ss_moment: .ds 9
ss_ts: .ds 4
ss_coarse: .ds 4
ss_tr: .ds 4

; Scheduled register convention is BC:DE, high word first.
.macro ss_read address
 ld hl,#(address)
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
.endm
.macro ss_write address
 ld hl,#(address)
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ld (hl),c
 inc hl
 ld (hl),b
.endm
.macro ss_sub address
 ld hl,#(address)
 ld a,e
 sub a,(hl)
 ld e,a
 inc hl
 ld a,d
 sbc a,(hl)
 ld d,a
 inc hl
 ld a,c
 sbc a,(hl)
 ld c,a
 inc hl
 ld a,b
 sbc a,(hl)
 ld b,a
.endm
; R = memory - R. Useful for body_velocity - (wheel_velocity + spin).
.macro ss_reverse_sub address
 ld hl,#(address)
 ld a,(hl+)
 sub a,e
 ld e,a
 ld a,(hl+)
 sbc a,d
 ld d,a
 ld a,(hl+)
 sbc a,c
 ld c,a
 ld a,(hl)
 sbc a,b
 ld b,a
.endm
.macro ss_add address
 ld hl,#(address)
 ld a,(hl+)
 add a,e
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
.endm
; Add the contribution to the wheel while keeping the same value in
; registers for the opposite body force.
.macro ss_accumulate address
 ld hl,#(address)
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
.endm
.macro ss_negate
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ld a,#0
 sbc a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
.endm
; Q24 native ABI is DE:BC. The register entry consumes one scratch stack
; byte after its return address. The shuffle preserves the index in A.
.macro ss_q24
 dec sp
 ld h,b
 ld l,c
 ld b,d
 ld c,e
 ld d,h
 ld e,l
 call _q24_apply_a
 ld h,b
 ld l,c
 ld b,d
 ld c,e
 ld d,h
 ld e,l
.endm
.macro ss_q24_phase coefficient,selected
 ld hl,#coefficient
 ld a,(#_riding_subphase)
 or a
 jr z,selected
 inc hl
selected:
 ld a,(hl)
 ss_q24
.endm
.macro ss_arm body,wheel,destination
 ss_read _Bike+body
 ss_reverse_sub _Bike+wheel
 ss_write destination
.endm
; The native table products are (raw + 2^23) = integer*2^24 + biased.
; The wheel uses only the integer. The body gets both pieces, and four
; such biased fractions per axis account for exactly two whole units.
.macro ss_sub_fraction product
 ld hl,#(ss_force_products+product)
 ld a,e
 sub a,(hl)
 ld e,a
 inc hl
 ld a,d
 sbc a,(hl)
 ld d,a
 inc hl
 ld a,c
 sbc a,(hl)
 ld c,a
 ld a,b
 sbc a,#0
 ld b,a
.endm

; Return a full signed33 spring+damper in A:BCDE and publish its wrapped
; low 32 bits for the wheel. Carry out of bit 31 and both operand signs
; determine byte 4, including for oppositely signed products.
.macro ss_force_pair product,wheel,positive
 ld hl,#(ss_force_products+product+3)
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ld a,b
 add a,a
 sbc a,a
 push af
 ss_add ss_force_products+28+product+3
 bit 7,(hl)
 pop hl
 ld a,h
 jr z,positive
 dec a
positive:
 adc a,#0
 ss_write _riding_suspension_state+16+wheel
.endm

.macro ss_force_axis pair,wheel,axis,first_pos,second_pos
 ld hl,#(_force_residual+axis*8)
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld c,(hl)
 ld b,#2
 ss_sub_fraction pair
 ss_sub_fraction pair+7
 ss_sub_fraction pair+28
 ss_sub_fraction pair+35
 ss_write _riding_force_sums+axis*9

 ss_force_pair pair,wheel,first_pos
 ld h,a
 ld a,(#_force_residual+axis*8+7)
 sub a,h
 push af
 ss_reverse_sub _force_residual+axis*8+3
 pop hl
 ld a,h
 sbc a,#0
 push af
 push bc
 push de

 ss_force_pair pair+7,wheel+4,second_pos
 push af
 ; Stack now has the second sign, the first difference in two words,
 ; and its fifth byte in the A slot of the final saved AF.
 ldhl sp,#2
 ld a,(hl+)
 sub a,e
 ld e,a
 ld a,(hl+)
 sbc a,d
 ld d,a
 ld a,(hl+)
 sbc a,c
 ld c,a
 ld a,(hl+)
 sbc a,b
 ld b,a
 inc hl
 ld a,(hl)
 sbc a,#0
 pop hl
 sub a,h
 ld (#_riding_force_sums+axis*9+8),a
 ss_write _riding_force_sums+axis*9+4
 add sp,#6
.endm
.macro ss_reaction_product arm
 ld a,#14
 push af
 inc sp
 ld hl,#(ss_coarse+arm)
 ld e,(hl)
 inc hl
 ld d,(hl)
 push de
 ss_read ss_tr
 push bc
 push de
 call _riding_mulq32
 add sp,#7
 ld b,h
 ld c,l
.endm
; wheel is the position offset in Bike; offset selects the wheel's 32-bit
; entry in the paired suspension arrays. The lookup pose holds gsx[2],gsy[2].
.macro ss_wheel_inputs wheel,offset
 ss_read _riding_pose_anchor+offset
 ss_sub ss_damping+16+offset
 ss_write _riding_suspension_state+16+offset
 ss_read _riding_pose_anchor+8+offset
 ss_sub ss_damping+24+offset
 ss_write _riding_suspension_state+24+offset
 ld hl,#_riding_pose_anchor+offset
 ld de,#_riding_suspension_state+24+offset
 call ss_spring_product
 push bc
 push hl
 push de
 ld hl,#_riding_pose_anchor+8+offset
 ld de,#_riding_suspension_state+16+offset
 call ss_spring_product
 call ss_spring_difference
 add sp,#6
 .if offset
 ss_accumulate ss_ts
 .else
 ss_write ss_ts
 .endif
 ss_read ss_damping+offset
 ss_add _Bike+wheel+8
 ss_reverse_sub _Bike+8
 ss_write ss_damping+offset
 ss_read ss_damping+8+offset
 ss_add _Bike+12
 ss_sub _Bike+wheel+12
 ss_write ss_damping+8+offset
.endm
.macro ss_wheel_reaction offset,next_wheel,reaction_index,ordinary,have_reaction
 ; Round coarse arms only when this wheel has a reaction torque.
 ld hl,#_riding_suspension_state+8+offset
 ld a,(hl+)
 or a,(hl)
 inc hl
 or a,(hl)
 inc hl
 or a,(hl)
 jp z,next_wheel
 ld hl,#ss_damping+24+offset
 call ss_coarse_arm
 ld hl,#ss_coarse+2
 ld (hl),e
 inc hl
 ld (hl),d
 push de
 ld hl,#ss_damping+16+offset
 call ss_coarse_arm
 ld hl,#ss_coarse
 ld (hl),e
 inc hl
 ld (hl),d
 push de
 ss_read _riding_suspension_state+8+offset
 push bc
 push de
 .ifdef RIDING_GAS_REACTION
 call _riding_gas_reaction
 jr nc,ordinary
 add sp,#8
 jr have_reaction
ordinary:
 .endif
 call _riding_reaction_input32
 add sp,#8
 ld b,h
 ld c,l
 ss_q24_phase _q24_index_C_REACT,reaction_index
 .ifdef RIDING_GAS_REACTION
have_reaction:
 .endif
 ss_write ss_tr
 ss_reaction_product 2
 ss_accumulate _riding_suspension_state+16+offset
 xor a
 call _riding_force_sub_integer_regs
 ss_reaction_product 0
 ss_negate
 ss_accumulate _riding_suspension_state+24+offset
 ld a,#1
 call _riding_force_sub_integer_regs
.endm

.area _CODE_8
_riding_suspension_scheduled::
 ss_arm 0,24,ss_damping+16
 ss_arm 0,48,ss_damping+20
 ss_arm 4,28,ss_damping+24
 ss_arm 4,52,ss_damping+28
 call ss_spin_four
 ss_wheel_inputs 24,0
 ss_wheel_inputs 48,4
 ld hl,#_q24_index_C_SPRING_FW
 ld a,(#_riding_subphase)
 or a
 jr z,ss_spring_selected
 inc hl
ss_spring_selected:
 ld a,(hl)
 ld hl,#_riding_suspension_state+16
 ld de,#ss_force_products
 call ss_force_four
 ld hl,#_q24_index_C_FRIC_W
 ld a,(#_riding_subphase)
 or a
 jr z,ss_damper_selected
 inc hl
ss_damper_selected:
 ld a,(hl)
 ld hl,#ss_damping
 ld de,#ss_force_products+28
 call ss_force_four
 ss_force_axis 0,0,0,ss_x0_pos,ss_x1_pos
 ss_force_axis 14,8,1,ss_y0_pos,ss_y1_pos
 ss_wheel_reaction 0,ss_wheel1,ss_reaction0_index,ss_ordinary0,ss_reaction_ready0
ss_wheel1:
 ss_wheel_reaction 4,ss_wheels_done,ss_reaction1_index,ss_ordinary1,ss_reaction_ready1
ss_wheels_done:
 xor a
 push af
 inc sp
 call _riding_force_finish
 inc sp
 ld b,h
 ld c,l
 ss_write _riding_suspension_state+32
 ld a,#1
 push af
 inc sp
 call _riding_force_finish
 inc sp
 ld b,h
 ld c,l
 ss_write _riding_suspension_state+36
 ld hl,#ss_ts+1
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 ld a,c
 add a,a
 sbc a,a
 ld b,a
 sra b
 rr c
 rr d
 rr e
 sra b
 rr c
 rr d
 rr e
 jr nc,ss_spring_rounded
 inc de
 ld a,d
 or a,e
 jr nz,ss_spring_rounded
 inc bc
ss_spring_rounded:
 ss_q24_phase _q24_index_C_SPRING_T,ss_c_spring_t_index
 ss_negate
 ss_write _riding_suspension_state+40
 ld hl,#_q24_fraction
 ld de,#_riding_suspension_state+44
 .rept 4
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 call ss_damping_torque18
 ld b,h
 ld c,l
 ss_q24_phase _q24_index_C_FRIC_T,ss_c_fric_t_index
 ss_reverse_sub _riding_suspension_state+40
 ss_write _riding_suspension_state+40
 ret

; The returned spring impulse uses only bits 12..43 of the difference,
; so six low product bytes suffice for every signed input.
ss_spring_difference:
 push hl
 ldhl sp,#4
 ld a,(hl+)
 sub a,e
 ld a,(hl+)
 sbc a,d
 pop de
 ; Preserve difference byte 1 and its borrow while reducing bytes 2..5.
 push af
 ld a,(hl+)
 sbc a,e
 ld e,a
 ld a,(hl+)
 sbc a,d
 ld d,a
 ld a,(hl+)
 sbc a,c
 ld c,a
 ld a,(hl)
 sbc a,b
 ld b,a
 pop af
 ld h,a
.macro ss_join_nibbles low,high,out
 ld a,low
 xor a,high
 and a,#0x0f
 xor a,low
 swap a
 ld out,a
.endm
 ss_join_nibbles h,e,h
 ss_join_nibbles e,d,e
 ss_join_nibbles d,c,d
 ss_join_nibbles c,b,b
 ld c,d
 ld d,e
 ld e,h
 ret

; floor(angular_residual * 27007 / 2^24). The normalized residual limits
; the result to signed16. The signed48 product is returned in BC:HL:DE.
_riding_angle_fraction::
 ld hl,#_angular_residual
 ld bc,#27007
 call _riding_product32x16_regs
 ld e,h
 ld d,c
 ret
ss_coarse_arm:
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 ; Round to Q10 for reaction. Extend the original sign before propagating
 ; the rounding carry, including at the positive signed32 limit.
 ld a,b
 add a,a
 sbc a,a
 ld h,a
 ld a,e
 add a,a
 ld a,d
 adc a,#0
 ld e,a
 ld a,c
 adc a,#0
 ld d,a
 ld a,b
 adc a,#0
 ld c,a
 ld a,h
 adc a,#0
 ld b,a
 jp ss_sat16
; Saturate internal signed32 to signed16, preserving sign extension.
ss_sat16:
 ld a,d
 add a,a
 sbc a,a
 cp c
 jr nz,ss_clamp
 cp b
 ret z
ss_clamp:
 bit 7,b
 jr nz,ss_negative
 ld de,#0x7fff
 ld bc,#0
 ret
ss_negative:
 ld de,#0x8000
 ld bc,#0xffff
 ret

; HL -> signed32 arm, DE -> signed32 speed. Return all 64 product bits in
; ss_product_upper:BC:HL:DE. Most speeds need just one signed32 x signed16
; product. The ROM0 multiplier restores the caller bank after table reads.
ss_lever_product:
 push hl
 ld a,(de)
 inc de
 ld c,a
 ld a,(de)
 inc de
 ld b,a
 ld a,(de)
 inc de
 ld l,a
 ld a,(de)
 ld h,a
 ; speed = signed_low + 65536 * (signed_high + signbit(low)).
 bit 7,b
 jr z,ss_check_speed_high
 inc hl
 ld a,h
 xor a,#0x80
 or a,l
 jr z,ss_positive_32768
ss_check_speed_high:
 ld a,h
 or a,l
 jr nz,ss_wide_speed
 pop hl
 call _riding_product32x16_regs
 ld a,b
 add a,a
 sbc a,a
 ld (#ss_product_upper),a
 ld (#ss_product_upper+1),a
 ret

ss_positive_32768:
 ; The adjusted high digit is +32768. Double the full 16384 product.
 push bc
 ld bc,#16384
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call _riding_product32x16_regs
 sla e
 rl d
 rl l
 rl h
 rl c
 rl b
 jr ss_combine_products
ss_wide_speed:
 push bc
 ld b,h
 ld c,l
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call _riding_product32x16_regs
ss_combine_products:
 push bc
 push hl
 push de
 ldhl sp,#6
 ld c,(hl)
 inc hl
 ld b,(hl)
 inc hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call _riding_product32x16_regs
 ; Add high_product << 16 to the sign-extended low_product.
 ld a,b
 add a,a
 sbc a,a
 ld (#ss_product_upper),a
 ld (#ss_product_upper+1),a
 push de
 ld d,h
 ld e,l
 ldhl sp,#2
 ld a,(hl+)
 add a,e
 ld e,a
 ld a,(hl+)
 adc a,d
 ld d,a
 ld a,(hl+)
 adc a,c
 ld c,a
 ld a,(hl+)
 adc a,b
 ld b,a
 ld a,(#ss_product_upper)
 adc a,(hl)
 inc hl
 ld (#ss_product_upper),a
 ld a,(#ss_product_upper+1)
 adc a,(hl)
 ld (#ss_product_upper+1),a
 ld h,d
 ld l,e
 pop de
 add sp,#10
 ret

; Spring needs just the low 48 bits even when the signed result is wider.
; A narrow displacement goes straight to the existing single product. A
; signed24 pair uses three byte rows rather than two signed32x16 products.
ss_spring_product:
 push hl
 ld h,d
 ld l,e
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 add a,a
 sbc a,a
 cp a,(hl)
 jr nz,ss_spring_check24
 inc hl
 cp a,(hl)
 jr nz,ss_spring_fallback
 pop hl
 jp _riding_product32x16_regs
ss_spring_check24:
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 add a,a
 sbc a,a
 cp a,h
 jr nz,ss_spring_fallback
 push de
 bit 7,h
 jr z,ss_spring_speed_pos
 xor a
 sub a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
 ld a,#0
 sbc a,l
 ld l,a
ss_spring_speed_pos:
 ; Keep the sign and speed's upper two magnitude bytes on the stack.
 ld a,h
 ld h,l
 ld l,b
 push hl
 push af
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld b,a
 add a,a
 sbc a,a
 cp a,(hl)
 jr nz,ss_spring_arm_wide
 pop af
 xor a,b
 bit 7,b
 jr z,ss_spring_arm_pos
 push af
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ld a,#0
 sbc a,b
 ld b,a
 pop af
ss_spring_arm_pos:
 pop hl
 add sp,#4
 push af
 call ss_magnitude_product
 pop af
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
 ld a,#0
 sbc a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
 ret
ss_spring_arm_wide:
 add sp,#4
 pop de
ss_spring_fallback:
 pop hl
 jp ss_lever_product

; The four products share omega. For signed24 operands write it as
; lo + 256*mid + 65536*top, with a signed top byte. Each byte selects a
; multiplication-table bank just once for all four independent arms.
ss_spin_four:
 ld hl,#_riding_suspension_state+4
 ld a,(hl+)
 or a,(hl)
 inc hl
 or a,(hl)
 inc hl
 or a,(hl)
 jr nz,ss_spin_nonzero
 ld hl,#ss_damping
 .rept 16
 ld (hl+),a
 .endm
 ret
ss_spin_nonzero:
 dec hl
 ld a,(hl+)
 add a,a
 sbc a,a
 cp a,(hl)
 jp nz,ss_spin_full
.macro ss_arm_width offset
 ld hl,#ss_damping+16+offset+2
 ld a,(hl+)
 add a,a
 sbc a,a
 cp a,(hl)
 jp nz,ss_spin_full
.endm
 ss_arm_width 0
 ss_arm_width 4
 ss_arm_width 8
 ss_arm_width 12
 ld a,(#_riding_suspension_state+4)
 ld de,#ss_damping
 call ss_spin_rows
 ld hl,#_riding_suspension_state+5
 ld a,(hl+)
 or a,(hl)
 jp z,ss_spin_byte
 ld a,(#_riding_suspension_state+5)
 ld de,#ss_spin_mid
 call ss_spin_rows
 ld a,(#_riding_suspension_state+6)
 or a
 jr z,ss_spin_top_ready
 inc a
 jr z,ss_spin_top_ready
 dec a
 bit 7,a
 jr z,ss_spin_top_digit
 cpl
 inc a
ss_spin_top_digit:
 ld de,#ss_spin_top
 call ss_spin_rows
ss_spin_top_ready:
 ; L and M are signed32 rows. Their first two product bytes affect only
 ; the carry into floor((L + 256*M) / 65536). The remaining result of
 ; this unsigned16 by signed24 product fits signed24, including minima.
.macro ss_spin_merge label,offset,arm
label:
 ld hl,#ss_spin_mid+offset
 ld a,(#ss_damping+offset+1)
 add a,(hl)
 inc hl
 ld a,(#ss_damping+offset+2)
 adc a,(hl)
 ld e,a
 inc hl
 ld a,(#ss_damping+offset+3)
 adc a,(hl)
 ld d,a
 inc hl
 ; Sign of L equals sign of its arm when lo is nonzero. Use the
 ; actual high bit of L to cover a zero low row as well.
 ld a,(#ss_damping+offset+3)
 bit 7,a
 ld a,#0
 jr z,001$
 dec a
001$:
 adc a,(hl)
 ld c,a
 add a,a
 sbc a,a
 ld b,a
 ld a,(#_riding_suspension_state+6)
 or a
 jr z,004$
 inc a
 jr nz,002$
 ss_sub ss_damping+arm
 jr 004$
002$:
 ld a,(#_riding_suspension_state+6)
 bit 7,a
 jr z,005$
 ss_sub ss_spin_top+offset
 jr 004$
005$:
 ss_add ss_spin_top+offset
004$:
 ; Round the full signed product once after the Q18 shift.
 sra b
 rr c
 rr d
 rr e
 sra b
 rr c
 rr d
 rr e
 jr nc,006$
 inc de
 ld a,d
 or a,e
 jr nz,006$
 inc bc
006$:
 ss_write ss_damping+offset
.endm
 ss_spin_merge ss_merge_0,0,24
 ss_spin_merge ss_merge_4,4,28
 ss_spin_merge ss_merge_8,8,16
 ss_spin_merge ss_merge_12,12,20
 ret
ss_spin_byte:
 ; For omega in 1..255 each first row is the complete signed32 product.
.macro ss_spin_byte_shift label,offset
label:
 ld hl,#ss_damping+offset+2
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 sra d
 rr e
 sra d
 rr e
 jr nc,001$
 inc de
001$:
 ld a,d
 add a,a
 sbc a,a
 ld b,a
 ld c,a
 ss_write ss_damping+offset
.endm
 ss_spin_byte_shift ss_spin_byte_y0,0
 ss_spin_byte_shift ss_spin_byte_y1,4
 ss_spin_byte_shift ss_spin_byte_x0,8
 ss_spin_byte_shift ss_spin_byte_x1,12
 ret
ss_spin_full:
.macro ss_spin_fallback offset,arm
 ld hl,#ss_damping+arm
 ld de,#_riding_suspension_state+4
 call ss_lever_spin18
 ld b,h
 ld c,l
 ss_write ss_damping+offset
.endm
 ss_spin_fallback 0,24
 ss_spin_fallback 4,28
 ss_spin_fallback 8,16
 ss_spin_fallback 12,20
 ret

; Return clamp32((speed * arm + 2^17) >> 18) in HLDE.
ss_lever_spin18:
 ; A signed16 speed produces a signed48 product, which always fits signed32
 ; after the Q18 shift. Zero is frequent when the bike is at rest.
 push hl
 ld h,d
 ld l,e
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 add a,a
 sbc a,a
 cp a,(hl)
 jr nz,ss_spin_wide
 inc hl
 cp a,(hl)
 jr nz,ss_spin_wide
 pop hl
 ld a,b
 or a,c
 jr z,ss_spin_zero
 call _riding_product32x16_regs
 sra b
 rr c
 rr h
 rr l
 sra b
 rr c
 rr h
 rr l
 ld d,h
 ld e,l
 ld h,b
 ld l,c
 ret nc
 inc de
 ld a,d
 or a,e
 ret nz
 inc hl
 ret
ss_spin_zero:
 ld hl,#0
 ld de,#0
 ret
ss_spin_wide:
 pop hl
 call ss_lever_product
 ld a,l
 add a,#2
 ld e,a
 ld a,h
 adc a,#0
 ld d,a
 ld a,c
 adc a,#0
 ld l,a
 ld a,b
 adc a,#0
 ld h,a
 ld a,(#ss_product_upper)
 adc a,#0
 ld c,a
 ld a,(#ss_product_upper+1)
 adc a,#0
 ld b,a
 add a,a
 sbc a,a
 jp ss_reduce18

; Add or subtract one signed24 by signed24 product. With a wider input,
; extend the partial sum and let the wide routine finish the remaining terms.
.macro ss_moment_term label,speed,arm,subtract,partial,wide
label:
 ld hl,#ss_damping+speed
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld d,a
 add a,a
 sbc a,a
 cp a,(hl)
 .if partial
 jp nz,004$
 .else
 jp nz,wide
 .endif
 ld a,c
 or a,b
 or a,d
 .if partial
 jr z,006$
 .else
 jp z,ss_mt_first_zero
 .endif
 bit 7,d
 jr z,001$
 xor a
 sub a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
 ld a,#0
 sbc a,d
 ld d,a
001$:
 ld e,b
 push de
 ld hl,#ss_damping+arm
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld b,a
 add a,a
 sbc a,a
 cp a,(hl)
 jr nz,003$
 pop hl
 ld a,b
 or a
 jr nz,007$
 ld a,d
 or a,e
 .if partial
 jr z,006$
 .else
 jp z,ss_mt_first_zero
 .endif
007$:
 ld a,(#ss_damping+speed+3)
 xor a,b
 push af
 bit 7,b
 jr z,002$
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ld a,#0
 sbc a,b
 ld b,a
002$:
 call ss_mt_product
 pop af
 bit 7,a
 .if subtract
 jr z,005$
 .else
 jr nz,005$
 .endif
 .if partial
 call ss_magnitude_add
 .else
 call ss_mt_seed_positive
 .endif
 jr 006$
003$:
 pop hl
 .if partial
004$:
 ld hl,#ss_moment+6
 ld a,(hl+)
 add a,a
 sbc a,a
 ld (hl+),a
 ld (hl),a
 .endif
 jp wide
005$:
 .if partial
 call ss_magnitude_sub
 .else
 call ss_mt_seed_negative
 .endif
006$:
.endm

; The first product seeds all seven accumulator bytes, including its sign.
ss_mt_first_zero:
 xor a
 ld hl,#ss_moment
 .rept 7
 ld (hl+),a
 .endm
 jp ss_mt_y0
ss_mt_seed_positive:
 push hl
 ld hl,#ss_moment
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 pop de
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 xor a
 ld (hl),a
 ret
ss_mt_seed_negative:
 push hl
 ld hl,#ss_moment
 xor a
 sub a,e
 ld (hl+),a
 ld a,#0
 sbc a,d
 ld (hl+),a
 pop de
 ld a,#0
 sbc a,e
 ld (hl+),a
 ld a,#0
 sbc a,d
 ld (hl+),a
 ld a,#0
 sbc a,c
 ld (hl+),a
 ld a,#0
 sbc a,b
 ld (hl+),a
 sbc a,a
 ld (hl),a
 ret

; Return clamp32(sum(arm_x * rely - arm_y * relx) >> 18) in HLDE.
; The signed24 path preserves every fractional bit. A wider operand transfers
; the existing partial sum to the nine-byte accumulator before its product.
ss_damping_torque18:
 ; Both horizontal speeds must vanish for these two zero cases. Either
 ; all speeds vanish, or equal vertical speeds act on opposite x arms.
 ld hl,#ss_damping
 ld a,(hl+)
 or a,(hl)
 jr nz,ss_mt_general
 inc hl
 .rept 6
 or a,(hl)
 inc hl
 .endm
 jr nz,ss_mt_general
 ld a,(hl+)
 or a,(hl)
 inc hl
 or a,(hl)
 inc hl
 or a,(hl)
 inc hl
 jr nz,ss_mt_vertical
 .rept 3
 or a,(hl)
 inc hl
 .endm
 or a,(hl)
 jr nz,ss_mt_general
ss_mt_zero:
 ld hl,#0
 ld de,#0
 ret
ss_mt_vertical:
 ; Compare both full-width vertical speeds.
 ld hl,#ss_damping+8
 ld de,#ss_damping+12
 .rept 4
 ld a,(de)
 inc de
 cp a,(hl)
 jr nz,ss_mt_general
 inc hl
 .endm
 ; Opposite signs exclude the same-sign pair INT_MIN, INT_MIN.
 ld hl,#ss_damping+19
 ld a,(#ss_damping+23)
 xor a,(hl)
 bit 7,a
 jr z,ss_mt_general
 ld hl,#ss_damping+20
 ld a,(#ss_damping+16)
 add a,(hl)
 jr nz,ss_mt_general
 inc hl
 ld a,(#ss_damping+17)
 adc a,(hl)
 jr nz,ss_mt_general
 inc hl
 ld a,(#ss_damping+18)
 adc a,(hl)
 jr nz,ss_mt_general
 inc hl
 ld a,(#ss_damping+19)
 adc a,(hl)
 jr z,ss_mt_zero
ss_mt_general:
 ; Four signed24 products of magnitude at most 2^46 fit a signed56
 ; accumulator, and their Q18 result fits signed32 without saturation.
 ss_moment_term ss_mt_x0,8,16,0,0,ss_moment_wide
 ss_moment_term ss_mt_y0,0,24,1,1,ss_mt_wide_term1
 ss_moment_term ss_mt_x1,12,20,0,1,ss_mt_wide_term2
 ss_moment_term ss_mt_y1,4,28,1,1,ss_mt_wide_term3
ss_moment_shift:
 ld hl,#ss_moment+2
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld a,(hl+)
 ld b,(hl)
 ld l,a
 ld h,b
 ld a,(#ss_moment+6)
 jp ss_shift18

; A wide operand still uses at most four byte-table rows. Fold each exact
; magnitude into the signed nine-byte sum before moving to the next term.
ss_moment_wide:
 xor a
 ld hl,#ss_moment
 .rept 9
 ld (hl+),a
 .endm
.macro ss_mt_wide label,speed,arm,subtraction
label:
 ld hl,#ss_damping+speed
 ld de,#ss_damping+arm
 .if subtraction
 ld a,#0x80
 .else
 xor a
 .endif
 call ss_mt_wide_mac
.endm
 ss_mt_wide ss_mt_wide_term0,8,16,0
 ss_mt_wide ss_mt_wide_term1,0,24,1
 ss_mt_wide ss_mt_wide_term2,12,20,0
 ss_mt_wide ss_mt_wide_term3,4,28,1
 ld hl,#ss_moment+2
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld a,(hl+)
 ld b,(hl)
 ld l,a
 ld h,b
 ld a,(#ss_moment+6)
 ld c,a
 ld a,(#ss_moment+7)
 ld b,a
 ld a,(#ss_moment+8)
ss_reduce18:
 ; A:BC is the signed upper portion above the four result bytes (HLDE).
 ; Two final right shifts fit signed32 exactly when A:BC is -2..1.
 or a,a
 jr nz,ss_reduce_negative
 ld a,b
 or a,a
 jr nz,ss_max32
 ld a,c
 cp a,#2
 jr nc,ss_max32
 jr ss_shift18
ss_reduce_negative:
 bit 7,a
 jr z,ss_max32
 inc a
 jr nz,ss_min32
 ld a,b
 inc a
 jr nz,ss_min32
 ld a,c
 cp a,#0xfe
 jr c,ss_min32
ss_shift18:
 sra a
 rr h
 rr l
 rr d
 rr e
 sra a
 rr h
 rr l
 rr d
 rr e
 ret
ss_min32:
 ld hl,#0x8000
 ld de,#0
 ret
ss_max32:
 ld hl,#0x7fff
 ld de,#0xffff
 ret

.macro ss_add_low48
 push hl
 ld hl,#ss_moment
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
.endm
.macro ss_sub_low48
 push hl
 ld hl,#ss_moment
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
.endm

; Source pointers are consumed while copying their unsigned magnitudes.
; Zero and INT32_MIN both fit this representation.
ss_mt_abs_copy:
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 bit 7,b
 ret z
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ld a,#0
 sbc a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
 ret

ss_mt_skip_arm:
 add sp,#4
 ret

ss_mt_wide_mac:
 push af
 push de
 call ss_mt_abs_copy
 ld a,(hl)
 ss_write ss_spin_mid+4
 ld h,a
 ld a,b
 or a,c
 or a,d
 or a,e
 jr z,ss_mt_skip_arm
 ld a,h
 pop hl
 push af
 call ss_mt_abs_copy
 ld a,(hl)
 ld l,a
 ld a,b
 or a,c
 or a,d
 or a,e
 jr z,ss_mt_skip_arm
 ld a,l
 pop hl
 xor a,h
 pop hl
 xor a,h
 push af
 ss_write ss_spin_mid
 xor a
 ld hl,#ss_spin_top
 .rept 8
 ld (hl+),a
 .endm
 call ss_mt_wide_rows
 pop af
 bit 7,a
 ld de,#ss_spin_top
 ld hl,#ss_moment
 jr nz,ss_mt_fold_sub
 or a
 .rept 8
 ld a,(de)
 adc a,(hl)
 ld (hl+),a
 inc de
 .endm
 ret nc
 inc (hl)
 ret
ss_mt_fold_sub:
 or a
 .rept 8
 ld a,(de)
 ld c,a
 ld a,(hl)
 sbc a,c
 ld (hl+),a
 inc de
 .endm
 ret nc
 dec (hl)
 ret

ss_magnitude_add:
 ss_add_low48
 ret nc
 inc (hl)
 ret
ss_magnitude_sub:
 ss_sub_low48
 ret nc
 dec (hl)
 ret

; A is an unsigned omega digit, DE points to four signed32 row results.
ss_spin_rows:
 or a
 jr nz,ss_spin_select
 ld h,d
 ld l,e
 .rept 16
 ld (hl+),a
 .endm
 ret
ss_spin_select:
 ld c,a
 and a,#31
 add a,a
 or a,#>_physics_scale_planes_36
 ld h,a
 ld a,c
 rlca
 rlca
 rlca
 and a,#7
 add a,#36
 jp ss_spin_rows_mapped

.area _CODE
; Read the same two pages for all four arms. B is the carry byte between
; successive digits, and C retains the row multiplier for sign correction.
.macro ss_spin_row label,arm
 ld a,(#ss_damping+arm)
 ld l,a
 ld a,(hl)
 ld (de),a
 inc de
 inc h
 ld b,(hl)
 ld a,(#ss_damping+arm+1)
 ld l,a
 dec h
 ld a,(hl)
 add a,b
 ld (de),a
 inc de
 inc h
 ld a,(hl)
 adc a,#0
 ld b,a
 ld a,(#ss_damping+arm+2)
 ld l,a
 dec h
 ld a,(hl)
 add a,b
 ld (de),a
 inc de
 inc h
 ld a,(hl)
 adc a,#0
 bit 7,l
 jr z,label
 ; A negative arm is unsigned_low24 - 2^24.
 sub a,c
label:
 ld (de),a
 inc de
 dec h
.endm
ss_spin_rows_mapped:
 ld (#0x2000),a
 ss_spin_row ss_spin_row_y0,24
 ss_spin_row ss_spin_row_y1,28
 ss_spin_row ss_spin_row_x0,16
 ss_spin_row ss_spin_row_x1,20
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret

; Multiply B:DE (arm magnitude) by H:L:C (speed magnitude). Combine the
; complete byte-table rows before returning the unsigned product in BC:HL:DE.
; The spin rows are free by the time the spring and damping products run.
.macro ss_mt_two_rows
 ; A is the middle speed digit. Save its row while looking up the low digit.
 push bc
 push de
 ld c,a
 call ss_mt_row
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
 call _riding_product24x8_row
 ldhl sp,#0
 ld a,(hl+)
 add a,d
 ld d,a
 ld a,(hl+)
 adc a,c
 ld c,a
 ld a,(hl+)
 adc a,b
 ld b,a
 ld a,(hl)
 adc a,#0
 ld h,b
 ld l,c
 ld c,a
 ld b,#0
 add sp,#8
.endm
ss_magnitude_product:
 ld a,h
 or a
 jr nz,ss_mt_three
 ld a,l
 or a
 jr nz,ss_mt_two
 call _riding_product24x8_row
 ld h,b
 ld l,c
 ld bc,#0
 jr ss_mt_done
ss_mt_three:
 push hl
 push bc
 push de
 ld c,a
 call ss_mt_row
 ; Store top partial at byte offset 2, then compute the two lower rows.
 ld hl,#ss_spin_mid
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ld (hl),c
 inc hl
 ld (hl),b
 pop de
 pop bc
 pop hl
 ld a,l
 ss_mt_two_rows
 ld a,(#ss_spin_mid+0)
 add a,l
 ld l,a
 ld a,(#ss_spin_mid+1)
 adc a,h
 ld h,a
 ld a,(#ss_spin_mid+2)
 adc a,c
 ld c,a
 ld a,(#ss_spin_mid+3)
 adc a,b
 ld b,a
 jr ss_mt_done
ss_mt_two:
 ss_mt_two_rows
ss_mt_done:
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret
ss_mt_row:
 ld a,c
 dec a
 jr z,ss_mt_row_one
 dec a
 jp nz,_riding_product24x8_row
 sla e
 rl d
 ld a,b
 rla
 ld c,a
 ld b,#0
 rl b
 ret
ss_mt_row_one:
 ld c,b
 ld b,#0
 ret

; B:DE and H:L:C are unsigned 24-bit magnitudes. Preserve the three
; arm digits across the upper row, so the low row uses the same registers.
ss_mt_product:
 ld a,h
 or a
 jr z,ss_mt_product_low
 dec a
 jr nz,ss_mt_product_upper
 ; A top digit of one contributes the unchanged arm at byte offset two.
 ld a,e
 ld (#ss_spin_mid),a
 ld a,d
 ld (#ss_spin_mid+1),a
 ld a,b
 ld (#ss_spin_mid+2),a
 call ss_mt_product_low
 ld a,(#ss_spin_mid)
 add a,l
 ld l,a
 ld a,(#ss_spin_mid+1)
 adc a,h
 ld h,a
 ld a,(#ss_spin_mid+2)
 adc a,c
 ld c,a
 ret nc
 inc b
 ret
ss_mt_product_upper:
 jp ss_magnitude_product
ss_mt_product_low:
 ld a,l
 or a
 jr z,ss_mt_product_single
 ld l,a
 rlca
 rlca
 rlca
 and a,#7
 add a,#36
 ld (#0x2000),a
 ld a,l
 and a,#31
 add a,a
 or a,#>_physics_scale_planes_36
 ld h,a
 ld l,e
 ld a,(hl)
 ld (#ss_spin_top),a
 inc h
 ld a,(hl)
 ld l,d
 dec h
 add a,(hl)
 ld (#ss_spin_top+1),a
 inc h
 ld a,(hl)
 adc a,#0
 ld l,b
 dec h
 add a,(hl)
 ld (#ss_spin_top+2),a
 inc h
 ld a,(hl)
 adc a,#0
 ld (#ss_spin_top+3),a
 call _riding_product24x8_row
 ld hl,#ss_spin_top
 ld a,(hl+)
 add a,d
 ld d,a
 ld a,(hl+)
 adc a,c
 ld c,a
 ld a,(hl+)
 adc a,b
 ld h,a
 ld a,(#ss_spin_top+3)
 adc a,#0
 ld l,c
 ld c,a
 ld b,#0
 jr ss_mt_product_done
ss_mt_product_single:
 call _riding_product24x8_row
 ld h,b
 ld l,c
 ld bc,#0
ss_mt_product_done:
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret

; Each row leaves DE at the next byte of the product. A 24-by-8 table
; product also covers a full-width arm by reading its last digit from the
; same table pages. Restore ROMB0 only after the last nonzero speed digit.
ss_mt_wide_rows:
 ld de,#ss_spin_top
 ld a,(#ss_spin_mid+4)
 call ss_mt_wide_row
 ld a,(#ss_spin_mid+5)
 call ss_mt_wide_row
 ld a,(#ss_spin_mid+6)
 or a
 jr z,001$
 call ss_mt_wide_row
 jr 002$
001$:
 inc de
002$:
 ld a,(#ss_spin_mid+7)
 or a
 call nz,ss_mt_wide_row
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret
ss_mt_wide_row:
 or a
 jr nz,003$
 inc de
 ret
003$:
 push de
 push de
 ld c,a
 ld hl,#ss_spin_mid
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld b,(hl)
 call _riding_product24x8_row
 ld a,(#ss_spin_mid+3)
 or a
 jr z,ss_mt_accum4
 ld l,a
 dec h
 ld a,(hl)
 add a,b
 ld b,a
 inc h
 ld a,(hl)
 adc a,#0

.macro ss_mt_accum_low4
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
.endm
ss_mt_accum5:
 pop hl
 push af
 ss_mt_accum_low4
 pop de
 ld a,(hl)
 adc a,d
 ld (hl+),a
 jr ss_mt_carry
ss_mt_accum4:
 pop hl
 ss_mt_accum_low4
ss_mt_carry:
 jr nc,ss_mt_row_done
ss_mt_carry_loop:
 inc (hl)
 jr nz,ss_mt_row_done
 inc hl
 jr ss_mt_carry_loop
ss_mt_row_done:
 pop de
 inc de
 ret

; The caller supplies four signed inputs in HL, seven-byte output records in
; DE, and a coefficient index in A. All four products share one bank mapping.
; For the positive suspension scales at most one, the low byte contributes
; only one quotient byte and an unsigned 16-bit prefix contributes at most
; two. Inputs of every width retain the table's full biased low 24 bits.
.area _HRAM
; One HRAM page holds all eight records. C can advance through the records
; independently of the table pointers DE/HL and the third input digit in B.
ss_force_products: .ds 56
ss_force_page: .ds 1
ss_force_byte2: .ds 1
ss_force_byte3: .ds 1
ss_force_index: .ds 1

.area _CODE
ss_force_four:
 push hl
 ld b,d
 ld c,e
 ldh (#ss_force_index),a
 srl a
 ld d,a
 ld e,#0x40
 jr nc,ss_force_page_set
 ld e,#0x60
ss_force_page_set:
 ld a,(#_q24_first_bank_low)
 add a,d
 ld (#0x2000),a
 ld a,#1
 ld (#0x3000),a
 ld a,e
 ldh (#ss_force_page),a
 add a,#26
 ld h,a
 ; The metadata flags cover coefficients that saturate or have negative sign.
 ; Keep the scalar path available to different generated coefficient sets.
 ld l,#14
 ld a,(hl)
 ld l,#23
 or a,(hl)
 pop hl
 jp nz,ss_force_generic
 call ss_force_lane
 call ss_force_lane
 call ss_force_lane
 call ss_force_lane
ss_force_restore:
 xor a
 ld (#0x3000),a
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret

; DE and HL walk rows for byte zero and byte one. Emit the biased fraction
; and the first two quotient bytes. INC rr, INC r and LD preserve carry.
.macro ss_force_emit_low
 ld a,(de)
 ldh (c),a
 inc c
 inc d
 ld a,(de)
 add a,(hl)
 ldh (c),a
 inc c
 inc d
 inc h
 .rept 2
 ld a,(de)
 adc a,(hl)
 ldh (c),a
 inc c
 inc d
 inc h
 .endm
 ld a,(hl)
 adc a,#0
 ldh (c),a
 inc c
.endm
ss_force_lane:
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 push hl
 or a
 jr z,ss_force_positive
 inc a
 jr nz,ss_force_wide_dec
 ld a,b
 inc a
 jr nz,ss_force_negative24
 ld a,d
 inc a
 jr z,ss_force_negative8
 ld l,d
 ldh a,(#ss_force_page)
 ld d,a
 add a,#11
 jr ss_force_narrow16
ss_force_positive:
 ld a,b
 or a
 jr nz,ss_force_positive24
 ld a,d
 or a
 jr z,ss_force_positive8
 ld l,d
 ldh a,(#ss_force_page)
 ld d,a
 add a,#5
ss_force_narrow16:
 ld h,a
 ss_force_emit_low
 inc h
 ld a,(hl)
 adc a,#0
 ldh (c),a
 inc c
 ldh (c),a
 inc c
 pop hl
 ret
ss_force_negative8:
 ldh a,(#ss_force_page)
 add a,#27
 jr ss_force_narrow8
ss_force_positive8:
 ldh a,(#ss_force_page)
ss_force_narrow8:
 ld h,a
 ld l,e
 .rept 4
 ld a,(hl)
 ldh (c),a
 inc c
 inc h
 .endm
 ld a,(hl)
 .rept 3
 ldh (c),a
 inc c
 .endm
 pop hl
 ret

ss_force_wide_dec:
 dec a
 jr ss_force_wide
ss_force_negative24:
 ld a,#255
 jr ss_force_wide
ss_force_positive24:
 xor a
ss_force_wide:
 ldh (#ss_force_byte3),a
 ld l,d
 ldh a,(#ss_force_page)
 ld d,a
 add a,#5
 ld h,a
 ss_force_emit_low
 ; Add the third table digit starting at product byte two. No upper
 ; prefix bytes exist yet: its quotient fits unsigned16 for both phases.
 dec c
 dec c
 dec c
 ldh a,(#ss_force_byte3)
 inc a
 ldh a,(#ss_force_page)
 jr nz,ss_force_unsigned2
 add a,#11
 jr ss_force_row2
ss_force_unsigned2:
 add a,#17
ss_force_row2:
 ld h,a
 ld a,b
 ld l,a
 ldh a,(c)
 add a,(hl)
 ldh (c),a
 inc c
 inc h
 .rept 2
 ldh a,(c)
 adc a,(hl)
 ldh (c),a
 inc c
 inc h
 .endm
 .rept 2
 ld a,(hl)
 adc a,#0
 ldh (c),a
 inc c
 inc h
 .endm
 ldh a,(#ss_force_byte3)
 inc a
 jr z,ss_force_lane_done
 dec a
 jr z,ss_force_lane_done
 ld l,a
 ldh a,(#ss_force_page)
 add a,#22
 ld h,a
 dec c
 dec c
 dec c
 dec c
 ldh a,(c)
 add a,(hl)
 ldh (c),a
 inc c
 inc h
 .rept 3
 ldh a,(c)
 adc a,(hl)
 ldh (c),a
 inc c
 inc h
 .endm
ss_force_lane_done:
 pop hl
 ret

; Unsupported generated scales use the scalar saturation and fractional rules.
ss_force_generic:
 call ss_force_restore
 call ss_force_generic_lane
 call ss_force_generic_lane
 call ss_force_generic_lane
ss_force_generic_lane:
 push bc
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 push hl
 dec sp
 ldh a,(#ss_force_index)
 call _q24_apply_a
 ; Stack holds the next input and the destination for this record.
 pop hl
 ld a,l
 ldh (#ss_force_byte2),a
 ld a,h
 ldh (#ss_force_byte3),a
 pop hl
 ldh a,(#_q24_fraction)
 ld (hl+),a
 ldh a,(#_q24_fraction+1)
 ld (hl+),a
 ldh a,(#_q24_fraction+2)
 xor a,#128
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld b,h
 ld c,l
 ldh a,(#ss_force_byte2)
 ld l,a
 ldh a,(#ss_force_byte3)
 ld h,a
 ret

.ifdef RIDING_GAS_REACTION
.area _CODE_8
; Stack ABI0 tq32,kx16,ky16. The generated row includes both rounding
; operations. Close separation keeps its full distance-squared division.
_riding_gas_reaction::
 ldhl sp,#2
 ld a,(hl+)
 cp #<reaction_gas
 jr z,gas_positive
 cp #<(-reaction_gas)
 jr nz,gas_other
 ld a,(hl+)
 cp #>(-reaction_gas)
 jr nz,gas_other
 ld a,(hl+)
 and (hl)
 inc a
 jr nz,gas_other
 ld a,#3
 jr gas_mode
gas_positive:
 ld a,(hl+)
 cp #>reaction_gas
 jr nz,gas_other
 ld a,(hl+)
 or (hl)
 jr nz,gas_other
gas_mode:
 ld c,a
 ld a,(#_riding_subphase)
 or a
 ld a,c
 jr z,gas_page
 add a,#6
gas_page:
 push af
 ldhl sp,#8
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 push bc
 push de
 call _riding_recip_index
 add sp,#4
 ld c,e
 pop af
 ld b,a
 ld a,c
 cp #16
 jr nc,gas_read
gas_other:
 and a
 ret
gas_read:
 jp gas_read_fixed

.area _CODE
gas_read_fixed:
 ld hl,#_riding_gas_rows
 add hl,bc                    ; B is the phase/sign page, C the distance index
 ld a,#7
 ld (#0x2000),a
 ld e,(hl)
 inc h
 ld d,(hl)
 inc h
 ld c,(hl)
 ld a,c
 add a,a
 sbc a,a
 ld b,a
 ld a,(#__current_bank)
 ld (#0x2000),a
 scf
 ret
.endif
