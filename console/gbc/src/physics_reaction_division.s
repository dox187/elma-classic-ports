; Exact close-compression torque quotient for the production suspension.
; int32_t riding_close_reaction32(int32_t torque, uint32_t distance2)
;     __sdcccall(0);
; Caller has ROM bank 8 selected. Args and return use GBDK stack ABI0;
; return DE=low16, HL=high16. AF/BC/DE/HL clobbered. Reentrant, no globals.
; Mathematical result: clamp_i32(trunc_zero(torque * 4194304 / distance2)).
; distance2==0 returns 0. All other uint32 denominators accepted.
; Six local bytes plus two bytes for the internal call; no ROM0 code.
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
 jr cr_fraction_start
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
