.include "hdr.asm"
.include "phys.inc"
.include "wide_native_trig.inc"
.RAMSECTION ".wnt_ram" BANK 0 SLOT 1 ALIGN 256
wnt_ram dsb 256
.ENDS
.SECTION ".wnt_pair_text" SUPERFREE
; Input index16 at DP0, u24 at DP8. Output unsignedQ40 pair DP80/88.
; Caller supplies canonical first-quadrant cell/remainder (last cell restricted).
; Coefficients loaded as unsigned magnitudes; proven signs select add/sub.
.MACRO WNT_LOAD
 lda.l \1+\2,x
 sta.b 0
 lda.l \1+\2+2,x
 sta.b 2
 .IF \3 == 5
 sep #$20
 lda.l \1+\2+4,x
 sta.b 4
 rep #$20
 .ELSE
 stz.b 4
 .IF \3 == 3
 lda.b 2
 and #$00FF
 sta.b 2
 .ENDIF
 .ENDIF
.ENDM
.MACRO WNT_HORNER
 WNT_LOAD \1,16,3
 WNT_MUL24 0,8,16,32,40,48,52,3,1
 ; H2 magnitude: sin abs(c2)+product, cos abs(c2)-product.
 lda.l \1+12,x
 .IF \2 == 0
 clc
 adc.b 16
 .ELSE
 sec
 sbc.b 16
 .ENDIF
 sta.b 0
 lda.l \1+14,x
 .IF \2 == 0
 adc.b 18
 .ELSE
 sbc.b 18
 .ENDIF
 sta.b 2
 stz.b 4
 WNT_MUL24 0,8,16,32,40,48,52,4,1
 ; H1 magnitude: sin c1-product, cos abs(c1)+product.
 lda.l \1+7,x
 .IF \2 == 0
 sec
 sbc.b 16
 .ELSE
 clc
 adc.b 16
 .ENDIF
 sta.b 0
 lda.l \1+9,x
 .IF \2 == 0
 sbc.b 18
 .ELSE
 adc.b 18
 .ENDIF
 sta.b 2
 sep #$20
 lda.l \1+11,x
 .IF \2 == 0
 sbc.b 20
 .ELSE
 adc.b 20
 .ENDIF
 sta.b 4
 rep #$20
 WNT_MUL24 0,8,16,32,40,48,52,5,1
 ; c0 +/- product, 7byte positive Q48 result.
 lda.l \1,x
 .IF \2 == 0
 clc
 adc.b 16
 .ELSE
 sec
 sbc.b 16
 .ENDIF
 sta.b 64
 lda.l \1+2,x
 .IF \2 == 0
 adc.b 18
 .ELSE
 sbc.b 18
 .ENDIF
 sta.b 66
 lda.l \1+4,x
 .IF \2 == 0
 adc.b 20
 .ELSE
 sbc.b 20
 .ENDIF
 sta.b 68
 sep #$20
 lda.l \1+6,x
 .IF \2 == 0
 adc.b #0
 .ELSE
 sbc.b #0
 .ENDIF
 sta.b 70
 rep #$20
 ; Positive nearest rounding Q48 -> Q40, preserving unit value 2^40.
 lda.b 64
 clc
 adc #128
 sta.b 64
 lda.b 66
 adc #0
 sta.b 66
 lda.b 68
 adc #0
 sta.b 68
 sep #$20
 lda.b 70
 adc.b #0
 sta.b 70
 rep #$20
 lda.b 65
 sta.b \3
 lda.b 67
 sta.b \3+2
 lda.b 69
 sta.b \3+4
.ENDM
wnt_pair:
 php
 phb
 phd
 phx
 rep #$30
 sep #$20
 lda.b #$80
 pha
 plb
 rep #$20
 lda #wnt_ram
 tcd
 ; Explicit pad for the five-byte multiply output used as a six-byte addend.
 sep #$20
 stz.b 21
 rep #$20
 ; index*19 fits16 bits for all1609 cells.
 lda.b 0
 sta.b 24
 asl a
 asl a
 asl a
 asl a
 clc
 adc.b 24
 adc.b 24
 adc.b 24
 tax
 WNT_HORNER wnt_sin,0,80
 WNT_HORNER wnt_cos,1,88
 plx
 pld
 plb
 plp
wnt_pair_end:
 rtl
.ENDS
