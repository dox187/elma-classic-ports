; Presentation interpolation. The physical state is never written here.
; phys_view is replaced only between game_render_begin/end; NMI does not
; read it. Angles follow the shortest wrapped arc, positions use 1/256 of
; a physics step (subpixel rounding below 0.08 level pixels).
.include "hdr.asm"

.RAMSECTION ".game_render_vars" BANK 0 SLOT 1
render_prev      dsb 52
render_current   dsb 52
render_interp    dw
Render_delta     dsb 4
Render_product   dsb 4
.ENDS


; Exact fixed-coordinate interpolation. Alpha's signed half is chosen
; once per begin. Position products retain the original 32-bit rounding.
.MACRO RENDER_POSITION
	lda.w render_current+\1
	sec
	sbc.w render_prev+\1
	sta.w Render_delta
	lda.w render_current+\1+2
	sbc.w render_prev+\1+2
	sta.w Render_delta+2
	clc
	adc #128
	cmp #256
	bcs \3
	lda.w Render_delta+1
	xba
	sta $211B
	sta $211B
	sep #$20
	lda.w render_interp
	sta $211C
	rep #$20
	lda $2134
	sta.w Render_product
	sep #$20
	lda $2136
	rep #$20
	and #$00FF
	bit #$0080
	beq +
	ora #$FF00
+	sta.w Render_product+2
	lda.w \2+\1
	clc
	adc.w Render_product
	sta.w phys_view+\1
	lda.w \2+\1+2
	adc.w Render_product+2
	sta.w phys_view+\1+2
\3:
.ENDM

; Bits 8-23 of the signed PPU product are exactly the previous angle
; product's middle word; no sign-extension buffer or helper call needed.
.MACRO RENDER_ANGLE
	lda.w render_current+\1
	sec
	sbc.w render_prev+\1
	xba
	sta $211B
	sta $211B
	sep #$20
	lda.w render_interp
	sta $211C
	rep #$20
	lda $2135
	clc
	adc.w \2+\1
	sta.w phys_view+\1
.ENDM

.SECTION ".game_render_text" SUPERFREE

game_render_reset:
	php
	phb
	rep #$30
	sep #$20
	lda #$80
	pha
	plb
	rep #$20
; All view buffers are BANK 0 SLOT 1, within the low-WRAM mirror.
.REPEAT 26 INDEX K
	lda.w phys_view+2*K
	sta.w render_prev+2*K
	sta.w render_current+2*K
.ENDR
	plb
	plp
game_render_reset_end:
	rtl

game_render_capture:
	php
	jsl phys_read_view
	bra _render_copy_previous

; Previous full output is already current when there was no quick step.
game_render_previous:
	php
_render_copy_previous:
	phb
	rep #$30
	sep #$20
	lda #$80
	pha
	plb
	rep #$20
.REPEAT 26 INDEX K
	lda.w phys_view+2*K
	sta.w render_prev+2*K
.ENDR
	plb
	plp
game_render_capture_end:
game_render_previous_end:
	rtl

; void game_render_begin(u16 alpha): 0..255, or 256 to show current.
game_render_begin:
	php
	phb
	rep #$30
	lda 6,s
	sta.l render_interp
	sep #$20
	lda #$80
	pha
	plb
	rep #$20
.REPEAT 26 INDEX K
	lda.w phys_view+2*K
	sta.w render_current+2*K
.ENDR
	lda.w render_interp
	cmp #256
	bcc +
	jmp _render_done
+	lda.w render_current+48
	cmp.w render_prev+48
	beq +
	jmp _render_done           ; turns and gravity changes remain discrete
+	lda.w render_interp
	bit #$0080
	beq +
	jmp _render_high
+
	RENDER_POSITION 0, render_prev, _rp_lo_0
	RENDER_POSITION 4, render_prev, _rp_lo_4
	RENDER_POSITION 12, render_prev, _rp_lo_12
	RENDER_POSITION 16, render_prev, _rp_lo_16
	RENDER_POSITION 20, render_prev, _rp_lo_20
	RENDER_POSITION 24, render_prev, _rp_lo_24
	RENDER_POSITION 32, render_prev, _rp_lo_32
	RENDER_POSITION 36, render_prev, _rp_lo_36
	RENDER_POSITION 40, render_prev, _rp_lo_40
	RENDER_POSITION 44, render_prev, _rp_lo_44
	RENDER_ANGLE 8, render_prev
	RENDER_ANGLE 28, render_prev
	RENDER_ANGLE 30, render_prev
	jmp _render_done
_render_high:
	RENDER_POSITION 0, render_current, _rp_hi_0
	RENDER_POSITION 4, render_current, _rp_hi_4
	RENDER_POSITION 12, render_current, _rp_hi_12
	RENDER_POSITION 16, render_current, _rp_hi_16
	RENDER_POSITION 20, render_current, _rp_hi_20
	RENDER_POSITION 24, render_current, _rp_hi_24
	RENDER_POSITION 32, render_current, _rp_hi_32
	RENDER_POSITION 36, render_current, _rp_hi_36
	RENDER_POSITION 40, render_current, _rp_hi_40
	RENDER_POSITION 44, render_current, _rp_hi_44
	RENDER_ANGLE 8, render_current
	RENDER_ANGLE 28, render_current
	RENDER_ANGLE 30, render_current
_render_done:
	plb
	plp
game_render_begin_end:
	rtl

game_render_end:
	php
	phb
	rep #$30
	sep #$20
	lda #$80
	pha
	plb
	rep #$20
.REPEAT 26 INDEX K
	lda.w render_current+2*K
	sta.w phys_view+2*K
.ENDR
	plb
	plp
game_render_end_end:
	rtl

.ENDS
