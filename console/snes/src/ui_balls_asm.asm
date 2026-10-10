; The balls of the menus (ui_balls.c): the step of a frame and the sprites,
; the parts that run every frame. Positions are in 1/64 of a pixel of the
; screen (0.4 of the original's picture of 640x560).

.include "hdr.asm"
.include "core.inc"

.DEFINE NBALLS 9
.DEFINE WALL_X 256*64
.DEFINE WALL_Y 224*64

.BASE $00
.RAMSECTION ".ui_balls_vars" BANK $7E SLOT 2
ui_bx       dsw NBALLS          ; center
ui_by       dsw NBALLS
ui_bvx      dsw NBALLS          ; a frame
ui_bvy      dsw NBALLS
ui_ba       dsw NBALLS          ; angle, 65536 a turn
ui_bw       dsw NBALLS          ; angle a frame
ui_br       dsw NBALLS          ; radius
ui_bhalf    dsw NBALLS          ; half the side of the sprite, pixels
ui_btile    dsw NBALLS          ; first tile of the sprite
ui_bbig     dsw NBALLS          ; 2: a sprite of 64x64
ui_bsz      dsw NBALLS          ; size: 0, 1, 2
ui_bpairs   dsb 2*36+2          ; pairs close to each other: count, (i, j)... times 2
; Work of the collisions:
b_ma        dw                  ; multiplication: b_ma * b_mb -> b_mr
b_mb        dw
b_mr0       db                  ; (a byte under b_mr for shifting it)
b_mr        dsb 4
b_p         dw                  ; the two balls, times 2
b_q         dw
b_k         dw                  ; size of p * 3 + size of q, times 2
b_dx        dw                  ; from p to q, quarter pixels
b_dy        dw
b_rr        dw                  ; the sum of the radii
b_d         dw                  ; the distance
b_nx        dw                  ; the normal, times 256
b_ny        dw
b_dvx       dw                  ; the speed of q against p
b_dvy       dw
b_vn        dw                  ; along the normal
b_vt        dw                  ; along the tangent (-ny, nx)
b_a         dw
b_n         dw                  ; pairs left
b_i         dw
b_ball      dw
b_s         dsb 4
b_e         dsb 4               ; the energy now
b_e0        dsb 4               ; the energy of the start
.ENDS
.BASE $80

.SECTION ".ui_balls_asm_text" SUPERFREE

; void ui_balls_move(void): moves the balls by a frame, turns them, bounces
; them on the walls (goutkozes) and on each other (ggutkozes). Called from
; C (DB = $7E, D = 0).
ui_balls_move:
	php
	rep #$30
	ldx #(NBALLS-1)*2
_move:
	lda ui_bx,x
	clc
	adc ui_bvx,x
	sta ui_bx,x
	lda ui_by,x
	clc
	adc ui_bvy,x
	sta ui_by,x
	lda ui_ba,x
	clc
	adc ui_bw,x
	sta ui_ba,x
	; Turned back when touching a wall and going towards it:
	lda ui_bvx,x
	bmi _left
	lda ui_bx,x
	clc
	adc ui_br,x
	cmp #WALL_X+1
	bcc _ydir
	bra _flipx
_left:
	lda ui_bx,x
	sec
	sbc ui_br,x
	bpl _ydir
_flipx:
	lda #0
	sec
	sbc ui_bvx,x
	sta ui_bvx,x
_ydir:
	lda ui_bvy,x
	bmi _up
	lda ui_by,x
	clc
	adc ui_br,x
	cmp #WALL_Y+1
	bcc _nextb
	bra _flipy
_up:
	lda ui_by,x
	sec
	sbc ui_br,x
	bpl _nextb
_flipy:
	lda #0
	sec
	sbc ui_bvy,x
	sta ui_bvy,x
_nextb:
	dex
	dex
	bpl _move

	; Pairs: |dx| and |dy| both under the sum of the radii.
	sep #$20
	stz ui_bpairs
	rep #$20
	ldx #0                      ; i times 2
_pi:
	txy
	iny
	iny                         ; j times 2
_pj:
	cpy #NBALLS*2
	bcs _ni
	lda ui_br,x
	clc
	adc ui_br,y
	sta.b tcc__r0               ; the sum of the radii
	lda ui_bx,y
	sec
	sbc ui_bx,x
	bpl +
	eor #$FFFF
	inc a
+	cmp.b tcc__r0
	bcs _nj
	lda ui_by,y
	sec
	sbc ui_by,x
	bpl +
	eor #$FFFF
	inc a
+	cmp.b tcc__r0
	bcs _nj
	; Close: listed.
	stx.b tcc__r1
	sty.b tcc__r1+2
	lda ui_bpairs
	and #$00FF
	asl a
	tax
	sep #$20
	lda.b tcc__r1
	sta ui_bpairs+1,x
	lda.b tcc__r1+2
	sta ui_bpairs+2,x
	inc ui_bpairs
	rep #$20
	ldx.b tcc__r1
	ldy.b tcc__r1+2
_nj:
	iny
	iny
	bra _pj
_ni:
	inx
	inx
	cpx #(NBALLS-1)*2
	bcc _pi

	; The pairs that touch bounce.
	lda ui_bpairs
	and #$00FF
	beq _nopairs
	sta b_n
	stz b_i
-	ldx b_i
	lda ui_bpairs+1,x
	and #$00FF
	sta b_p
	lda ui_bpairs+2,x
	and #$00FF
	sta b_q
	jsr _collide
	inc b_i
	inc b_i
	dec b_n
	bne -
_nopairs:
	plp
	rtl

; void ui_balls_energy(u16 set): the kinetic energy of the balls, sum of
; r*r/256 * |v|*|v|/256; with set it becomes the energy to keep, else the
; speeds are scaled towards it (the bounces of the original keep it; the
; rounding of the speeds here loses or gains a little at each bounce).
ui_balls_energy:
	php
	rep #$30
	stz b_e
	stz b_e+2
	ldx #(NBALLS-1)*2
-	stx b_ball
	lda ui_bvx,x
	sta b_ma
	sta b_mb
	jsr _mul
	lda b_mr+1
	sta b_s
	ldx b_ball
	lda ui_bvy,x
	sta b_ma
	sta b_mb
	jsr _mul
	lda b_mr+1
	clc
	adc b_s
	sta b_mb                    ; |v|^2 / 256
	ldx b_ball
	lda ui_bsz,x
	asl a
	tax
	lda.l _km,x
	sta b_ma
	jsr _mul
	lda b_mr
	clc
	adc b_e
	sta b_e
	lda b_mr+2
	adc b_e+2
	sta b_e+2
	ldx b_ball
	dex
	dex
	bpl -
	lda 5,s
	beq +
	lda b_e
	sta b_e0
	lda b_e+2
	sta b_e0+2
	plp
	rtl
+	; The ratio of the energies times 256, both shifted to 16 bits:
	lda b_e
	ora b_e+2
	bne +
	plp
	rtl                         ; nothing moves
+	lda b_e0
	sta b_mr
	lda b_e0+2
	sta b_mr+2
-	lda b_e+2
	beq +
	lsr b_e+2
	ror b_e
	lsr b_mr+2
	ror b_mr
	bra -
+	lda b_e
	sta b_d
	; b_mr * 256 / b_d:
	lda b_mr+2
	cmp #$0080
	bcs _escale_max             ; far too slow: as fast as allowed
	xba
	and #$FF00
	sta b_mr+2
	lda b_mr+1
	and #$00FF
	ora b_mr+2
	sta b_mr+2
	lda b_mr
	xba
	and #$FF00
	sta b_mr
	lda b_mr+2
	cmp b_d
	bcs _escale_max             ; the quotient would not fit
	jsr _div32
	bra +
_escale_max:
	lda #320
+	; sqrt: 1 + (r - 1) / 2 near 1, within 0.75 and 1.25:
	cmp #192
	bcs +
	lda #192
+	cmp #320
	bcc +
	lda #320
+	lsr a
	clc
	adc #128
	sta b_mb
	ldx #(NBALLS-1)*2
-	stx b_ball
	lda ui_bvx,x
	sta b_ma
	jsr _mulr
	ldx b_ball
	lda b_mr+1
	sta ui_bvx,x
	lda ui_bvy,x
	sta b_ma
	jsr _mulr
	ldx b_ball
	lda b_mr+1
	sta ui_bvy,x
	dex
	dex
	bpl -
	plp
	rtl

; r*r/256 of the sizes (the radii 614, 768, 1280 in 1/64 pixels) / 4:
_km:
	.dw 368, 576, 1600

; b_ma * b_mb (signed) -> b_mr, with the multiplier of the PPU (16 x 8
; bits): the low byte of b_mb taken as signed, the high byte corrected.
_mul:
	sep #$20
	lda b_ma
	sta.l $00211B
	lda b_ma+1
	sta.l $00211B
	lda b_mb
	sta.l $00211C
	rep #$20
	lda.l $002134
	sta b_mr
	lda.l $002135
	xba
	and #$00FF
	cmp #$0080
	bcc +
	ora #$FF00
+	sta b_mr+2
	; The high byte, plus one if the low byte was taken as negative:
	lda b_mb
	xba
	and #$00FF
	cmp #$0080
	bcc +
	ora #$FF00
+	sta b_a
	lda b_mb
	and #$0080
	beq +
	inc b_a
+	sep #$20
	lda b_a
	sta.l $00211C
	rep #$20
	lda.l $002134
	clc
	adc b_mr+1
	sta b_mr+1
	sep #$20
	lda.l $002136
	adc b_mr+3
	sta b_mr+3
	rep #$20
	rts

; The same, rounded to whole multiples of 256 (b_mr+1 is the product / 256
; rounded to the nearest: floors would add to the speeds at each bounce).
_mulr:
	jsr _mul
	lda b_mr
	clc
	adc #$0080
	sta b_mr
	lda b_mr+2
	adc #0
	sta b_mr+2
	rts

; A / b_a (unsigned, b_a 1-255) -> A, with the divider of the CPU.
_div:
	sta.l $004204
	sep #$20
	lda b_a
	sta.l $004206
	rep #$20
	nop                         ; 16 cycles
	nop
	nop
	nop
	nop
	nop
	nop
	lda.l $004214
	rts

; b_mr / b_d (32 by 16 bits, unsigned) -> A; the quotient fits in 16.
_div32:
	lda #0
	ldx #32
-	asl b_mr
	rol b_mr+2
	rol a
	bcs +
	cmp b_d
	bcc ++
+	sbc b_d
	inc b_mr
++	dex
	bne -
	lda b_mr
	rts

; A signed >> 4 -> A
_asr4:
	cmp #$8000
	ror a
	cmp #$8000
	ror a
	cmp #$8000
	ror a
	cmp #$8000
	ror a
	rts

; ggutkozes of b_p and b_q if they touch: the speeds along the normal are
; exchanged as an elastic bounce of masses r*r, and the rubbing at the
; touch turns them (F of the original, its denominator as it is).
_collide:
	ldx b_p
	ldy b_q
	lda ui_bx,y
	sec
	sbc ui_bx,x
	jsr _asr4
	sta b_dx
	lda ui_by,y
	sec
	sbc ui_by,x
	jsr _asr4
	sta b_dy
	lda ui_br,x
	clc
	adc ui_br,y
	lsr a
	lsr a
	lsr a
	lsr a
	sta b_rr
	; The distance squared (under 2*160*160):
	lda b_dx
	sta b_ma
	sta b_mb
	jsr _mul
	lda b_mr
	sta b_d
	lda b_dy
	sta b_ma
	sta b_mb
	jsr _mul
	lda b_mr
	clc
	adc b_d
	sta b_d                     ; d2
	bne +
	rts                         ; at the same place
+	lda b_rr
	sta b_ma
	sta b_mb
	jsr _mul
	lda b_d
	cmp b_mr
	bcc +
	rts                         ; not touching
+	; The distance: two steps of Newton from the sum of the radii.
	lda b_rr
	sta b_a
	lda b_d
	jsr _div
	clc
	adc b_rr
	lsr a
	bne +
	inc a
+	sta b_a
	lda b_d
	jsr _div
	clc
	adc b_a
	lsr a
	bne +
	inc a
+	sta b_a                     ; the distance
	; The normal: d* 256 / the distance, with the sign of d.
	lda b_dx
	bpl +
	eor #$FFFF
	inc a
+	xba
	and #$FF00
	jsr _div
	ldx b_dx
	bpl +
	eor #$FFFF
	inc a
+	sta b_nx
	lda b_dy
	bpl +
	eor #$FFFF
	inc a
+	xba
	and #$FF00
	jsr _div
	ldx b_dy
	bpl +
	eor #$FFFF
	inc a
+	sta b_ny
	; The speed of q against p, along the normal and the tangent:
	ldx b_p
	ldy b_q
	lda ui_bvx,y
	sec
	sbc ui_bvx,x
	sta b_dvx
	lda ui_bvy,y
	sec
	sbc ui_bvy,x
	sta b_dvy
	; dv . dr (32 bits): going apart when it is not negative.
	lda b_dvx
	sta b_ma
	lda b_dx
	sta b_mb
	jsr _mul
	lda b_mr
	sta b_s
	lda b_mr+2
	sta b_s+2
	lda b_dvy
	sta b_ma
	lda b_dy
	sta b_mb
	jsr _mul
	lda b_mr
	clc
	adc b_s
	sta b_mr
	lda b_mr+2
	adc b_s+2
	sta b_mr+2
	bmi +
	rts                         ; going apart
+	; The speed along the normal over the distance, times 256: dv . dr
	; * 256 / d2, exact (a normal of a rounded length would bounce harder
	; or softer than an elastic bounce).
	lda #0
	sec
	sbc b_mr
	sta b_mr
	lda #0
	sbc b_mr+2
	sta b_mr+2
	lda b_mr+1
	sta b_mr+2
	lda b_mr0
	and #$FF00
	sta b_mr
	jsr _div32
	eor #$FFFF
	inc a
	sta b_vn
	lda b_dvy
	sta b_ma
	lda b_nx
	sta b_mb
	jsr _mulr
	lda b_mr+1
	sta b_vt
	lda b_dvx
	sta b_ma
	lda b_ny
	sta b_mb
	jsr _mulr
	lda b_vt
	sec
	sbc b_mr+1
	sta b_vt
	; The table index of the sizes:
	ldx b_p
	lda ui_bsz,x
	asl a
	adc ui_bsz,x                ; times 3
	ldy b_q
	clc
	adc ui_bsz,y
	asl a
	sta b_k
	; p: + kv(p, q) / 256 * vn / 256 * dr
	tax
	lda.l _kv,x
	sta b_ma
	lda b_vn
	sta b_mb
	jsr _mulr
	lda b_mr+1
	ldy b_p
	jsr _addv
	; q: - kv(q, p) / 256 * vn / 256 * dr
	ldx b_q
	lda ui_bsz,x
	asl a
	adc ui_bsz,x
	ldy b_p
	clc
	adc ui_bsz,y
	asl a
	tax
	lda.l _kv,x
	sta b_ma
	lda b_vn
	sta b_mb
	jsr _mulr
	lda b_mr+1
	eor #$FFFF
	inc a
	ldy b_q
	jsr _addv
	; Rubbing: the tangential speed minus the speeds of the surfaces.
	ldx b_p
	lda ui_bw,x
	jsr _asr2
	sta b_ma
	lda ui_bsz,x
	asl a
	tax
	lda.l _kr,x
	sta b_mb
	jsr _mulr
	lda b_vt
	sec
	sbc b_mr+1
	sta b_vt
	ldx b_q
	lda ui_bw,x
	jsr _asr2
	sta b_ma
	lda ui_bsz,x
	asl a
	tax
	lda.l _kr,x
	sta b_mb
	jsr _mulr
	lda b_vt
	sec
	sbc b_mr+1
	sta b_vt                    ; G
	ldx b_k
	lda.l _kw1,x
	sta b_ma
	lda b_vt
	sta b_mb
	jsr _mulr
	ldx b_p
	lda ui_bw,x
	clc
	adc b_mr+1
	sta ui_bw,x
	ldx b_k
	lda.l _kw2,x
	sta b_ma
	lda b_vt
	sta b_mb
	jsr _mulr
	ldx b_q
	lda ui_bw,x
	clc
	adc b_mr+1
	sta ui_bw,x
	rts

; Adds A * dr / 256 to the speed of ball Y (times 2).
_addv:
	sty b_ball
	sta b_ma
	lda b_dx
	sta b_mb
	jsr _mulr
	ldx b_ball
	lda ui_bvx,x
	clc
	adc b_mr+1
	sta ui_bvx,x
	lda b_dy
	sta b_mb
	jsr _mulr
	ldx b_ball
	lda ui_bvy,x
	clc
	adc b_mr+1
	sta ui_bvy,x
	rts

_asr2:
	cmp #$8000
	ror a
	cmp #$8000
	ror a
	rts

; Of a collision of sizes i and j (m = r*r, the radii 614, 768, 1280 in
; 1/64 pixels): 2 mj / (mi + mj) times 256, the change of the speed of i;
; the changes of the turning of i and j (angle units a frame, 10430 a
; radian) for a rubbing speed in 1/64 pixels a frame, times 256: 10430 mj /
; ((5 mj + mi) ri) and 10430 mi / ((5 mj + mi) rj).
_kv:
	.dw 256, 312, 416, 199, 256, 376, 95, 135, 256
_kw1:
	.dw 725, 771, 831, 530, 579, 649, 223, 268, 348
_kw2:
	.dw 725, 394, 92, 1037, 579, 140, 2023, 1242, 348
; The speed of the surface of a turning ball, 1/64 pixels a frame for a
; quarter of its angle units a frame, times 256: r * 4 * 256 / 10430.
_kr:
	.dw 60, 75, 126

; void ui_balls_sprites(s16 dy): the sprites of the balls (OAM 1-9),
; moved down by dy lines, or off the screen. From C (DB = $7E: the OAM
; shadow in low RAM is there too).
ui_balls_sprites:
	php
	rep #$30
	lda 5,s
	sta.b tcc__r1               ; dy
	stz.b tcc__r4               ; the bits of the high table, 2 a sprite
	stz.b tcc__r4h
	ldx #(NBALLS-1)*2
	txa
	asl a
	adc #4
	tay                         ; OAM of sprite 9
_spr:
	lda ui_bx,x
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	sec
	sbc ui_bhalf,x
	sta.b tcc__r2               ; x
	lda ui_by,x
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	sec
	sbc ui_bhalf,x
	clc
	adc.b tcc__r1
	sta.b tcc__r3               ; y
	; Off the screen at x 256 (a sprite of 64 lines would come around
	; from the bottom):
	cmp #224
	bpl _off
	cmp #-63
	bmi _off
	lda.b tcc__r2
	cmp #256
	bpl _off
	cmp #-63
	bpl _on
_off:
	lda #256
	sta.b tcc__r2
	lda #224
	sta.b tcc__r3
_on:
	sep #$20
	lda.b tcc__r2
	sta core_oam,y
	lda.b tcc__r3
	sta core_oam+1,y
	lda ui_btile,x
	sta core_oam+2,y
	lda ui_btile+1,x
	and #$01
	ora #$28                    ; priority 2, palette 4 (color math)
	sta core_oam+3,y
	rep #$20
	; Two bits: the size and bit 8 of x.
	asl.b tcc__r4
	rol.b tcc__r4h
	asl.b tcc__r4
	rol.b tcc__r4h
	lda.b tcc__r2
	xba
	and #$0001
	ora ui_bbig,x
	ora.b tcc__r4
	sta.b tcc__r4
	dey
	dey
	dey
	dey
	dex
	dex
	bpl _spr
	; Sprites 1-9: bits 2-7 of byte 512, byte 513, bits 0-3 of byte 514.
	sep #$20
	lda.b tcc__r4
	asl a
	asl a
	sta.b tcc__r5
	lda core_oam+512
	and #$03
	ora.b tcc__r5
	sta core_oam+512
	rep #$20
	lda.b tcc__r4
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	sep #$20
	sta core_oam+513
	rep #$20
	lda.b tcc__r4+1             ; bits 8-23
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	and #$000F
	sta.b tcc__r5
	sep #$20
	lda core_oam+514
	and #$F0
	ora.b tcc__r5
	sta core_oam+514
	plp
	rtl

.ENDS
