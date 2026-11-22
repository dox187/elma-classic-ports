; Scheduled movement with exact signed Q24 residual carry.
; SDCC register ABI: value DEBC, shift and slot on stack; result DEBC.
.module physics_phase
.area _CODE
_phase_advance::
 ldhl sp,#3
 ld a,(hl)
 add a,a
 add a,a
 add a,#<(_move_residual+2)
 ld l,a
 ld a,#>(_move_residual+2)
 adc a,#0
 ld h,a
 call _riding_phase_advance_hl
 pop hl
 inc sp
 inc sp
 jp (hl)

; Native entry. HL is the address of byte 2 of the coordinate's residual.
_riding_phase_advance_hl::
 ld a,(#_riding_subphase)
 or a,a
 jr nz,phase_second
 ; A full substep adds only the low velocity nibble at bit 20.
 ; Bias the signed residual by half a unit: the byte addition's carry
 ; is exactly the extra position unit, and its low 16 bits stay intact.
 ld a,c
 swap a
 and a,#0xf0
 push bc
 ld b,a
 ld a,(hl)
 xor a,#0x80
 add a,b
 ld b,a
 ; Save the carry in C without affecting the biased result in B.
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
 ld l,a
 ; Join neighboring nibbles instead of shifting all four bytes four times.
 .macro shift_four low,high
 ld a,high
 xor a,low
 and a,#0x0f
 xor a,low
 swap a
 ld low,a
 .endm
 shift_four c,b
 shift_four b,e
 shift_four e,d
 ld a,d
 add a,a
 sbc a,a
 xor a,d
 and a,#0x0f
 xor a,d
 swap a
 ld d,a
 ld a,l
 or a,a
 jr z,phase_done
 jr phase_increment
phase_second:
 push hl
 ld a,(#_riding_move_index)
 dec sp
 call _q24_apply_a
 pop hl
 push de
 push bc
 ; Bias the old signed residual by half a Q24 unit. In unsigned
 ; arithmetic the correction is carry + sign_extension(fraction).
 ; q24_apply publishes a canonical signed 24-bit fraction in HRAM.
 ld a,(hl)
 xor a,#0x80
 ld b,a
 dec hl
 dec hl
 ldh a,(#_q24_fraction)
 add a,(hl)
 ld (hl+),a
 ldh a,(#_q24_fraction+1)
 adc a,(hl)
 ld (hl+),a
 ldh a,(#_q24_fraction+2)
 adc a,b
 ld b,a
 ldh a,(#_q24_fraction+3)
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
 pop de
 or a,a
 jr z,phase_done
 bit 7,a
 jr nz,phase_decrement
phase_increment:
 inc bc
 ld a,b
 or a,c
 jr nz,phase_done
 inc de
 jr phase_done
phase_decrement:
 dec bc
 ld a,b
 and a,c
 inc a
 jr nz,phase_done
 dec de
phase_done:
 ret

_phase_move::
 ld a,(#_riding_subphase)
 or a,a
 jr z,angle_first
 ld a,(#_riding_angle_index)
 ldhl sp,#2
 ld (hl),a
 jp _q24_apply
angle_first:
 .macro shift_five upper,lower
 ld a,upper
 xor a,lower
 and a,#7
 xor a,lower
 rrca
 rrca
 rrca
 ld upper,a
 .endm
 shift_five d,e
 shift_five e,b
 shift_five b,c
 ld a,c
 rrca
 rrca
 rrca
 and a,#0xe0
 ld c,a
 pop hl
 inc sp
 jp (hl)
