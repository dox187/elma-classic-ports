; The bike and the rider as sprites (bike.h).
;
; The parts of the bike are drawn beforehand at many angles (tools/
; gen_bike.py); every frame bike_draw computes where each part is and at
; which angle, as kibike of the original game (KIRAJ320.CPP) does, picks the
; nearest picture, loads the pictures that changed into the VRAM and writes
; the sprites. test/bikefix.py does the same in Python, step by step.
;
; Units: 1/16 pixel, y up, relative to the center of the bike. The wheels'
; 32 pictures stay in the VRAM (tiles 0-127); the other parts have their
; places in two pairs of tile rows: tiles 128-159 (thigh, leg, upper arm,
; forearm, the 4 pieces of the suspensions) and 160-191 (head, torso, the
; body of the bike on up to 6 sprites). A picture that changed goes to the
; VRAM straight from the ROM through the queue of the NMI (bk_load), the
; ones that do not fit in a frame wait for the next one.
;
; The parts: 0 thigh, 1 leg, 2 upper arm, 3 forearm, 4-5 front suspension,
; 6-7 rear suspension, 8 head, 9 torso, 10 body of the bike.

.include "hdr.asm"
.include "core.inc"
.include "bike_data.inc"

; phys_view (bike_view_t) as 816-tcc lays it out (s32 on 4 bytes, aligned
; to 4 bytes):
.DEFINE PV_BODY_X   0
.DEFINE PV_BODY_Y   4
.DEFINE PV_BODY_A   8
.DEFINE PV_WHEEL_X  12
.DEFINE PV_WHEEL_Y  20
.DEFINE PV_WHEEL_A  28
.DEFINE PV_RIDER_X  32
.DEFINE PV_RIDER_Y  36
.DEFINE PV_HEAD_X   40
.DEFINE PV_HEAD_Y   44
.DEFINE PV_TURNED   48
; bike_anim (bike_anim_t):
.DEFINE BA_TURN     0
.DEFINE BA_VOLT     2
.DEFINE BA_VOLT1    4

.DEFINE TURN_DONE   65470       ; forgas >= 0.999: not turning
.DEFINE ENTRY_COST  96          ; an entry of the queue in the vertical blank,
.DEFINE LOAD_COST   1600+4*ENTRY_COST ; the loads of a frame: in bytes
.DEFINE OBJ_ROOM    2*OBJ_KINDS ; entries of the queue left for the objects
.DEFINE PRIO        $20         ; priority 2: behind the front pictures
.DEFINE FRAME       10          ; the part of the body of the bike
.DEFINE OAM_BIKE    32          ; first sprite of the bike
.DEFINE OAM_OBJ     64          ; first sprite of the objects
.DEFINE VRAM_PARTS  VRAM_OBJ+128*16

; The direct page of bike_draw (and objects_draw):
.ENUM $00
Z_CAMX      dw
Z_CAMY      dw
Z_BSX       dw          ; center of the bike on the screen (1/16 pixel)
Z_BSY       dw
Z_TH        dw          ; angle of the bike
Z_TR        dw          ; turned (hatra_f): 0 or 1
Z_C         db          ; cos and sin of the bike's angle, times 128
Z_S         db
Z_B         db          ; factors
Z_A         db
Z_MA        db          ; the squash of the turn: (f - 1) j j^T, times 64
Z_MB        db
Z_MD        db
Z_G         db
Z_T0        dw
Z_T1        dw
Z_T2        dw
Z_T3        dw
Z_T4        dw
Z_T5        dw
Z_VX        dw          ; a vector
Z_VY        dw
Z_AX        dw          ; atan2
Z_AY        dw
Z_W0X       dw          ; points: wheels (in this order), rider,
Z_W0Y       dw          ; handlebar, rear suspension, shoulder, hand,
Z_W1X       dw          ; elbow
Z_W1Y       dw
Z_RX        dw
Z_RY        dw
Z_HAX       dw
Z_HAY       dw
Z_REX       dw
Z_REY       dw
Z_SHX       dw
Z_SHY       dw
Z_KX        dw
Z_KY        dw
Z_ELX       dw
Z_ELY       dw
Z_ROT       dw          ; index of the tables of the bike's angle
Z_IDX       dw          ; index of the tables of a distance
Z_IDXT      dw          ; index of the tables of the limbs
Z_TI        dw          ; the bike's angle in 1024 steps
Z_TI2       dw          ; the same + 512 + 1024
Z_THM       dw          ; the bike's angle + 1/2
Z_A8        dw          ; an angle in 256 steps
Z_LV        dw          ; level of the squashed pictures, 4: not turning
Z_NEG       dw          ; the turn's squash is negative (mirrored)
Z_TEFF      dw          ; turned as drawn
Z_LATE      dw          ; the wheel drawn over the bike, $FFFF: none
Z_LEFT      dw          ; the time of the vertical blank left (bytes)
Z_PEND      dw          ; bit p: part p wants another picture
Z_PTR       dsb 4       ; a long pointer (a descriptor: bike_desc_single and
                        ; bike_desc_frame are in one bank)
Z_DST       dw
Z_NS        dw
Z_BXS       dw          ; the center of the bike on the screen, biased,
Z_BYS       dw          ; for the corner of a single sprite (bk_oam)
Z_TA        dw          ; tile | attributes << 8
Z_FL        dw          ; flips of a part
Z_PX        dw
Z_PY        dw
.ENDE

.BASE $00

.RAMSECTION ".bike_dp" BANK 0 SLOT 1 ALIGN 256
bike_dp     dsb 256
.ENDS

.RAMSECTION ".bike_vars" BANK 0 SLOT 1
bike_cur    dsw 11      ; the descriptor of each part in the VRAM, 0: none
bike_ta     dsw 11      ; its first tile | attributes << 8
bike_toggle dw          ; which group of parts loads first
bike_pend   dw          ; bit p: part p wants a picture not in the VRAM
bike_ph     dw          ; P_H is set for this Z_TR ($FFFF: not set)
bike_bn     dw          ; the sprites of the body (bk_bodyset)
bike_bx     dw          ; their corners for its flips (from bike_desc_single)
bike_bnl    dw          ; the sprites of the body in the last frame
bike_key    dsb 10      ; the step of the angle and the mirroring of the
                        ; picture of each single part in the last frame
                        ; ($FF: none)
bike_fkey   dw          ; the same for the body
bike_tkey   dw          ; the same for the single parts while turning
P_CX        dsw 11      ; the parts: center
P_CY        dsw 11
P_AL        dsw 11      ; angle
P_H         dsw 11      ; mirrored: 64 (128 for the body) or 0
W_DESC      dsw 11      ; the picture wanted (descriptor)
W_KF        dsw 11      ; its flips << 8
.ENDS

.BASE $80

; M7A = A (16 bits); A is 8 bits after it.
.MACRO MA
	sep #$20
	sta.w $211B
	xba
	sta.w $211B
.ENDM

; M7B = A (8 bits); A = bits 8-23 of the product (16 bits).
.MACRO MB
	sta.w $211C
	rep #$20
	lda.w $2135
.ENDM

; A >>= 1, keeping the sign (16 bits).
.MACRO ASR
	cmp.w #$8000
	ror a
.ENDM

; A = (2 * \1) * \2 >> 8: a word and a byte of the direct page (the byte
; times 128 makes it \1 * factor).
.MACRO MUL2
	rep #$20
	lda.b \1
	asl a
	MA
	lda.b \2
	MB
.ENDM

; The relative position of a point of phys_view, in units: the bytes 1-2
; of the 16.16 meters (1/256 meters) minus the body's, * 1.2 (77/64).
.MACRO CONV
	lda.l phys_view+\1+1
	sec
	sbc.b \2
	asl a
	asl a
	MA
	lda.b #77
	MB
	sta.b \3
.ENDM

; Part \1 (2 * part) wants W_DESC (in A, W_KF): pending if it is not in
; the VRAM, else its flips are taken.
.MACRO CHK
	cmp bike_cur+\1
	beq +
	lda.w #1<<(\1/2)
	tsb bike_pend
	bra ++
+	lda.w #1<<(\1/2)
	trb bike_pend
	lda W_KF+\1
	and.w #$FF00
	ora.l bk_ta0+\1
	cmp bike_ta+\1
	beq ++
	sta bike_ta+\1
++
.ENDM

; The step of the angle of a single part at 64 angles and its mirroring
; (\1 = 2 * part, 8 bits): its picture (bike_t_lk64, bike_t_d64) when they
; changed since the last frame (\2 = 1: the first piece of a suspension,
; the second one too).
.MACRO PIC64
	lda P_AL+\1+1
	clc
	adc #2
	lsr a
	lsr a
	ora P_H+\1
	cmp bike_key+\1/2
.IF \2 == 1
	bne +
	jmp +++
+
.ELSE
	beq +++
.ENDIF
	sta bike_key+\1/2
.IF \2 == 1
	sta bike_key+\1/2+1
.ENDIF
	rep #$20
	and #$00FF
	asl a
	tax
	lda.l bike_t_lk64,x
	sta W_KF+\1
.IF \2 == 1
	sta W_KF+\1+2
.ENDIF
	lda.l bike_t_d64+256*\1/2,x
	sta W_DESC+\1
	CHK \1
.IF \2 == 1
	lda W_DESC+\1
	clc
	adc.w #4*BK_PER_PART
	sta W_DESC+\1+2
	CHK \1+2
.ENDIF
	sep #$20
+++
.ENDM

; The OAM address of the sprite in place \1 of the bike (bk_oam).
.DEFINE BK_OAM      core_oam+4*OAM_BIKE
.DEFINE BK_HB       core_oam+512+OAM_BIKE/4

; x on the screen (A, biased by 256) to the OAM at \1, the bit of x >= 256
; at \2 with mask \3, checked on \4: 0 both sides, 1 the left one, 3 the
; right one. Off the screen: jumps to the next ++ (hidden).
.MACRO EDGEX
.IF \4 == 0
	sec
	sbc.w #256
	cmp.w #256
	bcc +
	cmp.w #-15 & $FFFF
	bcc ++
	pha
	sep #$20
	lda.b #\3
	tsb.w \2
	rep #$20
	pla
.ENDIF
.IF \4 == 1
	cmp.w #256
	bcs +
	cmp.w #241
	bcc ++
	pha
	sep #$20
	lda.b #\3
	tsb.w \2
	rep #$20
	pla
.ENDIF
.IF \4 == 3
	cmp.w #512
	bcs ++
.ENDIF
+	sta.w \1
.ENDM

; y on the screen (A, biased by 256) to the OAM at \1, or hidden.
.MACRO EDGEY
	sec
	sbc.w #256
	cmp.w #224
	bcc +
	cmp.w #-15 & $FFFF
	bcc ++
+	sta.w \1
.ENDM

; The modes of the sprites of the bike: 0 all of them on the screen, 1
; their x checked on the left (the bike near the left edge), 3 on the
; right, 2 x and y.

; The sprite of single part \1 (2 * part) in place \2, mode \3.
.MACRO PUT
	lda.b Z_BXS
	clc
	adc P_CX+\1
	lsr a
	lsr a
	lsr a
	lsr a
.IF \3 == 0
	sta.w BK_OAM+4*\2
.ELSE
	EDGEX BK_OAM+4*\2, BK_HB+\2/4, 1<<(2*(\2&3)), (\3&1)*\3
.ENDIF
	lda.b Z_BYS
	sec
	sbc P_CY+\1
	lsr a
	lsr a
	lsr a
	lsr a
.IF \3 == 2
	EDGEY BK_OAM+4*\2+1
.ELSE
	sta.w BK_OAM+4*\2+1
.ENDIF
	lda bike_ta+\1
	sta.w BK_OAM+4*\2+2
.IF \3 != 0
	bra +++
++	lda #$E000                  ; x 0, y 224
	sta.w BK_OAM+4*\2
+++
.ENDIF
.ENDM

; Sprite \1 (0-5) of the body in its place (7 + \1), mode \2: its corner
; from the pivot at bike_desc_single + X + 4 * \1.
.MACRO BODY
	lda.l bike_desc_single+4*\1,x
	clc
	adc.b Z_PX
.IF \2 == 0
	sta.w BK_OAM+4*(7+\1)
.ELSE
	EDGEX BK_OAM+4*(7+\1), BK_HB+(7+\1)/4, 1<<(2*((7+\1)&3)), (\2&1)*\2
.ENDIF
	lda.l bike_desc_single+4*\1+2,x
	clc
	adc.b Z_PY
.IF \2 == 2
	EDGEY BK_OAM+4*(7+\1)+1
.ELSE
	sta.w BK_OAM+4*(7+\1)+1
.ENDIF
	lda.b Z_TA
	clc
	adc.w #2*\1
	sta.w BK_OAM+4*(7+\1)+2
.IF \2 != 0
	bra +++
++	lda #$E000
	sta.w BK_OAM+4*(7+\1)
+++
.ENDIF
.ENDM

; Wheel \1 in place \2, mode \3.
.MACRO WHEEL
	lda.b Z_BXS
	clc
	adc.b Z_W0X+4*\1
	lsr a
	lsr a
	lsr a
	lsr a
.IF \3 == 0
	sta.w BK_OAM+4*\2
.ELSE
	EDGEX BK_OAM+4*\2, BK_HB+\2/4, 1<<(2*(\2&3)), (\3&1)*\3
.ENDIF
	lda.b Z_BYS
	sec
	sbc.b Z_W0Y+4*\1
	lsr a
	lsr a
	lsr a
	lsr a
.IF \3 == 2
	EDGEY BK_OAM+4*\2+1
.ELSE
	sta.w BK_OAM+4*\2+1
.ENDIF
	lda.l phys_view+PV_WHEEL_A+2*\1+1
	and #$00FF
	asl a
	tax
	lda.l bike_t_wheel256,x
	sta.w BK_OAM+4*\2+2
.IF \3 != 0
	bra +++
++	lda #$E000
	sta.w BK_OAM+4*\2
+++
.ENDIF
.ENDM

; The sprites of the bike in mode \1 (\2: the routine of the body in
; that mode), from the parts 3, 2 ... to the wheels.
.MACRO SPRITES
	PUT 2*3, 1, \1
	PUT 2*2, 2, \1
	PUT 2*9, 3, \1
	PUT 2*1, 4, \1
	PUT 2*0, 5, \1
	PUT 2*8, 6, \1
	jsr \2
	PUT 2*7, 13, \1
	PUT 2*6, 14, \1
	PUT 2*5, 15, \1
	PUT 2*4, 16, \1
	lda.b Z_LATE
	bmi +
	jmp bk_late
+	WHEEL 1, 17, \1
	WHEEL 0, 18, \1
	lda #$E000                  ; not turning: no wheel over the bike
	sta.w BK_OAM
	rts
.ENDM


; A (8 bits) = (A * Z_G >> 8) >> 6 (bits 6-13 of the product >> 8).
.MACRO M6
	MA
	lda.b Z_G
	MB
	asl a
	asl a
	xba
	sep #$20
.ENDM

; The squash of the center of part \1 (2 * part): x += x a + y b,
; y += x b + y d.
.MACRO SQ
	lda P_CX+\1
	asl a
	asl a
	MA
	lda.b Z_MA
	MB
	sta.b Z_T0                  ; x a
	sep #$20
	lda.b Z_MB
	MB
	sta.b Z_T1                  ; x b
	lda P_CY+\1
	asl a
	asl a
	MA
	lda.b Z_MB
	MB
	clc
	adc.b Z_T0
	clc
	adc P_CX+\1
	sta P_CX+\1
	sep #$20
	lda.b Z_MD
	MB
	clc
	adc.b Z_T1
	clc
	adc P_CY+\1
	sta P_CY+\1
.ENDM

; The angle of part \1 mirrored: Z_T0 - alpha.
.MACRO MIR
	lda.b Z_T0
	sec
	sbc P_AL+\1
	sta P_AL+\1
.ENDM

; The center of the rod of part \6 (2 * part) from a = (\1, \2) to b =
; (\3, \4): a + c * (b - a), c = \5 (times 128).
.MACRO CENTER
	lda.b \3
	sec
	sbc.b \1
	asl a
	MA
	lda.b #\5
	MB
	clc
	adc.b \1
	sta P_CX+\6
	lda.b \4
	sec
	sbc.b \2
	asl a
	MA
	lda.b #\5
	MB
	clc
	adc.b \2
	sta P_CY+\6
.ENDM

.SECTION ".bike_text" SUPERFREE

; For each part: its bit, its first tile with its palette and priority.
bk_bit:
	.dw 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024
; The time of the vertical blank for 0-5 loads of a single sprite:
bk_lcap:
	.dw 0, 128+2*ENTRY_COST, 2*(128+2*ENTRY_COST), 3*(128+2*ENTRY_COST)
	.dw 4*(128+2*ENTRY_COST), 5*(128+2*ENTRY_COST)
bk_ta0:
	.dw 128|(BK_PAL_THIGH*2|PRIO)<<8, 130|(BK_PAL_LEG*2|PRIO)<<8
	.dw 132|(BK_PAL_UPARM*2|PRIO)<<8, 134|(BK_PAL_FOREARM*2|PRIO)<<8
	.dw 136|(BK_PAL_S1A*2|PRIO)<<8, 138|(BK_PAL_S1B*2|PRIO)<<8
	.dw 140|(BK_PAL_S2A*2|PRIO)<<8, 142|(BK_PAL_S2B*2|PRIO)<<8
	.dw 160|(BK_PAL_HEAD*2|PRIO)<<8, 162|(BK_PAL_TORSO*2|PRIO)<<8
	.dw 164|(BK_PAL_FRAME*2|PRIO)<<8

;---------------------------------------------------------------------------
; void bike_reset(void): no part in the VRAM, the sprites hidden.
bike_reset:
	php
	phb
	rep #$30
	sep #$20
	lda #$80
	pha
	plb
	rep #$20
	ldx #0
-	lda #$FFFF                  ; no picture yet: empty tiles
	sta bike_cur,x
	lda.l bk_ta0,x
	sta bike_ta,x
	inx
	inx
	cpx #22
	bcc -
	lda #0
	sta bike_cur+2*FRAME        ; the body: no sprites
	sta bike_toggle
	sta bike_pend
	sta bike_bn
	sta bike_bnl
	dec a
	sta bike_key
	sta bike_key+2
	sta bike_key+4
	sta bike_key+6
	sta bike_key+8
	sta bike_fkey
	sta bike_tkey
	sta bike_ph
	ldx.w #OAM_BIKE*4           ; the sprites hidden
	lda #$E000                  ; x 0, y 224
-	sta core_oam,x
	inx
	inx
	inx
	inx
	cpx.w #OAM_OBJ*4
	bcc -
	plb
	plp
	rtl

;---------------------------------------------------------------------------
; void bike_draw(s16 cam_x, s16 cam_y)
bike_draw:
	php
	phb
	phd
	rep #$30
	lda 8,s
	tax
	lda 10,s
	tay
	pea bike_dp
	pld
	stx.b Z_CAMX
	sty.b Z_CAMY
	sep #$20
	lda #$80
	pha
	plb
	lda.b #:bike_desc_single    ; the bank of the descriptors (Z_PTR)
	sta.b Z_PTR+2
	rep #$30
	jsr bk_geometry
	lda.b Z_LATE                ; turning
	bmi +
	jsr bk_turn
+	jsr bk_pictures
	jsr bk_load
	jsr bk_oam
bike_draw_end:
	pld
	plb
	plp
	rtl

;---------------------------------------------------------------------------
; A = (d >> 8) * 4915 >> 12 (16 bits), d = Z_T1:Z_T0 (0 if negative): the
; 1/16 level pixels of a distance from the origin. With Eh = d >> 16 and
; El = d >> 8 & 255: 16 * Eh * 19 + (Eh * 51 + El * 19 + El * 51 >> 8) >> 4.
bk_lpx16:
	rep #$20
	lda.b Z_T1
	bpl +
	lda #0
	rts
+	MA
	lda #19
	sta.w $211C
	rep #$20
	lda.w $2134
	asl a
	asl a
	asl a
	asl a
	sta.b Z_T2                  ; 16 * Eh * 19
	sep #$20
	lda #51
	sta.w $211C
	rep #$20
	lda.b Z_T0
	xba
	and #$00FF
	asl a
	tax
	lda.w $2134                 ; Eh * 51
	clc
	adc.l bike_t_lpx,x          ; El * 19 + (El * 51 >> 8)
	lsr a
	lsr a
	lsr a
	lsr a
	clc
	adc.b Z_T2
	rts

;---------------------------------------------------------------------------
; Z_IDX = the squared length of (Z_VX, Z_VY) in 1/4 pixels (each clamped
; to -127..127) >> 3, at most 1023. Keeps Y.
bk_d4:
	lda.b Z_VX
	jsr _q
	sta.b Z_T5
	lda.b Z_VY
	jsr _q
	clc
	adc.b Z_T5
	lsr a
	lsr a
	lsr a
	cmp #1024
	bcc +
	lda #1023
+	sta.b Z_IDX
	rts
_q:
	ASR
	ASR
	bpl +
	eor #$FFFF
	inc a
+	cmp #128
	bcc +
	lda #127
+	asl a
	tax
	lda.l bike_t_sq,x
	rts

;---------------------------------------------------------------------------
; A = the angle of (Z_VX, Z_VY) in 256 steps (counterclockwise): the table
; by |y| >> 3 and |x| >> 3, both halved until they are below 512. Keeps Y.
bk_atan2:
	lda.b Z_VY
bk_atan2a:                      ; (A = Z_VY, 16 bits)
	bpl +
	eor #$FFFF
	inc a
+	sta.b Z_AY
	lda.b Z_VX
	bpl +
	eor #$FFFF
	inc a
+	sta.b Z_AX
	ora.b Z_AY
	cmp #512
	bcc ++
-	lsr.b Z_AX
	lsr.b Z_AY
	lsr a
	cmp #512
	bcs -
++	lda.b Z_AY
	asl a
	asl a
	asl a
	and #$0FC0
	sta.b Z_AY
	lda.b Z_AX
	lsr a
	lsr a
	lsr a
	ora.b Z_AY
	tax
	lda.l bike_t_atan8,x
	and #$00FF
	ldx.b Z_VX
	bmi _xn
	ldx.b Z_VY
	bpl _done
	eor #$FFFF
	inc a
	bra _done
_xn:
	ldx.b Z_VY
	bmi +
	eor #$FFFF
	inc a
+	clc
	adc #128
_done:
	and #$00FF
	rts

;---------------------------------------------------------------------------

;---------------------------------------------------------------------------
; Where the parts are (P_CX, P_CY), their angles and mirroring (P_AL, P_H).
bk_geometry:
	; The center of the bike on the screen:
	rep #$30
	lda.b Z_CAMX
	asl a
	asl a
	asl a
	asl a
	sta.b Z_T3
	lda.l phys_view+PV_BODY_X
	sec
	sbc.l bike_org_x
	sta.b Z_T0
	lda.l phys_view+PV_BODY_X+2
	sbc.l bike_org_x+2
	sta.b Z_T1
	jsr bk_lpx16
	sec
	sbc.b Z_T3
	sta.b Z_BSX
	lda.b Z_CAMY
	asl a
	asl a
	asl a
	asl a
	sta.b Z_T3
	lda.l bike_org_y
	sec
	sbc.l phys_view+PV_BODY_Y
	sta.b Z_T0
	lda.l bike_org_y+2
	sbc.l phys_view+PV_BODY_Y+2
	sta.b Z_T1
	jsr bk_lpx16
	sec
	sbc.b Z_T3
	sta.b Z_BSY
	; The angle:
	lda.l phys_view+PV_BODY_A
	sta.b Z_TH
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	sta.b Z_TI
	tax
	sep #$20
	lda.l bike_t_sin,x
	sta.b Z_S
	lda.l bike_t_sin+256,x
	sta.b Z_C
	rep #$20
	lda.l phys_view+PV_TURNED
	and #$00FF
	beq +
	lda #1
+	sta.b Z_TR
	lda.l bike_anim+BA_TURN     ; turning?
	cmp.w #TURN_DONE
	bcs +
	jsr bk_turn0
	rep #$30
	bra ++
+	lda #4
	sta.b Z_LV
	lda #$FFFF
	sta.b Z_LATE
++
	; Points from the physics:
	lda.l phys_view+PV_BODY_X+1
	sta.b Z_T4
	lda.l phys_view+PV_BODY_Y+1
	sta.b Z_T5
	CONV PV_WHEEL_X, Z_T4, Z_W0X
	CONV PV_WHEEL_Y, Z_T5, Z_W0Y
	CONV PV_WHEEL_X+4, Z_T4, Z_W1X
	CONV PV_WHEEL_Y+4, Z_T5, Z_W1Y
	CONV PV_RIDER_X, Z_T4, Z_RX
	CONV PV_RIDER_Y, Z_T5, Z_RY
	; Points fixed to the bike and to the rider: tables by the angle >> 6
	; and turned.
	rep #$30
	lda.b Z_TI                  ; 4 * (the angle >> 6)
	asl a
	asl a
	ldx.b Z_TR
	beq +
	ora #$1000
+	tax
	stx.b Z_ROT
	lda.l bike_rot_handle,x
	sta.b Z_HAX
	lda.l bike_rot_handle+2,x
	sta.b Z_HAY
	lda.l bike_rot_rear,x
	sta.b Z_REX
	lda.l bike_rot_rear+2,x
	sta.b Z_REY
	lda.l bike_rot_torso_c,x
	clc
	adc.b Z_RX
	sta P_CX+2*9
	lda.l bike_rot_torso_c+2,x
	clc
	adc.b Z_RY
	sta P_CY+2*9
	lda.l bike_rot_head,x       ; szamitfejr
	clc
	adc.b Z_RX
	sta P_CX+2*8
	lda.l bike_rot_head+2,x
	clc
	adc.b Z_RY
	sta P_CY+2*8
	jsr bk_limbs
	lda.l bike_anim+BA_VOLT     ; volting: the arm swung
	and #$FF00
	beq +
	ldx.b Z_ROT                 ; the shoulder
	lda.l bike_rot_shoulder,x
	clc
	adc.b Z_RX
	sta.b Z_SHX
	lda.l bike_rot_shoulder+2,x
	clc
	adc.b Z_RY
	sta.b Z_SHY
	jsr bk_hand
	jsr bk_arm
+	jsr bk_susp
	; Torso, head, body: at the angle of the bike.
	rep #$30
	lda.b Z_TR
	beq +
	lda.b Z_TH
	clc
	adc.w #($8000-BK_TORSO_BETA) & $FFFF
	sta P_AL+2*9
	lda.b Z_THM
	bra ++
+	lda.b Z_TH
	clc
	adc.w #BK_TORSO_BETA
	sta P_AL+2*9
	lda.b Z_TH
++	sta P_AL+2*8
	sta P_AL+2*FRAME
	; The mirroring of the parts (P_H) when turned changed or after a
	; mirrored turn.
	lda.b Z_TR
	cmp bike_ph
	beq +
	sta bike_ph
	stz P_H+2*4
	stz P_H+2*6
	tax
	beq ++
	lda.w #64
	sta P_H+2*0
	sta P_H+2*1
	stz P_H+2*2
	sta P_H+2*3
	sta P_H+2*8
	sta P_H+2*9
	asl a
	sta P_H+2*FRAME
	rts
++	stz P_H+2*0
	stz P_H+2*1
	lda.w #64
	sta P_H+2*2
	stz P_H+2*3
	stz P_H+2*8
	stz P_H+2*9
	stz P_H+2*FRAME
+	rts

;---------------------------------------------------------------------------
; The legs and the arms from the tables by the rider's place in the frame
; of the bike (gen_bike.py): their centers rotated with the bike, their
; angles added to its angle; mirrored when turned.
.MACRO LIMB
.IF \3 == 0
.IF \4 == 0
	lda.l bike_limb_\1_phi,x   ; 2 r (cos, sin) of its angle + the bike's
	clc
	adc.b Z_TI
.ELSE
	lda.b Z_TI2                 ; mirrored: 512 - its angle (+ 1024:
	sec                         ; bike_t_sin is long enough)
	sbc.l bike_limb_\1_phi,x
.ENDIF
	tay
	lda.l bike_limb_\1_r2,x
	MA
	tyx
	lda.l bike_t_sin+256,x
	MB
	sta P_CX+\2
	sep #$20
	lda.l bike_t_sin,x
	MB
	sta P_CY+\2
	ldx.b Z_IDXT
.ELSE
.IF \4 == 0
	lda.l bike_limb_\1_x2,x
.ELSE
	lda #0                      ; mirrored
	sec
	sbc.l bike_limb_\1_x2,x
.ENDIF
	sta.b Z_T3                  ; turning: x squashed along the bike,
	asl a                       ; x += x (f - 1)
	asl a
	MA
	lda.b Z_G
	MB
	clc
	adc.b Z_T3
	MA
	lda.b Z_C
	MB
	sta.b Z_T0                  ; x c
	sep #$20
	lda.b Z_S
	MB
	sta.b Z_T1                  ; x s
	lda.l bike_limb_\1_y2,x
	MA
	lda.b Z_S
	MB
	sta.b Z_T2                  ; y s
	sep #$20
	lda.b Z_C
	MB
	clc
	adc.b Z_T1
	sta P_CY+\2
	lda.b Z_T0
	sec
	sbc.b Z_T2
	sta P_CX+\2
.ENDIF
.IF \4 == 0
	lda.l bike_limb_\1_a16,x
	clc
	adc.b Z_TH
.ELSE
	lda.b Z_THM                 ; mirrored: 1/2 - its angle
	sec
	sbc.l bike_limb_\1_a16,x
.ENDIF
	sta P_AL+\2
.ENDM

; The four limbs (\1: turning, \2: turned), the arms not while volting.
.MACRO LIMBS
	LIMB thigh, 2*0, \1, \2
	LIMB leg, 2*1, \1, \2
	lda.l bike_anim+BA_VOLT     ; volting: the arms elsewhere (bk_arm)
	and #$FF00
	beq +
	jmp _lmir
+	LIMB uparm, 2*2, \1, \2
	LIMB forearm, 2*3, \1, \2
.ENDM

bk_limbs:
	rep #$30
	; The rider in the frame of the bike: x = rx c + ry s, y = ry c - rx s.
	lda.b Z_RX
	asl a
	MA
	lda.b Z_C
	MB
	sta.b Z_T0
	sep #$20
	lda.b Z_S
	MB
	sta.b Z_T1
	lda.b Z_RY
	asl a
	MA
	lda.b Z_S
	MB
	clc
	adc.b Z_T0
	sta.b Z_T0
	sep #$20
	lda.b Z_C
	MB
	sec
	sbc.b Z_T1
	sec
	sbc.w #BK_LIMB_Y0
	bpl +
	lda #0
+	lsr a
	lsr a
	cmp.w #BK_LIMB_NY
	bcc +
	lda.w #BK_LIMB_NY-1
+	xba
	lsr a
	lsr a                       ; row * 64
	sta.b Z_T2
	lda.b Z_T0
	ldx.b Z_TR
	beq +
	eor #$FFFF
	inc a
+	sec
	sbc.w #BK_LIMB_X0
	bpl +
	lda #0
+	lsr a
	lsr a
	cmp #64
	bcc +
	lda #63
+	ora.b Z_T2
	asl a
	tax
	stx.b Z_IDXT
	lda.b Z_TI
	clc
	adc.w #512+1024
	sta.b Z_TI2
	lda.b Z_TH
	eor #$8000
	sta.b Z_THM
	lda.b Z_LATE
	bpl +
	jmp _lnorm
+	lda.b Z_TR
	beq +
	jmp _lturn1
+	LIMBS 1, 0
	jmp _lmir
_lturn1:
	LIMBS 1, 1
	jmp _lmir
_lnorm:
	lda.b Z_TR
	beq +
	jmp _lnorm1
+	LIMBS 0, 0
	jmp _lmir
_lnorm1:
	LIMBS 0, 1
_lmir:
	rts

;---------------------------------------------------------------------------
; The hand (Z_KX, Z_KY): the handlebar, swung around the shoulder while
; volting.
bk_hand:
	rep #$30
	lda.b Z_HAX
	sta.b Z_KX
	lda.b Z_HAY
	sta.b Z_KY
	lda.l bike_anim+BA_VOLT
	xba
	and #$00FF
	bne +
	rts
+	sta.b Z_T0                  ; table index
	; Up when volt1 == turned:
	lda.l bike_anim+BA_VOLT1
	and #$00FF
	beq +
	lda #1
+	eor.b Z_TR
	bne +
	lda #512
	clc
	adc.b Z_T0
	sta.b Z_T0
+	ldx.b Z_T0
	sep #$20
	lda.l bike_t_volt_c0,x
	sta.b Z_B                   ; h cos
	lda.l bike_t_volt_c0+256,x
	sta.b Z_A                   ; h sin
	rep #$20
	lda.b Z_HAX
	sec
	sbc.b Z_SHX
	asl a
	asl a
	MA                          ; 4 kx
	lda.b Z_B
	MB
	sta.b Z_T1                  ; kx hc
	sep #$20
	lda.b Z_A
	MB
	sta.b Z_T2                  ; kx hs
	lda.b Z_HAY
	sec
	sbc.b Z_SHY
	asl a
	asl a
	MA                          ; 4 ky
	lda.b Z_B
	MB
	sta.b Z_T3                  ; ky hc
	sep #$20
	lda.b Z_A
	MB
	sta.b Z_T4                  ; ky hs
	lda.b Z_TR
	bne _tr
	lda.b Z_T1
	clc
	adc.b Z_T4
	clc
	adc.b Z_SHX
	sta.b Z_KX
	lda.b Z_T3
	sec
	sbc.b Z_T2
	clc
	adc.b Z_SHY
	sta.b Z_KY
	rts
_tr:
	lda.b Z_T1
	sec
	sbc.b Z_T4
	clc
	adc.b Z_SHX
	sta.b Z_KX
	lda.b Z_T2
	clc
	adc.b Z_T3
	clc
	adc.b Z_SHY
	sta.b Z_KY
	rts

;---------------------------------------------------------------------------
; Operands of the side term of ketkormetszete: Z_T2 = 4 * (-vy * sg),
; Z_T3 = 4 * (vx * sg), sg = -1 when turned. Keeps Y.
bk_side:
	rep #$30
	lda.b Z_VY
	asl a
	asl a
	ldx.b Z_TR
	bne +
	eor #$FFFF
	inc a
+	sta.b Z_T2
	lda.b Z_VX
	asl a
	asl a
	ldx.b Z_TR
	beq +
	eor #$FFFF
	inc a
+	sta.b Z_T3
	rts

; Z_T4 = A, negated when turned.
bk_sg:
	ldx.b Z_TR
	beq +
	eor #$FFFF
	inc a
+	sta.b Z_T4
	rts

; The elbow: shoulder + a * (hand - shoulder) + b * (the side); the upper
; arm at 128 + atan(b / a), the forearm at 128 - atan(b / (1 - a)) from the
; angle of shoulder -> hand.
bk_arm:
	rep #$30
	lda.b Z_KX
	sec
	sbc.b Z_SHX
	sta.b Z_VX
	lda.b Z_KY
	sec
	sbc.b Z_SHY
	sta.b Z_VY
	jsr bk_d4
	ldx.b Z_IDX
	sep #$20
	lda.l bike_t_elbow_a,x
	sta.b Z_A
	lda.l bike_t_elbow_b,x
	sta.b Z_B
	jsr bk_side
	MUL2 Z_VX, Z_A
	clc
	adc.b Z_SHX
	sta.b Z_ELX
	lda.b Z_T2
	MA
	lda.b Z_B
	MB
	clc
	adc.b Z_ELX
	sta.b Z_ELX
	MUL2 Z_VY, Z_A
	clc
	adc.b Z_SHY
	sta.b Z_ELY
	lda.b Z_T3
	MA
	lda.b Z_B
	MB
	clc
	adc.b Z_ELY
	sta.b Z_ELY
	jsr bk_atan2
	clc
	adc #128
	sta.b Z_A8
	ldx.b Z_IDX
	lda.l bike_t_elbow_gu,x
	and #$00FF
	jsr bk_sg
	lda.b Z_A8
	clc
	adc.b Z_T4
	and #$00FF
	xba
	sta P_AL+2*2                ; upper arm
	ldx.b Z_IDX
	lda.l bike_t_elbow_gf,x
	and #$00FF
	jsr bk_sg
	lda.b Z_A8
	sec
	sbc.b Z_T4
	and #$00FF
	xba
	sta P_AL+2*3                ; forearm
	CENTER Z_ELX, Z_ELY, Z_SHX, Z_SHY, BK_C_UPARM, 2*2
	CENTER Z_KX, Z_KY, Z_ELX, Z_ELY, BK_C_FOREARM, 2*3
	rts

;---------------------------------------------------------------------------
; The suspensions, two pieces each: front from the front wheel to the
; handlebar, rear from the rear point to the rear wheel. The pieces' centers
; are at fixed distances from the ends along the rod (bike_t_s1_ka ...: by
; its angle).
.MACRO ROD
	lda.b \3
	sec
	sbc.b \1
	sta.b Z_VX
	lda.b \4
	sec
	sbc.b \2
	sta.b Z_VY
	jsr bk_atan2a
	xba
	sta P_AL+\5                ; (the second piece takes its picture)
	xba
	asl a
	asl a
	tax
	lda.l bike_t_\6_ka,x
	clc
	adc.b \1
	sta P_CX+\5
	lda.l bike_t_\6_ka+2,x
	clc
	adc.b \2
	sta P_CY+\5
	lda.l bike_t_\6_kb,x
	clc
	adc.b \3
	sta P_CX+\5+2
	lda.l bike_t_\6_kb+2,x
	clc
	adc.b \4
	sta P_CY+\5+2
.ENDM

bk_susp:
	rep #$30
	lda.b Z_TR
	beq +
	jmp _strn
+	ROD Z_W0X, Z_W0Y, Z_HAX, Z_HAY, 2*4, s1
	ROD Z_REX, Z_REY, Z_W1X, Z_W1Y, 2*6, s2
	rts
_strn:
	ROD Z_W1X, Z_W1Y, Z_HAX, Z_HAY, 2*4, s1
	ROD Z_REX, Z_REY, Z_W0X, Z_W0Y, 2*6, s2
	rts

;---------------------------------------------------------------------------
; The turn: everything but the wheels squashed along the bike around its
; center (setaffinitas), the squashed pictures, the wheel drawn over it.
; Its factors (before the limbs, squashed in the frame of the bike).
bk_turn0:
	rep #$30
	lda #4
	sta.b Z_LV
	lda #$FFFF
	sta.b Z_LATE
	lda.l bike_anim+BA_TURN
	cmp.w #TURN_DONE
	bcc +
	rts
+	xba
	and #$00FF
	tax
	sep #$20
	lda.l bike_t_turn_f,x
	sta.b Z_A
	lda.l bike_t_turn_g,x
	sta.b Z_G
	lda.l bike_t_turn_lv,x
	rep #$20
	and #$00FF
	sta.b Z_LV
	stz.b Z_NEG
	lda.b Z_A
	and #$0080
	beq +
	inc.b Z_NEG
+	lda.b Z_TR
	eor.b Z_NEG
	sta.b Z_TEFF
	; The front wheel (0) on top: f > 0 not turned, or f <= 0 turned.
	lda.b Z_A
	and #$00FF
	beq _fle0
	bit #$0080
	bne _fle0
	lda.b Z_TR                  ; f > 0
	beq _front
	bra _rear
_fle0:
	lda.b Z_TR
	bne _front
_rear:
	lda #1
	bra +
_front:
	lda #0
+	sta.b Z_LATE
	rts

; The squash of the other parts: (f - 1) * (c c, c s, s s) >> 6.
bk_turn:
	rep #$30
	lda.b Z_TI                  ; c c, c s, s s (bike_t_cc ...)
	asl a
	tax
	lda.l bike_t_cc,x
	M6
	sta.b Z_MA
	rep #$20
	lda.l bike_t_cs,x
	M6
	sta.b Z_MB
	rep #$20
	lda.l bike_t_ss,x
	M6
	sta.b Z_MD
	rep #$20
	; Squash the centers of the parts 4-9 and the arms while volting
	; (around the center of the bike): x += x a + y b, y += x b + y d.
	lda.l bike_anim+BA_VOLT
	and #$FF00
	bne +
	jmp _sq4
+	SQ 2*2
	SQ 2*3
_sq4:
	SQ 2*4
	SQ 2*5
	SQ 2*6
	SQ 2*7
	SQ 2*8
	SQ 2*9
	; Not squashed pictures, mirrored if f < 0: alpha = 2 th + 1/2 - alpha.
	lda.b Z_LV
	cmp #4
	bne +
	lda.b Z_NEG
	bne ++
+	rts
++	lda.b Z_TH
	asl a
	clc
	adc #$8000
	sta.b Z_T0
	MIR 2*0
	MIR 2*1
	MIR 2*2
	MIR 2*3
	MIR 2*4
	MIR 2*6
	MIR 2*8
	MIR 2*9
	MIR 2*FRAME
	; The mirroring flipped (P_H was set for Z_TR), to be set again in the
	; next frame.
	lda #$FFFF
	sta bike_ph
	lda.w #64
	sta P_H+2*4
	sta P_H+2*6
	ldx.b Z_TR
	bne +
	sta P_H+2*0
	sta P_H+2*1
	stz P_H+2*2
	sta P_H+2*3
	sta P_H+2*8
	sta P_H+2*9
	asl a
	sta P_H+2*FRAME
	rts
+	stz P_H+2*0
	stz P_H+2*1
	sta P_H+2*2
	stz P_H+2*3
	stz P_H+2*8
	stz P_H+2*9
	stz P_H+2*FRAME
	rts

;---------------------------------------------------------------------------
; The pictures wanted (W_DESC, W_KF): the step of the angle (P_AL) and the
; mirroring (P_H) give the stored picture and its flips from the tables
; bike_t_lk32/64/128 (k | flips << 8, gen_bike.py). Only for the parts
; whose step or mirroring changed (bike_key ...): a part whose picture is not
; in the VRAM is pending (bike_pend), else its flips are taken.
bk_pictures:
	rep #$30
	lda.b Z_LV
	cmp #4
	beq +
	jmp bk_tpictures
+	lda bike_tkey               ; not turning
	bmi +
	lda #$FFFF
	sta bike_tkey
+	sep #$20
	PIC64 2*0, 0
	PIC64 2*1, 0
	PIC64 2*2, 0
	PIC64 2*3, 0
	PIC64 2*4, 1                ; the pieces of a suspension: the same angle
	PIC64 2*6, 1
	PIC64 2*8, 0
	PIC64 2*9, 0
	rep #$20
	lda P_AL+2*FRAME            ; the body: 128 steps
	clc
	adc.w #256
	xba
	and.w #$00FF
	lsr a
	ora P_H+2*FRAME
	cmp bike_fkey
	bne +
	rts
+	sta bike_fkey
	asl a
	tax
	lda.l bike_t_lk128,x
	sta W_KF+2*FRAME
	and #$00FF
	xba
	lsr a                       ; * BK_FRAME_DESC
	clc
	adc.w #bike_desc_frame
	sta W_DESC+2*FRAME
	ldy.w #2*FRAME
	bra bk_check

; Part Y/2 wants W_DESC (W_KF): pending if it is not in the VRAM, else its
; flips are taken.
bk_check:
	tyx
	lda W_DESC,y
	cmp bike_cur,y
	beq +
	lda.l bk_bit,x
	tsb bike_pend
	rts
+	lda.l bk_bit,x
	trb bike_pend
	lda W_KF,y
	and.w #$FF00
	ora.l bk_ta0,x
	cmp bike_ta,y
	beq +
	sta bike_ta,y
	cpy.w #2*FRAME
	bne +
	jmp bk_bodyset
+	rts

; The squashed pictures: all at the angle of the bike as drawn. The parts
; 0-9 share their key (bike_tkey: (level + 1) << 8 | step).
bk_tpictures:
	lda.b Z_TH
	ldx.b Z_TEFF
	beq +
	eor #$8000
+	sta.b Z_T5                  ; alpha
	clc
	adc.w #1024
	xba
	and.w #$00FF
	lsr a
	lsr a
	lsr a
	ldx.b Z_TEFF
	beq +
	ora #32
+	sta.b Z_T3
	lda.b Z_LV
	inc a
	xba
	ora.b Z_T3
	cmp bike_tkey
	beq _tframe
	sta bike_tkey
	lda #$FFFF                  ; the keys of the single parts are new
	sta bike_key                ; after the turn
	sta bike_key+2
	sta bike_key+4
	sta bike_key+6
	sta bike_key+8
	lda.b Z_T3
	asl a
	tax
	lda.l bike_t_lk32,x
	sta.b Z_T4                  ; k | flips << 8
	and #$00FF
	clc
	adc.w #BK_N_PART_HALF
	sta.b Z_T3
	lda.b Z_LV
	asl a
	asl a
	asl a
	asl a
	clc
	adc.b Z_T3
	asl a
	asl a
	clc
	adc.w #bike_desc_single     ; + 4 * (32 + lv * 16 + k)
	sta.b Z_T3
	ldy #0
-	lda.b Z_T3
	sta W_DESC,y
	clc
	adc.w #4*BK_PER_PART
	sta.b Z_T3
	lda.b Z_T4
	sta W_KF,y
	jsr bk_check
	iny
	iny
	cpy.w #2*FRAME
	bcc -
_tframe:
	lda.b Z_T5                  ; the body, 64 steps
	clc
	adc.w #512
	xba
	and.w #$00FF
	lsr a
	lsr a
	ldx.b Z_TEFF
	beq +
	ora #64
+	sta.b Z_T3
	lda.b Z_LV
	inc a
	xba
	ora.b Z_T3
	cmp bike_fkey
	bne +
	rts
+	sta bike_fkey
	lda.b Z_T3
	asl a
	tax
	lda.l bike_t_lk64,x
	sta W_KF+2*FRAME
	and #$00FF
	sta.b Z_T3
	lda.b Z_LV
	xba
	lsr a
	lsr a
	lsr a                       ; lv * 32
	clc
	adc.b Z_T3
	clc
	adc.w #2*BK_N_TURN_FRAME_HALF
	xba
	lsr a                       ; * BK_FRAME_DESC
	clc
	adc.w #bike_desc_frame
	sta W_DESC+2*FRAME
	ldy.w #2*FRAME
	jmp bk_check

;---------------------------------------------------------------------------
; Loading the pictures that changed: straight from the ROM through the
; queue of the NMI, two transfers a load (the top and the bottom halves of
; its sprites): a single part, the body (gen_bike.py keeps its sprites in
; rows), or while turning the parts 0-7 together (bike_turn_rows). The
; loads of a frame take at most LOAD_COST of the vertical blank (and leave
; OBJ_ROOM entries of the queue for the objects). The parts 0-7 and the
; head, the torso and the body take turns to go first; a group stops at
; its first load that does not fit.
bk_load:
	rep #$30
	lda bike_pend
	sta.b Z_PEND
	bne +
	rts
+	lda bike_toggle
	eor #1
	sta bike_toggle
	; Each load takes at least 128 + 2 * ENTRY_COST: no more of them than
	; the queue has room for.
	lda.w #(DMAQ_MAX-OBJ_ROOM)*8
	sec
	sbc core_dmaq_n
	bcs +
	rts
+	cmp.w #2*8*(LOAD_COST/(128+2*ENTRY_COST))
	lda.w #LOAD_COST
	bcs +
	lda.w #(DMAQ_MAX-OBJ_ROOM)*8
	sec
	sbc core_dmaq_n
	lsr a
	lsr a
	lsr a
	and #$FFFE                  ; 2 * loads
	tax
	lda.l bk_lcap,x
+	sta.b Z_LEFT
	sep #$20                    ; DMA channel 7: the templates of the
	stz $4370                   ; queue into the WRAM (bk_load1)
	lda #$80
	sta $4371
	lda.b #:bike_q_single
	sta $4374
	stz $2183
	rep #$20
	lda bike_toggle             ; (toggled: 1 = the parts 0-7 first)
	beq +
	jsr _group0
	jmp _group1
+	jsr _group1

; The parts 0-7: one at a time, or all of them while turning.
_group0:
	lda.b Z_PEND
	and #$00FF
	beq _r0
	sta.b Z_T5                  ; the parts left
	lda.b Z_LV
	cmp #4
	beq _single0
	lda.b Z_LEFT
	sec
	sbc.w #8*128+2*ENTRY_COST
	bcc _r0
	sta.b Z_LEFT
	ldy #0
-	tyx
	jsr bk_take
	iny
	iny
	cpy.w #2*8
	bcc -
	lda W_DESC                  ; 4 * (lv * 16 + angle)
	sec
	sbc.w #bike_desc_single+4*BK_N_PART_HALF
	tax
	lda.l bike_turn_rows,x
	sta.b Z_T0
	lda.l bike_turn_rows+2,x
	and #$00FF
	sta.b Z_T1
	lda.w #8*64
	sta.b Z_T2
	lda.w #VRAM_PARTS
	sta.b Z_DST
	jmp bk_qrows
_single0:
-	lda.b Z_T5                  ; the lowest part left
	beq ++
	asl a
	tax
	lda.l bike_t_low2,x
	tay
	tax
	lda.l bk_bit,x
	trb.b Z_T5
	lda.b Z_LEFT
	sec
	sbc.w #128+2*ENTRY_COST
	bcc +
	sta.b Z_LEFT
	jsr bk_load1
	bra -
+	lda.l bk_bit,x              ; not loaded: it and the ones left
	tsb.b Z_T5
++	lda.b Z_PEND
	and #$00FF
	eor.b Z_T5
	trb bike_pend
_r0:
	rts

; The head, the torso, the body.
_group1:
	lda.b Z_PEND
	and #$0100
	beq +
	lda.b Z_LEFT
	sec
	sbc.w #128+2*ENTRY_COST
	bcc _r0
	sta.b Z_LEFT
	ldy.w #2*8
	jsr bk_load1
	lda.w #$0100
	trb bike_pend
+	lda.b Z_PEND
	and #$0200
	beq +
	lda.b Z_LEFT
	sec
	sbc.w #128+2*ENTRY_COST
	bcc _r0
	sta.b Z_LEFT
	ldy.w #2*9
	jsr bk_load1
	lda.w #$0200
	trb bike_pend
+	lda.b Z_PEND
	and #$0400
	beq _r0
	jsr bk_nframe
	dec a                       ; its sprites
	xba
	lsr a
	sta.b Z_T2                  ; * 128
	adc.w #2*ENTRY_COST         ; (C clear)
	sta.b Z_T3
	lda.b Z_LEFT
	sec
	sbc.b Z_T3
	bcc _r0
	sta.b Z_LEFT
	lsr.b Z_T2                  ; the bytes of a row
	ldx.w #2*FRAME
	txy
	jsr bk_take
	jsr bk_bodyset
	ldy.w #BK_FRAME_ROWS
	lda [Z_PTR],y
	sta.b Z_T0
	iny
	iny
	lda [Z_PTR],y
	and #$00FF
	sta.b Z_T1
	lda.w #VRAM_OBJ+164*16
	sta.b Z_DST
	jmp bk_qrows

; Part Y/2 (a single sprite) gets its wanted picture and loads it: its two
; transfers of the queue copied from bike_q_single by DMA (channel 7, set
; up by bk_load). Keeps Y; its bit of bike_pend stays (the caller clears
; it).
bk_load1:
	tyx
	lda W_KF,y
	and #$FF00
	ora.l bk_ta0,x
	sta bike_ta,y
	lda W_DESC,y
	sta bike_cur,y
	asl a                       ; bike_q_single + 4 * (desc - bike_desc_single)
	asl a
	clc
	adc.w #(bike_q_single-4*bike_desc_single) & $FFFF
	sta $4372
	lda core_dmaq_n
	clc
	adc.w #core_dmaq
	sta $2181
	lda #16
	sta $4375
	sep #$20
	lda #$80
	sta $420B
	rep #$20
	lda core_dmaq_n
	clc
	adc #16
	sta core_dmaq_n
	lda core_dmaq_bytes
	adc #128
	sta core_dmaq_bytes
	rts

; Two transfers of the queue: Z_T2 bytes from Z_T1:Z_T0 to the VRAM at
; Z_DST (words), the next Z_T2 bytes 16 tiles further.
bk_qrows:
	ldx core_dmaq_n
	lda.b Z_T0
	sta core_dmaq+1,x
	clc
	adc.b Z_T2
	sta core_dmaq+8+1,x
	lda.b Z_T2
	sta core_dmaq+4,x
	sta core_dmaq+8+4,x
	asl a
	clc
	adc core_dmaq_bytes
	sta core_dmaq_bytes
	lda.b Z_DST
	sta core_dmaq+6,x
	clc
	adc #256
	sta core_dmaq+8+6,x
	sep #$20
	lda.b Z_T1
	sta core_dmaq+3,x
	sta core_dmaq+8+3,x
	stz core_dmaq,x             ; (DMAQ_VRAM)
	stz core_dmaq+8,x
	rep #$20
	txa
	clc
	adc #16
	sta core_dmaq_n
	rts

; Part Y/2 (X = Y) gets its wanted picture: Z_PTR is its descriptor.
bk_take:
	lda.l bk_bit,x
	trb bike_pend
	lda W_DESC,y
	sta bike_cur,y
	sta.b Z_PTR
	lda W_KF,y
	and #$FF00
	ora.l bk_ta0,x
	sta bike_ta,y
	rts

; A = the last slot of the body's wanted picture (2 + sprites - 1).
bk_nframe:
	lda W_DESC+2*FRAME
	sta.b Z_PTR
	lda [Z_PTR]
	and #$00FF
	inc a
	rts

;---------------------------------------------------------------------------
; The sprites of the bike, each in its own place of the OAM (from 32), the
; first on top (the reverse of the order the PC draws): 0 the wheel drawn
; over the bike while turning, 1-6 the parts 3, 2, 9, 1, 0, 8, 7-12 the
; body, 13-16 the parts 7, 6, 5, 4, 17-18 the wheels. A sprite that is off
; the screen or not used is hidden (y 224). Positions are biased by 256
; pixels: a sprite is on the screen when x is 241..511 and y 241..479 (the
; low byte is what the OAM gets, x < 256 sets the bit of x >= 256).
bk_oam:
	rep #$30
	lda.b Z_BSX
	clc
	adc.w #8+4096-128
	sta.b Z_BXS
	lsr a
	lsr a
	lsr a
	lsr a
	clc
	adc #8
	sta.b Z_PX                  ; the pivot of the body
	lda.b Z_BSY
	clc
	adc.w #8+4096-128
	sta.b Z_BYS
	lsr a
	lsr a
	lsr a
	lsr a
	clc
	adc #8
	sta.b Z_PY
	stz.w BK_HB
	stz.w BK_HB+2
	stz.w BK_HB+4
	; The parts are within 48 pixels of the center: with the center at
	; 56..199, 56..167 they are all on the screen.
	lda.b Z_BSY
	sec
	sbc.w #56*16
	cmp.w #112*16
	bcc +
	jmp bk_oam2
+	lda.b Z_BSX
	sec
	sbc.w #56*16
	cmp.w #144*16
	bcc ++
	lda.b Z_BSX                 ; near the left or the right edge
	sec
	sbc.w #128*16
	bpl +
	jmp bk_oam1
+	jmp bk_oam3
++	SPRITES 0, bk_body0

bk_oam1:
	SPRITES 1, bk_body1

bk_oam2:
	SPRITES 2, bk_body2

bk_oam3:
	SPRITES 3, bk_body3

; The sprites of the body in modes 0-3.
bk_body0:
	jsr bk_body
	cmp bike_bnl                ; (Z_NS) fewer sprites than in the last
	sta bike_bnl                ; frame: the places not used hidden
	bcs +
	asl a
	tax
	jsr bk_hbody
+	ldx.b Z_NS                  ; the sprites from the last one
	txa
	asl a
	tax
	lda.l _bt0,x
	sta.b Z_T5
	ldx.b Z_T4
	jmp (bike_dp+Z_T5)
_bt0:
	.dw _b00, _b01, _b02, _b03, _b04, _b05, _b06
_b06:
	BODY 5, 0
_b05:
	BODY 4, 0
_b04:
	BODY 3, 0
_b03:
	BODY 2, 0
_b02:
	BODY 1, 0
_b01:
	BODY 0, 0
_b00:
	rts

bk_body1:
	jsr bk_body
	cmp bike_bnl                ; (Z_NS) fewer sprites than in the last
	sta bike_bnl                ; frame: the places not used hidden
	bcs +
	asl a
	tax
	jsr bk_hbody
+	ldx.b Z_NS                  ; the sprites from the last one
	txa
	asl a
	tax
	lda.l _bt1,x
	sta.b Z_T5
	ldx.b Z_T4
	jmp (bike_dp+Z_T5)
_bt1:
	.dw _b10, _b11, _b12, _b13, _b14, _b15, _b16
_b16:
	BODY 5, 1
_b15:
	BODY 4, 1
_b14:
	BODY 3, 1
_b13:
	BODY 2, 1
_b12:
	BODY 1, 1
_b11:
	BODY 0, 1
_b10:
	rts

bk_body2:
	jsr bk_body
	cmp bike_bnl                ; (Z_NS) fewer sprites than in the last
	sta bike_bnl                ; frame: the places not used hidden
	bcs +
	asl a
	tax
	jsr bk_hbody
+	ldx.b Z_NS                  ; the sprites from the last one
	txa
	asl a
	tax
	lda.l _bt2,x
	sta.b Z_T5
	ldx.b Z_T4
	jmp (bike_dp+Z_T5)
_bt2:
	.dw _b20, _b21, _b22, _b23, _b24, _b25, _b26
_b26:
	BODY 5, 2
_b25:
	BODY 4, 2
_b24:
	BODY 3, 2
_b23:
	BODY 2, 2
_b22:
	BODY 1, 2
_b21:
	BODY 0, 2
_b20:
	rts

bk_body3:
	jsr bk_body
	cmp bike_bnl                ; (Z_NS) fewer sprites than in the last
	sta bike_bnl                ; frame: the places not used hidden
	bcs +
	asl a
	tax
	jsr bk_hbody
+	ldx.b Z_NS                  ; the sprites from the last one
	txa
	asl a
	tax
	lda.l _bt3,x
	sta.b Z_T5
	ldx.b Z_T4
	jmp (bike_dp+Z_T5)
_bt3:
	.dw _b30, _b31, _b32, _b33, _b34, _b35, _b36
_b36:
	BODY 5, 3
_b35:
	BODY 4, 3
_b34:
	BODY 3, 3
_b33:
	BODY 2, 3
_b32:
	BODY 1, 3
_b31:
	BODY 0, 3
_b30:
	rts

; Turning: the wheel drawn over the bike in place 0, the other one in 17
; (checked as in mode 2).
bk_late:
	lda.b Z_LATE
	bne +
	jmp _late0
+	WHEEL 1, 0, 2
	WHEEL 0, 17, 2
	jmp _late1
_late0:
	WHEEL 0, 0, 2
	WHEEL 1, 17, 2
_late1:
	lda #$E000
	sta.w BK_OAM+4*18
	rts

; Z_T4 = the corners of the sprites of the body for its flips (from
; bike_desc_single), Z_NS = their number (0: none), Z_TA = the first tile
; with the attributes (bike_bodyset).
bk_body:
	lda bike_bx
	sta.b Z_T4
	lda bike_ta+2*FRAME
	sta.b Z_TA
	lda bike_bn
	sta.b Z_NS
	rts

; The body's picture or flips changed: bike_bn, bike_bx for bk_body.
bk_bodyset:
	lda bike_cur+2*FRAME
	sta.b Z_PTR
	beq +
	lda [Z_PTR]
	and #$00FF
+	sta bike_bn
	lda bike_ta+2*FRAME
	xba
	and #$00C0                  ; the flips: 64 f
	lsr a
	lsr a
	lsr a
	sta.b Z_T3                  ; 8 f
	asl a
	adc.b Z_T3                  ; 24 f
	adc.w #(1+3*BK_FRAME_SPRITES-bike_desc_single) & $FFFF
	adc bike_cur+2*FRAME
	sta bike_bx
	rts

; Hides the places of the body from 7 + X/2 on.
bk_hbody:
	lda #$E000
	jmp (_hb,x)
_hb:
	.dw _h0, _h1, _h2, _h3, _h4, _h5, _h6
_h0:
	sta.w BK_OAM+4*7
_h1:
	sta.w BK_OAM+4*8
_h2:
	sta.w BK_OAM+4*9
_h3:
	sta.w BK_OAM+4*10
_h4:
	sta.w BK_OAM+4*11
_h5:
	sta.w BK_OAM+4*12
_h6:
	rts

.ENDS
