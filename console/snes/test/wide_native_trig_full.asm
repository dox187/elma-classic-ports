.include "hdr.asm"
.include "phys.inc"
.include "wide_native_trig_lite.inc"
.RAMSECTION ".wnf_ram" BANK 0 SLOT 1 ALIGN 256
wnt_ram dsb 256
.ENDS
.SECTION ".wnf_text" SUPERFREE
.MACRO WNF_ENTRY
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
.ENDM
.MACRO WNF_EXIT
 plx
 pld
 plb
 plp
.ENDM
; Input signed48Q32 atDP0, output signed32Q30 DP80/88.
; Two exact-angle cache entries DP144/160: angle6,sin4,cos4,valid2.
; PreservesX/Y,D/DB/flags; Aclobbered. Call reset before first use.
wnt_cache_reset:
 WNF_ENTRY
 stz.b 158
 stz.b 174
 stz.b 176
 WNF_EXIT
 rtl
.MACRO WNF_CACHE_CHECK
 lda.b \1+14
 beq _wnf_cache_miss\@
 lda.b 0
 cmp.b \1
 bne _wnf_cache_miss\@
 lda.b 2
 cmp.b \1+2
 bne _wnf_cache_miss\@
 lda.b 4
 cmp.b \1+4
 bne _wnf_cache_miss\@
 lda.b \1+6
 sta.b 80
 lda.b \1+8
 sta.b 82
 lda.b \1+10
 sta.b 88
 lda.b \1+12
 sta.b 90
 lda #1
 sta.b 182
 jmp wnf_exit
_wnf_cache_miss\@:
.ENDM
wnt_trig:
 WNF_ENTRY
 stz.b 182
 WNF_CACHE_CHECK 144
 WNF_CACHE_CHECK 160
 lda.b 0
 sta.b 120
 lda.b 2
 sta.b 122
 lda.b 4
 sta.b 124
 ; abs(angle48)<<16 forms an unsigned64Q48 phase. Fullsigned48domain,
 ; including minimum -32768rad, fits this magnitude without overflow.
 stz.b 96
 stz.b 112
 lda.b 0
 sta.b 98
 lda.b 2
 sta.b 100
 lda.b 4
 sta.b 102
 bpl wnf_positive
 lda #1
 sta.b 112
 lda.b 98
 eor #$FFFF
 clc
 adc #1
 sta.b 98
 lda.b 100
 eor #$FFFF
 adc #0
 sta.b 100
 lda.b 102
 eor #$FFFF
 adc #0
 sta.b 102
wnf_positive:
 lda.b 102
 cmp #32
 bcs wnf_binary_mod
wnf_fast_mod:
 lda.b 102
 cmp #6
 bcc wnf_mod_done
 bne wnf_fast_sub
 lda.b 100
 cmp #18558
 bcc wnf_mod_done
 bne wnf_fast_sub
 lda.b 98
 cmp #54545
 bcc wnf_mod_done
 bne wnf_fast_sub
 lda.b 96
 cmp #2886
 bcc wnf_mod_done
wnf_fast_sub:
 lda.b 96
 sec
 sbc #2886
 sta.b 96
 lda.b 98
 sbc #54545
 sta.b 98
 lda.b 100
 sbc #18558
 sta.b 100
 lda.b 102
 sbc #6
 sta.b 102
 bra wnf_fast_mod
wnf_binary_mod:
 lda.b 102
 cmp #128
 bcs wnf_large_mod
 ; Select an exact shifted divisor from the angle's integer leading bit.
 ; Starting shift=floor(log2(integerangle))-2 is at least the largest
 ; quotientbit; an occasional extra initial bit is harmless. Fullsigned48
 ; minimum selects shift13; all shiftedperiods fit unsigned64.
 lda.b 102
 ldx #0
wnf_count_bits:
 lsr a
 beq wnf_count_ready
 inx
 bra wnf_count_bits
wnf_count_ready:
 dex
 dex
 stx.b 116
 txa
 asl a
 asl a
 asl a
 tax
 lda.l wnf_period_shifts,x
 sta.b 104
 lda.l wnf_period_shifts+2,x
 sta.b 106
 lda.l wnf_period_shifts+4,x
 sta.b 108
 lda.l wnf_period_shifts+6,x
 sta.b 110
 ldx.b 116
 inx
 bra wnf_mod_loop
wnf_large_mod:
 lda #24576
 sta.b 104
 lda #4276
 sta.b 106
 lda #60753
 sta.b 108
 lda #25735
 sta.b 110
 ldx #13
wnf_mod_loop:
 lda.b 102
 cmp.b 110
 bcc wnf_mod_shift
 bne wnf_mod_sub
 lda.b 100
 cmp.b 108
 bcc wnf_mod_shift
 bne wnf_mod_sub
 lda.b 98
 cmp.b 106
 bcc wnf_mod_shift
 bne wnf_mod_sub
 lda.b 96
 cmp.b 104
 bcc wnf_mod_shift
wnf_mod_sub:
 lda.b 96
 sec
 sbc.b 104
 sta.b 96
 lda.b 98
 sbc.b 106
 sta.b 98
 lda.b 100
 sbc.b 108
 sta.b 100
 lda.b 102
 sbc.b 110
 sta.b 102
wnf_mod_shift:
 lsr.b 110
 ror.b 108
 ror.b 106
 ror.b 104
 dex
 bne wnf_mod_loop
wnf_mod_done:
 ; Match original signed modulo normalized to [0,2pi), not an approximate
 ; modulo against a roundedQ32 period.
 lda.b 112
 beq wnf_normalized
 lda.b 96
 ora.b 98
 ora.b 100
 ora.b 102
 beq wnf_normalized
 lda #2886
 sec
 sbc.b 96
 sta.b 96
 lda #54545
 sbc.b 98
 sta.b 98
 lda #18558
 sbc.b 100
 sta.b 100
 lda #6
 sbc.b 102
 sta.b 102
wnf_normalized:
 stz.b 112
 ; Strict a>pi determines sine sign, preserving equality semantics.
 lda.b 102
 cmp #3
 bcc wnf_quadrant
 bne wnf_minus_pi
 lda.b 100
 cmp #9279
 bcc wnf_quadrant
 bne wnf_minus_pi
 lda.b 98
 cmp #27272
 bcc wnf_quadrant
 bne wnf_minus_pi
 lda.b 96
 cmp #34211
 bcc wnf_quadrant
 beq wnf_quadrant
wnf_minus_pi:
 lda.b 96
 sec
 sbc #34211
 sta.b 96
 lda.b 98
 sbc #27272
 sta.b 98
 lda.b 100
 sbc #9279
 sta.b 100
 lda.b 102
 sbc #3
 sta.b 102
 lda #2
 sta.b 112
wnf_quadrant:
 ; Strict a>floor(pi/2), reflected using the original oddQ48 pi.
 lda.b 102
 cmp #1
 bcc wnf_angle_ready
 bne wnf_reflect
 lda.b 100
 cmp #37407
 bcc wnf_angle_ready
 bne wnf_reflect
 lda.b 98
 cmp #46404
 bcc wnf_angle_ready
 bne wnf_reflect
 lda.b 96
 cmp #17105
 bcc wnf_angle_ready
 beq wnf_angle_ready
wnf_reflect:
 lda #34211
 sec
 sbc.b 96
 sta.b 96
 lda #27272
 sbc.b 98
 sta.b 98
 lda #9279
 sbc.b 100
 sta.b 100
 lda #3
 sbc.b 102
 sta.b 102
 lda.b 112
 ora #4
 sta.b 112
wnf_angle_ready:
 lda.b 112
 bit #2
 beq wnf_flags_ready
 eor #4
 sta.b 112
wnf_flags_ready:
 ; Index=a>>36. u=round((a & (2^36-1))/2^20), with explicit carry.
 lda.b 100
 lsr a
 lsr a
 lsr a
 lsr a
 sta.b 0
 lda.b 102
 and #$000F
 xba
 asl a
 asl a
 asl a
 asl a
 ora.b 0
 sta.b 0
 lda.b 98
 lsr a
 lsr a
 lsr a
 lsr a
 sta.b 8
 lda #0
 adc #0
 sta.b 114
 lda.b 100
 and #$000F
 xba
 asl a
 asl a
 asl a
 asl a
 ora.b 8
 clc
 adc.b 114
 sta.b 8
 bcc wnf_u_ready
 inc.b 0
wnf_u_ready:
 jsr wnl_dispatch
 lda.b 112
 bit #2
 beq wnf_sin_ready
 lda.b 80
 eor #$FFFF
 clc
 adc #1
 sta.b 80
 lda.b 82
 eor #$FFFF
 adc #0
 sta.b 82
wnf_sin_ready:
 lda.b 112
 bit #4
 beq wnf_cos_ready
 lda.b 88
 eor #$FFFF
 clc
 adc #1
 sta.b 88
 lda.b 90
 eor #$FFFF
 adc #0
 sta.b 90
wnf_cos_ready:
 ldx #144
 lda.b 176
 beq wnf_store_cache
 ldx #160
wnf_store_cache:
 lda.b 120
 sta.b 0,x
 lda.b 122
 sta.b 2,x
 lda.b 124
 sta.b 4,x
 lda.b 80
 sta.b 6,x
 lda.b 82
 sta.b 8,x
 lda.b 88
 sta.b 10,x
 lda.b 90
 sta.b 12,x
 lda #1
 sta.b 14,x
 lda.b 176
 eor #1
 sta.b 176
wnf_exit:
 WNF_EXIT
wnt_trig_end:
 rtl
wnf_period_shifts:
 .DW $0B46,$D511,$487E,$0006
 .DW $168C,$AA22,$90FD,$000C
 .DW $2D18,$5444,$21FB,$0019
 .DW $5A30,$A888,$43F6,$0032
 .DW $B460,$5110,$87ED,$0064
 .DW $68C0,$A221,$0FDA,$00C9
 .DW $D180,$4442,$1FB5,$0192
 .DW $A300,$8885,$3F6A,$0324
 .DW $4600,$110B,$7ED5,$0648
 .DW $8C00,$2216,$FDAA,$0C90
 .DW $1800,$442D,$FB54,$1921
 .DW $3000,$885A,$F6A8,$3243
 .DW $6000,$10B4,$ED51,$6487
 .DW $C000,$2168,$DAA2,$C90F
.ENDS
