; Free-wheel torque, velocity and motion. Additions wrap modulo 2^32.
.module physics_free_fast
.area _CODE_9
_riding_free32::
 ldhl sp,#2
; HL points to k*, dvx32, dvy32, tq32 in the caller's frame.
_riding_free_inputs::
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 push de
 ld b,h
 ld c,l
 ld hl,#8
 add hl,de
 ld d,b
 ld e,c
 ; Consume both impulses in record order. HL reaches alfa as DE reaches tq.
 .rept 2
 ld a,(de)
 inc de
 add a,(hl)
 ld (hl+),a
 .rept 3
 ld a,(de)
 inc de
 adc a,(hl)
 ld (hl+),a
 .endm
 .endm
 push hl
 ld h,d
 ld l,e
 call _riding_circle_load
 ld a,d
 or a,e
 or a,b
 or a,c
 jr z,wheel_load_omega
.ifdef RIDING_FREE_THROTTLE
 call _riding_free_throttle
 jr c,free_apply
.endif
 ld hl,#_q24_index_C_FREE
 ld a,(#_riding_subphase)
 or a,a
 jr z,free_coefficient
 inc hl
free_coefficient:
 ld a,(hl)
 dec sp
 call _q24_apply_a
free_apply:
 ; Store the new omega modulo 2^32 and retain it for the angle update.
 pop hl
 push hl
 inc hl
 inc hl
 inc hl
 inc hl
 ld a,(hl)
 add a,c
 ld (hl+),a
 ld c,a
 ld a,(hl)
 adc a,b
 ld (hl+),a
 ld b,a
 ld a,(hl)
 adc a,e
 ld (hl+),a
 ld e,a
 ld a,(hl)
 adc a,d
 ld (hl),a
 ld d,a
 jr wheel_angle
_riding_wheel_move::
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
_riding_wheel_move_hl::
 push hl
 ld de,#16
 add hl,de
 push hl
wheel_load_omega:
 pop hl
 push hl
 inc hl
 inc hl
 inc hl
 inc hl
 call _riding_circle_load
wheel_angle:
 ld a,d
 or a,e
 or a,b
 or a,c
 pop hl
 jr z,wheel_translate
 push hl
 ; The partial substep uses the saturating coefficient and publishes its
 ; fraction. For the full substep, omega*32 wraps in the phase word.
 call _riding_angle_regs
 pop hl
 call _riding_circle_add
wheel_translate:
 pop hl
 ld a,l
 cp a,#<(_Bike+24)
 jr nz,wheel_move_other
 ld a,h
 cp a,#>(_Bike+24)
 ld bc,#(_move_residual+10)
 jr z,wheel_move_slot
wheel_move_other:
 ld bc,#(_move_residual+18)
 ld a,l
 cp a,#<_Bike
 jr nz,wheel_move_slot
 ld a,h
 cp a,#>_Bike
 jr nz,wheel_move_slot
 ld bc,#(_move_residual+2)
wheel_move_slot:
 jp _riding_circle_axes

.ifdef RIDING_FREE_THROTTLE
; DEBC is a nonzero torque. For constant throttle, publish the same
; fractional remainder and saturation byte as q24_apply, even in free fall.
; A miss preserves all four input bytes and clears carry.
_riding_free_throttle::
 ld a,d
 or a,e
 jr nz,free_check_negative
 ld a,c
 xor a,#<free_gas
 ret nz
 ld a,b
 xor a,#>free_gas
 ret nz
 ld hl,#free_throttle_values
 jr free_select_step
free_check_negative:
 ld a,d
 and a,e
 inc a
 jr nz,free_miss
 ld a,c
 xor a,#<(-free_gas)
 ret nz
 ld a,b
 xor a,#>(-free_gas)
 ret nz
 ld hl,#free_throttle_values+16
free_select_step:
 ld a,(#_riding_subphase)
 or a
 jr z,free_read_throttle
 ld de,#8
 add hl,de
free_read_throttle:
 xor a
 ldh (#_q24_saturated),a
 ld a,(hl+)
 ldh (#_q24_fraction),a
 ld a,(hl+)
 ldh (#_q24_fraction+1),a
 ld a,(hl+)
 ldh (#_q24_fraction+2),a
 ld a,(hl+)
 ldh (#_q24_fraction+3),a
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 scf
 ret
free_miss:
 or a
 ret
.endif
