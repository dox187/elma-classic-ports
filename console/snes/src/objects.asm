; The objects of the level as sprites: apples, the flower, killers
; (kirakegyjatekost of KIRAJ320.CPP).
;
; Each kind of object has one 16x16 picture in the VRAM (tiles 192 + 2k):
; the current frame of its animation (anim::getframe, 0.014 game time a
; frame). The frames that changed of the kinds on the screen go to the VRAM
; straight from the ROM through the queue of the NMI (two transfers each). Apples and the flower bob up and down (5 pixels of
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
O_OX        dw
O_X         dw
O_VIS       dw          ; bit k: kind k on the screen
.ENDE

.BASE $00

.RAMSECTION ".obj_vars" BANK $7E SLOT 2
bike_org_x  dsb 4       ; origin of the level pixels (16.16)
bike_org_y  dsb 4
obj_count   dw
obj_used    dw          ; bit k: the level has objects of kind k
obj_x       dsw 64      ; center in level pixels
obj_y       dsw 64
obj_ta      dsw 64      ; tile | attributes << 8 (by its kind)
obj_kbit    dsw 64      ; 1 << its kind
obj_poff    dsw 64      ; offset of an apple in phys_objs, $FFFF: not one
obj_phase   dsw 64      ; phase of the bobbing (0-255), $FFFF: none
obj_curf    dsw 8       ; frame of each kind in the VRAM, $FFFF: none
obj_ba      dw          ; angle of the bobbing (0-255 in the high byte)
obj_acc     dsb 4       ; time * OBJ_ANIM_K (frames since the start: high word)
obj_time    dw          ; the time of the last frame
obj_prevac  dw          ; frames since the start in the last frame
obj_kf      dsw 8       ; the frame of each kind now
obj_oam_end dw          ; end of the sprites written in the last frame
obj_dirty   dw          ; bit k: the frame of kind k in the VRAM is not obj_kf
.ENDS

.BASE $80

.SECTION ".obj_text" SUPERFREE

; The bit of x >= 256 of a sprite in the high table:
ob_hb:
	.db 1, 4, 16, 64

;---------------------------------------------------------------------------
; void obj_reset(void): no frame loaded.
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
	lda #$FFFE                  ; neither the time nor the frames follow
	sta.l obj_time
	sta.l obj_prevac
	lda #0
	sta.l obj_dirty
	ldx.w #OAM_OBJ*4            ; the sprites hidden
	txa
	sta.l obj_oam_end
	lda #$E000                  ; x 0, y 224
-	sta.l core_oam,x
	inx
	inx
	inx
	inx
	cpx.w #128*4
	bcc -
	plb
	plp
	rtl

;---------------------------------------------------------------------------
; void objects_draw(s16 cam_x, s16 cam_y, u16 time)
; DB = $7E throughout: the variables and the low RAM; I/O with long
; addresses.
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
	pea $7E7E
	plb
	plb
	jsr ob_time
	jsr ob_sprites
	jsr ob_frames
objects_draw_end:
	pld
	plb
	plp
	rtl

;---------------------------------------------------------------------------
; O_T2:O_T3 = O_T0 * O_T1 (unsigned, CPU multiplier).
ob_mul:
	sep #$20
	lda.b O_T0
	sta.l $004202
	lda.b O_T1
	sta.l $004203
	nop
	nop
	nop
	rep #$20
	lda.l $004216
	sta.b O_T2                  ; a0 b0
	stz.b O_T3
	sep #$20
	lda.b O_T1+1
	sta.l $004203
	nop
	nop
	nop
	rep #$20
	lda.l $004216
	sta.b O_T4                  ; a0 b1
	sep #$20
	lda.b O_T0+1
	sta.l $004202
	lda.b O_T1
	sta.l $004203
	nop
	nop
	nop
	rep #$20
	lda.l $004216
	sta.b O_T5                  ; a1 b0
	sep #$20
	lda.b O_T1+1
	sta.l $004203
	nop
	nop
	nop
	rep #$20
	lda.l $004216
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
; The time of the animations. Frames since the start: time * OBJ_ANIM_K
; >> 16; angle of the bobbing: time * OBJ_BOB_K. Added to when the time
; grew by a few steps, multiplied else.
ob_time:
	lda obj_time
	cmp.w #$FFFE
	beq _mul
	lda.b O_TIME
	sec
	sbc obj_time
	beq _have
	cmp.w #5
	bcs _mul
	tax
-	lda obj_acc
	clc
	adc.w #OBJ_ANIM_K
	sta obj_acc
	bcc +
	inc obj_acc+2
+	lda obj_ba
	clc
	adc.w #OBJ_BOB_K
	sta obj_ba
	dex
	bne -
	bra _have
_mul:
	lda.b O_TIME
	sta.b O_T0
	lda.w #OBJ_ANIM_K
	sta.b O_T1
	jsr ob_mul
	lda.b O_T2
	sta obj_acc
	lda.b O_T3
	sta obj_acc+2
	lda.w #OBJ_BOB_K
	sta.b O_T1
	jsr ob_mul
	lda.b O_T2
	sta obj_ba
_have:
	lda.b O_TIME
	sta obj_time
	lda obj_acc+2
	sta.b O_AC
	rts

;---------------------------------------------------------------------------
; The frames of the animations: loads the ones that changed of the kinds
; on the screen (O_VIS).
ob_frames:
	; Room in the queue for 2 transfers a kind (else nothing changes now:
	; the frames are counted from obj_prevac the next time):
	lda core_dmaq_n
	cmp.w #(DMAQ_MAX-2*OBJ_KINDS)*8+1
	bcc +
	rts
+	; f = ac mod frames of the kind: the same as in the last frame, one
	; more, or divided.
	lda.b O_AC
	sec
	sbc obj_prevac
	sta.b O_T5
	bne +
	lda obj_dirty               ; the same frames: only kinds that came
	and.b O_VIS                 ; onto the screen may want theirs
	bne +
	rts
+	stz obj_dirty
	lda obj_used
	sta.b O_T4                  ; the kinds left
	ldx #0                      ; 2 * kind
_kind:
	lsr.b O_T4
	bcc _knext
	lda.b O_T5
	bne +
	lda obj_kf,x
	bra _cmp
+	dec a
	bne _div
	lda obj_kf,x
	inc a
	cmp.l obj_kind_nfr,x
	bcc _kf
	lda #0
	bra _kf
_div:
	lda.b O_AC
	sta.l $004204
	sep #$20
	lda.l obj_kind_nfr,x
	sta.l $004206
	rep #$20
	nop
	nop
	nop
	nop
	nop
	lda.l $004216
_kf:
	sta obj_kf,x
_cmp:
	cmp obj_curf,x
	beq _knext
	tay
	lda.l ob_bits,x
	and.b O_VIS
	beq _dirty
	tya
	sta obj_curf,x
	jsr ob_load
	bra _knext
_dirty:
	lda.l ob_bits,x
	tsb obj_dirty
_knext:
	inx
	inx
	lda.b O_T4
	bne _kind
	lda.b O_AC
	sta obj_prevac
	rts

; Frame A of kind X/2 straight from the ROM to the VRAM: its two transfers
; of the queue (obj_q, gen_bike.py). Keeps X.
ob_load:
	asl a
	asl a
	asl a
	asl a                       ; 16 bytes a frame
	adc.l obj_q_offs,x
	phx
	tax
	ldy core_dmaq_n
	lda.l obj_q,x
	sta core_dmaq,y
	lda.l obj_q+2,x
	sta core_dmaq+2,y
	lda.l obj_q+4,x
	sta core_dmaq+4,y
	lda.l obj_q+6,x
	sta core_dmaq+6,y
	lda.l obj_q+8,x
	sta core_dmaq+8,y
	lda.l obj_q+10,x
	sta core_dmaq+10,y
	lda.l obj_q+12,x
	sta core_dmaq+12,y
	lda.l obj_q+14,x
	sta core_dmaq+14,y
	tya
	clc
	adc #16
	sta core_dmaq_n
	lda core_dmaq_bytes
	adc #128
	sta core_dmaq_bytes
	plx
	rts

ob_bits:
	.dw 1, 2, 4, 8, 16, 32, 64, 128

;---------------------------------------------------------------------------
; The sprites. Y = 2 * object. Positions are biased by 256 pixels: a
; sprite is on the screen when x is 241..511 and y 241..479.
ob_sprites:
	lda.b O_CAMX
	clc
	adc.w #8-256+241
	sta.b O_T2                  ; x - O_T2 = biased x - 241
	lda.b O_CAMY
	clc
	adc.w #8-256+241
	sta.b O_T3
	lda obj_ba
	xba
	and #$00FF
	sta.b O_T4                  ; angle of the bobbing (0-255)
	stz core_oam+512+OAM_OBJ/4
	stz core_oam+512+OAM_OBJ/4+2
	stz core_oam+512+OAM_OBJ/4+4
	stz core_oam+512+OAM_OBJ/4+6
	stz core_oam+512+OAM_OBJ/4+8
	stz core_oam+512+OAM_OBJ/4+10
	stz core_oam+512+OAM_OBJ/4+12
	stz core_oam+512+OAM_OBJ/4+14
	ldx.w #OAM_OBJ*4
	stx.b O_OX
	stz.b O_VIS
	lda obj_count
	asl a
	tay
_obj:
	dey
	dey
	bmi _hide
	lda obj_x,y
	sec
	sbc.b O_T2
	cmp.w #512-241
	bcs _obj
	sta.b O_X                   ; x - 241
	ldx obj_poff,y              ; an apple: not eaten?
	bmi +
	lda.l phys_objs+PO_ACTIVE,x
	and #$00FF
	beq _obj
+	ldx obj_phase,y             ; killers do not bob
	bmi _still
	txa
	clc
	adc.b O_T4
	and #$00FF
	asl a
	tax
	lda.l bike_t_bob16,x
	clc
	adc obj_y,y
	bra +
_still:
	lda obj_y,y
+	sec
	sbc.b O_T3
	cmp.w #480-241
	bcs _obj
	adc.w #241
	ldx.b O_OX
	sta core_oam+1,x            ; y (its high byte goes into the tile)
	lda obj_ta,y
	sta core_oam+2,x
	lda.b O_X
	adc.w #241                  ; (C clear)
	sep #$20
	sta core_oam,x              ; x
	rep #$20
	cmp.w #256
	bcs +
	jsr ob_x8
+	lda obj_kbit,y
	tsb.b O_VIS
	inx
	inx
	inx
	inx
	stx.b O_OX
	cpx.w #128*4
	bcc _obj
_hide:
	; Hide the sprite after the last and the ones used in the last frame.
	ldx.b O_OX
	cpx obj_oam_end
	bcs +
	lda #$E000                  ; y 224
-	sta core_oam,x
	inx
	inx
	inx
	inx
	cpx obj_oam_end
	bcc -
+	lda.b O_OX
	sta obj_oam_end
	rts

; Sets the bit of x >= 256 of the sprite at X in core_oam.
ob_x8:
	phx
	txa
	lsr a
	lsr a
	and #$0003
	tax
	sep #$20
	lda.l ob_hb,x
	sta.b O_T0
	rep #$20
	lda 1,s
	lsr a
	lsr a
	lsr a
	lsr a
	tax
	sep #$20
	lda.b O_T0
	ora core_oam+512,x
	sta core_oam+512,x
	rep #$20
	plx
	rts

.ENDS
