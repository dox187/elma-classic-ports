; Multiplications of the game loop (game.c) with the multiplier of the CPU,
; much faster than the 32-bit arithmetic of the compiler.

.include "hdr.asm"
.include "core.inc"

.SECTION ".game_math_text" SUPERFREE

; u16 game_mulhi(u16 a, u16 b): (a*b) >> 16, unsigned.
game_mulhi:
	php
	phb
	rep #$30
	sep #$20
	lda #$80
	pha
	plb
	rep #$20
	lda 6,s
	tax
	lda 8,s
	tay
	jsr _mul16
	plb
	plp
	rtl

; u16 game_px(u32 d): level pixels of a distance d in 16.16 meters,
; ((d >> 8) * 4915) >> 16 (levels.h PX_PER_M_NUM), for 0 <= d < 2^24.
game_px:
	php
	phb
	rep #$30
	sep #$20
	lda #$80
	pha
	plb
	rep #$20
	lda 7,s                     ; bits 8-23 of d
	tax
	ldy #4915
	jsr _mul16
	plb
	plp
	rtl

; The high word of X*Y (16x16 unsigned) in tcc__r0, with DB $80: four
; products of 8 bits.
_mul16:
	stx Gm_a
	sty Gm_b
	sep #$20
	lda Gm_a                    ; al*bh
	sta $4202
	lda Gm_b+1
	sta $4203
	nop
	nop
	nop
	rep #$20
	lda $4216
	sta Gm_mid
	sep #$20
	lda Gm_a+1                  ; ah*bl
	sta $4202
	lda Gm_b
	sta $4203
	stz Gm_carry
	stz Gm_carry+1
	nop
	rep #$20
	lda $4216
	clc
	adc Gm_mid
	sta Gm_mid                  ; bits 8-23 of the middle, bit 24 in the carry
	bcc +
	inc Gm_carry
+	sep #$20
	lda Gm_a                    ; al*bl: only its high byte counts
	sta $4202
	lda Gm_b
	sta $4203
	nop
	nop
	nop
	rep #$20
	lda $4216
	xba
	and #$00FF
	clc
	adc Gm_mid
	sta Gm_mid
	bcc +
	inc Gm_carry
+	sep #$20
	lda Gm_a+1                  ; ah*bh: bits 16-31
	sta $4202
	lda Gm_b+1
	sta $4203
	nop
	nop
	nop
	rep #$20
	lda $4216
	sta.l tcc__r0
	lda Gm_mid
	xba
	and #$00FF
	clc
	adc.l tcc__r0
	sta.l tcc__r0
	lda Gm_carry
	xba
	clc
	adc.l tcc__r0
	sta.l tcc__r0
	rts

.ENDS

.RAMSECTION ".game_math_vars" BANK 0 SLOT 1
Gm_a      dw
Gm_b      dw
Gm_mid    dw
Gm_carry  dw
.ENDS
