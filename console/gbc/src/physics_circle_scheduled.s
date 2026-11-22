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
circle_axes:
 push bc
 call circle_axis
 pop bc
 inc bc
 inc bc
 inc bc
 inc bc
circle_axis:
 ; HL points to the position, BC to byte 2 of its residual.
 push hl
 push bc
 ld de,#8
 add hl,de
 call circle_load
 pop hl
 call _riding_phase_advance_hl
 pop hl
 jp circle_add
circle_load:
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ret
circle_add:
 ld a,(hl)
 add a,c
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
