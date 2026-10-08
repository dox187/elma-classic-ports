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
; body of the bike on up to 6 sprites). A picture that changed is copied
; into a copy of these rows in the RAM (DMA from the ROM), and the changed
; range of each row goes to the VRAM through the queue of the NMI: at most
; 4 transfers and BUDGET bytes a frame, the rest waits for the next frame.
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
.DEFINE BUDGET      1600        ; bytes of tiles a frame
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
Z_W0X       dw          ; points: wheels (in this order), rider, head,
Z_W0Y       dw          ; handlebar, rear suspension, foot, hip, shoulder,
Z_W1X       dw          ; hand, knee, elbow
Z_W1Y       dw
Z_RX        dw
Z_RY        dw
Z_HDX       dw
Z_HDY       dw
Z_HAX       dw
Z_HAY       dw
Z_REX       dw
Z_REY       dw
Z_FOX       dw
Z_FOY       dw
Z_HIX       dw
Z_HIY       dw
Z_SHX       dw
Z_SHY       dw
Z_KX        dw
Z_KY        dw
Z_KNX       dw
Z_KNY       dw
Z_ELX       dw
Z_ELY       dw
Z_IDX       dw          ; index of the tables of a distance
Z_A8        dw          ; an angle in 256 steps
Z_LV        dw          ; level of the squashed pictures, 4: not turning
Z_NEG       dw          ; the turn's squash is negative (mirrored)
Z_TEFF      dw          ; turned as drawn
Z_LATE      dw          ; the wheel drawn over the bike, $FFFF: none
Z_LEFT      dw          ; bytes left of the budget
Z_LO        dw
Z_HI        dw
Z_PAIR      dw
Z_PEND      dw          ; bit p: part p wants another picture
Z_ACC       dw          ; bit p: part p is loaded this frame
Z_PTR       dsb 4       ; a long pointer
Z_SRC       dsb 4       ; source of a DMA
Z_DST       dw
Z_NS        dw
Z_BXB       dw          ; the center of the bike on the screen, biased
Z_BYB       dw          ; (bk_oam)
Z_BXS       dw          ; the same for the corner of a single sprite
Z_BYS       dw
Z_TA        dw          ; tile | attributes << 8
Z_FL        dw          ; flips of a part
Z_PX        dw
Z_PY        dw
Z_FAST      dw          ; $FFFF: the bike far from the edges of the screen
.ENDE

.BASE $00

.RAMSECTION ".bike_dp" BANK 0 SLOT 1 ALIGN 256
bike_dp     dsb 256
.ENDS

.RAMSECTION ".bike_vars" BANK 0 SLOT 1
bike_cur    dsw 11      ; the descriptor of each part in the VRAM, 0: none
bike_curf   dsw 11      ; flips of its sprites << 8
bike_ta     dsw 11      ; its first tile | attributes << 8
bike_toggle dw          ; which pair of rows goes first
bike_rlo    dsw 2       ; ranges of slots loaded this frame ($FFFF: none)
bike_rhi    dsw 2
bike_oam_end dw         ; end of the sprites written in the last frame
bike_stale  dw          ; bit p: part p is not in the copy of the rows
P_CX        dsw 11      ; the parts: center
P_CY        dsw 11
P_AL        dsw 11      ; angle
P_H         dsw 11      ; mirrored: 64 (128 for the body) or 0
W_DESC      dsw 11      ; the picture wanted (descriptor)
W_KF        dsw 11      ; its flips << 8
.ENDS

.RAMSECTION ".bike_stage" BANK $7E SLOT 2
bike_stage  dsb 2048    ; tiles 128-191 (rows: 128, 144, 160, 176)
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
	rep #$20
	lda.l phys_view+\1+1
	sec
	sbc.l phys_view+\2+1
	asl a
	asl a
	MA
	lda.b #77
	MB
	sta.b \3
.ENDM

; The picture of a single part at 64 angles: \1 = 2 * part.
.MACRO PIC64
	lda P_AL+\1
	clc
	adc.w #512
	xba
	and.w #$00FF
	lsr a
	lsr a
	ora P_H+\1
	asl a
	tax
	lda.l bike_t_lk64,x
	sta W_KF+\1
	and.w #$00FF
	asl a
	asl a
	clc
	adc.w #bike_desc_single+4*BK_PER_PART*\1/2
	sta W_DESC+\1
.ENDM

; Part \1 (2 * part) keeps its picture: its flips may change. Else its bit
; \2 in Z_PEND.
.MACRO CHECK
	lda W_DESC+\1
	cmp bike_cur+\1
	beq +
	lda.w #\2
	tsb.b Z_PEND
	bra ++
+	lda W_KF+\1
	and.w #$FF00
	cmp bike_curf+\1
	beq ++
	sta bike_curf+\1
	ora.l bk_ta0+\1
	sta bike_ta+\1
++
.ENDM

; The sprite of a single part (\1 = 2 * part) into core_oam at X, when
; the bike may be near the edges of the screen.
.MACRO PUT1
	lda.b Z_BXS
	clc
	adc P_CX+\1
	lsr a
	lsr a
	lsr a
	lsr a
	cmp.w #512
	bcs +++
	cmp.w #241
	bcc +++
	sta core_oam,x
	sta.b Z_T0
	lda.b Z_BYS
	sec
	sbc P_CY+\1
	lsr a
	lsr a
	lsr a
	lsr a
	cmp.w #480
	bcs +++
	cmp.w #241
	bcc +++
	sta core_oam+1,x
	lda bike_ta+\1
	sta core_oam+2,x
	lda.b Z_T0
	cmp.w #256
	bcs +
	jsr bk_x8
+	inx
	inx
	inx
	inx
+++
.ENDM

; The same when the whole bike is on the screen (bk_oam).
.MACRO PUT1F
	lda.b Z_BXS
	clc
	adc P_CX+\1
	lsr a
	lsr a
	lsr a
	lsr a
	sta core_oam,x
	lda.b Z_BYS
	sec
	sbc P_CY+\1
	lsr a
	lsr a
	lsr a
	lsr a
	sta core_oam+1,x
	lda bike_ta+\1
	sta core_oam+2,x
	inx
	inx
	inx
	inx
.ENDM

.SECTION ".bike_text" SUPERFREE

; For each part: its place in the copy of the rows, its first tile with its
; palette and priority, its bit, its slot.
bk_dst:
	.dw 0, 64, 128, 192, 256, 320, 384, 448, 1024, 1088, 1152
bk_ta0:
	.dw 128|(BK_PAL_THIGH*2|PRIO)<<8, 130|(BK_PAL_LEG*2|PRIO)<<8
	.dw 132|(BK_PAL_UPARM*2|PRIO)<<8, 134|(BK_PAL_FOREARM*2|PRIO)<<8
	.dw 136|(BK_PAL_S1A*2|PRIO)<<8, 138|(BK_PAL_S1B*2|PRIO)<<8
	.dw 140|(BK_PAL_S2A*2|PRIO)<<8, 142|(BK_PAL_S2B*2|PRIO)<<8
	.dw 160|(BK_PAL_HEAD*2|PRIO)<<8, 162|(BK_PAL_TORSO*2|PRIO)<<8
	.dw 164|(BK_PAL_FRAME*2|PRIO)<<8
bk_bit:
	.dw 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024
; (2 << slot) - 1:
bike_t_fitmask:
	.dw 1, 3, 7, 15, 31, 63, 127, 255
; The bit of x >= 256 of a sprite in the high table:
bk_hb:
	.db 1, 4, 16, 64

;---------------------------------------------------------------------------
; void bike_reset(void): no part in the VRAM, the copy of the rows cleared.
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
	lda #0
	sta bike_curf,x
	lda.l bk_ta0,x
	sta bike_ta,x
	inx
	inx
	cpx #22
	bcc -
	lda #0
	sta bike_cur+2*FRAME        ; the body: no sprites
	sta bike_toggle
	sta bike_stale
	lda.w #OAM_OBJ*4
	sta bike_oam_end
	; Zeros into bike_stage (DMA from a fixed 0 byte):
	lda.w #bike_stage
	sta $2181
	sep #$20
	lda.b #:bike_stage & 1
	sta $2183
	lda #$08                    ; fixed source, one register
	sta $4370
	lda #$80
	sta $4371
	rep #$20
	lda.w #bike_zero
	sta $4372
	sep #$20
	lda.b #:bike_zero
	sta $4374
	rep #$20
	lda #2048
	sta $4375
	sep #$20
	lda #$80
	sta $420B
	plb
	plp
	rtl

bike_zero:
	.db 0

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
	rep #$30
	jsr bk_geometry
	jsr bk_turn
	jsr bk_pictures
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
	sta.b Z_T2
	sep #$20
	lda #51
	sta.w $211C
	rep #$20
	lda.w $2134
	sta.b Z_T3
	lda.b Z_T0
	xba
	and #$00FF
	MA
	lda #19
	sta.w $211C
	rep #$20
	lda.w $2134
	clc
	adc.b Z_T3
	sta.b Z_T3
	sep #$20
	lda #51
	sta.w $211C
	rep #$20
	lda.w $2135
	and #$00FF
	clc
	adc.b Z_T3
	lsr a
	lsr a
	lsr a
	lsr a
	clc
	adc.b Z_T2
	rts

;---------------------------------------------------------------------------
; Z_IDX = the squared length of (Z_VX, Z_VY) in 1/4 pixels (each clamped
; to -127..127) >> A (3 or 4), at most 1023. Keeps X and Y.
bk_d4:
	rep #$20
	sta.b Z_IDX
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
	dec.b Z_IDX
	dec.b Z_IDX
	dec.b Z_IDX
	beq +
	lsr a
+	cmp #1024
	bcc +
	lda #1023
+	sta.b Z_IDX
	rts
_q:
	ASR
	ASR
	clc
	adc #127
	bpl +
	lda #0
+	cmp #255
	bcc +
	lda #254
+	sec
	sbc #127
	sta.b Z_AY
	MA
	lda.b Z_AY
	sta.w $211C
	rep #$20
	lda.w $2134
	rts

;---------------------------------------------------------------------------
; A = the angle of (Z_VX, Z_VY) in 256 steps (counterclockwise): the table
; by |y| >> 3 and |x| >> 3, both halved until they are below 512. Keeps Y.
bk_atan2:
	rep #$30
	lda.b Z_VX
	bpl +
	eor #$FFFF
	inc a
+	sta.b Z_AX
	lda.b Z_VY
	bpl +
	eor #$FFFF
	inc a
+	sta.b Z_AY
_norm:
	ora.b Z_AX
	cmp #512
	bcc +
	lsr.b Z_AX
	lsr.b Z_AY
	lda.b Z_AY
	bra _norm
+	lda.b Z_AY
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
; The center of the rod of part Y/2 from a = (Z_T0, Z_T1) to b = (Z_T2,
; Z_T3): a + c * (b - a), c in Z_B (times 128). Keeps Y.
bk_center:
	rep #$20
	lda.b Z_T2
	sec
	sbc.b Z_T0
	asl a
	MA
	lda.b Z_B
	MB
	clc
	adc.b Z_T0
	sta P_CX,y
	lda.b Z_T3
	sec
	sbc.b Z_T1
	asl a
	MA
	lda.b Z_B
	MB
	clc
	adc.b Z_T1
	sta P_CY,y
	rts

;---------------------------------------------------------------------------
; Where the parts are (P_CX, P_CY), their angles and mirroring (P_AL, P_H).
bk_geometry:
	; The center of the bike on the screen:
	rep #$30
	lda.l phys_view+PV_BODY_X
	sec
	sbc.l bike_org_x
	sta.b Z_T0
	lda.l phys_view+PV_BODY_X+2
	sbc.l bike_org_x+2
	sta.b Z_T1
	jsr bk_lpx16
	sta.b Z_T0
	lda.b Z_CAMX
	asl a
	asl a
	asl a
	asl a
	sta.b Z_T1
	lda.b Z_T0
	sec
	sbc.b Z_T1
	sta.b Z_BSX
	lda.l bike_org_y
	sec
	sbc.l phys_view+PV_BODY_Y
	sta.b Z_T0
	lda.l bike_org_y+2
	sbc.l phys_view+PV_BODY_Y+2
	sta.b Z_T1
	jsr bk_lpx16
	sta.b Z_T0
	lda.b Z_CAMY
	asl a
	asl a
	asl a
	asl a
	sta.b Z_T1
	lda.b Z_T0
	sec
	sbc.b Z_T1
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
	; Points from the physics:
	CONV PV_WHEEL_X, PV_BODY_X, Z_W0X
	CONV PV_WHEEL_Y, PV_BODY_Y, Z_W0Y
	CONV PV_WHEEL_X+4, PV_BODY_X, Z_W1X
	CONV PV_WHEEL_Y+4, PV_BODY_Y, Z_W1Y
	CONV PV_RIDER_X, PV_BODY_X, Z_RX
	CONV PV_RIDER_Y, PV_BODY_Y, Z_RY
	; Points fixed to the bike and to the rider: tables by the angle >> 6
	; and turned.
	rep #$30
	lda.b Z_TH
	lsr a
	lsr a
	lsr a
	lsr a
	and #$0FFC
	ldx.b Z_TR
	beq +
	ora #$1000
+	tax
	lda.l bike_rot_handle,x
	sta.b Z_HAX
	lda.l bike_rot_handle+2,x
	sta.b Z_HAY
	lda.l bike_rot_rear,x
	sta.b Z_REX
	lda.l bike_rot_rear+2,x
	sta.b Z_REY
	lda.l bike_rot_foot,x
	sta.b Z_FOX
	lda.l bike_rot_foot+2,x
	sta.b Z_FOY
	lda.l bike_rot_hip,x
	clc
	adc.b Z_RX
	sta.b Z_HIX
	lda.l bike_rot_hip+2,x
	clc
	adc.b Z_RY
	sta.b Z_HIY
	lda.l bike_rot_shoulder,x
	clc
	adc.b Z_RX
	sta.b Z_SHX
	lda.l bike_rot_shoulder+2,x
	clc
	adc.b Z_RY
	sta.b Z_SHY
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
	jsr bk_hand
	jsr bk_arm
+	jsr bk_susp
	; Torso, head, body: at the angle of the bike.
	rep #$30
	lda.b Z_TR
	beq +
	lda.w #64
	sta P_H+2*9
	sta P_H+2*8
	asl a
	sta P_H+2*FRAME
	lda.b Z_TH
	clc
	adc.w #($8000-BK_TORSO_BETA) & $FFFF
	sta P_AL+2*9
	lda.b Z_TH
	eor #$8000
	bra ++
+	stz P_H+2*9
	stz P_H+2*8
	stz P_H+2*FRAME
	lda.b Z_TH
	clc
	adc.w #BK_TORSO_BETA
	sta P_AL+2*9
	lda.b Z_TH
++	sta P_AL+2*8
	sta P_AL+2*FRAME
	stz P_CX+2*FRAME
	stz P_CY+2*FRAME
	rts

;---------------------------------------------------------------------------
; The legs and the arms from the tables by the rider's place in the frame
; of the bike (gen_bike.py): their centers rotated with the bike, their
; angles added to its angle; mirrored when turned.
.MACRO LIMB
	ldx.b Z_IDX
	lda.l bike_limb_\1_x,x
	ldy.b Z_TR
	beq +
	eor #$FFFF
	inc a
+	asl a
	MA
	lda.b Z_C
	MB
	sta.b Z_T0                  ; x c
	sep #$20
	lda.b Z_S
	MB
	sta.b Z_T1                  ; x s
	lda.l bike_limb_\1_y,x
	asl a
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
	txa
	lsr a
	tax
	lda.l bike_limb_\1_a,x
	and #$00FF
	ldy.b Z_TR
	beq +
	eor #$FFFF
	clc
	adc.w #129
	and #$00FF
+	xba
	clc
	adc.b Z_TH
	sta P_AL+\2
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
	sta.b Z_IDX
	LIMB thigh, 2*0
	LIMB leg, 2*1
	LIMB uparm, 2*2
	LIMB forearm, 2*3
	lda.b Z_TR
	beq +
	lda.w #64
	sta P_H+2*0
	sta P_H+2*1
	sta P_H+2*3
	stz P_H+2*2
	rts
+	stz P_H+2*0
	stz P_H+2*1
	stz P_H+2*3
	lda.w #64
	sta P_H+2*2
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
	lda #3
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
	lda.b Z_TR
	beq +
	lda.w #64
	sta P_H+2*3
	stz P_H+2*2
	bra ++
+	stz P_H+2*3
	lda.w #64
	sta P_H+2*2
++	lda.b Z_ELX
	sta.b Z_T0
	lda.b Z_ELY
	sta.b Z_T1
	lda.b Z_SHX
	sta.b Z_T2
	lda.b Z_SHY
	sta.b Z_T3
	sep #$20
	lda.b #BK_C_UPARM
	sta.b Z_B
	ldy.w #2*2
	jsr bk_center
	lda.b Z_KX
	sta.b Z_T0
	lda.b Z_KY
	sta.b Z_T1
	lda.b Z_ELX
	sta.b Z_T2
	lda.b Z_ELY
	sta.b Z_T3
	sep #$20
	lda.b #BK_C_FOREARM
	sta.b Z_B
	ldy.w #2*3
	jmp bk_center

;---------------------------------------------------------------------------
; The suspensions, two pieces each: front from the front wheel to the
; handlebar, rear from the rear point to the rear wheel. The pieces' centers
; are at fixed distances from the ends along the rod.
bk_susp:
	rep #$30
	lda.b Z_TR
	bne +
	lda.b Z_W0X
	sta.b Z_T0
	lda.b Z_W0Y
	sta.b Z_T1
	bra ++
+	lda.b Z_W1X
	sta.b Z_T0
	lda.b Z_W1Y
	sta.b Z_T1
++	lda.b Z_HAX
	sta.b Z_T2
	lda.b Z_HAY
	sta.b Z_T3
	lda.w #2*BK_S1_KA
	sta.b Z_T4
	lda.w #(2*BK_S1_KB) & $FFFF
	sta.b Z_T5
	ldy.w #2*4
	jsr _pieces
	lda.b Z_REX
	sta.b Z_T0
	lda.b Z_REY
	sta.b Z_T1
	lda.b Z_TR
	bne +
	lda.b Z_W1X
	sta.b Z_T2
	lda.b Z_W1Y
	sta.b Z_T3
	bra ++
+	lda.b Z_W0X
	sta.b Z_T2
	lda.b Z_W0Y
	sta.b Z_T3
++	lda.w #2*BK_S2_KA
	sta.b Z_T4
	lda.w #(2*BK_S2_KB) & $FFFF
	sta.b Z_T5
	ldy.w #2*6
; a = (Z_T0, Z_T1), b = (Z_T2, Z_T3), Y = 2 * the first piece, 2 * the
; distances of the pieces' centers from a and b in Z_T4, Z_T5.
_pieces:
	lda.b Z_T2
	sec
	sbc.b Z_T0
	sta.b Z_VX
	lda.b Z_T3
	sec
	sbc.b Z_T1
	sta.b Z_VY
	jsr bk_atan2
	sta.b Z_A8
	xba
	sta P_AL,y
	sta P_AL+2,y
	lda.b Z_A8
	asl a
	asl a
	tax
	lda #0
	sta P_H,y
	sta P_H+2,y
	sep #$20
	lda.l bike_t_sin+256,x
	sta.b Z_B                   ; cos
	lda.l bike_t_sin,x
	sta.b Z_A                   ; sin
	rep #$20
	lda.b Z_T4
	MA
	lda.b Z_B
	MB
	clc
	adc.b Z_T0
	sta P_CX,y
	sep #$20
	lda.b Z_A
	MB
	clc
	adc.b Z_T1
	sta P_CY,y
	lda.b Z_T5
	MA
	lda.b Z_B
	MB
	clc
	adc.b Z_T2
	sta P_CX+2,y
	sep #$20
	lda.b Z_A
	MB
	clc
	adc.b Z_T3
	sta P_CY+2,y
	rts

;---------------------------------------------------------------------------
; The turn: everything but the wheels squashed along the bike around its
; center (setaffinitas), the squashed pictures, the wheel drawn over it.
bk_turn:
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
	; The squash matrix: (f - 1) * (c c, c s, s s) >> 6.
	lda.b Z_C
	and #$00FF
	cmp #$0080
	bcc +
	ora #$FF00
+	MA                          ; c
	lda.b Z_C
	sta.w $211C
	rep #$20
	lda.w $2134
	sta.b Z_T0                  ; c c
	sep #$20
	lda.b Z_S
	sta.w $211C
	rep #$20
	lda.w $2134
	sta.b Z_T1                  ; c s
	lda.b Z_S
	and #$00FF
	cmp #$0080
	bcc +
	ora #$FF00
+	MA                          ; s
	lda.b Z_S
	sta.w $211C
	rep #$20
	lda.w $2134
	sta.b Z_T2                  ; s s
	lda.b Z_T0
	jsr _m6
	sta.b Z_MA
	rep #$20
	lda.b Z_T1
	jsr _m6
	sta.b Z_MB
	rep #$20
	lda.b Z_T2
	jsr _m6
	sta.b Z_MD
	; Squash the centers of the parts 0-9 (around the center of the bike):
	; x += x a + y b, y += x b + y d.
	ldy #0
_sq:
	rep #$20
	lda P_CX,y
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
	lda P_CY,y
	asl a
	asl a
	MA
	lda.b Z_MB
	MB
	clc
	adc.b Z_T0
	clc
	adc P_CX,y
	sta P_CX,y
	sep #$20
	lda.b Z_MD
	MB
	clc
	adc.b Z_T1
	clc
	adc P_CY,y
	sta P_CY,y
	iny
	iny
	cpy.w #2*FRAME
	bcc _sq
	; Not squashed pictures, mirrored if f < 0: alpha = 2 th + 1/2 - alpha.
	lda.b Z_LV
	cmp #4
	bne +++
	lda.b Z_NEG
	beq +++
	ldy #0
-	lda.b Z_TH
	asl a
	clc
	adc #$8000
	sec
	sbc P_AL,y
	sta P_AL,y
	lda P_H,y
	eor.w #64
	sta P_H,y
	iny
	iny
	cpy.w #2*FRAME
	bcc -
	lda.b Z_TH
	asl a
	clc
	adc #$8000
	sec
	sbc P_AL+2*FRAME
	sta P_AL+2*FRAME
	lda P_H+2*FRAME
	eor.w #128
	sta P_H+2*FRAME
+++	rts
; A (8 bits) = (A * Z_G >> 8) >> 6.
_m6:
	MA
	lda.b Z_G
	MB
	ASR
	ASR
	ASR
	ASR
	ASR
	ASR
	sep #$20
	rts

;---------------------------------------------------------------------------
; The pictures wanted (W_DESC, W_KF): the step of the angle (P_AL) and the
; mirroring (P_H) give the stored picture and its flips from the tables
; bike_t_lk32/64/128 (k | flips << 8, gen_bike.py).
bk_pictures:
	rep #$30
	lda.b Z_LV
	cmp #4
	beq +
	jmp bk_tpictures
+	PIC64 2*0
	PIC64 2*1
	PIC64 2*2
	PIC64 2*3
	PIC64 2*4                   ; the pieces of a suspension: the same angle
	lda W_KF+2*4
	sta W_KF+2*5
	lda W_DESC+2*4
	clc
	adc.w #4*BK_PER_PART
	sta W_DESC+2*5
	PIC64 2*6
	lda W_KF+2*6
	sta W_KF+2*7
	lda W_DESC+2*6
	clc
	adc.w #4*BK_PER_PART
	sta W_DESC+2*7
	PIC64 2*8
	PIC64 2*9
	lda P_AL+2*FRAME            ; the body: 128 steps
	clc
	adc.w #256
	xba
	and.w #$00FF
	lsr a
	ora P_H+2*FRAME
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
	rts

; The squashed pictures: all at the angle of the bike as drawn.
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
+	asl a
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
	ldy #0
-	sta W_DESC,y
	clc
	adc.w #4*BK_PER_PART
	tax
	lda.b Z_T4
	sta W_KF,y
	txa
	iny
	iny
	cpy.w #2*FRAME
	bcc -
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
+	asl a
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
	rts

;---------------------------------------------------------------------------
; Loading the pictures that changed, within the budget.
bk_load:
	rep #$30
	stz.b Z_PEND
	CHECK 2*0, 1
	CHECK 2*1, 2
	CHECK 2*2, 4
	CHECK 2*3, 8
	CHECK 2*4, 16
	CHECK 2*5, 32
	CHECK 2*6, 64
	CHECK 2*7, 128
	CHECK 2*8, 256
	CHECK 2*9, 512
	CHECK 2*FRAME, 1024
	lda.b Z_PEND
	bne +
	rts
+	; Room in the queue for 8 transfers:
	lda core_dmaq_n
	cmp.w #(DMAQ_MAX-8)*8+1
	bcc +
	rts
+	; The ranges of slots of the parts that changed: pair 0 (parts 0-7,
	; slots 0-7), pair 1 (head 0, torso 1, body 2..).
	lda #$FFFF
	sta bike_rlo
	sta bike_rlo+2
	stz.b Z_T4                  ; bytes of pair 0
	stz.b Z_T5                  ; bytes of pair 1
	lda.b Z_PEND
	and #$00FF
	beq +
	tax
	lda.l bike_t_lowbit,x
	and #$00FF
	sta bike_rlo
	lda.l bike_t_highbit,x
	and #$00FF
	sta bike_rhi
	sec
	sbc bike_rlo
	inc a
	xba
	lsr a
	sta.b Z_T4
+	lda.b Z_PEND
	xba
	and #$0007
	beq ++
	tax
	lda.l bike_t_lowbit,x
	and #$00FF
	sta bike_rlo+2
	txa
	and #$0004
	beq +
	jsr bk_nframe               ; the body: slots 2..2 + n - 1
	bra +++
+	lda.l bike_t_highbit,x
	and #$00FF
+++	sta bike_rhi+2
	sec
	sbc bike_rlo+2
	inc a
	xba
	lsr a
	sta.b Z_T5
++	lda.b Z_PEND
	sta.b Z_ACC
	lda bike_toggle
	eor #1
	sta bike_toggle
	; All of them if they fit the budget; else the pair first in turn
	; and the parts of the other while its range fits.
	lda.b Z_T4
	clc
	adc.b Z_T5
	cmp.w #BUDGET+1
	bcc _stage0
	lda bike_toggle             ; (toggled: 1 = pair 0 was first)
	beq _p1first
	lda.w #BUDGET
	sec
	sbc.b Z_T4
	asl a
	xba
	and #$00FF                  ; slots left
	clc
	adc bike_rlo+2
	dec a
	sta.b Z_T3                  ; the last slot of pair 1 that fits
	lda.b Z_ACC
	and #$00FF
	sta.b Z_ACC
	ldx #2
	jsr _fit
	bra _stage0
_p1first:
	lda.w #BUDGET
	sec
	sbc.b Z_T5
	asl a
	xba
	and #$00FF
	clc
	adc bike_rlo
	dec a
	sta.b Z_T3                  ; the last slot of pair 0 that fits
	lda.b Z_ACC
	and #$0700
	sta.b Z_ACC
	ldx #0
	jsr _fit
_stage0:
	; At most 4 sprites: straight from the ROM (8 transfers).
	lda.b Z_ACC
	and #$00FF
	tax
	lda.l bike_t_popcnt,x
	and #$00FF
	sta.b Z_T4
	lda.b Z_ACC
	xba
	and #$0003
	tax
	lda.l bike_t_popcnt,x
	and #$00FF
	clc
	adc.b Z_T4
	sta.b Z_T4
	lda.b Z_ACC
	and #$0400
	beq +
	jsr bk_nframe
	dec a
	clc
	adc.b Z_T4
	sta.b Z_T4
+	lda.b Z_T4
	cmp #5
	bcs +
	jmp bk_direct
+	; The parts loaded straight in earlier frames whose places are in the
	; ranges: their copy in the rows is renewed too.
	stz.b Z_T4
	lda bike_rlo
	bmi ++
	asl a
	tax
	lda.l bike_t_fitmask,x
	lsr a
	eor #$FFFF
	sta.b Z_T4                  ; slots from rlo
	lda bike_rhi
	asl a
	tax
	lda.l bike_t_fitmask,x
	and.b Z_T4
	sta.b Z_T4                  ; slots rlo..rhi of pair 0
++	lda bike_rlo+2
	bmi ++
	bne +
	lda.w #$0100                ; the head
	tsb.b Z_T4
+	lda bike_rlo+2
	cmp #2
	bcs +
	lda bike_rhi+2
	beq +
	lda.w #$0200                ; the torso
	tsb.b Z_T4
+	lda bike_rhi+2
	cmp #2
	bcc ++
	lda.w #$0400                ; the body
	tsb.b Z_T4
++	lda bike_stale
	and.b Z_T4
	ora.b Z_ACC
	sta.b Z_T5                  ; the parts copied now
	eor #$FFFF
	and bike_stale
	sta bike_stale
	; Copy the pictures into the copy of the rows: DMA channel 7 into the
	; WRAM.
	sep #$20
	lda #$00
	sta $4370
	lda #$80
	sta $4371
	stz $2183
	lda.b #:bike_desc_single
	sta.b Z_PTR+2
	rep #$20
_stage:
	lda.b Z_T5
	bne +
	jmp _queue
+	and #$00FF
	beq +
	tax
	lda.l bike_t_lowbit,x
	bra ++
+	lda.b Z_T5
	xba
	tax
	lda.l bike_t_lowbit,x
	clc
	adc #8
++	and #$00FF
	asl a
	tax
	tay
	lda.l bk_bit,x
	trb.b Z_T5
	and.b Z_ACC
	bne +
	lda bike_cur,y              ; renewed: the picture in the VRAM
	sta.b Z_PTR
	bra ++
+	jsr bk_take
++	lda.l bk_dst,x
	clc
	adc.w #bike_stage
	sta.b Z_DST
	cpy.w #2*FRAME
	beq _fr
	ldy #0
	jsr bk_stage_sprite
	bra _stage
_fr:
	lda [Z_PTR]
	and #$00FF
	sta.b Z_NS
	ldy #1
-	jsr bk_stage_sprite
	lda.b Z_DST
	clc
	adc #64
	sta.b Z_DST
	iny
	iny
	iny
	dec.b Z_NS
	bne -
	bra _stage
_queue:
	; The queue: top and bottom row of each pair.
	ldx #0
	jsr _qpair
	ldx #2
_qpair:
	lda bike_rlo,x
	cmp #$FFFF
	bne +
	rts
+	sta.b Z_LO
	lda bike_rhi,x
	sec
	sbc.b Z_LO
	inc a
	xba
	lsr a
	lsr a                       ; size: slots * 64
	sta.b Z_T1
	txa
	xba                         ; pair * 512
	asl a                       ; pair * 1024
	sta.b Z_T2
	lda.b Z_LO
	xba
	lsr a
	lsr a                       ; lo * 64
	clc
	adc.b Z_T2
	clc
	adc.w #bike_stage
	sta.b Z_T2                  ; source
	txa
	xba                         ; pair * 512 (words: 2 tile rows)
	sta.b Z_T3
	lda.b Z_LO
	asl a
	asl a
	asl a
	asl a
	asl a                       ; lo * 32 (words)
	clc
	adc.b Z_T3
	clc
	adc.w #VRAM_PARTS
	sta.b Z_T3                  ; VRAM address
	jsr bk_queue
	lda.b Z_T2
	clc
	adc #512
	sta.b Z_T2
	lda.b Z_T3
	clc
	adc #256
	sta.b Z_T3
	jmp bk_queue

; Pair X/2 second: its pending parts whose last slot is at most Z_T3 are
; added to Z_ACC, its range shrinks to them (or goes).
_fit:
	lda.b Z_T3
	cmp bike_rlo,x
	bmi _none
	cpx #0
	bne _f1
	; Pair 0: the parts of slots rlo..Z_T3.
	cmp #8
	bcc +
	lda #7
+	asl a
	tax
	lda.l bike_t_fitmask,x      ; (2 << slot) - 1
	and.b Z_PEND
	and #$00FF
	beq _none0
	tax
	ora.b Z_ACC
	sta.b Z_ACC
	lda.l bike_t_highbit,x
	and #$00FF
	sta bike_rhi
	rts
_f1:
	; Pair 1: the head (slot 0), the torso (1), the body (2..).
	lda.b Z_PEND
	and #$0700
	sta.b Z_T2
	jsr bk_nframe
	cmp.b Z_T3
	beq +
	bcc +
	lda.b Z_T2                  ; not the body
	and #$0300
	sta.b Z_T2
+	lda.b Z_T3
	cmp #1
	bcs +
	lda.b Z_T2                  ; not the torso
	and #$0100
	sta.b Z_T2
+	lda.b Z_T2
	beq _none
	ora.b Z_ACC
	sta.b Z_ACC
	lda.b Z_T2
	xba
	tax
	lda.l bike_t_highbit,x
	and #$00FF
	cmp #2
	bne +
	jsr bk_nframe
+	sta bike_rhi+2
	rts
_none0:
	ldx #0
_none:
	lda #$FFFF
	sta bike_rlo,x
	rts

; Part Y/2 (X = Y) gets its wanted picture: Z_PTR is its descriptor.
bk_take:
	lda W_DESC,y
	sta bike_cur,y
	sta.b Z_PTR
	lda W_KF,y
	and #$FF00
	sta bike_curf,y
	ora.l bk_ta0,x
	sta bike_ta,y
	rts

; Loading at most 4 sprites: the transfers straight from the ROM (two a
; sprite); their copy in the rows is out of date (bike_stale).
bk_direct:
	lda.b Z_ACC
	tsb bike_stale
	sep #$20
	lda.b #:bike_desc_single
	sta.b Z_PTR+2
	rep #$20
	lda.b Z_ACC
	sta.b Z_T5
-	lda.b Z_T5
	bne +
	rts
+	and #$00FF
	beq +
	tax
	lda.l bike_t_lowbit,x
	bra ++
+	lda.b Z_T5
	xba
	tax
	lda.l bike_t_lowbit,x
	clc
	adc #8
++	and #$00FF
	asl a
	tax
	tay
	lda.l bk_bit,x
	trb.b Z_T5
	jsr bk_take
	lda.l bk_ta0,x
	and #$00FF                  ; first tile
	asl a
	asl a
	asl a
	asl a
	clc
	adc.w #VRAM_OBJ
	sta.b Z_DST
	cpy.w #2*FRAME
	beq +
	ldy #0
	jsr bk_queue_sprite
	bra -
+	lda [Z_PTR]
	and #$00FF
	sta.b Z_NS
	ldy #1
--	jsr bk_queue_sprite
	lda.b Z_DST
	clc
	adc #32
	sta.b Z_DST
	iny
	iny
	iny
	dec.b Z_NS
	bne --
	bra -

; The sprite whose pointer is at [Z_PTR],y to the VRAM at Z_DST (words):
; two transfers of the queue (its top and bottom tiles).
bk_queue_sprite:
	phx
	lda [Z_PTR],y
	sta.b Z_SRC
	iny
	iny
	lda [Z_PTR],y
	dey
	dey
	sta.b Z_SRC+2
	ldx core_dmaq_n
	sep #$20
	lda.b #DMAQ_VRAM
	sta core_dmaq,x
	sta core_dmaq+8,x
	lda.b Z_SRC+2
	sta core_dmaq+3,x
	sta core_dmaq+8+3,x
	rep #$20
	lda.b Z_SRC
	sta core_dmaq+1,x
	clc
	adc #64
	sta core_dmaq+8+1,x
	lda #64
	sta core_dmaq+4,x
	sta core_dmaq+8+4,x
	lda.b Z_DST
	sta core_dmaq+6,x
	clc
	adc #256
	sta core_dmaq+8+6,x
	lda core_dmaq_bytes
	clc
	adc #128
	sta core_dmaq_bytes
	txa
	clc
	adc #16
	sta core_dmaq_n
	plx
	rts

; A = the last slot of the body's wanted picture (2 + sprites - 1).
bk_nframe:
	lda W_DESC+2*FRAME
	sta.b Z_PTR
	sep #$20
	lda.b #:bike_desc_frame
	sta.b Z_PTR+2
	rep #$20
	lda [Z_PTR]
	and #$00FF
	inc a
	rts

; A transfer of Z_T1 bytes from $7E:Z_T2 to the VRAM at Z_T3 (words).
bk_queue:
	phx
	ldx core_dmaq_n
	sep #$20
	lda.b #DMAQ_VRAM
	sta core_dmaq,x             ; type +0, source +1, bank +3, size +4,
	lda #$7E                    ; VRAM address +6
	sta core_dmaq+3,x
	rep #$20
	lda.b Z_T2
	sta core_dmaq+1,x
	lda.b Z_T1
	sta core_dmaq+4,x
	lda.b Z_T3
	sta core_dmaq+6,x
	lda.b Z_T1
	clc
	adc core_dmaq_bytes
	sta core_dmaq_bytes
	txa
	clc
	adc #8
	sta core_dmaq_n
	plx
	rts

; Copies the sprite whose pointer is at [Z_PTR],y into the rows at Z_DST.
bk_stage_sprite:
	lda [Z_PTR],y
	sta.b Z_SRC
	iny
	iny
	lda [Z_PTR],y
	dey
	dey
	sep #$20
	sta $4374
	rep #$20
	lda.b Z_DST
	sta $2181
	lda.b Z_SRC
	sta $4372
	lda #64
	sta $4375
	sep #$20
	lda #$80
	sta $420B
	rep #$20
	lda.b Z_DST
	clc
	adc #512
	sta $2181
	lda.b Z_SRC
	clc
	adc #64
	sta $4372
	lda #64
	sta $4375
	sep #$20
	lda #$80
	sta $420B
	rep #$20
	rts

;---------------------------------------------------------------------------
; The sprites of the bike: OAM 32-63, the first on top (the reverse of the
; order the PC draws). Pivots are biased by 256 pixels: a sprite is on the
; screen when its x is 241..511 and y 241..479 (the low byte is what the
; OAM gets, x < 256 sets the bit of x >= 256).
bk_oam:
	rep #$30
	lda.b Z_BSX
	clc
	adc.w #8+4096
	sta.b Z_BXB
	sec
	sbc #128
	sta.b Z_BXS
	lda.b Z_BSY
	clc
	adc.w #8+4096
	sta.b Z_BYB
	sec
	sbc #128
	sta.b Z_BYS
	stz core_oam+512+OAM_BIKE/4
	stz core_oam+512+OAM_BIKE/4+2
	stz core_oam+512+OAM_BIKE/4+4
	stz core_oam+512+OAM_BIKE/4+6
	ldx.w #OAM_BIKE*4
	; The parts are within 48 pixels of the center: with the center at
	; 56..199, 56..167 they are all on the screen (Z_FAST).
	stz.b Z_FAST
	lda.b Z_BSX
	sec
	sbc.w #56*16
	cmp.w #144*16
	bcs +
	lda.b Z_BSY
	sec
	sbc.w #56*16
	cmp.w #112*16
	bcs +
	dec.b Z_FAST
+	lda.b Z_LATE
	bmi +
	jsr bk_wheel
+	bit.b Z_FAST
	bmi +
	jmp _edge
+	PUT1F 2*3
	PUT1F 2*2
	PUT1F 2*9
	PUT1F 2*1
	PUT1F 2*0
	PUT1F 2*8
	jsr bk_frame
	PUT1F 2*7
	PUT1F 2*6
	PUT1F 2*5
	PUT1F 2*4
	jmp _wheels
_edge:
	PUT1 2*3
	PUT1 2*2
	PUT1 2*9
	PUT1 2*1
	PUT1 2*0
	PUT1 2*8
	jsr bk_frame
	PUT1 2*7
	PUT1 2*6
	PUT1 2*5
	PUT1 2*4
_wheels:
	lda.b Z_LATE
	bpl +
	lda #1
	jsr bk_wheel
	lda #0
	jsr bk_wheel
	bra ++
+	eor #1
	jsr bk_wheel
++	; Hide the sprite after the last and the ones used in the last frame.
	stx.b Z_T5
	lda #$E000                  ; y 224
-	cpx.w #OAM_OBJ*4
	bcs +
	sta core_oam,x
	inx
	inx
	inx
	inx
	cpx bike_oam_end
	bcc -
+	lda.b Z_T5
	sta bike_oam_end
	rts

; A wheel (A = 0, 1). X = offset in core_oam.
bk_wheel:
	phx
	asl a
	tay
	asl a
	tax
	lda.b Z_BXS
	clc
	adc.b Z_W0X,x
	lsr a
	lsr a
	lsr a
	lsr a
	sta.b Z_T0
	lda.b Z_BYS
	sec
	sbc.b Z_W0Y,x
	lsr a
	lsr a
	lsr a
	lsr a
	sta.b Z_T1
	tyx
	lda.l phys_view+PV_WHEEL_A,x
	clc
	adc #512
	xba
	and #$00FF
	and #$00FC
	lsr a                       ; 64 steps * 2
	tax
	lda.l bike_t_wheel,x
	sta.b Z_TA
	plx
	jmp bk_put

; The sprites of the body of the bike. X = offset in core_oam.
bk_frame:
	lda bike_cur+2*FRAME
	bne +
	rts
+	sta.b Z_PTR
	lda bike_ta+2*FRAME
	sta.b Z_TA
	lda.b Z_BXB
	clc
	adc P_CX+2*FRAME
	lsr a
	lsr a
	lsr a
	lsr a
	sec
	sbc #128
	sta.b Z_PX
	lda.b Z_BYB
	sec
	sbc P_CY+2*FRAME
	lsr a
	lsr a
	lsr a
	lsr a
	sec
	sbc #128
	sta.b Z_PY
	lda [Z_PTR]
	and #$00FF
	sta.b Z_NS
	; The corners for the flips: 1 + 3 * 6 + 12 * (flips >> 6).
	lda bike_curf+2*FRAME
	xba
	and #$00C0
	lsr a
	lsr a
	lsr a
	sta.b Z_T2                  ; 8 f
	lsr a
	clc
	adc.b Z_T2                  ; 12 f
	clc
	adc.w #1+3*BK_FRAME_SPRITES
	tay
-	lda [Z_PTR],y               ; dx + 128, dy + 128
	sta.b Z_T4
	and #$00FF
	clc
	adc.b Z_PX
	sta.b Z_T0
	lda.b Z_T4
	xba
	and #$00FF
	clc
	adc.b Z_PY
	sta.b Z_T1
	jsr bk_put
	inc.b Z_TA
	inc.b Z_TA
	iny
	iny
	dec.b Z_NS
	bne -
	rts

; A 16x16 sprite at (Z_T0, Z_T1) (biased), Z_TA = tile | attributes << 8,
; into core_oam at X if on the screen; X goes to the next sprite. Keeps Y.
bk_put:
	bit.b Z_FAST
	bpl +
	lda.b Z_T0
	sta core_oam,x
	lda.b Z_T1
	sta core_oam+1,x
	lda.b Z_TA
	sta core_oam+2,x
	inx
	inx
	inx
	inx
	rts
+	lda.b Z_T0
	cmp #241
	bcc _off
	cmp #512
	bcs _off
	sta core_oam,x
	lda.b Z_T1
	cmp #241
	bcc _off
	cmp #480
	bcs _off
	sta core_oam+1,x
	lda.b Z_TA
	sta core_oam+2,x
	lda.b Z_T0
	cmp #256
	bcs +
	jsr bk_x8
+	inx
	inx
	inx
	inx
_off:
	rts

; Sets the bit of x >= 256 of the sprite at X in core_oam.
bk_x8:
	phx
	txa
	lsr a
	lsr a
	and #$0003
	tax
	sep #$20
	lda.l bk_hb,x
	sta.b Z_T1
	rep #$20
	lda 1,s
	lsr a
	lsr a
	lsr a
	lsr a
	tax
	sep #$20
	lda.b Z_T1
	ora core_oam+512,x
	sta core_oam+512,x
	rep #$20
	plx
	rts

.ENDS
