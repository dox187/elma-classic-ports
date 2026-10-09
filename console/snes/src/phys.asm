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

; Work variables of the parts of the step (low RAM, absolute addresses):
.RAMSECTION ".phys_work" BANK 0 SLOT 1
g1_ram              dsb 32      ; the springs (torques ... gravity)
g2_ram              dsb 32      ; the body, the rider, the view
g3_ram              dsb 32      ; the collisions and the objects
g1x_ram             dsb 32      ; more of each part
g2x_ram             dsb 32
g3x_ram             dsb 32
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

;---------------------------------------------------------------------------
; G2 helpers (the body, the rider, the view), A 16-bit.

; The multiplicand of the multiplier = A (A is byte-swapped after it; it
; also starts a useless product): the 16-bit stores to $211B write $211C
; too, which leaves its byte in the shared latch of the Mode 7 registers.
.MACRO G2_MA
	xba
	sta.w MPYA
	sta.w MPYA
.ENDM

; The multiplicand = the constant \1 (A is changed).
.MACRO G2_MAK
	lda #(((\1) >> 8) & $FF) | (((\1) & $FF) << 8)
	sta.w MPYA
	sta.w MPYA
.ENDM

; Kept from the head of a step for the rider of the next one (low RAM):

.DEFINE g2_ofxb g2_ram+0        ; rsh( mq16( Sn, K44_15 ), 6 )+32768-1
.DEFINE g2_ofyb g2_ram+2        ; rsh( mq16( Cs, K44_15 ), 6 )+32768+1

; The rider (phys_rider): page A bytes, low RAM.
.DEFINE G2_DX $DA               ; dx, dy (2^-15 m) for the exact x, y
.DEFINE G2_DY $DC
.DEFINE G2_FLAG $DE             ; 0: the fast case
.DEFINE G2_IX $FC               ; 2*(dirx+4079), 2*(diry+4079) of the spring
.DEFINE G2_IY $FE
.DEFINE g2_w g2_ram+4           ; body.w at the start of the step
.DEFINE g2_sxr g2_ram+8         ; the box of phys_rider: 2*(s-G2_RB+4079)
.DEFINE g2_syr g2_ram+10        ; with s = (-Sn, Cs)*G2_SK/256
.DEFINE G2_SK 12
.DEFINE G2_RB 2000
.DEFINE G2_OA 2610              ; the octagon after the box: a vertex
.DEFINE G2_OB 3690              ; (2610, 1080) within 2825

; A = (A+64) >> 7, signed (A+64 within 16 bits).
.MACRO G2_SHR7
	clc
	adc #64
	asl a
	xba
	and #$00FF
	bcc _g2s7\@
	ora #$FF00
_g2s7\@:
.ENDM

; The double word \1 += rsh( \2, 8 ) = (\2 >> 8)+bit 7 of \2; X is used.
; With a third argument A is \2+2 already, and N its sign.
.MACRO G2_ADDRSH8
	.IF NARGS == 2
	lda.b \2+2
	.ENDIF
	bmi _g2ar_n\@
	xba
	and #$00FF
	bra _g2ar_e\@
_g2ar_n\@:
	xba
	ora #$FF00
_g2ar_e\@:
	tax
	lda.b \2
	xba
	asl a
	lda.b \2+1
	adc.b \1
	sta.b \1
	txa
	adc.b \1+2
	sta.b \1+2
.ENDM

; Y = G of G2_MULKS for \1 = x+$808080 (in range), s = \2; \1 is used.
.MACRO G2_MKG
	lda.b \1
	eor #$8080
	sta.w MPYB                  ; *e0
	xba
	tay
	lda.w MPYM
	clc
	.IF \2 == 0
	adc #16384+128
	.ELSE
	adc #16384
	.ENDIF
	sta.b \1
	sty.w MPYB                  ; *e1
	lda.w MPYL
	and #$00FF
	clc
	adc.b \1
	xba
	and #$00FF
	clc
	adc.w MPYM
	sec
	.IF \2 == 0
	sbc #64
	.ELSE
	sbc #64-(1 << (\2-1))
	.ENDIF
	tay
.ENDM

; \1 = floor( (x*M+2^(15+s))/2^(16+s) ) (MULK for K_SH = 24+s) for the
; double word \1 = x+$808080 (clamped here), s = \2 (0 to 3) and the
; multiplicand M: with x*M = P0+256*P1+65536*P2 (the signed bytes e0, e1,
; e2 of x are the bytes of \1 xor $80), P0 = 256*W0+.., P1 = 256*V1+l1, it
; is (P2+G) >> s for G = V1+floor( (W0+l1+(s ? 0 : 128))/256 )+(s ? 2^(s-1)
; : 0). X and Y are used. With a third argument a result of two bytes
; (|G| < 32768) is left as it is with \1+2 = $8000.
.MACRO G2_MULKS
	lda.b \1+2
	cmp #$0080
	bne _g2md_x\@
	G2_MKG \1, \2
	tya
	.REPT \2
	cmp #$8000
	ror a
	.ENDR
	sta.b \1
	.IF NARGS == 3
	lda #$8000                  ; (a 16-bit result)
	sta.b \1+2
	.ELSE
	ldx #0
	cmp #$8000
	bcc _g2md_p\@
	dex
_g2md_p\@:
	stx.b \1+2
	.ENDIF
	jmp _g2md_e\@
_g2md_x\@:
	tax                         ; (N of \1+2)
	bmi _g2md_lo\@
	cmp #$0100
	bcc _g2md_3\@
	lda #$FFFF
	sta.b \1
	lda #$00FF
	sta.b \1+2
	bra _g2md_3\@
_g2md_lo\@:
	stz.b \1
	stz.b \1+2
_g2md_3\@:
	G2_MKG \1, \2
	lda.b \1+2
	eor #$0080
	sta.w MPYB                  ; *e2
	tya
	eor #$8000
	clc
	adc.w MPYL
	sta.b \1
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #0                      ; P2+G+$808000
	.REPT \2
	lsr a
	ror.b \1
	.ENDR
	tax
	lda.b \1
	sec
	sbc #($808000 >> \2) & $FFFF
	sta.b \1
	txa
	sbc #($808000 >> \2) >> 16
	sta.b \1+2
_g2md_e\@:
.ENDM

; A = V1+floor( (W0+l1+128)/256 )+64 for the products 2d*w0 = 256*W0+..
; and 2d*w1 = 256*V1+l1 of the multiplicand 2d (in [-32768, 32766]) and
; the signed bytes WD; T0 is used.
.MACRO G2_WQ
	lda.b WD
	sta.w MPYB                  ; *w0
	lda.w MPYM
	clc
	adc #128+16384
	sta.b T0
	lda.b WD+1
	sta.w MPYB                  ; *w1
	lda.w MPYL
	and #$00FF
	clc
	adc.b T0
	xba
	and #$00FF
	clc
	adc.w MPYM
.ENDM

; A = MULK( x, K_RIDER_D )+32 for \1 = x+$808080 of two signed bytes (\1+2
; = $0080) and the multiplicand K_RIDER_D_M/2: (G+64) >> 1 with G of
; G2_MKG (s = 1); Y and \1 are used.
.MACRO G2_DMP
	lda.b \1
	eor #$8080
	sta.w MPYB                  ; *e0
	xba
	tay
	lda.w MPYM
	clc
	adc #16384+256
	sta.b \1
	sty.w MPYB                  ; *e1
	lda.w MPYL
	and #$00FF
	clc
	adc.b \1
	xba
	and #$00FF
	clc
	adc.w MPYM
	cmp #$8000
	ror a
.ENDM

; \2 -= MULK( x, K_RIDER_D ) for \1 = x+$808080 (any, clamped here) and the
; multiplicand K_RIDER_D_M/2: (G+P) >> 1 with G of G2_DMP (G2_MKG, s = 1)
; and P = M*e2 (the third signed byte), as (G+32768+P+$800000) >> 1 =
; MULK+$404000. T0, Y and \1 are used.
.MACRO G2_DMP3
	lda.b \1+2
	cmp #$0100
	bcc _g2d3_in\@
	bmi _g2d3_lo\@
	lda #$FFFF
	sta.b \1
	lda #$00FF
	sta.b \1+2
	bra _g2d3_in\@
_g2d3_lo\@:
	stz.b \1
	stz.b \1+2
_g2d3_in\@:
	lda.b \1
	eor #$8080
	sta.w MPYB                  ; *e0
	xba
	tay
	lda.w MPYM
	clc
	adc #16384+256
	sta.b T0
	sty.w MPYB                  ; *e1
	lda.w MPYL
	and #$00FF
	clc
	adc.b T0
	xba
	and #$00FF
	clc
	adc.w MPYM
	clc
	adc #32768-64
	sta.b T0                    ; G+32768
	lda.b \1+2
	eor #$0080
	sta.w MPYB                  ; *e2
	lda.w MPYL
	clc
	adc.b T0
	sta.b T0
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #0
	lsr a
	ror.b T0
	sta.b T0+2                  ; MULK+$404000
	lda.b \2
	sec
	sbc.b T0
	tax
	lda.b \2+2
	sbc.b T0+2
	tay
	txa
	clc
	adc #$4000
	sta.b \2
	tya
	adc #$0040
	sta.b \2+2
.ENDM

; The double word \1 += A (signed 16-bit, N its sign), then the double word
; \2 += rsh( \1, 8 ); X is used.
.MACRO G2_VPOS
	bmi _g2vp_n\@
	clc
	adc.b \1
	sta.b \1
	lda.b \1+2
	adc #0
	bra _g2vp_s\@
_g2vp_n\@:
	clc
	adc.b \1
	sta.b \1
	lda.b \1+2
	adc #$FFFF
_g2vp_s\@:
	sta.b \1+2
	bmi _g2vp_m\@
	xba
	and #$00FF
	bra _g2vp_x\@
_g2vp_m\@:
	xba
	ora #$FF00
_g2vp_x\@:
	tax
	lda.b \1-1                  ; bit 15: bit 7 of \1
	asl a
	lda.b \1+1
	adc.b \2
	sta.b \2
	txa
	adc.b \2+2
	sta.b \2+2
.ENDM

.IF SEAT_NX != -13923 || SEAT_NY != 29663 || SEAT_C8 != 1117372
.FAIL "phys_rider: the seat constants"
.ENDIF
.IF RIDER_ELL != 30247 || RIDER_TOP_SQ != 247401441 || RIDER_RIGHT != 8520 || RIDER_TOP != 15729 || RIDER_LEFT != -16384
.FAIL "phys_rider: g2_ellt"
.ENDIF
.IF K_RIDER_D_SH != 18 || K_RIDER_S_SH != 13 || (K_RIDER_D_M & 1) != 0
.FAIL "phys_rider: the shifts of K_RIDER_D, K_RIDER_S"
.ENDIF

; The largest y with xs^2+y^2 <= RIDER_TOP_SQ for each x >> 8 (xs of the
; largest x of the range), 0 to RIDER_RIGHT:
g2_ellt:
	.dw 15721, 15700, 15665, 15615, 15550, 15471, 15377, 15268, 15143, 15002
	.dw 14845, 14671, 14480, 14270, 14041, 13793, 13523, 13231, 12914, 12573
	.dw 12203, 11803, 11370, 10898, 10385, 9821, 9198, 8505, 7720, 6814
	.dw 5727, 4327, 2056, 0

; \2 = the angle of the circle \1 as 65536 a turn, for the multiplicand
; 4*K_WVIEW_M-65536 = 17908: with x = a >> 15 it is x+floor( (17908*x
; +2^15)/2^16 ) = x+V+((W0+l+128) >> 8) for 17908*x0 = 256*W0+.., 17908*x1
; = 256*V+l (x0, x1 the signed bytes of x); T0, T1 and X are used.
.IF K_WVIEW_M != 20861 || K_WVIEW_SH != 14
.FAIL "G2_ANG16: 4*K_WVIEW_M = 65536+17908"
.ENDIF
.MACRO G2_ANG16
	lda.b \1+C_A
	asl a
	lda.b \1+C_A+2
	rol a                       ; x
	sta.b T0
	sta.w MPYB                  ; *x0
	clc
	adc #$0080
	xba
	tax                         ; x1
	lda.w MPYM
	clc
	adc #16384+128
	sta.b T1
	stx.w MPYB                  ; *x1
	lda.w MPYL
	and #$00FF
	clc
	adc.b T1
	xba
	and #$00FF
	clc
	adc.w MPYM
	clc
	adc.b T0
	sec
	sbc #64
	sta.w \2
.ENDM

; \2 = qsin( \1 ) for the double word \1 in [0, pi/2] (W) of the direct
; page, -qsin( \1 ) for \3 = 1: the table value t plus v = floor( (f*d
; +16384)/32768 ) = h+((W0+l+128+16384) >> 8)-64, with f the multiplicand
; and e = 2d in signed bytes (f*e0 = 256*W0+.., f*e1 = 256*h+l), from
; g2_qs at 8i (i = b >> 19); -(t+v) = ~(t+v-1). T2 and X are used.
.MACRO G2_QSIN
	lda.b \1+2
	and #$FFF8
	tax                         ; 8i
	lda.b \1
	asl a
	asl a
	asl a
	asl a                       ; the low byte of f, in the high byte
	sta.w MPYA
	lda.b \1+1
	lsr a
	lsr a
	lsr a
	lsr a
	and #$007F                  ; the high byte of f
	sta.w MPYA
	lda.l g2_qs+4,x
	sta.w MPYB                  ; f*e0
	lda.w MPYM
	clc
	adc #16512
	sta.b T2
	lda.l g2_qs+6,x
	sta.w MPYB                  ; f*e1
	lda.w MPYL
	and #$00FF
	clc
	adc.b T2
	xba
	and #$00FF
	clc
	adc.w MPYM
	sec
	sbc #64+\3                  ; v (v-1)
	bmi _g2qs_neg\@
	clc
	adc.l g2_qs,x
	.IF \3 != 0
	eor #$FFFF
	.ENDIF
	sta.b \2
	lda.l g2_qs+2,x
	adc #0
	bra _g2qs_end\@
_g2qs_neg\@:
	clc
	adc.l g2_qs,x
	.IF \3 != 0
	eor #$FFFF
	.ENDIF
	sta.b \2
	lda.l g2_qs+2,x
	adc #$FFFF
_g2qs_end\@:
	.IF \3 != 0
	eor #$FFFF
	.ENDIF
	sta.b \2+2
.ENDM

; A = q15( \1 ) for \1 in [0, 2^22] (a double word of the direct page): \1
; >> 7, at most 32767.
.MACRO G2_Q15P
	lda.b \1-1
	asl a                       ; bit 7 of \1
	lda.b \1+1
	rol a
	bpl _g2qp\@
	lda #32767
_g2qp\@:
.ENDM

; A = q15( \1 ) for \1 in [-2^22, 0].
.MACRO G2_Q15N
	lda.b \1-1
	asl a
	lda.b \1+1
	rol a
	cmp #$8000
	bne _g2qn\@
	inc a
_g2qn\@:
.ENDM

; \3 = \2 + rsh( 256*HV+E, 6 ) for A = E+\4 (E+32+32768 in [0, 65535]) and
; HV = \1 (a word of the direct page, |HV| < 16000): with U = E+32+32768,
; G = HV+(U >> 8)-128 and r = (U >> 6) & 3 it is 4G+r, whose sign is G's.
; T2 and Y are used.
.MACRO G2_HEADADD
	clc
	adc #(32+32768-\4) & $FFFF
	tay
	and #$00C0
	asl a
	asl a
	xba
	sta.b T2                    ; r
	tya
	xba
	and #$00FF
	clc
	adc.b \1
	sec
	sbc #128                    ; G
	bmi _g2ha_neg\@
	asl a
	asl a
	ora.b T2
	clc
	adc.b \2
	sta.b \3
	lda.b \2+2
	adc #0
	bra _g2ha_end\@
_g2ha_neg\@:
	asl a
	asl a
	ora.b T2
	clc
	adc.b \2
	sta.b \3
	lda.b \2+2
	adc #$FFFF
_g2ha_end\@:
	sta.b \3+2
.ENDM

; The offsets of the rider's rest over the body, for phys_rider (g2_ofxb):
; rsh( mq16( \2, K44_15 ), 6 ), plus \3. The multiplicand is X = \2: it is
; floor( (4*K44_15*X+2^15)/2^16 ) with 4*K44_15 = 65536-31*256+72: X+V1
; +((W0+l1+128+16384) >> 8)-64 (X*72 = 256*W0+.., -31*X = 256*V1+l1).
.MACRO G2_OFF44
	lda #72
	sta.w MPYB
	lda.w MPYM
	clc
	adc #16512
	sta.b T2
	lda #$00E1                  ; -31
	sta.w MPYB
	lda.w MPYL
	and #$00FF
	clc
	adc.b T2
	xba
	and #$00FF
	clc
	adc.w MPYM
	clc
	adc.b \2
	clc
	adc #\3-64
	sta.w \1
.ENDM

; trig: CS22, SN22, CS, SN of the angle a of the body, then phys_head. With
; b = |a|: sin( b ), cos( b ) = qsin( b ), qsin( HALFPI_W-b ) for b <=
; HALFPI_W, else qsin( PI_W-b ), -qsin( b-HALFPI_W ).
phys_trig:
	.ACCU 16
	.INDEX 16
	lda.b S_BODY+C_A+2
	bpl _g2tr_p
	lda.b S_BODY+C_A
	clc
	adc #HALFPI_W & $FFFF
	sta.b T0
	lda.b S_BODY+C_A+2
	adc #HALFPI_W >> 16
	sta.b T0+2                  ; HALFPI_W-b
	bmi _g2tr_n2
	lda #0
	sec
	sbc.b S_BODY+C_A
	sta.b T1
	lda #0
	sbc.b S_BODY+C_A+2
	sta.b T1+2                  ; b
	jmp _g2tr_n
_g2tr_p2:
	; b > HALFPI_W: PI_W-b and b-HALFPI_W, T3 bit 15: the sin is negative.
	lda #PI_W & $FFFF
	sec
	sbc.b S_BODY+C_A
	sta.b T1
	lda #PI_W >> 16
	sbc.b S_BODY+C_A+2
	sta.b T1+2
	lda #0
	bra _g2tr_b2
_g2tr_n2:
	lda.b S_BODY+C_A
	clc
	adc #PI_W & $FFFF
	sta.b T1
	lda.b S_BODY+C_A+2
	adc #PI_W >> 16
	sta.b T1+2
	lda #$8000
_g2tr_b2:
	sta.b T3
	lda #0
	sec
	sbc.b T0
	sta.b T0
	lda #0
	sbc.b T0+2
	sta.b T0+2                  ; b-HALFPI_W
	jmp _g2tr_b
_g2tr_p:
	lda #HALFPI_W & $FFFF
	sec
	sbc.b S_BODY+C_A
	sta.b T0
	lda #HALFPI_W >> 16
	sbc.b S_BODY+C_A+2
	sta.b T0+2                  ; HALFPI_W-b
	bmi _g2tr_p2
	G2_QSIN S_BODY+C_A, SN22, 0
	G2_Q15P SN22
	sta.b SN
	G2_QSIN T0, CS22, 0
	G2_Q15P CS22
	sta.b CS
	jmp _g2hd_cs
_g2tr_n:
	G2_QSIN T1, SN22, 1
	G2_Q15N SN22
	sta.b SN
	G2_QSIN T0, CS22, 0
	G2_Q15P CS22
	sta.b CS
	jmp _g2hd_cs
_g2tr_b:
	G2_QSIN T0, CS22, 1
	G2_Q15N CS22
	sta.b CS
	G2_QSIN T1, SN22, 0
	lda.b T3
	bmi +
	G2_Q15P SN22
	sta.b SN
	jmp phys_head
+	lda #0
	sec
	sbc.b SN22
	sta.b SN22
	lda #0
	sbc.b SN22+2
	sta.b SN22+2
	G2_Q15N SN22
	sta.b SN


; szamitfejr for hx = K09_15 (\1 = 1, turned) or -K09_15 (\1 = 0), after
; the multiplicand Cs: head = rider + rsh( mq16( Cs, hx )+mq16( Sn, -K63_15
; ), 6 ), ..., each product as W0+256*V+l (the signed bytes of the
; constants); also g2_ofxb, g2_ofyb (OFY with Cs*2*K44_15 = Cs*(256*113
; -92): the low byte is K63_15's) and the box of phys_rider, s = (-Sn,
; Cs)*12/256 from V of Cs*hx1, Sn*hx1 (hx1 = 12 or -12).
.MACRO G2_HEAD
	.IF \1 == 0
	ldx #$F47B                  ; -K09_15: 123, -12
	ldy #$00F4
	.ELSE
	ldx #$0C85                  ; K09_15: -123, 12
	ldy #$000C
	.ENDIF
	stx.w MPYB                  ; Cs*hx0
	lda.w MPYM
	sta.b T0                    ; Ex
	sty.w MPYB                  ; Cs*hx1
	lda.w MPYL
	and #$00FF
	clc
	adc.b T0
	sta.b T0
	lda.w MPYM
	sta.b T0+2                  ; HVx
	asl a
	.IF \1 == 0
	eor #$FFFF
	sec
	.ELSE
	clc
	.ENDIF
	adc #2*(4079-G2_RB)
	sta.w g2_syr
	lda #$00A4
	sta.w MPYB                  ; Cs*(-92)
	lda.w MPYM
	clc
	adc #16384+64
	sta.b T1                    ; Ey+16448
	lda #113
	sta.w MPYB                  ; Cs*113
	; OFY = rsh( mq16( Cs, K44_15 ), 6 ) = floor( (Cs*2*K44_15+2^14)/2^15 )
	; = 2*V+((W0+l+64) >> 7) for Cs*(-92) = 256*W0+.., Cs*113 = 256*V+l:
	lda.w MPYL
	and #$00FF
	clc
	adc.b T1
	asl a
	xba
	and #$00FF                  ; ((W0+l+64) >> 7)+128
	clc
	adc.w MPYM
	clc
	adc.w MPYM
	clc
	adc #32768+1-128
	sta.w g2_ofyb
	lda #81
	sta.w MPYB                  ; Cs*81
	lda.w MPYL
	and #$00FF
	clc
	adc.b T1
	sta.b T1
	lda.w MPYM
	sta.b T1+2                  ; HVy
	lda.b SN
	G2_MA
	lda #92
	sta.w MPYB                  ; Sn*92
	lda.w MPYM
	clc
	adc.b T0
	sta.b T0
	stx.w MPYB                  ; Sn*hx0
	lda.w MPYM
	clc
	adc.b T1
	sta.b T1
	sty.w MPYB                  ; Sn*hx1
	lda.w MPYM
	tax
	clc
	adc.b T1+2
	sta.b T1+2
	txa
	asl a
	.IF \1 == 0
	clc
	.ELSE
	eor #$FFFF
	sec
	.ENDIF
	adc #2*(4079-G2_RB)
	sta.w g2_sxr
	lda.w MPYL
	and #$00FF
	clc
	adc.b T1
	G2_HEADADD T1+2, S_RIDY, S_HEADY, 16448
	lda #$00AF
	sta.w MPYB                  ; Sn*(-81)
	lda.w MPYM
	clc
	adc.b T0+2
	sta.b T0+2
	lda.w MPYL
	and #$00FF
	clc
	adc.b T0
	G2_HEADADD T0+2, S_RIDX, S_HEADX, 0
	G2_OFF44 g2_ofxb, SN, 32768-1
.ENDM

; szamitfejr: the head from the rider and the angle (CS, SN), G2_HEAD.
.IF K09_15 != $0B85 || K63_15 != $50A4 || 2*K44_15 != 113*256-92
.FAIL "phys_head: the signed bytes of the constants"
.ENDIF
phys_head:
	.ACCU 16
	.INDEX 16
	lda.b CS
_g2hd_cs:
	G2_MA
	lda.b S_TURNED
	and #$00FF
	beq +
	jmp _g2hd_t
+	G2_HEAD 0
	rts
_g2hd_t:
	G2_HEAD 1
	rts

; phys_view from the state; the angles as 65536 a turn: rsh( mq24( a >> 15,
; K_WVIEW ), K_WVIEW_SH-8 ).
.MACRO G2_VIEW
	lda.b S_BODY+C_RX
	sta.w phys_view+0
	lda.b S_BODY+C_RX+2
	sta.w phys_view+2
	lda.b S_BODY+C_RY
	sta.w phys_view+4
	lda.b S_BODY+C_RY+2
	sta.w phys_view+6
	lda.b S_K2+C_RX
	sta.w phys_view+12
	lda.b S_K2+C_RX+2
	sta.w phys_view+14
	lda.b S_K4+C_RX
	sta.w phys_view+16
	lda.b S_K4+C_RX+2
	sta.w phys_view+18
	lda.b S_K2+C_RY
	sta.w phys_view+20
	lda.b S_K2+C_RY+2
	sta.w phys_view+22
	lda.b S_K4+C_RY
	sta.w phys_view+24
	lda.b S_K4+C_RY+2
	sta.w phys_view+26
	lda.b S_RIDX
	sta.w phys_view+32
	lda.b S_RIDX+2
	sta.w phys_view+34
	lda.b S_RIDY
	sta.w phys_view+36
	lda.b S_RIDY+2
	sta.w phys_view+38
	lda.b S_HEADX
	sta.w phys_view+40
	lda.b S_HEADX+2
	sta.w phys_view+42
	lda.b S_HEADY
	sta.w phys_view+44
	lda.b S_HEADY+2
	sta.w phys_view+46
	lda.b S_TURNED              ; turned, gravity
	sta.w phys_view+48
	G2_MAK 17908
	G2_ANG16 S_BODY, phys_view+8
	G2_ANG16 S_K2, phys_view+28
	G2_ANG16 S_K4, phys_view+30
.ENDM

; The view of the bike (phys_view) and the other outputs from the state
; (phys_step makes them itself).
phys_mkview:
	.ACCU 16
	.INDEX 16
	jsr _g2_view
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
_g2_view:
	G2_VIEW
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
	lda #$FFFF                  ; no cell of the circles yet
	sta.w g3_ram+2
	sta.w g3_ram+10
	sta.w g3_ram+26
	sta.w g3x_ram+8             ; no candidates of the objects kept (OC_N)
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
	jsr phys_trig               ; and phys_head
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

;---------------------------------------------------------------------------
; G1, the springs (phys_torques ... phys_gravity): helpers. A 16-bit.

.DEFINE G1_W8D $D4              ; signed digits of 8 * clamp24( w1 )
.DEFINE G1_W8OK $D7             ; bit 7 clear when G1_W8D holds them
.DEFINE G1_T $D8                ; a word of scratch

; Per step, from phys_anchors (low RAM; pt_gsx, pt_gsy hold gs):
.DEFINE G1_GS g1_ram+0          ; wheel j at +4j: rsh( gsx, 2 ) and
                                ; -rsh( gsy, 2 ) (+2)

; In phys_erok (page A): the signed digits of relx and rely (r0, r1, r2, 0),
; their dampers, -ky for G1_WSLOW:
.DEFINE G1_RX T1
.DEFINE G1_RY T2
.DEFINE G1_DMX R2               ; MULK( rel, K_DAMP ) + 70 (16-bit, r2 = 0)
.DEFINE G1_DMY T0               ; or + $1010046 (32-bit)
.DEFINE G1_NKY T0
.DEFINE G1_KX1 T2               ; (phys_ftn) the high signed digit of kx

; In phys_erok: cross_s + $808082 and cross_d + $80 (the start values take
; back the $808000 that each term adds); GVX, GVY are set after it.
.DEFINE G1_CRS GVX
.DEFINE G1_CRD GVY

; The multiplicand from A (A byte-swapped after).
.MACRO G1_LDMA
	sep #$20
	sta.w MPYA
	xba
	sta.w MPYA
	rep #$20
.ENDM

; The multiplicand from a word of the direct page.
.MACRO G1_LDMD
	sep #$20
	lda.b \1
	sta.w MPYA
	lda.b \1+1
	sta.w MPYA
	rep #$20
.ENDM

; N = 0 and Z = 1 when the double word \1 is a 16-bit signed number.
.MACRO G1_FITS
	lda.b \1
	asl a
	lda.b \1+2
	adc #0
.ENDM

; \3 = clamp16( rsh( \1 - \2, 3 ) ) and A = \3, \4 = \1 - \2, all in the
; direct page (rsh adds the last bit shifted out).
.MACRO G1_KOTO
	lda.b \1
	sec
	sbc.b \2
	sta.b \3
	sta.b \4
	lda.b \1+2
	sbc.b \2+2
	sta.b \4+2
	cmp #3
	bcc _gk_ok\@
	cmp #$FFFD
	bcc _gk_far\@
_gk_ok\@:
	lsr a
	ror.b \3
	lsr a
	ror.b \3
	lsr a
	ror.b \3
	lda.b \3
	adc #0
	sta.b \3
	bra _gk_d\@
_gk_far\@:
	MOV32 T0, \4
	RSH32 T0, 3
	CLAMP16 T0
	sta.b \3
_gk_d\@:
.ENDM

; \3 = rsh( mq24( w1, M ), 5 ) + \2 - \1 + $8080 for the multiplicand M,
; with the digits of 8 w1 (\1: wheel velocity, \2: body velocity): with
; the products Pi, u0 = P0 >> 8 and P1 = 256 M1 + l1, the rsh is P2 + V for
; V = M1 + ((u0 + l1 + 128) >> 8) (|u0| <= 16320, |V| <= 16320).
.MACRO G1_WTERM
	lda.b G1_W8D
	sta.w MPYB
	lda.w MPYM
	clc
	adc #32768+128
	sta.b G1_T
	lda.b G1_W8D+1
	sta.w MPYB
	lda.w MPYL
	and #$00FF
	clc
	adc.b G1_T
	xba
	and #$00FF
	adc.w MPYM                  ; V + 128
	eor #$8000
	tay                         ; V + $8080
	lda.b G1_W8D+2
	sta.w MPYB
	tya
	clc
	adc.w MPYL
	tay
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #$FF80                  ; the high byte of P2 sign-extended, carry
	tax
	tya
	clc
	adc.b \2
	tay
	txa
	adc.b \2+2
	tax
	tya
	sec
	sbc.b \1
	sta.b \3
	txa
	sbc.b \1+2
	sta.b \3+2
.ENDM

; A:X = mq16( M, v ) for the multiplicand M and the signed digits of v,
; the low bytes of \1 and \2 (direct page).
.MACRO G1_MQB
	lda.b \1
	sta.w MPYB
	ldy.w MPYM
	lda.b \2
	sta.w MPYB
	tya
	clc
	adc.w MPYL
	tax
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #$FF80
	cpy #$8000
	bcc _gmqb_p\@
	dec a
_gmqb_p\@:
.ENDM

; korongrelv without the digits of 8 w1: \2 = rsh( mq24( w1, \3 ), 5 ) +
; body.v - \1 + $8080 (the multiplicand \3), w1's signed bytes in MD0..MD2.
.MACRO G1_WSLOW
	sep #$20
	MB_DP \3
	RSET24 MD0
	rep #$20
	RFIN 5, $808000-$101000
	lda.b R
	clc
	adc.b S_BODY+\4
	tax
	lda.b R+2
	adc.b S_BODY+\4+2
	tay
	txa
	sec
	sbc.b \1
	sta.b \2
	tya
	sbc.b \1+2
	sta.b \2+2
.ENDM

; cross_d += mq24( rel, M ) for the multiplicand M and the signed digits of
; rel at \1 (\2 = 1: three of them); a term adds $808000 more (G1_CRD).
.MACRO G1_XD
	lda.b \1
	sta.w MPYB
	lda.w MPYM
	eor #$8000
	tay
	lda.b \1+1
	sta.w MPYB
	tya
	clc
	adc.w MPYL
	tax
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc.b G1_CRD+2
	sta.b G1_CRD+2
	txa
	clc
	adc.b G1_CRD
	sta.b G1_CRD
	bcc _gx_c\@
	inc.b G1_CRD+2
_gx_c\@:
	.IF \2 == 1
	lda.b \1+2
	sta.w MPYB
	lda.w MPYL
	xba
	and #$FF00
	clc
	adc.b G1_CRD
	sta.b G1_CRD
	lda.w MPYM
	adc.b G1_CRD+2
	sta.b G1_CRD+2
	.ENDIF
.ENDM

; korongrelv of one axis: \3 = rel + $8080 = rsh( mq24( w1, M ), 5 ) +
; body.v - \1 + $8080 for the multiplicand M (also in \5 for G1_WSLOW,
; there made from KY for \7 = 1; \2 = body.v, \6 = C_VX or C_VY), the
; signed digits r0, r1 (with \3+2 = 0: rel in 16 bits) or r0, r1, r2, 0
; of clamp24( rel ) into \4 and cross_d += mq24( rel, M ).
.MACRO G1_REL
	bit.b G1_W8D+2
	bpl _gr_f\@
	jmp _gr_ws\@
_gr_f\@:
	G1_WTERM \1, \2, \3
_gr_t\@:
	bne _gr_m\@
	; 16 bits: r0, r1 (r2 = 0):
	lda.b \3
	eor #$8080
	sta.b \4
	G1_XD \4, 0
	jmp _gr_e\@
_gr_m\@:
	clc
	adc #$0080
	cmp #$0100
	bcs _gr_c\@
	lda.b \3+2
	and #$00FF
	sta.b \4+2
	lda.b \3
	eor #$8080
	sta.b \4
	bra _gr_3\@
_gr_c\@:
	; beyond 24 bits: the digits of the clamp
	ldx #$7F7F
	lda.b \3+2
	bpl _gr_cp\@
	ldx #$8080
_gr_cp\@:
	stx.b \4
	txa
	and #$00FF
	sta.b \4+2
_gr_3\@:
	G1_XD \4, 1
	jmp _gr_e\@
_gr_ws\@:
	MOV32 T3, S_BODY+C_W
	RSH32 T3, 4
	.IF \7 == 1
	lda.b KY
	eor #$FFFF
	inc a
	sta.b \5
	.ENDIF
	DIGT3
	G1_WSLOW \1, \3, \5, \6
	lda.b \3+2
	jmp _gr_t\@
_gr_e\@:
.ENDM

; \2 = MULK( rel, K_DAMP ) + 70 (16-bit) from the signed digits of rel at
; \1 when rel is 16-bit (\3+2 = 0, \3 = rel + $8080), else the MULK +
; $1010046 (32-bit); the multiplicand
; K_DAMP_M: with the products Pi of the digits, u0 = P0 >> 8 and P1 = 256 M1
; + l1, MULK = ((u0 + P1 + 256 P2 + 64) >> 7) = ((u0 + l1 + 64) >> 7) + 2
; (M1 + P2).
.IF K_DAMP_SH != 15
.FAIL
.ENDIF
.MACRO G1_DAMPR
	lda.b \1
	sta.w MPYB
	lda.w MPYM
	clc
	adc #64+70*128                  ; (|u0| <= 8946)
	sta.b G1_T
	lda.b \1+1
	sta.w MPYB
	lda.w MPYL
	and #$00FF
	clc
	adc.b G1_T
	asl a
	xba
	and #$00FF                      ; ((u0 + l1 + 64) >> 7) + 70
	ldx.b \3+2
	bne _gd_3\@
	adc.w MPYM
	clc
	adc.w MPYM
	sta.b \2
	bra _gd_e\@
_gd_3\@:
	sta.b G1_T
	lda.w MPYM
	eor #$8000
	tay
	lda.b \1+2
	sta.w MPYB
	tya
	clc
	adc.w MPYL
	tax
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #0                          ; A:X = M1 + P2 + $808000
	sta.b \2+2
	txa
	asl a
	rol.b \2+2
	clc
	adc.b G1_T
	sta.b \2
	bcc _gd_e\@
	inc.b \2+2
_gd_e\@:
.ENDM

; \1 = MULK( g, K_SPRING ) + the damper \3 for the multiplicand g (\2: rel
; + $8080, \2+2 = 0: \3 is 16-bit): with the products of g and the
; signed digits -64, -94, 8 of 16 K_SPRING_M, MULK = P2 + ((P0 + 256 P1 +
; 2^15) >> 16) = 8 g + V, V = M1 + ((u0 + l1 + 128) >> 8); 8 g + V + a
; 16-bit damper by the sign of V + the damper.
.IF K_SPRING_SH != 12 || K_SPRING_M*16 != 8*65536-94*256-64
.FAIL
.ENDIF
.MACRO G1_SPRG
	lda #$FFC0
	sta.w MPYB
	lda.w MPYM
	clc
	adc #$2080                      ; (|u0| <= 8192)
	sta.b G1_T
	lda #$FFA2
	sta.w MPYB
	lda.w MPYL
	and #$00FF
	clc
	adc.b G1_T
	xba
	and #$00FF
	adc.w MPYM                      ; V + 32
	ldx.b \2+2
	bne _gs_3\@
	clc
	adc.b \3
	sec
	sbc #102
	sta.b G1_T                      ; V + damper
	bmi _gs_n\@
	lda #$0008
	sta.w MPYB
	lda.w MPYL
	clc
	adc.b G1_T
	sta.w \1+0
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #$FF80
	sta.w \1+2
	bra _gs_e\@
_gs_n\@:
	lda #$0008
	sta.w MPYB
	lda.w MPYL
	clc
	adc.b G1_T
	sta.w \1+0
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #$FF7F
	sta.w \1+2
	bra _gs_e\@
_gs_3\@:
	eor #$8000
	sta.b G1_T
	lda #$0008
	sta.w MPYB
	lda.w MPYL
	clc
	adc.b G1_T
	tay
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #0
	tax                             ; Y:X = MULK + $808020
	tya
	clc
	adc.b \3
	tay
	txa
	adc.b \3+2
	tax
	tya
	sec
	sbc #$8066
	sta.w \1+0
	txa
	sbc #$0181
	sta.w \1+2
_gs_e\@:
.ENDM

; cross_s += mq24( g, gs ) for the multiplicand g and the digits of the
; word gs at \1 (absolute); a term adds $808000 more (G1_CRS).
.MACRO G1_XS
	lda.w \1
	sta.w MPYB
	clc
	adc #$0080
	xba
	tax                         ; the high digit
	lda.w MPYM
	eor #$8000
	tay
	stx.w MPYB
	tya
	clc
	adc.w MPYL
	tax
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc.b G1_CRS+2
	sta.b G1_CRS+2
	txa
	clc
	adc.b G1_CRS
	sta.b G1_CRS
	bcc _gc_c\@
	inc.b G1_CRS+2
_gc_c\@:
.ENDM

; The same as G1_SPRG and G1_XS for a gumi \1 beyond 16 bits (\4: the
; output, \5: gs).
.MACRO G1_SPRSLOW
	MULK \1, K_SPRING
	ldx.b \2+2
	bne _gw_3\@
	lda.b \3
	sec
	sbc #70
	ldy #0
	cmp #$8000
	bcc _gw_p\@
	dey
_gw_p\@:
	clc
	adc.b R
	sta.w \4+0
	tya
	adc.b R+2
	sta.w \4+2
	bra _gw_x\@
_gw_3\@:
	lda.b \3
	clc
	adc.b R
	tax
	lda.b \3+2
	adc.b R+2
	tay
	txa
	sec
	sbc #$0046
	sta.w \4+0
	tya
	sbc #$0101
	sta.w \4+2
_gw_x\@:
	MOV32 T3, \1
	DIGT3
	MB_ABS \5
	RSET24 MD0
	rep #$21
	lda.b R
	adc.b G1_CRS
	sta.b G1_CRS
	lda.b R+2
	adc.b G1_CRS+2
	sta.b G1_CRS+2
.ENDM

; \3 = the damper \2 alone (no spring; \1: rel + $8080).
.MACRO G1_DSTORE
	ldx.b \1+2
	bne _gt_3\@
	lda.b \2
	sec
	sbc #70
	sta.w \3+0
	ldx #0
	cmp #$8000
	bcc _gt_p\@
	dex
_gt_p\@:
	stx.w \3+2
	bra _gt_e\@
_gt_3\@:
	lda.b \2
	sec
	sbc #$0046
	sta.w \3+0
	lda.b \2+2
	sbc #$0101
	sta.w \3+2
_gt_e\@:
.ENDM

; erokszamitasa of the wheel \1 (S_K2, S_K4), number \2: pt_dx, pt_dy[k],
; the sums of the torques on the body, the friction.
.MACRO G1_EROK
	; koto = clamp16( rsh( wheel-body, 3 ) ), the multiplier -ky:
	G1_KOTO \1+C_RX, S_BODY+C_RX, KX, GX
	G1_KOTO \1+C_RY, S_BODY+C_RY, KY, GY
	eor #$FFFF
	inc a
	xba
	sta.w MPYA
	sta.w MPYA
	; korongrelv = rot90( koto ) * w1 + body.v - wheel.v, and cross_d:
	G1_REL \1+C_VX, S_BODY+C_VX, RLX, G1_RX, G1_NKY, C_VX, 1
	lda.b KX
	xba
	sta.w MPYA
	sta.w MPYA
	G1_REL \1+C_VY, S_BODY+C_VY, RLY, G1_RY, KX, C_VY, 0
	; the dampers:
	lda #((K_DAMP_M & $FF) << 8) | (K_DAMP_M >> 8)
	sta.w MPYA
	sta.w MPYA
	G1_DAMPR G1_RX, G1_DMX, RLX
	G1_DAMPR G1_RY, G1_DMY, RLY
	; gumi = gs - (wheel - body), the springs unless both are within 0.0001
	; m, and cross_s:
	lda.w pt_gsx+4*\2
	sec
	sbc.b GX
	sta.b GX
	tay
	lda.w pt_gsx+4*\2+2
	sbc.b GX+2
	sta.b GX+2
	cpy #$8000
	adc #0
	beq _ge_x16\@
	jmp _ge_xs\@
_ge_x16\@:
	tya
	clc
	adc #SPRING_ZERO_P
	cmp #2*SPRING_ZERO_P+1
	bcs _ge_xf\@
	jmp _ge_x0\@
_ge_xf\@:
	tya
	xba
	sta.w MPYA
	sta.w MPYA
	G1_SPRG pt_dx+4*\2, RLX, G1_DMX
	G1_XS G1_GS+4*\2+2
_ge_y\@:
	lda.w pt_gsy+4*\2
	sec
	sbc.b GY
	sta.b GY
	tay
	lda.w pt_gsy+4*\2+2
	sbc.b GY+2
	sta.b GY+2
	cpy #$8000
	adc #0
	beq _ge_y16\@
	jmp _ge_ys\@
_ge_y16\@:
	tya
	xba
	sta.w MPYA
	sta.w MPYA
	G1_SPRG pt_dy+4*\2, RLY, G1_DMY
	G1_XS G1_GS+4*\2
_ge_ft\@:
	; Ftestnyom, with a torque on the wheel; the friction:
	lda.w pt_m+4*\2
	ora.w pt_m+4*\2+2
	beq _ge_nf\@
	lda #4*\2
	sta.b CK4
	jsr phys_ftn
_ge_nf\@:
	lda.b IN
	bit #PH_QUICK
	bne _ge_q\@
	jmp phys_fric
_ge_q\@:
	rts
_ge_xs\@:
	G1_SPRSLOW GX, RLX, G1_DMX, pt_dx+4*\2, G1_GS+4*\2+2
	jmp _ge_y\@
_ge_ys\@:
	G1_SPRSLOW GY, RLY, G1_DMY, pt_dy+4*\2, G1_GS+4*\2
	jmp _ge_ft\@
_ge_x0\@:
	; gx is within 0.0001 m: gy too?
	lda.w pt_gsy+4*\2
	sec
	sbc.b GY
	sta.b GY
	tay
	lda.w pt_gsy+4*\2+2
	sbc.b GY+2
	sta.b GY+2
	tax
	tya
	clc
	adc #SPRING_ZERO_P
	tay
	txa
	adc #0
	bne _ge_xon\@
	cpy #2*SPRING_ZERO_P+1
	bcs _ge_xon\@
	G1_DSTORE RLX, G1_DMX, pt_dx+4*\2
	G1_DSTORE RLY, G1_DMY, pt_dy+4*\2
	lda.b G1_CRS+2
	clc
	adc #$0101
	sta.b G1_CRS+2
	jmp _ge_ft\@
_ge_xon\@:
	; (GY back to wheel - body)
	lda.w pt_gsy+4*\2
	sec
	sbc.b GY
	sta.b GY
	lda.w pt_gsy+4*\2+2
	sbc.b GY+2
	sta.b GY+2
	ldy.b GX
	jmp _ge_xf\@
.ENDM

; Y = G of G1_MULKS for \1 = x+$808080 (in range), s = \2; \1 is used.
.MACRO G1_MKG
	lda.b \1
	eor #$8080
	sta.w MPYB                  ; *e0
	xba
	tay
	lda.w MPYM
	clc
	.IF \2 == 0
	adc #16384+128
	.ELSE
	adc #16384
	.ENDIF
	sta.b \1
	sty.w MPYB                  ; *e1
	lda.w MPYL
	and #$00FF
	clc
	adc.b \1
	xba
	and #$00FF
	clc
	adc.w MPYM
	sec
	.IF \2 == 0
	sbc #64
	.ELSE
	sbc #64-(1 << (\2-1))
	.ENDIF
	tay
.ENDM

; \1 = floor( (x*M+2^(15+s))/2^(16+s) ) (MULK for K_SH = 24+s) for the
; double word \1 = x+$808080 (clamped here), s = \2 (0 to 3) and the
; multiplicand M: with x*M = P0+256*P1+65536*P2 (the signed bytes e0, e1,
; e2 of x are the bytes of \1 xor $80), P0 = 256*W0+.., P1 = 256*V1+l1, it
; is (P2+G) >> s for G = V1+floor( (W0+l1+(s ? 0 : 128))/256 )+(s ? 2^(s-1)
; : 0). X and Y are used.
.MACRO G1_MULKS
	lda.b \1+2
	cmp #$0080
	bne _g1md_x\@
	G1_MKG \1, \2
	tya
	.REPT \2
	cmp #$8000
	ror a
	.ENDR
	sta.b \1
	ldx #0
	cmp #$8000
	bcc _g1md_p\@
	dex
_g1md_p\@:
	stx.b \1+2
	jmp _g1md_e\@
_g1md_x\@:
	tax                         ; (N of \1+2)
	bmi _g1md_lo\@
	cmp #$0100
	bcc _g1md_3\@
	lda #$FFFF
	sta.b \1
	lda #$00FF
	sta.b \1+2
	bra _g1md_3\@
_g1md_lo\@:
	stz.b \1
	stz.b \1+2
_g1md_3\@:
	G1_MKG \1, \2
	lda.b \1+2
	eor #$0080
	sta.w MPYB                  ; *e2
	tya
	eor #$8000
	clc
	adc.w MPYL
	sta.b \1
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #0                      ; P2+G+$808000
	.REPT \2
	lsr a
	ror.b \1
	.ENDR
	tax
	lda.b \1
	sec
	sbc #($808000 >> \2) & $FFFF
	sta.b \1
	txa
	sbc #($808000 >> \2) >> 16
	sta.b \1+2
_g1md_e\@:
.ENDM

; The body: v += -MULK( \1[0]+\1[1], K_20 )+\3 (\2: v; the multiplicand
; K_20_M/2), r += rsh( v, 8 ) (\4: r).
.MACRO G1_BODYV
	lda.w \1+0
	clc
	adc.w \1+4
	tax
	lda.w \1+2
	adc.w \1+6
	tay
	txa
	clc
	adc #$8080
	sta.b T0
	tya
	adc #$0080
	sta.b T0+2
	G1_MULKS T0, 2
	lda.b \2
	sec
	sbc.b T0
	tax
	lda.b \2+2
	sbc.b T0+2
	tay
	txa
	clc
	adc.b \3
	sta.b \2
	tya
	adc.b \3+2
	sta.b \2+2
	tay
	lda.b \2-1
	asl a
	lda.b \2+1
	adc.b \4
	sta.b \4
	tya
	xba
	and #$00FF
	eor #$0080
	adc.b \4+2
	sec
	sbc #$0080
	sta.b \4+2
.ENDM

; \3 = rsh( mq24( C, K60_15 ), 13 ), \4 = rsh( mq24( C, K85_15 ), 13 ) for
; C = \2 (the multiplicand K60_15, the signed digits of C: e0 its low byte,
; e1 and e2 bytes 1 and 2 of C+$8080 xor $80 and as they are): with
; Y = (C K60_15 + 2^20) >> 13 = 8 (Q1 + P2) + ((Q0 + p1a + 4096) >> 5),
; \3 = Y >> 8 and \4 = (Y + C) >> 8 as K85_15 = K60_15 + 2^13; \1 holds
; Y + $4040200, \3 and \4 hold $40402 more unless \5 and \6 are 1.
.IF K85_15 - K60_15 != 8192
.FAIL
.ENDIF
.MACRO G1_ANC2
	lda.b \2
	clc
	adc #$8080
	tax                         ; C+$8080: byte 1 = e1 xor $80
	lda.b \2+2
	adc #0
	tay                         ; e2
	lda.b \2
	sta.w MPYB
	lda.w MPYM
	clc
	adc #20480
	sta.b G1_T
	txa
	xba
	eor #$0080
	sta.w MPYB
	lda.w MPYL
	and #$00FF
	clc
	adc.b G1_T
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	sta.b G1_T
	lda.w MPYM
	eor #$8000
	tax
	sty.w MPYB
	txa
	clc
	adc.w MPYL
	sta.b \1
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #0
	asl.b \1
	rol a
	asl.b \1
	rol a
	asl.b \1
	rol a
	tax
	lda.b G1_T
	clc
	adc.b \1
	sta.b \1
	txa
	adc #0
	sta.b \1+2
	lda.b \1+1
	.IF \5 == 1
	sec
	sbc #$0402
	.ENDIF
	sta.b \3
	lda.b \1+3
	and #$00FF
	.IF \5 == 1
	sbc #$0004
	.ENDIF
	sta.b \3+2
	lda.b \1
	clc
	adc.b \2
	sta.b \1
	lda.b \1+2
	adc.b \2+2
	sta.b \1+2
	lda.b \1+1
	.IF \6 == 1
	sec
	sbc #$0402
	.ENDIF
	sta.b \4
	lda.b \1+3
	and #$00FF
	.IF \6 == 1
	sbc #$0004
	.ENDIF
	sta.b \4+2
.ENDM

; From gs (X: high, Y: low word): \1 = gs (absolute), \2 = rsh( gs, 2 ) (\3 =
; 1: its negative).
.MACRO G1_GSV
	sty.w \1+0
	stx.w \1+2
	tya
	clc
	adc #2
	tay
	txa
	adc #0
	lsr a
	tax
	tya
	ror a
	tay
	txa
	lsr a
	tya
	ror a
	.IF \3 == 1
	eor #$FFFF
	inc a
	.ENDIF
	sta.w \2+0
.ENDM

; A = clamp16( rsh( \1, 2 ) ) of a double word of the direct page.
.MACRO G1_G16
	G1_FITS \1
	bne _gg_s\@
	lda.b \1
	cmp #$8000
	ror a
	cmp #$8000
	ror a
	adc #0
	bra _gg_d\@
_gg_s\@:
	MOV32 T0, \1
	RSH32 T0, 2
	CLAMP16 T0
_gg_d\@:
.ENDM

; A = clamp16( rsh( rel, 8 ) ) for \1 = rel + $8080 of the direct page: it
; is (\1 >> 8) - 128.
.MACRO G1_RV16B
	lda.b \1+2
	clc
	adc #$0080
	cmp #$0100
	bcs _grb_s\@
	lda.b \1+1
	sec
	sbc #$0080
	bvs _grb_c\@
	bpl _grb_d\@
	cmp #$8080
	bcs _grb_d\@
_grb_c\@:
	lda #$8080
	bra _grb_d\@
_grb_s\@:
	lda.b \1
	sec
	sbc #$8080
	sta.b T0
	lda.b \1+2
	sbc #0
	sta.b T0+2
	RSH32 T0, 8
	CLAMP16 T0
_grb_d\@:
.ENDM

; 2^(n-1) for n = 1..6 (Ftestnyom):
G1_HALF:
	.dw 0, 1, 2, 4, 8, 16, 32

; M[\1] of the brake for the wheel \2 (see BRAKE_TORQUE) when its
; deflection and rsh( w - w_body, 8 ) are 16-bit: MULK( x, K ) is then
; Q1 + ((Q0 + p1a + 128) >> 8) with the products of x and K's digits
; (K_BRK_S as 1000 / 2^16).
.MACRO G1_BRAKE
	lda.b \2+C_W
	sec
	sbc.b S_BODY+C_W
	sta.b T0
	lda.b \2+C_W+2
	sbc.b S_BODY+C_W+2
	sta.b T0+2
	clc
	adc #$0080
	cmp #$00FF
	bcs _gb_sj\@
	G1_FITS S_DEFL+4*\1
	beq _gb_f\@
_gb_sj\@:
	jmp _gb_s\@
_gb_f\@:
	lda.b T0-1
	asl a
	lda.b T0+1
	adc #0                      ; rsh( dw, 8 )
	G1_LDMA
	lda #$FF8B
	sta.w MPYB
	lda.w MPYM
	clc
	adc #16512
	sta.b G1_T
	lda #$0048
	sta.w MPYB
	lda.w MPYL
	and #$00FF
	clc
	adc.b G1_T
	xba
	and #$00FF
	adc.w MPYM
	sta.b T1                    ; MULK( dw, K_BRK_W ) + 64
	G1_LDMD S_DEFL+4*\1
	lda #$FFE8
	sta.w MPYB
	lda.w MPYM
	clc
	adc #16512
	sta.b G1_T
	lda #$0004
	sta.w MPYB
	lda.w MPYL
	and #$00FF
	clc
	adc.b G1_T
	xba
	and #$00FF
	adc.w MPYM                  ; MULK( defl, K_BRK_S ) + 64
	clc
	adc.b T1
	eor #$FFFF
	clc
	adc #129                    ; M = -( the sum )
	sta.w pt_m+4*\1
	ldx #0
	cmp #$8000
	bcc _gb_p\@
	dex
_gb_p\@:
	stx.w pt_m+4*\1+2
	jmp _gb_d\@
_gb_s\@:
	BRAKE_TORQUE \1, \2
_gb_d\@:
.ENDM

; Ftestnyom: \1 (pt_dx or pt_dy) of the wheel +=  (\2 = 0) or -= (\2 = 1)
; rsh( A:X, n ), n in R, 2^(n-1) in T3.
.MACRO G1_FTNADD
	tay
	txa
	clc
	adc.b T3
	sta.b T1
	tya
	adc #0
	ldy.b R
	beq _gfa_d\@
_gfa_l\@:
	cmp #$8000
	ror a
	ror.b T1
	dey
	bne _gfa_l\@
_gfa_d\@:
	ldx.b CK4
	.IF \2 == 0
	tay
	lda.w \1,x
	clc
	adc.b T1
	sta.w \1,x
	tya
	adc.w \1+2,x
	sta.w \1+2,x
	.ELSE
	sta.b T1+2
	lda.w \1,x
	sec
	sbc.b T1
	sta.w \1,x
	lda.w \1+2,x
	sbc.b T1+2
	sta.w \1+2,x
	.ENDIF
.ENDM

; The torques of the brake (leptet; phys_step does the gas, the brake
; overrides it).
phys_torques:
	.ACCU 16
	.INDEX 16
	lda.b S_BRAKEWAS
	and #$00FF
	bne +
	stz.b S_DEFL
	stz.b S_DEFL+2
	stz.b S_DEFL+4
	stz.b S_DEFL+6
+	sep #$20
	lda #1
	sta.b S_BRAKEWAS
	rep #$20
	G1_BRAKE 0, S_K2
	G1_BRAKE 1, S_K4
	rts

; The anchors of the wheels on the body (P): gsx = ( b-a, a+b ), gsy =
; ( -cc-d, cc-d ) with a = 0.85 cos, b = 0.6 sin, cc = 0.85 sin, d = 0.6 cos
; (pt_gsx, pt_gsy), and rsh( gs, 2 ) for phys_erok (G1_GS).
phys_anchors:
	.ACCU 16
	.INDEX 16
	lda #((K60_15 & $FF) << 8) | (K60_15 >> 8)
	sta.w MPYA
	sta.w MPYA
	G1_ANC2 T3, CS22, T1, T0, 0, 1  ; d+$40402, a
	G1_ANC2 T3, SN22, T2, R, 1, 0   ; b, cc+$40402
	; gsx = ( b-a, a+b ), gsy = ( -cc-d, cc-d ) (the biases of cc and d go
	; away there):
	lda.b T2
	sec
	sbc.b T0
	tay
	lda.b T2+2
	sbc.b T0+2
	tax
	G1_GSV pt_gsx, G1_GS, 0
	lda.b T2
	clc
	adc.b T0
	tay
	lda.b T2+2
	adc.b T0+2
	tax
	G1_GSV pt_gsx+4, G1_GS+4, 0
	lda.b R
	clc
	adc.b T1
	sta.b T3
	lda.b R+2
	adc.b T1+2
	sta.b T3+2
	lda #$0804
	sec
	sbc.b T3
	tay
	lda #$0008
	sbc.b T3+2
	tax
	G1_GSV pt_gsy, G1_GS+2, 1
	lda.b R
	sec
	sbc.b T1
	tay
	lda.b R+2
	sbc.b T1+2
	tax
	G1_GSV pt_gsy+4, G1_GS+6, 1
	rts

; erokszamitasa of the wheel kor2 (phys_erok) and kor4 (_g1_ek4).
phys_erok:
	.ACCU 16
	.INDEX 16
	G1_EROK S_K2, 0
_g1_ek4:
	G1_EROK S_K4, 1

; Ftestnyom: the torque M[k] of the wheel pushes its axle (A 16-bit).
phys_ftn:
	.ACCU 16
	.INDEX 16
	lda.b KX
	clc
	adc #$0080
	xba
	sta.b G1_KX1                ; the high signed digit of kx
	lda.b KY
	clc
	adc #$0080
	xba
	sta.b G1_T                  ; the high signed digit of ky
	; k2 = kx kx + ky ky (the products of the signed digits, $80 of bias
	; in the high word for each lowest one), at least 65536:
	lda.b KX
	xba
	sta.w MPYA
	sta.w MPYA
	lda.b KX
	sta.w MPYB
	lda.w MPYL
	sta.b T1
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	sta.b T1+2
	lda.b G1_KX1
	sta.w MPYB
	lda.w $2133
	and #$FF00
	clc
	adc.b T1
	sta.b T1
	lda.w MPYM
	adc.b T1+2
	sta.b T1+2
	lda.b KY
	xba
	sta.w MPYA
	sta.w MPYA
	lda.b KY
	sta.w MPYB
	lda.w MPYL
	clc
	adc.b T1
	sta.b T1
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc.b T1+2
	sta.b T1+2
	lda.b G1_T
	sta.w MPYB
	lda.w $2133
	and #$FF00
	clc
	adc.b T1
	sta.b T1
	lda.w MPYM
	adc.b T1+2
	sec
	sbc #$0100
	bne +
	stz.b T1
	inc a
+	; s: shifts until the top bit (k2 < 2^31: at least one):
	ldx #0
-	inx
	asl.b T1
	rol a
	bpl -
	stx.b T3                    ; s
	sta.b T1+2
	; rc = rcp[m] + ((rcpd[m]*f + 64) >> 7), m = (X >> 24)-128, f = (X >> 17) & 127:
	xba
	and #$007F
	asl a
	tax
	lda.l phys_rcpd,x
	asl a
	xba
	sta.w MPYA
	sta.w MPYA
	lda.b T1+2
	lsr a
	and #$007F
	sta.w MPYB
	lda.w $2133
	asl a
	lda.w MPYM
	adc #0
	clc
	adc.l phys_rcp,x
	sta.b T0                    ; rc
	; B = rsh( mq24( M, rc ), 8 ) for a 16-bit M and s <= 7:
	ldy.b CK4
	lda.w pt_m,y
	asl a
	lda.w pt_m+2,y
	adc #0
	bne +
	lda.b T3
	cmp #8
	bcc ++
+	jmp _ftn_slow
++	eor #$0007
	sta.b R                     ; n = 7-s
	asl a
	tax
	lda.l G1_HALF,x
	sta.b T3                    ; 2^(n-1) (0 for n = 0)
	lda.w pt_m,y
	xba
	sta.w MPYA
	sta.w MPYA
	lda.b T0
	sta.w MPYB
	lda.w MPYM
	clc
	adc #16512
	sta.b T2+2
	lda.b T0
	clc
	adc #$0080
	xba
	sta.w MPYB
	lda.w MPYL
	and #$00FF
	clc
	adc.b T2+2
	xba
	and #$00FF
	adc.w MPYM
	sec
	sbc #64                     ; B
	; Dx += rsh( mq24( B, ky ), n ), Dy -= rsh( mq24( B, kx ), n ):
	xba
	sta.w MPYA
	sta.w MPYA
	G1_MQB KY, G1_T
	G1_FTNADD pt_dx, 0
	G1_MQB KX, G1_KX1
	G1_FTNADD pt_dy, 1
	rts
_ftn_slow:
	lda.b T3
	sta.b T2                    ; s
	lda.w pt_m,y
	sta.b T3
	lda.w pt_m+2,y
	sta.b T3+2
	DIGT3
	MB_DP T0
	RSET24 MD0
	rep #$20
	RFIN 8, $808000
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
_ftn_shift:
	; s <= 7: rsh( p, 7-s ), else p << (s-7):
	lda.b T2
	cmp #8
	bcs _ftn_left
	eor #$0007
	beq _ftn_add                ; s = 7: no shift
	sta.b T2                    ; n = 7-s
	asl a
	tax
	lda.l G1_HALF,x
	sta.b T3                    ; 2^(n-1)
	clc
	adc.b T1
	sta.b T1
	lda.b T1+2
	adc #0
	ldy.b T2
-	cmp #$8000
	ror a
	ror.b T1
	dey
	bne -
	sta.b T1+2
	lda.b R
	clc
	adc.b T3
	sta.b R
	lda.b R+2
	adc #0
	ldy.b T2
-	cmp #$8000
	ror a
	ror.b R
	dey
	bne -
	sta.b R+2
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
	lda #0
	sec
	sbc.b CS
	xba
	sta.b G1_T                  ; c8 = (-Cs) >> 8 (the low byte)
	G1_G16 GX
	xba
	sta.w MPYA
	sta.w MPYA
	lda.b SN+1                  ; s8 = Sn >> 8
	sta.w MPYB
	ldy.w MPYM
	G1_G16 GY
	xba
	sta.w MPYA
	sta.w MPYA
	lda.b G1_T
	sta.w MPYB
	tya
	clc
	adc.w MPYM
	bmi _fr_ret0
	bne _fr_fg
_fr_ret0:
	rts
_fr_fg:
	sta.b T3                    ; fg
	G1_RV16B RLX
	xba
	sta.w MPYA
	sta.w MPYA
	lda.b SN+1
	sta.w MPYB
	ldy.w MPYM
	G1_RV16B RLY
	xba
	sta.w MPYA
	sta.w MPYA
	lda.b G1_T
	sta.w MPYB
	tya
	clc
	adc.w MPYM
	bmi _fr_ret
	bne _fr_e
_fr_ret:
	rts
_fr_e:
	; e = MULK( mq16( clamp16( fg ), clamp16( sb ) ), K_FRIC ): both are
	; positive, mq16 = u0+P1 for the digits r0, r1 >= 0 of sb:
	cmp #32640
	bcc +
	lda #32639
+	tax                         ; sb
	lda.b T3
	cmp #32640
	bcc +
	lda #32639
+	xba
	sta.w MPYA
	sta.w MPYA                  ; fg
	stx.w MPYB
	lda.w MPYM
	eor #$8000
	tay
	txa
	clc
	adc #$0080
	xba
	sta.w MPYB
	tya
	clc
	adc.w MPYL
	tax
	lda.w MPYM
	xba
	and #$00FF
	adc #0
	tay                         ; Y:X = mq16+$8000
	txa
	sec
	sbc #$8000
	sta.b R
	tya
	sbc #0
	sta.b R+2
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
	CLAMP16 T0
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
	lda.b S_VOLTON
	ora.w pt_volt
	bne +
	rts
+	MOV32W pt_oldw, phys_dpa+S_BODY+C_W
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
	CLAMP16 T1
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
	stz.b GVX+2
	stz.b GVY+2
	lda.b S_GRAVITY
	and #$00FF
	bne +
	stz.b GVX
	lda #G_V
	sta.b GVY
	rts
+	cmp #2
	bcc _gv_up
	bne +
	lda #-G_V
	sta.b GVX
	dec.b GVX+2
	stz.b GVY
	rts
+	cmp #3
	bne _gv_up
	lda #G_V
	sta.b GVX
	stz.b GVY
	rts
_gv_up:
	stz.b GVX
	lda #-G_V
	sta.b GVY
	dec.b GVY+2
	rts

; frsqrt: for d2 in T1 (> 0): A = Y, T2 = k, T1 = d2 << 2k with 1/sqrt( d2 )
; = Y * 2^(k-30) (X is changed).
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
	tax                         ; 2 m
	lda.l phys_rsqd,x
	xba
	sta.w MPYA                  ; (the 16-bit stores: see G3_MA)
	sta.w MPYA
	lda.b T1+2
	lsr a
	and #$007F
	sta.w MPYB                  ; f
	lda.w MPYL                  ; (|rsqd f| < 2^15)
	clc
	adc #64
	asl a                       ; (rsqd f+64) >> 7:
	xba
	and #$00FF
	bcc +
	ora #$FF00
+	clc
	adc.l phys_rsq,x
	rts

; Signed 16-bit A = -A:
.MACRO NEGA
	eor #$FFFF
	inc a
.ENDM

; One axis of phys_rider (\1 = 0: x, 1: y): D = rider-body+1, to \3 if it
; is not in [-32768, 32767]; T2 (+2) = 2*rsh( rider-body, 1 ) = D & ~1 and
; G2_IX (G2_IY) = 2*(dir+4079), dirx = -((D-1+OFX) >> 1) (g2_ofxb = OFX-1
; +32768), diry = rsh( OFY-(D-1), 1 ) (g2_ofyb = OFY+1+32768); with \2 = 1
; C = 0 for the rider in the box of the axis (g2_sxr, g2_syr).
.MACRO G2_RDAX
	.IF \1 == 0
	lda.b S_RIDX
	sec
	sbc.b S_BODY+C_RX
	tax
	lda.b S_RIDX+2
	sbc.b S_BODY+C_RX+2
	.ELSE
	lda.b S_RIDY
	sec
	sbc.b S_BODY+C_RY
	tax
	lda.b S_RIDY+2
	sbc.b S_BODY+C_RY+2
	.ENDIF
	inx
	bne _g2ra_i\@
	inc a
_g2ra_i\@:
	cpx #$8000
	adc #0
	bne \3
	txa
	.IF \1 == 0
	eor #$8000
	clc
	adc.w g2_ofxb
	ror a                       ; ((D-1+OFX) >> 1)+32768
	eor #$FFFF
	.ELSE
	eor #$7FFF
	clc
	adc.w g2_ofyb
	ror a                       ; ((OFY-D) >> 1)+32768
	.ENDIF
	clc
	adc #32768+4079+1
	asl a
	.IF \1 == 0
	sta.b G2_IX
	.IF \2 != 0
	sec
	sbc.w g2_sxr                ; 2*(dirx-sx+G2_RB)
	cmp #4*G2_RB+1
	.ENDIF
	.ELSE
	sta.b G2_IY
	.IF \2 != 0
	sec
	sbc.w g2_syr
	cmp #4*G2_RB+1
	.ENDIF
	.ENDIF
	txa
	and #$FFFE
	.IF \1 == 0
	sta.b T2
	.ELSE
	sta.b T2+2
	.ENDIF
.ENDM

; beallitvezeto: the rider (vezeto_hatarolas keeps him over the seat). The
; usual case is fast: rider-body within 16 bits (P), the rider in a box
; around a point under his rest where neither the seat, the clamps nor the
; ellipse move him, the angular velocity of the body the one of the start
; of the step; the rest is done the slow way.
;
; The box: with s = (-Sn, Cs)*G2_SK/256 (g2_sxr, g2_syr, +-1), |dir-s| <=
; G2_RB in both axes puts the rider (in the frame of the body) within
; G2_RB*sqrt(2) (+8 for the roundings) of (0, K44_15-128*G2_SK), inside the
; region where nothing moves him: y <= RIDER_TOP and the ellipse 2847 away,
; the seat 2931.
.IF K44_15 != 14418 || G2_SK != 12 || G2_RB > 2000 || G2_OA > 2610 || G2_OB > 3690


.FAIL "phys_rider: the box"
.ENDIF
phys_rider:
	.ACCU 16
	.INDEX 16
	G2_RDAX 0, 1, _g2rd_sl1
	bcs _g2rd_bx
	G2_RDAX 1, 1, _g2rd_sl1
	bcs _g2rd_by
	jmp _g2rd_fast
_g2rd_sl1:
	jmp _g2rd_slow
_g2rd_bx:
	; (outside the box in x: y without its test)
	G2_RDAX 1, 0, _g2rd_sl1

_g2rd_by:
	; Outside the box: the octagon |u| <= G2_OA, |ux|+|uy| <= G2_OB of u =
	; dir-s is within G2_RB*sqrt(2) of the same point too (2*u as G2_IX
	; -g2_sxr-2*G2_RB, of 16 bits only up to 32767 but then not small).
	lda.b G2_IX
	sec
	sbc.w g2_sxr
	sec
	sbc #2*G2_RB
	bpl +
	eor #$FFFF
	inc a
+	cmp #2*G2_OA+1
	bcs _g2rd_ex
	sta.b T0
	lda.b G2_IY
	sec
	sbc.w g2_syr
	sec
	sbc #2*G2_RB
	bpl +
	eor #$FFFF
	inc a
+	cmp #2*G2_OA+1
	bcs _g2rd_ex
	clc
	adc.b T0
	cmp #2*G2_OB+1
	bcs _g2rd_ex
	jmp _g2rd_fast
_g2rd_ex:
	; x, y exactly. G2_DX, G2_DY = dx, dy, MD0, MD2 their high signed
	; bytes:
	stz.b G2_FLAG
	lda.b T2
	cmp #$8000
	ror a
	sta.b G2_DX
	clc
	adc #$0080
	xba
	sta.b MD0
	lda.b T2+2
	cmp #$8000
	ror a
	sta.b G2_DY
	clc
	adc #$0080
	xba
	sta.b MD2
	; x = rsh( mq16( Cs, dx )+mq16( Sn, dy ), 7 ): with the products as
	; 256*W0+.. (low bytes) and 256*V+l (high bytes), it is 2*(Va+Vb)
	; +((W0a+la+W0b+lb+64) >> 7) (|Cs|+|Sn| < 46400: no overflow, no clamp):
	lda.b CS
	G2_MA
	lda.b G2_DX
	sta.w MPYB                  ; Cs*dx0
	lda.w MPYM
	sta.b R
	lda.b G2_DY
	sta.w MPYB                  ; Cs*dy0
	lda.w MPYM
	sta.b R2
	lda.b MD0
	sta.w MPYB                  ; Cs*dx1
	lda.w MPYL
	and #$00FF
	clc
	adc.b R
	sta.b R
	lda.w MPYM
	sta.b R+2
	lda.b MD2
	sta.w MPYB                  ; Cs*dy1
	lda.w MPYL
	and #$00FF
	clc
	adc.b R2
	sta.b R2
	lda.w MPYM
	sta.b R2+2
	lda.b SN
	G2_MA
	lda.b G2_DY
	sta.w MPYB                  ; Sn*dy0
	lda.w MPYM
	clc
	adc.b R
	sta.b R
	lda.b MD2
	sta.w MPYB                  ; Sn*dy1
	lda.w MPYL
	and #$00FF
	clc
	adc.b R
	G2_SHR7
	sta.b T3
	lda.w MPYM
	clc
	adc.b R+2
	asl a
	clc
	adc.b T3
	sta.b T3                    ; x
	; y = rsh( mq16( Cs, dy )+mq16( -Sn, dx ), 7 ):
	lda #0
	sec
	sbc.b SN
	G2_MA
	lda.b G2_DX
	sta.w MPYB                  ; -Sn*dx0
	lda.w MPYM
	clc
	adc.b R2
	sta.b R2
	lda.b MD0
	sta.w MPYB                  ; -Sn*dx1
	lda.w MPYL
	and #$00FF
	clc
	adc.b R2
	G2_SHR7
	sta.b T3+2
	lda.w MPYM
	clc
	adc.b R2+2
	asl a
	clc
	adc.b T3+2
	sta.b T3+2                  ; y
	jmp _g2rd_xy
_g2rd_slow:
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
	CLAMP16 R
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
	CLAMP16 R
	sta.b T3+2
	lda #1
	sta.b G2_FLAG
_g2rd_xy:
	stz.w pt_tmp+4              ; moved
	lda.b S_TURNED
	and #$00FF
	beq +
	lda.b T3
	NEGA
	sta.b T3
+	; y in [10800, RIDER_TOP] and x in [RIDER_LEFT, 2048]: neither the seat
	; (lel >= (-13923*2048+29663*10800-510)/256-SEAT_C8 > 0) nor the clamps
	; move him:
	lda.b T3+2
	sec
	sbc #10800
	cmp #RIDER_TOP-10800+1
	bcs _g2rd_seatq
	lda.b T3
	clc
	adc #-RIDER_LEFT
	cmp #2048-RIDER_LEFT+1
	bcs _g2rd_seatq
	lda.b T3
	beq _g2rd_qb
	bmi _g2rd_qb
	jmp _far5
_g2rd_qb:
	jmp _rd_back
_g2rd_seatq:
	; The seat: lel = mq16( x, SEAT_NX )+mq16( y, SEAT_NY )-SEAT_C8 is at
	; least 256*(Vx+Vy)-1134203 with Vx, Vy the high bytes' products >> 8:
	; not below the seat if Vx+Vy >= 4431.
	lda.b T3
	G2_MA
	lda #$00CA                  ; -54
	sta.w MPYB
	ldx.w MPYM
	lda.b T3+2
	G2_MA
	lda #116
	sta.w MPYB
	txa
	clc
	adc.w MPYM
	bmi _g2rd_seat
	cmp #4431
	bcc _g2rd_seat
	jmp _rd_top
_g2rd_seat:
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
	CLAMP16 R
	sta.b T1                    ; l
	sep #$20
	MB_DP T1
	RSETK SEAT_NX
	RFIN 7, $808000
	lda.b T3
	jsr phys_ext32
	SUB32 T0, T0, R
	CLAMP16 T0
	sta.b T3
	sep #$20
	MB_DP T1
	RSETK SEAT_NY
	RFIN 7, $808000
	lda.b T3+2
	jsr phys_ext32
	SUB32 T0, T0, R
	CLAMP16 T0
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
	; Inside the ellipse for sure if y <= g2_ellt[x >> 8]:
	lda.b T3
	xba
	and #$00FF
	asl a
	tax
	lda.b T3+2
	cmp.l g2_ellt,x
	bcc _g2rd_noell
	bne _g2rd_ell
_g2rd_noell:
	jmp _rd_back
_g2rd_ell:
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
	ora.b G2_FLAG
	bne +
	jmp _g2rd_fast
+	lda.w pt_tmp+4
	bne +
	jmp _g2rd_sslow
+	lda.b S_TURNED
	and #$00FF
	beq +
	lda.b T3
	NEGA
	sta.b T3
+	; rider = body + rsh( mq16( Cs, x )+mq16( Sn, -y ), 6 ), body + rsh(
	; mq16( Sn, x )+mq16( Cs, y ), 6 ) as in phys_head (x in [RIDER_LEFT,
	; RIDER_RIGHT], y in [-3100, RIDER_TOP] here, after the seat: the sums
	; within 16 bits): MD0, MD2 the high signed bytes of x, y, T1 = -y and
	; its high signed byte:

	lda.b T3
	clc
	adc #$0080
	xba
	sta.b MD0
	lda.b T3+2
	clc
	adc #$0080
	xba
	sta.b MD2
	lda #0
	sec
	sbc.b T3+2
	sta.b T1
	clc
	adc #$0080
	xba
	sta.b T1+2
	lda.b CS
	G2_MA
	lda.b T3
	sta.w MPYB                  ; Cs*x0
	lda.w MPYM
	sta.b T0                    ; Ex
	lda.b MD0
	sta.w MPYB                  ; Cs*x1
	lda.w MPYL
	and #$00FF
	clc
	adc.b T0
	sta.b T0
	lda.w MPYM
	sta.b T0+2                  ; HVx
	lda.b T3+2
	sta.w MPYB                  ; Cs*y0
	lda.w MPYM
	sta.b R                     ; Ey
	lda.b MD2
	sta.w MPYB                  ; Cs*y1
	lda.w MPYL
	and #$00FF
	clc
	adc.b R
	sta.b R
	lda.w MPYM
	sta.b R+2                   ; HVy
	lda.b SN
	G2_MA
	lda.b T1
	sta.w MPYB                  ; Sn*(-y)0
	lda.w MPYM
	clc
	adc.b T0
	sta.b T0
	lda.b T1+2
	sta.w MPYB                  ; Sn*(-y)1
	lda.w MPYM
	clc
	adc.b T0+2
	sta.b T0+2
	lda.w MPYL
	and #$00FF
	clc
	adc.b T0
	G2_HEADADD T0+2, S_BODY+C_RX, S_RIDX, 0
	lda.b T3
	sta.w MPYB                  ; Sn*x0
	lda.w MPYM
	clc
	adc.b R
	sta.b R
	lda.b MD0
	sta.w MPYB                  ; Sn*x1
	lda.w MPYM
	clc
	adc.b R+2
	sta.b R+2
	lda.w MPYL
	and #$00FF
	clc
	adc.b R
	G2_HEADADD R+2, S_BODY+C_RY, S_RIDY, 0
	; dx, dy, dirx, diry again, and the fast products:
	G2_RDAX 0, 0, _g2rd_sl2
	G2_RDAX 1, 0, _g2rd_sl2
	jmp _g2rd_fast
_g2rd_sl2:
	jmp _g2rd_sslow

_g2rd_sslow:
	; The spring the slow way: dirx, diry (G2_IX, G2_IY: $FFFE outside the
	; table), dx, dy, then mvx, mvy:
	lda.w g2_ofxb
	eor #$8000
	inc a                       ; OFX
	jsr phys_ext32
	SUB32 T1, S_BODY+C_RX, T0   ; rgx
	HALFDIFF T1, S_RIDX
	clc
	adc #4079
	cmp #2*4079+1
	bcc +
	lda #$7FFF
+	asl a
	sta.b G2_IX
	lda.w g2_ofyb
	eor #$8000
	dec a                       ; OFY
	jsr phys_ext32
	ADD32 T1, S_BODY+C_RY, T0   ; rgy
	HALFDIFF T1, S_RIDY
	clc
	adc #4079
	cmp #2*4079+1
	bcc +
	lda #$7FFF
+	asl a
	sta.b G2_IY
	HALFDIFF S_RIDX, S_BODY+C_RX
	sta.b T2                    ; dx
	HALFDIFF S_RIDY, S_BODY+C_RY
	sta.b T2+2                  ; dy
_g2rd_wslow:
	; wb = rsh( body.w, 4 ); mvx = body.vx-rsh( mq24( wb, dy ), 7 ), ...;
	; R2 = rider_vx-mvx+$808080, T3 = rider_vy-mvy+$808080:
	MOV32 T3, S_BODY+C_W
	RSH32 T3, 4
	DIGT3
	MB_DP T2+2
	RSET24 MD0
	rep #$20
	RFIN 7, $808000
	lda.b S_RIDVX
	sec
	sbc.b S_BODY+C_VX
	tax
	lda.b S_RIDVX+2
	sbc.b S_BODY+C_VX+2
	tay
	txa
	clc
	adc.b R
	tax
	tya
	adc.b R+2
	tay
	txa
	clc
	adc #$8080
	sta.b R2
	tya
	adc #$0080
	sta.b R2+2
	sep #$20
	MB_DP T2
	RSET24 MD0
	rep #$20
	RFIN 7, $808000
	lda.b S_RIDVY
	sec
	sbc.b S_BODY+C_VY
	tax
	lda.b S_RIDVY+2
	sbc.b S_BODY+C_VY+2
	tay
	txa
	sec
	sbc.b R
	tax
	tya
	sbc.b R+2
	tay
	txa
	clc
	adc #$8080
	sta.b T3
	tya
	adc #$0080
	sta.b T3+2
	jmp _g2rd_mulk
_g2rd_ws:
	; (body.w changed, or w2 = -128: dx, dy for the slow way)
	lda.b T2
	cmp #$8000
	ror a
	sta.b T2
	lda.b T2+2
	cmp #$8000
	ror a
	sta.b T2+2
	jmp _g2rd_wslow
_g2rd_fast:
	; mvx = body.vx-rsh( mq24( wb, dy ), 7 ), mvy = body.vy+rsh( mq24( wb,
	; dx ), 7 ) with wb = rsh( body.w, 4 ) of the start of the step (its
	; signed bytes WD; w2 not -128 for mvy): R2 = rider_vx-mvx+$808080, T3 =

	; rider_vy-mvy+$808080.
	lda.b S_BODY+C_W
	cmp.w g2_w
	bne _g2rd_ws
	lda.b S_BODY+C_W+2
	cmp.w g2_w+2
	bne _g2rd_ws
	; rsh( mq24( wb, dy ), 7 ) = floor( (2*dy*wb+2^15)/2^16 ) = P2+V1+floor(
	; (W0+l1+128)/256 ) with 2*dy*w0 = 256*W0+.., 2*dy*w1 = 256*V1+l1 and
	; 2*dy*w2 = P2:
	lda.b T2+2
	G2_MA
	G2_WQ
	clc
	adc #$8080-64
	tax
	lda.b WD+2
	beq +
	sta.w MPYB                  ; *w2
	txa
	clc
	adc.w MPYL
	tax
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #0
	tay
	bra ++
+	ldy #$0080
++	txa
	clc
	adc.b S_RIDVX
	tax
	tya
	adc.b S_RIDVX+2
	tay
	txa
	sec
	sbc.b S_BODY+C_VX
	sta.b R2
	tya
	sbc.b S_BODY+C_VX+2
	sta.b R2+2
	; -rsh( mq24( wb, dx ), 7 ) the same way, -(V1+..) and -w2:
	lda.b T2
	G2_MA
	G2_WQ
	eor #$FFFF
	sec
	adc #$8080+64
	tax
	lda #0
	sec
	sbc.b WD+2
	beq +
	cmp #$FF80
	bne ++
	jmp _g2rd_ws
++	sta.w MPYB                  ; *(-w2)
	txa
	clc
	adc.w MPYL
	tax
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #0
	tay
	bra ++
+	ldy #$0080
++	txa
	clc
	adc.b S_RIDVY
	tax
	tya
	adc.b S_RIDVY+2
	tay
	txa
	sec
	sbc.b S_BODY+C_VY
	sta.b T3
	tya
	sbc.b S_BODY+C_VY+2
	sta.b T3+2
_g2rd_mulk:
	; v += MULK( dir, K_RIDER_S )-MULK( v-mv, K_RIDER_D )+gv, the position
	; += rsh( v, 8 ). The dampers first: R2, A = MULK( v-mv, K_RIDER_D )+32
	; (16 bits; a larger one is taken from v at once, and 32 is left):
	G2_MAK K_RIDER_D_M/2
	lda.b R2+2
	cmp #$0080
	beq +
	jmp _g2rd_dsx
+	G2_DMP R2

	sta.b R2
_g2rd_dy:
	lda.b T3+2
	cmp #$0080
	beq +
	jmp _g2rd_dsy
+	G2_DMP T3

_g2rd_spy:
	; the springs: g2_mst has MULK( dir, K_RIDER_S )+32:
	eor #$FFFF
	ldx.b G2_IY
	cpx #4*4079+1
	bcc +
	jmp _g2rd_ssy
+	sec
	adc.l g2_mst,x
	clc
	adc.b GVY
_g2rd_vy:
	G2_VPOS S_RIDVY, S_RIDY
	lda.b R2
	eor #$FFFF
	ldx.b G2_IX
	cpx #4*4079+1
	bcc +
	jmp _g2rd_ssx
+	sec

	adc.l g2_mst,x
	clc
	adc.b GVX
_g2rd_vx:
	G2_VPOS S_RIDVX, S_RIDX
	rts
_g2rd_dsx:
	; a damper of more than two bytes, taken from v at once:
	G2_DMP3 R2, S_RIDVX
	lda #32
	sta.b R2
	jmp _g2rd_dy
_g2rd_dsy:
	G2_DMP3 T3, S_RIDVY
	lda #32
	jmp _g2rd_spy

_g2rd_ssy:
	; a spring outside the table: v += MULK( dir, K_RIDER_S ), then gv
	; -MULK( v-mv, K_RIDER_D ) (dir again from the position):
	eor #$FFFF
	sta.b T3
	lda.w g2_ofyb
	eor #$8000
	dec a                       ; OFY
	jsr phys_ext32
	ADD32 T1, S_BODY+C_RY, T0   ; rgy
	HALFDIFF T1, S_RIDY
	jsr phys_ext32
	MULK T0, K_RIDER_S
	lda.b S_RIDVY
	clc
	adc.b R
	sta.b S_RIDVY
	lda.b S_RIDVY+2
	adc.b R+2
	sta.b S_RIDVY+2
	lda #32
	sec
	sbc.b T3
	clc
	adc.b GVY
	jmp _g2rd_vy
_g2rd_ssx:
	lda.w g2_ofxb
	eor #$8000
	inc a                       ; OFX
	jsr phys_ext32
	SUB32 T1, S_BODY+C_RX, T0   ; rgx
	HALFDIFF T1, S_RIDX
	jsr phys_ext32
	MULK T0, K_RIDER_S
	lda.b S_RIDVX
	clc
	adc.b R
	sta.b S_RIDVX
	lda.b S_RIDVX+2
	adc.b R+2
	sta.b S_RIDVX+2
	lda #32
	sec
	sbc.b R2
	clc
	adc.b GVX
	jmp _g2rd_vx

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

; G3: the collisions and the objects. Their direct page B bytes from $94
; (the objects reuse those of the collisions):
.DEFINE G3_DX $94               ; contacts: the signed digits of rx15 (4)
.DEFINE G3_DY $98               ; of ry15 (4)
.DEFINE G3_E $9C                ; the rest of the line's direction + $8000
.DEFINE G3_T $9E                ; tav, pos + the rounding (4)
.DEFINE G3_LEND $A4             ; the end of the list of lines
.DEFINE G3_RS $A6               ; the runs of the row: the first
.DEFINE G3_RE3 $A8              ; and the last
.DEFINE G3_SLOT $AA             ; the circle in g3_ram
.DEFINE G3_H $AC                ; 64 half (4)

; \2 = the multiplicand times the signed digits at \1 (3 bytes) >> 8, plus
; $808000, the top digit skipped when zero (A 8-bit in and out; Y is
; used). G3_SET24A adds the direct page word \3 (G3_SET24K the constant
; \3) to the low part
; in place of the bias $8000 (|the product of the lowest digit >> 8 + \3 -
; $8000| < 2^15 is needed).
.MACRO G3_SET24
	lda.b \1
	sta.w MPYB
	ldy.w MPYM
	lda.b \1+1
	sta.w MPYB
	rep #$21
	tya
	eor #$8000
	adc.w MPYL
	sta.b \2
	sep #$20
	lda.w MPYH
	eor #$80
	adc #0
	sta.b \2+2
	lda #0
	rol a
	sta.b \2+3
	lda.b \1+2
	beq _g3s24\@
	sta.w MPYB
	rep #$21
	lda.w MPYL
	adc.b \2+1
	sta.b \2+1
	sep #$20
	lda.w MPYH
	adc.b \2+3
	sta.b \2+3
_g3s24\@:
.ENDM

.MACRO G3_SET24H
	; (G3_SET24 without the lowest digit: smaller by 0 to 2^14)
	lda.b \1+1
	sta.w MPYB
	rep #$21
	lda.w MPYL
	adc #$8000
	sta.b \2
	sep #$20
	lda.w MPYH
	eor #$80
	adc #0
	sta.b \2+2
	lda #0
	rol a
	sta.b \2+3
	lda.b \1+2
	beq _g3s24h\@
	sta.w MPYB
	rep #$21
	lda.w MPYL
	adc.b \2+1
	sta.b \2+1
	sep #$20
	lda.w MPYH
	adc.b \2+3
	sta.b \2+3
_g3s24h\@:
.ENDM

.MACRO G3_SET24A
	lda.b \1
	sta.w MPYB
	ldy.w MPYM
	lda.b \1+1
	sta.w MPYB
	rep #$21
	tya
	adc.b \3
	clc
	adc.w MPYL
	sta.b \2
	sep #$20
	lda.w MPYH
	eor #$80
	adc #0
	sta.b \2+2
	lda #0
	rol a
	sta.b \2+3
	lda.b \1+2
	beq _g3s24a\@
	sta.w MPYB
	rep #$21
	lda.w MPYL
	adc.b \2+1
	sta.b \2+1
	sep #$20
	lda.w MPYH
	adc.b \2+3
	sta.b \2+3
_g3s24a\@:
.ENDM

.MACRO G3_SET24K
	lda.b \1
	sta.w MPYB
	ldy.w MPYM
	lda.b \1+1
	sta.w MPYB
	rep #$21
	tya
	adc #\3
	clc
	adc.w MPYL
	sta.b \2
	sep #$20
	lda.w MPYH
	eor #$80
	adc #0
	sta.b \2+2
	lda #0
	rol a
	sta.b \2+3
	lda.b \1+2
	beq _g3s24k\@
	sta.w MPYB
	rep #$21
	lda.w MPYL
	adc.b \2+1
	sta.b \2+1
	sep #$20
	lda.w MPYH
	adc.b \2+3
	sta.b \2+3
_g3s24k\@:
.ENDM

.DEFINE G3_FXD $B0              ; the wheel: the signed digits of clamp24( Fx ) (4)
.DEFINE G3_FYD $B4              ; of Fy (4)
.DEFINE G3_D1 $B8               ; signed digits (4)
.DEFINE G3_B $BC                ; the rolling: b (4)
.DEFINE G3_VXD $C0              ; holds: the digits of clamp16( vx >> 8 ) (2)
.DEFINE G3_VYD $C2              ; of vy (2)
.DEFINE G3_S $C4                ; nx vx + ny vy (4)
.DEFINE G3_REM $C8              ; remove (2)
.DEFINE G3_PX $D0               ; holds: S >> 16 roughly (2)
.DEFINE G3_W $D2                ; scratch (6)
.DEFINE G3_VX $D8               ; contacts: the last end point (d), its
.DEFINE G3_VY $DA               ; d2 within the radius (G3_VF 1), not (2)
.DEFINE G3_VF $DC               ; or none (0)
; contacts: two points within G3_MS on both axes are near (2 G3_MS^2 <
; MERGE_SQ).
.DEFINE G3_MS 4633
.IF 2*G3_MS*G3_MS >= MERGE_SQ
.FAIL
.ENDIF

; The multiplicand of the multiplier = A (A 16-bit, A is kept): the 16-bit
; stores to $211B write $211C too (a useless product, and its byte in the
; shared latch of the Mode 7 registers that the second store uses).
.MACRO G3_MA
	xba
	sta.w MPYA
	sta.w MPYA
	xba
.ENDM

; \2 = \1^2 + 2^23 (\1 a word of the direct page within [-32768, 32639],
; \2 a double word, \2+4 is changed; A 16-bit, X and Y are used): with the
; signed digits d0, d1 of v = \1, v^2 = 256 (v d1+F)+(v d0 & 255), F =
; floor( v d0/256 ) and v d1 >= 0; F+32768 gives the 2^23.
.MACRO G3_SQ1
	lda.b \1
	G3_MA
	clc
	adc #$0080
	eor #$0080
	sta.w MPYB                  ; v d0
	xba
	ldy.w MPYM                  ; F
	ldx.w MPYL
	sta.w MPYB                  ; v d1
	stx.b \2                    ; byte 0: the low byte of v d0
	tya
	eor #$8000
	clc
	adc.w MPYL
	sta.b \2+1
	lda.w MPYM
	xba
	and #$00FF
	adc #0
	sta.b \2+3
.ENDM

; \3 = \1^2 + \2^2 + 2^24 (the same, \3+4 is changed; G3_W is used):
.MACRO G3_SQ2
	G3_SQ1 \1, \3
	G3_SQ1 \2, G3_W
	lda.b \3
	clc
	adc.b G3_W
	sta.b \3
	lda.b \3+2
	adc.b G3_W+2
	sta.b \3+2
.ENDM

; holds: nv = rsh( S, 7 ) > -ELSZ_V for S >= G3_KEL; |nv| > BUMP_MIN_V
; for S >= G3_KB1 or S < G3_KB2.
.DEFINE G3_KEL (1-ELSZ_V)*128-64
.DEFINE G3_KB1 (BUMP_MIN_V+1)*128-64
.DEFINE G3_KB2 (-BUMP_MIN_V)*128-64
; |S - 65536 M| < 6200000 (M of phys_holds, |nx|+|ny| < 46500): no bump
; for |M| <= G3_BLIM.
.DEFINE G3_BLIM ((G3_KB1-6200000) >> 16)-1
.IF G3_BLIM < 1
.FAIL
.ENDIF

; \2 = the signed digits of clamp24( the double word \1 ) (direct page;
; G3_DIGCW: absolute), A 16-bit in, 8-bit out; Y is used.
.MACRO G3_DIGC
	lda.b \1
	clc
	adc #$8080
	tay
	lda.b \1+2
	adc #$0080
	cmp #$0100
	bcs _g3dc_c\@
	eor #$0080
	sta.b \2+2
	tya
	eor #$8080
	sta.b \2
	sep #$20
	bra _g3dc_e\@
_g3dc_c\@:
	.ACCU 16
	lda #$7F7F
	ldy.b \1+2
	bpl _g3dc_p\@
	lda #$8080
_g3dc_p\@:
	sta.b \2
	sta.b \2+2
	sep #$20
_g3dc_e\@:
.ENDM

.MACRO G3_DIGCW
	lda.w \1
	clc
	adc #$8080
	tay
	lda.w \1+2
	adc #$0080
	cmp #$0100
	bcs _g3dw_c\@
	eor #$0080
	sta.b \2+2
	tya
	eor #$8080
	sta.b \2
	sep #$20
	bra _g3dw_e\@
_g3dw_c\@:
	.ACCU 16
	lda #$7F7F
	ldy.w \1+2
	bpl _g3dw_p\@
	lda #$8080
_g3dw_p\@:
	sta.b \2
	sta.b \2+2
	sep #$20
_g3dw_e\@:
.ENDM

; The same for \1 within [-$808080, $7F7F7F] (no clamp):
.MACRO G3_DIG
	lda.b \1
	clc
	adc #$8080
	eor #$8080
	sta.b \2
	sep #$20
	lda.b \1+2
	adc #0
	sta.b \2+2
.ENDM

; \2 = the signed digits of clamp16( (the double word at \1 + X) >> 8 )
; (two bytes; A 16-bit):
.MACRO G3_DIGV
	lda.w \1+2,x
	clc
	adc #$007F
	cmp #$00FE
	bcs _g3dv_s\@
	lda.w \1+1,x               ; (|v >> 8| < 32512)
	clc
	adc #$0080
	eor #$0080
	sta.b \2
	bra _g3dv_e\@
_g3dv_s\@:
	lda.w \1+1,x
	clc
	adc #$8080
	sta.b \2
	lda.w \1+3,x
	adc #0
	and #$00FF
	bne _g3dv_c\@
	lda.b \2
	cmp #$0100
	bcc _g3dv_n\@
	eor #$8080
	sta.b \2
	bra _g3dv_e\@
_g3dv_c\@:
	cmp #$0080
	bcs _g3dv_n\@
	lda #$7F7F
	sta.b \2
	bra _g3dv_e\@
_g3dv_n\@:
	lda #$8080
	sta.b \2
_g3dv_e\@:
.ENDM

; \2 = the multiplicand times the two signed digits at \1, the whole
; product, plus $800000 (A 8-bit in and out; Y is used).
.MACRO G3_FULL
	lda.b \1
	sta.w MPYB
	ldy.w MPYL
	lda.w MPYH
	eor #$80
	sta.b \2+2
	stz.b \2+3
	lda.b \1+1
	sta.w MPYB
	rep #$21
	sty.b \2
	lda.w MPYL
	xba
	and #$FF00
	adc.b \2
	sta.b \2
	lda.w MPYM
	adc.b \2+2
	sta.b \2+2
	sep #$20
.ENDM

; \1 = (\1 >> \2) - ($808000 >> \2): the biased sum of G3_SET24 (with the
; rounding in it) shifted, 0 <= \2 <= 7 (direct page double word, A
; 16-bit; X, Y are used).
.DEFINE G3_U $CA                ; (4)
.DEFINE G3_NT $CE               ; need_t: the contact
.DEFINE G3_K $A2                ; contacts: the margin of a middle contact
.DEFINE G3_KW ((R_WHEEL_P+255) >> 8)+112 ; (of a wheel, of the head)
.DEFINE G3_KH ((R_HEAD_P+255) >> 8)+112
; The dominant axis of a line is x for |ex| >= G3_DOM (cos 45 degrees, Q15),
; else y.
.DEFINE G3_DOM 23170

; Objects: within A of a circle's center in both coordinates (halved)
; with 2 A^2 below the square limit is a hit for sure.
.DEFINE G3_AW (OBJ_WHEEL_P*45) >> 7
.DEFINE G3_AH (OBJ_HEAD_P*45) >> 7
.IF 2*G3_AW*G3_AW >= OBJ_WHEEL_SQ
.FAIL
.ENDIF
.IF 2*G3_AH*G3_AH >= OBJ_HEAD_SQ
.FAIL
.ENDIF

; MULK( Mk, K_MR ) and the free torque for Mk = +-GAS_T:
.DEFINE G3_GAS GAS_T
.DEFINE G3_MRX GAS_T*K_MR_M
.DEFINE G3_MRGAS ((G3_MRX >> 8)+((1 << (K_MR_SH-8)) >> 1)) >> (K_MR_SH-8)
.DEFINE G3_MRNGAS (((G3_MRX+255) >> 8)-((1 << (K_MR_SH-8)) >> 1)+(1 << (K_MR_SH-8))-1) >> (K_MR_SH-8)
.DEFINE G3_FRX GAS_T*K_FREE_M
.DEFINE G3_FRGAS G3_FRX >> 4
.DEFINE G3_FRNGAS (G3_FRX+15) >> 4

; The velocity of the wheel WK at \1 of page A = R >> 7 - $10100 (from
; G3_SET24K with the rounding; A 16-bit).
.MACRO G3_V7
	lda.b R+2
	asl.b R
	rol a
	sta.b R+2
	lda.b R+3
	and #$00FF
	bcc _g3v7\@
	ora #$FF00
_g3v7\@:
	tay
	lda.b R+1
	ldx.b WK
	sec
	sbc #$0100
	sta.w phys_dpa+\1,x
	tya
	sbc #$0001
	sta.w phys_dpa+\1+2,x
.ENDM

.MACRO G3_UNB
	.IF \2 == 6
	lda.b \1+1
	sec
	sbc #$8080
	sta.b G3_U
	lda.b \1+3
	and #$00FF
	eor #$0080
	sbc #$0080
	.REPT 2
	asl.b \1-1
	rol.b G3_U
	rol a
	.ENDR
	sta.b \1+2
	lda.b G3_U
	sta.b \1
	.ELSE
	.IF \2 == 7
	lda.b \1+2
	asl.b \1
	rol a
	sta.b \1+2
	ldy.b \1+1
	lda.b \1+3
	and #$00FF
	bcc _g3ub\@
	ora #$FF00
_g3ub\@:
	tax
	tya
	sec
	sbc #$0100
	sta.b \1
	txa
	sbc #$0001
	sta.b \1+2
	.ELSE
	lda.b \1+2
	.REPT \2
	cmp #$8000
	ror a
	ror.b \1
	.ENDR
	tax
	lda.b \1
	sec
	sbc #($808000 >> (\2)) & $FFFF
	sta.b \1
	txa
	sbc #($808000 >> (\2)) >> 16
	sta.b \1+2
	.ENDIF
	.ENDIF
.ENDM


; Copies a contact (\1 to \2) of the direct page B.
.MACRO CTCOPY
	ldx #CT_SIZE-2
_ctcopy_b1\@:	lda.b \1,x
	sta.b \2,x
	dex
	dex
	bpl _ctcopy_b1\@
.ENDM

; R = rsh( R, A ) for A from 0 to 31 (A 16-bit): by whole bytes for 8
; and more (phys_rshr below).
g3_rshr:
	.ACCU 16
	.INDEX 16
	cmp #8
	bcs +
	jmp phys_rshr
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
	sta.b R+2
	lda.b R+1
	sta.b R
	lda.b R+3
	and #$00FF
	cmp #$0080
	bcc +
	ora #$FF00
+	cpy #8
	beq ++
-	cmp #$8000
	ror a
	ror.b R
	dey
	cpy #8
	bne -
++	sta.b R+2
	rts

; need_t: the point of the contact at X (offset in page B) from the
; center QRX, QRY: t = r - rsh( mq16( n, h ), 7 ).
phys_need_t:
	.ACCU 16
	.INDEX 16
	lda.b CT_HT,x
	and #$00FF
	beq +
	rts
+	stx.b G3_NT
	lda.b CT_H,x
	clc
	adc #$0080
	eor #$0080
	sta.b G3_D1                 ; the digits of h
	stz.b G3_D1+2
	sep #$20
	MB_ABSX phys_dpb+CT_NX
	G3_SET24K G3_D1, R, $8040
	MB_ABSX phys_dpb+CT_NY
	G3_SET24K G3_D1, R2, $8040
	rep #$20
	G3_UNB R, 7
	G3_UNB R2, 7
	ldx.b G3_NT
	lda.b QRX
	sec
	sbc.b R
	sta.b CT_TX,x
	lda.b QRX+2
	sbc.b R+2
	sta.b CT_TX+2,x
	lda.b QRY
	sec
	sbc.b R2
	sta.b CT_TY,x
	lda.b QRY+2
	sbc.b R2+2
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
	; From the corner of the grid, within it (unsigned: below it is out):
	lda.b QRX
	sec
	sbc.w lev_gx
	sta.b QX
	lda.b QRX+2
	sbc.w lev_gx+2
	sta.b QX+2
	cmp.w lev_gw+2
	bcs _ct_out
	lda.b QRY
	sec
	sbc.w lev_gy
	sta.b QY
	lda.b QRY+2
	sbc.w lev_gy+2
	sta.b QY+2
	cmp.w lev_gh+2
	bcc _ct_in
_ct_out:
	; Racsonkivul: too far right or up. (Its bounds are 3 m and more beyond
	; the grid, tools/gen_phys.py: it is never set within the grid.)
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
+	bmi _ct_none
	lda #1
	sta.w phys_dpa+RACS
_ct_none:
	lda #0
	rts
_ct_in:
	; The list of the cell: the one of the last time when the circle is
	; still in the same cell (g3_ram: 8 bytes for each circle, WK = S_K2,
	; S_K4 or 32 for the head: the hint, a byte not used, 2 cx and 2 cy
	; (bytes), the list after its count (0: none) and its end), else from
	; the runs of the row.
	ldx.b WK
	ldy.b QHEAD
	beq +
	ldx #32                     ; the head
+	lda.b QY+1
	and #$FE00
	ora.b QX+2
	and #$FEFE                  ; 2 cy, 2 cx (the grid is within 250 m)
	cmp.w g3_ram-24+2,x
	bne _ct_miss
	ldy.w g3_ram-24+4,x
	bne +
	tya
	rts
+	lda.w g3_ram-24+6,x
	sta.b G3_LEND
_ct_list:
	stz.b G3_VF
	lda.b QX+1
	jmp _ct_line
_ct_miss:
	; The run of the row of the cell: from the one of the last time (the
	; hint: the number of the run in its row).
	sta.w g3_ram-24+2,x
	stx.b G3_SLOT
	lda.b QY+2
	and #$FFFE                  ; 2 cy
	clc
	adc.w lev_rows
	tay
	lda.w 2,y
	sbc #2                      ; (C clear)
	sta.b G3_RE3                ; the last run of the row
	lda.w 0,y
	sta.b G3_RS                 ; the first one
	lda.w g3_ram-24,x
	and #$00FF
	tax
	sta.b G3_T
	asl a
	adc.b G3_T
	adc.b G3_RS
	bcs ++
	cmp.b G3_RE3
	beq +
	bcc +
++	ldx #0                      ; (not in the row: from its start)
	lda.b G3_RS
+	tay
	lda.b QX+2
	lsr a                       ; cx
	sep #$20
	cmp.w 0,y
	bcc _ct_back
	cpy.b G3_RE3
	bcs _ct_run
	cmp.w 3,y
	bcc _ct_run
_ct_fwd:
	iny
	iny
	iny
	inx
	cpy.b G3_RE3
	bcs _ct_run
	cmp.w 3,y
	bcs _ct_fwd
	bra _ct_run
_ct_back:
	cpy.b G3_RS
	beq _ct_none8
	dey
	dey
	dey
	dex
	cmp.w 0,y
	bcc _ct_back
_ct_run:
	txa
	ldx.b G3_SLOT
	sta.w g3_ram-24,x
	rep #$20
	lda.w 1,y
	beq _ct_none16
	tay
	lda.w 0,y
	asl a
	sta.b G3_LEND
	tya
	clc
	adc #2
	sta.w g3_ram-24+4,x
	adc.b G3_LEND
	sta.b G3_LEND               ; the end of the list
	sta.w g3_ram-24+6,x
	ldy.w g3_ram-24+4,x
	jmp _ct_list
_ct_ret:
	lda.b QN
	rts
_ct_none8:
	rep #$20
	ldx.b G3_SLOT
_ct_none16:
	stz.w g3_ram-24+4,x
	lda #0
	rts
_ct_next:
	ldy.b QLIST
_ct_nexty:
	lda.b QX+1
_ct_line:                       ; (A = QX >> 8)
	cpy.b G3_LEND
	bcs _ct_ret
	ldx.w 0,y                   ; the line
	iny
	iny
	; The box of the line (QX >> 8, QY >> 8 in it):
	cmp.w 0,x
	bcc _ct_line
	beq +
	cmp.w 2,x
	beq +
	bcs _ct_line
+	lda.b QY+1
	cmp.w 4,x
	bcc _ct_nexty
	beq +
	cmp.w 6,x
	beq +
	bcs _ct_nexty
+	sty.b QLIST
	; From the middle of the line, in 2^-15 m: rx15 = (qx - M.x) >> 1, its
	; signed digits (|rx15| < 2^22: the level is within 250 m).
	lda.b QX
	sec
	sbc.w 8,x
	tay
	sep #$20
	lda.b QX+2
	sbc.w 10,x                  ; (C set if qx >= M.x)
	ror a
	eor #$80
	sta.b RX15+2
	rep #$20
	tya
	ror a
	sta.b RX15
	clc
	adc #$8080
	eor #$8080
	sta.b G3_DX
	lda.b RX15+2                ; (RX15+3, G3_DX+3: no matter)
	adc #0
	sta.b G3_DX+2
	lda.b QY
	sec
	sbc.w 11,x
	tay
	sep #$20
	lda.b QY+2
	sbc.w 13,x
	ror a
	eor #$80
	sta.b RY15+2
	rep #$20
	tya
	ror a
	sta.b RY15
	clc
	adc #$8080
	eor #$8080
	sta.b G3_DY
	sep #$20
	lda.b RY15+2
	adc #0
	sta.b G3_DY+2
	; tav = rsh( mq24( ry15, ex )+mq24( rx15, -ey )+mq16( ry15 >> 8, elx )
	;            +mq16( rx15 >> 8, -ely ), 6 ); the last two are below
	; 2^13 each.
	lda.b RY15+1
	sta.w MPYA
	lda.b RY15+2
	sta.w MPYA
	lda.w 24,x
	sta.w MPYB
	ldy.w MPYM
	lda.b RX15+1
	sta.w MPYA
	lda.b RX15+2
	sta.w MPYA
	lda.w 25,x
	eor #$FF
	inc a
	sta.w MPYB
	rep #$20
	tya
	eor #$8000
	clc
	adc.w MPYM
	sta.b G3_E                  ; + $8000
	lda.w 22,x
	NEGA
	xba
	sta.w MPYA
	sta.w MPYA                  ; -ey (see G3_MA)
	sep #$20
	G3_SET24A G3_DX, R, G3_E    ; (|the low part| < 2^15)
	lda.w 20,x
	sta.w MPYA
	lda.w 21,x
	sta.w MPYA
	G3_SET24K G3_DY, R2, $8020
	; T = the sum + 32: |tav| <= R needs -2^21 <= T < 2^21.
	rep #$21
	lda.b R
	adc.b R2
	sta.b G3_T
	lda.b R+2
	adc.b R2+2
	clc
	adc #$FEFF+32               ; - the biases, + 32 (for the test)
	cmp #64
	bcc +
	jmp _ct_next
+	xba                         ; tav = bits 6..21 of T
	asl a
	asl a
	eor #$8000
	sta.b G3_T+2
	lda.b G3_T
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	ora.b G3_T+2
	sta.b TAV
	bmi +
	cmp.b QR
	beq ++
	bcc ++
	jmp _ct_next                ; tav > R
+	clc
	adc.b QR
	bcs ++
	jmp _ct_next                ; tav < -R
++	; Surely in the middle (-half < pos < half) if the point, within R +
	; 0.0002 m of the line (tav), is more than R + 0.0196 m within the
	; extent of the line on its dominant axis: its box is that extent and
	; REACH = 0.41 m more (tools/gen_phys.py), and pos differs from the
	; projection by less than 0.007 m. In 1/256 m (QX >> 8 and the box):
	; G3_K = ceil( R/256 )+112 (set with QR).
	lda.w 20,x
	bpl +
	NEGA
+	cmp #G3_DOM
	bcc _ct_ky
	lda.w 0,x                   ; x dominant: bx0+K <= QX >> 8 <= bx1-K
	clc
	adc.b G3_K
	bcs _ct_pos
	cmp.b QX+1
	beq +
	bcs _ct_pos
+	lda.w 2,x
	sec
	sbc.b G3_K
	bcc _ct_pos
	cmp.b QX+1
	bcc _ct_pos
	jmp _ct_mid
_ct_ky:
	lda.w 4,x                   ; y dominant
	clc
	adc.b G3_K
	bcs _ct_pos
	cmp.b QY+1
	beq +
	bcs _ct_pos
+	lda.w 6,x
	sec
	sbc.b G3_K
	bcc _ct_pos
	cmp.b QY+1
	bcc _ct_pos
	jmp _ct_mid
_ct_pos:
	; pos = rsh( mq24( rx15, ex )+mq24( ry15, ey ), 6 ) against the half
	; of the line:
	sep #$20
	G3_SET24K G3_DX, R, $8020
	lda.w 22,x
	sta.w MPYA
	lda.w 23,x
	sta.w MPYA
	G3_SET24 G3_DY, R2
	rep #$21
	lda.b R
	adc.b R2
	sta.b G3_T
	lda.b R+2
	adc.b R2+2
	clc
	adc #$FEFF
	sta.b G3_T+2                ; T = the sum + 32
	; The whole words of T and 64 half (HH = half >> 10) decide unless T
	; >> 16 is HH or -HH-1: middle for -HH <= T >> 16 < HH.
	tay
	lda.w 29,x
	lsr a
	lsr a
	sta.b G3_H                  ; HH
	tya
	bmi +
	cmp.b G3_H
	bcc _ct_mid
	beq _ct_pex
	bra _ct_b                   ; pos > half
+	clc
	adc.b G3_H
	bpl _ct_mid
	inc a
	bpl _ct_pex
	jmp _ct_a                   ; pos < -half
_ct_pex:
	lda.w 27,x
	and #$FF00
	sta.b G3_H
	lda.w 29,x
	lsr a
	ror.b G3_H
	lsr a
	ror.b G3_H
	sta.b G3_H+2                ; H = 64 half
	lda.b G3_T
	clc
	adc.b G3_H
	lda.b G3_T+2
	adc.b G3_H+2
	bpl +
	jmp _ct_a                   ; pos < -half: T < -H
+	lda.b G3_T
	sec
	sbc.b G3_H
	tay
	lda.b G3_T+2
	sbc.b G3_H+2
	bmi _ct_mid                 ; pos > half: T >= H + 64
	bne _ct_b
	cpy #64
	bcc _ct_mid
_ct_b:
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
	; In the middle: n and h from the line. (The head needs only that
	; there is one; the first contact goes to CT0, a second one to CTN.)
	lda.b QHEAD
	beq +
	lda #1
	rts
+	ldy #CT0
	lda.b QN
	beq +
	ldy #CTN
+	lda.b TAV
	bmi +
	sta.w phys_dpb+CT_H,y
	lda.w 22,x
	NEGA
	sta.w phys_dpb+CT_NX,y
	lda.w 20,x
	sta.w phys_dpb+CT_NY,y
	bra ++
+	NEGA
	sta.w phys_dpb+CT_H,y
	lda.w 22,x
	sta.w phys_dpb+CT_NX,y
	lda.w 20,x
	NEGA
	sta.w phys_dpb+CT_NY,y
++	lda.w 26,x
	sta.w phys_dpb+CT_DN,y
	lda #$0100
	sta.w phys_dpb+CT_HT,y      ; has_n
	jmp _ct_found
_ct_a:
	; The start: A = 2M - B - par, d = q - A = q + B + par - 2M.
	lda.w 8,x
	asl a
	sta.b T0
	lda.w 10,x
	and #$00FF
	rol a
	sta.b T0+2                  ; 2 M.x
	lda.w 31,x
	lsr a                       ; (C: par bit 0)
	lda.w 14,x
	adc.b QX
	tay
	lda.w 16,x
	and #$00FF
	adc.b QX+2
	sta.b DDX+2
	tya
	sec
	sbc.b T0
	sta.b DDX
	lda.b DDX+2
	sbc.b T0+2
	sta.b DDX+2
	lda.w 11,x
	asl a
	sta.b T0
	lda.w 13,x
	and #$00FF
	rol a
	sta.b T0+2                  ; 2 M.y
	lda.w 31,x
	lsr a
	lsr a                       ; (C: par bit 1)
	lda.w 17,x
	adc.b QY
	tay
	lda.w 19,x
	and #$00FF
	adc.b QY+2
	sta.b DDY+2
	tya
	sec
	sbc.b T0
	sta.b DDY
	lda.b DDY+2
	sbc.b T0+2
	sta.b DDY+2
_ct_end:
	; Within the radius of an end point:
	ldx #DDX
	jsr phys_within
	bcc +
	ldx #DDY
	jsr phys_within
	bcs ++
+	jmp _ct_next
++	; The end point of the line before (the vertex of both): its d2.
	lda.b DDX
	cmp.b G3_VX
	bne +
	lda.b DDY
	cmp.b G3_VY
	bne +
	lda.b G3_VF
	beq +
	lsr a
	bcc _ct_endout              ; 2: not within
	jmp _ct_endin               ; 1: within
_ct_endout:
	jmp _ct_next
+	G3_SQ2 DDX, DDY, T1         ; d2 + 2^24
	lda.b DDX
	sta.b G3_VX
	lda.b DDY
	sta.b G3_VY
	lda.b T1
	cmp.b QRSQ
	lda.b T1+2
	sbc.b QRSQ+2
	cmp #$0100                  ; (signed: d2-QRSQ within +-2^30)
	bmi +
	lda #2
	sta.b G3_VF
	jmp _ct_next
+	lda #1
	sta.b G3_VF
_ct_endin:
	lda.b QHEAD
	beq +
	lda #1
	rts
+	ldy #CT0
	lda.b QN
	beq +
	ldy #CTN
+	lda.b QRX
	sec
	sbc.b DDX
	sta.w phys_dpb+CT_TX,y
	lda.b QRX+2
	sbc.b DDX+2
	sta.w phys_dpb+CT_TX+2,y
	lda.b QRY
	sec
	sbc.b DDY
	sta.w phys_dpb+CT_TY,y
	lda.b QRY+2
	sbc.b DDY+2
	sta.w phys_dpb+CT_TY+2,y
	lda #1
	sta.w phys_dpb+CT_HT,y      ; has_t
	lda #0
	sta.w phys_dpb+CT_DN,y
_ct_found:
	lda.b QN
	bne +
	inc.b QN                    ; (it is in CT0)
	jmp _ct_next
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
	; Within G3_MS on both axes: near for sure (no squares).
	lda.b T0
	clc
	adc #G3_MS
	cmp #2*G3_MS+1
	bcs ++
	lda.b T1
	clc
	adc #G3_MS
	cmp #2*G3_MS+1
	bcs ++
	lda.b T0
	ora.b T1
	beq +
	jmp _ct_mrg
+	jmp _ct_same                ; the same point
++	G3_SQ2 T0, T1, T2           ; d2 + 2^24
	lda.b T2
	cmp #MERGE_SQ & $FFFF
	lda.b T2+2
	sbc #(MERGE_SQ >> 16)+$0100
	bcc _ct_mrg
	jmp _ct_two
_ct_mrg:
	; (t0 + tn) >> 1:
	ADD32 T0, CT0+CT_TX, CTN+CT_TX
	ASR32 T0, 1
	MOV32 CT0+CT_TX, T0
	ADD32 T0, CT0+CT_TY, CTN+CT_TY
	ASR32 T0, 1
	MOV32 CT0+CT_TY, T0
_ct_same:
	sep #$20
	stz.b CT0+CT_HN
	rep #$20
	stz.b CT0+CT_DN
	jmp _ct_next
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

; A = unit15( rsh( v*MB, 14 ) ) for v = A within [-32640, 32639], MB > 0
; (A 16-bit; X, G3_W are used): with the signed digits d0, d1 of v, U =
; MB d1+F+32+32768 (F = floor( MB d0/256 )) = q 65536+L, the result is
; (U >> 6)-512 = (q+32) 1024+(L >> 6)-33280.
.MACRO G3_NQ
	clc
	adc #$0080
	eor #$0080
	sta.w MPYB                  ; MB d0
	xba
	ldx.w MPYM                  ; F (within +-16384)
	sta.w MPYB                  ; MB d1
	txa
	clc
	adc #32800
	clc
	adc.w MPYL
	tax                         ; L
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #$FFA0                  ; q+32
	cmp #64
	bcs _nq_e\@
	asl a
	asl a
	xba
	sta.b G3_W
	txa
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	clc
	adc.b G3_W
	sec
	sbc #513
	bcc _nq_lo\@                ; below -32767
	adc #$8000                  ; (C set: - 32767)
	bra _nq_d\@
_nq_e\@:
	cmp #$8000
	bcs _nq_lo\@                ; q < -32
	cmp #64
	bne _nq_hi\@                ; q > 32
	txa
	bmi _nq_hi\@
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	clc
	adc #32256
	bra _nq_d\@
_nq_hi\@:
	lda #32767
	bra _nq_d\@
_nq_lo\@:
	lda #-32767
_nq_d\@:
.ENDM

; norm: n and h of the contact at X (offset in page B) from d = DDX, DDY
; (P). The usual case is fast: d within 16 bits and k = 1 (|d| from 0.25
; to 0.5 m); the rest the slow way.
phys_norm:
	.ACCU 16
	.INDEX 16
	stx.b NCT
	stz.b NSH
	lda.b DDX                   ; d within [-32640, 32639]?
	clc
	adc #32640
	tay
	lda.b DDX+2
	adc #0
	bne _no_sh
	cpy #65280
	bcs _no_sh
	lda.b DDY
	clc
	adc #32640
	tay
	lda.b DDY+2
	adc #0
	bne _no_sh
	cpy #65280
	bcs _no_sh
	jmp _no_sq
_no_sh:
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
	jmp _no_d2
_no_sq:
	G3_SQ2 DDX, DDY, T1
	lda.b T1+2
	sec
	sbc #$0100
	sta.b T1+2                  ; d2
_no_d2:
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
	ldy.b T2
	cpy #1
	bne +
	ldy.b NSH
	beq ++
+	jmp _no_slow
++
	; The fast case: n = unit15( rsh( d Y, 14 ) ), h = clamp16( rsh( (X
	; >> 17) Y, 14 ) ):
	G3_MA
	lda.b DDX
	G3_NQ
	ldx.b NCT
	sta.b CT_NX,x
	lda.b DDY
	G3_NQ
	ldx.b NCT
	sta.b CT_NY,x
	lda.b T1+2
	lsr a
	cmp #32640
	bcc +
	jmp _no_h
+	G3_NQ
	cmp #32640
	bcc +
	lda #32639
+	ldx.b NCT
	sta.b CT_H,x
	rts
_no_slow:
	sep #$20
	MB_DP T0
	rep #$20
	lda.b DDX
	jsr phys_mfa
	lda #15
	sec
	sbc.b T2
	jsr g3_rshr
	jsr phys_unit15
	ldx.b NCT
	sta.b CT_NX,x
	lda.b DDY
	jsr phys_mfa
	lda #15
	sec
	sbc.b T2
	jsr g3_rshr
	jsr phys_unit15
	ldx.b NCT
	sta.b CT_NY,x
_no_h:
	; h = clamp16( rsh( mf16( X >> 17, Y ), 13+k ) << sh ):
	lda.b T1+2
	lsr a
	jsr phys_mfa
	lda #13
	clc
	adc.b T2
	jsr g3_rshr
	ldx.b NSH
	beq +
-	asl.b R
	rol.b R+2
	dex
	bne -
+	CLAMP16 R
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

; \1 = rsh( \1 - \2, 7 ) (a double word of the direct page; RFIN 7, \2 of
; R) by one shift: 2 \1 >> 8, the carry of the shift its sign (A 16-bit, Y
; is used, \1+4 is read):
.MACRO G3_FIN7
	lda.b \1
	clc
	adc #(64-(\2)) & $FFFF
	sta.b \1
	lda.b \1+2
	adc #((64-(\2)) >> 16) & $FFFF
	asl.b \1
	rol a
	sta.b \1+2
	ldy.b \1+1
	lda.b \1+3
	and #$00FF
	bcc _g3f7\@
	ora #$FF00
_g3f7\@:
	sta.b \1+2
	sty.b \1
.ENDM

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
	G3_FIN7 R, $808000
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
	G3_FIN7 R, $808000
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
; A nonzero: the velocity towards the point goes. The signed digits of Fx,
; Fy are in G3_FXD, G3_FYD (phys_wheel).
phys_holds:
	.ACCU 16
	.INDEX 16
	stx.b NCT
	sta.b G3_REM
	; vx = clamp16( k->vx >> 8 ), vy: their signed digits:
	ldx.b WK
	G3_DIGV phys_dpa+C_VX, G3_VXD
	G3_DIGV phys_dpa+C_VY, G3_VYD
	; F n = mq24( Fx, nx )+mq24( Fy, ny ), and M = (nx d1(vx)) >> 8 +
	; (ny d1(vy)) >> 8 from the high digits of vx, vy:
	ldx.b NCT
	sep #$20
	MB_ABSX phys_dpb+CT_NX
	G3_SET24H G3_FXD, R2
	lda.b G3_VXD+1
	sta.w MPYB
	ldy.w MPYM
	sty.b G3_PX
	MB_ABSX phys_dpb+CT_NY
	G3_SET24H G3_FYD, T1
	lda.b G3_VYD+1
	sta.w MPYB
	rep #$21
	lda.w MPYM
	adc.b G3_PX
	sta.b G3_PX
	; F n without the products of the lowest digits (F', each of those
	; within [-2^14, 2^14)): F n > 0 for F' > 32768, <= 0 for F' < -32766.
	lda.b R2
	clc
	adc.b T1
	tay
	lda.b R2+2
	adc.b T1+2
	sec
	sbc #$0101
	bmi +
	bne _ho_fp
	cpy #$8001
	bcs _ho_fp
	bra _ho_fx
+	cmp #$FFFF
	bne _ho_yes
	cpy #$8002
	bcc _ho_yes
_ho_fx:
	; F n = F' + the products of the lowest digits:
	sta.b R2+2
	sty.b R2
	ldx.b NCT
	sep #$20
	MB_ABSX phys_dpb+CT_NX
	lda.b G3_FXD
	sta.w MPYB
	ldy.w MPYM
	MB_ABSX phys_dpb+CT_NY
	lda.b G3_FYD
	sta.w MPYB
	rep #$21
	tya
	adc.w MPYM                  ; (within [-32768, 32766])
	ldy #0
	cmp #$8000
	bcc +
	dey
+	clc
	adc.b R2
	tax
	tya
	adc.b R2+2
	bmi _ho_yes
	bne _ho_fp
	txa
	beq _ho_yes
_ho_fp:
	; The force away: no contact if moving away too (nv > -ELSZ_V, S >=
	; G3_KEL with S = mf16( nx, vx )+mf16( ny, vy ), nv = rsh( S, 7 )):
	jsr _ho_s
	lda.b G3_S
	cmp #G3_KEL & $FFFF
	lda.b G3_S+2
	sbc #(G3_KEL >> 16) & $FFFF
	bvc +
	eor #$8000
+	bmi _ho_yesn
	clc
	rts
_ho_yes:
	; No bump for sure if |M| <= G3_BLIM (|S - 65536 M| < 6200000):
	lda.b G3_REM
	bne _ho_ex
	lda.b G3_PX
	clc
	adc #G3_BLIM
	cmp #2*G3_BLIM+1
	bcs _ho_ex
	ldx.b NCT
	sec
	rts
_ho_ex:
	jsr _ho_s
	lda.b G3_REM
	bne _ho_nvj
	lda.b G3_S
	cmp #G3_KB1 & $FFFF
	lda.b G3_S+2
	sbc #(G3_KB1 >> 16) & $FFFF
	bvc +
	eor #$8000
+	bpl _ho_nvj
_ho_yesn:
	; A bump needs S < G3_KB2 (or S >= G3_KB1, ruled out here):
	lda.b G3_REM
	bne _ho_nvj
	lda.b G3_S
	cmp #G3_KB2 & $FFFF
	lda.b G3_S+2
	sbc #(G3_KB2 >> 16) & $FFFF
	bvc +
	eor #$8000
+	bmi _ho_nvj
	ldx.b NCT
	sec
	rts
_ho_nvj:
	jmp _ho_nv
; G3_S = S = mf16( nx, vx )+mf16( ny, vy ) of the contact NCT.
_ho_s:
	ldx.b NCT
	sep #$20
	MB_ABSX phys_dpb+CT_NX
	G3_FULL G3_VXD, R
	MB_ABSX phys_dpb+CT_NY
	G3_FULL G3_VYD, T0
	rep #$21
	lda.b R
	adc.b T0
	sta.b G3_S
	lda.b R+2
	adc.b T0+2
	sec
	sbc #$0100
	sta.b G3_S+2
	rts
_ho_nv:
	MOV32 NV, G3_S
	G3_FIN7 NV, 0
	lda.b G3_REM
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
	G3_FIN7 R, $808000
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
	G3_FIN7 R, $808000
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

; A = clamp16( the double word \1 of the direct page ), [-32640, 32639]
; (X is changed):
.MACRO G3_CL16
	lda.b \1+2
	beq _g3cl_p\@
	inc a
	bne _g3cl_s\@
	lda.b \1
	cmp #-32640
	bcs _g3cl_d\@
	lda #-32640
	bra _g3cl_d\@
_g3cl_s\@:
	ldx #\1
	jsr phys_clamp16
	bra _g3cl_d\@
_g3cl_p\@:
	lda.b \1
	cmp #32640
	bcc _g3cl_d\@
	lda #32639
_g3cl_d\@:
.ENDM

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
	G3_CL16 T0
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
	G3_CL16 T0
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
	G3_CL16 T0
	sta.b T0
	G3_CL16 T1
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
	G3_FIN7 R, 2*$808000
	G3_CL16 R
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
	; fn = rsh( mq24( Fx, -ny )+mq24( Fy, nx ), 7 ) (the digits of Fx, Fy
	; from phys_wheel):
	ldx.b T2+2
	lda.b CT_NY,x
	NEGA
	sta.b T0
	sep #$20
	MB_DP T0
	RSET24 G3_FXD
	MB_ABSX phys_dpb+CT_NX
	RADD24 G3_FYD
	rep #$20
	G3_FIN7 R, 2*$808000
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

; The circle at X of the page A (D = PHYS_DPA) moves with its velocity:
; a = wrap( a+w ), r += rsh( v, 8 ) (A 16-bit; X is kept).
.MACRO G3_MOVE
	lda.b C_A,x
	clc
	adc.b C_W,x
	sta.b C_A,x
	lda.b C_A+2,x
	adc.b C_W+2,x
	sta.b C_A+2,x
	; wrap: back between -pi and pi (signed, by the biased high words):
	eor #$8000
	cmp #((PI_W >> 16) & $FFFF)+$8000
	bcc _g3mv_lt\@
	bne _g3mv_ge\@
	lda.b C_A,x
	cmp #PI_W & $FFFF
	bcc _g3mv_r\@
_g3mv_ge\@:
	lda.b C_A,x                ; a >= pi
	sec
	sbc #TWOPI_W & $FFFF
	sta.b C_A,x
	lda.b C_A+2,x
	sbc #TWOPI_W >> 16
	sta.b C_A+2,x
	bra _g3mv_r\@
_g3mv_lt\@:
	cmp #(((-PI_W) >> 16) & $FFFF)-$8000
	bcc _g3mv_add\@
	bne _g3mv_r\@
	lda.b C_A,x
	cmp #(-PI_W) & $FFFF
	bcs _g3mv_r\@
_g3mv_add\@:
	lda.b C_A,x                ; a < -pi
	clc
	adc #TWOPI_W & $FFFF
	sta.b C_A,x
	lda.b C_A+2,x
	adc #TWOPI_W >> 16
	sta.b C_A+2,x
_g3mv_r\@:
	; r += rsh( v, 8 ) = (v >> 8) + bit 7 of v:
	lda.b C_VX-1,x
	asl a
	lda.b C_VX+1,x
	adc.b C_RX,x
	sta.b C_RX,x
	lda.b C_VX+3,x
	and #$00FF
	eor #$0080
	adc.b C_RX+2,x
	sec
	sbc #$0080
	sta.b C_RX+2,x
	lda.b C_VY-1,x
	asl a
	lda.b C_VY+1,x
	adc.b C_RY,x
	sta.b C_RY,x
	lda.b C_VY+3,x
	and #$00FF
	eor #$0080
	adc.b C_RY+2,x
	sec
	sbc #$0080
	sta.b C_RY+2,x
.ENDM

; The wheel moves with its velocity: a += w, r += rsh( v, 8 ) (page A, the
; wheel at X).
phys_move:
	.ACCU 16
	.INDEX 16
	G3_MOVE
	rts

; beallit for the wheel WK with the force FX, FY and the torque MK of page
; A; the change of its angle is its new w. D = PHYS_DPB; QR, QRSQ, G3_K,
; QHEAD are those of a wheel (phys_step).
phys_wheel:
	.ACCU 16
	.INDEX 16
	stz.b QN
	; phys_contacts with the center and its place in the grid from here:
	ldx.b WK
	lda.w phys_dpa+C_RX,x
	sta.b QRX
	sec
	sbc.w lev_gx
	sta.b QX
	lda.w phys_dpa+C_RX+2,x
	sta.b QRX+2
	sbc.w lev_gx+2
	sta.b QX+2
	cmp.w lev_gw+2
	bcs ++
	lda.w phys_dpa+C_RY,x
	sta.b QRY
	sec
	sbc.w lev_gy
	sta.b QY
	lda.w phys_dpa+C_RY+2,x
	sta.b QRY+2
	sbc.w lev_gy+2
	sta.b QY+2
	cmp.w lev_gh+2
	bcs +++
	jsr _ct_in
	bra ++++
++	lda.w phys_dpa+C_RY,x
	sta.b QRY
	lda.w phys_dpa+C_RY+2,x
	sta.b QRY+2
+++	jsr _ct_out
++++	sta.b WN
	bne +
	jmp _wh_free
+	; The signed digits of clamp24( Fx ), clamp24( Fy ) (biztostalppont_regi,
	; holds and the rolling use them):
	G3_DIGCW phys_dpa+FX, G3_FXD
	rep #$20
	G3_DIGCW phys_dpa+FY, G3_FYD
	rep #$20
	lda.b CT0+CT_HN             ; (need_n, push: their quick cases here)
	and #$00FF
	bne +
	ldx #CT0
	jsr phys_need_n
+	lda.b CT0+CT_H
	cmp #BAND_P
	bpl +
	ldx #CT0
	jsr phys_push
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
	G3_CL16 T0
	sta.b T0
	G3_CL16 T1
	sta.b T0+2
	G3_SQ2 T0, T0+2, T1         ; v2 + 2^24
	lda.b T1+2
	cmp #((V1MS_16*V1MS_16) >> 16)+$0100
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
+	ldx #CT0
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
	jmp _wh_held
+	jmp _wh_roll

_wh_free:
	ldx.b WR
	sep #$20
	lda #0
	sta.w phys_dpa+R_ON,x
	rep #$20
	; Free in the air: w += the torque * K_FREE (whole products); none
	; without a torque, constants for the gas.
	lda.w phys_dpa+MK
	ldx.w phys_dpa+MK+2
	bne _wh_fmn
	cmp #0
	bne +
	ldx.b WK
	jmp _wh_fv
+	.IF K_FREE_SH == 4
	cmp #G3_GAS
	bne _wh_fmg
	lda #G3_FRGAS & $FFFF
	sta.b R
	lda #G3_FRGAS >> 16
	sta.b R+2
	jmp _wh_fw
_wh_fmn:
	cpx #$FFFF
	bne _wh_fmg
	cmp #(-G3_GAS) & $FFFF
	bne _wh_fmg
	lda #(-G3_FRNGAS) & $FFFF
	sta.b R
	lda #((-G3_FRNGAS) >> 16) & $FFFF
	sta.b R+2
	jmp _wh_fw
	.ELSE
_wh_fmn:
	.ENDIF
_wh_fmg:
	G3_DIGCW phys_dpa+MK, G3_D1
	MB_IMM K_FREE_M
	lda.b G3_D1
	sta.w MPYB
	lda.w MPYL
	pha                         ; the lowest byte of the product
	G3_SET24 G3_D1, R
	rep #$20
	lda.b R
	sec
	sbc #$8000
	sta.b R
	lda.b R+2
	sbc #$0080
	.REPT 4
	asl.b R
	rol a
	.ENDR
	sta.b R+2
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
_wh_fw:
	ldx.b WK
	lda.w phys_dpa+C_W,x
	clc
	adc.b R
	sta.w phys_dpa+C_W,x
	lda.w phys_dpa+C_W+2,x
	adc.b R+2
	sta.w phys_dpa+C_W+2,x
_wh_fv:
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
	G3_FIN7 R, 2*$808000
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
	sep #$20
	MB_DP N90X
	G3_SET24K G3_FXD, R, $8040
	MB_DP N90Y
	G3_SET24 G3_FYD, R2
	rep #$21
	lda.b R
	adc.b R2
	sta.b FN
	lda.b R+2
	adc.b R2+2
	clc
	adc #$FEFF                  ; - the biases (the rounding is in R)
	asl.b FN
	rol a                       ; (C: the sign)
	sta.b FN+2
	lda.b FN+3
	and #$00FF
	bcc +
	ora #$FF00
+	tax                         ; fn, high word
	lda.b FN+1                  ; low word
	; the signed digits of clamp24( fn ) for MULK( fn, K_FN ):
	clc
	adc #$8080
	tay
	txa
	adc #$0080
	cmp #$0100
	bcs _wh_fnc
	eor #$0080
	sta.b G3_D1+2
	tya
	eor #$8080
	sta.b G3_D1
	bra _wh_fnd
_wh_fnc:
	lda #$7F7F
	cpx #$8000
	bcc +
	lda #$8080
+	sta.b G3_D1
	sta.b G3_D1+2
_wh_fnd:
	; rho = 1/(theta + m h^2) from the table, h within 0..26367 (rhod f
	; fits 16 bits):
	lda.b CT0+CT_H
	bpl +
	lda #0
+	cmp #26368
	bcc +
	lda #26367
+	tay
	asl a
	xba
	and #$00FF
	asl a
	tax                         ; 2i
	lda.l phys_rhod,x
	xba
	sta.w MPYA                  ; (the 16-bit stores: see G3_MA)
	sta.w MPYA
	tya
	and #$007F
	sta.w MPYB                  ; f
	lda.w MPYL
	clc
	adc #64
	asl a
	xba
	and #$00FF
	bcc +
	ora #$FF00                  ; (rhod f+64) >> 7
+	clc
	adc.l phys_rho,x
	sta.b HRHO
	; b = MULK( fn, K_FN )+MULK( Mk, K_MR ):
	sep #$20
	MB_IMM K_FN_M
	G3_SET24K G3_D1, R, $8000+((1 << (K_FN_SH-8)) >> 1)
	rep #$20
	G3_UNB R, K_FN_SH-8
	; MULK( Mk, K_MR ): none without a torque, constants for the gas:
	lda.w phys_dpa+MK
	ldx.w phys_dpa+MK+2
	bne _wh_mkn
	cmp #0
	bne +
	jmp _wh_sp                  ; Mk = 0: b = R
+	cmp #G3_GAS
	bne _wh_mkg
	lda.b R
	clc
	adc #G3_MRGAS & $FFFF
	sta.b R
	lda.b R+2
	adc #G3_MRGAS >> 16
	sta.b R+2
	jmp _wh_sp
_wh_mkn:
	cpx #$FFFF
	bne _wh_mkg
	cmp #(-G3_GAS) & $FFFF
	bne _wh_mkg
	lda.b R
	sec
	sbc #G3_MRNGAS & $FFFF
	sta.b R
	lda.b R+2
	sbc #(G3_MRNGAS >> 16) & $FFFF
	sta.b R+2
	jmp _wh_sp
_wh_mkg:
	MOV32 G3_B, R
	G3_DIGCW phys_dpa+MK, G3_D1
	MB_IMM K_MR_M
	G3_SET24K G3_D1, R, $8000+((1 << (K_MR_SH-8)) >> 1)
	rep #$20
	G3_UNB R, K_MR_SH-8
	ADD32 R, G3_B, R
_wh_sp:
	; sp = clamp24( sp + rsh( mq24( b, rho ), 5 ) ):
	G3_DIGC R, G3_D1
	MB_DP HRHO
	G3_SET24K G3_D1, R, $8010
	rep #$20
	lda.b R+2
	.REPT 5
	cmp #$8000
	ror a
	ror.b R
	.ENDR
	tax
	lda.b R
	clc
	adc.b SP
	tay
	txa
	adc.b SP+2
	tax
	tya
	sec
	sbc #($808000 >> 5) & $FFFF
	sta.b SP
	txa
	sbc #($808000 >> 5) >> 16
	sta.b SP+2
	clc
	adc #$007F
	cmp #$00FE
	bcc +
	ldx #SP
	jsr phys_clamp24
+
	; w = 40 sp = 8 (sp + 4 sp):
	lda.b SP
	asl a
	sta.b G3_U
	lda.b SP+2
	rol a
	asl.b G3_U
	rol a
	tax
	lda.b G3_U
	clc
	adc.b SP
	sta.b G3_U
	txa
	adc.b SP+2
	.REPT 3
	asl.b G3_U
	rol a
	.ENDR
	ldx.b WK
	sta.w phys_dpa+C_W+2,x
	lda.b G3_U
	sta.w phys_dpa+C_W,x
	; v = rsh( mq24( sp, n90 ), 7 ):
	G3_DIG SP, G3_D1
	MB_DP N90X
	G3_SET24K G3_D1, R, $8040
	rep #$20
	G3_V7 C_VX
	sep #$20
	MB_DP N90Y
	G3_SET24K G3_D1, R, $8040
	rep #$20
	G3_V7 C_VY
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
	ldx.b WK
	pea PHYS_DPA
	pld
	G3_MOVE
	pea PHYS_DPB
	pld
	rts

;---------------------------------------------------------------------------
; Objects (D = PHYS_DPB; the circles are read in page A).

; The candidates of the objects, kept for the next steps (g3x_ram): the
; active objects within OC_M+1 whole meters of the box of the circles of a
; step (whole meters: the high words of the positions). They hold all the
; objects that can touch a circle while each circle stays within OC_M m of
; that box (an object touches one within 1 m only: their whole meters
; differ by 1 at most). phys_level clears OC_N.
.DEFINE OC_X0 g3x_ram+0         ; the box of the circles, OC_M more: its
.DEFINE OC_XW g3x_ram+2         ; lowest whole meter and width (x, y)
.DEFINE OC_Y0 g3x_ram+4
.DEFINE OC_YW g3x_ram+6
.DEFINE OC_N g3x_ram+8          ; the number of candidates, $FFFF: none kept
.DEFINE OC_L g3x_ram+10         ; 3 times their numbers, from the last one
.DEFINE OC_MAX 22
.DEFINE OC_M 0                  ; the margin of the box (m)
; Page B bytes of the objects (G3_OL: the candidates of a step when there
; are more than OC_MAX, up to 52):
.DEFINE G3_LP $94               ; the candidates: their list
.DEFINE G3_LN $96               ; and number
.DEFINE G3_LM $98               ; the room of the list
.DEFINE G3_BX $9A               ; the whole meters of the circles ($8000
.DEFINE G3_BX1 $9C              ; added): the lowest and highest x
.DEFINE G3_BY $9E               ; and y
.DEFINE G3_BY1 $A0
.DEFINE G3_CX0 $A2              ; the candidates: their lowest whole meter
.DEFINE G3_CXW $A4              ; and the width (x, y)
.DEFINE G3_CY0 $A6
.DEFINE G3_CYW $A8
.DEFINE G3_OC $AA               ; the circle: its position in page A
.DEFINE G3_OL $AC

; sprite (utkozikesprite): A = the offset (12 times the number) of the
; first active object within the circle at G3_OC of page A (a wheel or the
; head: lim T2 (P) and square limit T3 (2^-30 m^2)), or $FFFF; T0+2, T1+2
; hold the high words of its position. Only the candidates of phys_objects
; are tested (G3_LP, G3_LN): they hold all the objects that can touch a
; circle, in the order of the objects from the end of the list.
phys_sprite:
	.ACCU 16
	.INDEX 16
	ldy.b G3_LN
_sp_loop:
	dey
	bpl +
	lda #$FFFF
	rts
+	lda (G3_LP),y
	and #$00FF
	asl a
	asl a
	tax                         ; 12 o
	; Within 1 m only when the whole meters differ by 1 at most:
	lda.l phys_objs+6,x
	sec
	sbc.b T0+2
	inc a
	cmp #3
	bcs _sp_loop
	lda.l phys_objs+10,x
	sec
	sbc.b T1+2
	inc a
	cmp #3
	bcs _sp_loop
	lda.l phys_objs+2,x
	and #$FF00                  ; active
	beq _sp_loop
	; The rest of the circle:
	phy
	ldy.b G3_OC
	lda.w phys_dpa,y
	sta.b T0
	lda.w phys_dpa+4,y
	sta.b T1
	ply
	lda #OBJ_HEAD_P
	sta.b T2
	lda #G3_AH
	sta.b T2+2
	lda #OBJ_HEAD_SQ & $FFFF
	sta.b T3
	lda #OBJ_HEAD_SQ >> 16
	sta.b T3+2
	lda.b G3_OC
	cmp #S_HEADX
	beq +
	lda #OBJ_WHEEL_P & $FFFF
	sta.b T2
	lda #G3_AW
	sta.b T2+2
	lda #OBJ_WHEEL_SQ & $FFFF
	sta.b T3
	lda #OBJ_WHEEL_SQ >> 16
	sta.b T3+2
+	lda.b T0
	sec
	sbc.l phys_objs+4,x
	sta.b R
	lda.b T0+2
	sbc.l phys_objs+6,x
	sta.b R+2
	jsr _sp_within
	bcs +
	jmp _sp_loop
+	lda.b T1
	sec
	sbc.l phys_objs+8,x
	sta.b R
	lda.b T1+2
	sbc.l phys_objs+10,x
	sta.b R+2
	jsr _sp_within
	bcs +
	jmp _sp_loop
+	; (dx >> 1)^2 + (dy >> 1)^2 < sq:
	lda.b R+2
	cmp #$8000
	ror a
	lda.b R
	ror a
	sta.b R2+2                  ; dy >> 1
	phx
	lda.b T0
	sec
	sbc.l phys_objs+4,x
	sta.b R2
	lda.b T0+2
	sbc.l phys_objs+6,x
	cmp #$8000
	ror a
	ror.b R2                    ; dx >> 1
	; Deep within (|x|, |y| <= T2+2, 2 (T2+2)^2 < sq): no squares needed.
	lda.b R2
	bpl +
	eor #$FFFF
	inc a
+	cmp.b T2+2
	beq +
	bcs _sp_sq
+	lda.b R2+2
	bpl +
	eor #$FFFF
	inc a
+	cmp.b T2+2
	beq +
	bcs _sp_sq
+	pla                         ; 12 o
	rts
_sp_sq:
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
	cmp.b T3+2
	bcc _sp_hit
	bne _sp_no
	cpx.b T3
	bcc _sp_hit
_sp_no:
	plx
	jmp _sp_loop
_sp_hit:
	pla                         ; 12 o
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

; The lowest and highest whole meters \4, \5 ($8000 added) of the three
; at \1, \2, \3 (absolute):
.MACRO G3_OMM
	lda.w \1
	eor #$8000
	sta.b \4
	sta.b \5
	lda.w \2
	eor #$8000
	cmp.b \4
	bcs +
	sta.b \4
	bra ++
+	cmp.b \5
	bcc ++
	sta.b \5
++	lda.w \3
	eor #$8000
	cmp.b \4
	bcs +
	sta.b \4
	bra ++
+	cmp.b \5
	bcc ++
	sta.b \5
++
.ENDM

; To _ob_new unless the whole meter at \1 is within the box from \2 of
; width \3:
.MACRO G3_OIN
	lda.w \1
	sec
	sbc.w \2
	cmp.w \3
	bcs _ob_new
.ENDM

; vizsgalat's objects: eats, kills, finishes (EV). D = PHYS_DPA here. The
; candidates of phys_sprite: the kept ones (or new ones) within 1 m of the
; box of the circles (in whole meters).
phys_objects:
	.ACCU 16
	.INDEX 16
	pea PHYS_DPB
	pld
	lda.w OC_N
	bmi _ob_new
	G3_OIN phys_dpa+S_K2+C_RX+2, OC_X0, OC_XW
	G3_OIN phys_dpa+S_K4+C_RX+2, OC_X0, OC_XW
	G3_OIN phys_dpa+S_HEADX+2, OC_X0, OC_XW
	G3_OIN phys_dpa+S_K2+C_RY+2, OC_Y0, OC_YW
	G3_OIN phys_dpa+S_K4+C_RY+2, OC_Y0, OC_YW
	G3_OIN phys_dpa+S_HEADY+2, OC_Y0, OC_YW
	lda #OC_L
	sta.b G3_LP
	lda.w OC_N
	sta.b G3_LN
	bne _ob_some
	jmp _ob_ret
_ob_new:
	jsr _ob_scan
	lda.b G3_LN
	bne _ob_some
	jmp _ob_ret
_ob_some:
	stz.w pt_tmp+6              ; dead
	stz.w pt_tmp+8              ; finished
_ob_again:
	stz.w pt_tmp+10             ; again
	stz.w pt_tmp+12             ; the circle: 0 kor2, 2 kor4, 4 the head
_ob_circle:
	ldx.w pt_tmp+12
	lda.l _ob_cof,x
	sta.b G3_OC
	tax
	lda.w phys_dpa+2,x
	sta.b T0+2
	lda.w phys_dpa+6,x
	sta.b T1+2
	jsr phys_sprite
	cmp #$FFFF
	beq _ob_next
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
	inc.w phys_dpa+S_APPLES
	lda.l phys_objs+2,x
	beq +
	dec a
	sta.w phys_dpa+S_GRAVITY
+	rep #$20
	inc.w pt_tmp+10
	txa
	ldx #0
-	cmp #12
	bcc +
	sbc #12
	inx
	bra -
+	stx.w phys_eaten
	lda.w phys_dpa+EV
	ora #PH_EAT
	sta.w phys_dpa+EV
	bra _ob_next
++	cmp #1
	bne _ob_next
	lda.w phys_dpa+S_APPLES     ; the flower, with all the apples
	and #$00FF
	cmp.w lev_need
	bcc _ob_next
	inc.w pt_tmp+8
_ob_next:
	lda.w pt_tmp+12
	inc a
	inc a
	sta.w pt_tmp+12
	cmp #6
	bcs +
	jmp _ob_circle
+	lda.w pt_tmp+10
	beq +
	jmp _ob_again
+	lda.w pt_tmp+8
	beq +
	lda.w phys_dpa+EV
	ora #PH_FINISH
	sta.w phys_dpa+EV
	bra _ob_ret
+	lda.w pt_tmp+6
	beq _ob_ret
	lda.w phys_dpa+EV
	ora #PH_DEAD
	sta.w phys_dpa+EV
_ob_ret:
	pea PHYS_DPA
	pld
	rts
_ob_cof:
	.dw S_K2+C_RX, S_K4+C_RX, S_HEADX

; New candidates (G3_LP, G3_LN): kept (OC_*) when they are OC_MAX at most,
; else the ones of this step (within 1 m of the box of the circles) in
; G3_OL.
_ob_scan:
	G3_OMM phys_dpa+S_K2+C_RX+2, phys_dpa+S_K4+C_RX+2, phys_dpa+S_HEADX+2, G3_BX, G3_BX1
	G3_OMM phys_dpa+S_K2+C_RY+2, phys_dpa+S_K4+C_RY+2, phys_dpa+S_HEADY+2, G3_BY, G3_BY1
	lda.b G3_BX
	eor #$8000
	sec
	sbc #OC_M
	sta.w OC_X0                 ; the lowest - OC_M
	dec a
	sta.b G3_CX0                ; - 1 more
	lda.b G3_BX1
	sec
	sbc.b G3_BX
	clc
	adc #1+2*OC_M
	sta.w OC_XW                 ; to the highest + OC_M
	inc a
	inc a
	sta.b G3_CXW                ; + 1 more
	lda.b G3_BY
	eor #$8000
	sec
	sbc #OC_M
	sta.w OC_Y0
	dec a
	sta.b G3_CY0
	lda.b G3_BY1
	sec
	sbc.b G3_BY
	clc
	adc #1+2*OC_M
	sta.w OC_YW
	inc a
	inc a
	sta.b G3_CYW
	lda #OC_L
	sta.b G3_LP
	lda #OC_MAX
	sta.b G3_LM
	jsr _ob_list
	bcs +
	sty.w OC_N
	sty.b G3_LN
	rts
+	lda #$FFFF                  ; too many: none kept
	sta.w OC_N
	lda.w OC_X0
	clc
	adc #OC_M-1
	sta.b G3_CX0                ; the lowest - 1
	lda.w OC_XW
	sec
	sbc #2*OC_M-2
	sta.b G3_CXW                ; to the highest + 1
	lda.w OC_Y0
	clc
	adc #OC_M-1
	sta.b G3_CY0
	lda.w OC_YW
	sec
	sbc #2*OC_M-2
	sta.b G3_CYW
	lda #phys_dpb+G3_OL
	sta.b G3_LP
	lda #52
	sta.b G3_LM
	jsr _ob_list
	sty.b G3_LN
	rts

; The active objects with their whole meters within G3_CX0 (G3_CXW of
; them) and G3_CY0 (G3_CYW) into the list at G3_LP, from the last one: Y =
; their number; C set if there are more than G3_LM.
_ob_list:
	ldy #0
	lda.w phys_nobjs
	bne +
	clc
	rts
+	asl a
	adc.w phys_nobjs
	asl a
	asl a
	sec
	sbc #12
	tax                         ; 12 (n-1)
_ob_l1:
	lda.l phys_objs+6,x
	sec
	sbc.b G3_CX0
	cmp.b G3_CXW
	bcs _ob_l2
	lda.l phys_objs+10,x
	sec
	sbc.b G3_CY0
	cmp.b G3_CYW
	bcs _ob_l2
	lda.l phys_objs+2,x
	and #$FF00                  ; active
	beq _ob_l2
	cpy.b G3_LM
	bcs _ob_lfull
	txa
	lsr a
	lsr a
	sep #$20
	sta (G3_LP),y
	rep #$20
	iny
_ob_l2:
	txa
	sec
	sbc #12
	tax
	bcs _ob_l1
	clc
	rts
_ob_lfull:
	sec
	rts

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
	tax
	pea PHYS_DPA                ; PHYS_ENTER
	pld
	sep #$20
	lda.l lev_bank
	pha
	plb
	rep #$20
	stx.b IN
	stz.b EV
	stz.b RACS
	stz.w phys_bump
	stz.w pt_fric
	stz.w pt_fric+2
	; the sums of the torques (G1_CRS, G1_CRD):
	lda #$8082
	sta.b G1_CRS
	lda #$FE7E
	sta.b G1_CRS+2
	lda #$0080
	sta.b G1_CRD
	lda #$FDFE
	sta.b G1_CRD+2
	; w1 = rsh( body.w, 4 ) and the signed bytes of its clamp24 (the bytes
	; of w1+$808080 xor $80); body.w is kept for phys_rider:
	lda.b S_BODY+C_W
	sta.w g2_w
	clc
	adc #8
	sta.b W1
	lda.b S_BODY+C_W+2
	sta.w g2_w+2
	adc #0
	cmp #$8000
	ror a
	ror.b W1
	sta.b W1+2
	; 8 w1 = ((body.w + 8) >> 1) & ~7 and its signed digits (G1_W8D), when
	; they fit:
	clc
	adc #$0080
	cmp #$00FF
	bcs _g1st_w8far
	lda.b W1
	and #$FFF8
	sta.b G1_W8D                ; the low signed digit
	lda.b W1-1
	asl a
	lda.b W1+1
	adc #0
	sta.b G1_W8D+1              ; the middle one
	clc
	adc #$0080
	xba
	and #$00FF
	sta.b G1_W8D+2              ; the high one, G1_W8OK = 0
	bra _g1st_w8
_g1st_w8far:
	lda #$FFFF
	sta.b G1_W8D+2
_g1st_w8:
	lda.b W1+2
	.REPT 3
	cmp #$8000
	ror a
	ror.b W1
	.ENDR
	sta.b W1+2
	lda.b W1
	clc
	adc #$8080
	tax
	lda.b W1+2
	adc #$0080
	bmi _g2st_wlo
	cmp #$0100
	bcc _g2st_win
	ldx #$FFFF
	lda #$00FF
	bra _g2st_win
_g2st_wlo:
	ldx #0
	lda #0
_g2st_win:
	eor #$0080
	sta.b WD+2
	txa
	eor #$8080
	sta.b WD
	; the torques of the wheels (pt_m; phys_torques for the brake):
	lda.b IN
	bit #PH_BRAKE
	beq +
	jsr phys_torques
	bra _g1st_tq
+	sep #$20
	stz.b S_BRAKEWAS
	rep #$20
	stz.w pt_m
	stz.w pt_m+2
	stz.w pt_m+4
	stz.w pt_m+6
	and #PH_GAS
	beq _g1st_tq
	lda.b S_TURNED
	and #$00FF
	beq _g1st_gas4
	; Turned: kor2 gets -600 Nm while its omega > -110 rad/s.
	lda.b S_K2+C_W
	sec
	sbc #(-TULP_W) & $FFFF
	tax
	lda.b S_K2+C_W+2
	sbc #((-TULP_W) >> 16) & $FFFF
	bmi _g1st_tq
	bne +
	cpx #0
	beq _g1st_tq
+	lda #(-GAS_T) & $FFFF
	sta.w pt_m
	lda #$FFFF
	sta.w pt_m+2
	bra _g1st_tq
_g1st_gas4:
	; kor4 gets 600 Nm while its omega < 110 rad/s.
	lda.b S_K4+C_W
	sec
	sbc #TULP_W & $FFFF
	lda.b S_K4+C_W+2
	sbc #TULP_W >> 16
	bpl _g1st_tq
	lda #GAS_T
	sta.w pt_m+4
_g1st_tq:
	jsr phys_anchors
	jsr phys_erok
	jsr _g1_ek4
	; the change of the body's w (pt_crs): MULK( rsh( cross_s, 2 ), K_TS )+
	; MULK( rsh( cross_d, 8 ), K_TD ). G1_CRS & ~3 = x'+$808080 for x' =
	; 4*rsh( cross_s, 2 ), MULK = floor( (x'*M+2^15)/2^16 ):
	lda.b G1_CRS+2
	cmp #$0100
	bcc +
	jmp _g1st_tss
+	lda.b G1_CRS
	and #$FFFC
	sta.b G1_CRS
	lda #((K_TS_M & $FF) << 8) | (K_TS_M >> 8)
	sta.w MPYA
	sta.w MPYA
	G1_MULKS G1_CRS, 0
_g1st_ts2:
	; MULK( y, K_TD ) for y = rsh( cross_d, 8 ) = G1_CRD >> 8 in 16 bits
	; (the multiplicand): floor( (y*32*M+2^15)/2^16 ), 32*K_TD_M =
	; 12*65536-115*256+64 (the products: 64y = 256*W0+.., -115y = 256*V1
	; +l1, 12y = P2; P2+V1+floor( (W0+l1+128)/256 )):
	lda.b G1_CRD+2
	clc
	adc #$0080
	and #$FF00
	beq +
	jmp _g1st_tds
+	lda.b G1_CRD+1
	xba
	sta.w MPYA
	sta.w MPYA
	lda #64
	sta.w MPYB
	lda.w MPYM
	clc
	adc #16512
	sta.b G1_T
	lda #$008D
	sta.w MPYB
	lda.w MPYL
	and #$00FF
	clc
	adc.b G1_T
	xba
	and #$00FF
	adc.w MPYM
	eor #$8000
	tay                         ; V1+floor( .. )+$8040
	lda #12
	sta.w MPYB
	tya
	clc
	adc.w MPYL
	tax
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #$FF80
	tay                         ; Y:X = the MULK+$8040
_g1st_td2:
	txa
	clc
	adc.b G1_CRS
	tax
	tya
	adc.b G1_CRS+2
	tay
	txa
	sec
	sbc #$8040
	sta.w pt_crs
	tya
	sbc #0
	sta.w pt_crs+2
	; phys_volts only when a volt starts or ends:
	lda.b S_VOLTON
	bne +
	lda.b IN
	and #PH_VOLT_R|PH_VOLT_L
	beq ++
	lda.b S_LASTVOLT
	and #$00FF
	cmp #VOLT_GAP
	bcc ++
+	jsr phys_volts
++	; the gravity (phys_gravity), mostly 1:
	lda.b S_GRAVITY
	and #$00FF
	cmp #1
	bne +
	stz.b GVX
	stz.b GVX+2
	lda #-G_V
	sta.b GVY
	lda #$FFFF
	sta.b GVY+2
	bra ++
+	jsr phys_gravity
++
	jsr phys_rider
	; beallit of the body: w -= pt_crs, a = wrap( a+w ):
	lda.b S_BODY+C_W
	sec
	sbc.w pt_crs
	sta.b S_BODY+C_W
	sta.w pt_da
	lda.b S_BODY+C_W+2
	sbc.w pt_crs+2
	sta.b S_BODY+C_W+2
	sta.w pt_da+2
	lda.b S_BODY+C_W
	clc
	adc.b S_BODY+C_A
	sta.b S_BODY+C_A
	lda.b S_BODY+C_W+2
	adc.b S_BODY+C_A+2
	sta.b S_BODY+C_A+2
	eor #$8000
	cmp #((PI_W >> 16) & $FFFF)+$8000
	bcc _g1st_lt
	bne _g1st_ge
	lda.b S_BODY+C_A
	cmp #PI_W & $FFFF
	bcc _g1st_v
_g1st_ge:
	lda.b S_BODY+C_A            ; a >= pi
	sec
	sbc #TWOPI_W & $FFFF
	sta.b S_BODY+C_A
	lda.b S_BODY+C_A+2
	sbc #TWOPI_W >> 16
	sta.b S_BODY+C_A+2
	bra _g1st_v
_g1st_lt:
	cmp #(((-PI_W) >> 16) & $FFFF)-$8000
	bcc _g1st_add
	bne _g1st_v
	lda.b S_BODY+C_A
	cmp #(-PI_W) & $FFFF
	bcs _g1st_v
_g1st_add:
	lda.b S_BODY+C_A            ; a < -pi
	clc
	adc #TWOPI_W & $FFFF
	sta.b S_BODY+C_A
	lda.b S_BODY+C_A+2
	adc #TWOPI_W >> 16
	sta.b S_BODY+C_A+2
_g1st_v:
	; v += -MULK( Dx0+Dx1, K_20 )+gv, r += rsh( v, 8 ):
.IF K_20_SH != 19 || (K_20_M & 1) != 0 || K_TS_SH != 14 || K_TD_SH != 11 || K_TD_M != 23658 || K_OMEGA_SH != 19
.FAIL "phys_step: the shifts of the constants"
.ENDIF
	lda #(((K_20_M/2) & $FF) << 8) | ((K_20_M/2) >> 8)
	sta.w MPYA
	sta.w MPYA
	G1_BODYV pt_dx, S_BODY+C_VX, GVX, S_BODY+C_RX
	G1_BODYV pt_dy, S_BODY+C_VY, GVY, S_BODY+C_RY
	; The wheels, each: defl[k] += rsh( da[k]-da1, 8 ):
	lda.w pt_dx
	clc
	adc.b GVX
	sta.b FX
	lda.w pt_dx+2
	adc.b GVX+2
	sta.b FX+2
	lda.w pt_dy
	clc
	adc.b GVY
	sta.b FY
	lda.w pt_dy+2
	adc.b GVY+2
	sta.b FY+2
	lda.w pt_m
	sta.b MK
	lda.w pt_m+2
	sta.b MK+2
	lda #R_WHEEL_P              ; the circle of contacts: a wheel
	sta.w phys_dpb+QR
	lda #R_WHEEL_SQ & $FFFF
	sta.w phys_dpb+QRSQ
	lda #R_WHEEL_SQ >> 16
	sta.w phys_dpb+QRSQ+2
	lda #G3_KW
	sta.w phys_dpb+G3_K
	stz.w phys_dpb+QHEAD
	lda #S_K2
	sta.w phys_dpb+WK
	lda #S_ROLL
	sta.w phys_dpb+WR
	pea PHYS_DPB
	pld
	jsr phys_wheel
	pea PHYS_DPA
	pld
	lda.b S_K2+C_W
	sec
	sbc.w pt_da
	sta.b T0
	lda.b S_K2+C_W+2
	sbc.w pt_da+2
	sta.b T0+2
	G2_ADDRSH8 S_DEFL, T0, 1
	lda.w pt_dx+4
	clc
	adc.b GVX
	sta.b FX
	lda.w pt_dx+6
	adc.b GVX+2
	sta.b FX+2
	lda.w pt_dy+4
	clc
	adc.b GVY
	sta.b FY
	lda.w pt_dy+6
	adc.b GVY+2
	sta.b FY+2
	lda.w pt_m+4
	sta.b MK
	lda.w pt_m+6
	sta.b MK+2
	lda #S_K4
	sta.w phys_dpb+WK
	lda #S_ROLL+R_SIZE
	sta.w phys_dpb+WR
	pea PHYS_DPB
	pld
	jsr phys_wheel
	pea PHYS_DPA
	pld
	lda.b S_K4+C_W
	sec
	sbc.w pt_da
	sta.b T0
	lda.b S_K4+C_W+2
	sbc.w pt_da+2
	sta.b T0+2
	G2_ADDRSH8 S_DEFL+4, T0, 1
	jsr phys_trig               ; and phys_head
	; The counters of the volts, and phys_volt_age, phys_volt1 (nothing
	; changes when the three counters are 255):
	lda.b S_VOLTT
	and.b S_VOLTT+1             ; (volt_t[1], last_volt)
	cmp #$FFFF
	beq +
	sep #$20
	lda.b S_LASTVOLT
	inc a
	beq ++
	sta.b S_LASTVOLT
++	lda.b S_VOLTT
	inc a
	beq ++
	sta.b S_VOLTT
++	lda.b S_VOLTT+1
	inc a
	beq ++
	sta.b S_VOLTT+1
++	lda.b S_LASTVOLT
	sta.w phys_volt_age
	lda.b S_VOLT1
	sta.w phys_volt1
	rep #$20
+	; The sounds: friction, the driven wheel's omega (not in a quick step).
	lda.b IN
	bit #PH_QUICK
	beq +
	jmp _st_head
+	lda.w pt_fric+2
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
+	lda.b 2,x
	bpl ++
	lda #0
	sec
	sbc.b 0,x
	sta.b T0
	lda #0
	sbc.b 2,x
	sta.b T0+2
	ldx #T0                     ; X: |w|, A = |w| >> 16
	; MULK( x, K_OMEGA ) = floor( (x*M+2^18)/2^19 ) for x = |w| >> 8 below
	; 1465600 (e2 < 23 in the signed bytes e0, e1, e2 of x): with M*e0 =
	; 256*W0+.., M*e1 = 256*V+l, M*e2 = 256*H+h it is (T+256*H+h) >> 3 =
	; 32*H+((T+h) >> 3), T = V+4+((W0+l) >> 8):
++	cmp #5725                   ; x >> 8
	bcc +
	jmp _g2st_om
+	lda.b 1,x
	clc
	adc #$8080
	tay                         ; x+$8080
	lda.b 3,x
	and #$00FF
	adc #0
	sta.b T1                    ; e2
	G2_MAK K_OMEGA_M
	tya
	eor #$8080
	sta.w MPYB                  ; M*e0
	xba
	tay
	lda.w MPYM
	clc
	adc #16384
	sta.b T2
	sty.w MPYB                  ; M*e1
	lda.w MPYL
	and #$00FF
	clc
	adc.b T2
	xba
	and #$00FF                  ; ((W0+l) >> 8)+64
	clc
	adc.w MPYM
	clc
	adc #4-64+8*1536
	sta.b T2                    ; T+8*1536
	lda.b T1
	sta.w MPYB                  ; M*e2
	lda.w MPYL
	and #$00FF
	clc
	adc.b T2
	lsr a
	lsr a
	lsr a
	sta.b T2                    ; ((T+h) >> 3)+1536
	lda.w MPYM
	sec
	sbc #48
	asl a
	asl a
	asl a
	asl a
	asl a
	clc
	adc.b T2
	sta.w phys_wheel_omega
_st_head:
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
	lda #G3_KH
	sta.w phys_dpb+G3_K
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
	; The outputs: phys_apples_left if an apple was eaten, the view (not in
	; a quick step).
	lda.b EV
	bit #PH_EAT
	beq +
	lda.b S_APPLES
	and #$00FF
	sta.b T0
	lda.w lev_need
	sec
	sbc.b T0
	sta.w phys_apples_left
+	lda.b IN
	bit #PH_QUICK
	bne +
	jsr _g2_view
+	ldx.b EV

	pld
	plb
	stx.b tcc__r0
	plp
phys_step_ret:                  ; (for measuring the time of a step)
	rtl

; The omega of a fast wheel: x >= 1465600, 65533 or more.
_g2st_om:
	cmp #5726
	bcc +
	lda #$FFFF
	sta.w phys_wheel_omega
	jmp _st_head
+	lda.b 1,x
	clc
	adc #$8080
	sta.b T1
	lda.b 3,x
	and #$00FF
	adc #$0080
	sta.b T1+2
	lda #K_OMEGA_M
	G2_MA
	G2_MULKS T1, 3
	lda.b T1+2
	beq +
	lda #$FFFF
	bra ++
+	lda.b T1
++	sta.w phys_wheel_omega
	jmp _st_head

; The rare cases of the MULKs of phys_step:

_g1st_tss:
	lda.b G1_CRS
	sec
	sbc #$8082
	sta.b T0
	lda.b G1_CRS+2
	sbc #$0080
	sta.b T0+2
	RSH32 T0, 2
	MULK T0, K_TS
	MOV32 G1_CRS, R
	jmp _g1st_ts2
_g1st_tds:
	MOV32 T1, G1_CRD
	ASR32 T1, 8
	MULK T1, K_TD
	lda.b R
	clc
	adc #$8040
	tax
	lda.b R+2
	adc #0
	tay
	jmp _g1st_td2

.ENDS

; phys_trig: for i from 0 to 805 the sin table value t = round( 2^22*sin(
; i/512 ) ) of phys_qsin (32 bits), e = 2*(the next one-t) and the high
; signed byte of e (its low byte is e's).
.IF round( 4194304*sin( 1/512 ) ) != 8192 || round( 4194304*sin( 400/512 ) ) != 2953493 || round( 4194304*sin( 805/512 ) ) != 4194299
.FAIL "g2_qs: the sin of phys_qsin"
.ENDIF
.SECTION ".g2_qs" SUPERFREE
g2_qs:
.REPT 806 INDEX G2_J
	.dw round( 4194304*sin( G2_J/512 ) ) & $FFFF
	.dw round( 4194304*sin( G2_J/512 ) ) >> 16
	.dw (2*round( 4194304*sin( (G2_J+1)/512 ) )-2*round( 4194304*sin( G2_J/512 ) )) & $FFFF
	.dw ((2*round( 4194304*sin( (G2_J+1)/512 ) )-2*round( 4194304*sin( G2_J/512 ) )+128) >> 8) & $FF
.ENDR
.ENDS

; MULK( d, K_RIDER_S )+32 = floor( (d*K_RIDER_S_M+4096)/8192 )+32 for d from

; -4079 to 4079 (phys_rider):
.SECTION ".g2_mst" SUPERFREE
g2_mst:
.REPT 2*4079+1 INDEX G2_I
	.dw floor( ((G2_I-4079)*K_RIDER_S_M+4096)/8192 )+32
.ENDR
.ENDS
