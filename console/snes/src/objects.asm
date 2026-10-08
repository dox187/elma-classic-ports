; The objects of the level as sprites: apples, the flower, killers
; (kirakegyjatekost of KIRAJ320.CPP).
;
; Each kind of object has one 16x16 picture in the VRAM (tiles 192 + 2k):
; the current frame of its animation (anim::getframe, 0.014 game time a
; frame). A frame that changed is copied into a copy of the two tile rows in
; the RAM, then the changed range goes to the VRAM through the queue of the
; NMI (two transfers). Apples and the flower bob up and down (5 pixels of
; the original game, sin(t * 15.5 + phase)). Eaten apples and the start are
; not drawn. OAM 64-127, the last object of the level first (on top).

.include "hdr.asm"
.include "core.inc"
.include "bike_data.inc"

.DEFINE PO_ACTIVE   3
.DEFINE PRIO        $20         ; priority 2: behind the front pictures
.DEFINE OAM_OBJ     64
.DEFINE VRAM_OBJS   VRAM_OBJ+192*16

; Direct page (bike_dp, shared with bike_draw):
.ENUM $00
O_CAMX      dw
O_CAMY      dw
O_TIME      dw
O_T0        dw
O_T1        dw
O_T2        dw
O_T3        dw
O_T4        dw
O_T5        dw
O_AC        dw          ; frames of the animations since the start
O_LO        dw
O_HI        dw
O_PTR       dsb 4
O_SRC       dsb 4
O_OX        dw
O_N         dw
O_X         dw
O_Y         dw
O_K         dw
.ENDE

.BASE $00

.RAMSECTION ".obj_vars" BANK $7E SLOT 2
bike_org_x  dsb 4       ; origin of the level pixels (16.16)
bike_org_y  dsb 4
obj_count   dw
obj_used    dw          ; bit k: the level has objects of kind k
obj_x       dsw 64      ; center in level pixels
obj_y       dsw 64
obj_kind    dsw 64      ; 0 flower, 1 killer, 2.. apples
obj_poff    dsw 64      ; offset of the object in phys_objs
obj_phase   dsw 64      ; phase of the bobbing (0-255)
obj_curf    dsw 8       ; frame of each kind in the VRAM, $FFFF: none
obj_ba      dw          ; angle of the bobbing (0-255 in the high byte)
obj_stage   dsb 1024    ; tiles 192-207, 208-223
.ENDS

.BASE $80

.SECTION ".obj_text" SUPERFREE

; The bit of x >= 256 of a sprite in the high table:
ob_hb:
	.db 1, 4, 16, 64
ob_zero:
	.db 0

;---------------------------------------------------------------------------
; void obj_reset(void): no frame loaded, the copy of the rows cleared.
obj_reset:
	php
	phb
	rep #$30
	sep #$20
	lda #$80
	pha
	plb
	rep #$20
	lda #$FFFF
	ldx #0
-	sta.l obj_curf,x
	inx
	inx
	cpx #16
	bcc -
	lda.w #obj_stage
	sta $2181
	sep #$20
	lda.b #:obj_stage & 1
	sta $2183
	lda #$08                    ; fixed source, one register
	sta $4370
	lda #$80
	sta $4371
	rep #$20
	lda.w #ob_zero
	sta $4372
	sep #$20
	lda.b #:ob_zero
	sta $4374
	rep #$20
	lda #1024
	sta $4375
	sep #$20
	lda #$80
	sta $420B
	plb
	plp
	rtl

;---------------------------------------------------------------------------
; void objects_draw(s16 cam_x, s16 cam_y, u16 time)
objects_draw:
	php
	phb
	phd
	rep #$30
	lda 8,s
	tax
	lda 10,s
	tay
	lda 12,s
	pea bike_dp
	pld
	sta.b O_TIME
	stx.b O_CAMX
	sty.b O_CAMY
	sep #$20
	lda #$80
	pha
	plb
	rep #$30
	jsr ob_anim
	sep #$20
	lda #$7E
	pha
	plb
	rep #$30
	jsr ob_sprites
objects_draw_end:
	pld
	plb
	plp
	rtl

;---------------------------------------------------------------------------
; O_T2:O_T3 = O_T0 * O_T1 (unsigned, CPU multiplier; DB = $80).
ob_mul:
	sep #$20
	lda.b O_T0
	sta $4202
	lda.b O_T1
	sta $4203
	nop
	nop
	nop
	rep #$20
	lda $4216
	sta.b O_T2                  ; a0 b0
	stz.b O_T3
	sep #$20
	lda.b O_T1+1
	sta $4203
	nop
	nop
	nop
	rep #$20
	lda $4216
	sta.b O_T4                  ; a0 b1
	sep #$20
	lda.b O_T0+1
	sta $4202
	lda.b O_T1
	sta $4203
	nop
	nop
	nop
	rep #$20
	lda $4216
	sta.b O_T5                  ; a1 b0
	sep #$20
	lda.b O_T1+1
	sta $4203
	nop
	nop
	nop
	rep #$20
	lda $4216
	sta.b O_T3                  ; a1 b1
	lda.b O_T4
	jsr _add
	lda.b O_T5
_add:
	pha
	xba
	and #$FF00
	clc
	adc.b O_T2
	sta.b O_T2
	pla
	xba
	and #$00FF
	adc.b O_T3
	sta.b O_T3
	rts

;---------------------------------------------------------------------------
; The frames of the animations: loads the ones that changed (DB = $80).
ob_anim:
	; Frames since the start: time * OBJ_ANIM_K >> 16; angle of the
	; bobbing: time * OBJ_BOB_K.
	lda.b O_TIME
	sta.b O_T0
	lda.w #OBJ_ANIM_K
	sta.b O_T1
	jsr ob_mul
	lda.b O_T3
	sta.b O_AC
	lda.w #OBJ_BOB_K
	sta.b O_T1
	jsr ob_mul
	lda.b O_T2
	sta.l obj_ba
	; Room in the queue for 2 transfers:
	lda core_dmaq_n
	cmp.w #(DMAQ_MAX-2)*8+1
	bcc +
	rts
+	lda #$FFFF
	sta.b O_LO
	sep #$20
	lda #$00
	sta $4370
	lda #$80
	sta $4371
	stz $2183
	lda.b #:obj_kind_table
	sta.b O_PTR+2
	rep #$20
	stz.b O_K
_kind:
	lda.b O_K
	tax
	lda.l obj_used
	and.l ob_bits,x
	beq _knext
	; f = ac mod frames of the kind:
	lda.b O_AC
	sta $4204
	txa
	lsr a
	tax
	sep #$20
	lda.l obj_kind_frames,x
	sta $4206
	nop
	nop
	nop
	nop
	nop
	nop
	rep #$20
	lda $4216
	sta.b O_T0
	ldx.b O_K
	cmp.l obj_curf,x
	beq _knext
	sta.l obj_curf,x
	; The pointer of the frame: obj_frames_k + f * 3.
	lda.l obj_kind_table,x
	sta.b O_PTR
	lda.b O_T0
	asl a
	clc
	adc.b O_T0
	tay
	lda [O_PTR],y
	sta.b O_SRC
	iny
	lda [O_PTR],y
	and #$FF00
	xba
	sta.b O_SRC+2
	; Into the copy of the rows (k * 64, + 512 for the bottom row):
	lda.b O_K
	asl a
	asl a
	asl a
	asl a
	asl a                       ; k * 64 (O_K = 2k)
	clc
	adc.w #obj_stage
	sta.b O_T1
	jsr _half
	lda.b O_SRC
	clc
	adc #64
	sta.b O_SRC
	lda.b O_T1
	clc
	adc #512
	jsr _half
	lda.b O_LO
	cmp #$FFFF
	bne +
	lda.b O_K
	sta.b O_LO
+	lda.b O_K
	sta.b O_HI
_knext:
	lda.b O_K
	inc a
	inc a
	sta.b O_K
	cmp.w #2*OBJ_KINDS
	bcs +
	jmp _kind
+
	; The queue: the range of the kinds that changed, top and bottom row.
	lda.b O_LO
	cmp #$FFFF
	bne +
	rts
+	lda.b O_HI
	sec
	sbc.b O_LO
	inc a
	inc a
	asl a
	asl a
	asl a
	asl a
	asl a                       ; (kinds) * 64
	sta.b O_T1
	lda.b O_LO
	asl a
	asl a
	asl a
	asl a
	asl a
	clc
	adc.w #obj_stage
	sta.b O_T2                  ; source
	lda.b O_LO
	asl a
	asl a
	asl a
	asl a
	clc
	adc.w #VRAM_OBJS
	sta.b O_T3                  ; VRAM: k * 32 words
	jsr ob_queue
	lda.b O_T2
	clc
	adc #512
	sta.b O_T2
	lda.b O_T3
	clc
	adc #256
	sta.b O_T3
; A transfer of O_T1 bytes from $7E:O_T2 to the VRAM at O_T3 (words).
ob_queue:
	ldx core_dmaq_n
	sep #$20
	lda.b #DMAQ_VRAM
	sta core_dmaq,x             ; type +0, source +1, bank +3, size +4,
	lda #$7E                    ; VRAM address +6
	sta core_dmaq+3,x
	rep #$20
	lda.b O_T2
	sta core_dmaq+1,x
	lda.b O_T1
	sta core_dmaq+4,x
	lda.b O_T3
	sta core_dmaq+6,x
	lda.b O_T1
	clc
	adc core_dmaq_bytes
	sta core_dmaq_bytes
	txa
	clc
	adc #8
	sta core_dmaq_n
	rts

; 64 bytes from O_SRC to $7E:A (DMA channel 7 into the WRAM).
_half:
	sta $2181
	lda.b O_SRC
	sta $4372
	sep #$20
	lda.b O_SRC+2
	sta $4374
	rep #$20
	lda #64
	sta $4375
	sep #$20
	lda #$80
	sta $420B
	rep #$20
	rts

ob_bits:
	.dw 1, 2, 4, 8, 16, 32, 64, 128

;---------------------------------------------------------------------------
; The sprites (DB = $7E).
ob_sprites:
	lda.w #OAM_OBJ*4
	sta.b O_OX
	stz.b O_N
	ldx #0
-	stz core_oam+512+OAM_OBJ/4,x
	inx
	inx
	cpx #16
	bcc -
	lda obj_count
	asl a
	tay
_obj:
	dey
	dey
	bpl +
	jmp _hide
+	lda obj_kind,y
	sta.b O_K
	cmp #2
	bcc +
	ldx obj_poff,y              ; an apple: not eaten?
	lda.l phys_objs+PO_ACTIVE,x
	and #$00FF
	beq _obj
+	lda obj_x,y
	sec
	sbc.b O_CAMX
	sec
	sbc #8
	sta.b O_X
	clc
	adc #15
	cmp #271
	bcs _obj
	lda #0
	ldx.b O_K
	cpx #1
	beq +                       ; killers do not bob
	lda obj_ba+1
	clc
	adc obj_phase,y
	and #$00FF
	tax
	lda.l bike_t_bob,x
	and #$00FF
	cmp #$0080
	bcc +
	ora #$FF00
+	clc
	adc obj_y,y
	sec
	sbc.b O_CAMY
	sec
	sbc #8
	sta.b O_Y
	clc
	adc #15
	cmp #239
	bcs _obj
	lda.b O_N
	cmp #64
	bcs _obj
	ldx.b O_OX
	sep #$20
	lda.b O_X
	sta core_oam,x
	lda.b O_Y
	sta core_oam+1,x
	lda.b O_K
	asl a
	clc
	adc #192
	sta core_oam+2,x
	lda.b #PRIO|3*2
	sta core_oam+3,x
	rep #$20
	lda.b O_X
	bpl +
	lda.b O_N
	clc
	adc.w #OAM_OBJ
	pha
	and #$0003
	tax
	sep #$20
	lda.l ob_hb,x
	sta.b O_T0
	rep #$20
	pla
	lsr a
	lsr a
	tax
	sep #$20
	lda.b O_T0
	ora core_oam+512,x
	sta core_oam+512,x
	rep #$20
+	lda.b O_OX
	clc
	adc #4
	sta.b O_OX
	inc.b O_N
	jmp _obj
_hide:
	ldx.b O_OX
-	cpx.w #128*4
	bcs +
	lda #$E000                  ; y 224
	sta core_oam,x
	inx
	inx
	inx
	inx
	bra -
+	rts

.ENDS
