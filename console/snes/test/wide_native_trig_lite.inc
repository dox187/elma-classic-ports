; Exact unsigned coefficient16/32 * unsignedQ16 remainder, nearest result.
; Dpagealigned, DB80-BF, A/X/Y16; PPU latch protocol matches core NMI.
.MACRO WNL_PARTIAL
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
 lda.b \2
 bpl _wnl_b\@
 rep #$20
 lda.b \1+\5
 clc
 adc.b \4+1
 sta.b \4+1
_wnl_b\@:
 rep #$20
 lda.b \1+\5
 bpl _wnl_a\@
 sep #$20
 lda.b \2
 clc
 adc.b \4+2
 sta.b \4+2
 rep #$20
_wnl_a\@:
 .IF \6 == 0
 ; First product: directly initialize, avoiding unnecessary carries.
 lda.b \4
 sta.b \3
 lda.b \4+2
 sta.b \3+2
 stz.b \3+4
 .ELSE
 lda.b \3+\6
 clc
 adc.b \4
 sta.b \3+\6
 .IF \6 < 3
 lda.b \3+\6+2
 adc.b \4+2
 sta.b \3+\6+2
 .IF \6 == 1
 sep #$20
 lda.b \3+5
 adc.b #0
 sta.b \3+5
 .ENDIF
 .ELSE
 sep #$20
 lda.b \3+5
 adc.b \4+2
 sta.b \3+5
 .ENDIF
 .ENDIF
 rep #$20
.ENDM
.MACRO WNL_MUL16
 ; coefficient,u,out,product,temp,coefficientbytes(2 or4)
 WNL_PARTIAL \1,\2,\4,\5,0,0
 WNL_PARTIAL \1,\2+1,\4,\5,0,1
 .IF \6 == 4
 WNL_PARTIAL \1,\2,\4,\5,2,2
 WNL_PARTIAL \1,\2+1,\4,\5,2,3
 .ENDIF
 lda.b \4
 clc
 adc #$8000
 lda.b \4+2
 adc #0
 sta.b \3
 lda.b \4+4
 adc #0
 sta.b \3+2
.ENDM
