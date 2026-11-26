; Exact close-compression torque quotient for the production suspension.
; int32_t riding_close_reaction32(int32_t torque, uint32_t distance2)
;     __sdcccall(0);
; Caller has ROM bank 8 selected. Args and return use GBDK stack ABI0;
; return DE=low16, HL=high16. AF/BC/DE/HL clobbered. Reentrant, no globals.
; Mathematical result: clamp_i32(trunc_zero(torque * 4194304 / distance2)).
; distance2==0 returns 0. All other uint32 denominators accepted.
; Six local bytes; temporary words hold the remainder and quotient digit.
.module physics_reaction_division
.area _CODE_8
_riding_close_reaction32::
 add sp,#-6
 ; Sign flag in local byte 4; unsigned magnitude in bytes 0..3.
 ldhl sp,#11
 ld a,(hl)
 and a,#0x80
 ldhl sp,#4
 ld (hl),a
 ldhl sp,#8
 ld c,(hl)
 inc hl
 ld b,(hl)
 inc hl
 ld e,(hl)
 inc hl
 ld d,(hl)
 or a
 jr z,cr_magnitude_ready
 xor a
 sub a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
 ld a,#0
 sbc a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
cr_magnitude_ready:
 ; If N < D the whole-number part is zero and N is already the
 ; remainder. Otherwise only the bottom nine quotient bits can survive
 ; the signed clamp after multiplying by 2^22. Seed with N >> 9 and
 ; feed the remaining nine numerator bits to the original division.
 ldhl sp,#12
 ld a,c
 sub (hl)
 inc hl
 ld a,b
 sbc (hl)
 inc hl
 ld a,e
 sbc (hl)
 inc hl
 ld a,d
 sbc (hl)
 jr nc,cr_integer_needed
 ldhl sp,#0
 xor a
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl),a
 jp cr_fraction_start
cr_integer_needed:
 ; Includes 0/0. A zero denominator retains its public result of zero.
 ldhl sp,#12
 ld a,(hl+)
 or (hl)
 inc hl
 or (hl)
 inc hl
 or (hl)
 jp z,cr_zero
 ldhl sp,#3
 ld a,b
 rrca
 ld a,c
 rra
 ld (hl-),a
 ld a,#0
 rra
 ld (hl-),a
 xor a
 ld (hl-),a
 ld (hl),a
 ld c,b
 ld b,e
 ld e,d
 ld d,#0
 srl e
 rr b
 rr c
 ldhl sp,#12
 ld a,c
 sub (hl)
 inc hl
 ld a,b
 sbc (hl)
 inc hl
 ld a,e
 sbc (hl)
 inc hl
 ld a,#0
 sbc (hl)
 jp nc,cr_saturate
 ldhl sp,#5
 ld (hl),#9
cr_integer_loop:
 ldhl sp,#0
 sla (hl)
 inc hl
 rl (hl)
 inc hl
 rl (hl)
 inc hl
 rl (hl)
 rl c
 rl b
 rl e
 rl d
 call cr_reduce
 ldhl sp,#5
 dec (hl)
 jr nz,cr_integer_loop
cr_fraction_start:
 ; Close wheel separations fit a 23-bit divisor. The remainder then
 ; doubles within 24 bits, and an entire quotient byte fits in A.
 ; Keep the low remainder in HL for native 16-bit addition.
 ldhl sp,#15
 ld a,(hl-)
 or a
 jr nz,cr_fraction_wide
 bit 7,(hl)
 jr nz,cr_fraction_wide
 ; Incoming remainder DEBC. Save its low word while loading -divisor.
 push bc
 ld c,e
 ldhl sp,#14
 xor a
 sub a,(hl)
 ld e,a
 inc hl
 ld a,#0
 sbc a,(hl)
 ld d,a
 inc hl
 ld a,#0
 sbc a,(hl)
 ld b,a
 pop hl
 ld a,#4
 call cr_fraction_byte
 ; Append the first six bits to the integer part in locals 0..1.
 push hl
 ldhl sp,#4
 ld (hl),a
 ldhl sp,#2
 ld a,(hl+)
 rrca
 rrca
 push af
 and a,#0x3f
 bit 0,(hl)
 jr z,cr_no_bit8
 or a,#0x40
cr_no_bit8:
 inc hl
 inc hl
 ld (hl-),a
 pop af
 and a,#0xc0
 or (hl)
 ld (hl),a
 pop hl
 ld a,#1
 call cr_fraction_byte
 push hl
 ldhl sp,#3
 ld (hl),a
 pop hl
 ld a,#1
 call cr_fraction_byte
 ldhl sp,#0
 ld (hl),a
 jr cr_result
cr_fraction_wide:
 ; Emit 22 exact fractional quotient bits, feeding zeros into remainder.
 ldhl sp,#5
 ld (hl),#22
cr_fraction_loop:
 ldhl sp,#0
 sla (hl)
 inc hl
 rl (hl)
 inc hl
 rl (hl)
 inc hl
 rl (hl)
 sla c
 rl b
 rl e
 rl d
 call cr_reduce
 ldhl sp,#5
 dec (hl)
 jr nz,cr_fraction_loop
cr_result:
 ldhl sp,#0
 ld c,(hl)
 inc hl
 ld b,(hl)
 inc hl
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 bit 7,(hl)
 jr z,cr_return_magnitude
 xor a
 sub a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
 ld a,#0
 sbc a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
cr_return_magnitude:
 ld h,d
 ld l,e
 ld d,b
 ld e,c
 add sp,#6
 ret
cr_zero:
 ld de,#0
 ld hl,#0
 add sp,#6
 ret
cr_saturate:
 ldhl sp,#4
 bit 7,(hl)
 ld de,#0xffff
 ld hl,#0x7fff
 jr z,cr_saturated_return
 ld de,#0
 ld hl,#0x8000
cr_saturated_return:
 add sp,#6
 ret
; B:DE = -divisor modulo 2^24, C:HL = remainder. A contains
; a sentinel followed by the quotient bits emitted so far. The carry
; from the trial addition means the shifted remainder reached divisor.
cr_fraction_byte:
 push af
 add hl,hl
 rl c
 push hl
 add hl,de
 ld a,c
 adc a,b
 jr c,cr_byte_one
 pop hl
 pop af
 add a,a
 jr nc,cr_fraction_byte
 ret
cr_byte_one:
 ld c,a
 inc sp
 inc sp
 pop af
 scf
 rla
 jr nc,cr_fraction_byte
 ret

; DEBC = 32-bit remainder after shifting; carry is its 33rd bit.
; Incoming remainder before shifting was < divisor. Therefore one
; subtraction suffices, even when the 33rd bit is set. A borrow in that
; case consumes the implicit high bit and the low 32 bits are exact.
cr_reduce:
 jr c,cr_subtract
 ldhl sp,#14
 ld a,c
 sub a,(hl)
 inc hl
 ld a,b
 sbc a,(hl)
 inc hl
 ld a,e
 sbc a,(hl)
 inc hl
 ld a,d
 sbc a,(hl)
 ret c
cr_subtract:
 ldhl sp,#14
 ld a,c
 sub a,(hl)
 ld c,a
 inc hl
 ld a,b
 sbc a,(hl)
 ld b,a
 inc hl
 ld a,e
 sbc a,(hl)
 ld e,a
 inc hl
 ld a,d
 sbc a,(hl)
 ld d,a
 ldhl sp,#2
 inc (hl)
 ret
_riding_close_reaction32_end::
