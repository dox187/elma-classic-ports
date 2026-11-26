; Scheduled packed circle_t motion, fixed ROM0.
; Stack ABI0: circle pointer, x residual slot (body 0, wheels 2/4).
; Layout rx0 ry4 vx8 vy12 alfa16 omega20. All additions wrap modulo 2^32.
.module physics_circle_scheduled
.area _CODE
_riding_circle_scheduled::
 ldhl sp,#4
 ld b,(hl)
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
; HL=circle, B=x slot. Angle has no residual, so zero omega leaves it intact.
_riding_circle_move_regs::
 push bc
 push hl
 ld de,#20
 add hl,de
 call circle_load
 ld a,c
 or a,b
 or a,e
 or a,d
 jr z,circle_angle_done
 ld a,#7
 push af
 inc sp
 call _phase_move
 pop hl
 push hl
 push de
 ld de,#16
 add hl,de
 pop de
 call circle_add
circle_angle_done:
 pop hl
 pop bc
 jr circle_translate
; The body has already advanced its angle using its fractional omega.
_riding_body_translate::
 ldhl sp,#4
 ld b,(hl)
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
circle_translate:
 ; Derive the X residual once. Y's signed Q24 residual follows four
 ; bytes later, and neither public velocity nor the circle pointer moves.
 ld a,b
 add a,a
 add a,a
 add a,#<(_move_residual+2)
 ld c,a
 ld a,#>(_move_residual+2)
 adc a,#0
 ld b,a
_riding_circle_axes::
circle_axes:
 ld a,(#_riding_subphase)
 or a
 jr z,circle_full_axes
 .macro circle_partial_axis advance
 push hl
 push bc
 ld de,#8
 add hl,de
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 pop hl
 call advance
 pop hl
 ld a,(hl)
 adc a,c
 .endm
 push bc
 circle_partial_axis _riding_phase_second_x
 call circle_add_low
 pop bc
 inc bc
 inc bc
 inc bc
 inc bc
 circle_partial_axis _riding_phase_second_carry
 jr circle_add_low

circle_full_axes:
 push bc
 call circle_full_axis
 pop bc
 .rept 4
 inc bc
 .endm
circle_full_axis:
 ; Position advances by floor(v/16) plus the carry from the biased
 ; residual. Save that carry for the low position byte, so neither
 ; axis needs to form and increment an intermediate displacement.
 push hl
 ld de,#8
 add hl,de
 ld a,(bc)
 xor #0x80
 ld e,a
 ld a,(hl)
 swap a
 and #0xf0
 add a,e
 push af
 xor #0x80
 ld (bc),a
 inc bc
 rlca
 sbc a,a
 ld (bc),a
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ; Join adjacent nibbles. When the upper word already sign-extends
 ; a 16-bit velocity, both upper bytes of its quotient are unchanged.
 .macro circle_shift_four low,high
 ld a,high
 xor a,low
 and #0x0f
 xor a,low
 swap a
 ld low,a
 .endm
 circle_shift_four c,b
 circle_shift_four b,e
 ld a,d
 inc a
 cp #2
 jr nc,circle_full_wide
 ld a,e
 xor a,d
 jr z,circle_full_add
 and #0xf0
 xor a,d
 swap a
 ld e,a
 jr circle_full_add
circle_full_wide:
 circle_shift_four e,d
 ld a,d
 add a,a
 sbc a,a
 xor a,d
 and #0x0f
 xor a,d
 swap a
 ld d,a
circle_full_add:
 pop af
 pop hl
 ld a,(hl)
 adc a,c
 jr circle_add_low
_riding_circle_load::
circle_load:
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ret
_riding_circle_add::
circle_add:
 ld a,(hl)
 add a,c
circle_add_low:
 ld (hl+),a
 ld a,(hl)
 adc a,b
 ld (hl+),a
 ld a,(hl)
 adc a,e
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld (hl+),a
 ret
_riding_circle_scheduled_end::


.area _CODE_8
_riding_translate_body_state::
 ld hl,#_Bike
 ld bc,#(_move_residual+2)
 jp circle_axes
