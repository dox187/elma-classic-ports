; In each reciprocal bin of 512 squared units, 16 slots share a pattern
; of two-bit results. Zero requests the full dot. The other codes select
; the bin's base length or either of the next two integers.
normal_read_lower::
 ld d,#0
 jr normal_read_row
normal_read_upper::
 ld d,#1
normal_read_row:
 ld a,(#normal_cache_key+5)
 ld c,a
 and #254
 ld e,a
 ld hl,#normal_length_rows
 add hl,de
 ld a,(hl+)
 ld b,a
 ld l,(hl)
 ld h,#0
 add hl,hl
 add hl,hl
 ld de,#normal_length_patterns
 add hl,de
 ; C = (squared >> 5) & 15, including the top bit from byte one.
 rr c
 ld a,(#normal_cache_key+4)
 rra
 swap a
 and #15
 ld c,a
 srl a
 srl a
 ld e,a
 ld d,#0
 add hl,de
 ld a,(hl)
 bit 1,c
 jr z,normal_length_half
 swap a
normal_length_half:
 bit 0,c
 jr z,normal_length_digit
 rrca
 rrca
normal_length_digit:
 and #3
 ld c,a
 ret z
 add b
 dec a
 ld c,a
 ret
