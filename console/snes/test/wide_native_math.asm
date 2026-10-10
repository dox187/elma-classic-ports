; Experimental exact raw64 arithmetic backend; not linked into production.
; void wide_mul64(const u16 *a, const u16 *b, u16 fraction,
;                 u16 *out, u16 *status);
; All buffers are in WRAM bank $7E; values are four little-endian words.
; Supports fractions 0, 40, 44 and 48. status: 0 success, 1 signed64 overflow,
; 2 unsupported fraction. Output is unchanged on failure.
; Computes the complete unsigned128 magnitude before nearest-half-away
; rounding. Each PPU coefficient pair shadows core_m7_latch before the
; first write, preserving the standard NMI/scroll latch contract.
; Preserves D,DB,X,Y and caller flags; owns a separate experimental DP page.

.RAMSECTION ".wide_native_math_ram" BANK 0 SLOT 1 ALIGN 256
wide_native_math_dp dsb 256
.ENDS
.SECTION ".wide_native_math_text" SUPERFREE
wide_mul64:
 php
 phb
 phd
 rep #$30
 phx
 phy
 pea wide_native_math_dp
 pld
 sep #$20
 lda #$7e
 pha
 plb
 rep #$20
 lda 22,s
 sta.b 54
 lda 26,s
 sta.b 56
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
 lda 20,s
 sta.b 48
 cmp #0
 beq _wide_mul_fraction_ok
 cmp #48
 beq _wide_mul_fraction_ok
 cmp #40
 beq _wide_mul_fraction_ok
 cmp #44
 beq _wide_mul_fraction_ok
 lda #2
 sta.b 50
 jmp _wide_mul_return
_wide_mul_fraction_ok:
 stz.b 50
 lda.b 6
 eor.b 14
 and #$8000
 sta.b 46

 lda.b 6
 bpl _wide_mul_abs_done_0
 sec
 lda #0
 sbc.b 0
 sta.b 0
 lda #0
 sbc.b 2
 sta.b 2
 lda #0
 sbc.b 4
 sta.b 4
 lda #0
 sbc.b 6
 sta.b 6
_wide_mul_abs_done_0:
 lda.b 14
 bpl _wide_mul_abs_done_8
 sec
 lda #0
 sbc.b 8
 sta.b 8
 lda #0
 sbc.b 10
 sta.b 10
 lda #0
 sbc.b 12
 sta.b 12
 lda #0
 sbc.b 14
 sta.b 14
_wide_mul_abs_done_8:
 sep #$20
 lda #$80
 pha
 plb
 rep #$20
 stz.b 16
 stz.b 18
 stz.b 20
 stz.b 22
 stz.b 24
 stz.b 26
 stz.b 28
 stz.b 30
 stz.b 32
 lda.b 0
 bne _wide_mul_a_nonzero_0
 jmp _wide_mul_a_done_0
_wide_mul_a_nonzero_0:
 xba
 sta.w core_m7_latch
 sta.w MPYA
 sta.w MPYA
 sep #$20
 lda.b 8
 bne _wide_mul_b_nonzero_0_0
 rep #$20
 jmp _wide_mul_pp_done_0_0
_wide_mul_b_nonzero_0_0:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_0_0
 lda #$ff
 bra _wide_mul_pp_sign_0_0
_wide_mul_pp_pos_0_0:
 lda #0
_wide_mul_pp_sign_0_0:
 sta.b 45
 lda.b 8
 bpl _wide_mul_b_unsigned_0_0
 rep #$20
 clc
 lda.b 43
 adc.b 0
 sta.b 43
 sep #$20
 lda #0
 bit.b 1
 bpl _wide_mul_a_ext_0_0
 lda #$ff
_wide_mul_a_ext_0_0:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_0_0:
 rep #$20
 lda.b 0
 bpl _wide_mul_a_unsigned_0_0
 lda.b 8
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_0_0:
 clc
 lda.b 42
 adc.b 16
 sta.b 16
 lda.b 44
 adc.b 18
 sta.b 18
 bcc _wide_mul_pp_done_0_0
 lda.b 20
 adc #0
 sta.b 20
 bcc _wide_mul_pp_done_0_0
 lda.b 22
 adc #0
 sta.b 22
 bcc _wide_mul_pp_done_0_0
 lda.b 24
 adc #0
 sta.b 24
 bcc _wide_mul_pp_done_0_0
 lda.b 26
 adc #0
 sta.b 26
 bcc _wide_mul_pp_done_0_0
 lda.b 28
 adc #0
 sta.b 28
 bcc _wide_mul_pp_done_0_0
 lda.b 30
 adc #0
 sta.b 30
 bcc _wide_mul_pp_done_0_0
 lda.b 32
 adc #0
 sta.b 32
_wide_mul_pp_done_0_0:
 sep #$20
 lda.b 9
 bne _wide_mul_b_nonzero_0_1
 rep #$20
 jmp _wide_mul_pp_done_0_1
_wide_mul_b_nonzero_0_1:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_0_1
 lda #$ff
 bra _wide_mul_pp_sign_0_1
_wide_mul_pp_pos_0_1:
 lda #0
_wide_mul_pp_sign_0_1:
 sta.b 45
 lda.b 9
 bpl _wide_mul_b_unsigned_0_1
 rep #$20
 clc
 lda.b 43
 adc.b 0
 sta.b 43
 sep #$20
 lda #0
 bit.b 1
 bpl _wide_mul_a_ext_0_1
 lda #$ff
_wide_mul_a_ext_0_1:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_0_1:
 rep #$20
 lda.b 0
 bpl _wide_mul_a_unsigned_0_1
 lda.b 9
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_0_1:
 clc
 lda.b 42
 adc.b 17
 sta.b 17
 lda.b 44
 adc.b 19
 sta.b 19
 bcc _wide_mul_pp_done_0_1
 lda.b 21
 adc #0
 sta.b 21
 bcc _wide_mul_pp_done_0_1
 lda.b 23
 adc #0
 sta.b 23
 bcc _wide_mul_pp_done_0_1
 lda.b 25
 adc #0
 sta.b 25
 bcc _wide_mul_pp_done_0_1
 lda.b 27
 adc #0
 sta.b 27
 bcc _wide_mul_pp_done_0_1
 lda.b 29
 adc #0
 sta.b 29
 bcc _wide_mul_pp_done_0_1
 lda.b 31
 adc #0
 sta.b 31
 bcc _wide_mul_pp_done_0_1
 sep #$20
 lda.b 33
 adc #0
 sta.b 33
 rep #$20
_wide_mul_pp_done_0_1:
 sep #$20
 lda.b 10
 bne _wide_mul_b_nonzero_0_2
 rep #$20
 jmp _wide_mul_pp_done_0_2
_wide_mul_b_nonzero_0_2:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_0_2
 lda #$ff
 bra _wide_mul_pp_sign_0_2
_wide_mul_pp_pos_0_2:
 lda #0
_wide_mul_pp_sign_0_2:
 sta.b 45
 lda.b 10
 bpl _wide_mul_b_unsigned_0_2
 rep #$20
 clc
 lda.b 43
 adc.b 0
 sta.b 43
 sep #$20
 lda #0
 bit.b 1
 bpl _wide_mul_a_ext_0_2
 lda #$ff
_wide_mul_a_ext_0_2:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_0_2:
 rep #$20
 lda.b 0
 bpl _wide_mul_a_unsigned_0_2
 lda.b 10
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_0_2:
 clc
 lda.b 42
 adc.b 18
 sta.b 18
 lda.b 44
 adc.b 20
 sta.b 20
 bcc _wide_mul_pp_done_0_2
 lda.b 22
 adc #0
 sta.b 22
 bcc _wide_mul_pp_done_0_2
 lda.b 24
 adc #0
 sta.b 24
 bcc _wide_mul_pp_done_0_2
 lda.b 26
 adc #0
 sta.b 26
 bcc _wide_mul_pp_done_0_2
 lda.b 28
 adc #0
 sta.b 28
 bcc _wide_mul_pp_done_0_2
 lda.b 30
 adc #0
 sta.b 30
 bcc _wide_mul_pp_done_0_2
 lda.b 32
 adc #0
 sta.b 32
_wide_mul_pp_done_0_2:
 sep #$20
 lda.b 11
 bne _wide_mul_b_nonzero_0_3
 rep #$20
 jmp _wide_mul_pp_done_0_3
_wide_mul_b_nonzero_0_3:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_0_3
 lda #$ff
 bra _wide_mul_pp_sign_0_3
_wide_mul_pp_pos_0_3:
 lda #0
_wide_mul_pp_sign_0_3:
 sta.b 45
 lda.b 11
 bpl _wide_mul_b_unsigned_0_3
 rep #$20
 clc
 lda.b 43
 adc.b 0
 sta.b 43
 sep #$20
 lda #0
 bit.b 1
 bpl _wide_mul_a_ext_0_3
 lda #$ff
_wide_mul_a_ext_0_3:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_0_3:
 rep #$20
 lda.b 0
 bpl _wide_mul_a_unsigned_0_3
 lda.b 11
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_0_3:
 clc
 lda.b 42
 adc.b 19
 sta.b 19
 lda.b 44
 adc.b 21
 sta.b 21
 bcc _wide_mul_pp_done_0_3
 lda.b 23
 adc #0
 sta.b 23
 bcc _wide_mul_pp_done_0_3
 lda.b 25
 adc #0
 sta.b 25
 bcc _wide_mul_pp_done_0_3
 lda.b 27
 adc #0
 sta.b 27
 bcc _wide_mul_pp_done_0_3
 lda.b 29
 adc #0
 sta.b 29
 bcc _wide_mul_pp_done_0_3
 lda.b 31
 adc #0
 sta.b 31
 bcc _wide_mul_pp_done_0_3
 sep #$20
 lda.b 33
 adc #0
 sta.b 33
 rep #$20
_wide_mul_pp_done_0_3:
 sep #$20
 lda.b 12
 bne _wide_mul_b_nonzero_0_4
 rep #$20
 jmp _wide_mul_pp_done_0_4
_wide_mul_b_nonzero_0_4:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_0_4
 lda #$ff
 bra _wide_mul_pp_sign_0_4
_wide_mul_pp_pos_0_4:
 lda #0
_wide_mul_pp_sign_0_4:
 sta.b 45
 lda.b 12
 bpl _wide_mul_b_unsigned_0_4
 rep #$20
 clc
 lda.b 43
 adc.b 0
 sta.b 43
 sep #$20
 lda #0
 bit.b 1
 bpl _wide_mul_a_ext_0_4
 lda #$ff
_wide_mul_a_ext_0_4:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_0_4:
 rep #$20
 lda.b 0
 bpl _wide_mul_a_unsigned_0_4
 lda.b 12
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_0_4:
 clc
 lda.b 42
 adc.b 20
 sta.b 20
 lda.b 44
 adc.b 22
 sta.b 22
 bcc _wide_mul_pp_done_0_4
 lda.b 24
 adc #0
 sta.b 24
 bcc _wide_mul_pp_done_0_4
 lda.b 26
 adc #0
 sta.b 26
 bcc _wide_mul_pp_done_0_4
 lda.b 28
 adc #0
 sta.b 28
 bcc _wide_mul_pp_done_0_4
 lda.b 30
 adc #0
 sta.b 30
 bcc _wide_mul_pp_done_0_4
 lda.b 32
 adc #0
 sta.b 32
_wide_mul_pp_done_0_4:
 sep #$20
 lda.b 13
 bne _wide_mul_b_nonzero_0_5
 rep #$20
 jmp _wide_mul_pp_done_0_5
_wide_mul_b_nonzero_0_5:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_0_5
 lda #$ff
 bra _wide_mul_pp_sign_0_5
_wide_mul_pp_pos_0_5:
 lda #0
_wide_mul_pp_sign_0_5:
 sta.b 45
 lda.b 13
 bpl _wide_mul_b_unsigned_0_5
 rep #$20
 clc
 lda.b 43
 adc.b 0
 sta.b 43
 sep #$20
 lda #0
 bit.b 1
 bpl _wide_mul_a_ext_0_5
 lda #$ff
_wide_mul_a_ext_0_5:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_0_5:
 rep #$20
 lda.b 0
 bpl _wide_mul_a_unsigned_0_5
 lda.b 13
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_0_5:
 clc
 lda.b 42
 adc.b 21
 sta.b 21
 lda.b 44
 adc.b 23
 sta.b 23
 bcc _wide_mul_pp_done_0_5
 lda.b 25
 adc #0
 sta.b 25
 bcc _wide_mul_pp_done_0_5
 lda.b 27
 adc #0
 sta.b 27
 bcc _wide_mul_pp_done_0_5
 lda.b 29
 adc #0
 sta.b 29
 bcc _wide_mul_pp_done_0_5
 lda.b 31
 adc #0
 sta.b 31
 bcc _wide_mul_pp_done_0_5
 sep #$20
 lda.b 33
 adc #0
 sta.b 33
 rep #$20
_wide_mul_pp_done_0_5:
 sep #$20
 lda.b 14
 bne _wide_mul_b_nonzero_0_6
 rep #$20
 jmp _wide_mul_pp_done_0_6
_wide_mul_b_nonzero_0_6:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_0_6
 lda #$ff
 bra _wide_mul_pp_sign_0_6
_wide_mul_pp_pos_0_6:
 lda #0
_wide_mul_pp_sign_0_6:
 sta.b 45
 lda.b 14
 bpl _wide_mul_b_unsigned_0_6
 rep #$20
 clc
 lda.b 43
 adc.b 0
 sta.b 43
 sep #$20
 lda #0
 bit.b 1
 bpl _wide_mul_a_ext_0_6
 lda #$ff
_wide_mul_a_ext_0_6:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_0_6:
 rep #$20
 lda.b 0
 bpl _wide_mul_a_unsigned_0_6
 lda.b 14
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_0_6:
 clc
 lda.b 42
 adc.b 22
 sta.b 22
 lda.b 44
 adc.b 24
 sta.b 24
 bcc _wide_mul_pp_done_0_6
 lda.b 26
 adc #0
 sta.b 26
 bcc _wide_mul_pp_done_0_6
 lda.b 28
 adc #0
 sta.b 28
 bcc _wide_mul_pp_done_0_6
 lda.b 30
 adc #0
 sta.b 30
 bcc _wide_mul_pp_done_0_6
 lda.b 32
 adc #0
 sta.b 32
_wide_mul_pp_done_0_6:
 sep #$20
 lda.b 15
 bne _wide_mul_b_nonzero_0_7
 rep #$20
 jmp _wide_mul_pp_done_0_7
_wide_mul_b_nonzero_0_7:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_0_7
 lda #$ff
 bra _wide_mul_pp_sign_0_7
_wide_mul_pp_pos_0_7:
 lda #0
_wide_mul_pp_sign_0_7:
 sta.b 45
 lda.b 15
 bpl _wide_mul_b_unsigned_0_7
 rep #$20
 clc
 lda.b 43
 adc.b 0
 sta.b 43
 sep #$20
 lda #0
 bit.b 1
 bpl _wide_mul_a_ext_0_7
 lda #$ff
_wide_mul_a_ext_0_7:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_0_7:
 rep #$20
 lda.b 0
 bpl _wide_mul_a_unsigned_0_7
 lda.b 15
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_0_7:
 clc
 lda.b 42
 adc.b 23
 sta.b 23
 lda.b 44
 adc.b 25
 sta.b 25
 bcc _wide_mul_pp_done_0_7
 lda.b 27
 adc #0
 sta.b 27
 bcc _wide_mul_pp_done_0_7
 lda.b 29
 adc #0
 sta.b 29
 bcc _wide_mul_pp_done_0_7
 lda.b 31
 adc #0
 sta.b 31
 bcc _wide_mul_pp_done_0_7
 sep #$20
 lda.b 33
 adc #0
 sta.b 33
 rep #$20
_wide_mul_pp_done_0_7:
_wide_mul_a_done_0:
 lda.b 2
 bne _wide_mul_a_nonzero_1
 jmp _wide_mul_a_done_1
_wide_mul_a_nonzero_1:
 xba
 sta.w core_m7_latch
 sta.w MPYA
 sta.w MPYA
 sep #$20
 lda.b 8
 bne _wide_mul_b_nonzero_1_0
 rep #$20
 jmp _wide_mul_pp_done_1_0
_wide_mul_b_nonzero_1_0:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_1_0
 lda #$ff
 bra _wide_mul_pp_sign_1_0
_wide_mul_pp_pos_1_0:
 lda #0
_wide_mul_pp_sign_1_0:
 sta.b 45
 lda.b 8
 bpl _wide_mul_b_unsigned_1_0
 rep #$20
 clc
 lda.b 43
 adc.b 2
 sta.b 43
 sep #$20
 lda #0
 bit.b 3
 bpl _wide_mul_a_ext_1_0
 lda #$ff
_wide_mul_a_ext_1_0:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_1_0:
 rep #$20
 lda.b 2
 bpl _wide_mul_a_unsigned_1_0
 lda.b 8
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_1_0:
 clc
 lda.b 42
 adc.b 18
 sta.b 18
 lda.b 44
 adc.b 20
 sta.b 20
 bcc _wide_mul_pp_done_1_0
 lda.b 22
 adc #0
 sta.b 22
 bcc _wide_mul_pp_done_1_0
 lda.b 24
 adc #0
 sta.b 24
 bcc _wide_mul_pp_done_1_0
 lda.b 26
 adc #0
 sta.b 26
 bcc _wide_mul_pp_done_1_0
 lda.b 28
 adc #0
 sta.b 28
 bcc _wide_mul_pp_done_1_0
 lda.b 30
 adc #0
 sta.b 30
 bcc _wide_mul_pp_done_1_0
 lda.b 32
 adc #0
 sta.b 32
_wide_mul_pp_done_1_0:
 sep #$20
 lda.b 9
 bne _wide_mul_b_nonzero_1_1
 rep #$20
 jmp _wide_mul_pp_done_1_1
_wide_mul_b_nonzero_1_1:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_1_1
 lda #$ff
 bra _wide_mul_pp_sign_1_1
_wide_mul_pp_pos_1_1:
 lda #0
_wide_mul_pp_sign_1_1:
 sta.b 45
 lda.b 9
 bpl _wide_mul_b_unsigned_1_1
 rep #$20
 clc
 lda.b 43
 adc.b 2
 sta.b 43
 sep #$20
 lda #0
 bit.b 3
 bpl _wide_mul_a_ext_1_1
 lda #$ff
_wide_mul_a_ext_1_1:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_1_1:
 rep #$20
 lda.b 2
 bpl _wide_mul_a_unsigned_1_1
 lda.b 9
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_1_1:
 clc
 lda.b 42
 adc.b 19
 sta.b 19
 lda.b 44
 adc.b 21
 sta.b 21
 bcc _wide_mul_pp_done_1_1
 lda.b 23
 adc #0
 sta.b 23
 bcc _wide_mul_pp_done_1_1
 lda.b 25
 adc #0
 sta.b 25
 bcc _wide_mul_pp_done_1_1
 lda.b 27
 adc #0
 sta.b 27
 bcc _wide_mul_pp_done_1_1
 lda.b 29
 adc #0
 sta.b 29
 bcc _wide_mul_pp_done_1_1
 lda.b 31
 adc #0
 sta.b 31
 bcc _wide_mul_pp_done_1_1
 sep #$20
 lda.b 33
 adc #0
 sta.b 33
 rep #$20
_wide_mul_pp_done_1_1:
 sep #$20
 lda.b 10
 bne _wide_mul_b_nonzero_1_2
 rep #$20
 jmp _wide_mul_pp_done_1_2
_wide_mul_b_nonzero_1_2:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_1_2
 lda #$ff
 bra _wide_mul_pp_sign_1_2
_wide_mul_pp_pos_1_2:
 lda #0
_wide_mul_pp_sign_1_2:
 sta.b 45
 lda.b 10
 bpl _wide_mul_b_unsigned_1_2
 rep #$20
 clc
 lda.b 43
 adc.b 2
 sta.b 43
 sep #$20
 lda #0
 bit.b 3
 bpl _wide_mul_a_ext_1_2
 lda #$ff
_wide_mul_a_ext_1_2:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_1_2:
 rep #$20
 lda.b 2
 bpl _wide_mul_a_unsigned_1_2
 lda.b 10
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_1_2:
 clc
 lda.b 42
 adc.b 20
 sta.b 20
 lda.b 44
 adc.b 22
 sta.b 22
 bcc _wide_mul_pp_done_1_2
 lda.b 24
 adc #0
 sta.b 24
 bcc _wide_mul_pp_done_1_2
 lda.b 26
 adc #0
 sta.b 26
 bcc _wide_mul_pp_done_1_2
 lda.b 28
 adc #0
 sta.b 28
 bcc _wide_mul_pp_done_1_2
 lda.b 30
 adc #0
 sta.b 30
 bcc _wide_mul_pp_done_1_2
 lda.b 32
 adc #0
 sta.b 32
_wide_mul_pp_done_1_2:
 sep #$20
 lda.b 11
 bne _wide_mul_b_nonzero_1_3
 rep #$20
 jmp _wide_mul_pp_done_1_3
_wide_mul_b_nonzero_1_3:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_1_3
 lda #$ff
 bra _wide_mul_pp_sign_1_3
_wide_mul_pp_pos_1_3:
 lda #0
_wide_mul_pp_sign_1_3:
 sta.b 45
 lda.b 11
 bpl _wide_mul_b_unsigned_1_3
 rep #$20
 clc
 lda.b 43
 adc.b 2
 sta.b 43
 sep #$20
 lda #0
 bit.b 3
 bpl _wide_mul_a_ext_1_3
 lda #$ff
_wide_mul_a_ext_1_3:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_1_3:
 rep #$20
 lda.b 2
 bpl _wide_mul_a_unsigned_1_3
 lda.b 11
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_1_3:
 clc
 lda.b 42
 adc.b 21
 sta.b 21
 lda.b 44
 adc.b 23
 sta.b 23
 bcc _wide_mul_pp_done_1_3
 lda.b 25
 adc #0
 sta.b 25
 bcc _wide_mul_pp_done_1_3
 lda.b 27
 adc #0
 sta.b 27
 bcc _wide_mul_pp_done_1_3
 lda.b 29
 adc #0
 sta.b 29
 bcc _wide_mul_pp_done_1_3
 lda.b 31
 adc #0
 sta.b 31
 bcc _wide_mul_pp_done_1_3
 sep #$20
 lda.b 33
 adc #0
 sta.b 33
 rep #$20
_wide_mul_pp_done_1_3:
 sep #$20
 lda.b 12
 bne _wide_mul_b_nonzero_1_4
 rep #$20
 jmp _wide_mul_pp_done_1_4
_wide_mul_b_nonzero_1_4:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_1_4
 lda #$ff
 bra _wide_mul_pp_sign_1_4
_wide_mul_pp_pos_1_4:
 lda #0
_wide_mul_pp_sign_1_4:
 sta.b 45
 lda.b 12
 bpl _wide_mul_b_unsigned_1_4
 rep #$20
 clc
 lda.b 43
 adc.b 2
 sta.b 43
 sep #$20
 lda #0
 bit.b 3
 bpl _wide_mul_a_ext_1_4
 lda #$ff
_wide_mul_a_ext_1_4:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_1_4:
 rep #$20
 lda.b 2
 bpl _wide_mul_a_unsigned_1_4
 lda.b 12
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_1_4:
 clc
 lda.b 42
 adc.b 22
 sta.b 22
 lda.b 44
 adc.b 24
 sta.b 24
 bcc _wide_mul_pp_done_1_4
 lda.b 26
 adc #0
 sta.b 26
 bcc _wide_mul_pp_done_1_4
 lda.b 28
 adc #0
 sta.b 28
 bcc _wide_mul_pp_done_1_4
 lda.b 30
 adc #0
 sta.b 30
 bcc _wide_mul_pp_done_1_4
 lda.b 32
 adc #0
 sta.b 32
_wide_mul_pp_done_1_4:
 sep #$20
 lda.b 13
 bne _wide_mul_b_nonzero_1_5
 rep #$20
 jmp _wide_mul_pp_done_1_5
_wide_mul_b_nonzero_1_5:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_1_5
 lda #$ff
 bra _wide_mul_pp_sign_1_5
_wide_mul_pp_pos_1_5:
 lda #0
_wide_mul_pp_sign_1_5:
 sta.b 45
 lda.b 13
 bpl _wide_mul_b_unsigned_1_5
 rep #$20
 clc
 lda.b 43
 adc.b 2
 sta.b 43
 sep #$20
 lda #0
 bit.b 3
 bpl _wide_mul_a_ext_1_5
 lda #$ff
_wide_mul_a_ext_1_5:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_1_5:
 rep #$20
 lda.b 2
 bpl _wide_mul_a_unsigned_1_5
 lda.b 13
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_1_5:
 clc
 lda.b 42
 adc.b 23
 sta.b 23
 lda.b 44
 adc.b 25
 sta.b 25
 bcc _wide_mul_pp_done_1_5
 lda.b 27
 adc #0
 sta.b 27
 bcc _wide_mul_pp_done_1_5
 lda.b 29
 adc #0
 sta.b 29
 bcc _wide_mul_pp_done_1_5
 lda.b 31
 adc #0
 sta.b 31
 bcc _wide_mul_pp_done_1_5
 sep #$20
 lda.b 33
 adc #0
 sta.b 33
 rep #$20
_wide_mul_pp_done_1_5:
 sep #$20
 lda.b 14
 bne _wide_mul_b_nonzero_1_6
 rep #$20
 jmp _wide_mul_pp_done_1_6
_wide_mul_b_nonzero_1_6:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_1_6
 lda #$ff
 bra _wide_mul_pp_sign_1_6
_wide_mul_pp_pos_1_6:
 lda #0
_wide_mul_pp_sign_1_6:
 sta.b 45
 lda.b 14
 bpl _wide_mul_b_unsigned_1_6
 rep #$20
 clc
 lda.b 43
 adc.b 2
 sta.b 43
 sep #$20
 lda #0
 bit.b 3
 bpl _wide_mul_a_ext_1_6
 lda #$ff
_wide_mul_a_ext_1_6:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_1_6:
 rep #$20
 lda.b 2
 bpl _wide_mul_a_unsigned_1_6
 lda.b 14
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_1_6:
 clc
 lda.b 42
 adc.b 24
 sta.b 24
 lda.b 44
 adc.b 26
 sta.b 26
 bcc _wide_mul_pp_done_1_6
 lda.b 28
 adc #0
 sta.b 28
 bcc _wide_mul_pp_done_1_6
 lda.b 30
 adc #0
 sta.b 30
 bcc _wide_mul_pp_done_1_6
 lda.b 32
 adc #0
 sta.b 32
_wide_mul_pp_done_1_6:
 sep #$20
 lda.b 15
 bne _wide_mul_b_nonzero_1_7
 rep #$20
 jmp _wide_mul_pp_done_1_7
_wide_mul_b_nonzero_1_7:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_1_7
 lda #$ff
 bra _wide_mul_pp_sign_1_7
_wide_mul_pp_pos_1_7:
 lda #0
_wide_mul_pp_sign_1_7:
 sta.b 45
 lda.b 15
 bpl _wide_mul_b_unsigned_1_7
 rep #$20
 clc
 lda.b 43
 adc.b 2
 sta.b 43
 sep #$20
 lda #0
 bit.b 3
 bpl _wide_mul_a_ext_1_7
 lda #$ff
_wide_mul_a_ext_1_7:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_1_7:
 rep #$20
 lda.b 2
 bpl _wide_mul_a_unsigned_1_7
 lda.b 15
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_1_7:
 clc
 lda.b 42
 adc.b 25
 sta.b 25
 lda.b 44
 adc.b 27
 sta.b 27
 bcc _wide_mul_pp_done_1_7
 lda.b 29
 adc #0
 sta.b 29
 bcc _wide_mul_pp_done_1_7
 lda.b 31
 adc #0
 sta.b 31
 bcc _wide_mul_pp_done_1_7
 sep #$20
 lda.b 33
 adc #0
 sta.b 33
 rep #$20
_wide_mul_pp_done_1_7:
_wide_mul_a_done_1:
 lda.b 4
 bne _wide_mul_a_nonzero_2
 jmp _wide_mul_a_done_2
_wide_mul_a_nonzero_2:
 xba
 sta.w core_m7_latch
 sta.w MPYA
 sta.w MPYA
 sep #$20
 lda.b 8
 bne _wide_mul_b_nonzero_2_0
 rep #$20
 jmp _wide_mul_pp_done_2_0
_wide_mul_b_nonzero_2_0:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_2_0
 lda #$ff
 bra _wide_mul_pp_sign_2_0
_wide_mul_pp_pos_2_0:
 lda #0
_wide_mul_pp_sign_2_0:
 sta.b 45
 lda.b 8
 bpl _wide_mul_b_unsigned_2_0
 rep #$20
 clc
 lda.b 43
 adc.b 4
 sta.b 43
 sep #$20
 lda #0
 bit.b 5
 bpl _wide_mul_a_ext_2_0
 lda #$ff
_wide_mul_a_ext_2_0:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_2_0:
 rep #$20
 lda.b 4
 bpl _wide_mul_a_unsigned_2_0
 lda.b 8
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_2_0:
 clc
 lda.b 42
 adc.b 20
 sta.b 20
 lda.b 44
 adc.b 22
 sta.b 22
 bcc _wide_mul_pp_done_2_0
 lda.b 24
 adc #0
 sta.b 24
 bcc _wide_mul_pp_done_2_0
 lda.b 26
 adc #0
 sta.b 26
 bcc _wide_mul_pp_done_2_0
 lda.b 28
 adc #0
 sta.b 28
 bcc _wide_mul_pp_done_2_0
 lda.b 30
 adc #0
 sta.b 30
 bcc _wide_mul_pp_done_2_0
 lda.b 32
 adc #0
 sta.b 32
_wide_mul_pp_done_2_0:
 sep #$20
 lda.b 9
 bne _wide_mul_b_nonzero_2_1
 rep #$20
 jmp _wide_mul_pp_done_2_1
_wide_mul_b_nonzero_2_1:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_2_1
 lda #$ff
 bra _wide_mul_pp_sign_2_1
_wide_mul_pp_pos_2_1:
 lda #0
_wide_mul_pp_sign_2_1:
 sta.b 45
 lda.b 9
 bpl _wide_mul_b_unsigned_2_1
 rep #$20
 clc
 lda.b 43
 adc.b 4
 sta.b 43
 sep #$20
 lda #0
 bit.b 5
 bpl _wide_mul_a_ext_2_1
 lda #$ff
_wide_mul_a_ext_2_1:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_2_1:
 rep #$20
 lda.b 4
 bpl _wide_mul_a_unsigned_2_1
 lda.b 9
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_2_1:
 clc
 lda.b 42
 adc.b 21
 sta.b 21
 lda.b 44
 adc.b 23
 sta.b 23
 bcc _wide_mul_pp_done_2_1
 lda.b 25
 adc #0
 sta.b 25
 bcc _wide_mul_pp_done_2_1
 lda.b 27
 adc #0
 sta.b 27
 bcc _wide_mul_pp_done_2_1
 lda.b 29
 adc #0
 sta.b 29
 bcc _wide_mul_pp_done_2_1
 lda.b 31
 adc #0
 sta.b 31
 bcc _wide_mul_pp_done_2_1
 sep #$20
 lda.b 33
 adc #0
 sta.b 33
 rep #$20
_wide_mul_pp_done_2_1:
 sep #$20
 lda.b 10
 bne _wide_mul_b_nonzero_2_2
 rep #$20
 jmp _wide_mul_pp_done_2_2
_wide_mul_b_nonzero_2_2:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_2_2
 lda #$ff
 bra _wide_mul_pp_sign_2_2
_wide_mul_pp_pos_2_2:
 lda #0
_wide_mul_pp_sign_2_2:
 sta.b 45
 lda.b 10
 bpl _wide_mul_b_unsigned_2_2
 rep #$20
 clc
 lda.b 43
 adc.b 4
 sta.b 43
 sep #$20
 lda #0
 bit.b 5
 bpl _wide_mul_a_ext_2_2
 lda #$ff
_wide_mul_a_ext_2_2:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_2_2:
 rep #$20
 lda.b 4
 bpl _wide_mul_a_unsigned_2_2
 lda.b 10
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_2_2:
 clc
 lda.b 42
 adc.b 22
 sta.b 22
 lda.b 44
 adc.b 24
 sta.b 24
 bcc _wide_mul_pp_done_2_2
 lda.b 26
 adc #0
 sta.b 26
 bcc _wide_mul_pp_done_2_2
 lda.b 28
 adc #0
 sta.b 28
 bcc _wide_mul_pp_done_2_2
 lda.b 30
 adc #0
 sta.b 30
 bcc _wide_mul_pp_done_2_2
 lda.b 32
 adc #0
 sta.b 32
_wide_mul_pp_done_2_2:
 sep #$20
 lda.b 11
 bne _wide_mul_b_nonzero_2_3
 rep #$20
 jmp _wide_mul_pp_done_2_3
_wide_mul_b_nonzero_2_3:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_2_3
 lda #$ff
 bra _wide_mul_pp_sign_2_3
_wide_mul_pp_pos_2_3:
 lda #0
_wide_mul_pp_sign_2_3:
 sta.b 45
 lda.b 11
 bpl _wide_mul_b_unsigned_2_3
 rep #$20
 clc
 lda.b 43
 adc.b 4
 sta.b 43
 sep #$20
 lda #0
 bit.b 5
 bpl _wide_mul_a_ext_2_3
 lda #$ff
_wide_mul_a_ext_2_3:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_2_3:
 rep #$20
 lda.b 4
 bpl _wide_mul_a_unsigned_2_3
 lda.b 11
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_2_3:
 clc
 lda.b 42
 adc.b 23
 sta.b 23
 lda.b 44
 adc.b 25
 sta.b 25
 bcc _wide_mul_pp_done_2_3
 lda.b 27
 adc #0
 sta.b 27
 bcc _wide_mul_pp_done_2_3
 lda.b 29
 adc #0
 sta.b 29
 bcc _wide_mul_pp_done_2_3
 lda.b 31
 adc #0
 sta.b 31
 bcc _wide_mul_pp_done_2_3
 sep #$20
 lda.b 33
 adc #0
 sta.b 33
 rep #$20
_wide_mul_pp_done_2_3:
 sep #$20
 lda.b 12
 bne _wide_mul_b_nonzero_2_4
 rep #$20
 jmp _wide_mul_pp_done_2_4
_wide_mul_b_nonzero_2_4:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_2_4
 lda #$ff
 bra _wide_mul_pp_sign_2_4
_wide_mul_pp_pos_2_4:
 lda #0
_wide_mul_pp_sign_2_4:
 sta.b 45
 lda.b 12
 bpl _wide_mul_b_unsigned_2_4
 rep #$20
 clc
 lda.b 43
 adc.b 4
 sta.b 43
 sep #$20
 lda #0
 bit.b 5
 bpl _wide_mul_a_ext_2_4
 lda #$ff
_wide_mul_a_ext_2_4:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_2_4:
 rep #$20
 lda.b 4
 bpl _wide_mul_a_unsigned_2_4
 lda.b 12
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_2_4:
 clc
 lda.b 42
 adc.b 24
 sta.b 24
 lda.b 44
 adc.b 26
 sta.b 26
 bcc _wide_mul_pp_done_2_4
 lda.b 28
 adc #0
 sta.b 28
 bcc _wide_mul_pp_done_2_4
 lda.b 30
 adc #0
 sta.b 30
 bcc _wide_mul_pp_done_2_4
 lda.b 32
 adc #0
 sta.b 32
_wide_mul_pp_done_2_4:
 sep #$20
 lda.b 13
 bne _wide_mul_b_nonzero_2_5
 rep #$20
 jmp _wide_mul_pp_done_2_5
_wide_mul_b_nonzero_2_5:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_2_5
 lda #$ff
 bra _wide_mul_pp_sign_2_5
_wide_mul_pp_pos_2_5:
 lda #0
_wide_mul_pp_sign_2_5:
 sta.b 45
 lda.b 13
 bpl _wide_mul_b_unsigned_2_5
 rep #$20
 clc
 lda.b 43
 adc.b 4
 sta.b 43
 sep #$20
 lda #0
 bit.b 5
 bpl _wide_mul_a_ext_2_5
 lda #$ff
_wide_mul_a_ext_2_5:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_2_5:
 rep #$20
 lda.b 4
 bpl _wide_mul_a_unsigned_2_5
 lda.b 13
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_2_5:
 clc
 lda.b 42
 adc.b 25
 sta.b 25
 lda.b 44
 adc.b 27
 sta.b 27
 bcc _wide_mul_pp_done_2_5
 lda.b 29
 adc #0
 sta.b 29
 bcc _wide_mul_pp_done_2_5
 lda.b 31
 adc #0
 sta.b 31
 bcc _wide_mul_pp_done_2_5
 sep #$20
 lda.b 33
 adc #0
 sta.b 33
 rep #$20
_wide_mul_pp_done_2_5:
 sep #$20
 lda.b 14
 bne _wide_mul_b_nonzero_2_6
 rep #$20
 jmp _wide_mul_pp_done_2_6
_wide_mul_b_nonzero_2_6:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_2_6
 lda #$ff
 bra _wide_mul_pp_sign_2_6
_wide_mul_pp_pos_2_6:
 lda #0
_wide_mul_pp_sign_2_6:
 sta.b 45
 lda.b 14
 bpl _wide_mul_b_unsigned_2_6
 rep #$20
 clc
 lda.b 43
 adc.b 4
 sta.b 43
 sep #$20
 lda #0
 bit.b 5
 bpl _wide_mul_a_ext_2_6
 lda #$ff
_wide_mul_a_ext_2_6:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_2_6:
 rep #$20
 lda.b 4
 bpl _wide_mul_a_unsigned_2_6
 lda.b 14
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_2_6:
 clc
 lda.b 42
 adc.b 26
 sta.b 26
 lda.b 44
 adc.b 28
 sta.b 28
 bcc _wide_mul_pp_done_2_6
 lda.b 30
 adc #0
 sta.b 30
 bcc _wide_mul_pp_done_2_6
 lda.b 32
 adc #0
 sta.b 32
_wide_mul_pp_done_2_6:
 sep #$20
 lda.b 15
 bne _wide_mul_b_nonzero_2_7
 rep #$20
 jmp _wide_mul_pp_done_2_7
_wide_mul_b_nonzero_2_7:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_2_7
 lda #$ff
 bra _wide_mul_pp_sign_2_7
_wide_mul_pp_pos_2_7:
 lda #0
_wide_mul_pp_sign_2_7:
 sta.b 45
 lda.b 15
 bpl _wide_mul_b_unsigned_2_7
 rep #$20
 clc
 lda.b 43
 adc.b 4
 sta.b 43
 sep #$20
 lda #0
 bit.b 5
 bpl _wide_mul_a_ext_2_7
 lda #$ff
_wide_mul_a_ext_2_7:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_2_7:
 rep #$20
 lda.b 4
 bpl _wide_mul_a_unsigned_2_7
 lda.b 15
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_2_7:
 clc
 lda.b 42
 adc.b 27
 sta.b 27
 lda.b 44
 adc.b 29
 sta.b 29
 bcc _wide_mul_pp_done_2_7
 lda.b 31
 adc #0
 sta.b 31
 bcc _wide_mul_pp_done_2_7
 sep #$20
 lda.b 33
 adc #0
 sta.b 33
 rep #$20
_wide_mul_pp_done_2_7:
_wide_mul_a_done_2:
 lda.b 6
 bne _wide_mul_a_nonzero_3
 jmp _wide_mul_a_done_3
_wide_mul_a_nonzero_3:
 xba
 sta.w core_m7_latch
 sta.w MPYA
 sta.w MPYA
 sep #$20
 lda.b 8
 bne _wide_mul_b_nonzero_3_0
 rep #$20
 jmp _wide_mul_pp_done_3_0
_wide_mul_b_nonzero_3_0:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_3_0
 lda #$ff
 bra _wide_mul_pp_sign_3_0
_wide_mul_pp_pos_3_0:
 lda #0
_wide_mul_pp_sign_3_0:
 sta.b 45
 lda.b 8
 bpl _wide_mul_b_unsigned_3_0
 rep #$20
 clc
 lda.b 43
 adc.b 6
 sta.b 43
 sep #$20
 lda #0
 bit.b 7
 bpl _wide_mul_a_ext_3_0
 lda #$ff
_wide_mul_a_ext_3_0:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_3_0:
 rep #$20
 lda.b 6
 bpl _wide_mul_a_unsigned_3_0
 lda.b 8
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_3_0:
 clc
 lda.b 42
 adc.b 22
 sta.b 22
 lda.b 44
 adc.b 24
 sta.b 24
 bcc _wide_mul_pp_done_3_0
 lda.b 26
 adc #0
 sta.b 26
 bcc _wide_mul_pp_done_3_0
 lda.b 28
 adc #0
 sta.b 28
 bcc _wide_mul_pp_done_3_0
 lda.b 30
 adc #0
 sta.b 30
 bcc _wide_mul_pp_done_3_0
 lda.b 32
 adc #0
 sta.b 32
_wide_mul_pp_done_3_0:
 sep #$20
 lda.b 9
 bne _wide_mul_b_nonzero_3_1
 rep #$20
 jmp _wide_mul_pp_done_3_1
_wide_mul_b_nonzero_3_1:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_3_1
 lda #$ff
 bra _wide_mul_pp_sign_3_1
_wide_mul_pp_pos_3_1:
 lda #0
_wide_mul_pp_sign_3_1:
 sta.b 45
 lda.b 9
 bpl _wide_mul_b_unsigned_3_1
 rep #$20
 clc
 lda.b 43
 adc.b 6
 sta.b 43
 sep #$20
 lda #0
 bit.b 7
 bpl _wide_mul_a_ext_3_1
 lda #$ff
_wide_mul_a_ext_3_1:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_3_1:
 rep #$20
 lda.b 6
 bpl _wide_mul_a_unsigned_3_1
 lda.b 9
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_3_1:
 clc
 lda.b 42
 adc.b 23
 sta.b 23
 lda.b 44
 adc.b 25
 sta.b 25
 bcc _wide_mul_pp_done_3_1
 lda.b 27
 adc #0
 sta.b 27
 bcc _wide_mul_pp_done_3_1
 lda.b 29
 adc #0
 sta.b 29
 bcc _wide_mul_pp_done_3_1
 lda.b 31
 adc #0
 sta.b 31
 bcc _wide_mul_pp_done_3_1
 sep #$20
 lda.b 33
 adc #0
 sta.b 33
 rep #$20
_wide_mul_pp_done_3_1:
 sep #$20
 lda.b 10
 bne _wide_mul_b_nonzero_3_2
 rep #$20
 jmp _wide_mul_pp_done_3_2
_wide_mul_b_nonzero_3_2:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_3_2
 lda #$ff
 bra _wide_mul_pp_sign_3_2
_wide_mul_pp_pos_3_2:
 lda #0
_wide_mul_pp_sign_3_2:
 sta.b 45
 lda.b 10
 bpl _wide_mul_b_unsigned_3_2
 rep #$20
 clc
 lda.b 43
 adc.b 6
 sta.b 43
 sep #$20
 lda #0
 bit.b 7
 bpl _wide_mul_a_ext_3_2
 lda #$ff
_wide_mul_a_ext_3_2:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_3_2:
 rep #$20
 lda.b 6
 bpl _wide_mul_a_unsigned_3_2
 lda.b 10
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_3_2:
 clc
 lda.b 42
 adc.b 24
 sta.b 24
 lda.b 44
 adc.b 26
 sta.b 26
 bcc _wide_mul_pp_done_3_2
 lda.b 28
 adc #0
 sta.b 28
 bcc _wide_mul_pp_done_3_2
 lda.b 30
 adc #0
 sta.b 30
 bcc _wide_mul_pp_done_3_2
 lda.b 32
 adc #0
 sta.b 32
_wide_mul_pp_done_3_2:
 sep #$20
 lda.b 11
 bne _wide_mul_b_nonzero_3_3
 rep #$20
 jmp _wide_mul_pp_done_3_3
_wide_mul_b_nonzero_3_3:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_3_3
 lda #$ff
 bra _wide_mul_pp_sign_3_3
_wide_mul_pp_pos_3_3:
 lda #0
_wide_mul_pp_sign_3_3:
 sta.b 45
 lda.b 11
 bpl _wide_mul_b_unsigned_3_3
 rep #$20
 clc
 lda.b 43
 adc.b 6
 sta.b 43
 sep #$20
 lda #0
 bit.b 7
 bpl _wide_mul_a_ext_3_3
 lda #$ff
_wide_mul_a_ext_3_3:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_3_3:
 rep #$20
 lda.b 6
 bpl _wide_mul_a_unsigned_3_3
 lda.b 11
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_3_3:
 clc
 lda.b 42
 adc.b 25
 sta.b 25
 lda.b 44
 adc.b 27
 sta.b 27
 bcc _wide_mul_pp_done_3_3
 lda.b 29
 adc #0
 sta.b 29
 bcc _wide_mul_pp_done_3_3
 lda.b 31
 adc #0
 sta.b 31
 bcc _wide_mul_pp_done_3_3
 sep #$20
 lda.b 33
 adc #0
 sta.b 33
 rep #$20
_wide_mul_pp_done_3_3:
 sep #$20
 lda.b 12
 bne _wide_mul_b_nonzero_3_4
 rep #$20
 jmp _wide_mul_pp_done_3_4
_wide_mul_b_nonzero_3_4:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_3_4
 lda #$ff
 bra _wide_mul_pp_sign_3_4
_wide_mul_pp_pos_3_4:
 lda #0
_wide_mul_pp_sign_3_4:
 sta.b 45
 lda.b 12
 bpl _wide_mul_b_unsigned_3_4
 rep #$20
 clc
 lda.b 43
 adc.b 6
 sta.b 43
 sep #$20
 lda #0
 bit.b 7
 bpl _wide_mul_a_ext_3_4
 lda #$ff
_wide_mul_a_ext_3_4:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_3_4:
 rep #$20
 lda.b 6
 bpl _wide_mul_a_unsigned_3_4
 lda.b 12
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_3_4:
 clc
 lda.b 42
 adc.b 26
 sta.b 26
 lda.b 44
 adc.b 28
 sta.b 28
 bcc _wide_mul_pp_done_3_4
 lda.b 30
 adc #0
 sta.b 30
 bcc _wide_mul_pp_done_3_4
 lda.b 32
 adc #0
 sta.b 32
_wide_mul_pp_done_3_4:
 sep #$20
 lda.b 13
 bne _wide_mul_b_nonzero_3_5
 rep #$20
 jmp _wide_mul_pp_done_3_5
_wide_mul_b_nonzero_3_5:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_3_5
 lda #$ff
 bra _wide_mul_pp_sign_3_5
_wide_mul_pp_pos_3_5:
 lda #0
_wide_mul_pp_sign_3_5:
 sta.b 45
 lda.b 13
 bpl _wide_mul_b_unsigned_3_5
 rep #$20
 clc
 lda.b 43
 adc.b 6
 sta.b 43
 sep #$20
 lda #0
 bit.b 7
 bpl _wide_mul_a_ext_3_5
 lda #$ff
_wide_mul_a_ext_3_5:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_3_5:
 rep #$20
 lda.b 6
 bpl _wide_mul_a_unsigned_3_5
 lda.b 13
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_3_5:
 clc
 lda.b 42
 adc.b 27
 sta.b 27
 lda.b 44
 adc.b 29
 sta.b 29
 bcc _wide_mul_pp_done_3_5
 lda.b 31
 adc #0
 sta.b 31
 bcc _wide_mul_pp_done_3_5
 sep #$20
 lda.b 33
 adc #0
 sta.b 33
 rep #$20
_wide_mul_pp_done_3_5:
 sep #$20
 lda.b 14
 bne _wide_mul_b_nonzero_3_6
 rep #$20
 jmp _wide_mul_pp_done_3_6
_wide_mul_b_nonzero_3_6:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_3_6
 lda #$ff
 bra _wide_mul_pp_sign_3_6
_wide_mul_pp_pos_3_6:
 lda #0
_wide_mul_pp_sign_3_6:
 sta.b 45
 lda.b 14
 bpl _wide_mul_b_unsigned_3_6
 rep #$20
 clc
 lda.b 43
 adc.b 6
 sta.b 43
 sep #$20
 lda #0
 bit.b 7
 bpl _wide_mul_a_ext_3_6
 lda #$ff
_wide_mul_a_ext_3_6:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_3_6:
 rep #$20
 lda.b 6
 bpl _wide_mul_a_unsigned_3_6
 lda.b 14
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_3_6:
 clc
 lda.b 42
 adc.b 28
 sta.b 28
 lda.b 44
 adc.b 30
 sta.b 30
 bcc _wide_mul_pp_done_3_6
 lda.b 32
 adc #0
 sta.b 32
_wide_mul_pp_done_3_6:
 sep #$20
 lda.b 15
 bne _wide_mul_b_nonzero_3_7
 rep #$20
 jmp _wide_mul_pp_done_3_7
_wide_mul_b_nonzero_3_7:
 sta.w MPYB
 rep #$20
 lda.w MPYL
 sta.b 42
 sep #$20
 lda.w MPYH
 sta.b 44
 bpl _wide_mul_pp_pos_3_7
 lda #$ff
 bra _wide_mul_pp_sign_3_7
_wide_mul_pp_pos_3_7:
 lda #0
_wide_mul_pp_sign_3_7:
 sta.b 45
 lda.b 15
 bpl _wide_mul_b_unsigned_3_7
 rep #$20
 clc
 lda.b 43
 adc.b 6
 sta.b 43
 sep #$20
 lda #0
 bit.b 7
 bpl _wide_mul_a_ext_3_7
 lda #$ff
_wide_mul_a_ext_3_7:
 adc.b 45
 sta.b 45
_wide_mul_b_unsigned_3_7:
 rep #$20
 lda.b 6
 bpl _wide_mul_a_unsigned_3_7
 lda.b 15
 and #$00ff
 clc
 adc.b 44
 sta.b 44
_wide_mul_a_unsigned_3_7:
 clc
 lda.b 42
 adc.b 29
 sta.b 29
 lda.b 44
 adc.b 31
 sta.b 31
 bcc _wide_mul_pp_done_3_7
 sep #$20
 lda.b 33
 adc #0
 sta.b 33
 rep #$20
_wide_mul_pp_done_3_7:
_wide_mul_a_done_3:
 lda.b 48
 bne _wide_mul_not_integer
 lda.b 16
 sta.b 34
 lda.b 18
 sta.b 36
 lda.b 20
 sta.b 38
 lda.b 22
 sta.b 40
 lda.b 24
 ora.b 26
 ora.b 28
 ora.b 30
 ora.b 32
 beq _wide_mul_integer_fits
 jmp _wide_mul_overflow
_wide_mul_integer_fits:
 jmp _wide_mul_round_done
_wide_mul_not_integer:
 cmp #48
 bne _wide_mul_not_48
 lda.b 22
 sta.b 34
 lda.b 24
 sta.b 36
 lda.b 26
 sta.b 38
 lda.b 28
 sta.b 40
 lda.b 30
 ora.b 32
 beq _wide_mul_48_fits
 jmp _wide_mul_overflow
_wide_mul_48_fits:
 sep #$20
 lda.b 21
 and #$80
 rep #$20
 bne _wide_mul_48_round_up
 jmp _wide_mul_round_done
_wide_mul_48_round_up:
 jmp _wide_mul_round_up
_wide_mul_not_48:
 cmp #40
 bne _wide_mul_shift44
 lda.b 21
 sta.b 34
 lda.b 23
 sta.b 36
 lda.b 25
 sta.b 38
 lda.b 27
 sta.b 40
 lda.b 29
 ora.b 31
 bne _wide_mul_overflow40
 sep #$20
 lda.b 33
 bne _wide_mul_overflow40
 lda.b 20
 and #$80
 rep #$20
 bne _wide_mul_round40_up
 jmp _wide_mul_round_done
_wide_mul_round40_up:
 jmp _wide_mul_round_up
_wide_mul_overflow40:
 rep #$20
 jmp _wide_mul_overflow
_wide_mul_shift44:
 lda.b 21
 lsr a
 lsr a
 lsr a
 lsr a
 sta.b 34
 lda.b 23
 and #$000f
 xba
 asl a
 asl a
 asl a
 asl a
 ora.b 34
 sta.b 34
 lda.b 23
 lsr a
 lsr a
 lsr a
 lsr a
 sta.b 36
 lda.b 25
 and #$000f
 xba
 asl a
 asl a
 asl a
 asl a
 ora.b 36
 sta.b 36
 lda.b 25
 lsr a
 lsr a
 lsr a
 lsr a
 sta.b 38
 lda.b 27
 and #$000f
 xba
 asl a
 asl a
 asl a
 asl a
 ora.b 38
 sta.b 38
 lda.b 27
 lsr a
 lsr a
 lsr a
 lsr a
 sta.b 40
 lda.b 29
 and #$000f
 xba
 asl a
 asl a
 asl a
 asl a
 ora.b 40
 sta.b 40
 lda.b 29
 and #$fff0
 ora.b 31
 bne _wide_mul_overflow44
 sep #$20
 lda.b 33
 bne _wide_mul_overflow44
 lda.b 21
 and #8
 rep #$20
 beq _wide_mul_round_done
 bra _wide_mul_round_up
_wide_mul_overflow44:
 rep #$20
 jmp _wide_mul_overflow
_wide_mul_round_up:
 sec
 lda.b 34
 adc #0
 sta.b 34
 lda.b 36
 adc #0
 sta.b 36
 lda.b 38
 adc #0
 sta.b 38
 lda.b 40
 adc #0
 sta.b 40
 bcs _wide_mul_overflow
_wide_mul_round_done:
 lda.b 46
 bne _wide_mul_negative
 lda.b 40
 bmi _wide_mul_overflow
 bra _wide_mul_store
_wide_mul_negative:
 lda.b 40
 cmp #$8000
 bcc _wide_mul_negate
 bne _wide_mul_overflow
 lda.b 34
 ora.b 36
 ora.b 38
 bne _wide_mul_overflow
_wide_mul_negate:
 sec
 lda #0
 sbc.b 34
 sta.b 34
 lda #0
 sbc.b 36
 sta.b 36
 lda #0
 sbc.b 38
 sta.b 38
 lda #0
 sbc.b 40
 sta.b 40
_wide_mul_store:
 sep #$20
 lda #$7e
 pha
 plb
 rep #$20
 lda.b 54
 tax
 lda.b 34
 sta.w 0,x
 lda.b 36
 sta.w 2,x
 lda.b 38
 sta.w 4,x
 lda.b 40
 sta.w 6,x
 bra _wide_mul_return
_wide_mul_overflow:
 lda #1
 sta.b 50
_wide_mul_return:
 sep #$20
 lda #$7e
 pha
 plb
 rep #$20
 lda.b 56
 tax
 lda.b 50
 sta.w 0,x
 ply
 plx
 pld
 plb
 plp
 rtl
; Exact nearest-half-away ((signed64 a << fraction) / signed64 b).
wide_div64:
 php
 phb
 phd
 rep #$30
 phx
 phy
 pea wide_native_math_dp
 pld
 sep #$20
 lda #$7e
 pha
 plb
 rep #$20
 lda 22,s
 sta.b 54
 lda 26,s
 sta.b 56
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
 lda 20,s
 sta.b 48
 stz.b 50
 cmp #0
 beq _wide_div_fraction_ok
 cmp #48
 beq _wide_div_fraction_ok
 cmp #40
 beq _wide_div_fraction_ok
 cmp #44
 beq _wide_div_fraction_ok
 jmp _wide_div_domain
_wide_div_fraction_ok:
 lda.b 8
 ora.b 10
 ora.b 12
 ora.b 14
 bne _wide_div_nonzero
 jmp _wide_div_domain
_wide_div_nonzero:
 lda.b 6
 eor.b 14
 and #$8000
 sta.b 46
 lda.b 6
 bpl _wide_div_a_abs
 sec
 lda #0
 sbc.b 0
 sta.b 0
 lda #0
 sbc.b 2
 sta.b 2
 lda #0
 sbc.b 4
 sta.b 4
 lda #0
 sbc.b 6
 sta.b 6
_wide_div_a_abs:
 lda.b 14
 bpl _wide_div_b_abs
 sec
 lda #0
 sbc.b 8
 sta.b 8
 lda #0
 sbc.b 10
 sta.b 10
 lda #0
 sbc.b 12
 sta.b 12
 lda #0
 sbc.b 14
 sta.b 14
_wide_div_b_abs:
 jsr _wide_math_setup_n
 stz.b 64
 stz.b 66
 stz.b 68
 stz.b 70
 stz.b 72
 ldx #128
 lda.b 16
 ora.b 18
 ora.b 20
 ora.b 22
 ora.b 24
 ora.b 26
 ora.b 28
 ora.b 30
 bne _wide_div_leading_word
 jmp _wide_div_bits_done
_wide_div_leading_word:
 lda.b 30
 bne _wide_div_leading_bits
 lda.b 28
 sta.b 30
 lda.b 26
 sta.b 28
 lda.b 24
 sta.b 26
 lda.b 22
 sta.b 24
 lda.b 20
 sta.b 22
 lda.b 18
 sta.b 20
 lda.b 16
 sta.b 18
 stz.b 16
 txa
 sec
 sbc #16
 tax
 bra _wide_div_leading_word
_wide_div_leading_bits:
 lda.b 30
 and #$8000
 bne _wide_div_bit
 asl.b 16
 rol.b 18
 rol.b 20
 rol.b 22
 rol.b 24
 rol.b 26
 rol.b 28
 rol.b 30
 dex
 bra _wide_div_leading_bits
_wide_div_bit:
 asl.b 16
 rol.b 18
 rol.b 20
 rol.b 22
 rol.b 24
 rol.b 26
 rol.b 28
 rol.b 30
 rol.b 64
 rol.b 66
 rol.b 68
 rol.b 70
 rol.b 72
 lda.b 72
 bne _wide_div_remainder_subtract
 lda.b 70
 cmp.b 14
 bcc _wide_div_remainder_less
 bne _wide_div_remainder_subtract
 lda.b 68
 cmp.b 12
 bcc _wide_div_remainder_less
 bne _wide_div_remainder_subtract
 lda.b 66
 cmp.b 10
 bcc _wide_div_remainder_less
 bne _wide_div_remainder_subtract
 lda.b 64
 cmp.b 8
 bcc _wide_div_remainder_less
 bne _wide_div_remainder_subtract
 bra _wide_div_remainder_subtract
_wide_div_remainder_subtract:
 sec
 lda.b 64
 sbc.b 8
 sta.b 64
 lda.b 66
 sbc.b 10
 sta.b 66
 lda.b 68
 sbc.b 12
 sta.b 68
 lda.b 70
 sbc.b 14
 sta.b 70
 lda.b 72
 sbc #0
 sta.b 72
 inc.b 16
_wide_div_remainder_less:
 dex
 beq _wide_div_bits_done
 jmp _wide_div_bit
_wide_div_bits_done:
 lda.b 16
 sta.b 34
 lda.b 18
 sta.b 36
 lda.b 20
 sta.b 38
 lda.b 22
 sta.b 40
 lda.b 24
 ora.b 26
 ora.b 28
 ora.b 30
 beq _wide_div_quotient_fits
 jmp _wide_mul_overflow
_wide_div_quotient_fits:
 asl.b 64
 rol.b 66
 rol.b 68
 rol.b 70
 rol.b 72
 lda.b 72
 bne _wide_div_round_subtract
 lda.b 70
 cmp.b 14
 bcc _wide_div_round_less
 bne _wide_div_round_subtract
 lda.b 68
 cmp.b 12
 bcc _wide_div_round_less
 bne _wide_div_round_subtract
 lda.b 66
 cmp.b 10
 bcc _wide_div_round_less
 bne _wide_div_round_subtract
 lda.b 64
 cmp.b 8
 bcc _wide_div_round_less
 bne _wide_div_round_subtract
 bra _wide_div_round_subtract
_wide_div_round_subtract:
 jmp _wide_mul_round_up
_wide_div_round_less:
 jmp _wide_mul_round_done
_wide_div_domain:
 lda #2
 sta.b 50
 jmp _wide_mul_return
_wide_math_setup_n:
 stz.b 16
 stz.b 18
 stz.b 20
 stz.b 22
 stz.b 24
 stz.b 26
 stz.b 28
 stz.b 30
 lda.b 48
 bne _wide_math_n_fractional
 lda.b 0
 sta.b 16
 lda.b 2
 sta.b 18
 lda.b 4
 sta.b 20
 lda.b 6
 sta.b 22
 rts
_wide_math_n_fractional:
 cmp #48
 bne _wide_math_n_40_44
 lda.b 0
 sta.b 22
 lda.b 2
 sta.b 24
 lda.b 4
 sta.b 26
 lda.b 6
 sta.b 28
 rts
_wide_math_n_40_44:
 lda.b 0
 sta.b 21
 lda.b 2
 sta.b 23
 lda.b 4
 sta.b 25
 lda.b 6
 sta.b 27
 lda.b 48
 cmp #40
 beq _wide_math_n_ready
 ldx #4
_wide_math_n_shift4:
 asl.b 16
 rol.b 18
 rol.b 20
 rol.b 22
 rol.b 24
 rol.b 26
 rol.b 28
 rol.b 30
 dex
 bne _wide_math_n_shift4
_wide_math_n_ready:
 rts

; sqrt(round-independent a<<fraction), rounded to nearest integer root.
wide_sqrt64:
 php
 phb
 phd
 rep #$30
 phx
 phy
 pea wide_native_math_dp
 pld
 sep #$20
 lda #$7e
 pha
 plb
 rep #$20
 lda 18,s
 sta.b 54
 lda 22,s
 sta.b 56
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
 sta.b 48
 stz.b 50
 cmp #0
 beq _wide_sqrt_fraction_ok
 cmp #48
 beq _wide_sqrt_fraction_ok
 cmp #40
 beq _wide_sqrt_fraction_ok
 cmp #44
 beq _wide_sqrt_fraction_ok
 jmp _wide_sqrt_domain
_wide_sqrt_fraction_ok:
 stz.b 46
 lda.b 6
 bpl _wide_sqrt_nonnegative
 jmp _wide_sqrt_domain
_wide_sqrt_nonnegative:
 jsr _wide_math_setup_n
 stz.b 64
 stz.b 66
 stz.b 68
 stz.b 70
 stz.b 72
 stz.b 34
 stz.b 36
 stz.b 38
 stz.b 40
 ldx #64
 lda.b 16
 ora.b 18
 ora.b 20
 ora.b 22
 ora.b 24
 ora.b 26
 ora.b 28
 ora.b 30
 bne _wide_sqrt_leading_word
 jmp _wide_sqrt_pairs_done
_wide_sqrt_leading_word:
 lda.b 30
 bne _wide_sqrt_leading_bits
 lda.b 28
 sta.b 30
 lda.b 26
 sta.b 28
 lda.b 24
 sta.b 26
 lda.b 22
 sta.b 24
 lda.b 20
 sta.b 22
 lda.b 18
 sta.b 20
 lda.b 16
 sta.b 18
 stz.b 16
 txa
 sec
 sbc #8
 tax
 bra _wide_sqrt_leading_word
_wide_sqrt_leading_bits:
 lda.b 30
 and #$c000
 bne _wide_sqrt_pair
 asl.b 16
 rol.b 18
 rol.b 20
 rol.b 22
 rol.b 24
 rol.b 26
 rol.b 28
 rol.b 30
 asl.b 16
 rol.b 18
 rol.b 20
 rol.b 22
 rol.b 24
 rol.b 26
 rol.b 28
 rol.b 30
 dex
 bra _wide_sqrt_leading_bits
_wide_sqrt_pair:
 asl.b 16
 rol.b 18
 rol.b 20
 rol.b 22
 rol.b 24
 rol.b 26
 rol.b 28
 rol.b 30
 rol.b 64
 rol.b 66
 rol.b 68
 rol.b 70
 rol.b 72
 asl.b 16
 rol.b 18
 rol.b 20
 rol.b 22
 rol.b 24
 rol.b 26
 rol.b 28
 rol.b 30
 rol.b 64
 rol.b 66
 rol.b 68
 rol.b 70
 rol.b 72
 asl.b 34
 rol.b 36
 rol.b 38
 rol.b 40
 lda.b 34
 sta.b 80
 lda.b 36
 sta.b 82
 lda.b 38
 sta.b 84
 lda.b 40
 sta.b 86
 stz.b 88
 sec
 rol.b 80
 rol.b 82
 rol.b 84
 rol.b 86
 rol.b 88
 lda.b 72
 cmp.b 88
 bcc _wide_sqrt_remainder_less
 bne _wide_sqrt_remainder_subtract
 lda.b 70
 cmp.b 86
 bcc _wide_sqrt_remainder_less
 bne _wide_sqrt_remainder_subtract
 lda.b 68
 cmp.b 84
 bcc _wide_sqrt_remainder_less
 bne _wide_sqrt_remainder_subtract
 lda.b 66
 cmp.b 82
 bcc _wide_sqrt_remainder_less
 bne _wide_sqrt_remainder_subtract
 lda.b 64
 cmp.b 80
 bcc _wide_sqrt_remainder_less
 bne _wide_sqrt_remainder_subtract
 bra _wide_sqrt_remainder_subtract
_wide_sqrt_remainder_subtract:
 sec
 lda.b 64
 sbc.b 80
 sta.b 64
 lda.b 66
 sbc.b 82
 sta.b 66
 lda.b 68
 sbc.b 84
 sta.b 68
 lda.b 70
 sbc.b 86
 sta.b 70
 lda.b 72
 sbc.b 88
 sta.b 72
 inc.b 34
_wide_sqrt_remainder_less:
 dex
 beq _wide_sqrt_pairs_done
 jmp _wide_sqrt_pair
_wide_sqrt_pairs_done:
 lda.b 72
 bne _wide_sqrt_round_up
 lda.b 70
 cmp.b 40
 bcc _wide_sqrt_round_down
 bne _wide_sqrt_round_up
 lda.b 68
 cmp.b 38
 bcc _wide_sqrt_round_down
 bne _wide_sqrt_round_up
 lda.b 66
 cmp.b 36
 bcc _wide_sqrt_round_down
 bne _wide_sqrt_round_up
 lda.b 64
 cmp.b 34
 bcc _wide_sqrt_round_down
 bne _wide_sqrt_round_up
_wide_sqrt_round_down:
 jmp _wide_mul_round_done
_wide_sqrt_round_up:
 jmp _wide_mul_round_up
_wide_sqrt_domain:
 lda #2
 sta.b 50
 jmp _wide_mul_return
.ENDS
