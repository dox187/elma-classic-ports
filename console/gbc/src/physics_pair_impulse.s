.module physics_pair_impulse
.area _CODE_93
; dot(impulse,normal) rounds to a positive number when the unscaled sum
; is at least 8192. Bound each product before paying for a wide dot. Each
; integer interval is in quarter bits: 2^(lo/4) <= magnitude <= 2^(hi/4).
; Distant magnitudes certify mixed signs, including with full-width forces.
_riding_pair_impulse_bound::
 ld hl,#_riding_pair_impulse
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 inc hl
 inc hl
 inc hl
 push hl
 ld a,(#_riding_pair_normal)
 ld e,a
 ld a,(#_riding_pair_normal+1)
 ld d,a
 inc de
 push de
 ; A nonnegative product of two magnitudes >=256 already exceeds
 ; 8192. If the other term has a nonnegative sign too, the impulse is
 ; outward regardless of their lower digits.
 ld a,(de)
 xor (hl)
 bit 7,a
 jr nz,pair_ranges
 ld a,(de)
 inc a
 cp #2
 jr c,pair_ranges        ; signed normal may be only one byte
 ld a,(hl-)
 add a
 sbc a
 xor (hl)
 jr nz,pair_test_second_sign
 ld a,(hl-)
 xor (hl)
 jr z,pair_ranges
pair_test_second_sign:
 pop de
 pop hl
 inc hl
 inc hl
 inc hl
 inc hl
 inc de
 inc de
 ld a,(de)
 xor (hl)
 bit 7,a
 jp z,pair_bounded_out
 dec hl
 dec hl
 dec hl
 dec hl
 dec de
 dec de
 push hl
 push de
pair_ranges:
 pop de
 pop hl
 push hl
 push de
 call pair_product_range
 pop de
 inc de
 inc de
 pop hl
 inc hl
 inc hl
 inc hl
 inc hl
 push af
 push bc
 call pair_product_range
 ld d,a
 ld e,b
 ld h,c                   ; second: upper D, lower E, sign H
 pop bc                   ; first: lower B, sign C
 pop af                   ; first: upper A
 bit 0,c
 jr nz,pair_second_only
 bit 0,h
 jr nz,pair_first_only
 ld l,a
 ld a,c
 xor h
 bit 7,a
 jr z,pair_both_positive  ; both-negative already accepted in bank 9
 bit 7,c
 jr nz,pair_mixed
 ; Exchange the bounds so BC belongs to the negative term and DE
 ; to the positive term. C and D will hold their upper bounds.
 ld c,d
 ld d,l
 ld a,b
 ld b,e
 ld e,a
 jr pair_compare_range
pair_mixed:
 ld c,l
pair_compare_range:
 ld a,b
 cp d
 jr nc,pair_bounded_in    ; negative minimum >= positive maximum
 ld a,e
 cp #56
 jr c,pair_unbounded
 sub c
 jr c,pair_unbounded
 cp #4
 jr nc,pair_bounded_out   ; negative <= positive/2, positive >= 16384
 ; A half-bit gap certifies at least (1 - 1/sqrt(2))*32768.
 cp #2
 jr c,pair_unbounded
 ld a,e
 cp #60
 jr nc,pair_bounded_out
 jr pair_unbounded
pair_second_only:
 bit 0,h
 jr nz,pair_bounded_in
 bit 7,h
 jr nz,pair_bounded_in
 ld b,e
 jr pair_single_positive
pair_first_only:
 bit 7,c
 jr nz,pair_bounded_in
pair_single_positive:
 ld a,b
 cp #52
 jr nc,pair_bounded_out
 jr pair_unbounded
pair_both_positive:
 ld a,b
 cp #52
 jr nc,pair_bounded_out
 ld a,e
 cp #52
 jr nc,pair_bounded_out
pair_unbounded:
 ld hl,#_riding_pair_impulse
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 ld hl,#_riding_pair_normal
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call _riding_dotq14_regs
 bit 7,h
 jr nz,pair_bounded_in
 ld a,h
 or l
 or d
 or e
 jr z,pair_bounded_in
pair_bounded_out:
 xor a
 ret
pair_bounded_in:
 ld a,#1
 ret

; HL points at the signed32 force's top byte, DE at the normal's top byte.
; Return B=lower, A=upper, C=0 positive, 128 negative, 1 exact zero.
pair_product_range:
 push de
 ld d,#4
 call pair_magnitude_range
 pop hl
 bit 0,c
 ret nz
 push af
 push bc
 ld d,#2
 call pair_magnitude_range
 ld d,a
 ld e,b
 pop hl
 pop af
 bit 0,c
 ret nz
 add d
 ld d,a
 ld a,h
 add e
 ld b,a
 ld a,l
 xor c
 ld c,a
 ld a,d
 ret

; Complementing negative digits gives |v|-1, including INT32_MIN.
; For a first nonzero digit n followed by k bytes, |v| lies between
; n*256^k and (n+1)*256^k inclusively. The table packs the lower bound
; in five bits and the difference to the upper bound in the upper three.
pair_magnitude_range:
 ld a,(hl)
 add a
 sbc a
 ld c,a
pair_magnitude_digit:
 ld a,(hl-)
 xor c
 jr nz,pair_magnitude_found
 dec d
 jr nz,pair_magnitude_digit
 ld b,d
 ld a,c
 or a
 jr z,pair_magnitude_zero
 ld c,#128                ; -1, with both log bounds equal to zero
 xor a
 ret
pair_magnitude_zero:
 inc c
 ret
pair_magnitude_found:
 ld e,a
 ld a,c
 and #128
 ld c,a
 ld a,d
 dec a
 rrca
 rrca
 rrca
 ld b,a
 ld d,#0
 ld hl,#pair_log_bounds
 add hl,de
 ld a,(hl)
 and #31
 or b
 ld b,a
 ld a,(hl)
 rlca
 rlca
 rlca
 and #7
 add b
 ret

; For n=1..255, lo = bit_length(n^4)-1 and hi = bit_length((n+1)^4-1).
; Entry = lo | (hi-lo)<<5. Digit zero is handled above.
pair_log_bounds:
 .db 0,128,100,70,72,73,74,43,44,76,45,77,46,78,47,47
 .db 48,48,48,80,49,49,81,50,50,50,82,51,51,51,51,51
 .db 52,52,52,52,52,52,84,53,53,53,53,53,53,85,54,54
 .db 54,54,54,54,54,86,55,55,55,55,55,55,55,55,55,55
 .db 56,56,56,56,56,56,56,56,56,56,56,56,88,57,57,57
 .db 57,57,57,57,57,57,57,57,57,57,89,58,58,58,58,58
 .db 58,58,58,58,58,58,58,58,58,58,58,90,59,59,59,59
 .db 59,59,59,59,59,59,59,59,59,59,59,59,59,59,59,59
 .db 60,60,60,60,60,60,60,60,60,60,60,60,60,60,60,60
 .db 60,60,60,60,60,60,60,60,92,61,61,61,61,61,61,61
 .db 61,61,61,61,61,61,61,61,61,61,61,61,61,61,61,61
 .db 61,61,61,61,61,93,62,62,62,62,62,62,62,62,62,62
 .db 62,62,62,62,62,62,62,62,62,62,62,62,62,62,62,62
 .db 62,62,62,62,62,62,62,94,63,63,63,63,63,63,63,63
 .db 63,63,63,63,63,63,63,63,63,63,63,63,63,63,63,63
 .db 63,63,63,63,63,63,63,63,63,63,63,63,63,63,63,63
