; The bike, the rider and the objects as sprites (bike.h).
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

; phys_view (bike_view_t) and phys_objs (phys_obj_t) as 816-tcc lays them
; out (s32 on 4 bytes, aligned to 4 bytes):
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
.DEFINE PO_ACTIVE   3
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
.DEFINE VRAM_OBJS   VRAM_OBJ+192*16

; The direct page of bike_draw and objects_draw:
.ENUM $00
Z_CAMX      dw
Z_CAMY      dw
Z_BSX       dw          ; center of the bike on the screen (1/16 pixel)
Z_BSY       dw
Z_TH        dw          ; angle of the bike
Z_TR        dw          ; turned (hatra_f): 0 or 1
Z_C         db          ; cos and sin of the bike's angle, times 128
Z_S         db
Z_CJ        db          ; the same, negated when the bike is turned
Z_SJ        db
Z_B         db          ; factors
Z_A         db
Z_F         db          ; the squash of the turn, times 128
Z_PAD       db
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
Z_LV        dw          ; level of the squashed pictures, 4: not turning
Z_NEG       dw          ; the turn's squash is negative (mirrored)
Z_TEFF      dw          ; turned as drawn
Z_LATE      dw          ; the wheel drawn over the bike, $FFFF: none
Z_LEFT      dw          ; bytes left of the budget
Z_LO        dw
Z_HI        dw
Z_PAIR      dw
Z_ACC       dw          ; bit p: part p is loaded this frame
Z_PTR       dsb 4       ; a long pointer
Z_SRC       dsb 4       ; source of a DMA
Z_DST       dw
Z_OX        dw          ; offset of the next sprite in core_oam
Z_N         dw          ; sprites written
Z_NMAX      dw
Z_HB        dw          ; first byte of the high table of the sprites
Z_PX        dw          ; pivot of a part on the screen (pixels)
Z_PY        dw
Z_ATTR      dw
Z_TILE      dw
Z_NS        dw
Z_I         dw
Z_LKHALF    dw
Z_LKMASK    dw
.ENDE

.BASE $00

.RAMSECTION ".bike_dp" BANK 0 SLOT 1 ALIGN 256
bike_dp     dsb 256
.ENDS

.RAMSECTION ".bike_vars" BANK 0 SLOT 1
bike_cur    dsw 11      ; the descriptor of each part in the VRAM, 0: none
bike_curf   dsw 11      ; flips of its sprites
bike_toggle dw          ; which pair of rows goes first
bike_rlo    dsw 2       ; ranges of slots loaded this frame ($FFFF: none)
bike_rhi    dsw 2
P_CX        dsw 11      ; the parts: center
P_CY        dsw 11
P_AL        dsw 11      ; angle
P_H         dsw 11      ; mirrored
W_DESC      dsw 11      ; the picture wanted (descriptor) and its flips
W_FLIP      dsw 11
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

; The relative position of a point of phys_view, in units:
; ((p - body) >> 3) * 77 >> 11.
.MACRO CONV
	rep #$20
	lda.l phys_view+\1
	sec
	sbc.l phys_view+\2
	sta.b Z_T0
	lda.l phys_view+\1+2
	sbc.l phys_view+\2+2
	xba
	and.w #$FF00
	asl a
	asl a
	asl a
	asl a
	asl a
	sta.b Z_T1
	lda.b Z_T0
	lsr a
	lsr a
	lsr a
	ora.b Z_T1
	MA
	lda.b #77
	MB
	ASR
	ASR
	ASR
	sta.b \3
.ENDM

; (\3, \4) = the point (\1, \2) of the bike (along it, up), rotated with
; the bike (and mirrored if turned).
.MACRO ROT
	rep #$20
	lda.w #(2*(\1)) & $FFFF
	MA
	lda.b Z_CJ
	MB
	sta.b \3
	sep #$20
	lda.b Z_SJ
	MB
	sta.b \4
	lda.w #(2*(\2)) & $FFFF
	MA
	lda.b Z_S
	MB
	sta.b Z_T0
	lda.b \3
	sec
	sbc.b Z_T0
	sta.b \3
	sep #$20
	lda.b Z_C
	MB
	clc
	adc.b \4
	sta.b \4
.ENDM

.SECTION ".bike_text" SUPERFREE

; For each part: its place in the copy of the rows, its first tile, its
; palette and priority, its bit, p * pictures of a part.
bk_dst:
	.dw 0, 64, 128, 192, 256, 320, 384, 448, 1024, 1088, 1152
bk_tile:
	.dw 128, 130, 132, 134, 136, 138, 140, 142, 160, 162, 164
bk_attr:
	.dw BK_PAL_THIGH*2|PRIO, BK_PAL_LEG*2|PRIO, BK_PAL_UPARM*2|PRIO
	.dw BK_PAL_FOREARM*2|PRIO, BK_PAL_S1A*2|PRIO, BK_PAL_S1B*2|PRIO
	.dw BK_PAL_S2A*2|PRIO, BK_PAL_S2B*2|PRIO, BK_PAL_HEAD*2|PRIO
	.dw BK_PAL_TORSO*2|PRIO, BK_PAL_FRAME*2|PRIO
bk_bit:
	.dw 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024
bk_base:
	.dw 0, BK_PER_PART, 2*BK_PER_PART, 3*BK_PER_PART, 4*BK_PER_PART
	.dw 5*BK_PER_PART, 6*BK_PER_PART, 7*BK_PER_PART, 8*BK_PER_PART
	.dw 9*BK_PER_PART
; The parts of each pair of rows and their slots:
bk_pair_part:
	.dw 0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20
bk_pair_slot:
	.dw 0, 1, 2, 3, 4, 5, 6, 7, 0, 1, 2
; The order of the sprites (the first on top), the PC draws the reverse:
bk_order:
	.dw 2*3, 2*2, 2*9, 2*1, 2*0, 2*8, 2*FRAME, 2*7, 2*6, 2*5, 2*4
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
	lda #0
-	sta bike_cur,x
	sta bike_curf,x
	inx
	inx
	cpx #22
	bcc -
	sta bike_toggle
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
; A = (Z_T1:Z_T0 >> 4) * 4915 >> 16 (16 bits): 1/16 level pixels of a
; distance from the origin (0 if negative).
bk_lpx16:
	rep #$20
	lda.b Z_T1
	bpl +
	lda #0
	rts
+	lda.b Z_T0
	lsr a
	lsr a
	lsr a
	lsr a
	sta.b Z_T2
	lda.b Z_T1
	xba
	and #$FF00
	asl a
	asl a
	asl a
	asl a
	ora.b Z_T2
	sta.b Z_T2                  ; e1:e0
	lda.b Z_T1
	lsr a
	lsr a
	lsr a
	lsr a
	and #$00FF
	sta.b Z_T3                  ; e2
	lda.b Z_T2
	and #$00FF
	MA
	lda #$33
	sta.w $211C
	rep #$20
	lda.w $2134
	sta.b Z_T4                  ; low = e0 * $33
	sep #$20
	lda #$13
	sta.w $211C
	rep #$20
	lda.w $2134
	sta.b Z_T5                  ; e0 * $13
	lda.b Z_T2
	xba
	and #$00FF
	MA
	lda #$33
	sta.w $211C
	rep #$20
	lda.w $2134
	clc
	adc.b Z_T5
	sta.b Z_T5                  ; mid = e0 * $13 + e1 * $33
	lda.b Z_T4
	xba
	and #$00FF
	clc
	adc.b Z_T5
	xba
	and #$00FF
	sta.b Z_T4                  ; (low >> 8 + mid) >> 8
	sep #$20
	lda #$13
	sta.w $211C
	rep #$20
	lda.w $2134
	clc
	adc.b Z_T4
	sta.b Z_T4                  ; + e1 * $13
	lda.b Z_T3
	MA
	lda #$33
	sta.w $211C
	rep #$20
	lda.w $2134
	clc
	adc.b Z_T4
	sta.b Z_T4                  ; + e2 * $33
	sep #$20
	lda #$13
	sta.w $211C
	rep #$20
	lda.w $2134
	xba
	and #$FF00
	clc
	adc.b Z_T4                  ; + e2 * $13 << 8
	rts

;---------------------------------------------------------------------------
; The squared length of (Z_VX, Z_VY) in 1/4 pixels, each clamped to
; -127..127: A = d4. Keeps X and Y.
bk_d4:
	rep #$20
	lda.b Z_VX
	jsr _q
	sta.b Z_T5
	lda.b Z_VY
	jsr _q
	clc
	adc.b Z_T5
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
; A = the angle of (Z_VX, Z_VY) (u16, counterclockwise). Keeps Y.
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
	ora.b Z_AX
	bne _scale
	rts                         ; 0
_scale:
	and #$FF00
	beq +
	lsr.b Z_AX
	lsr.b Z_AY
	lda.b Z_AX
	ora.b Z_AY
	bra _scale
+	lda.b Z_AY
	cmp.b Z_AX
	beq _yle
	bcs _ygt
_yle:
	xba                         ; ay << 8
	sta.w $4204
	sep #$20
	lda.b Z_AX
	sta.w $4206
	nop
	nop
	nop
	nop
	nop
	nop
	rep #$20
	lda.w $4214
	asl a
	tax
	lda.l bike_t_atan,x
	bra _quad
_ygt:
	lda.b Z_AX
	xba
	sta.w $4204
	sep #$20
	lda.b Z_AY
	sta.w $4206
	nop
	nop
	nop
	nop
	nop
	nop
	rep #$20
	lda.w $4214
	asl a
	tax
	lda #16384
	sec
	sbc.l bike_t_atan,x
_quad:
	sta.b Z_T5                  ; base
	lda.b Z_VX
	bmi _xneg
	lda.b Z_VY
	bmi +
	lda.b Z_T5
	rts
+	lda #0
	sec
	sbc.b Z_T5
	rts
_xneg:
	lda.b Z_VY
	bmi +
	lda #32768
	sec
	sbc.b Z_T5
	rts
+	lda #32768
	clc
	adc.b Z_T5
	rts

;---------------------------------------------------------------------------
; A part that is a rod from a = (Z_T0, Z_T1) to b = (Z_T2, Z_T3): its
; center a + c * (b - a) (c in Z_B, times 128), its angle, mirrored as X.
; Y = 2 * part.
bk_rod:
	rep #$30
	txa
	sta P_H,y
	lda.b Z_T2
	sec
	sbc.b Z_T0
	sta.b Z_VX
	lda.b Z_T3
	sec
	sbc.b Z_T1
	sta.b Z_VY
	MUL2 Z_VX, Z_B
	clc
	adc.b Z_T0
	sta P_CX,y
	MUL2 Z_VY, Z_B
	clc
	adc.b Z_T1
	sta P_CY,y
	jsr bk_atan2
	sta P_AL,y
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
	sta.b Z_SJ
	lda.l bike_t_sin+256,x
	sta.b Z_C
	sta.b Z_CJ
	rep #$20
	lda.l phys_view+PV_TURNED
	and #$00FF
	beq +
	lda #1
+	sta.b Z_TR
	beq +
	sep #$20
	lda.b Z_C
	jsr _neg8
	sta.b Z_CJ
	lda.b Z_S
	jsr _neg8
	sta.b Z_SJ
+
	; Points from the physics:
	CONV PV_WHEEL_X, PV_BODY_X, Z_W0X
	CONV PV_WHEEL_Y, PV_BODY_Y, Z_W0Y
	CONV PV_WHEEL_X+4, PV_BODY_X, Z_W1X
	CONV PV_WHEEL_Y+4, PV_BODY_Y, Z_W1Y
	CONV PV_RIDER_X, PV_BODY_X, Z_RX
	CONV PV_RIDER_Y, PV_BODY_Y, Z_RY
	CONV PV_HEAD_X, PV_BODY_X, Z_HDX
	CONV PV_HEAD_Y, PV_BODY_Y, Z_HDY
	; Points fixed to the bike and to the rider:
	ROT BK_HANDLE_J, BK_HANDLE_F, Z_HAX, Z_HAY
	ROT BK_REAR_J, BK_REAR_F, Z_REX, Z_REY
	ROT BK_FOOT_J, BK_FOOT_F, Z_FOX, Z_FOY
	ROT BK_HIP_J, BK_HIP_F, Z_HIX, Z_HIY
	ROT BK_SHOULDER_J, BK_SHOULDER_F, Z_SHX, Z_SHY
	ROT BK_TORSO_C_J, BK_TORSO_C_F, Z_T2, Z_T3
	rep #$30
	lda.b Z_HIX
	clc
	adc.b Z_RX
	sta.b Z_HIX
	lda.b Z_HIY
	clc
	adc.b Z_RY
	sta.b Z_HIY
	lda.b Z_SHX
	clc
	adc.b Z_RX
	sta.b Z_SHX
	lda.b Z_SHY
	clc
	adc.b Z_RY
	sta.b Z_SHY
	lda.b Z_T2
	clc
	adc.b Z_RX
	sta P_CX+2*9
	lda.b Z_T3
	clc
	adc.b Z_RY
	sta P_CY+2*9
	jsr bk_hand
	jsr bk_knee
	jsr bk_elbow
	; Rods: thigh (knee -> hip), leg (foot -> knee), upper arm (elbow ->
	; shoulder), forearm (hand -> elbow).
	rep #$30
	lda.b Z_KNX
	sta.b Z_T0
	lda.b Z_KNY
	sta.b Z_T1
	lda.b Z_HIX
	sta.b Z_T2
	lda.b Z_HIY
	sta.b Z_T3
	sep #$20
	lda.b #BK_C_THIGH
	sta.b Z_B
	rep #$20
	ldx.b Z_TR
	ldy.w #2*0
	jsr bk_rod
	lda.b Z_FOX
	sta.b Z_T0
	lda.b Z_FOY
	sta.b Z_T1
	lda.b Z_KNX
	sta.b Z_T2
	lda.b Z_KNY
	sta.b Z_T3
	sep #$20
	lda.b #BK_C_LEG
	sta.b Z_B
	rep #$20
	ldx.b Z_TR
	ldy.w #2*1
	jsr bk_rod
	lda.b Z_ELX
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
	rep #$20
	lda.b Z_TR
	eor #1
	tax
	ldy.w #2*2
	jsr bk_rod
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
	rep #$20
	ldx.b Z_TR
	ldy.w #2*3
	jsr bk_rod
	jsr bk_susp
	; Torso, head, body: at the angle of the bike.
	rep #$30
	lda.b Z_TR
	sta P_H+2*9
	sta P_H+2*8
	sta P_H+2*FRAME
	beq +
	lda.b Z_TH
	clc
	adc.w #($8000-BK_TORSO_BETA) & $FFFF
	sta P_AL+2*9
	lda.b Z_TH
	eor #$8000
	bra ++
+	lda.b Z_TH
	clc
	adc.w #BK_TORSO_BETA
	sta P_AL+2*9
	lda.b Z_TH
++	sta P_AL+2*8
	sta P_AL+2*FRAME
	lda.b Z_HDX
	sta P_CX+2*8
	lda.b Z_HDY
	sta P_CY+2*8
	stz P_CX+2*FRAME
	stz P_CY+2*FRAME
	rts

; A (8 bits) = -A, -128 -> 127.
_neg8:
	cmp.b #$80
	bne +
	lda.b #$81
+	eor.b #$FF
	inc a
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
; Z_T3 = 4 * (vx * sg), sg = -1 when turned.
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

; The knee: the middle of foot -> hip, b * (the side) from it.
bk_knee:
	rep #$30
	lda.b Z_HIX
	sec
	sbc.b Z_FOX
	sta.b Z_VX
	lda.b Z_HIY
	sec
	sbc.b Z_FOY
	sta.b Z_VY
	jsr bk_d4
	lsr a
	lsr a
	lsr a
	cmp #1024
	bcc +
	lda #1023
+	tax
	sep #$20
	lda.l bike_t_knee_b,x
	sta.b Z_B
	jsr bk_side
	lda.b Z_T2
	MA
	lda.b Z_B
	MB
	sta.b Z_T0
	lda.b Z_VX
	ASR
	clc
	adc.b Z_T0
	clc
	adc.b Z_FOX
	sta.b Z_KNX
	lda.b Z_T3
	MA
	lda.b Z_B
	MB
	sta.b Z_T0
	lda.b Z_VY
	ASR
	clc
	adc.b Z_T0
	clc
	adc.b Z_FOY
	sta.b Z_KNY
	rts

; The elbow: shoulder + a * (hand - shoulder) + b * (the side).
bk_elbow:
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
	lsr a
	lsr a
	lsr a
	cmp #1024
	bcc +
	lda #1023
+	tax
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
	rts

;---------------------------------------------------------------------------
; The suspensions, two pieces each: front from the front wheel to the
; handlebar, rear from the rear point to the rear wheel.
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
	ldy.w #2*4
	ldx #0
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
++	ldy.w #2*6
	ldx #2048
; a = (Z_T0, Z_T1), b = (Z_T2, Z_T3), Y = 2 * the first piece, X = offset
; of the tables of the pieces (bike_t_s1a, s1b, s2a, s2b follow each other).
_pieces:
	stx.b Z_T4
	lda.b Z_T2
	sec
	sbc.b Z_T0
	sta.b Z_VX
	lda.b Z_T3
	sec
	sbc.b Z_T1
	sta.b Z_VY
	jsr bk_d4
	lsr a
	lsr a
	lsr a
	lsr a
	cmp #1024
	bcc +
	lda #1023
+	clc
	adc.b Z_T4
	tax
	sep #$20
	lda.l bike_t_s1a,x
	sta.b Z_A
	lda.l bike_t_s1a+1024,x
	sta.b Z_B
	MUL2 Z_VX, Z_A
	clc
	adc.b Z_T0
	sta P_CX,y
	MUL2 Z_VY, Z_A
	clc
	adc.b Z_T1
	sta P_CY,y
	MUL2 Z_VX, Z_B
	clc
	adc.b Z_T2
	sta P_CX+2,y
	MUL2 Z_VY, Z_B
	clc
	adc.b Z_T3
	sta P_CY+2,y
	jsr bk_atan2
	sta P_AL,y
	sta P_AL+2,y
	lda #0
	sta P_H,y
	sta P_H+2,y
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
	sta.b Z_F
	lda.l bike_t_turn_lv,x
	rep #$20
	and #$00FF
	sta.b Z_LV
	stz.b Z_NEG
	lda.b Z_F
	and #$0080
	beq +
	inc.b Z_NEG
+	lda.b Z_TR
	eor.b Z_NEG
	sta.b Z_TEFF
	; The front wheel (0) on top: f > 0 not turned, or f <= 0 turned.
	lda.b Z_F
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
	; Squash the centers of the parts 0-9 (around the center of the bike):
	; t = p . j, p += (t * f - t) * j.
	ldy #0
_sq:
	rep #$20
	lda P_CX,y
	asl a
	MA
	lda.b Z_C
	MB
	sta.b Z_T0
	lda P_CY,y
	asl a
	MA
	lda.b Z_S
	MB
	clc
	adc.b Z_T0
	sta.b Z_T0                  ; t
	asl a
	MA
	lda.b Z_F
	MB
	sec
	sbc.b Z_T0
	asl a                       ; 2 (t f - t)
	MA
	lda.b Z_C
	MB
	clc
	adc P_CX,y
	sta P_CX,y
	sep #$20
	lda.b Z_S
	MB
	clc
	adc P_CY,y
	sta P_CY,y
	iny
	iny
	cpy.w #2*FRAME
	bcs +
	jmp _sq
+
	; Pictures: not squashed (mirrored if f < 0) or squashed.
	ldy #0
_pic:
	lda.b Z_LV
	cmp #4
	bne _sqp
	lda.b Z_NEG
	beq _next
	lda.b Z_TH
	asl a
	clc
	adc #$8000
	sec
	sbc P_AL,y
	sta P_AL,y
	lda P_H,y
	eor #1
	sta P_H,y
	bra _next
_sqp:
	lda.b Z_TEFF
	sta P_H,y
	beq +
	lda.b Z_TH
	eor #$8000
	bra ++
+	lda.b Z_TH
++	sta P_AL,y
_next:
	iny
	iny
	cpy.w #2*11
	bcc _pic
	rts

;---------------------------------------------------------------------------
; The picture of an angle: Z_T0 = alpha, Z_T1 = mirrored; A = the stored
; picture, Z_T2 = its flips (gen_bike.py).
bk_lk32:
	lda.b Z_T0
	clc
	adc #1024
	xba
	and #$00FF
	lsr a
	lsr a
	lsr a
	ldx #16
	bra bk_lk
bk_lk64:
	lda.b Z_T0
	clc
	adc #512
	xba
	and #$00FF
	lsr a
	lsr a
	ldx #32
	bra bk_lk
bk_lk128:
	lda.b Z_T0
	clc
	adc #256
	xba
	and #$00FF
	lsr a
	ldx #64
bk_lk:
	stx.b Z_LKHALF
	ldx.b Z_T1
	bne _m
	cmp.b Z_LKHALF
	bcc +
	sbc.b Z_LKHALF
	ldx #$C0
	stx.b Z_T2
	rts
+	stz.b Z_T2
	rts
_m:
	eor #$FFFF
	inc a
	pha
	lda.b Z_LKHALF
	asl a
	dec a
	sta.b Z_LKMASK
	pla
	and.b Z_LKMASK
	cmp.b Z_LKHALF
	bcc +
	sbc.b Z_LKHALF
	ldx #$40
	stx.b Z_T2
	rts
+	ldx #$80
	stx.b Z_T2
	rts

;---------------------------------------------------------------------------
; The pictures wanted (W_DESC, W_FLIP).
bk_pictures:
	rep #$30
	ldy #0
_part:
	lda P_AL,y
	sta.b Z_T0
	lda P_H,y
	sta.b Z_T1
	lda.b Z_LV
	cmp #4
	beq _normal
	cpy.w #2*FRAME
	beq _tframe
	jsr bk_lk32
	clc
	adc.w #BK_N_PART_HALF
	sta.b Z_T3
	lda.b Z_LV
	asl a
	asl a
	asl a
	asl a                       ; lv * 16
	clc
	adc.b Z_T3
	bra _single
_tframe:
	jsr bk_lk64
	sta.b Z_T3
	lda.b Z_LV
	xba
	lsr a
	lsr a
	lsr a                       ; lv * 32
	clc
	adc.b Z_T3
	clc
	adc.w #2*BK_N_FRAME_HALF/2    ; + 64
	bra _frame
_normal:
	cpy.w #2*FRAME
	beq _nframe
	jsr bk_lk64
_single:
	tyx
	clc
	adc.l bk_base,x
	asl a
	asl a
	clc
	adc.w #bike_desc_single
	bra _store
_nframe:
	jsr bk_lk128
_frame:
	asl a
	asl a
	asl a
	asl a
	asl a
	clc
	adc.w #bike_desc_frame
_store:
	sta W_DESC,y
	lda.b Z_T2
	sta W_FLIP,y
	iny
	iny
	cpy.w #2*11
	bcc _part
	rts

;---------------------------------------------------------------------------
; Loading the pictures that changed, within the budget.
bk_load:
	rep #$30
	; The flips of the parts whose picture stays:
	ldy #0
-	lda W_DESC,y
	cmp bike_cur,y
	bne +
	lda W_FLIP,y
	sta bike_curf,y
+	iny
	iny
	cpy.w #2*11
	bcc -
	stz.b Z_ACC
	lda #$FFFF
	sta bike_rlo
	sta bike_rlo+2
	; Room in the queue for 4 transfers:
	lda core_dmaq_n
	cmp.w #(DMAQ_MAX-4)*8+1
	bcc +
	rts
+	lda.w #BUDGET
	sta.b Z_LEFT
	lda bike_toggle
	pha
	eor #1
	sta bike_toggle
	pla
	pha
	jsr bk_pair
	pla
	eor #1
	jsr bk_pair
	lda.b Z_ACC
	bne +
	rts
+	; Copy the pictures into the copy of the rows: DMA channel 7 into the
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
	ldy #0
_stage:
	tyx
	lda.l bk_bit,x
	and.b Z_ACC
	beq _skip
	lda W_DESC,y
	sta bike_cur,y
	sta.b Z_PTR
	lda W_FLIP,y
	sta bike_curf,y
	lda.l bk_dst,x
	clc
	adc.w #bike_stage
	sta.b Z_DST
	cpy.w #2*FRAME
	beq _fr
	phy
	ldy #0
	jsr bk_stage_sprite
	ply
	bra _skip
_fr:
	phy
	lda [Z_PTR]
	and #$00FF
	sta.b Z_NS
	ldy #1
-	iny
	iny
	jsr bk_stage_sprite
	lda.b Z_DST
	clc
	adc #64
	sta.b Z_DST
	iny
	iny
	iny
	dec.b Z_NS
	bne -
	ply
_skip:
	iny
	iny
	cpy.w #2*11
	bcc _stage
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
	and #$00FF
	sta.b Z_SRC+2
	lda.b Z_DST
	jsr _half
	lda.b Z_SRC
	clc
	adc #64
	sta.b Z_SRC
	lda.b Z_DST
	clc
	adc #512
_half:
	sta $2181
	lda.b Z_SRC
	sta $4372
	sep #$20
	lda.b Z_SRC+2
	sta $4374
	rep #$20
	lda #64
	sta $4375
	sep #$20
	lda #$80
	sta $420B
	rep #$20
	rts

; One pair of rows (A): the parts that changed, in the order of their
; slots, while the range fits the budget.
bk_pair:
	sta.b Z_PAIR
	lda #$FFFF
	sta.b Z_LO
	ldx #0
	lda.b Z_PAIR
	beq +
	ldx.w #2*8
+
_p:
	lda.l bk_pair_part,x
	tay
	lda W_DESC,y
	cmp bike_cur,y
	beq _pn
	lda #1
	sta.b Z_NS
	cpy.w #2*FRAME
	bne +
	sta.b Z_PTR+2               ; any bank with the descriptors
	lda W_DESC,y
	sta.b Z_PTR
	sep #$20
	lda.b #:bike_desc_frame
	sta.b Z_PTR+2
	rep #$20
	lda [Z_PTR]
	and #$00FF
	sta.b Z_NS
+	lda.l bk_pair_slot,x
	sta.b Z_T4                  ; s0
	clc
	adc.b Z_NS
	dec a
	sta.b Z_T5                  ; s1
	lda.b Z_LO
	cmp #$FFFF
	bne +
	lda.b Z_T4
+	sta.b Z_T3                  ; new lo
	lda.b Z_T5
	sec
	sbc.b Z_T3
	inc a
	xba
	lsr a                       ; * 128
	cmp.b Z_LEFT
	beq +
	bcs _pdone
+	lda.b Z_T3
	sta.b Z_LO
	lda.b Z_T5
	sta.b Z_HI
	phx
	tyx
	lda.l bk_bit,x
	plx
	ora.b Z_ACC
	sta.b Z_ACC
_pn:
	inx
	inx
	lda.b Z_PAIR
	bne +
	cpx.w #2*8
	bcc _p
	bra _pdone
+	cpx.w #2*11
	bcc _p
_pdone:
	lda.b Z_LO
	cmp #$FFFF
	bne +
	rts
+	lda.b Z_PAIR
	asl a
	tax
	lda.b Z_LO
	sta bike_rlo,x
	lda.b Z_HI
	sta bike_rhi,x
	sec
	sbc.b Z_LO
	inc a
	xba
	lsr a
	eor #$FFFF
	sec
	adc.b Z_LEFT
	sta.b Z_LEFT
	rts

;---------------------------------------------------------------------------
; The sprites of the bike: OAM 32-63.
bk_oam:
	rep #$30
	lda.w #OAM_BIKE*4
	sta.b Z_OX
	stz.b Z_N
	lda #32
	sta.b Z_NMAX
	lda.w #OAM_BIKE
	sta.b Z_HB
	stz core_oam+512+OAM_BIKE/4
	stz core_oam+512+OAM_BIKE/4+2
	stz core_oam+512+OAM_BIKE/4+4
	stz core_oam+512+OAM_BIKE/4+6
	lda.w #:bike_desc_single
	sta.b Z_PTR+2
	lda.b Z_LATE
	bmi +
	jsr bk_wheel
+	ldx #0
-	lda.l bk_order,x
	tay
	phx
	jsr bk_part
	plx
	inx
	inx
	cpx.w #2*11
	bcc -
	lda.b Z_LATE
	bpl +
	lda #1
	jsr bk_wheel
	lda #0
	jsr bk_wheel
	bra ++
+	eor #1
	jsr bk_wheel
++	ldx.b Z_OX
-	cpx.w #OAM_OBJ*4
	bcs +
	lda #$E000                  ; y 224
	sta core_oam,x
	inx
	inx
	inx
	inx
	bra -
+	rts

; A wheel (A = 0, 1).
bk_wheel:
	rep #$30
	asl a
	tay
	asl a
	tax
	lda.b Z_BSX
	clc
	adc.b Z_W0X,x
	jsr _pivot
	sta.b Z_PX
	lda.b Z_BSY
	sec
	sbc.b Z_W0Y,x
	jsr _pivot
	sta.b Z_PY
	tyx
	lda.l phys_view+PV_WHEEL_A,x
	clc
	adc #512
	xba
	and #$00FF
	lsr a
	lsr a                       ; q
	ldx.w #PRIO
	cmp #32
	bcc +
	sbc #32
	ldx.w #PRIO|$C0
+	stx.b Z_ATTR
	pha
	and #$0007
	asl a
	sta.b Z_TILE
	pla
	and #$0018
	asl a
	asl a
	clc
	adc.b Z_TILE
	sta.b Z_TILE                ; (k >> 3) * 32 + (k & 7) * 2
	lda #$FFF8
	sta.b Z_T0
	sta.b Z_T1
	jmp bk_sprite

; (A + 8) >> 4, keeping the sign.
_pivot:
	clc
	adc #8
	ASR
	ASR
	ASR
	ASR
	rts

; A part (Y = 2 * part) with its picture in the VRAM.
bk_part:
	lda bike_cur,y
	bne +
	rts
+	sta.b Z_PTR
	lda.b Z_BSX
	clc
	adc P_CX,y
	jsr _pivot
	sta.b Z_PX
	lda.b Z_BSY
	sec
	sbc P_CY,y
	jsr _pivot
	sta.b Z_PY
	tyx
	lda bike_curf,y
	ora.l bk_attr,x
	sta.b Z_ATTR
	lda.l bk_tile,x
	sta.b Z_TILE
	cpy.w #2*FRAME
	beq +
	lda #$FFF8
	sta.b Z_T0
	sta.b Z_T1
	jmp bk_sprite
+	phy
	lda [Z_PTR]
	and #$00FF
	sta.b Z_NS
	ldy #1
-	lda [Z_PTR],y
	and #$00FF
	cmp #$0080
	bcc +
	ora #$FF00
+	sta.b Z_T0
	iny
	lda [Z_PTR],y
	and #$00FF
	cmp #$0080
	bcc +
	ora #$FF00
+	sta.b Z_T1
	iny
	iny
	iny
	iny
	phy
	jsr bk_sprite
	ply
	lda.b Z_TILE
	clc
	adc #2
	sta.b Z_TILE
	dec.b Z_NS
	bne -
	ply
	rts

; A 16x16 sprite: pivot (Z_PX, Z_PY), its corner from the pivot unflipped
; (Z_T0, Z_T1), tile Z_TILE, attributes Z_ATTR (flips). Into core_oam at
; Z_OX unless off the screen or Z_NMAX sprites written. Keeps Y.
bk_sprite:
	rep #$30
	lda.b Z_ATTR
	bit #$40
	beq +
	lda #$FFF0
	sec
	sbc.b Z_T0
	sta.b Z_T0
	lda.b Z_ATTR
+	bit #$80
	beq +
	lda #$FFF0
	sec
	sbc.b Z_T1
	sta.b Z_T1
+	lda.b Z_PX
	clc
	adc.b Z_T0
	sta.b Z_T0
	clc
	adc #15
	cmp #271
	bcs _off
	lda.b Z_PY
	clc
	adc.b Z_T1
	sta.b Z_T1
	clc
	adc #15
	cmp #239
	bcs _off
	lda.b Z_N
	cmp.b Z_NMAX
	bcs _off
	ldx.b Z_OX
	sep #$20
	lda.b Z_T0
	sta core_oam,x
	lda.b Z_T1
	sta core_oam+1,x
	lda.b Z_TILE
	sta core_oam+2,x
	lda.b Z_ATTR
	sta core_oam+3,x
	rep #$20
	lda.b Z_T0
	bpl +
	lda.b Z_N
	clc
	adc.b Z_HB
	pha
	and #$0003
	tax
	sep #$20
	lda.l bk_hb,x
	sta.b Z_T0
	rep #$20
	pla
	lsr a
	lsr a
	tax
	sep #$20
	lda.b Z_T0
	ora core_oam+512,x
	sta core_oam+512,x
	rep #$20
+	lda.b Z_OX
	clc
	adc #4
	sta.b Z_OX
	inc.b Z_N
_off:
	rts

.ENDS
