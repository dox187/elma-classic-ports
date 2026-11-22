; Scheduled movement with exact signed Q24 residual carry.
; SDCC register ABI: value DEBC, shift and slot on stack; result DEBC.
.module physics_phase
.area _CODE
_phase_advance::
 ld a,(#_riding_subphase)
 or a,a
 jr nz,phase_second
 ; A full substep adds only the low velocity nibble at bit 20.
 ; Bias the signed residual by half a unit: the byte addition's carry
 ; is exactly the extra position unit, and its low 16 bits stay intact.
 ldhl sp,#3
 ld a,(hl)
 add a,a
 add a,a
 add a,#<(_move_residual+2)
 ld l,a
 ld a,#>(_move_residual+2)
 adc a,#0
 ld h,a
 push bc
 ld a,(hl)
 xor a,#0x80
 ld b,a
 ld a,c
 swap a
 and a,#0xf0
 add a,b
 ld b,a
 ld a,#0
 adc a,#0
 ld c,a
 ld a,b
 xor a,#0x80
 ld (hl+),a
 rlca
 sbc a,a
 ld (hl),a
 ld a,c
 pop bc
 or a,a
 push af
 .rept 4
 sra d
 rr e
 rr b
 rr c
 .endm
 pop af
 jp z,phase_done
 jp phase_increment
phase_second:
 ld a,(#_riding_move_index)
 push af
 inc sp
 call _q24_apply
 push de
 push bc
 ld hl,#_q24_fraction
 ld c,(hl)
 inc hl
 ld b,(hl)
 inc hl
 ld e,(hl)
 inc hl
 ld d,(hl)
phase_residual:
 ldhl sp,#7
 ld a,(hl)
 add a,a
 add a,a
 ld l,a
 ld h,#0
 push de
 ld de,#_move_residual
 add hl,de
 pop de
 ld a,(hl)
 add a,c
 ld c,a
 inc hl
 ld a,(hl)
 adc a,b
 ld b,a
 inc hl
 ld a,(hl)
 adc a,e
 ld e,a
 inc hl
 ld a,(hl)
 adc a,d
 ld d,a
 bit 7,d
 jr nz,phase_negative
 ld a,d
 or a,a
 jr nz,phase_carry_positive
 bit 7,e
 jr nz,phase_carry_positive
 xor a
 jr phase_store
phase_negative:
 ld a,d
 cp #255
 jr nz,phase_carry_negative
 bit 7,e
 jr z,phase_carry_negative
 xor a
 jr phase_store
phase_carry_positive:
 dec d
 ld a,#1
 jr phase_store
phase_carry_negative:
 inc d
 ld a,#255
phase_store:
 push af
 ld (hl),d
 dec hl
 ld (hl),e
 dec hl
 ld (hl),b
 dec hl
 ld (hl),c
 pop af
 pop bc
 pop de
 or a,a
 jr z,phase_done
 bit 7,a
 jr nz,phase_decrement
phase_increment:
 inc c
 jr nz,phase_done
 inc b
 jr nz,phase_done
 inc e
 jr nz,phase_done
 inc d
 jr phase_done
phase_decrement:
 ld a,c
 sub a,#1
 ld c,a
 ld a,b
 sbc a,#0
 ld b,a
 ld a,e
 sbc a,#0
 ld e,a
 ld a,d
 sbc a,#0
 ld d,a
phase_done:
 pop hl
 inc sp
 inc sp
 jp (hl)

_phase_move::
 ld a,(#_riding_subphase)
 or a,a
 jr z,angle_first
 ld a,(#_riding_angle_index)
 ldhl sp,#2
 ld (hl),a
 jp _q24_apply
angle_first:
 .rept 5
 sla c
 rl b
 rl e
 rl d
 .endm
 pop hl
 inc sp
 jp (hl)
