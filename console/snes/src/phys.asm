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

; Kept from the head of a step for the rider of the next one (low RAM):
.DEFINE g2_ofxb g2_ram+0        ; rsh( mq16( Sn, K44_15 ), 6 )+32768
.DEFINE g2_ofyb g2_ram+2        ; rsh( mq16( Cs, K44_15 ), 6 )+32768

; The rider (phys_rider): page A bytes of the fast case, low RAM.
.DEFINE G2_DX $DA               ; rider_x-body_x (P)
.DEFINE G2_DY $DC               ; rider_y-body_y (P)
.DEFINE G2_FLAG $DE             ; 0: the fast case
.DEFINE G2_DIRX $FC             ; dirx, diry of the spring
.DEFINE G2_DIRY $FE
.DEFINE g2_w g2_ram+4           ; body.w at the start of the step

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

; The double word \1 += A (signed 16-bit); Y is used.
.MACRO G2_ADDS16
	tay
	clc
	adc.b \1
	sta.b \1
	tya
	bmi _g2as_n\@
	lda.b \1+2
	adc #0
	bra _g2as_e\@
_g2as_n\@:
	lda.b \1+2
	adc #$FFFF
_g2as_e\@:
	sta.b \1+2
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

; Y:X = R+$808080 for \2 = 0, -R+$808080 for \2 = 1, with R = rsh( mq24(
; wb, \1 ), 7 ) (|\1| <= 16384, WD the signed bytes of wb, MD0 = 2*w2 and
; MD1 = -2*w2 in [-126, 126]): 2*P2+2*V1+((W0+l1+64) >> 7) of the products
; \1*w0 = 256*W0+.., \1*w1 = 256*V1+l1, \1*w2 = P2; T0 is used.
.MACRO G2_WBMUL
	lda.b \1
	G2_MA
	lda.b WD
	sta.w MPYB                  ; *w0
	lda.w MPYM
	clc
	adc #64+8192
	sta.b T0
	lda.b WD+1
	sta.w MPYB                  ; *w1
	lda.w MPYL
	and #$00FF
	clc
	adc.b T0
	asl a
	xba
	and #$00FF                  ; ((W0+l1+64) >> 7)+64
	clc
	adc.w MPYM
	clc
	adc.w MPYM                  ; 2*V1+..+64
	.IF \2 == 0
	clc
	adc #$8080-64
	tax
	lda.b MD0
	.ELSE
	eor #$FFFF
	sec
	adc #$8080+64
	tax
	lda.b MD0+1
	.ENDIF
	and #$00FF
	beq _g2wb_z\@
	sta.w MPYB                  ; *(+-2*w2)
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
	bra _g2wb_e\@
_g2wb_z\@:
	ldy #$0080
_g2wb_e\@:
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

; \4 += MULK( \1, K_RIDER_S )-\2+\3, \5 += rsh( \4, 8 ): |\1| < 4080 from
; the table g2_mst (else K_RIDER_S_M is the multiplicand of MULK).
.MACRO G2_RIDV
	lda.b \1
	clc
	adc #4079
	cmp #2*4079+1
	bcc _g2rv_f\@
	jmp _g2rv_s\@
_g2rv_f\@:
	asl a
	tax
	lda.l g2_mst,x
	clc
	adc.b \3                    ; MULK+gv (16 bits)
	ldx.b \2+2
	cpx #$8000
	bne _g2rv_32\@
	sec
	sbc.b \2                    ; -MULK of two bytes
	G2_ADDS16 \4
	jmp _g2rv_p\@
_g2rv_32\@:
	tax
	lda.b \4
	sec
	sbc.b \2
	sta.b \4
	lda.b \4+2
	sbc.b \2+2
	sta.b \4+2
	txa
	G2_ADDS16 \4
	jmp _g2rv_p\@
_g2rv_s\@:
	lda.b \2+2
	cmp #$8000
	bne _g2rv_s32\@
	lda.b \2
	cmp #$8000
	lda #0
	bcc _g2rv_sp\@
	dec a
_g2rv_sp\@:
	sta.b \2+2
_g2rv_s32\@:
	lda.b \1
	jsr phys_ext32
	MULK T0, K_RIDER_S
	lda.b \4
	sec
	sbc.b \2
	tax
	lda.b \4+2
	sbc.b \2+2
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
	adc.b \3
	sta.b \4
	tya
	adc.b \3+2
	sta.b \4+2
_g2rv_p\@:
	G2_ADDRSH8 \5, \4, 1
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

; \2 = the angle of the circle \1 as 65536 a turn (as phys_angle16).
.IF K_WVIEW_M != 20861 || K_WVIEW_SH != 14
.FAIL "G2_ANG16: 4*K_WVIEW_M = 65536+70*256-12"
.ENDIF
.MACRO G2_ANG16
	lda.b \1+C_A
	asl a
	lda.b \1+C_A+2
	rol a
	tay
	G2_MA
	lda #$00F4
	sta.w MPYB
	lda.w MPYM
	clc
	adc #2176
	sta.b T0
	lda #70
	sta.w MPYB
	lda.w MPYL
	and #$00FF
	clc
	adc.b T0
	xba
	and #$00FF
	clc
	adc.w MPYM
	sty.b T0
	clc
	adc.b T0
	sec
	sbc #8
	sta.w \2
.ENDM

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

; \2 = qsin( \1 ) for the double word \1 in [0, pi/2] (W) (a double
; word of the direct page): the table value plus floor( (f*d+16384)/32768 ) = h+((W0+l+128
; +16384) >> 8)-64, with f the multiplicand and e = 2d in signed bytes
; (f*e0 = 256*W0+.., f*e1 = 256*h+l). T2, X and Y are used.
.MACRO G2_QSIN
	lda.b \1+2
	lsr a
	lsr a
	lsr a                       ; i = b >> 19
	sta.b T2
	asl a
	tax
	adc.b T2
	tay                         ; 3i
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
	lda.l phys_qsind,x
	asl a                       ; e = 2d
	sta.w MPYB                  ; f*e0
	tax
	lda.w MPYM
	clc
	adc #16512
	sta.b T2+2
	txa
	clc
	adc #$0080
	xba
	sta.w MPYB                  ; f*e1
	lda.w MPYL
	and #$00FF
	clc
	adc.b T2+2
	xba
	and #$00FF
	clc
	adc.w MPYM
	tyx
	sec
	sbc #64
	bmi _g2qs_neg\@
	clc
	adc.l phys_qsin,x
	sta.b \2
	lda.l phys_qsin+2,x
	and #$00FF
	adc #0
	bra _g2qs_end\@
_g2qs_neg\@:
	clc
	adc.l phys_qsin,x
	sta.b \2
	lda.l phys_qsin+2,x
	and #$00FF
	adc #$FFFF
_g2qs_end\@:
	sta.b \2+2
.ENDM

; A = q15( \1 ) for \1 in [0, 2^22]: \1 >> 7, at most 32767.
.MACRO G2_Q15P
	lda.b \1
	xba
	asl a
	lda.b \1+1
	rol a
	bpl _g2qp\@
	lda #32767
_g2qp\@:
.ENDM

; A = q15( \1 ) for \1 in [-2^22, 0] (a double word of the direct page).
.MACRO G2_Q15N
	lda.b \1
	xba
	asl a
	lda.b \1+1
	rol a
	cmp #$8000
	bne _g2qn\@
	inc a
_g2qn\@:
.ENDM

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
++	; b = |a|: b > pi/2: sin( pi-b ), -sin( b-pi/2 ), else sin( b ),
	; sin( pi/2-b ); T1 = the argument of the sin, T0 of the cos:
	lda #HALFPI_W & $FFFF
	cmp.b T0
	lda #HALFPI_W >> 16
	sbc.b T0+2
	bcs _g2tr_le
	lda #PI_W & $FFFF
	sec
	sbc.b T0
	sta.b T1
	lda #PI_W >> 16
	sbc.b T0+2
	sta.b T1+2
	lda.b T0
	sec
	sbc #HALFPI_W & $FFFF
	sta.b T0
	lda.b T0+2
	sbc #HALFPI_W >> 16
	sta.b T0+2
	lda #$8000
	bra _g2tr_s
_g2tr_le:
	lda.b T0
	sta.b T1
	lda.b T0+2
	sta.b T1+2
	lda #HALFPI_W & $FFFF
	sec
	sbc.b T0
	sta.b T0
	lda #HALFPI_W >> 16
	sbc.b T0+2
	sta.b T0+2
	lda #0
_g2tr_s:
	sta.b T3                    ; bit 15: the cos is negative
	G2_QSIN T1, SN22
	lda.b S_BODY+C_A+2
	bmi _g2tr_sneg
	G2_Q15P SN22
	sta.b SN
	bra _g2tr_c
_g2tr_sneg:
	lda #0
	sec
	sbc.b SN22
	sta.b SN22
	lda #0
	sbc.b SN22+2
	sta.b SN22+2
	G2_Q15N SN22
	sta.b SN
_g2tr_c:
	G2_QSIN T0, CS22
	lda.b T3
	bmi _g2tr_cneg
	G2_Q15P CS22
	sta.b CS
	rts
_g2tr_cneg:
	lda #0
	sec
	sbc.b CS22
	sta.b CS22
	lda #0
	sbc.b CS22+2
	sta.b CS22+2
	G2_Q15N CS22
	sta.b CS
	rts

; \3 = \2 + rsh( 256*HV+E, 6 ) for E = \1, HV = \1+2 (words of the direct
; page, E+32+32768 in [0, 65535], |HV| < 16000): with U = E+32+32768,
; G = HV+(U >> 8)-128 and r = (U >> 6) & 3 it is 4G+r, whose sign is G's.
.MACRO G2_HEADADD
	lda.b \1
	clc
	adc #32+32768
	tay
	and #$00C0
	asl a
	asl a
	xba
	sta.b \1                    ; r
	tya
	xba
	and #$00FF
	clc
	adc.b \1+2
	sec
	sbc #128                    ; G
	bmi _g2ha_neg\@
	asl a
	asl a
	ora.b \1
	clc
	adc.b \2
	sta.b \3
	lda.b \2+2
	adc #0
	sta.b \3+2
	bra _g2ha_end\@
_g2ha_neg\@:
	asl a
	asl a
	ora.b \1
	clc
	adc.b \2
	sta.b \3
	lda.b \2+2
	adc #$FFFF
	sta.b \3+2
_g2ha_end\@:
.ENDM

; The offsets of the rider's rest over the body, for phys_rider (g2_ofxb,
; g2_ofyb): rsh( mq16( Sn, K44_15 ), 6 ) and rsh( mq16( Cs, K44_15 ), 6 ),
; plus 32768. The multiplicand is X = \2 (Cs or Sn): it is floor( (4*K44_15
; *X+2^15)/2^16 ) with 4*K44_15 = 65536-31*256+72: X+V1+((W0+l1+128+16384)
; >> 8)-64 (X*72 = 256*W0+.., -31*X = 256*V1+l1).
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
	adc #32768-64
	sta.w \1
.ENDM

; szamitfejr: the head from the rider and the angle (CS, SN): head = rider
; + rsh( mq16( Cs, hx )+mq16( Sn, -K63_15 ), 6 ), ..., each product as
; W0+256*V+l (the signed bytes of the constants); also g2_ofxb, g2_ofyb.
.IF K09_15 != $0B85 || K63_15 != $50A4 || K44_15 != $3852
.FAIL "phys_head: the signed bytes of the constants"
.ENDIF
phys_head:
	.ACCU 16
	.INDEX 16
	ldx #$F47B                  ; -K09_15: 123, -12
	lda.b S_TURNED
	and #$00FF
	beq +
	ldx #$0C85                  ; K09_15: -123, 12
+	stx.b T3
	lda.b CS
	G2_MA
	lda.b T3
	sta.w MPYB                  ; Cs*hx0
	lda.w MPYM
	sta.b T0                    ; Ex
	lda.b T3+1
	sta.w MPYB                  ; Cs*hx1
	lda.w MPYL
	and #$00FF
	clc
	adc.b T0
	sta.b T0
	lda.w MPYM
	sta.b T0+2                  ; HVx
	lda #$00A4
	sta.w MPYB                  ; Cs*(-92)
	lda.w MPYM
	sta.b T1                    ; Ey
	lda #81
	sta.w MPYB                  ; Cs*81
	lda.w MPYL
	and #$00FF
	clc
	adc.b T1
	sta.b T1
	lda.w MPYM
	sta.b T1+2                  ; HVy
	G2_OFF44 g2_ofyb, CS
	lda.b SN
	G2_MA
	lda #92
	sta.w MPYB                  ; Sn*92
	lda.w MPYM
	clc
	adc.b T0
	sta.b T0
	lda #$00AF
	sta.w MPYB                  ; Sn*(-81)
	lda.w MPYL
	and #$00FF
	clc
	adc.b T0
	sta.b T0
	lda.w MPYM
	clc
	adc.b T0+2
	sta.b T0+2
	lda.b T3
	sta.w MPYB                  ; Sn*hx0
	lda.w MPYM
	clc
	adc.b T1
	sta.b T1
	lda.b T3+1
	sta.w MPYB                  ; Sn*hx1
	lda.w MPYL
	and #$00FF
	clc
	adc.b T1
	sta.b T1
	lda.w MPYM
	clc
	adc.b T1+2
	sta.b T1+2
	G2_OFF44 g2_ofxb, SN
	G2_HEADADD T0, S_RIDX, S_HEADX
	G2_HEADADD T1, S_RIDY, S_HEADY
	rts

; The view of the bike (phys_view) from the state; the angles as 65536 a
; turn: rsh( mq24( a >> 15, K_WVIEW ), K_WVIEW_SH-8 ).
phys_angle16:                   ; A = the angle of the circle at X
	.ACCU 16
	.INDEX 16
	; v = a >> 15; 4*K_WVIEW_M = 65536+70*256-12, so the angle is
	; v + V1 + ((W0 + l1 + 128 + 2048) >> 8) - 8 with W0 = mq16( v, -12 ),
	; v*70 = 256*V1 + l1:
	lda.b C_A,x
	asl a
	lda.b C_A+2,x
	rol a
	tay
	G2_MA
	lda #$00F4
	sta.w MPYB
	lda.w MPYM
	clc
	adc #2176
	sta.b T0
	lda #70
	sta.w MPYB
	lda.w MPYL
	and #$00FF
	clc
	adc.b T0
	xba
	and #$00FF
	clc
	adc.w MPYM
	sty.b T0
	clc
	adc.b T0
	sec
	sbc #8
	rts

phys_mkview:
	.ACCU 16
	.INDEX 16
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
	G2_ANG16 S_BODY, phys_view+8
	G2_ANG16 S_K2, phys_view+28
	G2_ANG16 S_K4, phys_view+30
	lda.b S_TURNED              ; turned, gravity
	sta.w phys_view+48
; The other outputs (also after a quick step):
phys_mkout:
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

;---------------------------------------------------------------------------
; G1, the springs (phys_torques ... phys_gravity): helpers. A 16-bit.

.DEFINE G1_W8D $D4              ; signed digits of 8 * clamp24( w1 )
.DEFINE G1_W8OK $D7             ; bit 7 clear when G1_W8D holds them
.DEFINE G1_T $D8                ; a word of scratch

; Per step, from phys_anchors (low RAM; pt_gsx, pt_gsy hold gs + body.r):
.DEFINE G1_BVX g1_ram+0         ; body.vx - $808040, body.vy - $808040
.DEFINE G1_BVY g1_ram+4
.DEFINE G1_BRX g1_ram+8         ; body.rx - 4, body.ry - 4
.DEFINE G1_BRY g1_ram+12
.DEFINE G1_GS g1_ram+16         ; wheel j at +8j: rsh( gsx, 2 ), its high
                                ; signed digit (+2), -rsh( gsy, 2 ) (+4) and
                                ; its high signed digit (+6)
.DEFINE G1_S8 pt_oldw           ; Sn >> 8, (-Cs) >> 8 (until phys_volts)
.DEFINE G1_C8 pt_oldw+2

; In phys_erok: -ky and its high signed digit, that of kx, the damper:
.DEFINE G1_NKY T1
.DEFINE G1_NKY1 T1+2
.DEFINE G1_KX1 T2
.DEFINE G1_SPR T2+2             ; 0: no spring
.DEFINE G1_DMP R2               ; damper + 29 (16-bit), or - $808020 (32-bit)

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

; \3 = clamp16( rsh( \1 - \2, 3 ) ), \1 in the direct page, \2 = the body
; - 4 (absolute).
.MACRO G1_KOTO
	lda.b \1
	sec
	sbc.w \2
	sta.b \3
	lda.b \1+2
	sbc.w \2+2
	tax
	clc
	adc #3
	cmp #6
	bcs _gk_far\@
	txa
	lsr a
	ror.b \3
	lsr a
	ror.b \3
	lsr a
	ror.b \3
	bra _gk_d\@
_gk_far\@:
	stx.b T0+2
	lda.b \3
	sta.b T0
	ASR32 T0, 3
	CLAMP16 T0
	sta.b \3
_gk_d\@:
.ENDM

; \3 = rsh( mq24( w1, M ), 5 ) + \2 - \1 for the multiplicand M, with the
; digits of 8 w1 (\1: wheel velocity, \2: body velocity - $808040).
.MACRO G1_WTERM
	lda.b G1_W8D
	sta.w MPYB
	lda.w MPYM
	clc
	adc #16512
	sta.b G1_T
	lda.b G1_W8D+1
	sta.w MPYB
	lda.w MPYL
	and #$00FF
	clc
	adc.b G1_T
	xba
	and #$00FF
	adc.w MPYM
	eor #$8000
	sta.b G1_T
	lda.b G1_W8D+2
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
	tax
	tya
	clc
	adc.w \2
	tay
	txa
	adc.w \2+2
	tax
	tya
	sec
	sbc.b \1
	sta.b \3
	txa
	sbc.b \1+2
	sta.b \3+2
.ENDM

; A = MULK( x, K_DAMP ) + 29 for the 16-bit multiplicand x.
.MACRO G1_DAMP
	lda #$FFE3
	sta.w MPYB
	lda.w MPYM
	clc
	adc #3776
	sta.b G1_T
	lda #$0046
	sta.w MPYB
	lda.w MPYL
	and #$00FF
	clc
	adc.b G1_T
	asl a
	xba
	and #$00FF
	adc.w MPYM
	clc
	adc.w MPYM
.ENDM

; A:X = mq16( M, v ) for the multiplicand M and the signed digits of v,
; the low bytes of \1 and \2 (direct page; G1_MQW: absolute).
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

.MACRO G1_MQW
	lda.w \1
	sta.w MPYB
	ldy.w MPYM
	lda.w \2
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
	bcc _gmqw_p\@
	dec a
_gmqw_p\@:
.ENDM

; The double word \1 (absolute) += A:X.
.MACRO G1_ACC
	tay
	txa
	clc
	adc.w \1
	sta.w \1
	tya
	adc.w \1+2
	sta.w \1+2
.ENDM

; The spring of a wheel and its sum with the damper (G1_DMP): \1 = MULK(
; G, K_SPRING ) + the damper for the 16-bit multiplicand G (\2: 0 when the
; damper is 16-bit).
.MACRO G1_SPRING
	lda #$FFC0
	sta.w MPYB
	lda.w MPYM
	clc
	adc #8320
	sta.b G1_T
	lda #$FFA2
	sta.w MPYB
	lda.w MPYL
	and #$00FF
	clc
	adc.b G1_T
	xba
	and #$00FF
	adc.w MPYM
	.IF \2 == 0
	clc
	adc.b G1_DMP
	.ENDIF
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
	tax
	.IF \2 == 0
	tya
	sec
	sbc #$803D
	sta.w \1+0
	txa
	sbc #$0080
	sta.w \1+2
	.ELSE
	tya
	clc
	adc.b G1_DMP
	sta.w \1+0
	txa
	adc.b G1_DMP+2
	sta.w \1+2
	.ENDIF
.ENDM

; One direction of erokszamitasa: \6 = the damper of \1 (korongrelv) + the
; spring of \4 (gumi); cross_d += mq24( \1, k ) (\2, \3: the signed digits
; of k, \2 the word of it), cross_s += mq24( \4, gs ) (\5: gs and its
; digits); \7 = 1: k = -ky.
.MACRO G1_PART
	G1_FITS \1
	beq _gp_rf\@
_gp_rsj\@:
	jmp _gp_rs\@
_gp_rf\@:
	.IF \7 == 1
	lda.b KY
	cmp #-32640
	beq _gp_rsj\@
	.ENDIF
	G1_LDMD \1
	G1_DAMP
	sta.b G1_DMP
	G1_MQB \2, \3
	G1_ACC pt_crd
	lda.b G1_SPR
	beq _gp_d32j\@
	G1_FITS \4
	beq _gp_gf\@
_gp_d32j\@:
	jmp _gp_d32\@
_gp_gf\@:
	G1_LDMD \4
	G1_SPRING \6, 0
	jmp _gp_crs\@
_gp_d32\@:
	lda.b G1_DMP
	sec
	sbc #29
	ldx #0
	cmp #$8000
	bcc _gp_dp\@
	dex
_gp_dp\@:
	sec
	sbc #$8020
	sta.b G1_DMP
	txa
	sbc #$0080
	sta.b G1_DMP+2
	jmp _gp_s32\@
_gp_rs\@:
	; the damper: (mq24( rel, K_DAMP ) + 64) >> 7 = bytes 1..3 of twice it,
	; from R = mq24 + $808000; then mq24( rel, k ) with the same digits:
	MOV32 T3, \1
	DIGT3
	MB_IMM K_DAMP_M
	RSET24 MD0
	rep #$21
	lda.b R
	adc #64
	sta.b R
	lda.b R+2
	adc #0
	asl.b R
	rol a
	sta.b R+2
	xba
	and #$00FF
	cmp #$0080
	bcc _gp_rp\@
	ora #$FF00
_gp_rp\@:
	tax
	lda.b R+1
	sec
	sbc #$8120
	sta.b G1_DMP
	txa
	sbc #$0081
	sta.b G1_DMP+2
	sep #$20
	MB_DP \2
	RSET24 MD0
	rep #$20
	RFIN0 $808000
	lda.b R
	clc
	adc.w pt_crd
	sta.w pt_crd
	lda.b R+2
	adc.w pt_crd+2
	sta.w pt_crd+2
_gp_s32\@:
	lda.b G1_SPR
	bne _gp_sp\@
	lda.b G1_DMP
	clc
	adc #$8020
	sta.w \6+0
	lda.b G1_DMP+2
	adc #$0080
	sta.w \6+2
	jmp _gp_end\@
_gp_sp\@:
	G1_FITS \4
	beq _gp_gf2\@
	jmp _gp_gs\@
_gp_gf2\@:
	G1_LDMD \4
	G1_SPRING \6, 1
	jmp _gp_crs\@
_gp_gs\@:
	MULK \4, K_SPRING
	lda.b R
	clc
	adc.b G1_DMP
	tax
	lda.b R+2
	adc.b G1_DMP+2
	tay
	txa
	clc
	adc #$8020
	sta.w \6+0
	tya
	adc #$0080
	sta.w \6+2
	MOV32 T3, \4
	DIGT3
	MB_ABS \5+0
	RSET24 MD0
	rep #$20
	RFIN0 $808000
	lda.b R
	clc
	adc.w pt_crs
	sta.w pt_crs
	lda.b R+2
	adc.w pt_crs+2
	sta.w pt_crs+2
	jmp _gp_end\@
_gp_crs\@:
	G1_MQW \5, \5+2
	G1_ACC pt_crs
_gp_end\@:
.ENDM

; korongrelv without the digits of 8 w1: \2 = rsh( mq24( w1, \3 ), 5 ) +
; body.v - \1 (the multiplicand \3), w1's signed bytes in MD0..MD2.
.MACRO G1_WSLOW
	sep #$20
	MB_DP \3
	RSET24 MD0
	rep #$20
	RFIN 5, $808000
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

; erokszamitasa of the wheel \1 (S_K2, S_K4), number \2.
.MACRO G1_EROK
	; gumi = gs + body - wheel:
	lda.w pt_gsx+4*\2
	sec
	sbc.b \1+C_RX
	sta.b GX
	lda.w pt_gsx+4*\2+2
	sbc.b \1+C_RX+2
	sta.b GX+2
	lda.w pt_gsy+4*\2
	sec
	sbc.b \1+C_RY
	sta.b GY
	lda.w pt_gsy+4*\2+2
	sbc.b \1+C_RY+2
	sta.b GY+2
	; the spring, unless gumi is within 0.0001 m:
	ldx #1
	lda.b GX
	clc
	adc #SPRING_ZERO_P
	tay
	lda.b GX+2
	adc #0
	bne _ge_spr\@
	cpy #2*SPRING_ZERO_P+1
	bcs _ge_spr\@
	lda.b GY
	clc
	adc #SPRING_ZERO_P
	tay
	lda.b GY+2
	adc #0
	bne _ge_spr\@
	cpy #2*SPRING_ZERO_P+1
	bcs _ge_spr\@
	dex
_ge_spr\@:
	stx.b G1_SPR
	; koto = clamp16( rsh( wheel - body, 3 ) ), -ky, the high digits:
	G1_KOTO \1+C_RX, G1_BRX, KX
	G1_KOTO \1+C_RY, G1_BRY, KY
	lda #0
	sec
	sbc.b KY
	sta.b G1_NKY
	clc
	adc #$0080
	xba
	sta.b G1_NKY1
	lda.b KX
	clc
	adc #$0080
	xba
	sta.b G1_KX1
	; korongrelv = rot90( koto ) * w1 + body.v - wheel.v:
	bit.b G1_W8D+2
	bpl _ge_wf\@
	jmp _ge_ws\@
_ge_wf\@:
	lda.b G1_NKY
	G1_LDMA
	G1_WTERM \1+C_VX, G1_BVX, RLX
	lda.b KX
	G1_LDMA
	G1_WTERM \1+C_VY, G1_BVY, RLY
	jmp _ge_w\@
_ge_ws\@:
	MOV32 T3, S_BODY+C_W
	RSH32 T3, 4
	DIGT3
	rep #$20
	G1_WSLOW \1+C_VX, RLX, G1_NKY, C_VX
	G1_WSLOW \1+C_VY, RLY, KX, C_VY
_ge_w\@:
	G1_PART RLX, G1_NKY, G1_NKY1, GX, G1_GS+8*\2+4, pt_dx+4*\2, 1
	G1_PART RLY, KX, G1_KX1, GY, G1_GS+8*\2, pt_dy+4*\2, 0
	; Ftestnyom, with a torque on the wheel; the friction:
	lda.w pt_m+4*\2
	ora.w pt_m+4*\2+2
	beq _ge_nf\@
	jsr phys_ftn
_ge_nf\@:
	lda.b IN
	bit #PH_QUICK
	bne _ge_q\@
	jmp phys_fric
_ge_q\@:
	rts
.ENDM

; \3 = rsh( mq24( C, K60_15 ), 13 ), \4 = rsh( mq24( C, K85_15 ), 13 ) for
; C = \2 (its signed digits in MD0..MD2, the multiplicand K60_15): with
; Y = (C K60_15 + 2^20) >> 13 = 8 (Q1 + P2) + ((Q0 + p1a + 4096) >> 5),
; \3 = Y >> 8 and \4 = (Y + C) >> 8 as K85_15 = K60_15 + 2^13; \1 holds
; Y + $4040200.
.IF K85_15 - K60_15 != 8192
.FAIL
.ENDIF
.MACRO G1_ANC2
	lda.b MD0
	sta.w MPYB
	lda.w MPYM
	clc
	adc #20480
	sta.b G1_T
	lda.b MD1
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
	tay
	lda.b MD2
	sta.w MPYB
	tya
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
	sec
	sbc #$0402
	sta.b \3
	lda.b \1+3
	and #$00FF
	sbc #$0004
	sta.b \3+2
	lda.b \1
	clc
	adc.b \2
	sta.b \1
	lda.b \1+2
	adc.b \2+2
	sta.b \1+2
	lda.b \1+1
	sec
	sbc #$0402
	sta.b \4
	lda.b \1+3
	and #$00FF
	sbc #$0004
	sta.b \4+2
.ENDM

; From gs (X: high, Y: low word): \1 = gs + body.r\3 (absolute), \2 =
; rsh( gs, 2 ) (\4 = 1: its negative) and its high signed digit (\2+2).
.MACRO G1_GSV
	tya
	clc
	adc.b S_BODY+\3
	sta.w \1
	txa
	adc.b S_BODY+\3+2
	sta.w \1+2
	tya
	clc
	adc #2
	sta.b G1_T
	txa
	adc #0
	lsr a
	ror.b G1_T
	lsr a
	ror.b G1_T
	.IF \4 == 0
	lda.b G1_T
	.ELSE
	lda #0
	sec
	sbc.b G1_T
	.ENDIF
	sta.w \2
	clc
	adc #$0080
	xba
	sta.w \2+2
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

; A = clamp16( rsh( \1, 8 ) ) of a double word of the direct page.
.MACRO G1_RV16
	lda.b \1+2
	clc
	adc #$0080
	cmp #$00FF
	bcs _gr_s\@
	lda.b \1-1
	asl a
	lda.b \1+1
	adc #0
	bpl _gr_d\@
	cmp #$8080
	bcs _gr_d\@
	lda #$8080
	bra _gr_d\@
_gr_s\@:
	MOV32 T0, \1
	RSH32 T0, 8
	CLAMP16 T0
_gr_d\@:
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

phys_torques:
	.ACCU 16
	.INDEX 16
	lda.b IN
	and #PH_BRAKE
	beq +
	jmp _tq_brake
+	sep #$20
	stz.b S_BRAKEWAS
	rep #$20
	stz.w pt_m
	stz.w pt_m+2
	stz.w pt_m+4
	stz.w pt_m+6
	lda.b IN
	and #PH_GAS
	beq _tq_ret
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
	bmi _tq_ret
	bne +
	cpx #0
	beq _tq_ret
+	lda #(-GAS_T) & $FFFF
	sta.w pt_m
	lda #$FFFF
	sta.w pt_m+2
	rts
_tq_gas4:
	; kor4 gets 600 Nm while its omega < 110 rad/s.
	lda.b S_K4+C_W
	sec
	sbc #TULP_W & $FFFF
	lda.b S_K4+C_W+2
	sbc #TULP_W >> 16
	bpl _tq_ret
	lda #GAS_T
	sta.w pt_m+4
_tq_ret:
	rts
_tq_brake:
	; the brake (it overrides the gas):
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
; ( -cc-d, cc-d ) with a = 0.85 cos, b = 0.6 sin, cc = 0.85 sin, d = 0.6 cos;
; and what phys_erok needs of the body for both wheels (G1_*).
phys_anchors:
	.ACCU 16
	.INDEX 16
	sep #$20
	DIG24 CS22
	MB_IMM K60_15
	rep #$20
	G1_ANC2 T3, CS22, T1, T0    ; d, a
	sep #$20
	DIG24 SN22
	rep #$20
	G1_ANC2 T3, SN22, T2, R     ; b, cc
	; gsx = ( b-a, a+b ), gsy = ( -cc-d, cc-d ):
	lda.b T2
	sec
	sbc.b T0
	tay
	lda.b T2+2
	sbc.b T0+2
	tax
	G1_GSV pt_gsx, G1_GS, C_RX, 0
	lda.b T2
	clc
	adc.b T0
	tay
	lda.b T2+2
	adc.b T0+2
	tax
	G1_GSV pt_gsx+4, G1_GS+8, C_RX, 0
	lda.b R
	clc
	adc.b T1
	sta.b T3
	lda.b R+2
	adc.b T1+2
	sta.b T3+2
	lda #0
	sec
	sbc.b T3
	tay
	lda #0
	sbc.b T3+2
	tax
	G1_GSV pt_gsy, G1_GS+4, C_RY, 1
	lda.b R
	sec
	sbc.b T1
	tay
	lda.b R+2
	sbc.b T1+2
	tax
	G1_GSV pt_gsy+4, G1_GS+12, C_RY, 1
	; the body for korongrelv and koto:
	lda.b S_BODY+C_VX
	sec
	sbc #$8040
	sta.w G1_BVX
	lda.b S_BODY+C_VX+2
	sbc #$0080
	sta.w G1_BVX+2
	lda.b S_BODY+C_VY
	sec
	sbc #$8040
	sta.w G1_BVY
	lda.b S_BODY+C_VY+2
	sbc #$0080
	sta.w G1_BVY+2
	lda.b S_BODY+C_RX
	sec
	sbc #4
	sta.w G1_BRX
	lda.b S_BODY+C_RX+2
	sbc #0
	sta.w G1_BRX+2
	lda.b S_BODY+C_RY
	sec
	sbc #4
	sta.w G1_BRY
	lda.b S_BODY+C_RY+2
	sbc #0
	sta.w G1_BRY+2
	; the direction of the body in bytes (surlodasverseny):
	lda.b SN+1
	and #$00FF
	eor #$0080
	sec
	sbc #$0080
	sta.w G1_S8
	lda #0
	sec
	sbc.b CS
	xba
	and #$00FF
	eor #$0080
	sec
	sbc #$0080
	sta.w G1_C8
	; 8 w1 = ((body.w + 8) >> 1) & ~7 and its signed digits, when they fit:
	lda.b S_BODY+C_W
	clc
	adc #8
	sta.b T3
	lda.b S_BODY+C_W+2
	adc #0
	cmp #$8000
	ror a
	ror.b T3
	sta.b T3+2
	clc
	adc #$0080
	cmp #$00FF
	bcs _ga_w8far
	lda.b T3
	and #$FFF8
	sta.b G1_W8D                ; the low signed digit
	lda.b T3-1
	asl a
	lda.b T3+1
	adc #0
	sta.b G1_W8D+1              ; the middle one
	clc
	adc #$0080
	xba
	and #$00FF
	sta.b G1_W8D+2              ; the high one, G1_W8OK = 0
	rts
_ga_w8far:
	lda #$FFFF
	sta.b G1_W8D+2
	rts

; erokszamitasa of the wheel CK (CK4 = 4k): pt_dx, pt_dy[k] and the sums of
; the torques on the body, the friction.
phys_erok:
	.ACCU 16
	.INDEX 16
	lda.b CK
	cmp #S_K2
	beq _g1_ek2
	jmp _g1_ek4
_g1_ek2:
	G1_EROK S_K2, 0
_g1_ek4:
	G1_EROK S_K4, 1

; Ftestnyom: the torque M[k] of the wheel pushes its axle (A 16-bit).
phys_ftn:
	.ACCU 16
	.INDEX 16
	lda.b KY
	clc
	adc #$0080
	xba
	sta.b G1_T                  ; the high signed digit of ky
	; k2 = kx kx + ky ky (the products of the signed digits, $80 of bias
	; in the high word for each lowest one), at least 65536:
	G1_LDMD KX
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
	G1_LDMD KY
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
	G1_LDMA
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
	G1_LDMA
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
	G1_LDMA
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
	G1_G16 GX
	G1_LDMA
	lda.w G1_S8
	sta.w MPYB
	ldy.w MPYM
	G1_G16 GY
	G1_LDMA
	lda.w G1_C8
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
	G1_RV16 RLX
	G1_LDMA
	lda.w G1_S8
	sta.w MPYB
	ldy.w MPYM
	G1_RV16 RLY
	G1_LDMA
	lda.w G1_C8
	sta.w MPYB
	tya
	clc
	adc.w MPYM
	bmi _fr_ret
	bne _fr_e
_fr_ret:
	rts
_fr_e:
	; e = MULK( mq16( clamp16( fg ), clamp16( sb ) ), K_FRIC ):
	cmp #32640
	bcc +
	lda #32639
+	sta.b T3+2                  ; sb
	lda.b T3
	cmp #32640
	bcc +
	lda #32639
	sta.b T3
+	sep #$20
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

; beallitvezeto: the rider (vezeto_hatarolas keeps him over the seat). The
; usual case is fast: rider-body within 16 bits (P), the seat, the clamps
; and the ellipse not moving him, the angular velocity of the body the one
; of the start of the step; the rest is done the slow way.
phys_rider:
	.ACCU 16
	.INDEX 16
	; d = rider-body; fast if in [-32768, 32767]: dx = rsh( d, 1 ) in
	; [-16384, 16384], its high signed byte in [-64, 64] (no clamp):
	lda.b S_RIDX
	sec
	sbc.b S_BODY+C_RX
	tax
	lda.b S_RIDX+2
	sbc.b S_BODY+C_RX+2
	beq +
	inc a
	bne _g2rd_sl1
	txa
	bpl _g2rd_sl1
	bra ++
+	txa
	bmi _g2rd_sl1
++	sta.b G2_DX
	cmp #$8000
	ror a
	adc #0
	sta.b T2                    ; dx (2^-15 m)
	clc
	adc #$0080
	xba
	sta.b MD0                   ; its high signed byte
	lda.b S_RIDY
	sec
	sbc.b S_BODY+C_RY
	tax
	lda.b S_RIDY+2
	sbc.b S_BODY+C_RY+2
	beq +
	inc a
	bne _g2rd_sl1
	txa
	bpl _g2rd_sl1
	bra ++
+	txa
	bmi _g2rd_sl1
++	sta.b G2_DY
	cmp #$8000
	ror a
	adc #0
	sta.b T2+2                  ; dy
	clc
	adc #$0080
	xba
	sta.b MD2
	stz.b G2_FLAG
	bra _g2rd_rot
_g2rd_sl1:
	jmp _g2rd_slow
_g2rd_rot:
	; Usually x, y are needed only to know that the rider is not moved:
	; x~ = 2*(Va+Vb) of the high bytes' products (below) is x-185 to x+181,
	; y~ (with -(Sn*dx1 >> 8)) y-185 to y+183. Sure if y~ in [10800+192,
	; RIDER_TOP-192], x~ in [RIDER_LEFT+192, 2048-192] (the seat and the
	; clamps, see below) and x~+192 <= 0 or y~+192 <= g2_ellt[(x~+192) >> 8].
	lda.b CS
	G2_MA
	lda.b MD0
	sta.w MPYB                  ; Cs*dx1
	ldx.w MPYM
	lda.b MD2
	sta.w MPYB                  ; Cs*dy1
	ldy.w MPYM
	lda.b SN
	G2_MA
	lda.b MD2
	sta.w MPYB                  ; Sn*dy1
	txa
	clc
	adc.w MPYM
	asl a
	sta.b T3                    ; x~
	lda.b MD0
	sta.w MPYB                  ; Sn*dx1
	tya
	sec
	sbc.w MPYM
	asl a
	sta.b T3+2                  ; y~
	lda.b S_TURNED
	and #$00FF
	beq +
	lda #0
	sec
	sbc.b T3
	sta.b T3
+	lda.b T3+2
	sec
	sbc #10800+192
	cmp #RIDER_TOP-10800-2*192+1
	bcs _g2rd_exact
	lda.b T3
	clc
	adc #-RIDER_LEFT-192
	cmp #2048-RIDER_LEFT-2*192+1
	bcs _g2rd_exact
	lda.b T3
	clc
	adc #192
	beq _g2rd_sure
	bmi _g2rd_sure
	xba
	and #$00FF
	asl a
	tax
	lda.b T3+2
	clc
	adc #192
	cmp.l g2_ellt,x
	bcc _g2rd_sure
	beq _g2rd_sure
	bra _g2rd_exact
_g2rd_sure:
	jmp _g2rd_fast
_g2rd_exact:
	; x = rsh( mq16( Cs, dx )+mq16( Sn, dy ), 7 ): with the products as
	; 256*W0+.. (low bytes) and 256*V+l (high bytes), it is 2*(Va+Vb)
	; +((W0a+la+W0b+lb+64) >> 7) (|Cs|+|Sn| < 46400: no overflow, no clamp):
	lda.b CS
	G2_MA
	lda.b T2
	sta.w MPYB                  ; Cs*dx0
	lda.w MPYM
	sta.b R
	lda.b T2+2
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
	lda.b T2+2
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
	lda.b T2
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
_g2rd_sslow:
	; The spring the slow way: dirx, diry, dx, dy, then mvx, mvy:
	lda.w g2_ofxb
	eor #$8000
	jsr phys_ext32
	SUB32 T1, S_BODY+C_RX, T0   ; rgx
	HALFDIFF T1, S_RIDX
	sta.b G2_DIRX
	lda.w g2_ofyb
	eor #$8000
	jsr phys_ext32
	ADD32 T1, S_BODY+C_RY, T0   ; rgy
	HALFDIFF T1, S_RIDY
	sta.b G2_DIRY
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
_g2rd_fast:
	; dirx = rsh( rgx-rider_x, 1 ) = -((d_x+OFX) >> 1), diry = rsh( OFY
	; -d_y, 1 ) (17-bit sums with the biases, no clamp):
	lda.b G2_DX
	eor #$8000
	clc
	adc.w g2_ofxb
	ror a
	eor #$7FFF
	inc a
	sta.b G2_DIRX
	lda.b G2_DY
	eor #$7FFF
	clc
	adc.w g2_ofyb
	ror a
	eor #$8000
	inc a
	sta.b G2_DIRY
	; WD = the signed bytes of wb if body.w is the one of the start of the
	; step; its top one in [-63, 63]: MD0 = 2*w2, MD1 = -2*w2.
	lda.b S_BODY+C_W
	cmp.w g2_w
	bne _g2rd_ws
	lda.b S_BODY+C_W+2
	cmp.w g2_w+2
	bne _g2rd_ws
	lda.b WD+2
	clc
	adc #63
	and #$00FF
	cmp #127
	bcc +
_g2rd_ws:
	jmp _g2rd_wslow
+	sec
	sbc #63
	asl a
	and #$00FF
	sta.b MD0
	eor #$00FF
	inc a
	sta.b MD0+1
	G2_WBMUL T2+2, 0
	txa
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
	G2_WBMUL T2, 1
	txa
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
	; += rsh( v, 8 ):
	lda #K_RIDER_D_M/2
	G2_MA
	G2_MULKS R2, 1, 1
	G2_MULKS T3, 1, 1
	G2_RIDV G2_DIRX, R2, GVX, S_RIDVX, S_RIDX
	G2_RIDV G2_DIRY, T3, GVY, S_RIDVY, S_RIDY
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
	CLAMP16 T0
	sta.b T0
	CLAMP16 T1
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
	CLAMP16 T0
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
	CLAMP16 T0
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
	CLAMP16 T0
	sta.b T0
	CLAMP16 T1
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
	CLAMP16 R
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
	CLAMP16 T0
	sta.b T0
	CLAMP16 T1
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
	tax
	PHYS_ENTER
	stx.b IN
	stz.b EV
	stz.b RACS
	stz.w phys_bump
	stz.w pt_fric
	stz.w pt_fric+2
	stz.w pt_crs
	stz.w pt_crs+2
	stz.w pt_crd
	stz.w pt_crd+2
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
	.REPT 4
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
	; beallit of the body: w -= MULK( rsh( cross_s, 2 ), K_TS ): for x' =
	; 4*rsh( cross_s, 2 ) = (cross_s+2) & ~3 in 24 bits it is floor( (x'*M
	; +2^15)/2^16 ):
	lda.w pt_crs
	clc
	adc #$8082
	and #$FFFC
	sta.b T0
	lda.w pt_crs+2
	adc #$0080
	sta.b T0+2
	cmp #$0100
	bcc +
	jmp _g2st_tss
+	lda #K_TS_M
	G2_MA
	G2_MULKS T0, 0
_g2st_ts2:
	SUB32 S_BODY+C_W, S_BODY+C_W, T0
	; w -= MULK( rsh( cross_d, 8 ), K_TD ): for x = rsh( cross_d, 8 ) in 16
	; bits (the multiplicand) floor( (x*32*M+2^15)/2^16 ), 32*K_TD_M =
	; 12*65536-115*256+64 (the products: 64x = 256*W0+.., -115x = 256*V1
	; +l1, 12x = P2; P2+V1+floor( (W0+l1+128)/256 )):
	lda.w pt_crd
	clc
	adc #$0080
	sta.b T0
	lda.w pt_crd+2
	adc #0
	sta.b T0+2
	clc
	adc #$0080
	and #$FF00
	beq +
	jmp _g2st_tds
+	lda.b T0+1
	G2_MA
	lda #64
	sta.w MPYB
	lda.w MPYM
	clc
	adc #16512
	sta.b T0
	lda #$008D
	sta.w MPYB
	lda.w MPYL
	and #$00FF
	clc
	adc.b T0
	xba
	and #$00FF
	clc
	adc.w MPYM
	sec
	sbc #64
	tay                         ; V1+floor( (W0+l1+128)/256 )
	lda #12
	sta.w MPYB
	tya
	eor #$8000
	clc
	adc.w MPYL
	tax
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #0
	tay                         ; Y:X = the MULK+$808000
_g2st_td2:
	; w = w-(Y:X)+$808000:
	stx.b T0
	sty.b T0+2
	lda.b S_BODY+C_W
	sec
	sbc.b T0
	tax
	lda.b S_BODY+C_W+2
	sbc.b T0+2
	tay
	txa
	clc
	adc #$8000
	sta.b S_BODY+C_W
	sta.w pt_da
	tya
	adc #$0080
	sta.b S_BODY+C_W+2
	sta.w pt_da+2
	; v += -MULK( Dx0+Dx1, K_20 )+gv:
	lda.w pt_dx
	clc
	adc.w pt_dx+4
	tax
	lda.w pt_dx+2
	adc.w pt_dx+6
	tay
	txa
	clc
	adc #$8080
	sta.b T0
	tya
	adc #$0080
	sta.b T0+2
	lda.w pt_dy
	clc
	adc.w pt_dy+4
	tax
	lda.w pt_dy+2
	adc.w pt_dy+6
	tay
	txa
	clc
	adc #$8080
	sta.b T1
	tya
	adc #$0080
	sta.b T1+2
.IF K_20_SH != 19 || (K_20_M & 1) != 0 || K_TS_SH != 14 || K_TD_SH != 11 || K_TD_M != 23658 || K_OMEGA_SH != 19
.FAIL "phys_step: the shifts of the constants"
.ENDIF
	lda #K_20_M/2
	G2_MA
	G2_MULKS T0, 2
	G2_MULKS T1, 2
	lda.b S_BODY+C_VX
	sec
	sbc.b T0
	tax
	lda.b S_BODY+C_VX+2
	sbc.b T0+2
	tay
	txa
	clc
	adc.b GVX
	sta.b S_BODY+C_VX
	tya
	adc.b GVX+2
	sta.b S_BODY+C_VX+2
	lda.b S_BODY+C_VY
	sec
	sbc.b T1
	tax
	lda.b S_BODY+C_VY+2
	sbc.b T1+2
	tay
	txa
	clc
	adc.b GVY
	sta.b S_BODY+C_VY
	tya
	adc.b GVY+2
	sta.b S_BODY+C_VY+2
	ldx #S_BODY
	jsr phys_move
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
	lda #S_K2
	sta.w phys_dpb+WK
	lda #S_ROLL
	sta.w phys_dpb+WR
	pea PHYS_DPB
	pld
	jsr phys_wheel
	pea PHYS_DPA
	pld
	lda.w phys_dpb+R
	sec
	sbc.w pt_da
	sta.b T0
	lda.w phys_dpb+R+2
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
	lda.w phys_dpb+R
	sec
	sbc.w pt_da
	sta.b T0
	lda.w phys_dpb+R+2
	sbc.w pt_da+2
	sta.b T0+2
	G2_ADDRSH8 S_DEFL+4, T0, 1
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
	; The sounds: friction, the driven wheel's omega (not in a quick step).
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
	bpl +
	lda #0
	sec
	sbc.b 0,x
	sta.b T0
	lda #0
	sbc.b 2,x
	sta.b T0+2
	bra ++
+	sta.b T0+2
	lda.b 0,x
	sta.b T0
++	lda.b T0+1                  ; >> 8 (|w| < 2^31: fits after), +$808080
	clc
	adc #$8080
	sta.b T1
	lda.b T0+3
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
	lda.b IN
	bit #PH_QUICK
	bne +
	jsr phys_mkview
	bra ++
+	jsr phys_mkout
++	ldx.b EV
	pld
	plb
	stx.b tcc__r0
	plp
phys_step_ret:                  ; (for measuring the time of a step)
	rtl

; The rare cases of the MULKs of phys_step:
_g2st_tss:
	MOV32W phys_dpa+T0, pt_crs
	RSH32 T0, 2
	MULK T0, K_TS
	MOV32 T0, R
	jmp _g2st_ts2
_g2st_tds:
	MOV32W phys_dpa+T0, pt_crd
	RSH32 T0, 8
	MULK T0, K_TD
	lda.b R
	clc
	adc #$8000
	tax
	lda.b R+2
	adc #$0080
	tay
	jmp _g2st_td2

.ENDS

; MULK( d, K_RIDER_S ) = floor( (d*K_RIDER_S_M+4096)/8192 ) for d from -4079
; to 4079 (phys_rider):
.SECTION ".g2_mst" SUPERFREE
g2_mst:
.REPT 2*4079+1 INDEX G2_I
	.dw floor( ((G2_I-4079)*K_RIDER_S_M+4096)/8192 )
.ENDR
.ENDS
