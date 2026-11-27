.macro normal_pick_digit
 ld e,a
 ld a,(hl)
 bit 6,e
 jr z,10$
 swap a
10$:
 bit 5,e
 jr z,11$
 rrca
 rrca
11$:
 and #3
 jr z,13$
 ld e,a
 xor c
 and #3
 ld a,#2
 jr nz,12$
 ld a,#64
12$:
 ld (#normal_length_tag),a
 ld a,e
 add b
 dec a
13$:
 ld c,a
 ret
.endm

.ifdef NORMAL_INNER_LENGTHS
.area _CODE_93
; The inner directory covers squared distances 32768..65535. In these
; bins the low bit of the middle byte selects an eight-digit pattern half.
normal_read_inner::
 ld a,(#normal_cache_key+5)
 ld c,a
 and #254
 ld e,a
 ld d,#0
 ld hl,#(normal_inner_rows-128)
 add hl,de
 ld a,(hl+)
 ld b,a
 ld a,(hl)
 ld e,a
 and #252
 rrca
 rr c
 adc #0
 ld c,e
 ld e,a
 ld hl,#normal_inner_patterns
 add hl,de
 ld a,(#normal_cache_key+4)
 rrca                       ; bits 6 and 7 now occupy bits 5 and 6
 normal_pick_digit

.else
.area _CODE_5
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
 ; The row holds the four-byte-aligned offset and the round-trip code.
 ld e,(hl)
 ld a,(#normal_cache_key+4)
 ld d,a
 rlca
 ld a,c
 rla                        ; low two bits select a byte of the pattern
 xor e
 and #3
 xor e
 ld c,e                     ; keep the row's round-trip code
 ld e,a
 ld a,d                     ; bits 5 and 6 select a two-bit result
 ld d,#0
 ld hl,#normal_length_patterns
 add hl,de
 normal_pick_digit
.endif
