; The macros of the multiplications with the tables of quarter squares of
; mul.s, for mul.s and physics.S.

; Sets the multiplicand of the following MUL8s to A:
.macro SETA
	sta mp_lo1
	sta mp_hi1
	eor #$ff
	sta mp_lo2
	sta mp_hi2
.endm

; Unsigned product of the multiplicand and Y into lo, hi:
.macro MUL8 lo, hi
	sec
	MUL8C \lo, \hi
.endm

; The same with the carry set already: it stays set after it, as the
; product is not negative.
.macro MUL8C lo, hi
	lda (mp_lo1),y
	sbc (mp_lo2),y
	sta \lo
	lda (mp_hi1),y
	sbc (mp_hi2),y
	sta \hi
.endm
