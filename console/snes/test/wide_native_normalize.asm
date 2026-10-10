; Experimental narrow products for staged reciprocal-square-root refinement.
; void wide_mul32_shift32(const u16 *a, const u16 *b, u16 nearest,
;                         u16 *out, u16 *guard);
; Inputs/output unsigned32 in WRAM $7E. guard returns product bit31 (0/1).
; nearest=0 selects floor(product/2^32); nonzero selects nearest-half-up.
; Own experimental DP; preserves D/DB/X/Y/flags. No production calls.
;
; Exact middle-word construction: LLhi + LH + HL contributes above bit16;
; HH plus that sum's upper32 gives product bits32..63. Its bit15 is the
; sole rounding guard. No omitted low partial can carry into these words.

.MACRO WNM_COEFFICIENT
 lda.b \1
 xba
 sta.w core_m7_latch
 sta.w MPYA
 sta.w MPYA
.ENDM
.MACRO WNM_PARTIAL
 ; coefficientword, unsignedbyte, unsigned24 temp
 sep #$20
 lda.b \2
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b \3
 sep #$20
 lda.w MPYH
 sta.b \3+2
 stz.b \3+3
 lda.b \2
 bpl _wnm_b\@
 rep #$20
 lda.b \1
 clc
 adc.b \3+1
 sta.b \3+1
_wnm_b\@:
 rep #$20
 lda.b \1
 bpl _wnm_a\@
 sep #$20
 lda.b \2
 clc
 adc.b \3+2
 sta.b \3+2
_wnm_a\@:
 rep #$20
.ENDM
.MACRO WNM_MUL16
 ; Coefficient already loaded. aUnsigned16,bUnsigned16,out32,tempUnused.
 ; A*B=A_signed*int8(Blo)+256*A_signed*int8(Bhi)
 ;     +(Blo>=128 ? A_signed<<8 : 0)+(B>=32768 ? A_signed<<16 : 0)
 ;     +(A>=32768 ? B_unsigned<<16 : 0).
 ; Capture high bytes directly. Terms beyond product bit31 are discarded;
 ; the low product alone needs sign extension through out+3.
 sep #$20
 lda.b \2
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b \3
 sep #$20
 lda.w MPYH
 sta.b \3+2
 asl a
 lda.b #0
 bcc _wnm_low_positive\@
 dec a
_wnm_low_positive\@:
 sta.b \3+3
 lda.b \2+1
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
 lda.b \2
 bit #$0080
 beq _wnm_low_balanced\@
 lda.b \1
 clc
 adc.b \3+1
 sta.b \3+1
 sep #$20
 lda.b #0
 bit.b \1+1
 bpl _wnm_no_sign\@
 lda.b #$ff
_wnm_no_sign\@:
 adc.b \3+3
 sta.b \3+3
 rep #$20
_wnm_low_balanced\@:
 lda.b \2
 bpl _wnm_unsigned_b_pair\@
 clc
 lda.b \3+2
 adc.b \1
 sta.b \3+2
_wnm_unsigned_b_pair\@:
 lda.b \1
 bpl _wnm_unsigned_pair\@
 clc
 lda.b \3+2
 adc.b \2
 sta.b \3+2
_wnm_unsigned_pair\@:
.ENDM
.MACRO WNM_MUL32_HI
 ; a32,b32,out32,guardword,scratch16
wnm_product_ll\@:
 WNM_COEFFICIENT \1
 WNM_MUL16 \1,\2,\5,\5+4
 lda.b \5+2
 sta.b \5+8
wnm_product_lh\@:
 WNM_MUL16 \1,\2+2,\5,\5+4
 lda.b \5
 sta.b \5+10
 lda.b \5+2
 sta.b \5+12
 stz.b \5+14
wnm_product_hl\@:
 WNM_COEFFICIENT \1+2
 WNM_MUL16 \1+2,\2,\5,\5+4
 clc
 lda.b \5
 adc.b \5+10
 sta.b \5+10
 lda.b \5+2
 adc.b \5+12
 sta.b \5+12
 lda.b \5+14
 adc #0
 sta.b \5+14
 clc
 lda.b \5+8
 adc.b \5+10
 sta.b \5+10
 lda.b \5+12
 adc #0
 sta.b \5+12
 lda.b \5+14
 adc #0
 sta.b \5+14
wnm_product_hh\@:
 WNM_MUL16 \1+2,\2+2,\5,\5+4
wnm_matrix_sum\@:
 clc
 lda.b \5
 adc.b \5+12
 sta.b \3
 lda.b \5+2
 adc.b \5+14
 sta.b \3+2
 lda.b \5+10
 asl a
 lda #0
 adc #0
 sta.b \4
wnm_matrix_end\@:
.ENDM

.RAMSECTION ".wide_native_normalize_ram" BANK 0 SLOT 1 ALIGN 256
wide_native_normalize_dp dsb 256
.ENDS
.SECTION ".wide_native_normalize_text" SUPERFREE
wide_mul32_shift32:
 php
 phb
 phd
 rep #$30
 phx
 phy
 pea wide_native_normalize_dp
 pld
 sep #$20
 lda #$7e
 pha
 plb
 rep #$20
 lda 12,s
 tax
 lda.w 0,x
 sta.b 0
 lda.w 2,x
 sta.b 2
 lda 16,s
 tax
 lda.w 0,x
 sta.b 4
 lda.w 2,x
 sta.b 6
 sep #$20
 lda #$80
 pha
 plb
 rep #$20
wide_mul32_core_begin:
 WNM_MUL32_HI 0,4,8,12,14
 lda 20,s
 beq _wnm_floor
 lda.b 12
 beq _wnm_floor
 clc
 lda.b 8
 adc #1
 sta.b 8
 lda.b 10
 adc #0
 sta.b 10
_wnm_floor:
wide_mul32_core_end:
 sep #$20
 lda #$7e
 pha
 plb
 rep #$20
 lda 22,s
 tax
 lda.b 8
 sta.w 0,x
 lda.b 10
 sta.w 2,x
 lda 26,s
 tax
 lda.b 12
 sta.w 0,x
 ply
 plx
 pld
 plb
 plp
 rtl
; One complete Q32 Newton refinement, including integer parts of m/term.
; void wide_nr32(const u16 *m, const u16 *r, u16 reserved,
;                u16 *out, u16 *status);
; m/r/out are unsigned64 rawQ32. Domain: 1<=m<4, .5<=r<=1 and
; m*round(r*r)<=3 in Q32. status0 valid,2 outside domain; output unchanged.
; Matches separate nearest r^2, nearest m*r^2, then nearest r*(3-m*r^2)/2.
; Three middle-product macros share a single entry and DP page.
wide_nr32:
 php
 phb
 phd
 rep #$30
 phx
 phy
 pea wide_native_normalize_dp
 pld
 sep #$20
 lda #$7e
 pha
 plb
 rep #$20
 lda 12,s
 tax
 lda.w 0,x
 sta.b 0
 lda.w 2,x
 sta.b 2
 lda.w 4,x
 sta.b 4
 lda.w 6,x
 sta.b 6
 lda 16,s
 tax
 lda.w 0,x
 sta.b 8
 lda.w 2,x
 sta.b 10
 lda.w 4,x
 sta.b 12
 lda.w 6,x
 sta.b 14
 stz.b 24
wide_nr32_core_begin:
 lda.b 6
 bne _wnr_domain_a
 lda.b 4
 beq _wnr_domain_a
 cmp #4
 bcs _wnr_domain_a
 lda.b 14
 bne _wnr_domain_a
 lda.b 12
 beq _wnr_rate_fractional
 cmp #1
 bne _wnr_domain_a
 lda.b 8
 ora.b 10
 bne _wnr_domain_a
 ; Exact r=1: the update is nearest((3-m)/2).
 sec
 lda #0
 sbc.b 0
 sta.b 16
 lda #0
 sbc.b 2
 sta.b 18
 lda #3
 sbc.b 4
 sta.b 20
 lda #0
 sbc.b 6
 sta.b 22
 bcc _wnr_domain_a
 jmp _wnr_round_half
_wnr_domain_a:
 jmp _wnr_domain
_wnr_rate_fractional:
 lda.b 10
 cmp #$8000
 bcc _wnr_domain_a
 sep #$20
 lda #$80
 pha
 plb
 rep #$20
 lda.b 8
 beq _wnr_short_square
 jmp _wnr_general_square
_wnr_short_square:
 WNM_COEFFICIENT 10
 WNM_MUL16 10,10,26,48
 jmp _wnr_square_rounded
_wnr_general_square:
 WNM_MUL32_HI 8,8,26,42,48
 lda.b 42
 beq _wnr_square_rounded
 clc
 lda.b 26
 adc #1
 sta.b 26
 lda.b 28
 adc #0
 sta.b 28
_wnr_square_rounded:
 WNM_MUL32_HI 0,26,30,42,48
 clc
 lda.b 30
 adc.b 42
 sta.b 34
 lda.b 32
 adc #0
 sta.b 36
 lda #0
 adc #0
 sta.b 38
 stz.b 40
 ldx.b 4
_wnr_integer_m:
 clc
 lda.b 34
 adc.b 26
 sta.b 34
 lda.b 36
 adc.b 28
 sta.b 36
 lda.b 38
 adc #0
 sta.b 38
 lda.b 40
 adc #0
 sta.b 40
 dex
 bne _wnr_integer_m
 sec
 lda #0
 sbc.b 34
 sta.b 34
 lda #0
 sbc.b 36
 sta.b 36
 lda #3
 sbc.b 38
 sta.b 38
 lda #0
 sbc.b 40
 sta.b 40
 bcs _wnr_term_positive
 jmp _wnr_domain
_wnr_term_positive:
 lda.b 8
 beq _wnr_short_update
 jmp _wnr_general_update
_wnr_short_update:
 WNM_COEFFICIENT 10
 WNM_MUL16 10,34,48,52
 lda.b 50
 sta.b 44
 WNM_MUL16 10,36,48,52
 clc
 lda.b 48
 adc.b 44
 sta.b 16
 lda.b 50
 adc #0
 sta.b 18
 jmp _wnr_update_done
_wnr_general_update:
 WNM_MUL32_HI 8,34,16,42,48
_wnr_update_done:
 stz.b 20
 stz.b 22
 ldx.b 38
 beq _wnr_round_half
_wnr_integer_term:
 clc
 lda.b 16
 adc.b 8
 sta.b 16
 lda.b 18
 adc.b 10
 sta.b 18
 lda.b 20
 adc #0
 sta.b 20
 lda.b 22
 adc #0
 sta.b 22
 dex
 bne _wnr_integer_term
_wnr_round_half:
 clc
 lda.b 16
 adc #1
 sta.b 16
 lda.b 18
 adc #0
 sta.b 18
 lda.b 20
 adc #0
 sta.b 20
 lda.b 22
 adc #0
 sta.b 22
 lsr.b 22
 ror.b 20
 ror.b 18
 ror.b 16
wide_nr32_core_end:
 lda.b 24
 bne _wnr_return
 sep #$20
 lda #$7e
 pha
 plb
 rep #$20
 lda 22,s
 tax
 lda.b 16
 sta.w 0,x
 lda.b 18
 sta.w 2,x
 lda.b 20
 sta.w 4,x
 lda.b 22
 sta.w 6,x
 bra _wnr_return
_wnr_domain:
 lda #2
 sta.b 24
 jmp wide_nr32_core_end
_wnr_return:
 sep #$20
 lda #$7e
 pha
 plb
 rep #$20
 lda 26,s
 tax
 lda.b 24
 sta.w 0,x
 ply
 plx
 pld
 plb
 plp
 rtl
.ENDS
