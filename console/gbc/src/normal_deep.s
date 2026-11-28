.module normal_deep
 .ifdef RIDING_DEEP_ROWS
.area _CODE_27
normal_fraction_bank = 27
 .else
.area _CODE_33
normal_fraction_bank = 33
 .endif
.globl normal_fraction_bank
; Deep physical vectors have 0 <= abs(axis) <= floor(sqrt(d2)) <= 127.
; At that size each fractional quotient digit needs one byte of remainder.
; Keep the full signed solver for callers supplying a nonphysical d2.
normal_fraction::
 ; The caller has already classified d2 as negative or below 16384.
 ; An arbitrary negative key still needs the original wide kernel.
 ld a,(#normal_cache_key+7)
 bit 7,a
 jr nz,normal_fraction_miss
 ld hl,#normal_cache_key+4
 ld a,(hl+)
 ld e,a
 ld c,(hl)
 call _riding_isqrt14_regs
 ld a,e
 ld c,a
 or a
 jr z,normal_fraction_zero
 .ifdef RIDING_DEEP_ROWS
 ; Both components use the same row of half-fractions.
 add a
 ld l,a
 ld h,#>normal_fraction_rows
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 .endif
 ld hl,#normal_cache_key
 call normal_fraction_axis
 or a
 ret z
 push hl
 ld hl,#normal_cache_key+2
 call normal_fraction_axis
 pop de
 or a
 ret z
normal_fraction_store:
 ld a,l
 ld (#normal_cache_value+2),a
 ld a,h
 ld (#normal_cache_value+3),a
 ld hl,#normal_cache_value
 ld a,e
 ld (hl+),a
 ld (hl),d
 ld a,c
 ld (#normal_cache_value+4),a
 xor a
 ld (#normal_cache_value+5),a
 ld a,#1
 ld (#normal_cache_valid),a
 ret
normal_fraction_zero:
 ld de,#0
 ld hl,#16384
 jr normal_fraction_store
normal_fraction_miss:
 xor a
 ret

normal_fraction_axis:
 .ifdef RIDING_DEEP_ROWS
 ; For high byte 0 or FF, (lo XOR high) - high gives abs(axis).
 ; The borrow also validates its high byte: only a positive byte or a
 ; negative with nonzero low byte makes high + borrow wrap to zero.
 ld a,(hl+)
 ld b,(hl)
 xor b
 sub b
 ld l,a
 ld a,b
 adc #0
 jr nz,normal_fraction_miss
 sla b                          ; retain sign, clear the mirror flag
deep_magnitude:
 ld a,c
 sub l
 jr c,normal_fraction_miss
 jr z,deep_full
 cp l
 jr nc,deep_lower
 ld l,a
 inc b
deep_lower:
 ld a,l
 add a
 add e
 ld l,a
 ld h,d
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ; Each word is 2*floor(16384*n/d) plus one if its fraction is nonzero.
 ; Taking the upper half of (32768 - word) thus gives the complementary
 ; quotient even when the positive quotient was exactly integral.
 bit 0,b
 jr z,deep_half
 xor a
 sub l
 ld l,a
 ld a,#128
 sbc h
 ld h,a
deep_half:
 srl h
 rr l
 jr normal_fraction_sign
deep_full:
 ld hl,#16384
 jr normal_fraction_sign
 .else
 ld a,(hl+)
 ld e,a
 ld a,(hl)
 ld b,a
 or a
 jr z,normal_fraction_unsigned
 inc a
 jr nz,normal_fraction_miss
 xor a
 sub e
 jr z,normal_fraction_miss      ; -256, outside the narrow domain
 ld e,a
normal_fraction_unsigned:
 ld a,c
 sub e
 jr c,normal_fraction_miss
 ld hl,#16384
 jr z,normal_fraction_sign
 ld hl,#0
 ld a,e
 ; After each digit, 0 <= remainder < C. Hence doubling also fits A.
 .macro normal_fraction_bit byte,digit,?next
 add a
 cp c
 jr c,next
 sub c
 set digit,byte
next:
 .endm
 .irp digit,5,4,3,2,1,0
 normal_fraction_bit h,digit
 .endm
 .irp digit,7,6,5,4,3,2,1,0
 normal_fraction_bit l,digit
 .endm
 .endif
normal_fraction_sign:
 bit 7,b
 jr z,normal_fraction_done
 xor a
 sub l
 ld l,a
 sbc a,a
 sub h
 ld h,a
normal_fraction_done:
 ld a,#1
 ret
