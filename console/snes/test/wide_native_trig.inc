; Experimental exact signed coefficient * unsignedQ24 remainder -> signed40.
; WNT_MUL24 a,u,out,mag,product,temp,sign,bytes,nonnegative
; a:sign-extended signed40(5bytes), u:unsigned24(3),out:signed40(5).
; Scratch mag6/product8/temp4/sign2 must all be disjoint. Dpagealigned,
; DB exposes lowWRAM+PPU, A/X/Y16. PreservesX/Y,D,DB; clobbersA/flags.
; Ninth parameter 1 accepts nonnegative magnitude and omits sign handling.
; bytes5 accepts fullsigned40; bytes4 accepts signed29; bytes3 signed17.
; Smaller paths omit known-zero high magnitude limbs. No bitdiscard before
; final nearest rounding, ties away fromzero. Standard NMI latch retained.
.MACRO WNT_PARTIAL
 ; mag, ubyte, product, temp, coefficient-offset, product-offset
 rep #$20
 lda.b \1+\5
 xba
 sta.w core_m7_latch
 sta.w MPYA
 sta.w MPYA
 sep #$20
 lda.b \2
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b \4
 sep #$20
 lda.w MPYH
 sta.b \4+2
 stz.b \4+3
 ; PPU B is signed8; convert this product to unsignedB modulo24.
 lda.b \2
 bpl _wnt_b_positive\@
 rep #$20
 lda.b \1+\5
 clc
 adc.b \4+1
 sta.b \4+1
_wnt_b_positive\@:
 rep #$20
 ; The lower coefficient limbs are unsigned16, unlike PPU A.
 .IF \5 < 4
 lda.b \1+\5
 bpl _wnt_a_positive\@
 sep #$20
 lda.b \2
 clc
 adc.b \4+2
 sta.b \4+2
 rep #$20
_wnt_a_positive\@:
 .ENDIF
 lda.b \3+\6
 clc
 adc.b \4
 sta.b \3+\6
 .IF \6 < 5
 ; Unsigned24 partial padded with a zero byte; word carry propagation.
 lda.b \3+\6+2
 adc.b \4+2
 sta.b \3+\6+2
 .IF \6 < 3
 lda.b \3+\6+4
 adc #0
 sta.b \3+\6+4
 .ENDIF
 .IF \6 == 0
 lda.b \3+6
 adc #0
 sta.b \3+6
 .ENDIF
 .IF \6 == 1 || \6 == 3
 sep #$20
 lda.b \3+7
 adc.b #0
 sta.b \3+7
 .ENDIF
 .ELSE
 .IF \6 == 5
 sep #$20
 lda.b \3+7
 adc.b \4+2
 sta.b \3+7
 .ENDIF
 .ENDIF
 rep #$20
.ENDM

.MACRO WNT_MUL24
 rep #$20
 .IF \9 == 0
 stz.b \7
 .ENDIF
 lda.b \1
 sta.b \4
 lda.b \1+2
 sta.b \4+2
 lda.b \1+4
 and #$00FF
 sta.b \4+4
 .IF \9 == 0
 bit #$0080
 beq _wnt_magnitude\@
 lda #1
 sta.b \7
 lda.b \4
 eor #$FFFF
 clc
 adc #1
 sta.b \4
 lda.b \4+2
 eor #$FFFF
 adc #0
 sta.b \4+2
 sep #$20
 lda.b \4+4
 eor.b #$FF
 adc.b #0
 sta.b \4+4
 rep #$20
_wnt_magnitude\@:
 .ENDIF
 stz.b \5
 stz.b \5+2
 stz.b \5+4
 stz.b \5+6
 WNT_PARTIAL \4,\2,\5,\6,0,0
 WNT_PARTIAL \4,\2+1,\5,\6,0,1
 WNT_PARTIAL \4,\2+2,\5,\6,0,2
 .IF \8 >= 4
 WNT_PARTIAL \4,\2,\5,\6,2,2
 WNT_PARTIAL \4,\2+1,\5,\6,2,3
 WNT_PARTIAL \4,\2+2,\5,\6,2,4
 .ELSE
 ; Only signed17 minimum -65536 has a nonzero upper magnitude bit.
 lda.b \4+2
 beq _wnt_no17high\@
 lda.b \5+2
 clc
 adc.b \2
 sta.b \5+2
 sep #$20
 lda.b \5+4
 adc.b \2+2
 sta.b \5+4
 rep #$20
_wnt_no17high\@:
 .ENDIF
 .IF \8 == 5
 WNT_PARTIAL \4,\2,\5,\6,4,4
 WNT_PARTIAL \4,\2+1,\5,\6,4,5
 WNT_PARTIAL \4,\2+2,\5,\6,4,6
 .ENDIF
 ; Round unsigned magnitude before restoring sign: exact negative ties.
 lda.b \5+2
 clc
 adc #$0080
 sta.b \5+2
 lda.b \5+4
 adc #0
 sta.b \5+4
 lda.b \5+6
 adc #0
 sta.b \5+6
 lda.b \5+3
 sta.b \3
 lda.b \5+5
 sta.b \3+2
 sep #$20
 lda.b \5+7
 sta.b \3+4
 rep #$20
 .IF \9 == 0
 lda.b \7
 beq _wnt_done\@
 lda.b \3
 eor #$FFFF
 clc
 adc #1
 sta.b \3
 lda.b \3+2
 eor #$FFFF
 adc #0
 sta.b \3+2
 sep #$20
 lda.b \3+4
 eor.b #$FF
 adc.b #0
 sta.b \3+4
 rep #$20
_wnt_done\@:
 .ENDIF
.ENDM
