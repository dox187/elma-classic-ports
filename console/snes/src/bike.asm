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
Z_LEFT      dw          ; the time of the vertical blank left (bytes)
Z_ENT       dw          ; entries of the queue left
Z_PEND      dw          ; bit p: part p wants another picture
Z_PTR       dsb 4       ; a long pointer
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
bike_toggle dw          ; which group of parts loads first
bike_oam_end dw         ; end of the sprites written in the last frame
bike_pend   dw          ; bit p: part p wants a picture not in the VRAM
bike_key    dsw 11      ; the step of the angle and the mirroring of the
                        ; picture of each part in the last frame
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

; The step of the angle of a single part at 64 angles and its mirroring
; (\1 = 2 * part): its picture when they changed since the last frame
; (\2: bk_pic64 or bk_pic64s).
.MACRO PIC64
	lda P_AL+\1
	clc
	adc.w #512
	xba
	and.w #$00FF
	lsr a
	lsr a
	ora P_H+\1
	cmp bike_key+\1
	beq +
	ldy.w #\1
	jsr \2
+
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

; For each part: its bit, its first descriptor (of a single part), its
; first tile with its palette and priority.
bk_bit:
	.dw 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024
bk_desc0:
	.dw bike_desc_single, bike_desc_single+4*BK_PER_PART
	.dw bike_desc_single+8*BK_PER_PART, bike_desc_single+12*BK_PER_PART
	.dw bike_desc_single+16*BK_PER_PART, bike_desc_single+20*BK_PER_PART
	.dw bike_desc_single+24*BK_PER_PART, bike_desc_single+28*BK_PER_PART
	.dw bike_desc_single+32*BK_PER_PART, bike_desc_single+36*BK_PER_PART
bk_ta0:
	.dw 128|(BK_PAL_THIGH*2|PRIO)<<8, 130|(BK_PAL_LEG*2|PRIO)<<8
	.dw 132|(BK_PAL_UPARM*2|PRIO)<<8, 134|(BK_PAL_FOREARM*2|PRIO)<<8
	.dw 136|(BK_PAL_S1A*2|PRIO)<<8, 138|(BK_PAL_S1B*2|PRIO)<<8
	.dw 140|(BK_PAL_S2A*2|PRIO)<<8, 142|(BK_PAL_S2B*2|PRIO)<<8
	.dw 160|(BK_PAL_HEAD*2|PRIO)<<8, 162|(BK_PAL_TORSO*2|PRIO)<<8
	.dw 164|(BK_PAL_FRAME*2|PRIO)<<8
; The bit of x >= 256 of a sprite in the high table:
bk_hb:
	.db 1, 4, 16, 64

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
	sta bike_key,x
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
	sta bike_pend
	ldx.w #OAM_BIKE*4           ; the sprites hidden
	stx bike_oam_end
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
; bike_t_lk32/64/128 (k | flips << 8, gen_bike.py). Only for the parts
; whose step or mirroring changed (bike_key): a part whose picture is not
; in the VRAM is pending (bike_pend), else its flips are taken.
bk_pictures:
	rep #$30
	lda.b Z_LV
	cmp #4
	beq +
	jmp bk_tpictures
+	PIC64 2*0, bk_pic64
	PIC64 2*1, bk_pic64
	PIC64 2*2, bk_pic64
	PIC64 2*3, bk_pic64
	PIC64 2*4, bk_pic64s        ; the pieces of a suspension: the same angle
	PIC64 2*6, bk_pic64s
	PIC64 2*8, bk_pic64
	PIC64 2*9, bk_pic64
	lda P_AL+2*FRAME            ; the body: 128 steps
	clc
	adc.w #256
	xba
	and.w #$00FF
	lsr a
	ora P_H+2*FRAME
	cmp bike_key+2*FRAME
	bne +
	rts
+	sta bike_key+2*FRAME
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

; Part Y/2 at the step and mirroring A (its key): its picture from
; bike_t_lk64.
bk_pic64:
	sta bike_key,y
	asl a
	tax
	lda.l bike_t_lk64,x
	sta W_KF,y
	and.w #$00FF
	asl a
	asl a
	tyx
	adc.l bk_desc0,x            ; (C clear)
	sta W_DESC,y
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
	cmp bike_curf,y
	beq +
	sta bike_curf,y
	ora.l bk_ta0,x
	sta bike_ta,y
+	rts

; The same for the first piece of a suspension (Y/2) and the second one.
bk_pic64s:
	jsr bk_pic64
	lda bike_key,y
	sta bike_key+2,y
	lda W_KF,y
	sta W_KF+2,y
	lda W_DESC,y
	clc
	adc.w #4*BK_PER_PART
	sta W_DESC+2,y
	iny
	iny
	bra bk_check

; The squashed pictures: all at the angle of the bike as drawn. The parts
; 0-9 share their key ((level + 1) << 8 | step).
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
	cmp bike_key
	beq _tframe
	sta.b Z_T2                  ; the key
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
-	lda.b Z_T2
	sta bike_key,y
	lda.b Z_T3
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
	cmp bike_key+2*FRAME
	bne +
	rts
+	sta bike_key+2*FRAME
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
	lda.w #(DMAQ_MAX-OBJ_ROOM)*8
	sec
	sbc core_dmaq_n
	bcs +
	rts
+	lsr a
	lsr a
	lsr a
	sta.b Z_ENT                 ; entries of the queue left
	lda.w #LOAD_COST
	sta.b Z_LEFT
	sep #$20
	lda.b #:bike_desc_single    ; (the body's descriptors too)
	sta.b Z_PTR+2
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
	lda.w #8*128+2*ENTRY_COST
	jsr bk_cost
	bcc _r0
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
	ldy #0                      ; 2 * part
-	lsr.b Z_T5
	bcc +
	lda.w #128+2*ENTRY_COST
	jsr bk_cost
	bcc _r0
	jsr bk_load1
+	iny
	iny
	lda.b Z_T5
	bne -
_r0:
	rts

; The head, the torso, the body.
_group1:
	lda.b Z_PEND
	and #$0100
	beq +
	lda.w #128+2*ENTRY_COST
	jsr bk_cost
	bcc _r0
	ldy.w #2*8
	jsr bk_load1
+	lda.b Z_PEND
	and #$0200
	beq +
	lda.w #128+2*ENTRY_COST
	jsr bk_cost
	bcc _r0
	ldy.w #2*9
	jsr bk_load1
+	lda.b Z_PEND
	and #$0400
	beq _r0
	jsr bk_nframe
	dec a                       ; its sprites
	xba
	lsr a
	sta.b Z_T2                  ; * 128
	clc
	adc.w #2*ENTRY_COST
	jsr bk_cost
	bcc _r0
	lsr.b Z_T2                  ; the bytes of a row
	ldx.w #2*FRAME
	txy
	jsr bk_take
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

; A load that takes A of the vertical blank and two entries of the queue:
; C set if it fits (and they are taken), else C clear. Keeps Y.
bk_cost:
	ldx.b Z_ENT
	cpx #2
	bcc +
	sta.b Z_T3
	lda.b Z_LEFT
	sec
	sbc.b Z_T3
	bcc +
	sta.b Z_LEFT
	dex
	dex
	stx.b Z_ENT
+	rts

; Part Y/2 (a single sprite) gets its wanted picture and loads it. Keeps Y.
bk_load1:
	tyx
	jsr bk_take
	lda.l bk_ta0,x
	and #$00FF                  ; its first tile
	asl a
	asl a
	asl a
	asl a
	adc.w #VRAM_OBJ
	sta.b Z_DST
	lda [Z_PTR]
	sta.b Z_T0
	phy
	ldy #2
	lda [Z_PTR],y
	ply
	and #$00FF
	sta.b Z_T1
	lda #64
	sta.b Z_T2

; Two transfers of the queue: Z_T2 bytes from Z_T1:Z_T0 to the VRAM at
; Z_DST (words), the next Z_T2 bytes 16 tiles further. Keeps Y.
bk_qrows:
	ldx core_dmaq_n
	lda.b Z_T0
	sta core_dmaq+1,x           ; type +0, source +1, bank +3, size +4,
	clc                         ; VRAM address +6
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
	lda.b #DMAQ_VRAM
	sta core_dmaq,x
	sta core_dmaq+8,x
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
	sta bike_curf,y
	ora.l bk_ta0,x
	sta bike_ta,y
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
