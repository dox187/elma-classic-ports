; The text of the menus: the letters of menu.abc (ui_data.asm) drawn into a
; canvas of 2-bit tiles in RAM, which is the picture of BG3 (ui.c uploads
; it). The canvas has 28 rows of 34 tiles: the screen's 32 and two more,
; so a letter at the right edge needs no clipping.

.include "hdr.asm"
.include "core.inc"

.DEFINE UI_CANVAS_ROWS   28
.DEFINE UI_CANVAS_STRIDE 544        ; bytes of a row of tiles (34 tiles of 16)

.BASE $00
.RAMSECTION ".ui_canvas" BANK $7F SLOT 3
ui_canvas           dsb UI_CANVAS_ROWS*UI_CANVAS_STRIDE
ui_row_used         dsb 32          ; 1: a letter was drawn into the row of tiles
.ENDS
.BASE $80

; The direct page while drawing:
.RAMSECTION ".ui_text_dp" BANK 0 SLOT 1
ui_tdp              dsb 40
.ENDS

.DEFINE T_SPTR   0                  ; the string (long)
.DEFINE T_GPTR   4                  ; the rows of the letter (long)
.DEFINE T_XPC    8                  ; x in the original menus
.DEFINE T_Y      10                 ; top of the line on the screen
.DEFINE T_SIDX   12                 ; index in the string
.DEFINE T_W      14                 ; width of the letter in the original
.DEFINE T_COL    16                 ; first column of tiles, times 16
.DEFINE T_YY     18                 ; screen row of the row of the letter
.DEFINE T_ROWS   20                 ; rows left
.DEFINE T_NM     22                 ; inverted mask, columns 0 and 1
.DEFINE T_NML    24                 ; inverted mask, column 2 (low byte)
.DEFINE T_P0     26
.DEFINE T_P0L    28
.DEFINE T_P1     30
.DEFINE T_P1L    32
.DEFINE T_SHIFT  34                 ; columns of the letter, times 2
.DEFINE T_TMP    36

.SECTION ".ui_text_text" SUPERFREE

;---------------------------------------------------------------------------
; void ui_canvas_clear(void): clears the rows of tiles used since the last
; clear, with DMA channel 1 (the NMI uses channel 0) into WMDATA.
; void ui_canvas_clear_all(void): the whole canvas.
ui_canvas_clear_all:
	php
	phb
	sep #$20
	lda #$7F
	pha
	plb
	rep #$30
	ldx #UI_CANVAS_ROWS-1
	lda #$0101
-	sta ui_row_used,x           ; every row, two at a time
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
	rep #$30
_clear:
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
	ldx #0                      ; the row
	ldy #ui_canvas              ; its place
_row:
	sep #$20
	lda ui_row_used,x
	beq _next
	stz ui_row_used,x
	rep #$20
	tya
	sta.l $002181
	sep #$20
	lda.b #:ui_canvas
	and #$01
	sta.l $002183
	rep #$20
	lda #UI_CANVAS_STRIDE
	sta.l $004315
	sep #$20
	lda #$02
	sta.l $00420B
_next:
	rep #$20
	tya
	clc
	adc #UI_CANVAS_STRIDE
	tay
	inx
	cpx #UI_CANVAS_ROWS
	bcc _row
	plb
	plp
	rtl
_zero:
	.db 0

;---------------------------------------------------------------------------
; u16 ui_text_draw(u16 xpc, u16 y, const char* s): draws s from xpc of the
; original menus (640 wide), the top of its line at the screen row y, as
; abc8::write does it. Returns xpc after the last letter.
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
	lda 12,s
	sta.b T_SPTR
	lda 14,s
	sta.b T_SPTR+2
	stz.b T_SIDX
	sep #$20
	lda #$7F
	pha
	plb
	rep #$20
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
	lda.b T_XPC
	pld
	plb
	plp
	sta.b tcc__r0
	rtl

; Draws the letter X (16-bit A/X) at T_XPC, T_Y.
_glyph:
	lda.b T_XPC
	cmp #1024
	bcc +
	rts                         ; off the screen
+	tay
	; The column of tiles and the place in it:
	asl a
	phx
	tax
	lda.l ui_xcol,x
	cmp #32*16
	bcc +
	plx
	rts
+	sta.b T_COL
	tyx
	lda.l ui_xplace,x
	and #$00FF
	sta.b T_TMP
	; The letter (ui_font_ptr: 3 bytes each), then the place in it:
	pla
	sta.b T_GPTR
	asl a
	adc.b T_GPTR
	tax
	lda.l ui_font_ptr,x
	sta.b T_GPTR
	lda.l ui_font_ptr+2,x
	and #$00FF
	sta.b T_GPTR+2
	ldy.b T_TMP
	lda [T_GPTR],y
	clc
	adc.b T_GPTR
	sta.b T_GPTR
	; The first row, the number of rows and of columns:
	lda [T_GPTR]
	and #$00FF
	cmp #$0080
	bcc +
	ora #$FF00                  ; above the top of the line
+	clc
	adc.b T_Y
	sta.b T_YY
	ldy #1
	lda [T_GPTR],y
	and #$00FF
	bne +
	rts                         ; no rows
+	sta.b T_ROWS
	iny
	lda [T_GPTR],y
	and #$00FF
	bne +
	rts
+	asl a
	sta.b T_SHIFT               ; columns times 2
	; The rows of tiles used:
	lda.b T_YY
	bpl +
	lda #0
+	lsr a
	lsr a
	lsr a
	tax
	lda.b T_YY
	clc
	adc.b T_ROWS
	dec a
	bmi _norows
	lsr a
	lsr a
	lsr a
	sta.b T_TMP
	sep #$20
-	cpx #UI_CANVAS_ROWS
	bcs +
	lda #1
	sta ui_row_used,x
	inx
	cpx.b T_TMP
	bcc -
	beq -
+	rep #$20
_norows:
	ldy #3                      ; the first row of the letter
	ldx.b T_SHIFT
	jmp (_rowfn-2,x)

_rowfn:
	.dw _rows1, _rows2, _rows3

; The rows of a letter of N columns: each word (both planes of a row of a
; tile) is added to the canvas (letters do not overlap: the canvas is
; cleared before a picture of texts).
.MACRO GLYPH_ROWS ARGS N
	lda.b T_YY
	cmp #UI_CANVAS_ROWS*8
	bcs _skip\@                 ; above or under the screen
	asl a
	tax
	lda.l ui_rowofs,x
	clc
	adc.b T_COL
	tax
	lda ui_canvas,x
	ora [T_GPTR],y
	sta ui_canvas,x
	iny
	iny
	.IF N > 1
	lda ui_canvas+16,x
	ora [T_GPTR],y
	sta ui_canvas+16,x
	iny
	iny
	.ENDIF
	.IF N > 2
	lda ui_canvas+32,x
	ora [T_GPTR],y
	sta ui_canvas+32,x
	iny
	iny
	.ENDIF
	bra _next\@
_skip\@:
	tya
	clc
	adc #2*N
	tay
_next\@:
	inc.b T_YY
	dec.b T_ROWS
	bne _rows\1
	rts
.ENDM

_rows1:
	GLYPH_ROWS 1
_rows2:
	GLYPH_ROWS 2
_rows3:
	GLYPH_ROWS 3

; The place of each screen row in the canvas: the row of tiles times 544,
; the row in the tile times 2.
ui_rowofs:
.REPEAT UI_CANVAS_ROWS*8 INDEX i
	.dw (i >> 3)*UI_CANVAS_STRIDE + (i & 7)*2
.ENDR

.ENDS
