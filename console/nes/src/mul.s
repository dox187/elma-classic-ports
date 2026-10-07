; Fast multiplication for the physics, with tables of quarter squares:
; a*b = f(a+b) - f(|a-b|), f(n) = floor(n*n/4).
;
; The pointers below point into the tables offset by the multiplicand, so
; that indexing them with the multiplier gives the two quarter squares.
;
; The routines z... take their operands in m_a, m_b (and m_c, m_d) and
; return in A (low) and X (high); they are for the assembly of the
; physics. The C functions of fixmath.h wrap them.

.section .zp.data,"aw",@progbits
mp_lo1: .short sqr_lo
mp_hi1: .short sqr_hi
mp_lo2: .short nsq_lo
mp_hi2: .short nsq_hi

.section .zp.bss,"aw",@nobits
.globl m_a, m_b, m_c, m_d, m_p, m_q, m_t, mp_lo1, mp_hi1, mp_lo2, mp_hi2, sqr_lo, sqr_hi
m_a: .zero 2
m_b: .zero 2
m_c: .zero 2
m_d: .zero 2
m_p: .zero 4
m_q: .zero 4
m_t: .zero 4

.include "mul.inc"

.section .text.smul,"ax",@progbits
; Signed product of m_a and m_b into m_p[0..3]; A, X and Y are lost. With
; one of them from -256 to 255, or b +-16384 (a direction along an axis),
; it takes a shorter way to the same product.
.globl smul
smul:
	lda m_b+1
	beq smul_b8
	cmp #$ff
	beq smul_bn8
	lda m_a+1
	beq 1f
	cmp #$ff
	bne 2f
1:
	; a is the short one: swap them.
	ldx m_a
	ldy m_a+1
	lda m_b
	sta m_a
	lda m_b+1
	sta m_a+1
	stx m_b
	sty m_b+1
	tya
	beq smul_b8
	bne smul_bn8
2:
	lda m_b
	bne 3f
	lda m_b+1
	cmp #$40
	bne 4f
	jmp smul_axis
4:
	cmp #$c0
	bne 3f
	jmp smul_naxis
3:
	jmp smul16

; m_p = a*b for 0 <= b < 256: of a taken unsigned, less b << 16 if a < 0.
smul_b8:
	lda m_b
	SETA
	sec
	ldy m_a
	MUL8C m_p, m_p+1
	ldy m_a+1
	MUL8C m_t, m_p+2
	ldx #0
	clc
	lda m_p+1
	adc m_t
	sta m_p+1
	bcc 1f
	inc m_p+2
	bne 1f
	inx
1:
	bit m_a+1
	bpl 2f
	sec
	lda m_p+2
	sbc m_b
	sta m_p+2
	txa
	sbc #0
	tax
2:
	stx m_p+3
	rts

; m_p = a*b for -256 <= b < 0: a*(b+256) - (a << 8).
smul_bn8:
	jsr smul_b8
	ldx #0
	lda m_a+1
	bpl 1f
	dex
1:
	stx m_t+3
	sec
	lda m_p+1
	sbc m_a
	sta m_p+1
	lda m_p+2
	sbc m_a+1
	sta m_p+2
	lda m_p+3
	sbc m_t+3
	sta m_p+3
	rts

; m_p = a << 14, for b = 16384, and its negative for b = -16384.
smul_axis:
	lda #0
	sta m_p
	sta m_p+1
	lda m_a
	sta m_p+2
	lda m_a+1
	cmp #$80
	ror a
	ror m_p+2
	ror m_p+1
	cmp #$80
	ror a
	ror m_p+2
	ror m_p+1
	sta m_p+3
	rts

smul_naxis:
	jsr smul_axis
	sec
	ldx #0
	.irp i, 0, 1, 2, 3
	txa
	sbc m_p+\i
	sta m_p+\i
	.endr
	rts

smul16:
	lda m_a
	SETA
	sec
	ldy m_b
	MUL8C m_p, m_p+1
	ldy m_b+1
	MUL8C m_t, m_t+1
	lda m_a+1
	SETA
	ldy m_b
	MUL8C m_t+2, m_t+3
	ldy m_b+1
	MUL8C m_p+2, m_p+3
	; The middle products, at byte 1:
	clc
	lda m_p+1
	adc m_t
	sta m_p+1
	lda m_p+2
	adc m_t+1
	bcc 1f
	inc m_p+3
	clc
1:
	tax
	lda m_p+1
	adc m_t+2
	sta m_p+1
	txa
	adc m_t+3
	sta m_p+2
	bcc 2f
	inc m_p+3
2:
	; Signed: subtract b<<16 if a < 0 and a<<16 if b < 0.
	bit m_a+1
	bpl 3f
	sec
	lda m_p+2
	sbc m_b
	sta m_p+2
	lda m_p+3
	sbc m_b+1
	sta m_p+3
3:
	bit m_b+1
	bpl 4f
	sec
	lda m_p+2
	sbc m_a
	sta m_p+2
	lda m_p+3
	sbc m_a+1
	sta m_p+3
4:
	rts

; m_a (signed) times A (unsigned 8 bits) into m_p[0..2].
.section .text.smul8,"ax",@progbits
.globl smul8
smul8:
	sta m_t+2
	SETA
	ldy m_a
	MUL8 m_p, m_p+1
	ldy m_a+1
	MUL8 m_t, m_p+2
	clc
	lda m_p+1
	adc m_t
	sta m_p+1
	bcc 1f
	inc m_p+2
1:
	bit m_a+1
	bpl 2f
	sec
	lda m_p+2
	sbc m_t+2
	sta m_p+2
2:
	rts

; m_a*m_b + m_c*m_d into m_p.
.section .text.sdot,"ax",@progbits
.globl sdot
sdot:
	jsr smul
	lda m_p
	sta m_q
	lda m_p+1
	sta m_q+1
	lda m_p+2
	sta m_q+2
	lda m_p+3
	sta m_q+3
	lda m_c
	sta m_a
	lda m_c+1
	sta m_a+1
	lda m_d
	sta m_b
	lda m_d+1
	sta m_b+1
	jsr smul
	clc
	lda m_p
	adc m_q
	sta m_p
	lda m_p+1
	adc m_q+1
	sta m_p+1
	lda m_p+2
	adc m_q+2
	sta m_p+2
	lda m_p+3
	adc m_q+3
	sta m_p+3
	rts

; Bits 16..31 of m_p rounded, into A:X.
.section .text.zhi,"ax",@progbits
.globl zmulhi, phi
zmulhi:
	jsr smul
phi:
	lda m_p+1
	cmp #$80
	lda m_p+2
	adc #0
	tay
	lda m_p+3
	adc #0
	tax
	tya
	rts

; m_p >> 14 rounded and saturated, into A:X.
.section .text.zq14,"ax",@progbits
.globl zmulq14, zdotq14, pq14, smul
zdotq14:
	jsr sdot
	jmp pq14
zmulq14:
	jsr smul
pq14:
	clc
	lda m_p+1
	adc #$20
	sta m_p+1
	bcc 1f
	inc m_p+2
	bne 1f
	inc m_p+3
1:
	; Bits 29..31 must all be the sign:
	lda m_p+3
	and #$e0
	beq 2f
	cmp #$e0
	beq 2f
	jmp saturate
2:
	lda m_p+1
	asl a
	rol m_p+2
	rol m_p+3
	asl a
	rol m_p+2
	rol m_p+3
	lda m_p+2
	ldx m_p+3
	rts

; The largest number of the sign of m_p, into A:X.
saturate:
	lda m_p+3
	bmi 3f
	lda #$ff
	ldx #$7f
	rts
3:
	lda #0
	ldx #$80
	rts

; m_p >> 10 rounded and saturated, into A:X.
.section .text.zq10,"ax",@progbits
.globl zmulq10, pq10
zmulq10:
	jsr smul
pq10:
	clc
	lda m_p+1
	adc #$02
	sta m_p+1
	bcc 1f
	inc m_p+2
	bne 1f
	inc m_p+3
1:
	; Bits 25..31 must all be the sign:
	lda m_p+3
	and #$fe
	beq 2f
	cmp #$fe
	beq 2f
	jmp saturate
2:
	lsr m_p+3
	ror m_p+2
	ror m_p+1
	lsr m_p+3
	ror m_p+2
	ror m_p+1
	lda m_p+1
	ldx m_p+2
	rts

; --- The functions of fixmath.h for C ---------------------------------

; Takes a in A:X and b in __rc2:__rc3 into m_a and m_b.
.macro ARGS2
	sta m_a
	stx m_a+1
	lda __rc2
	sta m_b
	lda __rc3
	sta m_b+1
.endm

; int32_t mul16( int16_t a, int16_t b ): the product in A:X:__rc2:__rc3.
.section .text.mul16,"ax",@progbits
.globl mul16
mul16:
	ARGS2
	jsr smul
	lda m_p+2
	sta __rc2
	lda m_p+3
	sta __rc3
	lda m_p
	ldx m_p+1
	rts

; int16_t mulhi( int16_t a, int16_t b ): (a*b + 0x8000) >> 16.
.section .text.mulhi,"ax",@progbits
.globl mulhi
mulhi:
	ARGS2
	jmp zmulhi

; int16_t mulq14( int16_t a, int16_t b ): (a*b + 0x2000) >> 14, saturated.
.section .text.mulq14,"ax",@progbits
.globl mulq14
mulq14:
	ARGS2
	jmp zmulq14

; int16_t mulq10( int16_t a, int16_t b ): (a*b + 0x200) >> 10, saturated.
.section .text.mulq10,"ax",@progbits
.globl mulq10
mulq10:
	ARGS2
	jmp zmulq10

; int16_t dotq14( int16_t ax, int16_t ay, int16_t bx, int16_t by ):
; ax in A:X, ay in __rc2:__rc3, bx in __rc4:__rc5, by in __rc6:__rc7.
.section .text.dotq14,"ax",@progbits
.globl dotq14
dotq14:
	sta m_a
	stx m_a+1
	lda __rc4
	sta m_b
	lda __rc5
	sta m_b+1
	lda __rc2
	sta m_c
	lda __rc3
	sta m_c+1
	lda __rc6
	sta m_d
	lda __rc7
	sta m_d+1
	jmp zdotq14

.section .rodata.mul_tables,"a",@progbits
.p2align 8
sqr_lo:
	.set n, 0
	.rept 512
	.byte ((n*n)/4) & 255
	.set n, n+1
	.endr
sqr_hi:
	.set n, 0
	.rept 512
	.byte ((n*n)/4) >> 8
	.set n, n+1
	.endr
nsq_lo:
	.set n, 0
	.rept 512
	.byte (((n-255)*(n-255))/4) & 255
	.set n, n+1
	.endr
nsq_hi:
	.set n, 0
	.rept 512
	.byte (((n-255)*(n-255))/4) >> 8
	.set n, n+1
	.endr
