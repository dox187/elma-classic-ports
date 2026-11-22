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
 ld d,h
 ld e,l
 push de
 ld bc,#8
 add hl,bc
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ; Only the rounded torque contributes to omega; a zero impulse adds zero.
 or a,d
 or a,b
 or a,c
 jr z,free_velocity
 ld hl,#_q24_index_C_FREE
 ld a,(#_riding_subphase)
 or a,a
 jr z,free_coefficient
 inc hl
free_coefficient:
 ld a,(hl)
 dec sp
 call _q24_apply_a
 ; Add the full coefficient result (DEBC) to omega.
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push de
 ld de,#20
 add hl,de
 pop de
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
 ld (hl),a
free_velocity:
 pop de
 pop hl
 push hl
 ld bc,#8
 add hl,bc
 ; The impulses and the velocity components are contiguous in x,y order.
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
 pop hl
 jr wheel_move_hl
_riding_wheel_move::
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
wheel_move_hl:
 ld a,l
 cp a,#<(_Bike+24)
 jr nz,wheel_move_other
 ld a,h
 cp a,#>(_Bike+24)
 ld b,#2
 jr z,wheel_move_slot
wheel_move_other:
 ld b,#4
 ld a,l
 cp a,#<_Bike
 jr nz,wheel_move_slot
 ld a,h
 cp a,#>_Bike
 jr nz,wheel_move_slot
 ld b,#0
wheel_move_slot:
 jp _riding_circle_move_regs
