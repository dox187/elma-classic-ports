; The physics of the bike and the objects of a level, after LEPTET.CPP,
; BEALLIT.CPP, UTKOZES.CPP, UTKOZES2.CPP and the object handling of
; LEJATSZO.CPP of the original game, in fixed point. test/phys_spec.c
; describes it to the bit (the comments name its functions); phys.inc has
; the units, the direct pages and the arithmetic.
;
; C calls phys_level, phys_step and phys_turn with 16-bit registers and the
; data bank $7E; they save D and the data bank and use their own.

.include "hdr.asm"
.include "core.inc"
.include "phys.inc"

.BASE $00
.RAMSECTION ".phys_objs" BANK $7E SLOT 2
phys_objs           dsb 52*12   ; phys_obj_t of the level
.ENDS
.BASE $80

.RAMSECTION ".phys_dpa" BANK 0 SLOT 1 ALIGN 256
phys_dpa            dsb 256     ; the direct page of the step (PHYS_DPA)
.ENDS

.RAMSECTION ".phys_dpb" BANK 0 SLOT 1 ALIGN 256
phys_dpb            dsb 256     ; the direct page of the collisions
.ENDS

.RAMSECTION ".phys_vars" BANK 0 SLOT 1
phys_view           dsb 52      ; bike_view_t
phys_nobjs          dw
phys_apples_left    dw
phys_eaten          dw
phys_bump           dw
phys_wheel_omega    dw
phys_friction       dw
phys_volt_age       db
phys_volt1          db
; The level:
lev_addr            dw          ; its data in its bank
lev_bank            dw
lev_gx              dsb 4       ; corner of the grid (P)
lev_gy              dsb 4
lev_gw              dsb 4       ; size of the grid (P)
lev_gh              dsb 4
lev_racsx           dsb 4       ; Racsonkivul from here (P)
lev_racsy           dsb 4
lev_kill            dsb 16      ; the body dies outside (x0, x1, y0, y1)
lev_rows            dw          ; the rows of the grid
lev_need            dw          ; apples needed
; Temporaries of the step:
pt_m                dsb 8       ; torques of the wheels (T)
pt_dx               dsb 8       ; forces on the wheels (V)
pt_dy               dsb 8
pt_gsx              dsb 8       ; anchors of the wheels (P)
pt_gsy              dsb 8
pt_crs              dsb 4       ; sums of the torques on the body
pt_crd              dsb 4
pt_da               dsb 12      ; changes of the angles: body, kor2, kor4
pt_fric             dsb 4
pt_oldw             dsb 4
pt_volt             dw          ; bit 0 volt1, bit 1 volt2 of the step
pt_brake            dw
pt_k                dw          ; 0 or 1: the wheel
pt_tmp              dsb 16
.ENDS

.DEFINE PHYS_DPA phys_dpa
.DEFINE PHYS_DPB phys_dpb

; Offsets of the data of a level (tools/gen_phys.py):
.DEFINE LH_GX 0
.DEFINE LH_GY 4
.DEFINE LH_GW 8
.DEFINE LH_GH 10
.DEFINE LH_NOBJS 14
.DEFINE LH_OBJS 18
.DEFINE LH_ROWS 22
.DEFINE LH_RACS 24
.DEFINE LH_KILL 32
.DEFINE LH_BIKE 48
.DEFINE LH_NEED 80

.SECTION ".phys_text" SUPERFREE

;---------------------------------------------------------------------------
; Helpers (A 16-bit, the direct page of the caller).

; Clamps the double word of the direct page at X into [-$808080, $7F7F7F].
phys_clamp24:
	.ACCU 16
	.INDEX 16
	lda.b 2,x
	bmi _c24neg
	cmp #$007F
	bcc _c24ok
	bne _c24hi
	lda.b 0,x
	cmp #$7F80
	bcc _c24ok
_c24hi:
	lda #$7F7F
	sta.b 0,x
	lda #$007F
	sta.b 2,x
	rts
_c24neg:
	cmp #$FF7F
	beq _c24eq
	bcs _c24ok
	bra _c24lo
_c24eq:
	lda.b 0,x
	cmp #$7F80
	bcs _c24ok
_c24lo:
	lda #$7F80
	sta.b 0,x
	lda #$FF7F
	sta.b 2,x
_c24ok:
	rts

; A = clamp16( the double word of the direct page at X ): [-32640, 32639].
phys_clamp16:
	.ACCU 16
	.INDEX 16
	lda.b 2,x
	bmi _c16neg
	bne _c16hi
	lda.b 0,x
	cmp #32640
	bcc _c16ok
_c16hi:
	lda #32639
	rts
_c16neg:
	cmp #$FFFF
	bne _c16lo
	lda.b 0,x
	cmp #$8080
	bcs _c16ok
_c16lo:
	lda #$8080
	rts
_c16ok:
	lda.b 0,x
	rts

; A = q15( the double word at X ) = it >> 7, within [-32767, 32767].
phys_q15:
	.ACCU 16
	.INDEX 16
	lda.b 0,x
	xba
	asl a                       ; C = bit 7
	lda.b 1,x
	rol a
	ldy.b 2,x
	bmi _q15neg
	cmp #$8000
	bcc _q15ok
	lda #32767
	rts
_q15neg:
	cmp #$8000
	bne _q15ok
	lda #$8001
_q15ok:
	rts

; R = qsin( T1 ): sin of T1 (W, 0 to pi/2), Q22.
phys_qsinf:
	.ACCU 16
	.INDEX 16
	lda.b T1+2
	lsr a
	lsr a
	lsr a
	sta.b T2
	asl a
	clc
	adc.b T2
	pha                         ; 3i: the value
	lda.b T2
	asl a
	tax                         ; 2i: the step to the next
	lda.l phys_qsind,x
	sta.b T2+2
	lda.b T1
	lsr a
	lsr a
	lsr a
	lsr a
	sta.b T2
	lda.b T1+1
	and #$0700
	asl a
	asl a
	asl a
	asl a
	ora.b T2
	sta.b T2                    ; f = (b >> 4) & $7FFF
	sep #$20
	MB_DP T2
	DIG16 T2+2
	RSET16 MD0
	RFIN 7, $808000
	plx
	lda.l phys_qsin,x
	clc
	adc.b R
	sta.b R
	lda.l phys_qsin+2,x
	and #$00FF
	adc.b R+2
	sta.b R+2
	rts

; trig: CS22, SN22, CS, SN of the angle of the body.
phys_trig:
	.ACCU 16
	.INDEX 16
	lda.b S_BODY+C_A+2
	bpl +
	lda #0
	sec
	sbc.b S_BODY+C_A
	sta.b T0
	lda #0
	sbc.b S_BODY+C_A+2
	sta.b T0+2
	bra ++
+	sta.b T0+2
	lda.b S_BODY+C_A
	sta.b T0
++	; sin: qsin( b > pi/2 ? pi-b : b ), negative with a:
	lda #HALFPI_W & $FFFF
	cmp.b T0
	lda #HALFPI_W >> 16
	sbc.b T0+2                  ; C clear: b > pi/2
	bcs +
	lda #PI_W & $FFFF
	sec
	sbc.b T0
	sta.b T1
	lda #PI_W >> 16
	sbc.b T0+2
	sta.b T1+2
	bra ++
+	lda.b T0
	sta.b T1
	lda.b T0+2
	sta.b T1+2
++	jsr phys_qsinf
	lda.b S_BODY+C_A+2
	bpl +
	lda #0
	sec
	sbc.b R
	sta.b SN22
	lda #0
	sbc.b R+2
	sta.b SN22+2
	bra ++
+	lda.b R
	sta.b SN22
	lda.b R+2
	sta.b SN22+2
++	; cos: b > pi/2 ? -qsin( b-pi/2 ) : qsin( pi/2-b ):
	lda #HALFPI_W & $FFFF
	cmp.b T0
	lda #HALFPI_W >> 16
	sbc.b T0+2
	bcs _trig_c1
	lda.b T0
	sec
	sbc #HALFPI_W & $FFFF
	sta.b T1
	lda.b T0+2
	sbc #HALFPI_W >> 16
	sta.b T1+2
	jsr phys_qsinf
	lda #0
	sec
	sbc.b R
	sta.b CS22
	lda #0
	sbc.b R+2
	sta.b CS22+2
	bra _trig_q
_trig_c1:
	lda #HALFPI_W & $FFFF
	sec
	sbc.b T0
	sta.b T1
	lda #HALFPI_W >> 16
	sbc.b T0+2
	sta.b T1+2
	jsr phys_qsinf
	lda.b R
	sta.b CS22
	lda.b R+2
	sta.b CS22+2
_trig_q:
	ldx #SN22
	jsr phys_q15
	sta.b SN
	ldx #CS22
	jsr phys_q15
	sta.b CS
	rts

; szamitfejr: the head from the rider and the angle (CS, SN).
phys_head:
	.ACCU 16
	.INDEX 16
	sep #$20
	MB_DP CS
	lda.b S_TURNED
	beq +
	RSETK K09_15
	bra ++
+
	.ACCU 8
	RSETK -K09_15
++	sep #$20
	MB_DP SN
	RADDK -K63_15
	RFIN 6, 2*$808000
	ADD32 S_HEADX, S_RIDX, R
	sep #$20
	MB_DP SN
	lda.b S_TURNED
	beq +
	RSETK K09_15
	bra ++
+
	.ACCU 8
	RSETK -K09_15
++	sep #$20
	MB_DP CS
	RADDK K63_15
	RFIN 6, 2*$808000
	ADD32 S_HEADY, S_RIDY, R
	rts

; The view of the bike (phys_view) from the state; the angles as 65536 a
; turn: rsh( mq24( a >> 15, K_WVIEW ), K_WVIEW_SH-8 ).
phys_angle16:                   ; A = the angle of the circle at X
	.ACCU 16
	.INDEX 16
	lda.b C_A,x
	asl a
	lda.b C_A+2,x
	rol a                       ; a >> 15
	sta.b T0
	sep #$20
	MB_IMM K_WVIEW_M
	DIG16 T0
	RSET16 MD0
	RFIN (K_WVIEW_SH)-8, $808000
	lda.b R
	rts

phys_mkview:
	.ACCU 16
	.INDEX 16
	MOV32W phys_view+0, phys_dpa+S_BODY+C_RX
	MOV32W phys_view+4, phys_dpa+S_BODY+C_RY
	MOV32W phys_view+12, phys_dpa+S_K2+C_RX
	MOV32W phys_view+16, phys_dpa+S_K4+C_RX
	MOV32W phys_view+20, phys_dpa+S_K2+C_RY
	MOV32W phys_view+24, phys_dpa+S_K4+C_RY
	MOV32W phys_view+32, phys_dpa+S_RIDX
	MOV32W phys_view+36, phys_dpa+S_RIDY
	MOV32W phys_view+40, phys_dpa+S_HEADX
	MOV32W phys_view+44, phys_dpa+S_HEADY
	ldx #S_BODY
	jsr phys_angle16
	sta.w phys_view+8
	ldx #S_K2
	jsr phys_angle16
	sta.w phys_view+28
	ldx #S_K4
	jsr phys_angle16
	sta.w phys_view+30
	lda.b S_TURNED              ; turned, gravity
	sta.w phys_view+48
	sep #$20
	lda.b S_LASTVOLT
	sta.w phys_volt_age
	lda.b S_VOLT1
	sta.w phys_volt1
	rep #$20
	lda.b S_APPLES
	and #$00FF
	sta.b T0
	lda.w lev_need
	sec
	sbc.b T0
	sta.w phys_apples_left
	rts

; Our D and data bank, after php, phb, phd: the level's bank.
.MACRO PHYS_ENTER
	rep #$30
	pea PHYS_DPA
	pld
	sep #$20
	lda.l lev_bank
	pha
	plb
	rep #$20
.ENDM

;---------------------------------------------------------------------------
; void phys_level(u16 level)
phys_level:
	.ACCU 16
	.INDEX 16
	php
	phb
	phd
	rep #$30
	lda 8,s                     ; level
	sta.l pt_tmp
	asl a
	clc
	adc.l pt_tmp
	tax
	lda.l phys_lev_addr,x
	sta.l lev_addr
	lda.l phys_lev_addr+2,x
	and #$00FF
	sta.l lev_bank
	PHYS_ENTER
	ldx.w lev_addr
	lda.w LH_GX,x
	sta.w lev_gx
	lda.w LH_GX+2,x
	sta.w lev_gx+2
	lda.w LH_GY,x
	sta.w lev_gy
	lda.w LH_GY+2,x
	sta.w lev_gy+2
	stz.w lev_gw
	stz.w lev_gh
	lda.w LH_GW,x               ; cells of 2 m
	asl a
	sta.w lev_gw+2
	lda.w LH_GH,x
	asl a
	sta.w lev_gh+2
	lda.w LH_ROWS,x
	sta.w lev_rows
	lda.w LH_NEED,x
	sta.w lev_need
	lda.w LH_NOBJS,x
	sta.w phys_nobjs
	ldy #0
-	lda.w LH_RACS,x             ; Racsonkivul, then the kill box
	sta.w lev_racsx,y
	inx
	inx
	iny
	iny
	cpy #24
	bcc -
	; The state: zero, then the bike at the start.
	ldx #0
-	stz.b 0,x
	inx
	inx
	cpx #142
	bcc -
	ldx.w lev_addr
	ldy #0
-	lda.w LH_BIKE,x             ; kor1, kor2, kor4 positions
	sta.w phys_dpa+S_BODY,y
	lda.w LH_BIKE+2,x
	sta.w phys_dpa+S_BODY+2,y
	lda.w LH_BIKE+4,x
	sta.w phys_dpa+S_BODY+4,y
	lda.w LH_BIKE+6,x
	sta.w phys_dpa+S_BODY+6,y
	txa
	clc
	adc #8
	tax
	tya
	clc
	adc #C_SIZE
	tay
	cpy #3*C_SIZE
	bcc -
	lda.w LH_BIKE,x             ; the rider (x points after kor4)
	sta.b S_RIDX
	lda.w LH_BIKE+2,x
	sta.b S_RIDX+2
	lda.w LH_BIKE+4,x
	sta.b S_RIDY
	lda.w LH_BIKE+6,x
	sta.b S_RIDY+2
	sep #$20
	lda #1
	sta.b S_GRAVITY
	lda #255
	sta.b S_LASTVOLT
	sta.b S_VOLTT
	sta.b S_VOLTT+1
	rep #$20
	; The objects (phys_objs in bank $7E):
	ldx.w lev_addr
	lda.w LH_OBJS,x
	tay                         ; the objects of the level
	ldx #0
-	cpx.w phys_nobjs
	bcs ++
	phx
	txa
	asl a
	clc
	adc 1,s
	asl a
	asl a                       ; 12 bytes each
	tax
	lda.w 0,y                   ; type, anim
	sta.l phys_objs,x
	lda.w 2,y                   ; gravity, active: active unless the start
	and #$00FF
	sta.l phys_objs+2,x
	lda.w 0,y
	and #$00FF
	cmp #4
	beq +
	lda.l phys_objs+2,x
	ora #$0100
	sta.l phys_objs+2,x
+	lda.w 4,y
	sta.l phys_objs+4,x
	lda.w 6,y
	sta.l phys_objs+6,x
	lda.w 8,y
	sta.l phys_objs+8,x
	lda.w 10,y
	sta.l phys_objs+10,x
	tya
	clc
	adc #12
	tay
	plx
	inx
	bra -
++	stz.w phys_eaten
	stz.w phys_bump
	stz.w phys_friction
	stz.w phys_wheel_omega
	stz.b S_BODY+C_A            ; trig( 0 ), head
	stz.b S_BODY+C_A+2
	jsr phys_trig
	jsr phys_head
	jsr phys_mkview
	pld
	plb
	plp
	rtl

;---------------------------------------------------------------------------
; void phys_turn(void): hatra_f and szamitfejr (the angle of the body is
; the one trig had at the end of the last step).
phys_turn:
	.ACCU 16
	.INDEX 16
	php
	phb
	phd
	PHYS_ENTER
	sep #$20
	lda.b S_TURNED
	eor #1
	sta.b S_TURNED
	rep #$20
	jsr phys_head
	jsr phys_mkview
	pld
	plb
	plp
	rtl

;---------------------------------------------------------------------------
; Parts of the step (ps_step), A 16-bit, D = PHYS_DPA.

; M[k] of the brake: -( MULK( defl[k], K_BRK_S ) + MULK( rsh( w_k-w_body,
; 8 ), K_BRK_W ) ).
.MACRO BRAKE_TORQUE             ; \1: 0 or 1, \2: the wheel
	lda.b \2+C_W
	sec
	sbc.b S_BODY+C_W
	sta.b T0
	lda.b \2+C_W+2
	sbc.b S_BODY+C_W+2
	sta.b T0+2
	RSH32 T0, 8
	MULK S_DEFL+4*(\1), K_BRK_S
	MOV32 T1, R
	MULK T0, K_BRK_W
	lda.b T1
	clc
	adc.b R
	sta.b T1
	lda.b T1+2
	adc.b R+2
	sta.b T1+2
	lda #0
	sec
	sbc.b T1
	sta.w pt_m+4*(\1)
	lda #0
	sbc.b T1+2
	sta.w pt_m+4*(\1)+2
.ENDM

phys_torques:
	.ACCU 16
	.INDEX 16
	stz.w pt_m
	stz.w pt_m+2
	stz.w pt_m+4
	stz.w pt_m+6
	lda.b IN
	and #PH_BRAKE
	sta.w pt_brake
	beq +
	lda.b S_BRAKEWAS
	and #$00FF
	bne +
	stz.b S_DEFL
	stz.b S_DEFL+2
	stz.b S_DEFL+4
	stz.b S_DEFL+6
+	sep #$20
	lda.w pt_brake
	beq +
	lda #1
+	sta.b S_BRAKEWAS
	rep #$20
	lda.b IN
	and #PH_GAS
	beq _tq_brake
	lda.b S_TURNED
	and #$00FF
	beq _tq_gas4
	; Turned: kor2 gets -600 Nm while its omega > -110 rad/s.
	lda.b S_K2+C_W
	sec
	sbc #(-TULP_W) & $FFFF
	tax
	lda.b S_K2+C_W+2
	sbc #((-TULP_W) >> 16) & $FFFF
	bmi _tq_brake
	bne +
	cpx #0
	beq _tq_brake
+	lda #(-GAS_T) & $FFFF
	sta.w pt_m
	lda #$FFFF
	sta.w pt_m+2
	bra _tq_brake
_tq_gas4:
	; kor4 gets 600 Nm while its omega < 110 rad/s.
	lda.b S_K4+C_W
	sec
	sbc #TULP_W & $FFFF
	lda.b S_K4+C_W+2
	sbc #TULP_W >> 16
	bpl _tq_brake
	lda #GAS_T
	sta.w pt_m+4
_tq_brake:
	lda.w pt_brake
	bne +
	rts
+	BRAKE_TORQUE 0, S_K2
	BRAKE_TORQUE 1, S_K4
	rts

; The anchors of the wheels on the body (P): gsx = ( b-a, a+b ), gsy =
; ( -cc-d, cc-d ) with a = 0.85 cos, b = 0.6 sin, cc = 0.85 sin, d = 0.6 cos.
phys_anchors:
	.ACCU 16
	.INDEX 16
	sep #$20
	DIG24 CS22
	MB_IMM K85_15
	RSET24 MD0
	rep #$20
	RFIN 13, $808000
	MOV32 T0, R                 ; a
	sep #$20
	MB_IMM K60_15
	RSET24 MD0
	rep #$20
	RFIN 13, $808000
	MOV32 T1, R                 ; d
	sep #$20
	DIG24 SN22
	MB_IMM K60_15
	RSET24 MD0
	rep #$20
	RFIN 13, $808000
	MOV32 T2, R                 ; b
	sep #$20
	MB_IMM K85_15
	RSET24 MD0
	rep #$20
	RFIN 13, $808000            ; cc
	lda.b T2
	sec
	sbc.b T0
	sta.w pt_gsx
	lda.b T2+2
	sbc.b T0+2
	sta.w pt_gsx+2
	lda.b T2
	clc
	adc.b T0
	sta.w pt_gsx+4
	lda.b T2+2
	adc.b T0+2
	sta.w pt_gsx+6
	lda #0
	sec
	sbc.b R
	sta.b T3
	lda #0
	sbc.b R+2
	sta.b T3+2
	lda.b T3
	sec
	sbc.b T1
	sta.w pt_gsy
	lda.b T3+2
	sbc.b T1+2
	sta.w pt_gsy+2
	lda.b R
	sec
	sbc.b T1
	sta.w pt_gsy+4
	lda.b R+2
	sbc.b T1+2
	sta.w pt_gsy+6
	rts

; T0 = the double word at \2 of the direct page, + the one at \1,x ... the
; parts of a wheel against the body:
; \1 = (wheel field at X) - (body field), into the dp double word \2.
.MACRO WSUB
	lda.b \1,x
	sec
	sbc.b S_BODY+\1
	sta.b \2
	lda.b \1+2,x
	sbc.b S_BODY+\1+2
	sta.b \2+2
.ENDM

; erokszamitasa of the wheel CK (CK4 = 4k): pt_dx, pt_dy[k] and the sums of
; the torques on the body, the friction.
phys_erok:
	.ACCU 16
	.INDEX 16
	ldx.b CK
	ldy.b CK4
	; gumi = gs[k] + body - wheel:
	lda.w pt_gsx,y
	clc
	adc.b S_BODY+C_RX
	sta.b GX
	lda.w pt_gsx+2,y
	adc.b S_BODY+C_RX+2
	sta.b GX+2
	lda.b GX
	sec
	sbc.b C_RX,x
	sta.b GX
	lda.b GX+2
	sbc.b C_RX+2,x
	sta.b GX+2
	lda.w pt_gsy,y
	clc
	adc.b S_BODY+C_RY
	sta.b GY
	lda.w pt_gsy+2,y
	adc.b S_BODY+C_RY+2
	sta.b GY+2
	lda.b GY
	sec
	sbc.b C_RY,x
	sta.b GY
	lda.b GY+2
	sbc.b C_RY+2,x
	sta.b GY+2
	; koto = clamp16( rsh( wheel - body, 3 ) ) (2^-13 m):
	WSUB C_RX, T0
	WSUB C_RY, T1
	RSH32 T0, 3
	RSH32 T1, 3
	ldx #T0
	jsr phys_clamp16
	sta.b KX
	ldx #T1
	jsr phys_clamp16
	sta.b KY
	; korongrelv = rot90( koto ) * w1 + body.v - wheel.v:
	lda #0
	sec
	sbc.b KY
	sta.b T0                    ; -ky
	sep #$20
	MB_DP T0
	RSET24 WD
	rep #$20
	RFIN 5, $808000
	ldx.b CK
	lda.b R
	clc
	adc.b S_BODY+C_VX
	sta.b RLX
	lda.b R+2
	adc.b S_BODY+C_VX+2
	sta.b RLX+2
	lda.b RLX
	sec
	sbc.b C_VX,x
	sta.b RLX
	lda.b RLX+2
	sbc.b C_VX+2,x
	sta.b RLX+2
	sep #$20
	MB_DP KX
	RSET24 WD
	rep #$20
	RFIN 5, $808000
	ldx.b CK
	lda.b R
	clc
	adc.b S_BODY+C_VY
	sta.b RLY
	lda.b R+2
	adc.b S_BODY+C_VY+2
	sta.b RLY+2
	lda.b RLY
	sec
	sbc.b C_VY,x
	sta.b RLY
	lda.b RLY+2
	sbc.b C_VY+2,x
	sta.b RLY+2
	; The damper:
	MULK RLX, K_DAMP
	ldy.b CK4
	lda.b R
	sta.w pt_dx,y
	lda.b R+2
	sta.w pt_dx+2,y
	MULK RLY, K_DAMP
	ldy.b CK4
	lda.b R
	sta.w pt_dy,y
	lda.b R+2
	sta.w pt_dy+2,y
	; The spring, unless gumi is within 0.0001 m:
	lda.b GX
	clc
	adc #SPRING_ZERO_P
	tax
	lda.b GX+2
	adc #0
	bne _ek_spring
	cpx #2*SPRING_ZERO_P+1
	bcs _ek_spring
	lda.b GY
	clc
	adc #SPRING_ZERO_P
	tax
	lda.b GY+2
	adc #0
	bne _ek_spring
	cpx #2*SPRING_ZERO_P+1
	bcs _ek_spring
	jmp _ek_nospring
_ek_spring:
	MULK GX, K_SPRING
	ldy.b CK4
	lda.w pt_dx,y
	clc
	adc.b R
	sta.w pt_dx,y
	lda.w pt_dx+2,y
	adc.b R+2
	sta.w pt_dx+2,y
	MULK GY, K_SPRING
	ldy.b CK4
	lda.w pt_dy,y
	clc
	adc.b R
	sta.w pt_dy,y
	lda.w pt_dy+2,y
	adc.b R+2
	sta.w pt_dy+2,y
	; cross_s += mq24( gy, rsh( gsx, 2 ) )+mq24( gx, -rsh( gsy, 2 ) ):
	lda.w pt_gsx,y
	sta.b T0
	lda.w pt_gsx+2,y
	sta.b T0+2
	RSH32 T0, 2
	ldy.b CK4
	lda.w pt_gsy,y
	sta.b T1
	lda.w pt_gsy+2,y
	sta.b T1+2
	RSH32 T1, 2
	lda #0
	sec
	sbc.b T1
	sta.b T1                    ; -gs14y
	MOV32 T3, GY
	DIGT3
	MB_DP T0
	RSET24 MD0
	rep #$20
	MOV32 T3, GX
	DIGT3
	MB_DP T1
	RADD24 MD0
	rep #$20
	RFIN0 2*$808000
	lda.w pt_crs
	clc
	adc.b R
	sta.w pt_crs
	lda.w pt_crs+2
	adc.b R+2
	sta.w pt_crs+2
_ek_nospring:
	; cross_d += mq24( rely, kx )+mq24( relx, -ky ):
	MOV32 T3, RLY
	DIGT3
	MB_DP KX
	RSET24 MD0
	rep #$20
	lda #0
	sec
	sbc.b KY
	sta.b T0
	MOV32 T3, RLX
	DIGT3
	MB_DP T0
	RADD24 MD0
	rep #$20
	RFIN0 2*$808000
	lda.w pt_crd
	clc
	adc.b R
	sta.w pt_crd
	lda.w pt_crd+2
	adc.b R+2
	sta.w pt_crd+2
	; Ftestnyom, with a torque on the wheel:
	ldy.b CK4
	lda.w pt_m,y
	ora.w pt_m+2,y
	beq +
	jsr phys_ftn
+	jmp phys_fric

; Ftestnyom: the torque M[k] of the wheel pushes its axle (A 16-bit).
phys_ftn:
	.ACCU 16
	.INDEX 16
	; k2 = kx^2 + ky^2, at least 65536:
	SQUARE KX
	MOV32 T1, R
	SQUARE KY
	lda.b R
	clc
	adc.b T1
	sta.b T1
	lda.b R+2
	adc.b T1+2
	sta.b T1+2
	bne +
	stz.b T1
	inc a
	sta.b T1+2
+	; s: shifts until the top bit:
	ldx #0
	lda.b T1+2
	bmi +
-	asl.b T1
	rol a
	inx
	cmp #$0000
	bpl -
+	sta.b T1+2
	stx.b T2                    ; s
	; rc = rcp[m] + ((rcpd[m]*f + 64) >> 7), m = (X >> 24)-128, f = (X >> 17) & 127:
	xba
	and #$007F
	asl a
	tax
	lda.l phys_rcpd,x
	sta.b T0
	lda.l phys_rcp,x
	sta.b T0+2
	lda.b T1+2
	lsr a
	and #$007F
	sta.b T2+2                  ; f
	sep #$20
	MB_DP T0
	lda.b T2+2
	sta.w MPYB
	rep #$21
	lda.w MPYL
	adc #64
	cmp #$8000
	ror a
	cmp #$8000
	ror a
	cmp #$8000
	ror a
	cmp #$8000
	ror a
	cmp #$8000
	ror a
	cmp #$8000
	ror a
	cmp #$8000
	ror a
	clc
	adc.b T0+2
	sta.b T0                    ; rc
	; B = rsh( mq24( M, rc ), 8 ):
	ldy.b CK4
	lda.w pt_m,y
	sta.b T3
	lda.w pt_m+2,y
	sta.b T3+2
	DIGT3
	MB_DP T0
	RSET24 MD0
	rep #$20
	RFIN 8, $808000
	; px = mq24( B, ky ), py = mq24( B, kx ):
	MOV32 T3, R
	DIGT3
	MB_DP KY
	RSET24 MD0
	rep #$20
	RFIN0 $808000
	MOV32 T1, R                 ; px
	sep #$20
	MB_DP KX
	RSET24 MD0
	rep #$20
	RFIN0 $808000               ; py
	; s <= 7: rsh( p, 7-s ), else p << (s-7):
	lda.b T2
	cmp #8
	bcs _ftn_left
	eor #$0007
	beq _ftn_add                ; s = 7: no shift
	sta.b T2
	; rounding: + 2^(n-1), n = 7-s
	tax
	lda #1
-	dex
	beq +
	asl a
	bra -
+	sta.b T3                    ; 2^(n-1)
	lda.b T1
	clc
	adc.b T3
	sta.b T1
	bcc +
	inc.b T1+2
+	lda.b R
	clc
	adc.b T3
	sta.b R
	bcc +
	inc.b R+2
+	ldx.b T2
-	lda.b T1+2
	cmp #$8000
	ror a
	sta.b T1+2
	ror.b T1
	lda.b R+2
	cmp #$8000
	ror a
	sta.b R+2
	ror.b R
	dex
	bne -
	bra _ftn_add
_ftn_left:
	sbc #7                      ; C set
	tax
-	asl.b T1
	rol.b T1+2
	asl.b R
	rol.b R+2
	dex
	bne -
_ftn_add:
	; Dx += px, Dy -= py:
	ldy.b CK4
	lda.w pt_dx,y
	clc
	adc.b T1
	sta.w pt_dx,y
	lda.w pt_dx+2,y
	adc.b T1+2
	sta.w pt_dx+2,y
	lda.w pt_dy,y
	sec
	sbc.b R
	sta.w pt_dy,y
	lda.w pt_dy+2,y
	sbc.b R+2
	sta.w pt_dy+2,y
	rts

; surlodasverseny, the friction for the sound: pt_fric = the largest
; MULK( mq16( fg, sb ), K_FRIC ) with fg = mq16( g16x, s8 )+mq16( g16y, c8 ),
; sb = mq16( rvx, s8 )+mq16( rvy, c8 ), when both are positive.
phys_fric:
	.ACCU 16
	.INDEX 16
	MOV32 T0, GX
	RSH32 T0, 2
	MOV32 T1, GY
	RSH32 T1, 2
	MOV32 T2, RLX
	RSH32 T2, 8
	MOV32 T3, RLY
	RSH32 T3, 8
	ldx #T0
	jsr phys_clamp16
	sta.b T0                    ; g16x
	ldx #T1
	jsr phys_clamp16
	sta.b T0+2                  ; g16y
	ldx #T2
	jsr phys_clamp16
	sta.b T1                    ; rvx
	ldx #T3
	jsr phys_clamp16
	sta.b T1+2                  ; rvy
	lda #0
	sec
	sbc.b CS
	xba
	sta.b T2                    ; c8 in the low byte
	lda.b SN
	xba
	sta.b T2+2                  ; s8
	; fg:
	sep #$20
	MB_DP T0
	lda.b T2+2
	sta.w MPYB
	ldy.w MPYM
	MB_DP T0+2
	lda.b T2
	sta.w MPYB
	rep #$21
	tya
	adc.w MPYM
	bmi _fr_ret
	beq _fr_ret
	sta.b T3                    ; fg
	sep #$20
	MB_DP T1
	lda.b T2+2
	sta.w MPYB
	ldy.w MPYM
	MB_DP T1+2
	lda.b T2
	sta.w MPYB
	rep #$21
	tya
	adc.w MPYM
	bmi _fr_ret
	beq _fr_ret
	sta.b T3+2                  ; sb
	bra _fr_e
_fr_ret:
	rts
_fr_e:
	; e = MULK( mq16( fg, sb ), K_FRIC ):
	sep #$20
	MB_DP T3
	DIG16 T3+2
	RSET16 MD0
	RFIN0 $808000
	MULK R, K_FRIC
	lda.b R+2
	cmp.w pt_fric+2
	bmi _fr_none
	bne +
	lda.b R
	cmp.w pt_fric
	bcc _fr_none
+	MOV32W pt_fric, phys_dpa+R
_fr_none:
	rts

; A = clamp16( rsh( a - b, 1 ) ) for two double words of the direct page
; (T0 is used).
.MACRO HALFDIFF
	lda.b \1
	sec
	sbc.b \2
	sta.b T0
	lda.b \1+2
	sbc.b \2+2
	sta.b T0+2
	RSH32 T0, 1
	ldx #T0
	jsr phys_clamp16
.ENDM

; The volts (leptet): starts and ends, and the rider turns with the body.
phys_volts:
	.ACCU 16
	.INDEX 16
	stz.w pt_volt
	lda.b S_LASTVOLT
	and #$00FF
	cmp #VOLT_GAP
	bcc _v_go
	lda.b IN
	and #PH_VOLT_R
	beq +
	lda #1
	sta.w pt_volt
	sep #$20
	stz.b S_LASTVOLT
	lda #1
	sta.b S_VOLT1
	rep #$20
	lda.b EV
	ora #PH_VOLT
	sta.b EV
+	lda.b IN
	and #PH_VOLT_L
	beq _v_go
	lda.w pt_volt
	ora #2
	sta.w pt_volt
	sep #$20
	stz.b S_LASTVOLT
	stz.b S_VOLT1
	rep #$20
	lda.b EV
	ora #PH_VOLT
	sta.b EV
_v_go:
	MOV32W pt_oldw, phys_dpa+S_BODY+C_W
	; The end of volt 1: on another volt or after VOLT_END steps.
	lda.b S_VOLTON
	and #$00FF
	beq _v_end2
	lda.w pt_volt
	bne +
	lda.b S_VOLTT
	and #$00FF
	cmp #VOLT_END
	bcc _v_end2
+	lda.b S_BODY+C_W
	clc
	adc #LOKET_W & $FFFF
	sta.b S_BODY+C_W
	lda.b S_BODY+C_W+2
	adc #LOKET_W >> 16
	sta.b S_BODY+C_W+2
	; if w > volt_w[0]: w = volt_w[0]
	lda.b S_VOLTW
	sec
	sbc.b S_BODY+C_W
	lda.b S_VOLTW+2
	sbc.b S_BODY+C_W+2
	bpl +
	MOV32 S_BODY+C_W, S_VOLTW
+	; if w > 0: w -= OMEGAVALT, not below 0
	lda.b S_BODY+C_W+2
	bmi ++
	ora.b S_BODY+C_W
	beq ++
	lda.b S_BODY+C_W
	sec
	sbc #OMEGAVALT_W & $FFFF
	sta.b S_BODY+C_W
	lda.b S_BODY+C_W+2
	sbc #OMEGAVALT_W >> 16
	sta.b S_BODY+C_W+2
	bpl ++
	stz.b S_BODY+C_W
	stz.b S_BODY+C_W+2
++	sep #$20
	stz.b S_VOLTON
	rep #$20
_v_end2:
	lda.b S_VOLTON+1
	and #$00FF
	beq _v_start
	lda.w pt_volt
	bne +
	lda.b S_VOLTT+1
	and #$00FF
	cmp #VOLT_END
	bcc _v_start
+	lda.b S_BODY+C_W
	sec
	sbc #LOKET_W & $FFFF
	sta.b S_BODY+C_W
	lda.b S_BODY+C_W+2
	sbc #LOKET_W >> 16
	sta.b S_BODY+C_W+2
	; if w < volt_w[1]: w = volt_w[1]
	lda.b S_BODY+C_W
	sec
	sbc.b S_VOLTW+4
	lda.b S_BODY+C_W+2
	sbc.b S_VOLTW+6
	bpl +
	MOV32 S_BODY+C_W, S_VOLTW+4
+	; if w < 0: w += OMEGAVALT, not above 0
	lda.b S_BODY+C_W+2
	bpl ++
	lda.b S_BODY+C_W
	clc
	adc #OMEGAVALT_W & $FFFF
	sta.b S_BODY+C_W
	lda.b S_BODY+C_W+2
	adc #OMEGAVALT_W >> 16
	sta.b S_BODY+C_W+2
	bmi ++
	ora.b S_BODY+C_W
	beq ++
	stz.b S_BODY+C_W
	stz.b S_BODY+C_W+2
++	sep #$20
	stz.b S_VOLTON+1
	rep #$20
_v_start:
	lda.w pt_volt
	lsr a
	bcc +
	sep #$20
	lda #1
	sta.b S_VOLTON
	stz.b S_VOLTT
	rep #$20
	MOV32 S_VOLTW, S_BODY+C_W
	lda.b S_BODY+C_W
	sec
	sbc #LOKET_W & $FFFF
	sta.b S_BODY+C_W
	lda.b S_BODY+C_W+2
	sbc #LOKET_W >> 16
	sta.b S_BODY+C_W+2
+	lda.w pt_volt
	and #2
	beq +
	sep #$20
	lda #1
	sta.b S_VOLTON+1
	stz.b S_VOLTT+1
	rep #$20
	MOV32 S_VOLTW+4, S_BODY+C_W
	lda.b S_BODY+C_W
	clc
	adc #LOKET_W & $FFFF
	sta.b S_BODY+C_W
	lda.b S_BODY+C_W+2
	adc #LOKET_W >> 16
	sta.b S_BODY+C_W+2
+	lda.w pt_volt
	bne +
	rts
+	; The rider turns with the body: v += rot90( rider-body ) * dw.
	lda.b S_BODY+C_W
	sec
	sbc.w pt_oldw
	sta.b T1
	lda.b S_BODY+C_W+2
	sbc.w pt_oldw+2
	sta.b T1+2
	RSH32 T1, 12
	ldx #T1
	jsr phys_clamp16
	sta.b T1                    ; dw
	HALFDIFF S_RIDX, S_BODY+C_RX
	sta.b T2                    ; dx
	HALFDIFF S_RIDY, S_BODY+C_RY
	sta.b T2+2                  ; dy
	sep #$20
	MB_DP T1
	DIG16 T2+2
	RFULL16 MD0
	RSH32 R, 7
	SUB32 S_RIDVX, S_RIDVX, R
	sep #$20
	DIG16 T2
	RFULL16 MD0
	RSH32 R, 7
	ADD32 S_RIDVY, S_RIDVY, R
	rts

; The gravity of the step (GVX, GVY).
phys_gravity:
	.ACCU 16
	.INDEX 16
	stz.b GVX
	stz.b GVX+2
	stz.b GVY
	stz.b GVY+2
	lda.b S_GRAVITY
	and #$00FF
	bne +
	lda #G_V
	sta.b GVY
	rts
+	cmp #2
	bne +
	lda #-G_V
	sta.b GVX
	dec.b GVX+2
	rts
+	cmp #3
	bne +
	lda #G_V
	sta.b GVX
	rts
+	lda #-G_V
	sta.b GVY
	dec.b GVY+2
	rts

; frsqrt: for d2 in T1 (> 0): A = Y, T2 = k, T1 = d2 << 2k with 1/sqrt( d2 )
; = Y * 2^(k-30).
phys_frsqrt:
	.ACCU 16
	.INDEX 16
	ldx #0
	lda.b T1+2
	cmp #$4000
	bcs ++
-	asl.b T1
	rol a
	asl.b T1
	rol a
	inx
	cmp #$4000
	bcc -
++	sta.b T1+2
	stx.b T2
	xba
	and #$00FF
	sec
	sbc #64
	asl a
	tax
	lda.l phys_rsqd,x
	sta.b T2+2
	lda.l phys_rsq,x
	pha
	lda.b T1+2
	lsr a
	and #$007F
	sep #$20
	pha
	MB_DP T2+2
	pla
	sta.w MPYB
	rep #$21
	lda.w MPYL
	adc #64
	.REPT 7
	cmp #$8000
	ror a
	.ENDR
	clc
	adc 1,s
	plx
	rts

; Signed 16-bit A = -A:
.MACRO NEGA
	eor #$FFFF
	inc a
.ENDM

; beallitvezeto: the rider (vezeto_hatarolas keeps him over the seat).
phys_rider:
	.ACCU 16
	.INDEX 16
	HALFDIFF S_RIDX, S_BODY+C_RX
	sta.b T2                    ; dx (2^-15 m)
	HALFDIFF S_RIDY, S_BODY+C_RY
	sta.b T2+2                  ; dy
	sep #$20
	DIG16 T2, R2
	DIG16 T2+2, R2+2
	; x = clamp16( rsh( mq16( Cs, dx )+mq16( Sn, dy ), 7 ) ):
	MB_DP CS
	RSET16 R2
	sep #$20
	MB_DP SN
	RADD16 R2+2
	RFIN 7, 2*$808000
	ldx #R
	jsr phys_clamp16
	sta.b T3
	; y = clamp16( rsh( mq16( Cs, dy )+mq16( -Sn, dx ), 7 ) ):
	lda #0
	sec
	sbc.b SN
	sta.b T0
	sep #$20
	MB_DP CS
	RSET16 R2+2
	sep #$20
	MB_DP T0
	RADD16 R2
	RFIN 7, 2*$808000
	ldx #R
	jsr phys_clamp16
	sta.b T3+2
	stz.w pt_tmp+4              ; moved
	lda.b S_TURNED
	and #$00FF
	beq +
	lda.b T3
	NEGA
	sta.b T3
+	; The seat: lel = mq16( x, SEAT_NX )+mq16( y, SEAT_NY )-SEAT_C8.
	sep #$20
	MB_DP T3
	RSETK SEAT_NX
	sep #$20
	MB_DP T3+2
	RADDK SEAT_NY
	RFIN0 2*$808000+SEAT_C8
	lda.b R+2
	bmi _far1
	jmp _rd_top
_far1:
	RSH32 R, 7
	ldx #R
	jsr phys_clamp16
	sta.b T1                    ; l
	sep #$20
	MB_DP T1
	RSETK SEAT_NX
	RFIN 7, $808000
	lda.b T3
	jsr phys_ext32
	SUB32 T0, T0, R
	ldx #T0
	jsr phys_clamp16
	sta.b T3
	sep #$20
	MB_DP T1
	RSETK SEAT_NY
	RFIN 7, $808000
	lda.b T3+2
	jsr phys_ext32
	SUB32 T0, T0, R
	ldx #T0
	jsr phys_clamp16
	sta.b T3+2
	inc.w pt_tmp+4
_rd_top:
	lda.b T3+2
	SLT RIDER_TOP+1
	bmi +
	lda #RIDER_TOP
	sta.b T3+2
	inc.w pt_tmp+4
+	lda.b T3
	SLT RIDER_LEFT
	bpl +
	lda #RIDER_LEFT
	sta.b T3
	inc.w pt_tmp+4
+	lda.b T3
	SLT RIDER_RIGHT+1
	bmi +
	lda #RIDER_RIGHT
	sta.b T3
	inc.w pt_tmp+4
+	; The ellipse in front and up:
	lda.b T3
	bpl _far2
	jmp _rd_back
_far2:
	bne _far3
	jmp _rd_back
_far3:
	lda.b T3+2
	bpl _far4
	jmp _rd_back
_far4:
	bne _far5
	jmp _rd_back
_far5:
	sep #$20
	MB_DP T3
	RSETK RIDER_ELL
	RFIN 6, $808000
	lda.b R
	sta.b T0                    ; xs
	SQUARE T0
	MOV32 T1, R
	SQUARE T3+2
	ADD32 T1, T1, R             ; t2
	lda.b T1+2
	cmp #RIDER_TOP_SQ >> 16
	bcs _far6
	jmp _rd_back
_far6:
	bne +
	lda.b T1
	cmp #(RIDER_TOP_SQ & $FFFF)+1
	bcs _far7
	jmp _rd_back
_far7:
+	jsr phys_frsqrt             ; A = Y, T2 = k
	sta.b T0
	; sc = rsh( mf16( Y, RIDER_TOP ), 15-k ):
	sep #$20
	MB_DP T0
	lda.b #RIDER_TOP & $FF
	sta.b MD0
	lda.b #RIDER_TOP >> 8
	sta.b MD1
	RFULL16 MD0
	lda #15
	sec
	sbc.b T2
	jsr phys_rshr
	lda.b R
	sta.b T0                    ; sc
	; x = rsh( mq16( sc, x ), 7 ), y = rsh( mq16( sc, y ), 7 ):
	sep #$20
	MB_DP T0
	DIG16 T3
	RSET16 MD0
	RFIN 7, $808000
	lda.b R
	sta.b T3
	sep #$20
	DIG16 T3+2
	RSET16 MD0
	RFIN 7, $808000
	lda.b R
	sta.b T3+2
	inc.w pt_tmp+4
_rd_back:
	lda.w pt_tmp+4
	bne +
	jmp _rd_spring
+	lda.b S_TURNED
	and #$00FF
	beq +
	lda.b T3
	NEGA
	sta.b T3
+	; rider = body + rsh( mq16( Cs, x )+mq16( -Sn, y ), 6 ), ...
	lda #0
	sec
	sbc.b SN
	sta.b T0
	sep #$20
	DIG16 T3, R2
	DIG16 T3+2, R2+2
	MB_DP CS
	RSET16 R2
	sep #$20
	MB_DP T0
	RADD16 R2+2
	RFIN 6, 2*$808000
	ADD32 S_RIDX, S_BODY+C_RX, R
	sep #$20
	MB_DP SN
	RSET16 R2
	sep #$20
	MB_DP CS
	RADD16 R2+2
	RFIN 6, 2*$808000
	ADD32 S_RIDY, S_BODY+C_RY, R
_rd_spring:
	; The spring to rest 0.44 m over the body and the damper:
	sep #$20
	MB_DP SN
	RSETK K44_15
	RFIN 6, $808000
	SUB32 T1, S_BODY+C_RX, R    ; rgx
	sep #$20
	MB_DP CS
	RSETK K44_15
	RFIN 6, $808000
	ADD32 T2, S_BODY+C_RY, R    ; rgy
	HALFDIFF T1, S_RIDX
	sta.w pt_tmp+0              ; dirx
	HALFDIFF T2, S_RIDY
	sta.w pt_tmp+2              ; diry
	HALFDIFF S_RIDX, S_BODY+C_RX
	sta.b T2                    ; dx
	HALFDIFF S_RIDY, S_BODY+C_RY
	sta.b T2+2                  ; dy
	; wb = rsh( body.w, 4 ); mvx = body.vx-rsh( mq24( wb, dy ), 7 ), ...
	MOV32 T3, S_BODY+C_W
	RSH32 T3, 4
	DIGT3
	MB_DP T2+2
	RSET24 MD0
	rep #$20
	RFIN 7, $808000
	SUB32 T0, S_BODY+C_VX, R    ; mvx
	sep #$20
	MB_DP T2
	RSET24 MD0
	rep #$20
	RFIN 7, $808000
	ADD32 T1, S_BODY+C_VY, R    ; mvy
	; vx += MULK( dirx, K_RIDER_S )-MULK( vx-mvx, K_RIDER_D )+gvx:
	SUB32 T2, S_RIDVX, T0
	SUB32 R2, S_RIDVY, T1
	MULK T2, K_RIDER_D
	SUB32 S_RIDVX, S_RIDVX, R
	MULK R2, K_RIDER_D
	SUB32 S_RIDVY, S_RIDVY, R
	lda.w pt_tmp+0
	jsr phys_ext32
	MULK T0, K_RIDER_S
	ADD32 S_RIDVX, S_RIDVX, R
	lda.w pt_tmp+2
	jsr phys_ext32
	MULK T0, K_RIDER_S
	ADD32 S_RIDVY, S_RIDVY, R
	ADD32 S_RIDVX, S_RIDVX, GVX
	ADD32 S_RIDVY, S_RIDVY, GVY
	MOV32 T0, S_RIDVX
	RSH32 T0, 8
	ADD32 S_RIDX, S_RIDX, T0
	MOV32 T0, S_RIDVY
	RSH32 T0, 8
	ADD32 S_RIDY, S_RIDY, T0
	rts

; T0 = A sign-extended to 32 bits.
phys_ext32:
	.ACCU 16
	.INDEX 16
	sta.b T0
	cmp #$8000
	lda #0
	bcc +
	dec a
+	sta.b T0+2
	rts

; R = rsh( R, A ) for A from 0 to 31 (A 16-bit).
phys_rshr:
	.ACCU 16
	.INDEX 16
	cmp #0
	bne +
	rts
+	tay
	asl a
	asl a
	tax
	lda.b R
	clc
	adc.l phys_half-4,x
	sta.b R
	lda.b R+2
	adc.l phys_half-2,x
-	cmp #$8000
	ror a
	ror.b R
	dey
	bne -
	sta.b R+2
	rts

; 1 << (n-1) for n from 1 to 31, the halves of rsh:
phys_half:
	.dw $0001, $0000, $0002, $0000, $0004, $0000, $0008, $0000
	.dw $0010, $0000, $0020, $0000, $0040, $0000, $0080, $0000
	.dw $0100, $0000, $0200, $0000, $0400, $0000, $0800, $0000
	.dw $1000, $0000, $2000, $0000, $4000, $0000, $8000, $0000
	.dw $0000, $0001, $0000, $0002, $0000, $0004, $0000, $0008
	.dw $0000, $0010, $0000, $0020, $0000, $0040, $0000, $0080
	.dw $0000, $0100, $0000, $0200, $0000, $0400, $0000, $0800
	.dw $0000, $1000, $0000, $2000, $0000, $4000

;---------------------------------------------------------------------------
; The collisions, D = PHYS_DPB (A 16-bit).

; Copies a contact (\1 to \2) of the direct page B.
.MACRO CTCOPY
	ldx #CT_SIZE-2
_ctcopy_b1\@:	lda.b \1,x
	sta.b \2,x
	dex
	dex
	bpl _ctcopy_b1\@
.ENDM

; need_t: the point of the contact at X (offset in page B) from the
; center QRX, QRY: t = r - rsh( mq16( n, h ), 7 ).
phys_need_t:
	.ACCU 16
	.INDEX 16
	lda.b CT_HT,x
	and #$00FF
	beq +
	rts
+	phx
	lda.b CT_H,x
	sta.b T0
	sep #$20
	DIG16 T0
	MB_ABSX phys_dpb+CT_NX
	RSET16 MD0
	RFIN 7, $808000
	plx
	lda.b QRX
	sec
	sbc.b R
	sta.b CT_TX,x
	lda.b QRX+2
	sbc.b R+2
	sta.b CT_TX+2,x
	phx
	sep #$20
	MB_ABSX phys_dpb+CT_NY
	RSET16 MD0
	RFIN 7, $808000
	plx
	lda.b QRY
	sec
	sbc.b R
	sta.b CT_TY,x
	lda.b QRY+2
	sbc.b R+2
	sta.b CT_TY+2,x
	sep #$20
	lda #1
	sta.b CT_HT,x
	rep #$20
	rts

; talppontkereses with gombszakasz: the contacts (CT0, CT1) of the circle
; at QRX, QRY of radius QR (QRSQ its square) with the lines; A = QN. With
; QHEAD only whether there is one.
phys_contacts:
	.ACCU 16
	.INDEX 16
	stz.b QN
	; Racsonkivul: too far right or up.
	lda.b QRX
	cmp.w lev_racsx
	lda.b QRX+2
	sbc.w lev_racsx+2
	bvc +
	eor #$8000
+	bmi +
	lda #1
	sta.w phys_dpa+RACS
+	lda.b QRY
	cmp.w lev_racsy
	lda.b QRY+2
	sbc.w lev_racsy+2
	bvc +
	eor #$8000
+	bmi +
	lda #1
	sta.w phys_dpa+RACS
+	; From the corner of the grid, within it:
	lda.b QRX
	sec
	sbc.w lev_gx
	sta.b QX
	lda.b QRX+2
	sbc.w lev_gx+2
	sta.b QX+2
	bmi _ct_none
	cmp.w lev_gw+2
	bcs _ct_none
	lda.b QRY
	sec
	sbc.w lev_gy
	sta.b QY
	lda.b QRY+2
	sbc.w lev_gy+2
	sta.b QY+2
	bmi _ct_none
	cmp.w lev_gh+2
	bcc +
_ct_none:
	lda #0
	rts
+	lda.b QX+1
	sta.b QBX
	lda.b QY+1
	sta.b QBY
	; The run of the row of the cell:
	lda.b QY+2
	and #$FFFE                  ; 2*cy
	clc
	adc.w lev_rows
	tax
	lda.w 2,x
	sta.b QCNT                  ; the end of the runs
	lda.w 0,x
	tax                         ; the first run
	lda.b QX+2
	lsr a
	sta.b QL                    ; cx
	stz.b QLIST
	sep #$20
-	cpx.b QCNT
	bcs +
	lda.w 0,x
	cmp.b QL
	beq ++
	bcs +
++	ldy.w 1,x
	sty.b QLIST
	inx
	inx
	inx
	bra -
+	rep #$20
	ldx.b QLIST
	beq _ct_none
	lda.w 0,x
	sta.b QCNT
	inx
	inx
	stx.b QLIST
_ct_line:
	lda.b QCNT
	bne +
	lda.b QN
	rts
+	dec.b QCNT
	ldy.b QLIST
	lda.w 0,y
	sta.b QL
	iny
	iny
	sty.b QLIST
	tax
	; The box of the line:
	lda.b QBX
	cmp.w 0,x
	bcc _ct_line
	lda.w 2,x
	cmp.b QBX
	bcc _ct_line
	lda.b QBY
	cmp.w 4,x
	bcc _ct_line
	lda.w 6,x
	cmp.b QBY
	bcc _ct_line
	; From the middle of the line, in 2^-15 m:
	lda.w 10,x
	and #$00FF
	sta.b RX15+2
	lda.b QX
	sec
	sbc.w 8,x
	sta.b RX15
	lda.b QX+2
	sbc.b RX15+2
	sta.b RX15+2
	ASR32 RX15, 1
	lda.w 13,x
	and #$00FF
	sta.b RY15+2
	lda.b QY
	sec
	sbc.w 11,x
	sta.b RY15
	lda.b QY+2
	sbc.b RY15+2
	sta.b RY15+2
	ASR32 RY15, 1
	sep #$20
	DIG24 RX15, DGX
	DIG24 RY15, DGY
	; tav = rsh( mq24( ry15, ex )+mq24( rx15, -ey )+mq16( ry15 >> 8, elx )
	;            +mq16( rx15 >> 8, -ely ), 6 ):
	ldx.b QL
	MB_ABSX 20
	RSET24 DGY
	ldx.b QL
	rep #$20
	lda.w 22,x
	NEGA
	sta.b T0
	sep #$20
	MB_DP T0
	RADD24 DGX
	MB_DP RY15+1
	ldx.b QL
	lda.w 24,x
	sta.w MPYB
	rep #$21
	lda.w MPYM
	eor #$8000
	adc.b R
	sta.b R
	bcc +
	inc.b R+2
+	sep #$20
	MB_DP RX15+1
	ldx.b QL
	lda.w 25,x
	eor #$FF
	inc a
	sta.w MPYB
	rep #$21
	lda.w MPYM
	eor #$8000
	adc.b R
	sta.b R
	bcc +
	inc.b R+2
+	RFIN 6, 2*$808000+2*$8000
	; |tav| <= R:
	lda.b R+2
	beq +
	inc a
	beq ++
	jmp _ct_line
+	lda.b R
	cmp.b QR
	beq _ct_near
	bcc _ct_near
	jmp _ct_line
++	lda.b R
	clc
	adc.b QR
	bcs _ct_near
	jmp _ct_line
_ct_near:
	MOV32 TAV, R
	; pos = rsh( mq24( rx15, ex )+mq24( ry15, ey ), 6 ):
	sep #$20
	ldx.b QL
	MB_ABSX 20
	RSET24 DGX
	ldx.b QL
	MB_ABSX 22
	RADD24 DGY
	rep #$20
	RFIN 6, 2*$808000
	ldx.b QL
	stz.b CTN+CT_HT             ; has_t, has_n
	stz.b CTN+CT_DN
	; pos < -half: the start A = 2M - B - par; pos > half: the end B.
	lda.w 28,x
	sta.b T0
	lda.w 30,x
	and #$00FF
	sta.b T0+2                  ; half
	lda.b R
	clc
	adc.b T0
	lda.b R+2
	adc.b T0+2
	bpl +
	jmp _ct_a
+	lda.b T0
	sec
	sbc.b R
	lda.b T0+2
	sbc.b R+2
	bpl _ct_mid
	; The end B:
	lda.w 16,x
	and #$00FF
	sta.b T0
	lda.b QX
	sec
	sbc.w 14,x
	sta.b DDX
	lda.b QX+2
	sbc.b T0
	sta.b DDX+2
	lda.w 19,x
	and #$00FF
	sta.b T0
	lda.b QY
	sec
	sbc.w 17,x
	sta.b DDY
	lda.b QY+2
	sbc.b T0
	sta.b DDY+2
	jmp _ct_end
_ct_mid:
	; In the middle: n and h from the line.
	ldx.b QL
	lda.b TAV+2
	bmi +
	lda.w 22,x
	NEGA
	sta.b CTN+CT_NX
	lda.w 20,x
	sta.b CTN+CT_NY
	lda.b TAV
	sta.b CTN+CT_H
	bra ++
+	lda.w 22,x
	sta.b CTN+CT_NX
	lda.w 20,x
	NEGA
	sta.b CTN+CT_NY
	lda.b TAV
	NEGA
	sta.b CTN+CT_H
++	lda.w 26,x
	sta.b CTN+CT_DN
	sep #$20
	lda #1
	sta.b CTN+CT_HN
	rep #$20
	jmp _ct_found
_ct_a:
	; The start: A = 2M - B - par.
	ldx.b QL
	lda.w 10,x
	and #$00FF
	sta.b T0+2
	lda.w 8,x
	asl a
	rol.b T0+2
	sta.b T0                    ; 2 M.x
	lda.w 16,x
	and #$00FF
	sta.b T1+2
	lda.w 14,x
	sta.b T1
	SUB32 T0, T0, T1
	lda.w 31,x
	and #$0001
	sta.b T1
	stz.b T1+2
	SUB32 T0, T0, T1
	SUB32 DDX, QX, T0
	ldx.b QL
	lda.w 13,x
	and #$00FF
	sta.b T0+2
	lda.w 11,x
	asl a
	rol.b T0+2
	sta.b T0                    ; 2 M.y
	lda.w 19,x
	and #$00FF
	sta.b T1+2
	lda.w 17,x
	sta.b T1
	SUB32 T0, T0, T1
	lda.w 31,x
	lsr a
	and #$0001
	sta.b T1
	stz.b T1+2
	SUB32 T0, T0, T1
	SUB32 DDY, QY, T0
_ct_end:
	; Within the radius of an end point:
	ldx #DDX
	jsr phys_within
	bcc +
	ldx #DDY
	jsr phys_within
	bcs ++
+	jmp _ct_line
++	SQUARE DDX
	MOV32 T1, R
	SQUARE DDY
	ADD32 T1, T1, R
	lda.b T1+2
	cmp.b QRSQ+2
	bcc +
	bne ++
	lda.b T1
	cmp.b QRSQ
	bcc +
++	jmp _ct_line
+	SUB32 CTN+CT_TX, QRX, DDX
	SUB32 CTN+CT_TY, QRY, DDY
	sep #$20
	lda #1
	sta.b CTN+CT_HT
	rep #$20
_ct_found:
	lda.b QHEAD
	beq +
	lda #1
	rts
+	lda.b QN
	bne +
	CTCOPY CTN, CT0
	lda #1
	sta.b QN
	jmp _ct_line
+	; A second one: one with the first if they are within 0.1 m.
	ldx #CT0
	jsr phys_need_t
	ldx #CTN
	jsr phys_need_t
	SUB32 T0, CT0+CT_TX, CTN+CT_TX
	SUB32 T1, CT0+CT_TY, CTN+CT_TY
	ldx #T0
	jsr phys_merge_near
	bcs _far8
	jmp _ct_two
_far8:
	ldx #T1
	jsr phys_merge_near
	bcs _far9
	jmp _ct_two
_far9:
	SQUARE T0
	MOV32 T2, R
	SQUARE T1
	ADD32 T2, T2, R
	lda.b T2+2
	cmp #MERGE_SQ >> 16
	bcc +
	bne _ct_two
	lda.b T2
	cmp #MERGE_SQ & $FFFF
	bcs _ct_two
+	; (t0 + tn) >> 1:
	ADD32 T0, CT0+CT_TX, CTN+CT_TX
	ASR32 T0, 1
	MOV32 CT0+CT_TX, T0
	ADD32 T0, CT0+CT_TY, CTN+CT_TY
	ASR32 T0, 1
	MOV32 CT0+CT_TY, T0
	sep #$20
	stz.b CT0+CT_HN
	rep #$20
	stz.b CT0+CT_DN
	jmp _ct_line
_ct_two:
	CTCOPY CTN, CT1
	lda #2
	sta.b QN
	rts

; C set if -QR < the double word at X < QR.
phys_within:
	.ACCU 16
	.INDEX 16
	lda.b 2,x
	beq +
	inc a
	bne ++
	lda.b 0,x
	clc
	adc.b QR
	beq ++
	bcs +++
++	clc
	rts
+	lda.b 0,x
	cmp.b QR
	bcs ++
+++	sec
	rts
++	clc
	rts

; C set if -MERGE_P < the double word at X < MERGE_P.
phys_merge_near:
	.ACCU 16
	.INDEX 16
	lda.b 2,x
	beq +
	inc a
	bne ++
	lda.b 0,x
	clc
	adc #MERGE_P
	beq ++
	bcs +++
++	clc
	rts
+	lda.b 0,x
	cmp #MERGE_P
	bcs ++
+++	sec
	rts
++	clc
	rts

; R = MB * A, the whole product, for |A| <= 32767 (T3 is used).
phys_mfa:
	.ACCU 16
	.INDEX 16
	sta.b T3
	bmi +
	NEGA
	sta.b T3
	sep #$20
	DIG16 T3
	RFULL16 MD0
	lda #0
	sec
	sbc.b R
	sta.b R
	lda #0
	sbc.b R+2
	sta.b R+2
	rts
+	sep #$20
	DIG16 T3
	RFULL16 MD0
	rts

; C set if the double word at X is within [-32767, 32767].
phys_fits16:
	.ACCU 16
	.INDEX 16
	lda.b 2,x
	beq +
	inc a
	bne ++
	lda.b 0,x
	cmp #$8001
	rts
+	lda.b 0,x
	cmp #$8000
	bcs ++
	sec
	rts
++	clc
	rts

; A = clamp of R to [-32767, 32767] (a component of a unit vector).
phys_unit15:
	.ACCU 16
	.INDEX 16
	ldx #R
	jsr phys_fits16
	bcc +
	lda.b R
	rts
+	lda.b R+2
	bmi +
	lda #32767
	rts
+	lda #-32767
	rts

; norm: n and h of the contact at NSH+2... the contact at X (offset in page
; B) from d = DDX, DDY (P).
phys_norm:
	.ACCU 16
	.INDEX 16
	stx.b NCT
	stz.b NSH
-	ldx #DDX
	jsr phys_fits16
	bcc +
	ldx #DDY
	jsr phys_fits16
	bcs ++
+	ASR32 DDX, 1
	ASR32 DDY, 1
	inc.b NSH
	bra -
++	SQUARE DDX
	MOV32 T1, R
	SQUARE DDY
	ADD32 T1, T1, R
	ldx.b NCT
	stz.b CT_DN,x
	sep #$20
	lda #1
	sta.b CT_HN,x
	rep #$20
	lda.b T1
	ora.b T1+2
	bne +
	stz.b CT_NX,x
	stz.b CT_H,x
	lda #32767
	sta.b CT_NY,x
	rts
+	jsr phys_frsqrt             ; A = Y, T2 = k, T1 = d2 << 2k
	sta.b T0
	sep #$20
	MB_DP T0
	rep #$20
	lda.b DDX
	jsr phys_mfa
	lda #15
	sec
	sbc.b T2
	jsr phys_rshr
	jsr phys_unit15
	ldx.b NCT
	sta.b CT_NX,x
	lda.b DDY
	jsr phys_mfa
	lda #15
	sec
	sbc.b T2
	jsr phys_rshr
	jsr phys_unit15
	ldx.b NCT
	sta.b CT_NY,x
	; h = clamp16( rsh( mf16( X >> 17, Y ), 13+k ) << sh ):
	lda.b T1+2
	lsr a
	jsr phys_mfa
	lda #13
	clc
	adc.b T2
	jsr phys_rshr
	ldx.b NSH
	beq +
-	asl.b R
	rol.b R+2
	dex
	bne -
+	ldx #R
	jsr phys_clamp16
	ldx.b NCT
	sta.b CT_H,x
	rts

; need_n for the contact at X: n, h from the center and its point.
phys_need_n:
	.ACCU 16
	.INDEX 16
	lda.b CT_HN,x
	and #$00FF
	beq +
	rts
+	lda.b QRX
	sec
	sbc.b CT_TX,x
	sta.b DDX
	lda.b QRX+2
	sbc.b CT_TX+2,x
	sta.b DDX+2
	lda.b QRY
	sec
	sbc.b CT_TY,x
	sta.b DDY
	lda.b QRY+2
	sbc.b CT_TY+2,x
	sta.b DDY+2
	jmp phys_norm

; helyigazitas for the contact at X: the wheel (WK) out to the band; C set
; if it moved. QRX, QRY follow it.
phys_push:
	.ACCU 16
	.INDEX 16
	lda.b CT_H,x
	cmp #BAND_P
	bmi +
	clc
	rts
+	stx.b NCT
	lda #BAND_P
	sec
	sbc.b CT_H,x
	sta.b T0                    ; p
	lda #BAND_P
	sta.b CT_H,x
	sep #$20
	DIG16 T0
	MB_ABSX phys_dpb+CT_NX
	RSET16 MD0
	RFIN 7, $808000
	ldx.b WK
	lda.w phys_dpa+C_RX,x
	clc
	adc.b R
	sta.w phys_dpa+C_RX,x
	sta.b QRX
	lda.w phys_dpa+C_RX+2,x
	adc.b R+2
	sta.w phys_dpa+C_RX+2,x
	sta.b QRX+2
	ldx.b NCT
	sep #$20
	MB_ABSX phys_dpb+CT_NY
	RSET16 MD0
	RFIN 7, $808000
	ldx.b WK
	lda.w phys_dpa+C_RY,x
	clc
	adc.b R
	sta.w phys_dpa+C_RY,x
	sta.b QRY
	lda.w phys_dpa+C_RY+2,x
	adc.b R+2
	sta.w phys_dpa+C_RY+2,x
	sta.b QRY+2
	ldx.b NCT
	sec
	rts

; \1 (direct page) = the double word at \2 + X (absolute) >> 8, rounded
; down.
.MACRO SHR8WX
	lda.w \2+1,x
	sta.b \1
	lda.w \2+3,x
	and #$00FF
	cmp #$0080
	bcc _shr8wx\@
	ora #$FF00
_shr8wx\@:
	sta.b \1+2
.ENDM

; \1 (direct page) = the double word at \2 + X (absolute):
.MACRO MOV32WX
	lda.w \2,x
	sta.b \1
	lda.w \2+2,x
	sta.b \1+2
.ENDM

; holds (talppontigazitas): C set if the contact at X holds the wheel WK;
; A nonzero: the velocity towards the point goes.
phys_holds:
	.ACCU 16
	.INDEX 16
	stx.b NCT
	sta.b T2                    ; remove
	ldx.b WK
	SHR8WX T0, phys_dpa+C_VX
	SHR8WX T1, phys_dpa+C_VY
	ldx #T0
	jsr phys_clamp16
	sta.b T0
	ldx #T1
	jsr phys_clamp16
	sta.b T1
	; nv = rsh( mf16( nx, vx8 )+mf16( ny, vy8 ), 7 ):
	ldx.b NCT
	sep #$20
	MB_ABSX phys_dpb+CT_NX
	DIG16 T0
	RFULL16 MD0
	MOV32 T3, R
	ldx.b NCT
	sep #$20
	MB_ABSX phys_dpb+CT_NY
	DIG16 T1
	RFULL16 MD0
	ADD32 R, R, T3
	RSH32 R, 7
	MOV32 NV, R
	; Moving away (nv > -ELSZ) with the force away: no contact.
	lda.b NV
	clc
	adc #ELSZ_V
	tax
	lda.b NV+2
	adc #0
	bpl _far10
	jmp _ho_yes
_far10:
	bne +
	cpx #0
	bne _far11
	jmp _ho_yes
_far11:
+	lda.w phys_dpa+FX
	sta.b T3
	lda.w phys_dpa+FX+2
	sta.b T3+2
	DIGT3
	ldx.b NCT
	MB_ABSX phys_dpb+CT_NX
	RSET24 MD0
	rep #$20
	lda.w phys_dpa+FY
	sta.b T3
	lda.w phys_dpa+FY+2
	sta.b T3+2
	DIGT3
	ldx.b NCT
	MB_ABSX phys_dpb+CT_NY
	RADD24 MD0
	rep #$20
	RFIN0 2*$808000
	lda.b R+2
	bmi _ho_yes
	ora.b R
	beq _ho_yes
	clc
	rts
_ho_yes:
	lda.b T2
	bne _far12
	jmp _ho_bump
_far12:
	; v -= rsh( mq24( nv, n ), 7 ):
	MOV32 T3, NV
	DIGT3
	ldx.b NCT
	MB_ABSX phys_dpb+CT_NX
	RSET24 MD0
	rep #$20
	RFIN 7, $808000
	ldx.b WK
	lda.w phys_dpa+C_VX,x
	sec
	sbc.b R
	sta.w phys_dpa+C_VX,x
	lda.w phys_dpa+C_VX+2,x
	sbc.b R+2
	sta.w phys_dpa+C_VX+2,x
	ldx.b NCT
	sep #$20
	MB_ABSX phys_dpb+CT_NY
	RSET24 MD0
	rep #$20
	RFIN 7, $808000
	ldx.b WK
	lda.w phys_dpa+C_VY,x
	sec
	sbc.b R
	sta.w phys_dpa+C_VY,x
	lda.w phys_dpa+C_VY+2,x
	sbc.b R+2
	sta.w phys_dpa+C_VY+2,x
_ho_bump:
	; A bump over 1.5 m/s:
	lda.b NV+2
	bpl +
	lda #0
	sec
	sbc.b NV
	sta.b NV
	lda #0
	sbc.b NV+2
	sta.b NV+2
+	lda #BUMP_MIN_V & $FFFF
	cmp.b NV
	lda #BUMP_MIN_V >> 16
	sbc.b NV+2
	bmi _far13
	jmp _ho_end                 ; |nv| <= BUMP_MIN_V
_far13:
	MULK NV, K_BUMP
	lda.b R+2
	bne +
	lda.b R
	cmp #254
	bcc ++
+	lda #253
++	cmp.w phys_bump
	bcc +
	sta.w phys_bump
+	lda.w phys_dpa+EV
	ora #PH_BUMP
	sta.w phys_dpa+EV
_ho_end:
	ldx.b NCT
	sec
	rts

; side: R = (t1-t2)*n90 of t2 (sign), the contacts at SC1 = T2, SC2 = T2+2.
phys_side:
	.ACCU 16
	.INDEX 16
	ldx.b T2
	ldy.b T2+2
	lda.b CT_TX,x
	sec
	sbc.w phys_dpb+CT_TX,y
	sta.b T0
	lda.b CT_TX+2,x
	sbc.w phys_dpb+CT_TX+2,y
	sta.b T0+2
	ASR32 T0, 1
	ldx #T0
	jsr phys_clamp16
	sta.b T1                    ; dx
	ldx.b T2
	ldy.b T2+2
	lda.b CT_TY,x
	sec
	sbc.w phys_dpb+CT_TY,y
	sta.b T0
	lda.b CT_TY+2,x
	sbc.w phys_dpb+CT_TY+2,y
	sta.b T0+2
	ASR32 T0, 1
	ldx #T0
	jsr phys_clamp16
	sta.b T1+2                  ; dy
	ldx.b T2+2
	lda.b CT_NY,x
	NEGA
	sta.b T0
	sep #$20
	MB_DP T0
	DIG16 T1
	RSET16 MD0
	ldx.b T2+2
	sep #$20
	MB_ABSX phys_dpb+CT_NX
	DIG16 T1+2
	RADD16 MD0
	RFIN0 2*$808000
	rts

; C set unless (d < 0 and m > 0) or (d > 0 and m < 0): d = R, m = T3.
phys_same_side:
	.ACCU 16
	.INDEX 16
	lda.b R+2
	bmi _ss_dneg
	ora.b R
	beq _ss_yes
	lda.b T3+2                  ; d > 0: no if m < 0
	bmi _ss_no
	bra _ss_yes
_ss_dneg:
	lda.b T3+2                  ; d < 0: no if m > 0
	bmi _ss_yes
	ora.b T3
	bne _ss_no
_ss_yes:
	sec
	rts
_ss_no:
	clc
	rts

; biztostalppont_uj( T2 -> c1, T2+2 -> c2 ): C set if c1 stays.
phys_sure_new:
	.ACCU 16
	.INDEX 16
	ldx.b WK
	MOV32WX T0, phys_dpa+C_VX
	MOV32WX T1, phys_dpa+C_VY
	RSH32 T0, 8
	RSH32 T1, 8
	ldx #T0
	jsr phys_clamp16
	sta.b T0
	ldx #T1
	jsr phys_clamp16
	sta.b T1
	; nv = clamp16( rsh( mq16( -ny, vx )+mq16( nx, vy ), 7 ) ):
	ldx.b T2+2
	lda.b CT_NY,x
	NEGA
	sta.b T3
	sep #$20
	MB_DP T3
	DIG16 T0
	RSET16 MD0
	ldx.b T2+2
	sep #$20
	MB_ABSX phys_dpb+CT_NX
	DIG16 T1
	RADD16 MD0
	RFIN 7, 2*$808000
	ldx #R
	jsr phys_clamp16
	sta.b T0                    ; nv
	; m = w + rsh( mf16( nv, h ), 4 ):
	sep #$20
	MB_DP T0
	ldx.b T2+2
	lda.b CT_H,x
	sta.b T1
	lda.b CT_H+1,x
	sta.b T1+1
	DIG16 T1
	RFULL16 MD0
	RSH32 R, 4
	ldx.b WK
	lda.w phys_dpa+C_W,x
	clc
	adc.b R
	sta.b T3
	lda.w phys_dpa+C_W+2,x
	adc.b R+2
	sta.b T3+2
	jsr phys_side
	jmp phys_same_side

; biztostalppont_regi( T2 -> c1, T2+2 -> c2 ):
phys_sure_old:
	.ACCU 16
	.INDEX 16
	; fn = rsh( mq24( Fx, -ny )+mq24( Fy, nx ), 7 ):
	ldx.b T2+2
	lda.b CT_NY,x
	NEGA
	sta.b T0
	MOV32W phys_dpb+T3, phys_dpa+FX
	DIGT3
	MB_DP T0
	RSET24 MD0
	rep #$20
	MOV32W phys_dpb+T3, phys_dpa+FY
	DIGT3
	ldx.b T2+2
	MB_ABSX phys_dpb+CT_NX
	RADD24 MD0
	rep #$20
	RFIN 7, 2*$808000
	; x = rsh( mq24( fn, h ), 8 ); m = Mk + MULK( x, K_REGI ):
	MOV32 T3, R
	DIGT3
	ldx.b T2+2
	MB_ABSX phys_dpb+CT_H
	RSET24 MD0
	rep #$20
	RFIN 8, $808000
	MOV32 T0, R
	MULK T0, K_REGI
	lda.w phys_dpa+MK
	clc
	adc.b R
	sta.b T3
	lda.w phys_dpa+MK+2
	adc.b R+2
	sta.b T3+2
	jsr phys_side
	jmp phys_same_side

; a = wrap( a ) for the double word at X of the direct page: back between
; -pi and pi.
phys_wrap:
	.ACCU 16
	.INDEX 16
	lda.b 0,x
	cmp #PI_W & $FFFF
	lda.b 2,x
	sbc #PI_W >> 16
	bvc +
	eor #$8000
+	bmi +
	lda.b 0,x                   ; a >= pi
	sec
	sbc #TWOPI_W & $FFFF
	sta.b 0,x
	lda.b 2,x
	sbc #TWOPI_W >> 16
	sta.b 2,x
	rts
+	lda.b 0,x
	cmp #(-PI_W) & $FFFF
	lda.b 2,x
	sbc #((-PI_W) >> 16) & $FFFF
	bvc +
	eor #$8000
+	bpl +
	lda.b 0,x                   ; a < -pi
	clc
	adc #TWOPI_W & $FFFF
	sta.b 0,x
	lda.b 2,x
	adc #TWOPI_W >> 16
	sta.b 2,x
+	rts

; The wheel moves with its velocity: a += w, r += rsh( v, 8 ) (page A, the
; wheel at X).
phys_move:
	.ACCU 16
	.INDEX 16
	lda.b C_A,x
	clc
	adc.b C_W,x
	sta.b C_A,x
	lda.b C_A+2,x
	adc.b C_W+2,x
	sta.b C_A+2,x
	phx
	txa
	clc
	adc #C_A
	tax
	jsr phys_wrap
	plx
	; r += rsh( v, 8 ):
	lda.b C_VX+1,x
	sta.b T0
	lda.b C_VX+3,x
	and #$00FF
	cmp #$0080
	bcc +
	ora #$FF00
+	sta.b T0+2
	lda.b C_VX,x
	and #$0080
	beq +
	inc.b T0
	bne +
	inc.b T0+2
+	lda.b C_RX,x
	clc
	adc.b T0
	sta.b C_RX,x
	lda.b C_RX+2,x
	adc.b T0+2
	sta.b C_RX+2,x
	lda.b C_VY+1,x
	sta.b T0
	lda.b C_VY+3,x
	and #$00FF
	cmp #$0080
	bcc +
	ora #$FF00
+	sta.b T0+2
	lda.b C_VY,x
	and #$0080
	beq +
	inc.b T0
	bne +
	inc.b T0+2
+	lda.b C_RY,x
	clc
	adc.b T0
	sta.b C_RY,x
	lda.b C_RY+2,x
	adc.b T0+2
	sta.b C_RY+2,x
	rts

; beallit for the wheel WK with the force FX, FY and the torque MK of page
; A: R = the change of its angle. D = PHYS_DPB.
phys_wheel:
	.ACCU 16
	.INDEX 16
	ldx.b WK
	MOV32WX QRX, phys_dpa+C_RX
	MOV32WX QRY, phys_dpa+C_RY
	lda #R_WHEEL_P
	sta.b QR
	lda #R_WHEEL_SQ & $FFFF
	sta.b QRSQ
	lda #R_WHEEL_SQ >> 16
	sta.b QRSQ+2
	stz.b QHEAD
	jsr phys_contacts
	sta.b WN
	bne +
	jmp _wh_holds
+	ldx #CT0
	jsr phys_need_n
	ldx #CT0
	jsr phys_push
	bcc +
	lda.b WN
	cmp #2
	bne +
	sep #$20
	stz.b CT1+CT_HN
	rep #$20
+	lda.b WN
	cmp #2
	beq +
	jmp _wh_holds
+	ldx #CT1
	jsr phys_need_n
	ldx #CT1
	jsr phys_push
	bcc +
	SUB32 DDX, QRX, CT0+CT_TX
	SUB32 DDY, QRY, CT0+CT_TY
	ldx #CT0
	jsr phys_norm
+	; Two contacts: biztostalppont, the new way over 1 m/s, the old under.
	ldx.b WK
	MOV32WX T0, phys_dpa+C_VX
	MOV32WX T1, phys_dpa+C_VY
	RSH32 T0, 8
	RSH32 T1, 8
	ldx #T0
	jsr phys_clamp16
	sta.b T0
	ldx #T1
	jsr phys_clamp16
	sta.b T0+2
	SQUARE T0
	MOV32 T1, R
	SQUARE T0+2
	ADD32 T1, T1, R             ; v2
	lda.b T1+2
	cmp #(V1MS_16*V1MS_16) >> 16
	bne +
	lda.b T1
	cmp #(V1MS_16*V1MS_16) & $FFFF
	bne +
	jmp _wh_holds               ; exactly 1 m/s: neither
+	bcc _wh_old
	lda #CT0
	sta.b T2
	lda #CT1
	sta.b T2+2
	jsr phys_sure_new
	bcs +
	lda #1
	sta.b WN
	CTCOPY CT1, CT0
	bra _wh_holds
+	lda #CT1
	sta.b T2
	lda #CT0
	sta.b T2+2
	jsr phys_sure_new
	bcs _wh_holds
	lda #1
	sta.b WN
	bra _wh_holds
_wh_old:
	lda #CT0
	sta.b T2
	lda #CT1
	sta.b T2+2
	jsr phys_sure_old
	bcs +
	lda #1
	sta.b WN
	CTCOPY CT1, CT0
	bra _wh_holds
+	lda #CT1
	sta.b T2
	lda #CT0
	sta.b T2+2
	jsr phys_sure_old
	bcs _wh_holds
	lda #1
	sta.b WN
_wh_holds:
	; talppontigazitas: the second, then the first.
	lda.b WN
	cmp #2
	bne +
	ldx #CT1
	lda #1
	jsr phys_holds
	bcs +
	lda #1
	sta.b WN
+	lda.b WN
	beq _wh_free
	ldx #CT0
	lda #0
	jsr phys_holds
	bcs +
	lda.b WN
	dec a
	sta.b WN
	beq _wh_free
	CTCOPY CT1, CT0
+	lda.b WN
	cmp #1
	beq +
	ldx.b WR
	sep #$20
	lda #0
	sta.w phys_dpa+R_ON,x
	rep #$20
	lda.b WN
	cmp #2
	bne _wh_free
	jmp _wh_held
+	jmp _wh_roll

_wh_free:
	ldx.b WR
	sep #$20
	lda #0
	sta.w phys_dpa+R_ON,x
	rep #$20
	; Free in the air: w += the torque * K_FREE (whole products).
	MOV32W phys_dpb+T3, phys_dpa+MK
	DIGT3
	MB_IMM K_FREE_M
	lda.b MD0
	sta.w MPYB
	lda.w MPYL
	pha                         ; the lowest byte of the product
	RSET24 MD0
	rep #$20
	RFIN0 $808000
	.REPT 4
	asl.b R
	rol.b R+2
	.ENDR
	sep #$20
	pla
	lsr a
	lsr a
	lsr a
	lsr a
	ora.b R
	sta.b R
	rep #$20
	.IF K_FREE_SH > 4
	lda #K_FREE_SH-4
	jsr phys_rshr
	.ENDIF
	ldx.b WK
	lda.w phys_dpa+C_W,x
	clc
	adc.b R
	sta.w phys_dpa+C_W,x
	lda.w phys_dpa+C_W+2,x
	adc.b R+2
	sta.w phys_dpa+C_W+2,x
	; v += F:
	lda.w phys_dpa+C_VX,x
	clc
	adc.w phys_dpa+FX
	sta.w phys_dpa+C_VX,x
	lda.w phys_dpa+C_VX+2,x
	adc.w phys_dpa+FX+2
	sta.w phys_dpa+C_VX+2,x
	lda.w phys_dpa+C_VY,x
	clc
	adc.w phys_dpa+FY
	sta.w phys_dpa+C_VY,x
	lda.w phys_dpa+C_VY+2,x
	adc.w phys_dpa+FY+2
	sta.w phys_dpa+C_VY+2,x
	jmp _wh_move

_wh_held:
	ldx.b WK
	stz.w phys_dpa+C_VX,x
	stz.w phys_dpa+C_VX+2,x
	stz.w phys_dpa+C_VY,x
	stz.w phys_dpa+C_VY+2,x
	stz.w phys_dpa+C_W,x
	stz.w phys_dpa+C_W+2,x
	stz.b R
	stz.b R+2
	rts

_wh_roll:
	; Rolls around the contact point; n90 = ( -ny, nx ):
	lda.b CT0+CT_NY
	NEGA
	sta.b N90X
	lda.b CT0+CT_NX
	sta.b N90Y
	ldx.b WR
	lda.w phys_dpa+R_ON,x
	and #$00FF
	beq _wh_proj
	lda.w phys_dpa+R_NX,x
	cmp.b CT0+CT_NX
	bne _wh_proj
	lda.w phys_dpa+R_NY,x
	cmp.b CT0+CT_NY
	bne _wh_proj
	lda.w phys_dpa+R_OFF,x
	sta.b SP
	lda.w phys_dpa+R_OFF+2,x
	sta.b SP+2
	jmp _wh_fn
_wh_proj:
	; sp = rsh( mq24( vx, n90x )+mq24( vy, n90y ), 7 ), then / |n90|:
	ldx.b WK
	MOV32WX T3, phys_dpa+C_VX
	DIGT3
	MB_DP N90X
	RSET24 MD0
	rep #$20
	ldx.b WK
	MOV32WX T3, phys_dpa+C_VY
	DIGT3
	MB_DP N90Y
	RADD24 MD0
	rep #$20
	RFIN 7, 2*$808000
	MOV32 SP, R
	MOV32 T3, SP
	DIGT3
	MB_DP CT0+CT_DN
	RSET24 MD0
	rep #$20
	RFIN 22, $808000
	ADD32 SP, SP, R
_wh_fn:
	; fn = rsh( mq24( Fx, n90x )+mq24( Fy, n90y ), 7 ):
	MOV32W phys_dpb+T3, phys_dpa+FX
	DIGT3
	MB_DP N90X
	RSET24 MD0
	rep #$20
	MOV32W phys_dpb+T3, phys_dpa+FY
	DIGT3
	MB_DP N90Y
	RADD24 MD0
	rep #$20
	RFIN 7, 2*$808000
	MOV32 FN, R
	; rho = 1/(theta + m h^2) from the table, h within 0..26367:
	lda.b CT0+CT_H
	bpl +
	lda #0
+	cmp #26368
	bcc +
	lda #26367
+	pha
	and #$007F
	sta.b T0                    ; f
	pla
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	and #$FFFE                  ; 2i
	tax
	lda.l phys_rhod,x
	sta.b T0+2
	lda.l phys_rho,x
	sta.b HRHO
	sep #$20
	MB_DP T0+2
	lda.b T0
	sta.w MPYB
	rep #$21
	lda.w MPYL
	adc #64
	.REPT 7
	cmp #$8000
	ror a
	.ENDR
	clc
	adc.b HRHO
	sta.b HRHO
	; b = MULK( fn, K_FN )+MULK( Mk, K_MR ):
	MULK FN, K_FN
	MOV32 T1, R
	MOV32W phys_dpb+T0, phys_dpa+MK
	MULK T0, K_MR
	ADD32 T1, T1, R
	; sp = clamp24( sp + rsh( mq24( b, rho ), 5 ) ):
	MOV32 T3, T1
	DIGT3
	MB_DP HRHO
	RSET24 MD0
	rep #$20
	RFIN 5, $808000
	ADD32 SP, SP, R
	ldx #SP
	jsr phys_clamp24
	; w = 40 sp, the angle; v = rsh( mq24( sp, n90 ), 7 ):
	MOV32 T0, SP
	ASL32 T0, 3                 ; 8 sp
	MOV32 T1, T0
	ASL32 T1, 2                 ; 32 sp
	ADD32 T0, T0, T1
	ldx.b WK
	lda.b T0
	sta.w phys_dpa+C_W,x
	lda.b T0+2
	sta.w phys_dpa+C_W+2,x
	sep #$20
	DIG24 SP
	MB_DP N90X
	RSET24 MD0
	rep #$20
	RFIN 7, $808000
	ldx.b WK
	lda.b R
	sta.w phys_dpa+C_VX,x
	lda.b R+2
	sta.w phys_dpa+C_VX+2,x
	sep #$20
	MB_DP N90Y
	RSET24 MD0
	rep #$20
	RFIN 7, $808000
	ldx.b WK
	lda.b R
	sta.w phys_dpa+C_VY,x
	lda.b R+2
	sta.w phys_dpa+C_VY+2,x
	; The rolling for the next step:
	ldx.b WR
	lda.b SP
	sta.w phys_dpa+R_OFF,x
	lda.b SP+2
	sta.w phys_dpa+R_OFF+2,x
	lda.b CT0+CT_NX
	sta.w phys_dpa+R_NX,x
	lda.b CT0+CT_NY
	sta.w phys_dpa+R_NY,x
	sep #$20
	lda #1
	sta.w phys_dpa+R_ON,x
	rep #$20
_wh_move:
	; a += w, r += rsh( v, 8 ) in page A:
	pea PHYS_DPA
	pld
	ldx.b T0                    ; (save T0 of page A)
	phx
	ldx.w phys_dpb+WK
	jsr phys_move
	plx
	stx.b T0
	ldx.w phys_dpb+WK
	lda.b C_W,x
	sta.w phys_dpb+R
	lda.b C_W+2,x
	sta.w phys_dpb+R+2
	pea PHYS_DPB
	pld
	rts

;---------------------------------------------------------------------------
; Objects (D = PHYS_DPA).

; sprite (utkozikesprite): A = the first active object within the
; circle at T0, T1 (P) of lim T2 (P) and square limit T3 (2^-30 m^2), or
; $FFFF.
phys_sprite:
	.ACCU 16
	.INDEX 16
	stz.b T2+2                  ; the object
	ldy #0
_sp_loop:
	lda.b T2+2
	cmp.w phys_nobjs
	bcc +
	lda #$FFFF
	rts
+	tyx
	lda.l phys_objs+2,x
	and #$FF00                  ; active
	bne _far15
	jmp _sp_next
_far15:
	lda.b T0
	sec
	sbc.l phys_objs+4,x
	sta.b R
	lda.b T0+2
	sbc.l phys_objs+6,x
	sta.b R+2
	jsr _sp_within
	bcs _far16
	jmp _sp_next
_far16:
	lda.b T1
	sec
	sbc.l phys_objs+8,x
	sta.b R2
	lda.b T1+2
	sbc.l phys_objs+10,x
	sta.b R2+2
	lda.b R2
	sta.b R
	lda.b R2+2
	sta.b R+2
	jsr _sp_within
	bcs _far17
	jmp _sp_next
_far17:
	; (dx >> 1)^2 + (dy >> 1)^2 < sq:
	phy
	lda.l phys_objs+4,x
	sta.b R2                    ; (dx again)
	lda.b T0
	sec
	sbc.b R2
	sta.b R2
	lda.b T0+2
	sbc.l phys_objs+6,x
	cmp #$8000
	ror a
	ror.b R2
	lda.b T1
	sec
	sbc.l phys_objs+8,x
	sta.b R2+2
	lda.b T1+2
	sbc.l phys_objs+10,x
	cmp #$8000
	ror a
	ror.b R2+2
	SQUARE R2
	lda.b R+2
	pha
	lda.b R
	pha
	SQUARE R2+2
	pla
	clc
	adc.b R
	tax
	pla
	adc.b R+2
	ply
	cmp.b T3+2
	bcc _sp_hit
	bne _sp_next
	cpx.b T3
	bcc _sp_hit
_sp_next:
	tya
	clc
	adc #12
	tay
	inc.b T2+2
	jmp _sp_loop
_sp_hit:
	lda.b T2+2
	rts
; C set if -T2 < R < T2 (T2 up to 65535):
_sp_within:
	.ACCU 16
	.INDEX 16
	lda.b R+2
	beq +
	inc a
	bne ++
	lda.b R
	clc
	adc.b T2
	beq ++
	bcs +++
++	clc
	rts
+	lda.b R
	cmp.b T2
	bcs ++
+++	sec
	rts
++	clc
	rts

; vizsgalat's objects: eats, kills, finishes (EV).
phys_objects:
	.ACCU 16
	.INDEX 16
	stz.w pt_tmp+6              ; dead
	stz.w pt_tmp+8              ; finished
_ob_again:
	stz.w pt_tmp+10             ; again
	stz.w pt_tmp+12             ; the circle: 0 kor2, 1 kor4, 2 the head
_ob_circle:
	lda.w pt_tmp+12
	cmp #2
	beq +
	asl a
	asl a
	asl a
	sta.b T0
	asl a
	clc
	adc.b T0                    ; 24 k
	tax
	lda.b S_K2+C_RX,x
	sta.b T0
	lda.b S_K2+C_RX+2,x
	sta.b T0+2
	lda.b S_K2+C_RY,x
	sta.b T1
	lda.b S_K2+C_RY+2,x
	sta.b T1+2
	lda #OBJ_WHEEL_P & $FFFF
	sta.b T2
	lda #OBJ_WHEEL_SQ & $FFFF
	sta.b T3
	lda #OBJ_WHEEL_SQ >> 16
	sta.b T3+2
	bra ++
+	MOV32 T0, S_HEADX
	MOV32 T1, S_HEADY
	lda #OBJ_HEAD_P
	sta.b T2
	lda #OBJ_HEAD_SQ & $FFFF
	sta.b T3
	lda #OBJ_HEAD_SQ >> 16
	sta.b T3+2
++	jsr phys_sprite
	cmp #$FFFF
	beq _ob_next
	sta.b T0                    ; the object
	asl a
	clc
	adc.b T0
	asl a
	asl a
	tax                         ; 12 o
	lda.l phys_objs,x
	and #$00FF
	cmp #3
	bne +
	inc.w pt_tmp+6              ; a killer
	bra _ob_next
+	cmp #2
	bne ++
	; An apple: eaten, its gravity.
	sep #$20
	lda #0
	sta.l phys_objs+3,x
	inc.b S_APPLES
	lda.l phys_objs+2,x
	beq +
	dec a
	sta.b S_GRAVITY
+	rep #$20
	inc.w pt_tmp+10
	lda.b T0
	sta.w phys_eaten
	lda.b EV
	ora #PH_EAT
	sta.b EV
	bra _ob_next
++	cmp #1
	bne _ob_next
	lda.b S_APPLES              ; the flower, with all the apples
	and #$00FF
	cmp.w lev_need
	bcc _ob_next
	inc.w pt_tmp+8
_ob_next:
	inc.w pt_tmp+12
	lda.w pt_tmp+12
	cmp #3
	bcs +
	jmp _ob_circle
+	lda.w pt_tmp+10
	beq +
	jmp _ob_again
+	lda.w pt_tmp+8
	beq +
	lda.b EV
	ora #PH_FINISH
	sta.b EV
	rts
+	lda.w pt_tmp+6
	beq +
	lda.b EV
	ora #PH_DEAD
	sta.b EV
+	rts

;---------------------------------------------------------------------------
; u16 phys_step(u16 input)
phys_step:
	.ACCU 16
	.INDEX 16
	php
	phb
	phd
	rep #$30
	lda 8,s
	sta.l pt_tmp
	PHYS_ENTER
	lda.w pt_tmp
	sta.b IN
	stz.b EV
	stz.b RACS
	stz.w phys_bump
	stz.w pt_fric
	stz.w pt_fric+2
	stz.w pt_crs
	stz.w pt_crs+2
	stz.w pt_crd
	stz.w pt_crd+2
	; w1 = rsh( body.w, 4 ) and its signed bytes:
	MOV32 W1, S_BODY+C_W
	RSH32 W1, 4
	MOV32 T3, W1
	CLAMP24 T3
	sep #$20
	DIG24 T3, WD
	rep #$20
	jsr phys_torques
	jsr phys_anchors
	lda #S_K2
	sta.b CK
	stz.b CK4
	jsr phys_erok
	lda #S_K4
	sta.b CK
	lda #4
	sta.b CK4
	jsr phys_erok
	jsr phys_volts
	jsr phys_gravity
	jsr phys_rider
	; beallit of the body: w += -MULK( rsh( cross_s, 2 ), K_TS )
	; - MULK( rsh( cross_d, 8 ), K_TD ):
	MOV32W phys_dpa+T0, pt_crs
	RSH32 T0, 2
	MULK T0, K_TS
	SUB32 S_BODY+C_W, S_BODY+C_W, R
	MOV32W phys_dpa+T0, pt_crd
	RSH32 T0, 8
	MULK T0, K_TD
	SUB32 S_BODY+C_W, S_BODY+C_W, R
	MOV32W pt_da, phys_dpa+S_BODY+C_W
	; v += -MULK( Dx0+Dx1, K_20 )+gv:
	lda.w pt_dx
	clc
	adc.w pt_dx+4
	sta.b T0
	lda.w pt_dx+2
	adc.w pt_dx+6
	sta.b T0+2
	MULK T0, K_20
	SUB32 S_BODY+C_VX, S_BODY+C_VX, R
	ADD32 S_BODY+C_VX, S_BODY+C_VX, GVX
	lda.w pt_dy
	clc
	adc.w pt_dy+4
	sta.b T0
	lda.w pt_dy+2
	adc.w pt_dy+6
	sta.b T0+2
	MULK T0, K_20
	SUB32 S_BODY+C_VY, S_BODY+C_VY, R
	ADD32 S_BODY+C_VY, S_BODY+C_VY, GVY
	ldx #S_BODY
	jsr phys_move
	; The wheels:
	stz.w pt_k
_st_wheel:
	lda.w pt_k
	asl a
	asl a
	tay
	lda.w pt_dx,y
	clc
	adc.b GVX
	sta.b FX
	lda.w pt_dx+2,y
	adc.b GVX+2
	sta.b FX+2
	lda.w pt_dy,y
	clc
	adc.b GVY
	sta.b FY
	lda.w pt_dy+2,y
	adc.b GVY+2
	sta.b FY+2
	lda.w pt_m,y
	sta.b MK
	lda.w pt_m+2,y
	sta.b MK+2
	lda.w pt_k
	beq +
	lda #S_K4
	ldx #S_ROLL+R_SIZE
	bra ++
+	lda #S_K2
	ldx #S_ROLL
++	sta.w phys_dpb+WK
	stx.w phys_dpb+WR
	pea PHYS_DPB
	pld
	jsr phys_wheel
	pea PHYS_DPA
	pld
	lda.w pt_k
	asl a
	asl a
	tay
	lda.w phys_dpb+R
	sta.w pt_da+4,y
	lda.w phys_dpb+R+2
	sta.w pt_da+6,y
	inc.w pt_k
	lda.w pt_k
	cmp #2
	bcc _st_wheel
	; defl[k] += rsh( da[k]-da1, 8 ):
	ldy #0
-	lda.w pt_da+4,y
	sec
	sbc.w pt_da
	sta.b T0
	lda.w pt_da+6,y
	sbc.w pt_da+2
	sta.b T0+2
	RSH32 T0, 8
	lda.w phys_dpa+S_DEFL,y
	clc
	adc.b T0
	sta.w phys_dpa+S_DEFL,y
	lda.w phys_dpa+S_DEFL+2,y
	adc.b T0+2
	sta.w phys_dpa+S_DEFL+2,y
	iny
	iny
	iny
	iny
	cpy #8
	bcc -
	jsr phys_trig
	jsr phys_head
	; The counters of the volts:
	sep #$20
	lda.b S_LASTVOLT
	inc a
	beq +
	sta.b S_LASTVOLT
+	lda.b S_VOLTT
	inc a
	beq +
	sta.b S_VOLTT
+	lda.b S_VOLTT+1
	inc a
	beq +
	sta.b S_VOLTT+1
+	rep #$20
	; The sounds: friction, the driven wheel's omega.
	lda.w pt_fric+2
	beq +
	lda #$FFFF
	bra ++
+	lda.w pt_fric
++	sta.w phys_friction
	ldx #S_K4+C_W
	lda.b S_TURNED
	and #$00FF
	beq +
	ldx #S_K2+C_W
+	lda.b 0,x
	sta.b T0
	lda.b 2,x
	sta.b T0+2
	bpl +
	lda #0
	sec
	sbc.b T0
	sta.b T0
	lda #0
	sbc.b T0+2
	sta.b T0+2
+	lda.b T0+1                  ; >> 8 (|w| < 2^31: fits after)
	sta.b T1
	lda.b T0+3
	and #$00FF
	sta.b T1+2
	MULK T1, K_OMEGA
	lda.b R+2
	beq +
	lda #$FFFF
	bra ++
+	lda.b R
++	sta.w phys_wheel_omega
	; vizsgalat: the head against the lines.
	lda.b S_HEADX
	sta.w phys_dpb+QRX
	lda.b S_HEADX+2
	sta.w phys_dpb+QRX+2
	lda.b S_HEADY
	sta.w phys_dpb+QRY
	lda.b S_HEADY+2
	sta.w phys_dpb+QRY+2
	lda #R_HEAD_P
	sta.w phys_dpb+QR
	lda #R_HEAD_SQ & $FFFF
	sta.w phys_dpb+QRSQ
	lda #R_HEAD_SQ >> 16
	sta.w phys_dpb+QRSQ+2
	lda #1
	sta.w phys_dpb+QHEAD
	pea PHYS_DPB
	pld
	jsr phys_contacts
	pea PHYS_DPA
	pld
	cmp #0
	bne _st_dead
	; Out of the level:
	lda.b RACS
	bne _st_dead
	lda.b S_BODY+C_RX
	cmp.w lev_kill
	lda.b S_BODY+C_RX+2
	sbc.w lev_kill+2
	bvc +
	eor #$8000
+	bmi _st_dead
	lda.b S_BODY+C_RX
	cmp.w lev_kill+4
	lda.b S_BODY+C_RX+2
	sbc.w lev_kill+6
	bvc +
	eor #$8000
+	bpl _st_dead
	lda.b S_BODY+C_RY
	cmp.w lev_kill+8
	lda.b S_BODY+C_RY+2
	sbc.w lev_kill+10
	bvc +
	eor #$8000
+	bmi _st_dead
	lda.b S_BODY+C_RY
	cmp.w lev_kill+12
	lda.b S_BODY+C_RY+2
	sbc.w lev_kill+14
	bvc +
	eor #$8000
+	bpl _st_dead
	jsr phys_objects
	bra _st_end
_st_dead:
	lda.b EV
	ora #PH_DEAD
	sta.b EV
_st_end:
	jsr phys_mkview
	lda.b EV
	sta.w pt_tmp
	pld
	plb
	lda.l pt_tmp
	sta.b tcc__r0
	plp
phys_step_ret:                  ; (for measuring the time of a step)
	rtl

.ENDS
