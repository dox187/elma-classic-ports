; Experimental wide integer arithmetic; no production solver calls this yet.
;
; WIDE_MUL48_K input, output, scratch, K
;   signed48 * positive integer K -> exact signed64, without truncation.
;   All offsets are in the current direct page. input:6 bytes, output:8,
;   scratch:4; these regions must not overlap. D must be page aligned.
;   DB must expose low WRAM and PPU I/O ($80-$BF). A/X/Y enter16-bit.
;   Clobbers A/flags, preserves X,Y,D,DB; returns A16.
;   Requires core_m7_latch and the standard multiplier register defines.
;
; Three16-bit input limbs avoid repeatedly sign-extending partial products
; through the entire result. The first two unsigned limb products overlap
; at one word; the final signed limb supplies the sign of the64-bit result.
; Each limb uses exactly two PPU16x8 products. No guard or rounding bit is
; discarded, so this is also valid for Q36 spring/damper integer factors.

.MACRO WIDE_MUL48_LIMB
	; input, output, scratch, K, first-limb, final-signed-limb
	rep #$20
	lda.b \1
	xba
	sta.w core_m7_latch
	sta.w MPYA
	sta.w MPYA
	sep #$20
	lda.b #((\4) & $FF)
	sta.w MPYB
	rep #$20
	lda.w MPYL
	sta.b \3
	sep #$20
	lda.w MPYH
	sta.b \3+2
	bpl _wide_positive\@
	lda #$FF
	bra _wide_sign\@
_wide_positive\@:
	lda #0
_wide_sign\@:
	sta.b \3+3
	; Balanced high byte includes the carry of a signed low byte.
	lda.b #(((\4) - ((((\4) + 128) & 255) - 128)) / 256) & $FF
	sta.w MPYB
	rep #$20
	lda.w MPYL
	clc
	adc.b \3+1
	sta.b \3+1
	sep #$20
	lda.w MPYH
	adc.b \3+3
	sta.b \3+3
	rep #$20
	.IF \6 == 0
	; PPU A is signed16; the lower input limbs are unsigned16.
	lda.b \1
	bpl _wide_unsigned\@
	lda.b \3+2
	clc
	adc #(\4)
	sta.b \3+2
_wide_unsigned\@:
	.ENDIF
	lda.b \3
	.IF \5 == 0
	clc
	adc.b \2
	.ENDIF
	sta.b \2
	lda.b \3+2
	.IF \5 == 0
	adc #0
	.ENDIF
	sta.b \2+2
.ENDM

.MACRO WIDE_MUL48_K
	.IF (\4) < 1 || (\4) > 32639
	.FAIL "WIDE_MUL48_K: positive balanced16 coefficient required"
	.ENDIF
	WIDE_MUL48_LIMB \1, \2, \3, \4, 1, 0
	WIDE_MUL48_LIMB \1+2, \2+2, \3, \4, 0, 0
	WIDE_MUL48_LIMB \1+4, \2+4, \3, \4, 0, 1
.ENDM
