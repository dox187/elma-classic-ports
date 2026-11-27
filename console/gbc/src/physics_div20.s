; Signed floor division for the suspension force accumulator. Divide the
; complemented magnitude a byte at a time, then restore its original sign.
; For each byte, q,r = divmod(previous_remainder*256 + byte,20).
.module div20
.area _CODE

.macro div20_digit byte
 ld h,a
 ld a,byte
 add a,#<div20_q
 ld l,a
 ld a,h
 adc a,#>div20_q
 ld h,a
 ld a,(hl)
 ld byte,a
.endm
.macro div20_next byte
 div20_digit byte
 ld a,h
 add a,#20
 ld h,a
 ld a,(hl)
.endm

_riding_floor_div20::
 ldhl sp,#2
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ld a,b
 add a,a
 sbc a,a
 ; A:BCDE is a signed40 numerator. Return its signed quotient modulo
 ; 2^32 in HLDE and the Euclidean remainder (0..19) in A.
_riding_force_divmod20::
 push af
 bit 7,a
 jr z,div20_positive
 cpl
 ld h,a
 ld a,b
 cpl
 ld b,a
 ld a,c
 cpl
 ld c,a
 ld a,d
 cpl
 ld d,a
 ld a,e
 cpl
 ld e,a
 ld a,h
div20_positive:
 ld h,a
 ld a,#15
 ld (#0x2000),a
 ld a,h
 or a
 jr z,div20_narrow
 ; The highest quotient digit is above bit 31. Its remainder still
 ; contributes to every lower quotient digit.
 add a,#<div20_r
 ld l,a
 ld a,#>div20_r
 adc a,#0
 ld h,a
 ld a,(hl)
 jr div20_four
div20_narrow:
 cp b
 jr nz,div20_four
 cp c
 jr nz,div20_three
 cp d
 jr nz,div20_two
 jr div20_last
div20_four:
 div20_next b
div20_three:
 div20_next c
div20_two:
 div20_next d
div20_last:
 div20_next e
 ld h,a
 ldh a,(#__current_bank)
 ld (#0x2000),a
 pop af
 bit 7,a
 ld a,h
 ld h,b
 ld l,c
 ret z
 ; For negative X use X = -1 - ~X. Its quotient is ~q and
 ; its Euclidean remainder is 19 - r.
 ld b,a
 ld a,h
 cpl
 ld h,a
 ld a,l
 cpl
 ld l,a
 ld a,d
 cpl
 ld d,a
 ld a,e
 cpl
 ld e,a
 ld a,#19
 sub a,b
 ret

.area _CODE_15
div20_q:
value = 0
.rept 5120
 .db value / 20
 value = value + 1
.endm
; Exactly 20 pages after div20_q, including when the table is unaligned.
div20_r:
value = 0
.rept 5120
 .db value % 20
 value = value + 1
.endm
