; The physics (phys.asm, phys_col.asm): the direct pages, the units and the
; arithmetic of the PPU multiplier, after test/phys_spec.c.
;
; Units: positions P = 1/65536 m, velocities V = 1/2^24 m a step, angles
; and angular velocities W = 1/2^28 rad (a step), torques T = 1/16 Nm, unit
; vectors Q15.
;
; While the physics runs: native mode, X and Y 16-bit, D = PHYS_DPA (or
; PHYS_DPB in the collision code), DB = the bank of the lines of the level
; ($80-$BF, where the I/O registers and the low RAM are too).

.include "phys_const.inc"

; Keys and events of a step (phys.h):
.DEFINE PH_GAS 1
.DEFINE PH_BRAKE 2
.DEFINE PH_VOLT_R 4
.DEFINE PH_VOLT_L 8
.DEFINE PH_DEAD 1
.DEFINE PH_FINISH 2
.DEFINE PH_EAT 4
.DEFINE PH_BUMP 8
.DEFINE PH_VOLT 16

; The direct page A: the state (in the order of ps_dump of
; test/phys_spec.c), then temporaries.
.DEFINE C_RX 0                  ; a circle: position (P)
.DEFINE C_RY 4
.DEFINE C_VX 8                  ; velocity (V)
.DEFINE C_VY 12
.DEFINE C_A 16                  ; angle (W)
.DEFINE C_W 20                  ; angular velocity (W)
.DEFINE C_SIZE 24

.ENUM $00
S_BODY      dsb 24              ; kor1
S_K2        dsb 24              ; kor2
S_K4        dsb 24              ; kor4
S_RIDX      dsb 4               ; vezetor (P), vezetov (V)
S_RIDY      dsb 4
S_RIDVX     dsb 4
S_RIDVY     dsb 4
S_HEADX     dsb 4               ; fejr (P)
S_HEADY     dsb 4
S_DEFL      dsb 8               ; brake deflection of kor2, kor4 (2^-20 rad)
S_VOLTW     dsb 8               ; kezdoomega1, 2 (W)
S_ROLL      dsb 20              ; rolling of kor2, kor4: speed (V), normal, on
S_VOLTON    dsb 2               ; ugrasban1, 2
S_VOLTT     dsb 2               ; steps since the volt started
S_LASTVOLT  db                  ; steps since the last volt
S_TURNED    db                  ; hatra_f
S_GRAVITY   db                  ; gravirany
S_BRAKEWAS  db                  ; voltfek
S_VOLT1     db                  ; ugras1volt
S_APPLES    db                  ; kajaszam
; Temporaries of the step:
CS22        dsb 4               ; cos and sin of the body, Q22
SN22        dsb 4
CS          dsb 2               ; the same, Q15
SN          dsb 2
W1          dsb 4               ; the body's angular velocity >> 4
WD          dsb 4               ; its signed bytes
EV          dsb 2               ; events of the step
RACS        dsb 2               ; Racsonkivul
GVX         dsb 4               ; gravity (V)
GVY         dsb 4
FX          dsb 4               ; force on the wheel (V), its torque (T)
FY          dsb 4
MK          dsb 4
CK          dsb 2               ; the wheel: its offset in the page (S_K2, S_K4)
CK4         dsb 2               ; and 4 times its number
KX          dsb 2               ; koto (2^-13 m)
KY          dsb 2
GX          dsb 4               ; gumi (P)
GY          dsb 4
RLX         dsb 4               ; korongrelv (V)
RLY         dsb 4
IN          dsb 2               ; the keys of the step
.ENDE

.DEFINE R_OFF 0                 ; a rolling wheel's state: speed (V)
.DEFINE R_NX 4                  ; normal of its contact
.DEFINE R_NY 6
.DEFINE R_ON 8
.DEFINE R_SIZE 10

; Both pages end with the scratch of the arithmetic:
.ENUM $E0
MD0         db                  ; the signed bytes of a multiplier
MD1         db
MD2         db
MDX         db
R           dsb 4               ; sums of products
R2          dsb 4
T0          dsb 4               ; general
T1          dsb 4
T2          dsb 4
T3          dsb 4
.ENDE

; The registers of the multiplier:
.DEFINE MPYA $211B              ; 16-bit, written low byte first
.DEFINE MPYB $211C              ; 8-bit, starts the product
.DEFINE MPYL $2134              ; the 24-bit product
.DEFINE MPYM $2135
.DEFINE MPYH $2136

; ---------------------------------------------------------------------------
; The multiplicand (A 8-bit):
.MACRO MB_DP                    ; a word of the direct page
	lda.b \1
	sta.w MPYA
	lda.b \1+1
	sta.w MPYA
.ENDM

.MACRO MB_ABS                   ; a word by absolute address (DB), with X
	lda.w \1
	sta.w MPYA
	lda.w \1+1
	sta.w MPYA
.ENDM

.MACRO MB_ABSX
	lda.w \1,x
	sta.w MPYA
	lda.w \1+1,x
	sta.w MPYA
.ENDM

.MACRO MB_IMM                   ; a constant
	lda.b #(\1) & $FF
	sta.w MPYA
	lda.b #((\1) >> 8) & $FF
	sta.w MPYA
.ENDM

; The signed bytes of a 16-bit word in [-32640, 32639] (A 8-bit), into MD0
; or \2:
.MACRO DIG16
	lda.b \1
	.IF NARGS == 2
	sta.b \2
	.ELSE
	sta.b MD0
	.ENDIF
	cmp #$80
	lda.b \1+1
	adc #0
	.IF NARGS == 2
	sta.b \2+1
	.ELSE
	sta.b MD1
	.ENDIF
.ENDM

; The signed bytes of a 24-bit number in [-$808080, $7F7F7F], the low 3
; bytes of a double word of the direct page (A 8-bit):
.MACRO DIG24
	lda.b \1
	.IF NARGS == 2
	sta.b \2
	.ELSE
	sta.b MD0
	.ENDIF
	cmp #$80
	rep #$20
	lda.b \1+1
	adc #0
	sep #$20
	.IF NARGS == 2
	sta.b \2+1
	.ELSE
	sta.b MD1
	.ENDIF
	cmp #$80
	xba
	adc #0
	.IF NARGS == 2
	sta.b \2+2
	.ELSE
	sta.b MD2
	.ENDIF
.ENDM

; A double word of the direct page into [-$808080, $7F7F7F] (A 16-bit):
.MACRO CLAMP24
	lda.b \1+2
	clc
	adc #$007F
	cmp #$00FE
	bcc _clamp24_f1\@
	ldx #\1
	jsr phys_clamp24
_clamp24_f1\@:
.ENDM

; R = MB * the signed bytes at \1 (MD0..MD2) >> 8 (rounded down), plus
; $808000 (A 8-bit in, 8-bit out):
.MACRO RSET24
	lda.b \1
	sta.w MPYB
	ldy.w MPYM                  ; P0 >> 8
	lda.b \1+1
	sta.w MPYB
	rep #$21
	tya
	eor #$8000
	adc.w MPYL
	sta.b R
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #0
	sta.b R+2
	sep #$20
	lda.b \1+2
	sta.w MPYB
	rep #$21
	lda.w MPYL
	adc.b R+1
	sta.b R+1
	sep #$20
	lda.w MPYH
	adc.b R+3
	sta.b R+3
.ENDM

; R += the same, plus $808000:
.MACRO RADD24
	lda.b \1
	sta.w MPYB
	ldy.w MPYM
	lda.b \1+1
	sta.w MPYB
	rep #$21
	tya
	eor #$8000
	adc.w MPYL
	tax
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #0
	tay
	txa
	clc
	adc.b R
	sta.b R
	tya
	adc.b R+2
	sta.b R+2
	sep #$20
	lda.b \1+2
	sta.w MPYB
	rep #$21
	lda.w MPYL
	adc.b R+1
	sta.b R+1
	sep #$20
	lda.w MPYH
	adc.b R+3
	sta.b R+3
.ENDM

; R = MB * the signed bytes at \1 (MD0..MD1) >> 8, plus $808000 (A 8-bit
; in, 16-bit out):
.MACRO RSET16
	lda.b \1
	sta.w MPYB
	ldy.w MPYM
	lda.b \1+1
	sta.w MPYB
	rep #$21
	tya
	eor #$8000
	adc.w MPYL
	sta.b R
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #0
	sta.b R+2
.ENDM

; R += the same, plus $808000 (A 8-bit in, 16-bit out):
.MACRO RADD16
	lda.b \1
	sta.w MPYB
	ldy.w MPYM
	lda.b \1+1
	sta.w MPYB
	rep #$21
	tya
	eor #$8000
	adc.w MPYL
	tax
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #0
	tay
	txa
	clc
	adc.b R
	sta.b R
	tya
	adc.b R+2
	sta.b R+2
.ENDM

; The same with constant signed bytes (a constant in [-32640, 32639]):
.MACRO RSETK
	lda.b #(\1) & $FF
	sta.w MPYB
	ldy.w MPYM
	lda.b #(((\1) - ((((\1) + 128) & 255) - 128)) / 256) & $FF
	sta.w MPYB
	rep #$21
	tya
	eor #$8000
	adc.w MPYL
	sta.b R
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #0
	sta.b R+2
.ENDM

.MACRO RADDK
	lda.b #(\1) & $FF
	sta.w MPYB
	ldy.w MPYM
	lda.b #(((\1) - ((((\1) + 128) & 255) - 128)) / 256) & $FF
	sta.w MPYB
	rep #$21
	tya
	eor #$8000
	adc.w MPYL
	tax
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc #0
	tay
	txa
	clc
	adc.b R
	sta.b R
	tya
	adc.b R+2
	sta.b R+2
.ENDM

; R += MB * a signed byte >> 8, plus $8000 (A 8-bit in, 16-bit out):
.MACRO RADD8
	lda \1
	sta.w MPYB
	rep #$21
	lda.w MPYM
	eor #$8000
	adc.b R
	sta.b R
	bcc _radd8_c\@
	inc.b R+2
_radd8_c\@:
.ENDM

; R = R - bias, rounded and shifted right by \1 (A 16-bit in and out); \2 is
; the bias of the products in R.
.MACRO RFIN
	lda.b R
	clc
	adc #((1 << ((\1)-1)) - (\2)) & $FFFF
	sta.b R
	lda.b R+2
	adc #(((1 << ((\1)-1)) - (\2)) >> 16) & $FFFF
	.IF \1 >= 16
	.REPT (\1)-16
	cmp #$8000
	ror a
	.ENDR
	sta.b R
	cmp #$8000
	lda #0
	bcc _rfin_f1\@
	dec a
_rfin_f1\@:	sta.b R+2
	.ELSE
	.IF \1 >= 8
	sta.b R+2
	lda.b R+1
	sta.b R
	lda.b R+2
	xba
	and #$00FF
	cmp #$0080
	bcc _rfin_f1\@
	ora #$FF00
_rfin_f1\@:
	.REPT (\1)-8
	cmp #$8000
	ror a
	ror.b R
	.ENDR
	sta.b R+2
	.ELSE
	.REPT \1
	cmp #$8000
	ror a
	ror.b R
	.ENDR
	sta.b R+2
	.ENDIF
	.ENDIF
.ENDM

; R = R - bias (A 16-bit):
.MACRO RFIN0
	lda.b R
	sec
	sbc #(\1) & $FFFF
	sta.b R
	lda.b R+2
	sbc #((\1) >> 16) & $FFFF
	sta.b R+2
.ENDM

; ---------------------------------------------------------------------------
; Moves and sums of double words of the direct page (A 16-bit):
.MACRO MOV32
	lda.b \2
	sta.b \1
	lda.b \2+2
	sta.b \1+2
.ENDM

; \1 = \2 + \3
.MACRO ADD32
	lda.b \2
	clc
	adc.b \3
	sta.b \1
	lda.b \2+2
	adc.b \3+2
	sta.b \1+2
.ENDM

; \1 = \2 - \3
.MACRO SUB32
	lda.b \2
	sec
	sbc.b \3
	sta.b \1
	lda.b \2+2
	sbc.b \3+2
	sta.b \1+2
.ENDM

; The same by absolute addresses (in the data bank):
.MACRO MOV32W
	lda.w \2
	sta.w \1
	lda.w \2+2
	sta.w \1+2
.ENDM

; \1 = rsh( \1, \2 ): shifted right rounding to nearest, \1 in the direct
; page.
.MACRO RSH32
	lda.b \1
	clc
	adc #(1 << ((\2)-1)) & $FFFF
	sta.b \1
	lda.b \1+2
	adc #((1 << ((\2)-1)) >> 16) & $FFFF
	.REPT \2
	cmp #$8000
	ror a
	ror.b \1
	.ENDR
	sta.b \1+2
.ENDM

; \1 = \1 >> \2, rounded down:
.MACRO ASR32
	lda.b \1+2
	.REPT \2
	cmp #$8000
	ror a
	ror.b \1
	.ENDR
	sta.b \1+2
.ENDM

; R = rsh( mq24( dp double word \1, \2_M ), \2_SH-8 ): the constant
; multiplier \2 (A 16-bit in and out; T3 is used).
.MACRO MULK
	lda.b \1
	sta.b T3
	lda.b \1+2
	sta.b T3+2
	CLAMP24 T3
	sep #$20
	DIG24 T3
	MB_IMM \2_M
	RSET24 MD0
	rep #$20
	RFIN (\2_SH)-8, $808000
.ENDM

; R = rsh( mq24( T3, MB ) + ..., ) helpers: the signed bytes of T3 after
; its clamp (A 16-bit in, 8-bit out).
.MACRO DIGT3
	CLAMP24 T3
	sep #$20
	DIG24 T3
.ENDM

; R = MB * the signed bytes at \1 (2 of them), the whole product (A 8-bit
; in, 16-bit out).
.MACRO RFULL16
	lda.b \1+1
	sta.w MPYB
	ldx.w MPYL
	stx.b R+1
	lda.w MPYH
	sta.b R+3
	stz.b R
	lda.b \1
	sta.w MPYB
	rep #$21
	lda.w MPYL
	adc.b R
	sta.b R
	lda.w MPYM
	xba
	and #$00FF
	eor #$0080
	adc.b R+2
	sec
	sbc #$0080
	sta.b R+2
.ENDM

; R = the square of the 16-bit word \1 of the direct page (|\1| <= 32767),
; the whole product (A 16-bit in and out; T3 is used).
.MACRO SQUARE
	lda.b \1
	bpl _square_f1\@
	eor #$FFFF
	inc a
_square_f1\@:	sta.b T3                    ; |x|
	eor #$FFFF
	inc a
	sta.b T3+2                  ; -|x|
	sep #$20
	MB_DP T3
	DIG16 T3+2
	RFULL16 MD0
	lda #0
	sec
	sbc.b R
	sta.b R
	lda #0
	sbc.b R+2
	sta.b R+2
.ENDM

; N = (A < \1), signed 16-bit (A is changed):
.MACRO SLT
	sec
	sbc #\1
	bvc _slt_f1\@
	eor #$8000
_slt_f1\@:
.ENDM

; The direct page B, of the collisions:
.DEFINE CT_TX 0                 ; a contact: its point (P)
.DEFINE CT_TY 4
.DEFINE CT_NX 8                 ; unit vector to the center (Q15)
.DEFINE CT_NY 10
.DEFINE CT_H 12                 ; distance (P)
.DEFINE CT_DN 14                ; (2^30 - |n|^2)/2
.DEFINE CT_HT 16                ; has_t
.DEFINE CT_HN 17                ; has_n
.DEFINE CT_SIZE 18

.ENUM $00
QX          dsb 4               ; the point from the corner of the grid (P)
QY          dsb 4
QRX         dsb 4               ; the point (P)
QRY         dsb 4
QRSQ        dsb 4               ; the radius squared
QR          dw                  ; the radius (P)
QBX         dw                  ; QX >> 8, QY >> 8
QBY         dw
QHEAD       dw                  ; 1: only whether there is a contact
QN          dw                  ; contacts found
QLIST       dw                  ; the next entry of the list of lines
QCNT        dw                  ; lines left
QL          dw                  ; the line
RX15        dsb 4               ; from its middle (2^-15 m)
RY15        dsb 4
DGX         dsb 3               ; their signed bytes
DGY         dsb 3
TAV         dsb 4               ; distance from the line, along it (P)
POS         dsb 4
DDX         dsb 4               ; from an end of it (P)
DDY         dsb 4
CT0         dsb 18              ; the contacts
CT1         dsb 18
CTN         dsb 18
WN          dw                  ; contacts of the wheel
WK          dw                  ; the wheel's offset in page A
NCT         dw                  ; the contact of norm, push, holds
NV          dsb 4               ; holds: the velocity towards the point (V)
NSH         dw                  ; norm: shifts
N90X        dw                  ; the direction of rolling
N90Y        dw
SP          dsb 4               ; the speed along the ground (V)
FN          dsb 4               ; the force along it (V)
.ENDE

; The page B again: the wheel's rolling state.
.ENUM $90
WR          dw                  ; offset of the wheel's S_ROLL entry in page A
HRHO        dw                  ; the rolling inertia
.ENDE

; \1 = \1 << \2 (direct page double word):
.MACRO ASL32
	.REPT \2
	asl.b \1
	rol.b \1+2
	.ENDR
.ENDM
