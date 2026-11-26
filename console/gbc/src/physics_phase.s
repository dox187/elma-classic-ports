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
 call _riding_phase_carry_hl
 ret nc
 jr phase_increment

; Native position updates can consume the rounding carry in their first ADC.
_riding_phase_carry_hl::
 ld a,(#_riding_subphase)
 or a,a
 jp nz,_riding_phase_second_carry
 ; A full substep adds only the low velocity nibble at bit 20.
 ; Bias the signed residual by half a unit: the byte addition's carry
 ; is exactly the extra position unit, and its low 16 bits stay intact.
 ld a,(hl)
 xor a,#0x80
 ld (hl),a
 ld a,c
 swap a
 and a,#0xf0
 add a,(hl)
 push af
 xor a,#0x80
 ld (hl+),a
 rlca
 sbc a,a
 ld (hl),a
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
 ; An upper word of 0000 or FFFF already equals its arithmetic shift.
 ld a,e
 xor d
 jr nz,phase_shift_upper
 ld a,d
 inc a
 cp #2
 jr c,phase_shift_carry
phase_shift_upper:
 shift_four e,d
 ld a,d
 add a,a
 sbc a,a
 xor a,d
 and a,#0x0f
 xor a,d
 swap a
 ld d,a
phase_shift_carry:
 pop af
 ret
phase_increment:
 inc bc
 ld a,b
 or a,c
 ret nz
 inc de
 ret

_riding_phase_second_hl::
phase_second:
 call _riding_phase_second_carry
 ret nc
 jp phase_increment

; Return the integer floor in DEBC and the extra position unit in carry.
; Circle movement adds this carry directly into the low position byte.
.ifdef RIDING_PHASE_TABLES
; Both digit layouts produce a signed16 floor in DE and the 24-bit
; fraction in BC and q24_fraction+2. A full signed32 miss keeps DEBC
; intact for the original wide multiply. D already sign-extends every
; direct row's signed8 quotient.
 .macro phase_lookup publish,?phase_negative,?phase_positive_wide,?phase_negative_wide,?phase_page,?phase_words,?phase_direct,?phase_ready
 push hl
 ; Positive and negative high words use different canonical top bytes.
 ; The common 0000 and FFFF words can select their planes immediately.
 ld a,d
 inc a
 jr z,phase_negative
 dec a
 jp nz,phase_product_saved
 ld a,e
 or a
 jr nz,phase_positive_wide
 ld a,b
 cp #8
 jr c,phase_direct
 ld a,#0x40
 jr phase_words
phase_negative:
 ld a,e
 inc a
 jr nz,phase_negative_wide
 ld a,b
 cp #0xf8
 jr nc,phase_direct
 ld a,#0x7c
 jr phase_words
phase_positive_wide:
 cp #7
 jp nc,phase_product_saved
 jr phase_page
phase_negative_wide:
 dec a
 cp #0xf8
 jp c,phase_product_saved
 and #15
phase_page:
 add a,a
 add a,a
 or #0x40
phase_words:
 ld h,a
 ld l,b
 ld e,c
 ld d,#0x5c
 ld a,#32
 ld (#0x2000),a
 ld a,(de)
 ld c,a
 inc d
 ld a,(de)
 add (hl)
 ld b,a
 inc d
 inc h
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
 jr phase_ready

phase_direct:
 ; Signed12 velocity selects the four consecutive byte planes of a
 ; complete product. Its integer floor fits signed8 throughout.
 ld a,b
 and #15
 add a,a
 add a,a
 or #0x40
 ld h,a
 ld l,c
 ld a,#33
 ld (#0x2000),a
 ld c,(hl)
 inc h
 ld b,(hl)
 inc h
 ld a,(hl)
 inc h
 ld e,(hl)
 ldh (#_q24_fraction+2),a
phase_ready:
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
 ld a,(#__current_bank)
 ld (#0x2000),a
 .endif
 .endm

_riding_phase_second_carry::
 phase_lookup 1
 jr phase_residual_word

; The first circle axis has no observer before the second axis replaces
; all five published Q24 bytes and restores the caller's ROM bank.
_riding_phase_second_x::
 phase_lookup 0
phase_residual_word:
 pop hl
 ld a,(hl)
 xor #0x80
 ld (hl),a
 dec hl
 dec hl
 ld a,c
 add (hl)
 ld (hl+),a
 ld a,b
 adc (hl)
 ld (hl+),a
 ldh a,(#_q24_fraction+2)
 adc (hl)
 ; Unbias the signed residual, preserving the extra position unit.
 rla
 ld c,a
 ccf
 sbc a,a
 inc hl
 ld (hl-),a
 ld a,c
 rra
 ld (hl),a
 ld b,d
 ld c,e
 bit 7,d
 ld de,#0
 ret z
 dec de
 ret

.else
_riding_phase_second_carry::
_riding_phase_second_x::
.endif
 ld a,d
 or a,e
 or a,b
 or a,c
 jr nz,phase_product
phase_zero:
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
phase_product_saved:
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
 ret

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
 pop hl
 inc sp
 push hl
_riding_angle_regs::
 ld a,(#_riding_subphase)
 or a,a
 jr z,angle_first
 ld a,(#_riding_angle_index)
 dec sp
 call _q24_apply_a
 ret
angle_first:
 ; The upper bytes cross a three-bit boundary. The lower word wraps
 ; directly on the SM83's 16-bit add, including signed32 extremes.
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
 ld h,b
 ld l,c
 .rept 5
 add hl,hl
 .endm
 ld b,h
 ld c,l
 ret
