.include "hdr.asm"
.include "phys.inc"
.include "wide_native_trig_lite.inc"
.RAMSECTION ".wnl_ram" BANK 0 SLOT 1 ALIGN 256
wnt_ram dsb 256
.ENDS
.SECTION ".wnl_text" SUPERFREE
; First-quadrant index DP0, u16 DP8. Q30 positive outputs4 bytes DP80/88.
.MACRO WNL_HORNER
 lda.l \1+10,x
 sta.b 0
 WNL_MUL16 0,8,16,40,48,2
 lda.l \1+6,x
 .IF \2 == 0
 sec
 sbc.b 16
 .ELSE
 clc
 adc.b 16
 .ENDIF
 sta.b 0
 lda.l \1+8,x
 .IF \2 == 0
 sbc.b 18
 .ELSE
 adc.b 18
 .ENDIF
 sta.b 2
 WNL_MUL16 0,8,16,40,48,4
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
 adc #0
 .ELSE
 sbc #0
 .ENDIF
 sta.b 68
 ; Q40 -> Q30 rounding after both Horner products, as host normal conversion.
 lda.b 64
 clc
 adc #512
 sta.b 64
 lda.b 66
 adc #0
 sta.b 66
 lda.b 68
 adc #0
 sta.b 68
 lda.b 65
 sta.b \3
 lda.b 67
 sta.b \3+2
 lda.b 69
 and #$00FF
 lsr a
 ror.b \3+2
 ror.b \3
 lsr a
 ror.b \3+2
 ror.b \3
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
 lda.b 0
 and #$07FF
 sta.b 24
 asl a
 asl a
 sta.b 26
 asl a
 clc
 adc.b 26
 adc.b 24
 tax
 lda.b 0
 cmp #2048
 bcc _wnl_bank0
 cmp #4096
 bcc _wnl_bank1
 cmp #6144
 bcc _wnl_bank2
 jsr wnl_bank3
 bra _wnl_done
_wnl_bank0:
 jsr wnl_bank0
 bra _wnl_done
_wnl_bank1:
 jsr wnl_bank1
 bra _wnl_done
_wnl_bank2:
 jsr wnl_bank2
_wnl_done:
 plx
 pld
 plb
 plp
wnt_pair_end:
 rtl
wnl_bank0:
 WNL_HORNER wnl_sin0,0,80
 WNL_HORNER wnl_cos0,1,88
 rts
wnl_bank1:
 WNL_HORNER wnl_sin1,0,80
 WNL_HORNER wnl_cos1,1,88
 rts
wnl_bank2:
 WNL_HORNER wnl_sin2,0,80
 WNL_HORNER wnl_cos2,1,88
 rts
wnl_bank3:
 WNL_HORNER wnl_sin3,0,80
 WNL_HORNER wnl_cos3,1,88
 rts
wnl_text_end:
.ENDS
