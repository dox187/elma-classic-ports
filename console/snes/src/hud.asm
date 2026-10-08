; The time digits and the view box during a level (src/hud.h), as the
; original draws them (DIGIT.CPP kidigit, KIRAJ320.CPP kiview) at 0.4 of
; its size. Data: tools/gen_hud.py (build/gen/hud.asm, hud.inc).
;
; Time: two times of six 16x16 sprites (OAM 0-11), a digit in the left
; half of each (the second digit of the minutes and of the seconds with the
; colon after it). The original draws every pixel of a digit black or white
; by the brightness of the picture under it; here a digit is white (OBJ
; palette 6) where the level under its middle is ground, black (palette 7)
; where it is sky or an apple, read from the map of the view box (the
; colors of one time a frame, not in a frame where the view box took long).
;
; View box: the map of the level at a tenth of the level pixels (1.92 a
; meter, the original's 4.8 at 0.4) is stored column by column, a column 8
; pixels wide and a word a row in the format of a row of a 2-bit tile. The
; window (56x28) is 8 columns of 4 tiles on BG3: the rows of the window are
; copied from the ROM by DMA (channel 1, to WMDATA) into a buffer of these
; tiles in the WRAM, which goes to the VRAM in the next vertical blank. The BG3 horizontal scroll
; moves the columns to the pixel and window 1 cuts BG3 to the window's
; width. The apples are in the map (color 3); the ones eaten are painted
; over in the buffer with the color under them. The flowers and the bike
; are sprites (OAM 12-21) seen through holes (color 0) cleared in the
; buffer under them; the frame is two 32x32 sprites (OAM 22-23). Killers
; are pixels of ground in the map (tools/gen_hud.py). The view box is
; written only when something in it changes; when its columns change, the
; copy takes a frame and the rest the next one (the view box lags a frame).
;
; Called from C: 16-bit registers, data bank $7E, arguments on the stack.
; Inside, the data bank is $7E and the direct page is hud_dp.

.include "hdr.asm"
.include "core.inc"
.include "hud.inc"

; BG3: the map at $5400, the window's tiles from tile 1 (column c: tiles
; 1+4c .. 4+4c, their rows 1-28 the 28 rows of the window, row 0 under the
; frame). Screen row y shows the BG row y + 1 + vertical scroll.
.DEFINE HUD_BG3_MAP   VRAM_BG3_MAP
.DEFINE HUD_COL_VRAM  VRAM_BG3_CHR+8+1       ; column 0, row 1
.DEFINE HUD_BG3_VOFS  (256-HUD_VIEW_Y)&255
.DEFINE HUD_OAM_DOT   12
.DEFINE HUD_DOTS      10
.DEFINE HUD_OAM_FRAME 22
.DEFINE HUD_ATTR_BLACK $3F                  ; priority 3, palette 7, tiles 256+
.DEFINE HUD_MAXOBJ    64                    ; apples
.DEFINE HUD_MAXPHYS   128                   ; objects of phys_objs
.DEFINE HUD_MAGIC     $5A17

; The direct page of hud_load and hud_draw:
.ENUM $00
D_T0    dw
D_T1    dw
D_T2    dw
D_T3    dw
D_T4    dw
D_T5    dw
D_P0    dsb 4       ; long pointers
D_P1    dsb 4
D_CAMX  dw          ; the arguments of hud_draw
D_CAMY  dw
D_BJ    dw
D_TLO   dw
D_THI   dw
D_BLO   dw
D_BHI   dw
D_WIN   dsw 5       ; this frame's window: u0 v0 vx dot apples
D_SIG   dsw 5       ; the window last written
D_UB    dw          ; the bike in sixteenths of view pixels
D_VB    dw
D_OFF   dw          ; the bike's place in the window, sixteenths
D_XW    dw          ; u0 & 7: the first pixel of the window in its tile
D_ROW   dw          ; byte offset of a row in a column, $FFFF: outside
D_Q     dw          ; cam_x / 10
D_R     dw          ; cam_x % 10
D_W     dw          ; plane 0 of two columns of the map row under a time
D_S     dw
D_PWIN  dsw 5       ; the window being written (over two frames)
D_VX    dw          ; vx and the bike's dot of baljobb hud_bj_last
D_DOT   dw
D_HEAVY dw          ; 1: the view box took long this frame
D_END   db
.ENDE

.RAMSECTION ".hud_dp" BANK 0 SLOT 1 ALIGN 256
hud_dp          dsb D_END
.ENDS

.RAMSECTION ".hud_vars" BANK 0 SLOT 1
hud_show_time   db
hud_show_map    db
hud_magic       dw      ; HUD_MAGIC once the toggles are set
hud_lv_xmin     dw      ; first stored column of the map of the level
hud_lv_ncols    dw
hud_lv_vmin     dw      ; first stored row
hud_lv_maxrow   dw      ; last row the window may start at, from hud_lv_vmin
hud_lv_cols     dsb 3   ; the table of the columns (4 bytes a column)
hud_org_x       dsb 4   ; origin of the level (16.16 meters)
hud_org_y       dsb 4
hud_nfl         dw      ; flowers, times 2
hud_nap         dw      ; apples, times 2
hud_nap_half    dw      ; apples
hud_neat        dw      ; apples eaten, times 2
hud_apples_seen dw      ; phys_apples_left when the apples were last looked at
hud_lv_apples   dsb 3   ; the apples of the level in the map (u, v, under)
hud_state       dw      ; 0: write the view box, 1: up to date, 2: hidden
hud_ndot        dw      ; dot sprites, times 4
hud_ndot_old    dw      ; the same of the last written view box
hud_bj_last     dw      ; baljobb >> 8 of D_OFF and vx, $FFFF: none
hud_bufok       dw      ; 1: hud_buf has the columns hud_buf_col, hud_buf_row
hud_buf_col     dw      ; 4 * map column of window column 0
hud_buf_row     dw      ; byte offset of the first row
hud_buf_c64     dw      ; the byte column of window column 0, times 64
hud_buf_r02     dw      ; the row of the map in row 1 of the columns, * 2
hud_painted     dw      ; apples eaten already painted into hud_buf, times 2
hud_pending     dw      ; 1: the columns of D_PWIN are copied, to finish
hud_nhole       dw      ; words changed in hud_buf, times 2
hud_xyok        dw      ; 1: the positions of the digit sprites are set
hud_tsel        dw      ; the time whose colors are read this frame
hud_best_ok     dw      ; 1: the tiles of the best time are in hud_tile
hud_best_lo     dw
hud_best_hi     dw
hud_bmask       dw      ; white digits of the best time
hud_bdirty      dw      ; 1: write the best time's sprites
hud_nmask       dw      ; white digits of the time
hud_tok         dw      ; 1: hud_tm/ts/th are the time hud_tprev
hud_tprev_lo    dw
hud_tprev_hi    dw
hud_tm          dw      ; minutes, seconds, hundredths of the time
hud_ts          dw
hud_th          dw
hud_tile        dsw 12  ; sprite tile of each digit (low byte)
.ENDS

.BASE $00
.RAMSECTION ".hud_objs" BANK $7E SLOT 2
; The 8 columns of the window as their 32 tiles in the VRAM (rows 0 and
; 29-31 of a column stay transparent):
hud_buf         dsb 8*64
; The words of hud_buf changed (offset, the word before):
hud_hole_off    dsw HUD_DOTS
hud_hole_word   dsw HUD_DOTS
; The flowers (u, v), the apples (u, v, offset in phys_objs, the color
; under it, 1 once listed as eaten), the apples eaten (byte column * 64,
; v * 2, the masks painting the color under them), the apple (offset) of
; each object of phys_objs ($FFFF: none):
hud_fl_u        dsw 8
hud_fl_v        dsw 8
hud_ap_u        dsw HUD_MAXOBJ
hud_ap_v        dsw HUD_MAXOBJ
hud_ap_phys     dsw HUD_MAXOBJ
hud_ap_under    dsw HUD_MAXOBJ
hud_ap_eaten    dsw HUD_MAXOBJ
hud_eat_c64     dsw HUD_MAXOBJ
hud_eat_v2      dsw HUD_MAXOBJ
hud_eat_and     dsw HUD_MAXOBJ
hud_eat_or      dsw HUD_MAXOBJ
hud_phys2ap     dsw HUD_MAXPHYS
.ENDS
.BASE $80

.SECTION ".hud_text" SUPERFREE

;---------------------------------------------------------------------------
; void hud_load(u16 level)
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
	lda 8,s
	sta.b D_T4                  ; level
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
	; The level: hud_levels is 16 bytes an entry, level_geom 12.
	lda.b D_T4
	asl a
	asl a
	asl a
	asl a
	tax
	lda.l hud_levels+0,x
	sta hud_lv_xmin
	lda.l hud_levels+2,x
	sta hud_lv_ncols
	lda.l hud_levels+4,x
	sta hud_lv_vmin
	lda.l hud_levels+6,x
	sec
	sbc.w #HUD_VIEW_H
	sta hud_lv_maxrow
	lda.l hud_levels+8,x
	sta hud_lv_cols
	lda.l hud_levels+9,x
	sta hud_lv_cols+1
	lda.l hud_levels+12,x
	sta hud_lv_apples
	lda.l hud_levels+13,x
	sta hud_lv_apples+1
	lda.b D_T4
	asl a
	clc
	adc.b D_T4
	asl a
	asl a
	tax
	lda.l level_geom+0,x
	sta hud_org_x
	lda.l level_geom+2,x
	sta hud_org_x+2
	lda.l level_geom+4,x
	sta hud_org_y
	lda.l level_geom+6,x
	sta hud_org_y+2

	; BG3 tiles 0-32 empty, its map empty but the window's 8x4 tiles.
	pea 33*8
	pea 0
	pea VRAM_BG3_CHR
	jsl core_vram_fill_now
	pla
	pla
	pla
	pea 32*32
	pea 0
	pea HUD_BG3_MAP
	jsl core_vram_fill_now
	pla
	pla
	pla
	sep #$20
	lda.b #$80
	sta.l $002115
	rep #$20
	ldy.w #0                    ; tile row
--	tya
	asl a
	asl a
	asl a
	asl a
	asl a
	clc
	adc.w #HUD_BG3_MAP
	sta.l $002116
	tya
	clc
	adc.w #$2001                ; priority, tile 1 + 4c + r
-	sta.l $002118
	clc
	adc.w #4
	cmp.w #$2001+32
	bcc -
	iny
	cpy.w #4
	bcc --

	; Sprite tiles and the colors.
	pea 128*32
	pea :hud_sprite_tiles
	pea hud_sprite_tiles
	pea VRAM_OBJ+256*16
	jsl core_vram_now
	tsc
	clc
	adc.w #8
	tcs
	pea 8
	pea :hud_bg_colors
	pea hud_bg_colors
	pea 0
	jsl core_cgram_now
	tsc
	clc
	adc.w #8
	tcs
	pea 32
	pea :hud_obj_colors_white
	pea hud_obj_colors_white
	pea 128+6*16
	jsl core_cgram_now
	tsc
	clc
	adc.w #8
	tcs
	pea 32
	pea :hud_obj_colors_black
	pea hud_obj_colors_black
	pea 128+7*16
	jsl core_cgram_now
	tsc
	clc
	adc.w #8
	tcs

	; BG3 map at $5400 (32x32), its tiles at $5000; window 1 shows BG3
	; only inside it (empty for now); no color math.
	sep #$20
	lda.b #(HUD_BG3_MAP>>8)&$FC
	sta.l $002109
	lda.b #VRAM_BG3_CHR>>12
	sta.l $00210C
	lda.b #$03
	sta.l $002124
	lda.b #$04
	sta.l $00212E
	lda.b #1
	sta.l $002126
	lda.b #0
	sta.l $002127
	sta.l $002130
	sta.l $002131
	rep #$20
	lda.w #0
	sta.l core_scroll+8
	lda.w #HUD_BG3_VOFS
	sta.l core_scroll+10

	; OAM 0-23 hidden; 22 and 23 are 32x32.
	ldx.w #0
	lda.w #$E000
-	sta.l core_oam,x
	inx
	inx
	inx
	inx
	cpx.w #24*4
	bcc -
	lda.w #0
	sta.l core_oam+512
	sta.l core_oam+514
	lda.w #$A000
	sta.l core_oam+516

	; The window's columns transparent.
	ldx.w #8*64-2
	lda.w #0
-	sta hud_buf,x
	dex
	dex
	bpl -

	; The flowers and apples of phys_objs (12 bytes an object); the color
	; under an apple from the apples of the map at the same place.
	lda hud_lv_apples
	sta.b D_P0
	lda hud_lv_apples+1
	sta.b D_P0+1
	stz hud_nfl
	stz hud_nap
	stz hud_nap_half
	stz hud_neat
	ldx.w #HUD_MAXPHYS*2-2
	lda.w #$FFFF
-	sta hud_phys2ap,x
	dex
	dex
	bpl -
	ldx.w #0
	lda.l phys_nobjs
	sta.b D_T5
@obj:
	lda.b D_T5
	bne +
	jmp @objdone
+	dec.b D_T5
	lda.l phys_objs+4,x
	sec
	sbc hud_org_x
	sta.b D_T0
	lda.l phys_objs+6,x
	sbc hud_org_x+2
	sta.b D_T1
	jsr hud_fxview
	jsr hud_asr4
	sta.b D_T4                  ; u
	lda hud_org_y
	sec
	sbc.l phys_objs+8,x
	sta.b D_T0
	lda hud_org_y+2
	sbc.l phys_objs+10,x
	sta.b D_T1
	jsr hud_fxview
	jsr hud_asr4
	sta.b D_T3                  ; v
	lda.l phys_objs+0,x
	and.w #$00FF
	cmp.w #1
	bne +
	jmp @flower
+	cmp.w #2
	beq +
	jmp @next
+	ldy hud_nap
	cpy.w #HUD_MAXOBJ*2
	bcc +
	jmp @next
+	stx.b D_T2                  ; its index in phys_objs: offset / 12
	lda.b D_T2
	sta.l $004204
	sep #$20
	lda.b #12
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
	cmp.w #HUD_MAXPHYS
	bcs +
	asl a
	phx
	tax
	tya
	sta hud_phys2ap,x
	plx
+	lda.b D_T4
	sta hud_ap_u,y
	lda.b D_T3
	sta hud_ap_v,y
	txa
	sta hud_ap_phys,y
	lda.w #0
	sta hud_ap_eaten,y
	lda.w #2                    ; sky if not found
	sta hud_ap_under,y
	phy
	ldy.w #0
-	lda [D_P0],y
	cmp.w #$FFFF
	beq ++
	cmp.b D_T4
	bne +
	iny
	iny
	lda [D_P0],y
	dey
	dey
	cmp.b D_T3
	bne +
	iny
	iny
	iny
	iny
	lda [D_P0],y
	ply
	sta hud_ap_under,y
	phy
	bra ++
+	iny
	iny
	iny
	iny
	iny
	iny
	bra -
++	ply
	iny
	iny
	sty hud_nap
	tya
	lsr a
	sta hud_nap_half
	bra @next
@flower:
	ldy hud_nfl
	cpy.w #8*2
	bcs @next
	lda.b D_T4
	sta hud_fl_u,y
	lda.b D_T3
	sta hud_fl_v,y
	iny
	iny
	sty hud_nfl
@next:
	txa
	clc
	adc.w #12
	tax
	jmp @obj
@objdone:
	lda.l phys_apples_left
	sta hud_apples_seen
	stz hud_state
	stz hud_bufok
	stz hud_pending
	lda.w #$FFFF
	sta hud_bj_last
	stz hud_ndot_old
	stz hud_xyok
	stz hud_best_ok
	stz hud_bdirty
	stz hud_bmask
	stz hud_nmask
	stz hud_tsel
	stz hud_tok
	pld
	plb
	plp
	rtl

;---------------------------------------------------------------------------
; void hud_draw(s16 cam_x, s16 cam_y, u16 baljobb, u32 time_hs, u32 best_hs)
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
	lda 8,s
	sta.b D_CAMX
	lda 10,s
	sta.b D_CAMY
	lda 12,s
	sta.b D_BJ
	lda 14,s
	sta.b D_TLO
	lda 16,s
	sta.b D_THI
	lda 18,s
	sta.b D_BLO
	lda 20,s
	sta.b D_BHI
	jsr hud_do_map
	jsr hud_do_time
	pld
	plb
	plp
hud_draw_end:                   ; (for measurements: test/hud_check.py)
	rtl

;---------------------------------------------------------------------------
; The time digits.
hud_do_time:
	lda hud_show_time
	and.w #$00FF
	bne @on
	lda hud_xyok
	beq +
	stz hud_xyok
	ldx.w #0
	jsr hud_hide_digits
+	rts
@on:
	jsr hud_now
	; The best time, converted only when it changes:
	lda.b D_BLO
	and.b D_BHI
	cmp.w #$FFFF
	bne @hasbest
	lda hud_best_ok
	beq @bestdone
	stz hud_best_ok             ; it went: hide its sprites
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
	stz hud_xyok                ; it came: place its sprites
+	lda.w #1
	sta hud_best_ok
	sta hud_bdirty
@bestdone:
	lda hud_xyok
	bne +
	jsr hud_layout
+
	; The colors of one time a frame, not when the view box took long:
	; the row of the map under the middle of the digits (D_ROW, $FFFF if
	; outside the map: ground) and cam_x / 10 (D_Q, D_R).
	lda.b D_HEAVY
	beq +
	jmp @oam
+	lda.b D_CAMY
	clc
	adc.w #HUD_TIME_Y+7
	sta.l $004204
	sep #$20
	lda.b #10
	sta.l $004206
	rep #$20
	lda hud_lv_cols             ; meanwhile: the table of the columns
	sta.b D_P0
	lda hud_lv_cols+1
	sta.b D_P0+1
	nop
	lda.l $004214
	sec
	sbc hud_lv_vmin
	bmi @rowout
	cmp hud_lv_maxrow
	bcc @rowin
	sec
	sbc hud_lv_maxrow
	cmp.w #HUD_VIEW_H
	bcs @rowout
	adc hud_lv_maxrow
@rowin:
	asl a
	bra +
@rowout:
	lda.w #$FFFF
+	sta.b D_ROW
	lda.b D_CAMX
	sta.l $004204
	sep #$20
	lda.b #10
	sta.l $004206
	rep #$20
	nop
	nop
	nop
	nop
	nop
	nop
	nop
	lda.l $004214
	sta.b D_Q
	lda.l $004216
	sta.b D_R
	lda hud_tsel
	eor.w #1
	sta hud_tsel
	beq @colbest
	ldx.w #1
	jsr hud_colors
	sta hud_nmask
	bra @oam
@colbest:
	lda hud_best_ok
	beq @oam
	ldx.w #0
	jsr hud_colors
	cmp hud_bmask
	beq @oam
	sta hud_bmask
	lda.w #1
	sta hud_bdirty
@oam:
	; The sprites of the time: tile and attributes.
	lda hud_nmask
	asl a
	asl a
	sta.b D_T0
	asl a
	adc.b D_T0
	tax                         ; mask * 12
.REPEAT 6 INDEX K
	lda.l hud_attrtab+2*K,x
	ora hud_tile+12+2*K
	sta core_oam+(6+K)*4+2
.ENDR
	lda hud_bdirty
	beq +
	stz hud_bdirty
	lda hud_best_ok
	beq +
	lda hud_bmask
	asl a
	asl a
	sta.b D_T0
	asl a
	adc.b D_T0
	tax
.REPEAT 6 INDEX K
	lda.l hud_attrtab+2*K,x
	ora hud_tile+2*K
	sta core_oam+K*4+2
.ENDR
+	rts

; The positions of the digit sprites (the best time's hidden if none).
hud_layout:
	ldx.w #6*2
	ldy.w #6*4
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
	cpx.w #12*2
	bcc @loop
	lda hud_best_ok
	bne ++
	ldx.w #0
	jsr hud_hide_digits6
++	lda.w #1
	sta hud_xyok
	sta hud_bdirty
	rts

; The colors of time X (0 best, 1 now): A = bit k set if digit k is white.
hud_colors:
	stx.b D_T4
	txa
	beq +
	lda.w #12                   ; the first digit of the time, * 2
+	tax
	lda.b D_R
	clc
	adc.l hud_digit_cx,x
	tax
	lda.l hud_div10,x
	and.w #$00FF
	clc
	adc.b D_Q
	sta.b D_T0                  ; u under the first digit
	and.w #7
	sta.b D_S
	lda.b D_T0
	lsr a
	lsr a
	lsr a
	sec
	sbc hud_lv_xmin
	sta.b D_T0                  ; its column of the map
	jsr hud_mapbyte
	xba
	sta.b D_W
	lda.b D_T0
	inc a
	jsr hud_mapbyte
	ora.b D_W
	ldx.b D_S                   ; the pixel under the first digit to bit 15
	beq +
-	asl a
	dex
	bne -
+	xba
	and.w #$00F8
	lsr a
	lsr a
	lsr a
	sta.b D_T0                  ; 5 pixels, bit 4 under the first digit
	lda.b D_T4                  ; (t * 10 + r) * 32
	asl a
	asl a
	adc.b D_T4
	asl a
	adc.b D_R
	asl a
	asl a
	asl a
	asl a
	asl a
	adc.b D_T0
	tax
	lda.l hud_colmask,x
	and.w #$003F
	rts

; The ground of the map at column A (from hud_lv_xmin) and row D_ROW: A =
; a byte, bit set for a pixel of ground ($FF outside the map). Keeps D_T0,
; D_T4.
hud_mapbyte:
	cmp hud_lv_ncols
	bcs ++
	ldy.b D_ROW
	bmi ++
	asl a
	asl a
	tay
	lda [D_P0],y
	sta.b D_P1
	iny
	lda [D_P0],y
	sta.b D_P1+1
	ldy.b D_ROW
	lda [D_P1],y                ; ground: plane 0 without plane 1
	sta.b D_P1
	xba
	eor.w #$FFFF
	and.b D_P1
	and.w #$00FF
	rts
++	lda.w #$00FF
	rts

; Hides OAM 0-5 (hud_hide_digits6) or 0-11 (hud_hide_digits), from X = 0.
hud_hide_digits6:
	lda.w #$E000
-	sta.l core_oam,x
	inx
	inx
	inx
	inx
	cpx.w #6*4
	bcc -
	rts
hud_hide_digits:
	lda.w #$E000
-	sta.l core_oam,x
	inx
	inx
	inx
	inx
	cpx.w #12*4
	bcc -
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

;---------------------------------------------------------------------------
; D_T0/D_T1: a distance from the origin, 16.16 meters; A: the same in
; sixteenths of a view pixel (2n - 41n/512 of n = sixteenths of a meter),
; 0 if negative. Keeps X and Y.
hud_fxview:
	lda.b D_T1
	bpl +
	lda.w #0
	rts
+	lda.b D_T0
	xba
	and.w #$00FF
	lsr a
	lsr a
	lsr a
	lsr a
	sta.b D_T2
	lda.b D_T1
	asl a
	asl a
	asl a
	asl a
	ora.b D_T2
	sta.b D_T2                  ; n
	sep #$20                    ; 41 n on the multiplier of the PPU
	sta.l $00211B
	lda.b D_T2+1
	sta.l $00211B
	lda.b #41
	sta.l $00211C
	rep #$20
	lda.l $002135               ; 41 n >> 8
	lsr a
	sta.b D_T3
	lda.b D_T2
	asl a
	sec
	sbc.b D_T3
	rts

; A = A >> 4, arithmetic.
hud_asr4:
	cmp.w #$8000
	ror a
	cmp.w #$8000
	ror a
	cmp.w #$8000
	ror a
	cmp.w #$8000
	ror a
	rts

;---------------------------------------------------------------------------
; The view box. A new window whose columns or first row differ from those
; in hud_buf takes two frames: the columns are copied in the first, the
; rest is done in the second (with the same window), the view box lagging a
; frame; otherwise everything is done in one frame.
hud_do_map:
	stz.b D_HEAVY
	lda hud_show_map
	and.w #$00FF
	bne @show
	stz hud_pending
	lda hud_state
	cmp.w #2
	beq +
	lda.w #2
	sta hud_state
	stz hud_ndot_old
	ldx.w #HUD_OAM_DOT*4
	lda.w #$E000
-	sta.l core_oam,x
	inx
	inx
	inx
	inx
	cpx.w #24*4
	bcc -
	lda.w #$2126                ; window empty: no BG3
	ldx.w #1
	jsr hud_reg
	lda.w #$2127
	ldx.w #0
	jsr hud_reg
+	rts
@show:
	; Nothing in a frame where the time places its digits (the first one
	; of a level): both together would take too long.
	lda hud_xyok
	bne +
	lda hud_show_time
	and.w #$00FF
	beq +
	rts
+	lda hud_pending
	beq @calc
	jmp @finish
@calc:
	; The bike in sixteenths of view pixels:
	lda.l phys_view+0
	sec
	sbc hud_org_x
	sta.b D_T0
	lda.l phys_view+2
	sbc hud_org_x+2
	sta.b D_T1
	jsr hud_fxview
	sta.b D_UB
	lda hud_org_y
	sec
	sbc.l phys_view+4
	sta.b D_T0
	lda hud_org_y+2
	sbc.l phys_view+6
	sta.b D_T1
	jsr hud_fxview
	sta.b D_VB
	; b = baljobb >> 8: the bike's place 179 + 2b + 26b/256 (11.2 + 33.6
	; baljobb pixels), the window at 16 + 168b/256 (kept while b stays).
	lda.b D_BJ
	xba
	and.w #$00FF
	cmp hud_bj_last
	beq @bjsame
	sta hud_bj_last
	sta.b D_T0
	sep #$20
	sta.l $004202
	lda.b #26
	sta.l $004203
	rep #$20
	lda.b D_T0
	asl a
	clc
	sta.b D_T1
	lda.l $004216
	xba
	and.w #$00FF
	adc.b D_T1
	adc.w #179
	sta.b D_OFF
	sep #$20
	lda.b D_T0
	sta.l $004202
	lda.b #HUD_VIEW_XRANGE
	sta.l $004203
	rep #$20
	lsr a                       ; (waits for the product)
	lsr a
	lsr a
	lda.l $004216
	xba
	and.w #$00FF
	clc
	adc.w #HUD_VIEW_X0
	sta.b D_VX
	lda.b D_OFF
	lsr a
	lsr a
	lsr a
	lsr a
	sta.b D_DOT
@bjsame:
	lda.b D_UB
	sec
	sbc.b D_OFF
	jsr hud_asr4
	sta.b D_WIN+0               ; u0
	lda.b D_VB
	lsr a
	lsr a
	lsr a
	lsr a
	sec
	sbc.w #HUD_BIKE_ROW
	sta.b D_WIN+2               ; v0
	lda.b D_VX
	sta.b D_WIN+4               ; vx
	lda.b D_DOT
	sta.b D_WIN+6               ; the bike's dot
	lda.l phys_apples_left
	sta.b D_WIN+8
	; Unchanged: nothing to do.
	lda hud_state
	cmp.w #1
	bne @new
	lda.b D_WIN+0
	cmp.b D_SIG+0
	bne @new
	lda.b D_WIN+2
	cmp.b D_SIG+2
	bne @new
	lda.b D_WIN+4
	cmp.b D_SIG+4
	bne @new
	lda.b D_WIN+6
	cmp.b D_SIG+6
	bne @new
	lda.b D_WIN+8
	cmp.b D_SIG+8
	bne @new
	rts
@new:
	; Its columns (4 * the map column of window column 0) and first row
	; (the byte offset in a column, kept inside the map).
	lda.b D_WIN+2
	sec
	sbc hud_lv_vmin
	bpl +
	lda.w #0
+	cmp hud_lv_maxrow
	bcc +
	lda hud_lv_maxrow
+	asl a
	sta.b D_ROW
	lda.b D_WIN+0
	cmp.w #$8000
	ror a
	cmp.w #$8000
	ror a
	cmp.w #$8000
	ror a
	sta.b D_T4                  ; its first byte column
	sec
	sbc hud_lv_xmin
	asl a
	asl a
	sta.b D_T0
	ldx.w #8
-	lda.b D_WIN,x               ; the window to show
	sta.b D_PWIN,x
	dex
	dex
	bpl -
	lda hud_bufok
	beq @columns
	lda.b D_T0
	cmp hud_buf_col
	bne @columns
	lda.b D_ROW
	cmp hud_buf_row
	bne @columns
	jmp @finish
@columns:
	; The 8 columns into hud_buf (64 bytes a column, rows 1-28) by DMA
	; from the ROM to the WRAM (channel 1). Y: 4 * the map column
	; (outside the map: ground).
	lda.b D_T0
	sta hud_buf_col
	tay
	lda.b D_T4
	asl a
	asl a
	asl a
	asl a
	asl a
	asl a
	sta hud_buf_c64
	lda.b D_ROW
	sta hud_buf_row
	clc
	adc hud_lv_vmin
	clc
	adc hud_lv_vmin
	sta hud_buf_r02
	lda.w #1
	sta hud_bufok
	sta hud_pending
	sta.b D_HEAVY
	stz hud_nhole               ; (the holes went with the old columns)
	stz hud_painted
	lda hud_lv_cols
	sta.b D_P0
	lda hud_lv_cols+1
	sta.b D_P0+1
	lda hud_lv_ncols
	asl a
	asl a
	sta.b D_T3
	lda.w #hud_buf+2
	sta.b D_T2
	lda.w #8
	sta.b D_T5
	phb
	sep #$20
	lda.b #$80
	pha
	plb
	stz $2183                   ; WRAM bank $7E
	lda.b #$80
	sta $4311                   ; to WMDATA
	stz $4310                   ; one register, ascending
	rep #$20
@col:
	cpy.b D_T3
	bcs @ground
	lda [D_P0],y
	adc.b D_ROW
	sta $4312
	iny
	iny
	lda [D_P0],y
	sta $4314                   ; bank (and the size's low byte, below)
	iny
	iny
	bra +
@ground:
	lda.w #hud_ground_column
	sta $4312
	lda.w #:hud_ground_column
	sta $4314
	iny
	iny
	iny
	iny
+	lda.w #HUD_VIEW_H*2
	sta $4315
	lda.b D_T2
	sta $2181
	clc
	adc.w #64
	sta.b D_T2
	sep #$20
	lda.b #$02
	sta $420B
	rep #$20
	dec.b D_T5
	bne @col
	plb
	rts

@finish:
	; The window D_PWIN, its columns in hud_buf: room in the queues (a
	; transfer, two registers), else next frame.
	lda.l core_dmaq_n
	cmp.w #(DMAQ_MAX-1)*8+1
	bcc +
	rts
+	lda.l core_regq_n
	cmp.w #(REGQ_MAX-2)*4+1
	bcc +
	rts
+	stz hud_pending
	lda.w #1
	sta hud_state
	sta.b D_HEAVY
	ldx.w #8
-	lda.b D_PWIN,x
	sta.b D_SIG,x
	sta.b D_WIN,x
	dex
	dex
	bpl -
	; Apples eaten since the last look: the one of phys_eaten if one,
	; else a look at all.
	lda hud_apples_seen
	sec
	sbc.b D_WIN+8
	beq @eatdone
	ldx.b D_WIN+8
	stx hud_apples_seen
	cmp.w #1
	bne @scan
	lda.l phys_eaten
	cmp.w #HUD_MAXPHYS
	bcs @scan
	asl a
	tax
	lda hud_phys2ap,x
	bmi @scan
	tay
	lda hud_ap_eaten,y
	bne @scan
	ldx hud_ap_phys,y
	lda.l phys_objs+3,x
	and.w #$00FF
	bne @scan
	jsr hud_list
	bra @eatdone
@scan:
	jsr hud_eaten
@eatdone:
	; The holes of the last time filled back (in reverse order: the first
	; one saved the word before all).
	ldy hud_nhole
-	beq +
	dey
	dey
	ldx hud_hole_off,y
	lda hud_hole_word,y
	sta hud_buf+2,x
	cpy.w #0
	bra -
+	stz hud_nhole
	; The apples eaten since the columns were copied, if in them: the
	; color under them.
	ldx hud_painted
@paint:
	cpx hud_neat
	bcs @painted
	lda hud_eat_c64,x
	sec
	sbc hud_buf_c64
	cmp.w #8*64
	bcs @pnext
	sta.b D_T0                  ; column * 64
	lda hud_eat_v2,x
	sec
	sbc hud_buf_r02
	cmp.w #HUD_VIEW_H*2
	bcs @pnext
	adc.b D_T0
	tay
	lda hud_buf+2,y
	and hud_eat_and,x
	ora hud_eat_or,x
	sta hud_buf+2,y
@pnext:
	inx
	inx
	bra @paint
@painted:
	stx hud_painted

	; Scroll, window, frame.
	lda.b D_WIN+0
	and.w #7
	sta.b D_XW
	sec
	sbc.b D_WIN+4
	and.w #$00FF
	sta.l core_scroll+8
	lda.w #$2126
	ldx.b D_WIN+4
	jsr hud_reg
	lda.b D_WIN+4
	clc
	adc.w #HUD_VIEW_W-1
	tax
	lda.w #$2127
	jsr hud_reg
	lda.b D_WIN+4
	dec a
	ora.w #(HUD_VIEW_Y-1)<<8
	sta core_oam+HUD_OAM_FRAME*4+0
	clc
	adc.w #32
	sta core_oam+HUD_OAM_FRAME*4+4
	lda.w #HUD_FRAME_TILE|(HUD_ATTR_BLACK<<8)
	sta core_oam+HUD_OAM_FRAME*4+2
	lda.w #(HUD_FRAME_TILE+4)|(HUD_ATTR_BLACK<<8)
	sta core_oam+HUD_OAM_FRAME*4+6

	; The bike, then the flowers (the bike in front): sprites over holes.
	stz hud_ndot
	lda.b D_WIN+6
	sta.b D_T0
	lda.w #HUD_BIKE_ROW
	sta.b D_T1
	lda.w #HUD_TILE_BIKE|(HUD_ATTR_BLACK<<8)
	sta.b D_T5
	jsr hud_dot
	ldx.w #0
@fl:
	cpx hud_nfl
	bcs @fldone
	lda hud_fl_u,x
	sec
	sbc.b D_WIN+0
	cmp.w #HUD_VIEW_W
	bcs @flnext
	sta.b D_T0
	lda hud_fl_v,x
	sec
	sbc.b D_WIN+2
	cmp.w #HUD_VIEW_H
	bcs @flnext
	sta.b D_T1
	lda.w #HUD_TILE_FLOWER|(HUD_ATTR_BLACK<<8)
	sta.b D_T5
	phx
	jsr hud_dot
	plx
@flnext:
	inx
	inx
	bra @fl
@fldone:
	; The dot sprites of the last time not used now hidden.
	ldx hud_ndot
	lda.w #$E000
-	cpx hud_ndot_old
	bcs +
	sta core_oam+HUD_OAM_DOT*4,x
	inx
	inx
	inx
	inx
	bra -
+	lda hud_ndot
	sta hud_ndot_old
	; The 8 columns to the VRAM at the next frame.
	lda.l core_dmaq_n
	tax
	lda.w #DMAQ_VRAM
	sta core_dmaq+0,x
	lda.w #hud_buf
	sta core_dmaq+1,x
	lda.w #$7E
	sta core_dmaq+3,x
	lda.w #8*64
	sta core_dmaq+4,x
	lda.w #VRAM_BG3_CHR+8
	sta core_dmaq+6,x
	txa
	clc
	adc.w #8
	sta.l core_dmaq_n
	lda.l core_dmaq_bytes
	clc
	adc.w #8*64
	sta.l core_dmaq_bytes
	rts

; A dot at D_T0 (x), D_T1 (y) of the window, D_T5 the 2nd word of its
; sprite (tile, attributes): the sprite and a hole in hud_buf under it (the
; word before it saved).
hud_dot:
	ldy hud_ndot
	cpy.w #HUD_DOTS*4
	bcs ++
	lda.b D_T1
	adc.w #HUD_VIEW_Y
	xba
	ora.b D_WIN+4
	adc.b D_T0                  ; x < 256: no carry into y
	sta core_oam+HUD_OAM_DOT*4,y
	lda.b D_T5
	sta core_oam+HUD_OAM_DOT*4+2,y
	iny
	iny
	iny
	iny
	sty hud_ndot
	lda.b D_XW
	clc
	adc.b D_T0
	tay
	and.w #7
	asl a
	tax
	lda.l hud_hole,x
	sta.b D_T3
	tya
	and.w #$00F8
	asl a
	asl a
	asl a
	adc.b D_T1
	adc.b D_T1
	tax                         ; column * 64 + row * 2
	ldy hud_nhole
	cpy.w #HUD_DOTS*2
	bcs ++
	txa
	sta hud_hole_off,y
	lda hud_buf+2,x
	sta hud_hole_word,y
	and.b D_T3
	sta hud_buf+2,x
	iny
	iny
	sty hud_nhole
++	rts

; The apples eaten since the last look: to the list of the eaten ones
; (their byte column, row, the masks that paint the color under them).
hud_eaten:
	ldy.w #0
@ap:
	cpy hud_nap
	bcs @done
	lda hud_neat                ; all found: done
	lsr a
	clc
	adc hud_apples_seen
	cmp hud_nap_half
	bcs @done
	lda hud_ap_eaten,y
	bne @next
	ldx hud_ap_phys,y
	lda.l phys_objs+3,x         ; active
	and.w #$00FF
	bne @next
	jsr hud_list
@next:
	iny
	iny
	bra @ap
@done:
	rts

; Apple Y (offset in hud_ap_*) to the list of the eaten ones. Keeps Y.
hud_list:
	lda.w #1
	sta hud_ap_eaten,y
	lda hud_ap_u,y
	and.w #7
	asl a
	tax
	lda.l hud_hole,x
	sta.b D_T0
	lda.l hud_paint,x
	sta.b D_T1
	lda hud_ap_under,y
	cmp.w #2
	bcc +
	lda.b D_T1                  ; sky: plane 1
	xba
	sta.b D_T1
+	ldx hud_neat
	lda.b D_T0
	sta hud_eat_and,x
	lda.b D_T1
	sta hud_eat_or,x
	lda hud_ap_v,y
	asl a
	sta hud_eat_v2,x
	lda hud_ap_u,y
	and.w #$FFF8
	asl a
	asl a
	asl a
	sta hud_eat_c64,x
	inx
	inx
	stx hud_neat
	rts

; Queues the write of the register A (8-bit, $21xx) with X.
hud_reg:
	pha
	lda.l core_regq_n
	tay
	pla
	sta core_regq,y
	txa
	sta core_regq+2,y
	tya
	clc
	adc.w #4
	sta.l core_regq_n
	rts

.ENDS

.SECTION ".hud_tables" SUPERFREE
; Of the twelve digits (word tables): x and y on the screen, x of the
; middle of the digit plus 2 (the map is read at (cam_x + it) / 10).
hud_digit_xy:
	.dw HUD_TIME_X0+0|(HUD_TIME_Y<<8), HUD_TIME_X0+6|(HUD_TIME_Y<<8)
	.dw HUD_TIME_X0+16|(HUD_TIME_Y<<8), HUD_TIME_X0+22|(HUD_TIME_Y<<8)
	.dw HUD_TIME_X0+32|(HUD_TIME_Y<<8), HUD_TIME_X0+38|(HUD_TIME_Y<<8)
	.dw HUD_TIME_X1+0|(HUD_TIME_Y<<8), HUD_TIME_X1+6|(HUD_TIME_Y<<8)
	.dw HUD_TIME_X1+16|(HUD_TIME_Y<<8), HUD_TIME_X1+22|(HUD_TIME_Y<<8)
	.dw HUD_TIME_X1+32|(HUD_TIME_Y<<8), HUD_TIME_X1+38|(HUD_TIME_Y<<8)
hud_digit_cx:
	.dw HUD_TIME_X0+2, HUD_TIME_X0+8, HUD_TIME_X0+18, HUD_TIME_X0+24
	.dw HUD_TIME_X0+34, HUD_TIME_X0+40
	.dw HUD_TIME_X1+2, HUD_TIME_X1+8, HUD_TIME_X1+18, HUD_TIME_X1+24
	.dw HUD_TIME_X1+34, HUD_TIME_X1+40
; A row of a 2-bit tile without pixel n (both planes), and pixel n alone in
; plane 0:
hud_hole:
	.dw $7F7F, $BFBF, $DFDF, $EFEF, $F7F7, $FBFB, $FDFD, $FEFE
hud_paint:
	.dw $0080, $0040, $0020, $0010, $0008, $0004, $0002, $0001
.ENDS
