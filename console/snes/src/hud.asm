; Compact sprite HUD: outlined elapsed/best time and remaining apples.
; hud_show_map is retained for saved button bindings; it toggles the counter.
; No BG3, window registers, level geometry, WRAM map buffer or frame DMA.
.include "hdr.asm"
.include "core.inc"
.include "hud.inc"
.DEFINE HUD_MAGIC $5A17
.DEFINE HUD_ATTR $3D00             ; priority 3, OBJ palette 6, tiles 256+
.ENUM $00
D_T0 dw
D_T1 dw
D_T2 dw
D_T3 dw
D_T4 dw
D_T5 dw
D_TLO dw
D_THI dw
D_BLO dw
D_BHI dw
D_END db
.ENDE
.RAMSECTION ".hud_dp" BANK 0 SLOT 1 ALIGN 256
hud_dp dsb D_END
.ENDS
.RAMSECTION ".hud_vars" BANK 0 SLOT 1
hud_show_time db
hud_show_map db
hud_magic dw
hud_xyok dw
hud_best_ok dw
hud_best_lo dw
hud_best_hi dw
hud_bdirty dw
hud_tok dw
hud_tprev_lo dw
hud_tprev_hi dw
hud_tm dw
hud_ts dw
hud_th dw
hud_tile dsw 14                  ; best, now, remaining apples
.ENDS
.SECTION ".hud_text" SUPERFREE

; void hud_load(u16 level). Called in forced blank; level is now unused.
hud_load:
 php
 phb
 phd
 rep #$30
 pea hud_dp
 pld
 sep #$20
 lda.b #$7E
 pha
 plb
 rep #$20
 lda hud_magic
 cmp.w #HUD_MAGIC
 beq +
 lda.w #HUD_MAGIC
 sta hud_magic
 sep #$20
 lda.b #1
 sta hud_show_time
 sta hud_show_map
 rep #$20
+
 pea HUD_SPRITE_BYTES
 pea :hud_sprite_tiles
 pea hud_sprite_tiles
 pea VRAM_OBJ+256*16
 jsl core_vram_now
 tsc
 clc
 adc.w #8
 tcs
 pea 32
 pea :hud_obj_colors
 pea hud_obj_colors
 pea 128+6*16
 jsl core_cgram_now
 tsc
 clc
 adc.w #8
 tcs
 ; Clear the former minimap's OAM too on level transitions.
 ldx.w #0
 lda.w #$E000
- sta.l core_oam,x
 inx
 inx
 inx
 inx
 cpx.w #24*4
 bcc -
 lda.w #0
 sta.l core_oam+512
 sta.l core_oam+514
 sta.l core_oam+516
 stz hud_xyok
 stz hud_best_ok
 stz hud_bdirty
 stz hud_tok
 pld
 plb
 plp
 rtl

; ABI retains camera/baljobb arguments; only time and best are consumed.
hud_draw:
 php
 phb
 phd
 rep #$30
 pea hud_dp
 pld
 sep #$20
 lda.b #$7E
 pha
 plb
 rep #$20
 lda 14,s
 sta.b D_TLO
 lda 16,s
 sta.b D_THI
 lda 18,s
 sta.b D_BLO
 lda 20,s
 sta.b D_BHI
 jsr hud_do_time
 jsr hud_do_apples
 pld
 plb
 plp
hud_draw_end:
 rtl

hud_do_time:
 lda hud_show_time
 and.w #$00FF
 bne @on
 stz hud_xyok
 ldx.w #0
 jmp hud_hide_digits
@on:
 jsr hud_now
 lda.b D_BLO
 and.b D_BHI
 cmp.w #$FFFF
 bne @hasbest
 lda hud_best_ok
 beq @bestdone
 stz hud_best_ok
 stz hud_xyok
 bra @bestdone
@hasbest:
 lda hud_best_ok
 beq @newbest
 lda.b D_BLO
 cmp hud_best_lo
 bne @newbest
 lda.b D_BHI
 cmp hud_best_hi
 beq @bestdone
@newbest:
 lda.b D_BLO
 sta hud_best_lo
 sta.b D_T0
 lda.b D_BHI
 sta hud_best_hi
 sta.b D_T1
 jsr hud_conv
 lda.b D_T0
 pha
 lda.b D_T3
 pha
 lda.b D_T2
 ldx.w #HUD_SLOT_COLON
 ldy.w #0
 jsr hud_pair
 pla
 ldx.w #HUD_SLOT_COLON
 ldy.w #4
 jsr hud_pair
 pla
 ldx.w #0
 ldy.w #8
 jsr hud_pair
 lda hud_best_ok
 bne +
 stz hud_xyok
+ lda.w #1
 sta hud_best_ok
 sta hud_bdirty
@bestdone:
 lda hud_xyok
 bne +
 jsr hud_layout
+
.REPEAT 6 INDEX K
 lda hud_tile+12+2*K
 ora.w #HUD_ATTR
 sta.l core_oam+(6+K)*4+2
.ENDR
 lda hud_bdirty
 beq +
 stz hud_bdirty
 lda hud_best_ok
 beq +
.REPEAT 6 INDEX K
 lda hud_tile+2*K
 ora.w #HUD_ATTR
 sta.l core_oam+K*4+2
.ENDR
+ rts

hud_layout:
 ldx.w #12
 ldy.w #24
 lda hud_best_ok
 beq @loop
 ldx.w #0
 ldy.w #0
@loop:
 lda.l hud_digit_xy,x
 sta core_oam,y
 inx
 inx
 iny
 iny
 iny
 iny
 cpx.w #24
 bcc @loop
 lda hud_best_ok
 bne +
 ldx.w #0
 jsr hud_hide_digits6
+ lda.w #1
 sta hud_xyok
 sta hud_bdirty
 rts

hud_hide_digits6:
 lda.w #$E000
- sta.l core_oam,x
 inx
 inx
 inx
 inx
 cpx.w #24
 bcc -
 rts
hud_hide_digits:
 lda.w #$E000
- sta.l core_oam,x
 inx
 inx
 inx
 inx
 cpx.w #48
 bcc -
 rts

hud_do_apples:
 lda hud_show_map
 and.w #$00FF
 bne @on
 lda.w #$E000
 sta.l core_oam+12*4
 sta.l core_oam+13*4
 sta.l core_oam+14*4
 rts
@on:
 ; phys_apples_left is authoritative, including zero and simultaneous eats.
 lda.l phys_apples_left
 cmp.w #100
 bcc +
 lda.w #99
+ ldx.w #0
 ldy.w #24
 jsr hud_pair
 lda.w #(HUD_APPLE_Y<<8)|HUD_APPLE_X
 sta.l core_oam+12*4
 lda.w #HUD_ATTR|HUD_TILE_APPLE
 sta.l core_oam+12*4+2
 lda.w #(HUD_APPLE_Y<<8)|HUD_COUNT_X
 sta.l core_oam+13*4
 lda.w #(HUD_APPLE_Y<<8)|(HUD_COUNT_X+7)
 sta.l core_oam+14*4
 lda hud_tile+24
 ora.w #HUD_ATTR
 sta.l core_oam+13*4+2
 lda hud_tile+26
 ora.w #HUD_ATTR
 sta.l core_oam+14*4+2
 rts

;---------------------------------------------------------------------------
; The time of hud_draw: the tiles of its digits (hud_tile+12..+22), from
; the last time when it grew by less than a second, else converted.
hud_now:
	lda hud_tok
	beq @full
	lda.b D_TLO
	sec
	sbc hud_tprev_lo
	sta.b D_T0
	lda.b D_THI
	sbc hud_tprev_hi
	bne @full
	lda.b D_T0
	cmp.w #100
	bcs @full
	lda.b D_THI                 ; up to 59:59:99 (360000 = $57E40)
	cmp.w #5
	bcc @add
	bne @full
	lda.b D_TLO
	cmp.w #$7E40
	bcs @full
@add:
	lda.b D_TLO
	sta hud_tprev_lo
	lda.b D_THI
	sta hud_tprev_hi
	lda.b D_T0
	clc
	adc hud_th
	cmp.w #100
	bcc @h
	sbc.w #100
	sta hud_th
	lda hud_ts
	inc a
	cmp.w #60
	bcc @s
	lda hud_tm
	inc a
	sta hud_tm
	ldx.w #HUD_SLOT_COLON
	ldy.w #12
	jsr hud_pair
	lda.w #0
@s:	sta hud_ts
	ldx.w #HUD_SLOT_COLON
	ldy.w #16
	jsr hud_pair
	lda hud_th
@h:	sta hud_th
	ldx.w #0
	ldy.w #20
	jmp hud_pair
@full:
	lda.b D_TLO
	sta hud_tprev_lo
	sta.b D_T0
	lda.b D_THI
	sta hud_tprev_hi
	sta.b D_T1
	jsr hud_conv
	lda.b D_T2
	sta hud_tm
	lda.b D_T3
	sta hud_ts
	lda.b D_T0
	sta hud_th
	lda.w #1
	sta hud_tok
	lda hud_tm
	ldx.w #HUD_SLOT_COLON
	ldy.w #12
	jsr hud_pair
	lda hud_ts
	ldx.w #HUD_SLOT_COLON
	ldy.w #16
	jsr hud_pair
	lda hud_th
	ldx.w #0
	ldy.w #20
	jmp hud_pair

; A (0..99): the tiles of its two digits to hud_tile+Y, +Y+2; X is added
; to the slot of the second one (the colon after it).
hud_pair:
	stx.b D_T5
	tax
	lda.l hud_bcd,x
	and.w #$00FF
	sta.b D_T1
	lsr a
	lsr a
	lsr a
	lsr a
	tax
	lda.l hud_slot_tiles,x
	and.w #$00FF
	sta hud_tile,y
	lda.b D_T1
	and.w #$000F
	clc
	adc.b D_T5
	tax
	lda.l hud_slot_tiles,x
	and.w #$00FF
	sta hud_tile+2,y
	rts

; Converts the time in D_T0 (low) / D_T1 (high), hundredths, into minutes
; D_T2, seconds D_T3, hundredths D_T0; 59:59:99 at most as the original
; (BESTTIME.CPP ido2string).
hud_conv:
	lda.b D_T1
	cmp.w #$0005
	bcc @ok
	bne @max
	lda.b D_T0
	cmp.w #$7E40                ; 360000 = $57E40
	bcc @ok
@max:
	lda.w #59
	sta.b D_T2
	sta.b D_T3
	lda.w #99
	sta.b D_T0
	rts
@ok:
	; H = t >> 15 (0..10), L = t & $7FFF: t / 100 = 327 H + (68 H + L) / 100
	lda.b D_T0
	asl a
	lda.b D_T1
	rol a
	sta.b D_T2
	sep #$20
	sta.l $004202
	lda.b #68
	sta.l $004203
	rep #$20
	lda.b D_T0
	and.w #$7FFF
	clc
	adc.l $004216
	sta.l $004204
	sep #$20
	lda.b #100
	sta.l $004206
	rep #$20
	lda.b D_T2
	xba
	sta.b D_T3                  ; 256 H
	nop
	nop
	nop
	lda.l $004214
	sta.b D_T1                  ; (68 H + L) / 100
	lda.l $004216
	sta.b D_T0                  ; hundredths
	sep #$20
	lda.b D_T2
	sta.l $004202
	lda.b #71
	sta.l $004203
	rep #$20
	lda.b D_T3
	clc
	nop
	adc.l $004216               ; 327 H
	clc
	adc.b D_T1                  ; seconds
	sta.l $004204
	sep #$20
	lda.b #60
	sta.l $004206
	rep #$20
	nop
	nop
	nop
	nop
	nop
	nop
	nop
	nop
	lda.l $004214
	sta.b D_T2                  ; minutes
	lda.l $004216
	sta.b D_T3                  ; seconds
	rts


; Digit positions are constant; OAM large/X-high bits stay zero.
hud_digit_xy:
.REPEAT 6 INDEX K
 .dw (HUD_TIME_Y<<8)|(HUD_TIME_X0+K*7+(K>>1)*3)
.ENDR
.REPEAT 6 INDEX K
 .dw (HUD_TIME_Y<<8)|(HUD_TIME_X1+K*7+(K>>1)*3)
.ENDR
.ENDS
