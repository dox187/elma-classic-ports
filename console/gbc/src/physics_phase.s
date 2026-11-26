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
 ret z
phase_increment:
 inc bc
 ld a,b
 or a,c
 ret nz
 inc de
 ret

phase_second:
 ld a,d
 or a,e
 or a,b
 or a,c
 jr nz,phase_product
 ; The rounded product and its fraction are both zero. Also publish the
 ; canonical fourth residual byte, as the nonzero path does.
 ld a,(hl+)
 add a,a
 sbc a,a
 ld (hl),a
 xor a
 ld hl,#_q24_fraction
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl),a
 ret

phase_product:
 push hl
 ; Each coefficient has 32 byte-product pages. Pages 5..8 contain
 ; the four unbiased bytes of u8*m for the partial motion coefficient.
 ld a,(#_riding_move_index)
 srl a
 ld h,#0x45
 jr nc,phase_map
 ld h,#0x65
phase_map:
 ld l,a
 ld a,(#_q24_first_bank_low)
 add a,l
 ld (#0x2000),a
 ld a,#1
 ld (#0x3000),a
 ld a,d
 or a,e
 jr z,phase_pair_unsigned
 ld a,d
 and a,e
 inc a
 jr z,phase_pair_negative

 ; The low word is unsigned when the upper word contributes separately.
 push de
 ld d,h
 call phase_pair
 pop de
 ld l,e
 ld a,d
 inc a
 ld a,h
 jr z,phase_upper_negative
 sub a,#3
 jr phase_upper_page
phase_upper_negative:
 add a,#3
phase_upper_page:
 ; Page 5 gives e*m, page 11 gives (e-256)*m for a top byte of FF.
 ; Shift this product by 16 and propagate into the existing floor.
 ld h,a
 ldh a,(#_q24_fraction+2)
 add a,(hl)
 ldh (#_q24_fraction+2),a
 inc h
 ld a,c
 adc a,(hl)
 ld c,a
 inc h
 ld a,b
 adc a,(hl)
 ld b,a
 inc h
 ld a,#0
 adc a,(hl)
 ld e,a
 ld a,d
 inc a
 jr z,phase_extend24
 dec a
 jr z,phase_extend24
 ; Signed top byte * m contributes only to the integer result.
 ld l,a
 ld a,h
 add a,#14
 ld h,a
 ld a,c
 add a,(hl)
 ld c,a
 inc h
 ld a,b
 adc a,(hl)
 ld b,a
 inc h
 ld a,e
 adc a,(hl)
 ld e,a
 inc h
 ld a,#0
 adc a,(hl)
 ld d,a
 jr phase_finish
phase_extend24:
 ld a,e
 add a,a
 sbc a,a
 ld d,a
 jr phase_finish

phase_pair_negative:
 ld d,h
 ld a,h
 add a,#6
 ld h,a
 jr phase_narrow
phase_pair_unsigned:
 ld d,h
phase_narrow:
 call phase_pair
 ld a,b
 add a,a
 sbc a,a
 ld e,a
 ld d,a
phase_finish:
 xor a
 ldh (#_q24_saturated),a
 ld (#0x3000),a
 ld a,(#__current_bank)
 ld (#0x2000),a
 ldh a,(#_q24_fraction+2)
 add a,a
 sbc a,a
 ldh (#_q24_fraction+3),a
 pop hl
 ; DEBC is floor(v*m / 2^24). Adding the unsigned product fraction to
 ; (old residual + half) carries exactly one additional position unit.
 push bc
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
 ; Preserve the carry through unbiasing and sign-extending the residual.
 rla
 ld b,a
 ccf
 sbc a,a
 inc hl
 ld (hl-),a
 ld a,b
 rra
 ld (hl),a
 pop bc
 ret nc
 jp phase_increment

phase_pair:
 ; Unbiased product of the lower two digits. For m=691380 the low
 ; digit occupies four bytes and the pair's integer floor fits signed16.
 ld e,c
 ld l,b
 ld a,(de)
 ldh (#_q24_fraction),a
 inc d
 ld a,(de)
 add a,(hl)
 ldh (#_q24_fraction+1),a
 inc d
 inc h
 ld a,(de)
 adc a,(hl)
 ldh (#_q24_fraction+2),a
 inc d
 inc h
 ld a,(de)
 adc a,(hl)
 ld c,a
 inc h
 ld a,#0
 adc a,(hl)
 ld b,a
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
