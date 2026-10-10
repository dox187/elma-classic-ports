; Experimental exact root residual correction; no production calls.
; void wide_root_correct(const u16* estimate, const u16* residual,
;                        u16 limit, u16* out, u16* status);
; estimate unsigned64 with 256<=estimate<2^48; residual signed64 N-estimate^2.
; limit<=256 guarantees bounded correction; guard failures use status2.
; Returns frozen wp_abs nearest-sqrt plus post-root Newton correction.
; status0 exact,2 guard/budget fallback with output unchanged.
; Input residual must be formed exactly; intermediate addition stays signed64.
; Own named DP. WRAM7E buffers, 4-byte C pointers, preserves D/DB/X/Y/P.
.RAMSECTION ".wide_root_correct_ram" BANK 0 SLOT 1 ALIGN 256
wide_root_correct_dp dsb 256
.ENDS
.MACRO WRC_DELTA
 clc
 lda.b 0
 rol a
 sta.b 16
 lda.b 2
 rol a
 sta.b 18
 lda.b 4
 rol a
 sta.b 20
 lda.b 6
 rol a
 sta.b 22
 inc.b 16
.ENDM
.SECTION ".wide_root_correct_text" SUPERFREE
wide_root_correct:
 php
 phb
 phd
 rep #$30
 phx
 phy
 pea wide_root_correct_dp
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
 lda 20,s
 sta.b 28
 stz.b 24
 stz.b 26
wide_root_correct_core_begin:
 lda.b 28
 cmp #257
 bcs _wrc_bad_entry
 lda.b 6
 bne _wrc_bad_entry
 lda.b 2
 ora.b 4
 bne _wrc_loop
 lda.b 0
 cmp #256
 bcs _wrc_loop
_wrc_bad_entry:
 jmp _wrc_fallback
_wrc_loop:
 WRC_DELTA
 lda.b 14
 bpl _wrc_positive
 jmp _wrc_negative
_wrc_positive:
 lda.b 14
 cmp.b 22
 bcs _wrc_ge_6
 jmp _wrc_floor_done
_wrc_ge_6:
 bne _wrc_increment
 lda.b 12
 cmp.b 20
 bcs _wrc_ge_4
 jmp _wrc_floor_done
_wrc_ge_4:
 bne _wrc_increment
 lda.b 10
 cmp.b 18
 bcs _wrc_ge_2
 jmp _wrc_floor_done
_wrc_ge_2:
 bne _wrc_increment
 lda.b 8
 cmp.b 16
 bcs _wrc_ge_0
 jmp _wrc_floor_done
_wrc_ge_0:
 bra _wrc_increment
_wrc_increment:
 lda.b 24
 cmp.b 28
 bcc _wrc_increment_allowed
 jmp _wrc_fallback
_wrc_increment_allowed:
 inc.b 24
 sec
 lda.b 8
 sbc.b 16
 sta.b 8
 lda.b 10
 sbc.b 18
 sta.b 10
 lda.b 12
 sbc.b 20
 sta.b 12
 lda.b 14
 sbc.b 22
 sta.b 14
 clc
 lda.b 0
 adc #1
 sta.b 0
 lda.b 2
 adc #0
 sta.b 2
 lda.b 4
 adc #0
 sta.b 4
 lda.b 6
 adc #0
 sta.b 6
 jmp _wrc_loop
_wrc_negative:
 lda.b 24
 cmp.b 28
 bcc _wrc_decrement_allowed
 jmp _wrc_fallback
_wrc_decrement_allowed:
 inc.b 24
 sec
 lda.b 16
 sbc #2
 sta.b 16
 lda.b 18
 sbc #0
 sta.b 18
 lda.b 20
 sbc #0
 sta.b 20
 lda.b 22
 sbc #0
 sta.b 22
 clc
 lda.b 8
 adc.b 16
 sta.b 8
 lda.b 10
 adc.b 18
 sta.b 10
 lda.b 12
 adc.b 20
 sta.b 12
 lda.b 14
 adc.b 22
 sta.b 14
 sec
 lda.b 0
 sbc #1
 sta.b 0
 lda.b 2
 sbc #0
 sta.b 2
 lda.b 4
 sbc #0
 sta.b 4
 lda.b 6
 sbc #0
 sta.b 6
 jmp _wrc_loop
_wrc_floor_done:
 lda.b 0
 ora.b 2
 ora.b 4
 ora.b 6
 bne _wrc_nonzero_root
 jmp _wrc_fallback
_wrc_nonzero_root:
 lda.b 14
 cmp.b 6
 bcc _wrc_residual_correct
 bne _wrc_nearest_increment
 lda.b 12
 cmp.b 4
 bcc _wrc_residual_correct
 bne _wrc_nearest_increment
 lda.b 10
 cmp.b 2
 bcc _wrc_residual_correct
 bne _wrc_nearest_increment
 lda.b 8
 cmp.b 0
 bcc _wrc_residual_correct
 beq _wrc_residual_correct
_wrc_nearest_increment:
 sec
 lda.b 8
 sbc.b 16
 sta.b 8
 lda.b 10
 sbc.b 18
 sta.b 10
 lda.b 12
 sbc.b 20
 sta.b 12
 lda.b 14
 sbc.b 22
 sta.b 14
 clc
 lda.b 0
 adc #1
 sta.b 0
 lda.b 2
 adc #0
 sta.b 2
 lda.b 4
 adc #0
 sta.b 4
 lda.b 6
 adc #0
 sta.b 6
_wrc_residual_correct:
 lda.b 14
 bmi _wrc_success
 clc
 lda.b 8
 rol a
 sta.b 16
 lda.b 10
 rol a
 sta.b 18
 lda.b 12
 rol a
 sta.b 20
 lda.b 14
 rol a
 sta.b 22
 lda.b 22
 cmp.b 6
 bcc _wrc_success
 bne _wrc_final_increment
 lda.b 20
 cmp.b 4
 bcc _wrc_success
 bne _wrc_final_increment
 lda.b 18
 cmp.b 2
 bcc _wrc_success
 bne _wrc_final_increment
 lda.b 16
 cmp.b 0
 bcc _wrc_success
 bra _wrc_final_increment
_wrc_final_increment:
 clc
 lda.b 0
 adc #1
 sta.b 0
 lda.b 2
 adc #0
 sta.b 2
 lda.b 4
 adc #0
 sta.b 4
 lda.b 6
 adc #0
 sta.b 6
_wrc_success:
 bra wide_root_correct_core_end
_wrc_fallback:
 lda #2
 sta.b 26
wide_root_correct_core_end:
 lda.b 26
 bne _wrc_status
 lda 22,s
 tax
 lda.b 0
 sta.w 0,x
 lda.b 2
 sta.w 2,x
 lda.b 4
 sta.w 4,x
 lda.b 6
 sta.w 6,x
_wrc_status:
 lda 26,s
 tax
 lda.b 26
 sta.w 0,x
 ply
 plx
 pld
 plb
 plp
 rtl
.ENDS
