; The physics of the bike for the NES: what physics.c describes, to the
; bit, in assembly, which is several times faster and smaller than the C
; compiled. Its variables are in the zero page; the bike is Bike, laid out
; as bike_t of physics.h.

#include "physconst.h"
#include "mul.inc"

#ifdef __NES__
; On the NES the code runs in a bank of its own at $8000, entered through
; ph_step and ph_init in the fixed bank; its tables stay in the fixed bank.
#include "banks.h"
#else
#define PHYS_TEXT .text.physics
#endif

; Fields of a circle_t and of the bike_t:
#define RX 0
#define RY 4
#define VX 8
#define VY 10
#define ALFA 12
#define OMEGA 16
#define CIRCLE 18
#define BODY 0
#define WHEEL0 18
#define WHEEL1 36
#define RIDER_X 54
#define RIDER_Y 58
#define RIDER_VX 62
#define RIDER_VY 64
#define HEAD_X 66
#define HEAD_Y 70
#define TURNED 74
#define GRAVITY 75
#define BRAKE_WAS 76
#define STEPS 77
#define GFRAC 78
#define DBRAKE 79
#define VOLT 87
#define VOLT_OMEGA 89
#define BIKE_SIZE 93

; Fields of a seg_t:
#define S_PX 0
#define S_PY 2
#define S_DX 4
#define S_DY 6
#define S_EX 8
#define S_EY 10
#define S_LEN 12
#define S_X0 14
#define S_X1 15
#define S_Y0 16
#define S_Y1 17
#define SEG 18

; Fields of a contact: the normal, the distance and the contact point
; (from the origin of the lines):
#define C_NX 0
#define C_NY 2
#define C_L 4
#define C_TX 6
#define C_TY 8
#define CONTACT 10

#define IN_GAS 1
#define IN_BRAKE 2
#define IN_VOLT_RIGHT 4
#define IN_VOLT_LEFT 8

; The constants of kmul:
#define K_OMS 0
#define K_BRAKE_A 1
#define K_BRAKE_W 2
#define K_K_X 3
#define K_K_Y 4
#define K_SPRING_W 5
#define K_FRIC_W 6
#define K_REACT 7
#define K_TWENTIETH 8
#define K_SPRING_T 9
#define K_FRIC_T 10
#define K_FREE 11
#define K_ROLL_T 12
#define K_ROLL_W 13
#define K_ROLL_DW 14
#define K_ROLL_V 15
#define K_NEW 16
#define K_OLD 17
#define K_SEAT_NX 18
#define K_SEAT_NY 19
#define K_ELLIPSE 20
#define K_RREST 21
#define K_RIDER_S 22
#define K_RIDER_F 23
#define K_H_X 24
#define K_H_Y 25
#define KLIST X(OMS) X(BRAKE_A) X(BRAKE_W) X(K_X) X(K_Y) X(SPRING_W) X(FRIC_W) \
	X(REACT) X(TWENTIETH) X(SPRING_T) X(FRIC_T) X(FREE) X(ROLL_T) X(ROLL_W) \
	X(ROLL_DW) X(ROLL_V) X(NEW) X(OLD) X(SEAT_NX) X(SEAT_NY) X(ELLIPSE) \
	X(RREST) X(RIDER_S) X(RIDER_F) X(H_X) X(H_Y)

.section .zp.bss,"aw",@nobits
Sn: .zero 2          ; sin, cos and -sin of the body's angle, as the
Cs: .zero 2          ; vectors (Sn, Cs) and (Cs, NSn)
NSn: .zero 2
Oms: .zero 2
inp: .zero 1
odd: .zero 1
kk: .zero 1          ; the wheel, 0 or 2 (its index in the int16 arrays)
W: .zero CIRCLE      ; the wheel being moved
wdvx: .zero 2        ; its velocity change and torque
wdvy: .zero 2
wtq: .zero 2
qx: .zero 2          ; its center from the origin of the lines
qy: .zero 2
qxb: .zero 1         ; SEG_BOX of qx and qy
qyb: .zero 1
cx: .zero 4          ; a center in u
cy: .zero 4
L0: .zero 4
L1: .zero 4
t0: .zero 2
t1: .zero 2
t2: .zero 2
t3: .zero 2
t4: .zero 2
t5: .zero 2
t6: .zero 2
t7: .zero 2
nrm: .zero 4         ; a direction (x, y)
n90: .zero 4         ; and another
segp: .zero 2        ; the line looked at
sl: .zero 1          ; lines left
found: .zero 1
cp: .zero 2          ; a contact
cq: .zero 2          ; another one
moved: .zero 1
tz: .zero 2          ; for the macros
pbank: .zero 1       ; the bank at $8000 before the physics
kvec: .zero 2        ; where kmul goes on for the exponent of a constant

.section .bss.physics,"aw",@nobits
.globl Bike
Bike: .zero BIKE_SIZE
tq: .zero 4
gsx: .zero 4
gsy: .zero 4
dvx: .zero 4
dvy: .zero 4
ts: .zero 4
tf: .zero 4
dvbx: .zero 2
dvby: .zero 2
dwb: .zero 2
gx: .zero 2
gy: .zero 2
gx2: .zero 2
gy2: .zero 2
oldomega: .zero 2
two: .zero 1
nct: .zero 1
Ct0: .zero CONTACT
Ct1: .zero CONTACT

; --- Macros -------------------------------------------------------------------

.macro JEQ l
	bne .Lj\@
	jmp \l
.Lj\@:
.endm
.macro JNE l
	beq .Lj\@
	jmp \l
.Lj\@:
.endm
.macro JCS l
	bcc .Lj\@
	jmp \l
.Lj\@:
.endm
.macro JCC l
	bcs .Lj\@
	jmp \l
.Lj\@:
.endm
.macro JMI l
	bpl .Lj\@
	jmp \l
.Lj\@:
.endm

.macro MOVW d, s
	lda \s
	sta \d
	lda \s+1
	sta \d+1
.endm

.macro LDIW d, v
	lda #((\v) & 0xff)
	sta \d
	lda #(((\v) & 0xffff) >> 8)
	sta \d+1
.endm

.macro STAX d
	sta \d
	stx \d+1
.endm

; d = the address of a symbol:
.macro LDIA d, v
	lda #mos16lo(\v)
	sta \d
	lda #mos16hi(\v)
	sta \d+1
.endm

.macro LDAX s
	lda \s
	ldx \s+1
.endm

.macro ADDW d, a, b
	clc
	lda \a
	adc \b
	sta \d
	lda \a+1
	adc \b+1
	sta \d+1
.endm

.macro SUBW d, a, b
	sec
	lda \a
	sbc \b
	sta \d
	lda \a+1
	sbc \b+1
	sta \d+1
.endm

; d = a + A:X
.macro ADDAX d, a
	clc
	adc \a
	sta \d
	txa
	adc \a+1
	sta \d+1
.endm

; d = d - A:X
.macro SUBAX d
	sta tz
	stx tz+1
	SUBW \d, \d, tz
.endm

.macro NEGW d, s
	sec
	lda #0
	sbc \s
	sta \d
	lda #0
	sbc \s+1
	sta \d+1
.endm

; d = -A:X
.macro NEGAX d
	sta tz
	stx tz+1
	NEGW \d, tz
.endm

; L0 = a - b (32 bits):
.macro SUBL a, b
	sec
	lda \a
	sbc \b
	sta L0
	lda \a+1
	sbc \b+1
	sta L0+1
	lda \a+2
	sbc \b+2
	sta L0+2
	lda \a+3
	sbc \b+3
	sta L0+3
.endm

; d += L1 (32 bits):
.macro ADDL1 d
	clc
	lda \d
	adc L1
	sta \d
	lda \d+1
	adc L1+1
	sta \d+1
	lda \d+2
	adc L1+2
	sta \d+2
	lda \d+3
	adc L1+3
	sta \d+3
.endm

; A:X = sat16( a + b ) of two words (b may be indexed, ",y"):
.macro ADDSAT a, b, b1
	clc
	lda \a
	adc \b
	sta tz
	lda \a+1
	adc \b1
	sta tz+1
	jsr satv
.endm

; A:X = the constant k times A:X (kmul):
.macro KM k
	ldy #(2*(\k))
	jsr kmul
.endm

; Multiplications of the words a and b (in the zero page or not): m_p =
; a*b, A:X = mulq14( a, b ) and mulq10( a, b ).
.macro MUL16 a, b
	MOVW m_a, \a
	MOVW m_b, \b
	jsr smul
.endm

.macro MULQ14 a, b
	MOVW m_a, \a
	MOVW m_b, \b
	jsr zmulq14
.endm

.macro MULQ10 a, b
	MOVW m_a, \a
	MOVW m_b, \b
	jsr zmulq10
.endm

; Calls fn with the zero page operands a and b in X and Y:
.macro ZZ fn, a, b
	ldx #mos8(\a)
	ldy #mos8(\b)
	jsr \fn
.endm

; Branches to lbl if a < v (signed 16 bits, v a number) / a >= v:
.macro BLTI a, v, lbl
	sec
	lda \a
	sbc #((\v) & 0xff)
	lda \a+1
	sbc #(((\v) & 0xffff) >> 8)
	bvc .Lb\@
	eor #$80
.Lb\@:
	bpl .Le\@
	jmp \lbl
.Le\@:
.endm

.macro BGEI a, v, lbl
	sec
	lda \a
	sbc #((\v) & 0xff)
	lda \a+1
	sbc #(((\v) & 0xffff) >> 8)
	bvc .Lb\@
	eor #$80
.Lb\@:
	bmi .Le\@
	jmp \lbl
.Le\@:
.endm

; Branches to lbl if a < b (signed 16 bits):
.macro BLT a, b, lbl
	sec
	lda \a
	sbc \b
	lda \a+1
	sbc \b+1
	bvc .Lb\@
	eor #$80
.Lb\@:
	bpl .Le\@
	jmp \lbl
.Le\@:
.endm

; Moves the 16-bit field f of the line at segp, the contact at cp:
.macro LDS d, f
	ldy #\f
	lda (segp),y
	sta \d
	iny
	lda (segp),y
	sta \d+1
.endm

.macro LDC d, f
	ldy #\f
	lda (cp),y
	sta \d
	iny
	lda (cp),y
	sta \d+1
.endm

.macro STC f, s
	ldy #\f
	lda \s
	sta (cp),y
	iny
	lda \s+1
	sta (cp),y
.endm

.macro SETCP c
	lda #mos16lo(\c)
	sta cp
	lda #mos16hi(\c)
	sta cp+1
.endm

.macro SETCQ c
	lda #mos16lo(\c)
	sta cq
	lda #mos16hi(\c)
	sta cq+1
.endm

; --- Helpers ------------------------------------------------------------------

; Arithmetic on the zero page only, in the fixed bank where there is room.
.section .text.physics_helpers,"ax",@progbits

; A:X = A:X times the constant Y/2 of the tables, kc_m/2^e, rounded and
; saturated (KMUL of physics.c): x*m into m_p, then on to the shifts for e
; at kc_ent (kent_e below).
kmul:
	sta m_a
	stx m_a+1
	lda kc_ent,y
	sta kvec
	lda kc_ent+1,y
	sta kvec+1
	lda kc_m,y
	SETA
	sec
	ldy m_a
	MUL8C m_p, m_p+1
	ldy m_a+1
	MUL8C m_t, m_p+2
	clc
	lda m_p+1
	adc m_t
	sta m_p+1
	bcc 1f
	inc m_p+2
1:
	; Signed: less m << 16 if x < 0, the product then negative.
	ldx #0
	lda m_a+1
	bpl 2f
	sec
	lda m_p+2
	sbc mp_lo1
	sta m_p+2
	dex
2:
	stx m_p+3
	lda m_p+2
	jmp (kvec)

; e < 8: << 8-e, the result in bytes 1 and 2, saturated.
kent_5:
	asl m_p
	rol m_p+1
	rol m_p+2
	rol m_p+3
kent_6:
	asl m_p
	rol m_p+1
	rol m_p+2
	rol m_p+3
kent_7:
	asl m_p
	rol m_p+1
	rol m_p+2
	rol m_p+3
	lda m_p
	asl a
	lda m_p+1
	adc #0
	sta m_p+1
	lda m_p+2
	adc #0
	tax
	lda m_p+3
	adc #0
	sta m_p+3
	; Bytes 2 and 3 of the same sign:
	txa
	and #$80
	beq 1f
	lda #$ff
1:
	cmp m_p+3
	bne 2f
	lda m_p+1
	rts
2:
	lda m_p+3
	bmi 3f
	lda #$ff
	ldx #$7f
	rts
3:
	lda #0
	ldx #$80
	rts

; 8 <= e <= 12: >> e-8, byte 2 in A, the result in bytes 1 and 2.
kent_12:
	cmp #$80
	ror a
	ror m_p+1
	ror m_p
kent_11:
	cmp #$80
	ror a
	ror m_p+1
	ror m_p
kent_10:
	cmp #$80
	ror a
	ror m_p+1
	ror m_p
kent_9:
	cmp #$80
	ror a
	ror m_p+1
	ror m_p
kent_8:
	; Rounded by the bit below:
	tax
	lda m_p
	asl a
	lda m_p+1
	adc #0
	bcc 1f
	inx
1:
	rts

; e > 12: << 16-e, the result in bytes 2 and 3.
kent_13:
	asl m_p+1
	rol m_p+2
	rol m_p+3
kent_14:
	asl m_p+1
	rol m_p+2
	rol m_p+3
kent_15:
	asl m_p+1
	rol m_p+2
	rol m_p+3
	lda m_p+1
	asl a
	lda m_p+2
	adc #0
	tay
	lda m_p+3
	adc #0
	tax
	tya
	rts

; A:X = dotq14 of the zero page vectors at X and Y: the first product put
; aside in m_q, the second added to it.
dot_zz:
	stx tz
	sty tz+1
	lda 0,x
	sta m_a
	lda 1,x
	sta m_a+1
	lda 0,y
	sta m_b
	lda 1,y
	sta m_b+1
	jsr smul
	.irp i, 0, 1, 2, 3
	lda m_p+\i
	sta m_q+\i
	.endr
	ldx tz
	ldy tz+1
	lda 2,x
	sta m_a
	lda 3,x
	sta m_a+1
	lda 2,y
	sta m_b
	lda 3,y
	sta m_b+1
	jsr smul
	clc
	.irp i, 0, 1, 2, 3
	lda m_p+\i
	adc m_q+\i
	sta m_p+\i
	.endr
	jmp pq14

; A:X = L0 saturated to 16 bits.
sat_L0:
	lda L0+1
	and #$80
	beq 1f
	lda #$ff
1:
	cmp L0+2
	bne 2f
	cmp L0+3
	bne 2f
	lda L0
	ldx L0+1
	rts
2:
	lda L0+3
	bmi 3f
	lda #$ff
	ldx #$7f
	rts
3:
	lda #0
	ldx #$80
	rts

; A:X = sat16( L0 >> 8 ), sat16( L0 >> 4 ):
sat8_L0:
	lda L0+1
	sta L0
	lda L0+2
	sta L0+1
	lda L0+3
	sta L0+2
	and #$80
	beq 1f
	lda #$ff
1:
	sta L0+3
	jmp sat_L0

sat4_L0:
	; L0 >> 4 fits if bits 19..31 are all the sign:
	lda L0+3
	bmi 1f
	bne satmax
	lda L0+2
	cmp #$08
	bcs satmax
	bcc 2f
1:
	cmp #$ff
	bne satmin
	lda L0+2
	cmp #$f8
	bcc satmin
2:
	.rept 4
	lsr L0+2
	ror L0+1
	ror L0
	.endr
	lda L0
	ldx L0+1
	rts
satmax:
	lda #$ff
	ldx #$7f
	rts
satmin:
	lda #0
	ldx #$80
	rts

; A:X = tz, saturated if V is set after it was added (its sign is then
; the wrong one).
satv:
	bvs 1f
	lda tz
	ldx tz+1
	rts
1:
	lda tz+1
	bmi satmax
	bpl satmin

; A:X = the 24 bits of L0[0..2] saturated to 16.
sat24:
	lda L0+1
	and #$80
	beq 1f
	lda #$ff
1:
	cmp L0+2
	bne 2f
	lda L0
	ldx L0+1
	rts
2:
	lda L0+2
	bmi satmin
	bpl satmax

; L0 >>= 4, arithmetic.
sar4_L0:
	ldy #4
1:
	lda L0+3
	cmp #$80
	ror L0+3
	ror L0+2
	ror L0+1
	ror L0
	dey
	bne 1b
	rts

; L0 = A:X sign extended, L1 likewise.
sext_L0:
	sta L0
	stx L0+1
	txa
	ldx #0
	and #$80
	beq 1f
	dex
1:
	stx L0+2
	stx L0+3
	rts

sext_L1:
	sta L1
	stx L1+1
	txa
	ldx #0
	and #$80
	beq 1f
	dex
1:
	stx L1+2
	stx L1+3
	rts

; L0 += L1, L0 -= L1.
add_L0:
	clc
	lda L0
	adc L1
	sta L0
	lda L0+1
	adc L1+1
	sta L0+1
	lda L0+2
	adc L1+2
	sta L0+2
	lda L0+3
	adc L1+3
	sta L0+3
	rts

sub_L0:
	sec
	lda L0
	sbc L1
	sta L0
	lda L0+1
	sbc L1+1
	sta L0+1
	lda L0+2
	sbc L1+2
	sta L0+2
	lda L0+3
	sbc L1+3
	sta L0+3
	rts

; L0 = m_p, L1 = m_p.
copy_p:
	lda m_p
	sta L0
	lda m_p+1
	sta L0+1
	lda m_p+2
	sta L0+2
	lda m_p+3
	sta L0+3
	rts

copy_p1:
	lda m_p
	sta L1
	lda m_p+1
	sta L1+1
	lda m_p+2
	sta L1+2
	lda m_p+3
	sta L1+3
	rts

.section PHYS_TEXT,"ax",@progbits

; Sine and cosine of the body's angle into Sn, Cs and NSn (fsin of
; fixmath.c).
angle:
	lda Bike+BODY+ALFA+2
	asl a
	tay
	lda Bike+BODY+ALFA+1
	ldx #mos8(Sn)
	jsr sine
	lda Bike+BODY+ALFA+2
	clc
	adc #64
	asl a
	tay
	lda Bike+BODY+ALFA+1
	ldx #mos8(Cs)
	jsr sine
	NEGW NSn, Sn
	rts

; The sine of entry Y/2 (Y/2+128 with carry) with the fraction A, into the
; zero page at X.
sine:
	pha
	bcs 2f
	lda sintab,y
	sta 0,x
	lda sintab+1,y
	sta 1,x
	sec
	lda sintab+2,y
	sbc sintab,y
	sta m_a
	lda sintab+3,y
	sbc sintab+1,y
	sta m_a+1
	jmp 3f
2:
	lda sintab+256,y
	sta 0,x
	lda sintab+257,y
	sta 1,x
	sec
	lda sintab+258,y
	sbc sintab+256,y
	sta m_a
	lda sintab+259,y
	sbc sintab+257,y
	sta m_a+1
3:
	stx tz
	pla
	jsr smul8
	ldx tz
	clc
	lda 0,x
	adc m_p+1
	sta 0,x
	lda 1,x
	adc m_p+2
	sta 1,x
	rts

; Moves the circle W by its velocity and turns it (move of physics.c):
; alfa += omega << 7, rx += vx << 2, ry += vy << 2.
move_w:
	; omega << 7: omega >> 1 at byte 1, its low bit as bit 7 of byte 0
	lda W+OMEGA+1
	cmp #$80
	ror a
	sta L1+1
	lda W+OMEGA
	ror a
	sta L1
	lda #0
	ror a
	clc
	adc W+ALFA
	sta W+ALFA
	lda W+ALFA+1
	adc L1
	sta W+ALFA+1
	lda W+ALFA+2
	adc L1+1
	sta W+ALFA+2
	lda L1+1
	and #$80
	beq 1f
	lda #$ff
1:
	adc W+ALFA+3
	sta W+ALFA+3
	ldx #0
	ldy #0
	jsr 2f
	ldx #(VY-VX)
	ldy #(RY-RX)
	; fall through
2:
	; The coordinate (X 0 and Y 0 for x, 2 and 4 for y): += v << 2.
	lda W+VX+1,x
	sta L1+1
	and #$80
	beq 3f
	lda #$ff
3:
	sta L1+2
	lda W+VX,x
	asl a
	rol L1+1
	rol L1+2
	asl a
	rol L1+1
	rol L1+2
	clc
	adc W+RX,y
	sta W+RX,y
	lda W+RX+1,y
	adc L1+1
	sta W+RX+1,y
	lda W+RX+2,y
	adc L1+2
	sta W+RX+2,y
	lda L1+2
	and #$80
	beq 4f
	lda #$ff
4:
	adc W+RX+3,y
	sta W+RX+3,y
	rts

; L1 = A:X << 2, sign extended.
shl2_L1:
	jsr sext_L1
	asl L1
	rol L1+1
	rol L1+2
	rol L1+3
	asl L1
	rol L1+1
	rol L1+2
	rol L1+3
	rts

; Copies a circle of the bike (offset Y) into W and back.
circle_in:
	.set i, 0
	.rept CIRCLE
	lda Bike+i,y
	sta W+i
	.set i, i+1
	.endr
	rts

circle_out:
	.set i, 0
	.rept CIRCLE
	lda W+i
	sta Bike+i,y
	.set i, i+1
	.endr
	rts

; --- Contacts -----------------------------------------------------------------

; Calls seg_query for the cell of (cx, cy), with the center then from the
; corner of the cell in qx, qy and their SEG_BOX in qxb, qyb.
query:
	ldx #(cy-cx)
	jsr cell
	sta sl
	ldx #0
	jsr cell
	ldx sl
	jsr seg_query
	MOVW segp, Seg_cur
	lda Seg_left
	sta sl
	lda cx
	sta qx
	lda cx+1
	and #$0f
	sta qx+1
	lda cy
	sta qy
	lda cy+1
	and #$0f
	sta qy+1
	; Their SEG_BOX, as 0 <= q < 4096: bits 6..13 plus 128.
	lda qx
	asl a
	sta tz
	lda qx+1
	rol a
	asl tz
	rol a
	ora #$80
	sta qxb
	lda qy
	asl a
	sta tz
	lda qy+1
	rol a
	asl tz
	rol a
	ora #$80
	sta qyb
	rts

; A = seg_cell of the 32 bits at cx+X: c >> 12, 255 outside [0, 255 << 12).
cell:
	lda cx+3,x
	bne 1f
	lda cx+2,x
	cmp #$10
	bcs 1f
	asl a
	asl a
	asl a
	asl a
	sta tz
	lda cx+1,x
	lsr a
	lsr a
	lsr a
	lsr a
	ora tz
	rts
1:
	lda #$ff
	rts

nfar:
	clc
	rts
near:
	; Within its box first:
	ldy #S_X0
	lda qxb
	cmp (segp),y
	bcc nfar
	iny
	lda (segp),y
	cmp qxb
	bcc nfar
	iny
	lda qyb
	cmp (segp),y
	bcc nfar
	iny
	lda (segp),y
	cmp qyb
	bcc nfar
	ldy #S_PX
	sec
	lda qx
	sbc (segp),y
	sta t0
	iny
	lda qx+1
	sbc (segp),y
	sta t0+1
	ldy #S_PY
	sec
	lda qy
	sbc (segp),y
	sta t1
	iny
	lda qy+1
	sbc (segp),y
	sta t1+1
	; d = (x, y).(-ey, ex), |d| < r:
	LDS nrm, S_EX
	LDS nrm+2, S_EY
	NEGW n90, nrm+2
	MOVW n90+2, nrm
	ZZ dot_zz, t0, n90
	STAX t2
	sec
	lda t2
	sbc t7
	lda t2+1
	sbc t7+1
	bvc 1f
	eor #$80
1:
	bpl 9f                   ; d >= r
	clc
	lda t2
	adc t7
	sta tz
	lda t2+1
	adc t7+1
	bmi 9f                   ; d < -r
	ora tz
	beq 9f                   ; d = -r
	ZZ dot_zz, t0, nrm
	STAX t3
	sec
	rts
9:
	clc
	rts

; Carry set if pos (t3) is within the line: 0 <= pos <= len.
along:
	lda t3+1
	bmi 1f
	ldy #S_LEN
	sec
	lda (segp),y
	sbc t3
	iny
	lda (segp),y
	sbc t3+1
	bvc 2f
	eor #$80
2:
	bmi 1f
	sec
	rts
1:
	clc
	rts

; From the end point nearest to the center: (t0, t1) moved to it if pos >
; 0, and L0 their length squared.
end_point:
	lda t3+1
	bmi 1f
	ora t3
	beq 1f
	ldy #S_DX
	sec
	lda t0
	sbc (segp),y
	sta t0
	iny
	lda t0+1
	sbc (segp),y
	sta t0+1
	ldy #S_DY
	sec
	lda t1
	sbc (segp),y
	sta t1
	iny
	lda t1+1
	sbc (segp),y
	sta t1+1
1:
	MUL16 t0, t0
	jsr copy_p
	MUL16 t1, t1
	jsr copy_p1
	jmp add_L0

advance_line:
	clc
	lda segp
	adc #SEG
	sta segp
	bcc 1f
	inc segp+1
1:
	rts

; Normalizes (t0, t1) of length squared L0 into the contact at cp: its
; normal and length (normalize of physics.c). t2..t4 are lost.
normalize:
	lda L0+3
	ora L0+2
	JNE ntable
	lda L0+1
	cmp #$40
	JCS ntable
	; Deep in the ground, rare: with the square root and divisions in C.
	lda #0
	sta __rc2
	sta __rc3
	lda L0
	ldx L0+1
	jsr isqrt32
	STAX t2
	ora t2+1
	bne 2f
	LDIW t3, 0
	STC C_NX, t3
	STC C_L, t3
	LDIW t3, 16384
	STC C_NY, t3
	rts
2:
	MOVW __rc2, t2
	LDAX t0
	jsr div14
	STAX t3
	STC C_NX, t3
	MOVW __rc2, t2
	LDAX t1
	jsr div14
	STAX t3
	STC C_NY, t3
	STC C_L, t2
	rts
ntable:
	; i = (d2-16384) >> 9, at most 296, from the table of 2^18/sqrt( d2 ):
	sec
	lda L0+1
	sbc #$40
	sta t2
	lda L0+2
	sbc #0
	lsr a
	sta t2+1
	lda t2
	ror a
	sta t2
	lda t2+1
	beq 3f
	lda t2
	cmp #(296-256)
	bcc 3f
	lda #(296-256)
	sta t2
3:
	asl t2
	rol t2+1
	clc
	lda #mos16lo(rsqrt)
	adc t2
	sta t2
	lda #mos16hi(rsqrt)
	adc t2+1
	sta t2+1
	ldy #0
	lda (t2),y
	sta t4
	iny
	lda (t2),y
	sta t4+1                 ; r
	; n = sat16( d*r >> 4 ), l = n.d:
	MUL16 t0, t4
	jsr copy_p
	jsr sat4_L0
	STAX t2
	MUL16 t1, t4
	jsr copy_p
	jsr sat4_L0
	STAX t3
	STC C_NX, t2
	STC C_NY, t3
	ZZ dot_zz, t2, t0
	STAX t2
	STC C_L, t2
	rts

; The contact point of the contact at cp: (qx, qy) less its normal times
; its length.
contact_point:
	LDC t0, C_NX
	LDC t1, C_L
	MULQ14 t0, t1
	NEGAX t2
	ADDW t2, t2, qx
	STC C_TX, t2
	LDC t0, C_NY
	MULQ14 t0, t1
	NEGAX t2
	ADDW t2, t2, qy
	STC C_TY, t2
	rts

; The contacts of the wheel W, its center (cx, cy): 0, 1 or 2 of them in
; Ct0, Ct1 (talppontkereses of UTKOZES.CPP), in A.
contacts:
	lda #0
	sta found
	jsr query
	LDIW t7, R_WHEEL
cnext:
	lda sl
	bne 1f
	lda found
	rts
1:
	dec sl
	jsr near
	JCC cskip
	SETCP Ct0
	lda found
	beq 2f
	SETCP Ct1
2:
	jsr along
	bcc cend
	; Along the line:
	lda t2+1
	bmi 4f
	STC C_NX, n90
	STC C_NY, n90+2
	STC C_L, t2
	jmp cfound
4:
	NEGW t4, n90
	STC C_NX, t4
	NEGW t4, n90+2
	STC C_NY, t4
	NEGW t2, t2
	STC C_L, t2
	jmp cfound
cend:
	; Near an end point:
	jsr end_point
	BGEI t0, R_WHEEL, cskip
	BLTI t0, -R_WHEEL+1, cskip
	BGEI t1, R_WHEEL, cskip
	BLTI t1, -R_WHEEL+1, cskip
	; d2 >= R^2: no contact
	lda L0+2
	cmp #(((R_WHEEL*R_WHEEL) >> 16) & 0xff)
	bcc 6f
	JNE cskip
	lda L0+1
	cmp #(((R_WHEEL*R_WHEEL) >> 8) & 0xff)
	bcc 6f
	JNE cskip
	lda L0
	cmp #((R_WHEEL*R_WHEEL) & 0xff)
	JCS cskip
6:
	jsr normalize
cfound:
	lda found
	bne 7f
	inc found
	jmp cskip
7:
	; Two points: merged if closer than MERGE.
	SETCP Ct0
	jsr contact_point
	SETCP Ct1
	jsr contact_point
	SUBW t0, Ct1+C_TX, Ct0+C_TX
	SUBW t1, Ct1+C_TY, Ct0+C_TY
	BGEI t0, MERGE, ctwo
	BLTI t0, -MERGE+1, ctwo
	BGEI t1, MERGE, ctwo
	BLTI t1, -MERGE+1, ctwo
	MUL16 t0, t0
	jsr copy_p
	MUL16 t1, t1
	jsr copy_p1
	jsr add_L0
	lda L0+2
	JNE ctwo
	lda L0+1
	cmp #(((MERGE*MERGE) >> 8) & 0xff)
	bcc 2f
	JNE ctwo
	lda L0
	cmp #((MERGE*MERGE) & 0xff)
	JCS ctwo
2:
	; Their average: q - t0 - (d >> 1).
	lda t0+1
	cmp #$80
	ror t0+1
	ror t0
	lda t1+1
	cmp #$80
	ror t1+1
	ror t1
	SUBW t2, qx, Ct0+C_TX
	SUBW t0, t2, t0
	SUBW t2, qy, Ct0+C_TY
	SUBW t1, t2, t1
	MUL16 t0, t0
	jsr copy_p
	MUL16 t1, t1
	jsr copy_p1
	jsr add_L0
	SETCP Ct0
	jsr normalize
cskip:
	jsr advance_line
	jmp cnext
ctwo:
	lda #2
	rts

; Whether the head at (cx, cy) touches the ground, in A.
touches:
	jsr query
	LDIW t7, R_HEAD
tnext:
	lda sl
	bne 1f
	lda #0
	rts
1:
	dec sl
	jsr near
	bcc tskip
	jsr along
	bcc 2f
	lda #1
	rts
2:
	jsr end_point
	lda L0+3
	ora L0+2
	bne tskip
	lda L0+1
	cmp #(((R_HEAD*R_HEAD) >> 8) & 0xff)
	bcc 4f
	bne tskip
	lda L0
	cmp #((R_HEAD*R_HEAD) & 0xff)
	bcs tskip
4:
	lda #1
	rts
tskip:
	jsr advance_line
	jmp tnext

; --- A wheel on the ground ----------------------------------------------------

; Adds A:X << 8 to the 32 bits at Y in the zero page (W+RX, W+RY).
add8_w:
	sta tz
	stx tz+1
	txa
	ldx #0
	and #$80
	beq 1f
	dex
1:
	clc
	lda 1,y
	adc tz
	sta 1,y
	lda 2,y
	adc tz+1
	sta 2,y
	txa
	adc 3,y
	sta 3,y
	rts

; helyigazitas: the contact at cp pushes the wheel W out to the band; the
; one at cq (if its high byte is not 0) gets farther along its normal.
pushout:
	LDC t1, C_L
	LDIW t0, R_WHEEL-BAND
	SUBW t0, t0, t1          ; push
	lda t0+1
	JMI pdone
	ora t0
	JEQ pdone
	LDC t2, C_NX
	MULQ14 t0, t2
	STAX t1                  ; px
	LDC t3, C_NY
	MULQ14 t0, t3
	STAX t2                  ; py
	LDAX t1
	ldy #mos8(W+RX)
	jsr add8_w
	LDAX t2
	ldy #mos8(W+RY)
	jsr add8_w
	LDC t3, C_L
	ADDW t3, t3, t0
	STC C_L, t3
	lda cq+1
	JEQ pdone
	; the other one: l += (px, py).n
	ldy #C_NX
	lda (cq),y
	sta nrm
	iny
	lda (cq),y
	sta nrm+1
	iny
	lda (cq),y
	sta nrm+2
	iny
	lda (cq),y
	sta nrm+3
	ZZ dot_zz, t1, nrm
	STAX t0
	ldy #C_L
	clc
	lda (cq),y
	adc t0
	sta (cq),y
	iny
	lda (cq),y
	adc t0+1
	sta (cq),y
pdone:
	rts

; nrm = the normal of the contact at cp.
cp_normal:
	LDC nrm, C_NX
	LDC nrm+2, C_NY
	rts

; talppontigazitas: carry set if the contact at cp supports the wheel W;
; with A not 0 the velocity towards it is removed.
supports:
	sta moved
	jsr cp_normal
	ZZ dot_zz, W+VX, nrm
	STAX t0                  ; nv
	BLTI t0, -ELSZ+1, 1f     ; nv <= -ELSZ: supports
	ZZ dot_zz, wdvx, nrm
	cpx #$80
	bcs 1f                   ; negative
	stx tz
	ora tz
	beq 1f                   ; 0
	clc
	rts
1:
	lda moved
	beq 2f
	MULQ14 t0, nrm
	SUBAX W+VX
	MULQ14 t0, nrm+2
	SUBAX W+VY
2:
	sec
	rts

; Carry set if A:X (d) and t5 (m) are not of opposite signs (same_side).
same_side:
	sta tz
	stx tz+1
	lda tz+1
	bmi 1f
	ora tz
	beq 3f                   ; d = 0
	lda t5+1
	bmi 2f                   ; d > 0, m < 0
	sec
	rts
1:
	lda t5+1
	bmi 3f
	ora t5
	beq 3f
2:
	clc
	rts
3:
	sec
	rts

; n90 = the direction along the ground of cq: (-ny, nx).
cq_n90:
	ldy #C_NY
	lda (cq),y
	sta tz
	iny
	lda (cq),y
	sta tz+1
	NEGW n90, tz
	ldy #C_NX
	lda (cq),y
	sta n90+2
	iny
	lda (cq),y
	sta n90+3
	rts

; A:X = the contact point of cp from that of cq, along n90.
along_cq:
	ldy #C_TX
	sec
	lda (cp),y
	sbc (cq),y
	sta t0
	iny
	lda (cp),y
	sbc (cq),y
	sta t0+1
	ldy #C_TY
	sec
	lda (cp),y
	sbc (cq),y
	sta t1
	iny
	lda (cp),y
	sbc (cq),y
	sta t1+1
	ZZ dot_zz, t0, n90
	rts

; t1 = cq.l, then A:X = sat16( mul16( cq.l, t0 ) >> Y ).
lmul:
	sty moved
	ldy #C_L
	lda (cq),y
	sta t1
	iny
	lda (cq),y
	sta t1+1
	MUL16 t1, t0
	jsr copy_p
	ldy moved
1:
	lda L0+3
	cmp #$80
	ror L0+3
	ror L0+2
	ror L0+1
	ror L0
	dey
	bne 1b
	jmp sat_L0

; biztostalppont_uj: carry set if the wheel stays on cp turning around cq.
sure_new:
	jsr cq_n90
	ZZ dot_zz, W+VX, n90
	STAX t0                  ; vn
	ldy #10
	jsr lmul
	KM K_NEW
	ADDAX t5, W+OMEGA        ; m
	jsr along_cq
	jmp same_side

; biztostalppont_regi:
sure_old:
	jsr cq_n90
	ZZ dot_zz, wdvx, n90
	STAX t0                  ; dvn
	ldy #6
	jsr lmul
	KM K_OLD
	; m = tq + kmul, its sign in 17 bits:
	clc
	adc wtq
	sta t5
	txa
	adc wtq+1
	sta t5+1
	bvc 1f
	; overflowed: the sign is the other way, and it is not 0
	lda t5+1
	eor #$80
	ora #$01
	sta t5+1
1:
	jsr along_cq
	jmp same_side

; Carry set if the wheel W is faster than 1 m/s.
faster:
	BGEI W+VX, VEL_1MS, 1f
	BLTI W+VX, -VEL_1MS+1, 1f
	BGEI W+VY, VEL_1MS, 1f
	BLTI W+VY, -VEL_1MS+1, 1f
	MUL16 W+VX, W+VX
	jsr copy_p
	MUL16 W+VY, W+VY
	jsr copy_p1
	jsr add_L0
	; > VEL_1MS^2:
	lda #(((VEL_1MS*VEL_1MS) >> 16) & 0xff)
	cmp L0+2
	bcc 1f
	bne 2f
	lda #(((VEL_1MS*VEL_1MS) >> 8) & 0xff)
	cmp L0+1
	bcc 1f
	bne 2f
	lda #((VEL_1MS*VEL_1MS) & 0xff)
	cmp L0
	bcc 1f
2:
	clc
	rts
1:
	sec
	rts

; Ct0 = Ct1
copy_ct:
	ldx #CONTACT-1
1:
	lda Ct1,x
	sta Ct0,x
	dex
	bpl 1b
	rts

; Calls the test at the address in t6 for (Ct0, Ct1) and, if it holds,
; for (Ct1, Ct0): one contact is dropped if either does not hold.
sure_both:
	SETCP Ct0
	SETCQ Ct1
	jsr 1f
	bcs 2f
	lda #1
	sta nct
	jmp copy_ct
2:
	SETCP Ct1
	SETCQ Ct0
	jsr 1f
	bcs 3f
	lda #1
	sta nct
3:
	rts
1:
	jmp (t6)

; beallit for the wheel W with wdvx, wdvy and wtq.
wheel:
	; Its center in u:
	lda W+RX+1
	sta cx
	lda W+RX+2
	sta cx+1
	lda W+RX+3
	sta cx+2
	and #$80
	beq 1f
	lda #$ff
1:
	sta cx+3
	lda W+RY+1
	sta cy
	lda W+RY+2
	sta cy+1
	lda W+RY+3
	sta cy+2
	and #$80
	beq 1f
	lda #$ff
1:
	sta cy+3
	jsr contacts
	sta nct
	ldx #0
	cmp #2
	bne 1f
	inx
1:
	stx two
	lda nct
	JEQ wsupport
	SETCP Ct0
	SETCQ Ct1
	lda two
	bne 2f
	lda #0
	sta cq+1
2:
	jsr pushout
	lda two
	beq wsupport
	SETCP Ct1
	lda #0
	sta cq+1
	jsr pushout
	jsr faster
	bcc 3f
	LDIA t6, sure_new
	jmp 4f
3:
	LDIA t6, sure_old
4:
	jsr sure_both
	lda nct
	cmp #2
	bne wsupport
	SETCP Ct1
	lda #1
	jsr supports
	bcs wsupport
	lda #1
	sta nct
wsupport:
	lda nct
	beq wfree
	SETCP Ct0
	lda two
	jsr supports
	bcs 4f
	lda nct
	cmp #2
	bne 5f
	lda #1
	sta nct
	jsr copy_ct
	jmp 4f
5:
	lda #0
	sta nct
4:
	lda nct
	bne wheld
wfree:
	; Free: turns with its torque, moves with its velocity change.
	LDAX wtq
	KM K_FREE
	ADDAX W+OMEGA, W+OMEGA
	ADDW W+VX, W+VX, wdvx
	ADDW W+VY, W+VY, wdvy
	jmp move_w
wheld:
	cmp #2
	bne wroll
	; Held by two points:
	lda #0
	sta W+VX
	sta W+VX+1
	sta W+VY
	sta W+VY+1
	sta W+OMEGA
	sta W+OMEGA+1
	rts
wroll:
	; Rolls around the contact point:
	SETCQ Ct0
	jsr cq_n90
	ZZ dot_zz, W+VX, n90
	STAX t0                  ; vn
	ZZ dot_zz, wdvx, n90
	KM K_ROLL_T              ; dvn*ROLL_T
	; t = sat16( tq + it ):
	STAX t2
	ADDSAT t2, wtq, wtq+1
	STAX t2
	LDAX t0
	KM K_ROLL_W
	STAX t0
	LDAX t2
	KM K_ROLL_DW
	ADDAX W+OMEGA, t0
	LDAX W+OMEGA
	KM K_ROLL_V
	STAX t0                  ; speed
	MULQ14 t0, n90
	STAX W+VX
	MULQ14 t0, n90+2
	STAX W+VY
	jmp move_w

; --- The rider ----------------------------------------------------------------

; L0 = the 32 bits a - b, then A:X = sat16( L0 >> 8 ) or >> 4:
.macro DIFF8 a, b
	SUBL \a, \b
	jsr sat8_L0
.endm

.macro DIFF4 a, b
	SUBL \a, \b
	jsr sat4_L0
.endm

; vezeto_hatarolas: keeps the rider over the seat.
rider_limit:
	DIFF8 Bike+RIDER_X, Bike+BODY+RX
	STAX t3                  ; dx
	DIFF8 Bike+RIDER_Y, Bike+BODY+RY
	STAX t2                  ; dy; (t2, t3) = (dy, dx)
	ZZ dot_zz, t2, Sn        ; x = dx*Cs + dy*Sn
	STAX t0
	; y = dy*Cs + dx*(-Sn):
	ZZ dot_zz, t2, Cs
	STAX t1
	lda #0
	sta moved
	lda Bike+TURNED
	beq 1f
	NEGW t0, t0
1:
	; under = (y-SEAT_Y)*NY - (x-SEAT_X)*NX
	sec
	lda t1
	sbc #(SEAT_Y & 0xff)
	pha
	lda t1+1
	sbc #((SEAT_Y & 0xffff) >> 8)
	tax
	pla
	KM K_SEAT_NY
	STAX t4
	sec
	lda t0
	sbc #(SEAT_X & 0xff)
	pha
	lda t0+1
	sbc #((SEAT_X & 0xffff) >> 8)
	tax
	pla
	KM K_SEAT_NX
	SUBAX t4                 ; under
	lda t4+1
	bpl 2f
	LDAX t4
	KM K_SEAT_NX
	ADDAX t0, t0
	LDAX t4
	KM K_SEAT_NY
	SUBAX t1
	inc moved
2:
	BLTI t1, RIDER_TOP+1, 3f
	LDIW t1, RIDER_TOP
	inc moved
3:
	BGEI t0, RIDER_LEFT, 3f
	LDIW t0, RIDER_LEFT
	inc moved
3:
	BLTI t0, RIDER_RIGHT+1, 3f
	LDIW t0, RIDER_RIGHT
	inc moved
3:
	; Within the ellipse at the front top:
	lda t0+1
	JMI rlend
	ora t0
	JEQ rlend
	lda t1+1
	JMI rlend
	ora t1
	JEQ rlend
	LDAX t0
	KM K_ELLIPSE
	STAX t2
	MUL16 t2, t2
	jsr copy_p
	MUL16 t1, t1
	jsr copy_p1
	jsr add_L0
	; > RIDER_TOP^2:
	lda #(((RIDER_TOP*RIDER_TOP) >> 16) & 0xff)
	cmp L0+2
	bcc 5f
	JNE rlend
	lda #(((RIDER_TOP*RIDER_TOP) >> 8) & 0xff)
	cmp L0+1
	bcc 5f
	JNE rlend
	lda #((RIDER_TOP*RIDER_TOP) & 0xff)
	cmp L0
	JCS rlend
5:
	; Rare: back onto the ellipse, with a square root and divisions in C.
	lda L0+2
	sta __rc2
	lda L0+3
	sta __rc3
	lda L0
	ldx L0+1
	jsr isqrt32
	STAX t2                  ; d
	MOVW __rc4, t2
	LDIW __rc2, RIDER_TOP
	LDAX t0
	jsr muldiv
	STAX t0
	MOVW __rc4, t2
	LDIW __rc2, RIDER_TOP
	LDAX t1
	jsr muldiv
	STAX t1
	inc moved
rlend:
	lda moved
	bne 6f
	rts
6:
	lda Bike+TURNED
	beq 7f
	NEGW t0, t0
7:
	; rider = body + (x Cs - y Sn, x Sn + y Cs) << 8:
	ZZ dot_zz, t0, Cs        ; x*Cs + y*NSn
	STAX t2
	; x*Sn + y*Cs: (y, x).(Cs, Sn) as (Sn, Cs) . (x, y)
	ZZ dot_zz, Sn, t0
	STAX t3
	ldy #0
	jsr rider_from_body
	ldy #4
	MOVW t2, t3
	jmp rider_from_body

; Bike.rider(x or y, Y 0 or 4) = Bike.body.r + t2 << 8.
rider_from_body:
	ldx #0
	lda t2+1
	bpl 1f
	dex
1:
	lda Bike+BODY+RX,y
	sta Bike+RIDER_X,y
	clc
	lda Bike+BODY+RX+1,y
	adc t2
	sta Bike+RIDER_X+1,y
	lda Bike+BODY+RX+2,y
	adc t2+1
	sta Bike+RIDER_X+2,y
	txa
	adc Bike+BODY+RX+3,y
	sta Bike+RIDER_X+3,y
	rts

; beallitvezeto for two steps, with the gravity of two steps in gx2, gy2.
rider:
	jsr rider_limit
	; dir = (body-rider) >> 4 + the rest point (-Sn, Cs)*0.44:
	LDAX Sn
	KM K_RREST
	jsr sext_L1
	SUBL Bike+BODY+RX, Bike+RIDER_X
	jsr sar4_L0
	jsr sub_L0
	jsr sat_L0
	STAX t0
	LDAX Cs
	KM K_RREST
	jsr sext_L1
	SUBL Bike+BODY+RY, Bike+RIDER_Y
	jsr sar4_L0
	jsr add_L0
	jsr sat_L0
	STAX t1
	; d = (rider-body) >> 4:
	DIFF4 Bike+RIDER_X, Bike+BODY+RX
	STAX t2
	DIFF4 Bike+RIDER_Y, Bike+BODY+RY
	STAX t3
	; rel = rider_v - (body_v + (-dy, dx)*Oms):
	NEGW t4, t3
	MULQ14 t4, Oms
	ADDAX t4, Bike+BODY+VX
	SUBW t4, Bike+RIDER_VX, t4
	MULQ14 t2, Oms
	ADDAX t5, Bike+BODY+VY
	SUBW t5, Bike+RIDER_VY, t5
	; rider_v += dir*S - rel*F + g:
	LDAX t0
	KM K_RIDER_S
	STAX t2
	LDAX t4
	KM K_RIDER_F
	SUBAX t2
	ADDW t2, t2, gx2
	ADDW Bike+RIDER_VX, Bike+RIDER_VX, t2
	LDAX t1
	KM K_RIDER_S
	STAX t2
	LDAX t5
	KM K_RIDER_F
	SUBAX t2
	ADDW t2, t2, gy2
	ADDW Bike+RIDER_VY, Bike+RIDER_VY, t2
	; rider += rider_v << 3:
	LDAX Bike+RIDER_VX
	jsr shl3_L1
	ADDL1 Bike+RIDER_X
	LDAX Bike+RIDER_VY
	jsr shl3_L1
	ADDL1 Bike+RIDER_Y
	rts

; L1 = A:X << 3, sign extended.
shl3_L1:
	jsr shl2_L1
	asl L1
	rol L1+1
	rol L1+2
	rol L1+3
	rts

; --- A step -------------------------------------------------------------------

; The 32 bits at d += m_p, -= m_p:
.macro ADDP d
	clc
	lda \d
	adc m_p
	sta \d
	lda \d+1
	adc m_p+1
	sta \d+1
	lda \d+2
	adc m_p+2
	sta \d+2
	lda \d+3
	adc m_p+3
	sta \d+3
.endm

.macro SUBP d
	sec
	lda \d
	sbc m_p
	sta \d
	lda \d+1
	sbc m_p+1
	sta \d+1
	lda \d+2
	sbc m_p+2
	sta \d+2
	lda \d+3
	sbc m_p+3
	sta \d+3
.endm

; A:X = sat16( ((body - W) >> 4) + (A:X << 4) ) for the coordinate at Y
; (RX or RY), taken as sat16( (body - W + (A:X << 8)) >> 4 ):
spring_len:
	sta tz
	stx tz+1
	sec
	lda Bike+BODY,y
	sbc W,y
	sta L0
	lda Bike+BODY+1,y
	sbc W+1,y
	sta L0+1
	lda Bike+BODY+2,y
	sbc W+2,y
	sta L0+2
	lda Bike+BODY+3,y
	sbc W+3,y
	sta L0+3
	clc
	lda L0+1
	adc tz
	sta L0+1
	lda L0+2
	adc tz+1
	sta L0+2
	lda tz+1
	and #$80
	beq 1f
	lda #$ff
1:
	adc L0+3
	sta L0+3
	jmp sat4_L0

; A:X = sat16( (W - body) >> 8 ) for the coordinate at Y:
lever:
	sec
	lda W,y
	sbc Bike+BODY,y
	lda W+1,y
	sbc Bike+BODY+1,y
	sta L0
	lda W+2,y
	sbc Bike+BODY+2,y
	sta L0+1
	lda W+3,y
	sbc Bike+BODY+3,y
	sta L0+2
	jmp sat24

; A:X = sat16( body.v - W.v + A:X ) and sat16( body.v - W.v - A:X ), Y 0
; for x and 2 for y, in 24 bits:
vsum:
	jsr vdiff
	clc
	lda L0
	adc tz
	sta L0
	lda L0+1
	adc tz+1
	sta L0+1
	lda L0+2
	adc L1
	sta L0+2
	jmp sat24

vsub:
	jsr vdiff
	sec
	lda L0
	sbc tz
	sta L0
	lda L0+1
	sbc tz+1
	sta L0+1
	lda L0+2
	sbc L1
	sta L0+2
	jmp sat24

; tz = A:X, L1 its sign as a byte, L0[0..2] = body.v - W.v.
vdiff:
	sta tz
	stx tz+1
	txa
	and #$80
	beq 1f
	lda #$ff
1:
	sta L1
	sec
	lda Bike+BODY+VX,y
	sbc W+VX,y
	sta L0
	lda Bike+BODY+VX+1,y
	sbc W+VX+1,y
	sta L0+1
	; The sign of the 17 bits: that of the result, or the other if it
	; overflowed.
	bvs 2f
	and #$80
	beq 4f
	lda #$ff
	bne 4f
2:
	and #$80
	beq 3f
	lda #0
	beq 4f
3:
	lda #$ff
4:
	sta L0+2
	rts

; A = |clamp( A:X >> 4, -127, 127 )|, for the squares of the high bits of k.
high_bits:
	sta tz
	stx tz+1
	ldy #4
1:
	lda tz+1
	cmp #$80
	ror tz+1
	ror tz
	dey
	bne 1b
	lda tz+1
	bmi 3f
	bne 2f                   ; 256 and more
	lda tz
	cmp #128
	bcs 2f
	rts
2:
	lda #127
	rts
3:
	cmp #$ff
	bne 2b                   ; -257 and less
	lda tz
	cmp #$81
	bcc 2b                   ; -128 and less
	eor #$ff
	clc
	adc #1
	rts

; The forces between the wheel W and the body (erokszamitasa), with the
; anchor of its spring at (t6, t7) from the body and its torque in wtq:
; its velocity change into wdvx, wdvy, the torques into ts and tf.
forces:
	; The spring:
	LDAX t6
	ldy #RX
	jsr spring_len
	STAX t0                  ; gx
	LDAX t7
	ldy #RY
	jsr spring_len
	STAX t1                  ; gy
	LDAX t0
	KM K_SPRING_W
	STAX wdvx
	LDAX t1
	KM K_SPRING_W
	STAX wdvy
	MUL16 t6, t1
	ADDP ts
	MUL16 t7, t0
	SUBP ts
	; The damping:
	ldy #RX
	jsr lever
	STAX t2                  ; kx
	ldy #RY
	jsr lever
	STAX t3                  ; ky
	MULQ10 t3, Oms
	ldy #0
	jsr vsub
	STAX t4                  ; relx
	MULQ10 t2, Oms
	ldy #2
	jsr vsum
	STAX t5                  ; rely
	LDAX t4
	KM K_FRIC_W
	ADDAX wdvx, wdvx
	LDAX t5
	KM K_FRIC_W
	ADDAX wdvy, wdvy
	MUL16 t2, t5
	ADDP tf
	MUL16 t3, t4
	SUBP tf
	; The force of the wheel's torque on the axle:
	lda wtq
	ora wtq+1
	bne 1f
	rts
1:
	; d^2 >> 13 from the squares of the high bits of k, at most 255:
	LDAX t2
	jsr high_bits
	asl a
	tay
	lda sqr_lo,y
	sta t6
	lda sqr_hi,y
	sta t6+1
	LDAX t3
	jsr high_bits
	asl a
	tay
	clc
	lda sqr_lo,y
	adc t6
	sta t6
	lda sqr_hi,y
	adc t6+1
	; >> 5:
	ldx #5
2:
	lsr a
	ror t6
	dex
	bne 2b
	tax
	beq 3f
	lda #255
	sta t6
3:
	lda t6
	asl a
	tay
	bcs 4f
	lda recip,y
	sta t6
	lda recip+1,y
	sta t6+1
	jmp 5f
4:
	lda recip+256,y
	sta t6
	lda recip+257,y
	sta t6+1
5:
	; tr = KMUL( sat16( tq*rec >> 8 ), REACT ):
	MUL16 wtq, t6
	jsr copy_p
	jsr sat8_L0
	KM K_REACT
	STAX t6
	MULQ14 t3, t6
	ADDAX wdvx, wdvx
	MULQ14 t2, t6
	SUBAX wdvy
	rts

; The brake torque of the wheel W, Y the offset of its dbrake, into wtq.
brake:
	; da = (W.alfa - (body.alfa + dbrake)) >> 8, as 16 bits:
	clc
	lda Bike+BODY+ALFA
	adc Bike,y
	sta L0
	lda Bike+BODY+ALFA+1
	adc Bike+1,y
	sta L0+1
	lda Bike+BODY+ALFA+2
	adc Bike+2,y
	sta L0+2
	sec
	lda W+ALFA
	sbc L0
	lda W+ALFA+1
	sbc L0+1
	sta t1
	lda W+ALFA+2
	sbc L0+2
	sta t1+1
	; dw = clamp( W.omega - body.omega, +-16383 ):
	SUBW t2, W+OMEGA, Bike+BODY+OMEGA
	BLTI t2, 16384, 1f
	LDIW t2, 16383
1:
	BGEI t2, -16383, 2f
	LDIW t2, -16383
2:
	; tq = sat16( -da' - dw' ):
	LDAX t1
	KM K_BRAKE_A
	jsr sext_L0
	LDAX t2
	KM K_BRAKE_W
	jsr sext_L1
	jsr add_L0
	sec
	lda #0
	sbc L0
	sta L0
	lda #0
	sbc L0+1
	sta L0+1
	lda #0
	sbc L0+2
	sta L0+2
	lda #0
	sbc L0+3
	sta L0+3
	jsr sat_L0
	STAX wtq
	rts

; The velocity change of the body from those of the wheels, the axis at Y
; (0 x, 2 y): -1/20 of their sum.
body_dv:
	clc
	lda dvx,y
	adc dvx+2,y
	sta tz
	lda dvx+1,y
	adc dvx+3,y
	sta tz+1
	jsr satv
	KM K_TWENTIETH
	NEGAX t0
	rts

; uint8_t ph_step( uint8_t input ): 0 if the head hit the ground.
#ifndef __NES__
.globl ph_step
ph_step:
	sta inp
#endif
step:
	jsr angle
	LDAX Bike+BODY+OMEGA
	KM K_OMS
	STAX Oms

	; The start of braking:
	lda inp
	and #IN_BRAKE
	beq 1f
	lda Bike+BRAKE_WAS
	bne 1f
	ldx #0
	ldy #4
	jsr dbrake
	ldx #(WHEEL1-WHEEL0)
	ldy #4
	jsr dbrake
1:
	lda inp
	and #IN_BRAKE
	sta Bike+BRAKE_WAS

	; The anchors of the springs:
	LDAX Cs
	KM K_K_X
	STAX t0                  ; a
	LDAX Sn
	KM K_K_Y
	STAX t1                  ; b
	LDAX Sn
	KM K_K_X
	STAX t2                  ; c
	LDAX Cs
	KM K_K_Y
	STAX t3                  ; d
	ADDW gsx+2, t0, t1
	SUBW gsy+2, t2, t3
	SUBW gsx, t1, t0
	NEGW gsy, t2
	SUBW gsy, gsy, t3

	lda #0
	ldx #7
2:
	sta ts,x
	dex
	bpl 2b
	lda #0
	jsr wheel_forces
	lda #2
	jsr wheel_forces
	ldy #0
	jsr body_dv
	MOVW dvbx, t0
	ldy #4
	jsr body_dv
	MOVW dvby, t0
	; dwb = -sat16( ts >> 10 )*SPRING_T - sat16( tf >> 10 )*FRIC_T:
	ldx #0
	jsr sat10
	KM K_SPRING_T
	NEGAX dwb
	ldx #4
	jsr sat10
	KM K_FRIC_T
	SUBAX dwb
	jsr volts
	jsr gravity

	inc Bike+STEPS
	lda Bike+STEPS
	and #1
	sta odd
	beq 3f
	lda gx
	asl a
	sta gx2
	lda gx+1
	rol a
	sta gx2+1
	lda gy
	asl a
	sta gy2
	lda gy+1
	rol a
	sta gy2+1
	jsr rider
3:
	; The body:
	ADDSAT Bike+BODY+OMEGA, dwb, dwb+1
	STAX Bike+BODY+OMEGA
	ADDW t0, dvbx, gx
	ADDW Bike+BODY+VX, Bike+BODY+VX, t0
	ADDW t0, dvby, gy
	ADDW Bike+BODY+VY, Bike+BODY+VY, t0
	ldy #BODY
	jsr circle_in
	jsr move_w
	ldy #BODY
	jsr circle_out

	; The wheels:
	lda #0
	jsr wheel_move
	lda #2
	jsr wheel_move

	; The head (szamitfejr), checked every other step:
	lda odd
	beq 4f
	lda #1
	rts
4:
	jsr angle
	LDAX Cs
	KM K_H_X
	STAX t0                  ; hc
	LDAX Sn
	KM K_H_X
	STAX t1                  ; hs
	lda Bike+TURNED
	bne 5f
	NEGW t0, t0
	NEGW t1, t1
5:
	LDAX Sn
	KM K_H_Y
	SUBAX t0
	LDAX Cs
	KM K_H_Y
	ADDAX t1, t1
	; head = rider + (t0, t1) << 8, and its center in u:
	MOVW t2, t0
	ldy #(HEAD_X-RIDER_X)
	jsr head_from_rider
	MOVW t2, t1
	ldy #(HEAD_Y-RIDER_X)
	jsr head_from_rider
	ldx #3
6:
	lda Bike+HEAD_X+1,x
	sta cx,x
	lda Bike+HEAD_Y+1,x
	sta cy,x
	dex
	bpl 6b
	lda Bike+HEAD_X+3
	and #$80
	beq 7f
	lda #$ff
7:
	sta cx+3
	lda Bike+HEAD_Y+3
	and #$80
	beq 8f
	lda #$ff
8:
	sta cy+3
	jsr touches
	eor #1
	rts

; Bike.head(x or y at Y from RIDER_X) = the rider + t2 << 8 (the rider's
; coordinate at Y-12).
head_from_rider:
	ldx #0
	lda t2+1
	bpl 1f
	dex
1:
	lda Bike+RIDER_X-(HEAD_X-RIDER_X),y
	sta Bike+RIDER_X,y
	clc
	lda Bike+RIDER_X+1-(HEAD_X-RIDER_X),y
	adc t2
	sta Bike+RIDER_X+1,y
	lda Bike+RIDER_X+2-(HEAD_X-RIDER_X),y
	adc t2+1
	sta Bike+RIDER_X+2,y
	txa
	adc Bike+RIDER_X+3-(HEAD_X-RIDER_X),y
	sta Bike+RIDER_X+3,y
	rts

; dbrake[k] = wheel[k].alfa - body.alfa, X the offset of the wheel from
; WHEEL0, for 4 bytes (Y).
dbrake:
	stx tz
	txa
	lsr a
	lsr a
	; X/18*4: the wheel 0 or 1
	beq 1f
	lda #4
1:
	tay
	ldx tz
	sec
	lda Bike+WHEEL0+ALFA,x
	sbc Bike+BODY+ALFA
	sta Bike+DBRAKE,y
	lda Bike+WHEEL0+ALFA+1,x
	sbc Bike+BODY+ALFA+1
	sta Bike+DBRAKE+1,y
	lda Bike+WHEEL0+ALFA+2,x
	sbc Bike+BODY+ALFA+2
	sta Bike+DBRAKE+2,y
	lda Bike+WHEEL0+ALFA+3,x
	sbc Bike+BODY+ALFA+3
	sta Bike+DBRAKE+3,y
	rts

; A:X = sat16( (ts or tf at X) >> 10 ):
sat10:
	lda ts+1,x
	sta L0
	lda ts+2,x
	sta L0+1
	lda ts+3,x
	sta L0+2
	and #$80
	beq 1f
	lda #$ff
1:
	sta L0+3
	lda L0+3
	cmp #$80
	ror L0+3
	ror L0+2
	ror L0+1
	ror L0
	lda L0+3
	cmp #$80
	ror L0+3
	ror L0+2
	ror L0+1
	ror L0
	jmp sat_L0

; The torque and forces of wheel A (0 or 2, its index in the int16 arrays).
wheel_forces:
	sta kk
	asl a
	asl a
	asl a
	clc
	adc kk                   ; 18*k/2 = 9*index
	tay
	jsr circle_in_wheel
	; Gas, then brake:
	lda #0
	sta wtq
	sta wtq+1
	lda inp
	and #IN_GAS
	beq 3f
	lda Bike+TURNED
	beq 1f
	lda kk
	bne 3f
	BLTI W+OMEGA, -WHEEL_MAXW+1, 3f
	LDIW wtq, -GAS_TQ
	jmp 3f
1:
	lda kk
	beq 3f
	BGEI W+OMEGA, WHEEL_MAXW, 3f
	LDIW wtq, GAS_TQ
3:
	lda inp
	and #IN_BRAKE
	beq 4f
	lda kk
	asl a
	clc
	adc #DBRAKE
	tay
	jsr brake
4:
	ldx kk
	lda wtq
	sta tq,x
	lda wtq+1
	sta tq+1,x
	lda gsx,x
	sta t6
	lda gsx+1,x
	sta t6+1
	lda gsy,x
	sta t7
	lda gsy+1,x
	sta t7+1
	jsr forces
	ldx kk
	lda wdvx
	sta dvx,x
	lda wdvx+1
	sta dvx+1,x
	lda wdvy
	sta dvy,x
	lda wdvy+1
	sta dvy+1,x
	rts

; W = wheel at Y (9*index: 0 or 18).
circle_in_wheel:
	tya
	clc
	adc #WHEEL0
	tay
	jmp circle_in

; Moves wheel A (0 or 2) with its forces and gravity (beallit).
wheel_move:
	sta kk
	asl a
	asl a
	asl a
	clc
	adc kk
	pha
	tay
	jsr circle_in_wheel
	ldx kk
	clc
	lda dvx,x
	adc gx
	sta wdvx
	lda dvx+1,x
	adc gx+1
	sta wdvx+1
	clc
	lda dvy,x
	adc gy
	sta wdvy
	lda dvy+1,x
	adc gy+1
	sta wdvy+1
	lda tq,x
	sta wtq
	lda tq+1,x
	sta wtq+1
	jsr wheel
	pla
	clc
	adc #WHEEL0
	tay
	jmp circle_out

; The volts of a step (ugras).
volts:
	MOVW oldomega, Bike+BODY+OMEGA
	lda inp
	and #(IN_VOLT_RIGHT | IN_VOLT_LEFT)
	sta t0
	; The end of a volt to the right:
	lda Bike+VOLT
	beq 7f
	lda t0
	bne 1f
	dec Bike+VOLT
	bne 7f
1:
	clc
	lda Bike+BODY+OMEGA
	adc #(LOKET & 0xff)
	sta Bike+BODY+OMEGA
	lda Bike+BODY+OMEGA+1
	adc #(LOKET >> 8)
	sta Bike+BODY+OMEGA+1
	BLT Bike+VOLT_OMEGA, Bike+BODY+OMEGA, 2f
	jmp 3f
2:
	MOVW Bike+BODY+OMEGA, Bike+VOLT_OMEGA
3:
	BLTI Bike+BODY+OMEGA, 1, 4f
	sec
	lda Bike+BODY+OMEGA
	sbc #(OMEGAVALT & 0xff)
	sta Bike+BODY+OMEGA
	lda Bike+BODY+OMEGA+1
	sbc #(OMEGAVALT >> 8)
	sta Bike+BODY+OMEGA+1
	bpl 4f
	lda #0
	sta Bike+BODY+OMEGA
	sta Bike+BODY+OMEGA+1
4:
	lda #0
	sta Bike+VOLT
7:
	; The end of a volt to the left:
	lda Bike+VOLT+1
	beq 7f
	lda t0
	bne 1f
	dec Bike+VOLT+1
	bne 7f
1:
	sec
	lda Bike+BODY+OMEGA
	sbc #(LOKET & 0xff)
	sta Bike+BODY+OMEGA
	lda Bike+BODY+OMEGA+1
	sbc #(LOKET >> 8)
	sta Bike+BODY+OMEGA+1
	BLT Bike+BODY+OMEGA, Bike+VOLT_OMEGA+2, 2f
	jmp 3f
2:
	MOVW Bike+BODY+OMEGA, Bike+VOLT_OMEGA+2
3:
	lda Bike+BODY+OMEGA+1
	bpl 4f
	clc
	lda Bike+BODY+OMEGA
	adc #(OMEGAVALT & 0xff)
	sta Bike+BODY+OMEGA
	lda Bike+BODY+OMEGA+1
	adc #(OMEGAVALT >> 8)
	sta Bike+BODY+OMEGA+1
	bmi 4f
	lda #0
	sta Bike+BODY+OMEGA
	sta Bike+BODY+OMEGA+1
4:
	lda #0
	sta Bike+VOLT+1
7:
	; New volts:
	lda inp
	and #IN_VOLT_RIGHT
	beq 1f
	lda #VOLT_STEPS
	sta Bike+VOLT
	MOVW Bike+VOLT_OMEGA, Bike+BODY+OMEGA
	sec
	lda Bike+BODY+OMEGA
	sbc #(LOKET & 0xff)
	sta Bike+BODY+OMEGA
	lda Bike+BODY+OMEGA+1
	sbc #(LOKET >> 8)
	sta Bike+BODY+OMEGA+1
1:
	lda inp
	and #IN_VOLT_LEFT
	beq 1f
	lda #VOLT_STEPS
	sta Bike+VOLT+1
	MOVW Bike+VOLT_OMEGA+2, Bike+BODY+OMEGA
	clc
	lda Bike+BODY+OMEGA
	adc #(LOKET & 0xff)
	sta Bike+BODY+OMEGA
	lda Bike+BODY+OMEGA+1
	adc #(LOKET >> 8)
	sta Bike+BODY+OMEGA+1
1:
	lda t0
	bne 2f
	rts
2:
	; The rider gets the change of the body's turning:
	SUBW t1, Bike+BODY+OMEGA, oldomega
	LDAX t1
	KM K_OMS
	STAX t1                  ; dw
	DIFF4 Bike+RIDER_X, Bike+BODY+RX
	STAX t2
	DIFF4 Bike+RIDER_Y, Bike+BODY+RY
	STAX t3
	NEGW t3, t3
	MULQ14 t3, t1
	ADDAX Bike+RIDER_VX, Bike+RIDER_VX
	MULQ14 t2, t1
	ADDAX Bike+RIDER_VY, Bike+RIDER_VY
	rts

; Gravity, with its fraction carried over, into gx, gy.
gravity:
	lda #G_INT
	sta t0
	lda #0
	sta t0+1
	clc
	lda Bike+GFRAC
	adc #G_FRAC
	sta Bike+GFRAC
	bcc 1f
	inc t0
1:
	lda #0
	sta gx
	sta gx+1
	sta gy
	sta gy+1
	lda Bike+GRAVITY
	bne 2f
	MOVW gy, t0              ; up
	rts
2:
	cmp #2
	bne 4f
	NEGW gx, t0              ; left
	rts
4:
	cmp #3
	bne 5f
	MOVW gx, t0              ; right
	rts
5:
	NEGW gy, t0              ; down
	rts

; void ph_init( int32_t x, int32_t y ): x in A:X:__rc2:__rc3, y in
; __rc4..__rc7, the start of the left wheel in F.
#ifndef __NES__
.globl ph_init
ph_init:
	jsr init_args
#endif
init:
	ldx #BIKE_SIZE-1
	lda #0
1:
	sta Bike,x
	dex
	bpl 1b
	lda #1
	sta Bike+GRAVITY         ; down
	ldx #3
2:
	lda L0,x
	sta Bike+WHEEL0+RX,x
	lda L1,x
	sta Bike+WHEEL0+RY,x
	sta Bike+WHEEL1+RY,x
	dex
	bpl 2b
	ldy #(WHEEL1+RX)
	LDIW t0, F_WHEELBASE & 0xffff
	LDIW t1, F_WHEELBASE >> 16
	jsr init_from_l0
	ldy #(BODY+RX)
	LDIW t0, F_BODY_X & 0xffff
	LDIW t1, F_BODY_X >> 16
	jsr init_from_l0
	ldy #RIDER_X
	jsr init_from_l0
	MOVW L0, L1
	MOVW L0+2, L1+2
	ldy #(BODY+RY)
	LDIW t0, F_BODY_Y & 0xffff
	LDIW t1, F_BODY_Y >> 16
	jsr init_from_l0
	ldy #RIDER_Y
	LDIW t0, F_RIDER_Y & 0xffff
	LDIW t1, F_RIDER_Y >> 16
	jsr init_from_l0
	ldx #3
3:
	lda Bike+RIDER_X,x
	sta Bike+HEAD_X,x
	lda Bike+RIDER_Y,x
	sta L0,x
	dex
	bpl 3b
	ldy #HEAD_Y
	LDIW t0, F_HEAD_Y & 0xffff
	LDIW t1, F_HEAD_Y >> 16
	jmp init_from_l0

; The 32 bits of the bike at Y = L0 + (t0, t1).
init_from_l0:
	clc
	lda L0
	adc t0
	sta Bike,y
	lda L0+1
	adc t0+1
	sta Bike+1,y
	lda L0+2
	adc t1
	sta Bike+2,y
	lda L0+3
	adc t1+1
	sta Bike+3,y
	rts

.section .text.ph_entry,"ax",@progbits

#ifdef __NES__
.globl ph_step
ph_step:
	sta inp
	jsr bank_in
	jsr step
	sta tz
	jsr bank_out
	lda tz
	rts

.globl ph_init
ph_init:
	jsr init_args
	jsr bank_in
	jsr init
	; fall through

; Maps back the bank that was at $8000 before bank_in.
bank_out:
	lda pbank
	jmp set_prg_8000

; Maps the bank of the code at $8000, keeping the one that was there.
bank_in:
	jsr get_prg_8000
	sta pbank
	lda #PHYS_BANK
	jmp set_prg_8000
#endif

; The arguments of ph_init into L0 and L1.
init_args:
	sta L0
	stx L0+1
	lda __rc2
	sta L0+2
	lda __rc3
	sta L0+3
	lda __rc4
	sta L1
	lda __rc5
	sta L1+1
	lda __rc6
	sta L1+2
	lda __rc7
	sta L1+3
	rts

; void ph_turn( void )
.globl ph_turn
ph_turn:
	lda Bike+TURNED
	eor #1
	sta Bike+TURNED
	rts

.section .rodata.physics,"a",@progbits
; Indexed by twice the number of the constant:
#define X(n) C_##n##_M, 0,
kc_m: .byte KLIST 0
#undef X
#define KENT2(e) kent_##e
#define KENT(e) KENT2(e)
#define X(n) KENT(C_##n##_E),
kc_ent: .short KLIST 0
#undef X
; sin( 2*pi*i/256 )*16384, with the first value repeated at the end:
sintab:
	.short 0, 402, 804, 1205, 1606, 2006, 2404, 2801
	.short 3196, 3590, 3981, 4370, 4756, 5139, 5520, 5897
	.short 6270, 6639, 7005, 7366, 7723, 8076, 8423, 8765
	.short 9102, 9434, 9760, 10080, 10394, 10702, 11003, 11297
	.short 11585, 11866, 12140, 12406, 12665, 12916, 13160, 13395
	.short 13623, 13842, 14053, 14256, 14449, 14635, 14811, 14978
	.short 15137, 15286, 15426, 15557, 15679, 15791, 15893, 15986
	.short 16069, 16143, 16207, 16261, 16305, 16340, 16364, 16379
	.short 16384, 16379, 16364, 16340, 16305, 16261, 16207, 16143
	.short 16069, 15986, 15893, 15791, 15679, 15557, 15426, 15286
	.short 15137, 14978, 14811, 14635, 14449, 14256, 14053, 13842
	.short 13623, 13395, 13160, 12916, 12665, 12406, 12140, 11866
	.short 11585, 11297, 11003, 10702, 10394, 10080, 9760, 9434
	.short 9102, 8765, 8423, 8076, 7723, 7366, 7005, 6639
	.short 6270, 5897, 5520, 5139, 4756, 4370, 3981, 3590
	.short 3196, 2801, 2404, 2006, 1606, 1205, 804, 402
	.short 0, -402, -804, -1205, -1606, -2006, -2404, -2801
	.short -3196, -3590, -3981, -4370, -4756, -5139, -5520, -5897
	.short -6270, -6639, -7005, -7366, -7723, -8076, -8423, -8765
	.short -9102, -9434, -9760, -10080, -10394, -10702, -11003, -11297
	.short -11585, -11866, -12140, -12406, -12665, -12916, -13160, -13395
	.short -13623, -13842, -14053, -14256, -14449, -14635, -14811, -14978
	.short -15137, -15286, -15426, -15557, -15679, -15791, -15893, -15986
	.short -16069, -16143, -16207, -16261, -16305, -16340, -16364, -16379
	.short -16384, -16379, -16364, -16340, -16305, -16261, -16207, -16143
	.short -16069, -15986, -15893, -15791, -15679, -15557, -15426, -15286
	.short -15137, -14978, -14811, -14635, -14449, -14256, -14053, -13842
	.short -13623, -13395, -13160, -12916, -12665, -12406, -12140, -11866
	.short -11585, -11297, -11003, -10702, -10394, -10080, -9760, -9434
	.short -9102, -8765, -8423, -8076, -7723, -7366, -7005, -6639
	.short -6270, -5897, -5520, -5139, -4756, -4370, -3981, -3590
	.short -3196, -2801, -2404, -2006, -1606, -1205, -804, -402
	.short 0
; 2^18/sqrt( 16384 + (i+0.5)*512 ), see normalize:
rsqrt:
	.short 2032, 2002, 1972, 1944, 1918, 1892, 1867, 1843
	.short 1820, 1798, 1777, 1757, 1737, 1718, 1699, 1681
	.short 1664, 1647, 1630, 1614, 1599, 1584, 1569, 1555
	.short 1541, 1528, 1515, 1502, 1489, 1477, 1465, 1454
	.short 1443, 1431, 1421, 1410, 1400, 1390, 1380, 1370
	.short 1361, 1351, 1342, 1333, 1325, 1316, 1308, 1299
	.short 1291, 1283, 1275, 1268, 1260, 1253, 1246, 1239
	.short 1231, 1225, 1218, 1211, 1205, 1198, 1192, 1186
	.short 1179, 1173, 1167, 1161, 1156, 1150, 1144, 1139
	.short 1133, 1128, 1123, 1117, 1112, 1107, 1102, 1097
	.short 1092, 1087, 1083, 1078, 1073, 1069, 1064, 1060
	.short 1055, 1051, 1047, 1042, 1038, 1034, 1030, 1026
	.short 1022, 1018, 1014, 1010, 1006, 1003, 999, 995
	.short 992, 988, 984, 981, 977, 974, 971, 967
	.short 964, 960, 957, 954, 951, 948, 944, 941
	.short 938, 935, 932, 929, 926, 923, 920, 917
	.short 914, 912, 909, 906, 903, 901, 898, 895
	.short 892, 890, 887, 885, 882, 880, 877, 875
	.short 872, 870, 867, 865, 862, 860, 858, 855
	.short 853, 851, 848, 846, 844, 842, 839, 837
	.short 835, 833, 831, 829, 826, 824, 822, 820
	.short 818, 816, 814, 812, 810, 808, 806, 804
	.short 802, 800, 799, 797, 795, 793, 791, 789
	.short 787, 786, 784, 782, 780, 778, 777, 775
	.short 773, 771, 770, 768, 766, 765, 763, 761
	.short 760, 758, 757, 755, 753, 752, 750, 749
	.short 747, 745, 744, 742, 741, 739, 738, 736
	.short 735, 733, 732, 731, 729, 728, 726, 725
	.short 723, 722, 721, 719, 718, 716, 715, 714
	.short 712, 711, 710, 708, 707, 706, 704, 703
	.short 702, 701, 699, 698, 697, 695, 694, 693
	.short 692, 691, 689, 688, 687, 686, 684, 683
	.short 682, 681, 680, 679, 677, 676, 675, 674
	.short 673, 672, 671, 669, 668, 667, 666, 665
	.short 664, 663, 662, 661, 660, 659, 657, 656
	.short 655, 654, 653, 652, 651, 650, 649, 648
	.short 647, 646, 645, 644, 643, 642, 641, 640
	.short 639
; 2^17/(max( i, 16 )+0.5), see the force of the wheel torque:
recip:
	.short 7944, 7944, 7944, 7944, 7944, 7944, 7944, 7944
	.short 7944, 7944, 7944, 7944, 7944, 7944, 7944, 7944
	.short 7944, 7490, 7085, 6722, 6394, 6096, 5825, 5578
	.short 5350, 5140, 4946, 4766, 4599, 4443, 4297, 4161
	.short 4033, 3913, 3799, 3692, 3591, 3495, 3404, 3318
	.short 3236, 3158, 3084, 3013, 2945, 2881, 2819, 2759
	.short 2703, 2648, 2595, 2545, 2497, 2450, 2405, 2362
	.short 2320, 2280, 2241, 2203, 2166, 2131, 2097, 2064
	.short 2032, 2001, 1971, 1942, 1913, 1886, 1859, 1833
	.short 1808, 1783, 1759, 1736, 1713, 1691, 1670, 1649
	.short 1628, 1608, 1589, 1570, 1551, 1533, 1515, 1498
	.short 1481, 1464, 1448, 1432, 1417, 1402, 1387, 1372
	.short 1358, 1344, 1331, 1317, 1304, 1291, 1279, 1266
	.short 1254, 1242, 1231, 1219, 1208, 1197, 1186, 1176
	.short 1165, 1155, 1145, 1135, 1125, 1116, 1106, 1097
	.short 1088, 1079, 1070, 1061, 1053, 1044, 1036, 1028
	.short 1020, 1012, 1004, 997, 989, 982, 975, 967
	.short 960, 953, 946, 940, 933, 926, 920, 913
	.short 907, 901, 895, 889, 883, 877, 871, 865
	.short 859, 854, 848, 843, 838, 832, 827, 822
	.short 817, 812, 807, 802, 797, 792, 787, 783
	.short 778, 773, 769, 764, 760, 755, 751, 747
	.short 743, 738, 734, 730, 726, 722, 718, 714
	.short 710, 707, 703, 699, 695, 692, 688, 684
	.short 681, 677, 674, 670, 667, 664, 660, 657
	.short 654, 650, 647, 644, 641, 638, 635, 632
	.short 629, 626, 623, 620, 617, 614, 611, 608
	.short 605, 603, 600, 597, 594, 592, 589, 586
	.short 584, 581, 579, 576, 574, 571, 569, 566
	.short 564, 561, 559, 557, 554, 552, 550, 547
	.short 545, 543, 541, 538, 536, 534, 532, 530
	.short 527, 525, 523, 521, 519, 517, 515, 513
