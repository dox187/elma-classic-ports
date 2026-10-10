; Experimental compact state integration. No production caller yet.
;
; WIDE_INTEGRATE48 state, rate, result, scratch, status, shift, rate_bytes
; Signed48 state + signed40/48 per-step rate, rounded nearest with ties
; away from zero. shift5/8 describe the difference in fractional precision.
; Angles stay unwrapped: the original solver wraps wheels conditionally.
; Output is signed48 modulo 2^48; status=1 reports signed48 overflow.
; Each region must be disjoint: state/result6 bytes, scratch8, rate5/6, status2.
; D page aligned, A/X/Y16, DB maps low WRAM. Clobbers A/flags only.
; There is no multiplier, division, float, saturation, or PPU register use.
.MACRO WIDE_INTEGRATE48
	rep #$20
	lda.b \2+4
	.IF \7 == 5
	and #$00FF
	bit #$0080
	beq _wi_positive\@
	ora #$FF00
	.ELSE
	.IF \7 != 6
	.FAIL "WIDE_INTEGRATE48 requires rate5/6 bytes"
	.ENDIF
	bit #$8000
	beq _wi_positive\@
	.ENDIF
	sta.b \4+4
	.IF \7 == 6
	lda #$FFFF
	sta.b \4+6
	.ENDIF
	lda #((1 << (\6-1))-1)
	bra _wi_bias\@
_wi_positive\@:
	sta.b \4+4
	.IF \7 == 6
	lda #0
	sta.b \4+6
	.ENDIF
	lda #(1 << (\6-1))
_wi_bias\@:
	clc
	adc.b \2
	sta.b \4
	lda.b \2+2
	adc #0
	sta.b \4+2
	lda.b \4+4
	adc #0
	sta.b \4+4
	.IF \7 == 6
	; Preserve the49th sign/carry bit through rounding at signed48 limits.
	lda.b \4+6
	adc #0
	sta.b \4+6
	.ENDIF
	.IF \6 == 5
	.IF \7 == 6
	.FAIL "48-bit rate currently requires byte-aligned shift8"
	.ENDIF
	; Compose shifted words from byte-offset loads. Low-to-high writes
	; leave every source byte intact until its last use. status is scratch.
	lda.b \4
	and #$00E0
	.REPT 5
	lsr a
	.ENDR
	sta.b \5
	lda.b \4+1
	.REPT 3
	asl a
	.ENDR
	ora.b \5
	sta.b \4
	lda.b \4+2
	and #$00E0
	.REPT 5
	lsr a
	.ENDR
	sta.b \5
	lda.b \4+3
	.REPT 3
	asl a
	.ENDR
	ora.b \5
	sta.b \4+2
	lda.b \4+4
	bpl _wi_high_positive\@
	.REPT 5
	lsr a
	.ENDR
	ora #$F800
	bra _wi_high_ready\@
_wi_high_positive\@:
	.REPT 5
	lsr a
	.ENDR
_wi_high_ready\@:
	sta.b \4+4
	.ELSE
	.IF \6 != 8
	.FAIL "WIDE_INTEGRATE48 supports shifts5 and8 only"
	.ENDIF
	; Byte-aligned arithmetic shift8 needs no repeated shifts.
	lda.b \4+1
	sta.b \4
	lda.b \4+3
	sta.b \4+2
	lda.b \4+5
	.IF \7 == 5
	and #$00FF
	bit #$0080
	beq _wi_shift_positive\@
	ora #$FF00
_wi_shift_positive\@:
	.ENDIF
	sta.b \4+4
	.ENDIF
	clc
	lda.b \1
	adc.b \4
	sta.b \3
	lda.b \1+2
	adc.b \4+2
	sta.b \3+2
	lda.b \1+4
	adc.b \4+4
	sta.b \3+4
	; Signed overflow iff the two addends have equal signs and sum differs.
	eor.b \1+4
	and #$8000
	beq _wi_ok\@
	lda.b \1+4
	eor.b \4+4
	and #$8000
	bne _wi_ok\@
	lda #1
	bra _wi_status\@
_wi_ok\@:
	lda #0
_wi_status\@:
	sta.b \5
.ENDM
