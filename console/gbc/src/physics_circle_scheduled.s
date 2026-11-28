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
 .macro circle_store_position
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
 .endm
 push bc
 circle_partial_axis _riding_phase_second_x
 circle_store_position
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
 ld a,(hl+)
 ld d,a
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
 ld c,d
 ; Each next velocity byte supplies the high nibble for the previous
 ; byte's quotient. Leave the original in its register for the next pair.
 .macro circle_join_nibbles low
 xor a,low
 and #0x0f
 xor a,low
 swap a
 ld low,a
 .endm
 ld a,(hl+)
 ld b,a
 circle_join_nibbles c
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ; A zero or all-ones upper word is already the quotient's high word.
 ; Only the sign nibble still needs to join byte one.
 or d
 jr z,circle_word_positive
 ld a,e
 and d
 inc a
 jr nz,circle_general_word
 ld a,b
 swap a
 or #0xf0
 ld b,a
 jr circle_full_add
circle_word_positive:
 ld a,b
 swap a
 and #15
 ld b,a
circle_full_add:
 pop af
 pop hl
 ld a,(hl)
 adc a,c
circle_add_low:
 circle_store_position
 ret

circle_general_word:
 ld a,e
 circle_join_nibbles b
circle_full_wide:
 ld a,d
 circle_join_nibbles e
 ld a,d
 add a,a
 sbc a,a
 xor a,d
 and #0x0f
 xor a,d
 swap a
 ld d,a
 jr circle_full_add

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
 jr circle_add_low
_riding_circle_scheduled_end::


.area _CODE_8
_riding_translate_body_state::
.ifdef RIDING_PAIRED_CIRCLES
 jp _motion_body
.else
 ld hl,#_Bike
 ld bc,#(_move_residual+2)
 jp circle_axes
.endif

.ifdef RIDING_PAIRED_CIRCLES
; Generate each known circle's full-interval x/y pair in the movement bank.
; The arithmetic upper nibble comes from the two high velocity bytes,
; including the signed fourth byte, so the path covers every signed32 input.
 .macro motion_axis offset,res,?upper,?general,?done
 ; For the low position word consume V[4..19]. The top twelve bits
 ; only change the high word when their signed value plus carry is nonzero.
 ld hl,#(_Bike+offset+8)
 ld a,(hl+)
 swap a
 ld c,a
 and #0xf0
 ld d,a
 ld a,(hl+)
 swap a
 ld b,a
 xor c
 and #0xf0
 xor c
 ld c,a
 ld a,(hl)
 ld e,a
 swap a
 xor b
 and #0xf0
 xor b
 ld b,a
 ld a,(#(_move_residual+res+2))
 xor #128
 add d
 rla
 ld d,a
 ccf
 sbc a,a
 ld (#(_move_residual+res+3)),a
 ld a,d
 rra
 ld (#(_move_residual+res+2)),a
 ld hl,#(_Bike+offset)
 ld a,(hl)
 adc c
 ld (hl+),a
 ld a,(hl)
 adc b
 ld (hl+),a
 ; For a zero upper word, the high source byte is either 00 plus
 ; no carry or FF plus carry. ADC retains that same carry in both cases.
 ld a,(#(_Bike+offset+11))
 ld d,a
 adc #0
 jr nz,upper
 sbc a,a
 xor e
 and #0xf0
 jr z,done
 ld a,d
 rlca
 jr general
upper:
 sub d
 rrca
general:
 ; ADC combines the low-word carry with the two disjoint
 ; nibbles. The next ADC extends its carry into the signed high byte.
 ld l,d
 ld h,#>motion_s32_high
 ld d,(hl)
 inc h
 ld a,(hl)
 ld l,e
 inc h
 adc (hl)
 ld e,a
 ld a,d
 adc #0
 ld d,a
 ld hl,#(_Bike+offset+2)
 ld a,(hl)
 add e
 ld (hl+),a
 ld a,(hl)
 adc d
 ld (hl),a
done:
 .endm
 ; Both upper words must match before committing either coordinate.
 ; The fourth byte plus the third byte's sign bit must sum to zero.
 ; Zero directory entries route uncommon high words through the full-width routine.
 .macro motion_upper offset,miss
 ld hl,#(_Bike+offset+10)
 ld a,(hl+)
 ld e,a
 add a,a
 ld a,(hl)
 adc #0
 jp nz,miss
 ld l,e
 ld h,#>motion_upper_page
 ld a,(hl)
 or a
 jp z,miss
 .endm

 ; B contains the three-plane upper digit page selected by motion_upper.
 .macro motion_partial_axis offset,res,publish
 ld hl,#(_Bike+offset+8)
 ld a,(hl+)
 ld e,a
 ld l,(hl)
 ld h,#0x40
 ld d,#0x41
 ld a,(de)
 ld c,a
 inc d
 ld a,(de)
 add (hl)
 ld h,b
 ld b,a
 inc d
 ld a,(de)
 adc (hl)
 ldh (#_q24_fraction+2),a
 inc d
 inc h
 ld a,(de)
 adc (hl)
 ld e,a
 inc h
 ld a,#0
 adc (hl)
 ld d,a
 .if publish
 ldh a,(#_q24_fraction+2)
 add a,a
 sbc a,a
 ldh (#_q24_fraction+3),a
 ld a,c
 ldh (#_q24_fraction),a
 ld a,b
 ldh (#_q24_fraction+1),a
 xor a
 ldh (#_q24_saturated),a
 .endif
 ld hl,#(_move_residual+res)
 ld a,c
 add (hl)
 ld (hl+),a
 ld a,b
 adc (hl)
 ld (hl+),a
 ; Bias the high residual byte without losing the low-word carry.
 ld a,(hl)
 rla
 ccf
 rra
 ld b,a
 ldh a,(#_q24_fraction+2)
 adc b
 rla
 ld c,a
 ccf
 sbc a,a
 inc hl
 ld (hl-),a
 ld a,c
 rra
 ld (hl),a
 ld hl,#(_Bike+offset)
 ld a,(hl)
 adc e
 ld (hl+),a
 ld a,(hl)
 adc d
 ld (hl+),a
 ; The high word changes only when the low-word carry and the
 ; quotient's sign differ. RLA captures both bits, then ADC folds
 ; their parity into bit zero. The uncommon change is exactly +/-1.
 ld a,d
 rla
 adc #0
 rrca
 call c,motion_cross_word
 .endm

 .macro motion_axes base,res,?partial,?wide
 ld a,(#_riding_subphase)
 or a
 jp nz,partial
 motion_axis base,res
 motion_axis base+4,res+4
 jp motion_restore
partial:
 motion_upper base,wide
 ld c,a
 motion_upper base+4,wide
 push af
 ld b,c
 motion_partial_axis base,res,0
 pop af
 ld b,a
 motion_partial_axis base+4,res+4,1
 jp motion_restore
wide:
 ld hl,#(_Bike+base)
 ld bc,#(_move_residual+res+2)
 jp motion_generic
 .endm

; Each entry receives the exact circle whose coordinates are embedded below.
.area _CODE
 .macro motion_enter target
 ld a,#32
 ld (#0x2000),a
 jp target
 .endm
_motion_body::
 motion_enter motion_body
_motion_wheel1::
 motion_enter motion_wheel1
_motion_wheel2::
 motion_enter motion_wheel2
motion_generic:
 ldh a,(#__current_bank)
 ld (#0x2000),a
 jp _riding_circle_axes
motion_restore:
 ldh a,(#__current_bank)
 ld (#0x2000),a
 ret

.area _CODE_32
motion_cross_word:
 bit 7,d
 jr nz,motion_decrement_word
 inc (hl)
 ret nz
 inc hl
 inc (hl)
 ret
motion_decrement_word:
 ld a,(hl)
 sub #1
 ld (hl+),a
 ret nc
 dec (hl)
 ret
motion_body:
 motion_axes 0,0
motion_wheel1:
 motion_axes 24,8
motion_wheel2:
 motion_axes 48,16
.else
; The native fixtures and cartridges without partial-product rows use
; the caller's verified circle pointer and its selected residual slot.
.area _CODE_9
_motion_wheel1::
_motion_wheel2::
 jp circle_axes
.endif
