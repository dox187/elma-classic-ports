; The text of the menus: the letters of menu.abc (ui_data.asm) drawn into a
; canvas of 2-bit tiles in RAM, which is the picture of BG3 (ui.c uploads
; it). The canvas has 28 rows of 34 tiles: the screen's 32 and two more,
; so a letter at the right edge needs no clipping.

.include "hdr.asm"
.include "core.inc"

.DEFINE UI_CANVAS_ROWS   28
.DEFINE UI_CANVAS_COLS   34         ; columns of tiles: the screen's 32 and two more
.DEFINE UI_CANVAS_STRIDE 512        ; bytes of a column of tiles
.DEFINE UI_CANVAS_PAD    32         ; bytes above the first row and under the last one
.DEFINE UI_HMAX          12         ; rows of the tallest letter (tools/gen_ui.py)

.BASE $00
.RAMSECTION ".ui_canvas" BANK $7F SLOT 3
ui_canvas           dsb UI_CANVAS_COLS*UI_CANVAS_STRIDE
ui_row_used         dsb 32          ; 1: a letter was drawn into the row of tiles
ui_col_used         dsb UI_CANVAS_COLS  ; 1: a letter was drawn into the column of tiles
ui_clr_lo           dw              ; while clearing: the first row, the bytes of the
ui_clr_size         dw              ; rows to clear, their place in a column
ui_clr_ofs          dw
.ENDS
.BASE $80

; The direct page while drawing:
.RAMSECTION ".ui_text_dp" BANK 0 SLOT 1
ui_tdp              dsb 44
.ENDS

.DEFINE T_SPTR   0                  ; the string (long)
.DEFINE T_GPTR   4                  ; the data of the letter (long)
.DEFINE T_XPC    8                  ; x in the original menus
.DEFINE T_Y      10                 ; top of the line on the screen
.DEFINE T_SIDX   12                 ; index in the string
.DEFINE T_W      14                 ; width of the letter in the original
.DEFINE T_COL    16                 ; place of its first column in the canvas
.DEFINE T_YY2    18                 ; place of its first row in a column of the canvas
.DEFINE T_NCOL   20                 ; columns of the letter
.DEFINE T_TMP    22
.DEFINE T_STEP   24                 ; bytes of a column of the letter's data
.DEFINE T_ENTRY  26                 ; where the unrolled copy starts
.DEFINE T_CODE   28                 ; the letter
.DEFINE T_Y2     30                 ; twice the top of the line
.DEFINE T_FAST   32                 ; the line is in the screen: no clipping
.DEFINE T_CFIRST 34                 ; place of the first column drawn in the canvas ($FFFF: none)
.DEFINE T_CLAST  36                 ; place of the last column drawn (the greatest)

.SECTION ".ui_text_text" SUPERFREE

;---------------------------------------------------------------------------
; void ui_canvas_clear(void): clears the rows of tiles and the columns used
; since the last clear (the rows from the first to the last one used), with
; DMA channel 1 (the NMI uses channel 0) into WMDATA, and forgets them.
; void ui_canvas_clear_all(void): the whole canvas.
ui_canvas_clear_all:
	php
	phb
	sep #$20
	lda #$7F
	pha
	plb
	rep #$30
	ldx #(32+UI_CANVAS_COLS)-2
	lda #$0101
-	sta ui_row_used,x           ; every row and column, two at a time
	dex
	dex
	bpl -
	bra _clear
ui_canvas_clear:
	php
	phb
	sep #$20
	lda #$7F
	pha
	plb
_clear:
	rep #$10
	sep #$20
	ldx #0                      ; the first row used
-	cpx #UI_CANVAS_ROWS
	bcc +
	brl _none
+	lda ui_row_used,x
	bne +
	inx
	bra -
+	stx ui_clr_lo
	ldx #UI_CANVAS_ROWS-1       ; the last one
-	lda ui_row_used,x
	bne +
	dex
	bra -
+	rep #$20
	txa
	sec
	sbc ui_clr_lo
	inc a
	asl a
	asl a
	asl a
	asl a
	sta ui_clr_size             ; 16 bytes a row of tiles
	lda ui_clr_lo
	asl a
	asl a
	asl a
	asl a
	clc
	adc #UI_CANVAS_PAD+ui_canvas
	sta ui_clr_ofs
	sep #$20
	lda #$08                    ; fixed source, one register
	sta.l $004310
	lda #$80                    ; WMDATA
	sta.l $004311
	lda.b #:_zero
	sta.l $004314
	rep #$20
	lda #_zero
	sta.l $004312
	ldx #0                      ; the column
_col:
	sep #$20
	lda ui_col_used,x
	beq _next
	rep #$20
	txa
	xba
	asl a                       ; times 512
	clc
	adc ui_clr_ofs
	sta.l $002181
	sep #$20
	lda #$01                    ; bank $7F
	sta.l $002183
	rep #$20
	lda ui_clr_size
	sta.l $004315
	sep #$20
	lda #$02
	sta.l $00420B
_next:
	inx
	cpx #UI_CANVAS_COLS
	bcc _col
_none:
	rep #$30
	ldx #(32+UI_CANVAS_COLS)-2  ; forget them
-	stz ui_row_used,x
	dex
	dex
	bpl -
	plb
	plp
	rtl
_zero:
	.db 0

;---------------------------------------------------------------------------
; u16 ui_text_draw(u16 xpc, u16 y, const char* s): draws s from xpc of the
; original menus (640 wide), the top of its line at the screen row y, as
; abc8::write does it. Returns xpc after the last letter. The letters
; reach from the row above the top of the line to 11 rows under it; the
; rows and columns of tiles are marked as used for the whole line.
ui_text_draw:
	php
	phb
	phd
	rep #$30
	lda #ui_tdp
	tcd
	lda 8,s
	sta.b T_XPC
	lda 10,s
	sta.b T_Y
	asl a
	sta.b T_Y2
	lda 12,s
	sta.b T_SPTR
	lda 14,s
	sta.b T_SPTR+2
	stz.b T_SIDX
	lda #$FFFF
	sta.b T_CFIRST
	stz.b T_CLAST
	stz.b T_FAST
	lda.b T_Y
	dec a
	cmp #UI_CANVAS_ROWS*8-13
	bcs _char
	inc.b T_FAST                ; the whole line is on the screen
_char:
	ldy.b T_SIDX
	lda [T_SPTR],y
	and #$00FF
	beq _done
	inc.b T_SIDX
	cmp #32
	bne +
	lda.b T_XPC                 ; a space
	clc
	adc #10
	sta.b T_XPC
	bra _char
+	tax
	lda.l ui_font_pcw,x
	and #$00FF
	beq _char                   ; not in the font
	sta.b T_W
	jsr _glyph
	lda.b T_XPC
	clc
	adc.b T_W
	adc #2                      ; the space between letters
	sta.b T_XPC
	bra _char
_done:
	sep #$20
	lda #$7F
	pha
	plb
	rep #$20
	lda.b T_CFIRST
	bmi _nomark
	lda.b T_Y                   ; the rows of tiles used
	dec a
	bpl +
	lda #0
+	lsr a
	lsr a
	lsr a
	tax
	lda.b T_Y
	clc
	adc #11
	cmp #UI_CANVAS_ROWS*8
	bcc +
	lda #UI_CANVAS_ROWS*8-1
+	lsr a
	lsr a
	lsr a
	sta.b T_TMP
	sep #$20
	lda #1
-	sta ui_row_used,x
	inx
	cpx.b T_TMP
	bcc -
	beq -
	rep #$20
	lda.b T_CLAST               ; the columns
	xba
	and #$00FF                  ; the column times 2
	lsr a
	sta.b T_TMP
	lda.b T_CFIRST
	xba
	and #$00FF
	lsr a
	tax
	sep #$20
	lda #1
-	sta ui_col_used,x
	inx
	cpx.b T_TMP
	bcc -
	beq -
	rep #$20
_nomark:
	lda.b T_XPC
	pld
	plb
	plp
	sta.b tcc__r0
	rtl

; Draws the letter T_CODE at T_XPC, T_Y. Leaves the data bank at that of
; the letter.
_glyph:
	stx.b T_CODE
	lda.b T_XPC
	cmp #1024
	bcc +
	rts                         ; off the screen
+	asl a
	asl a
	tax
	lda.l ui_xinfo,x            ; the column of tiles and the place in it
	cmp #32*UI_CANVAS_STRIDE
	bcc +
	rts
+	sta.b T_COL
	lda.l ui_xinfo+2,x
	sta.b T_TMP
	lda.b T_CODE                ; the letter (ui_font_ptr: 3 bytes each)
	asl a
	adc.b T_CODE
	tax
	lda.l ui_font_ptr,x
	sta.b T_GPTR
	lda.l ui_font_ptr+2,x
	and #$00FF
	sta.b T_GPTR+2
	ldy.b T_TMP
	lda [T_GPTR],y              ; its place
	clc
	adc.b T_GPTR
	sta.b T_GPTR
	ldy #2                      ; the bytes of a column, 0: no rows
	lda [T_GPTR],y
	bne +
	rts
+	sta.b T_STEP
	ldy #4
	lda [T_GPTR],y
	sta.b T_NCOL
	ldy #6
	lda [T_GPTR],y
	clc
	adc.b T_COL
	cmp.b T_CLAST
	bcc +
	sta.b T_CLAST
+	lda [T_GPTR]
	clc
	adc.b T_Y2
	sta.b T_YY2                 ; the first row, the place in a column
	lda.b T_FAST
	bne _visible
	lda.b T_YY2                 ; above or under the screen
	bmi +
	cmp #UI_CANVAS_ROWS*16
	bcs _out
	bra _visible
+	clc
	adc.b T_STEP
	beq _out
	bpl _visible
_out:
	rts
_visible:
	lda.b T_CFIRST
	bpl +
	lda.b T_COL
	sta.b T_CFIRST
+	sep #$20                    ; the data are read from their bank, the canvas
	lda.b T_GPTR+2              ; written with long addresses
	pha
	plb
	rep #$20
	ldx.b T_STEP
	lda.l _entry,x
	sta.b T_ENTRY
	lda.b T_YY2
	clc
	adc.b T_COL
	tax
	lda.b T_GPTR
	clc
	adc #8
	tay
_column:
	pea _columndone-1
	jmp (ui_tdp+T_ENTRY)
_columndone:
	txa
	clc
	adc #UI_CANVAS_STRIDE
	tax
	tya
	clc
	adc.b T_STEP
	tay
	dec.b T_NCOL
	bne _column
	rts

; The rows of a column of a letter: each word (both planes of a row of a
; tile) is added to the canvas (letters do not overlap: the canvas is
; cleared before a picture of texts). X is the place in the canvas, Y that
; of the column in the data; the rows are done from the last one, starting
; in the chain at the number of rows of the letter.
_chain:
.REPEAT UI_HMAX INDEX i
	lda.w (UI_HMAX-1-i)*2,y
	ora.l ui_canvas+(UI_HMAX-1-i)*2,x
	sta.l ui_canvas+(UI_HMAX-1-i)*2,x
.ENDR
	rts

; Where the chain starts for 0 to UI_HMAX rows (11 bytes a row).
_entry:
.REPEAT UI_HMAX+1 INDEX i
	.dw _chain+(UI_HMAX-i)*11
.ENDR

.ENDS
