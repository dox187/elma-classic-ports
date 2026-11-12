; Exact signed16 x16 ->32 via Q(a+b)-Q(abs(a-b)), Q(n)=floor(n*n/4).
; SDCC stack ABI0 returns HLDE. Magnitudes are0..32768; Q(65536) is a
; constant. The 256KiB table occupies complete MBC5 banks20..35 at4000.
; Code stays in ROM0. Restore physical ROMB0 before returning; CURRENT_BANK
; stays the logical caller throughout data reads. Entry requires ROMB1=0, as
; guaranteed by the far readers. Interrupt handlers are ROM0 and never bank.
.module riding_mul_fast
.area _CODE
_riding_mul16::
 ldhl sp,#2
 ld a,(hl+)
 or a,(hl)
 jp z,math_mul16_zero
 inc hl
 ld a,(hl+)
 or a,(hl)
 jp z,math_mul16_zero
 ldhl sp,#2
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
math_mul16_loaded:
 ld a,(#__current_bank)
 push af
 ld a,d
 xor a,b
 push af
 bit 7,d
 jr z,010$
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
010$:
 bit 7,b
 jr z,020$
 xor a
 sub a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
020$:
 ld a,b
 or a,a
 jp z,081$
 ld a,d
 or a,a
 jp z,080$
 ; Exact power-of-two and square shortcuts after the one-row narrow path.
 ld a,b
 cp a,#64
 jr nz,021$
 ld a,c
 or a,a
 jp z,071$
021$:
 ld a,d
 cp a,#64
 jr nz,022$
 ld a,e
 or a,a
 jp z,070$
022$:
 ld a,d
 cp a,b
 jr nz,023$
 ld a,e
 cp a,c
 jp z,073$
023$:
 ; After old u8/axis/square paths, a magnitude in256..511 is256+lo.
 dec b
 jr z,082$
 inc b
 dec d
 jr z,083$
 inc d
 ld a,e
 sub a,c
 ld l,a
 ld a,d
 sbc a,b
 ld h,a
 jr nc,030$
 xor a
 sub a,l
 ld l,a
 ld a,#0
 sbc a,h
 ld h,a
030$:
 push hl
 ld a,e
 add a,c
 ld l,a
 ld a,d
 adc a,b
 ld h,a
 jr c,040$
 call 100$
 jr 050$
040$:
 ld hl,#0x4000
 ld de,#0
050$:
 ; Difference index goes into BC; save the32-bit Q(sum) on the stack.
 pop bc
 push hl
 push de
 ld h,b
 ld l,c
 call 100$
 ld b,h
 ld c,l
 ldhl sp,#0
 ld a,(hl)
 sub a,e
 ld e,a
 inc hl
 ld a,(hl)
 sbc a,d
 ld d,a
 inc hl
 ld a,(hl)
 sbc a,c
 ld c,a
 inc hl
 ld a,(hl)
 sbc a,b
 ld b,a
 add sp,#4
055$:
 pop af
 bit 7,a
 jr z,060$
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ld a,#0
 sbc a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
060$:
 pop af
 ld (#0x2000),a
 ld h,b
 ld l,c
 ret
083$:
 ld h,b
 ld l,c
 ld c,e
 ld d,h
 ld e,l
082$:
 ; DE=a, C=lo; preserve a for exact a*(256+lo)=a*lo+(a<<8).
 push de
 call _riding_mul16u8_unsigned
 pop bc
 ld a,d
 add a,c
 ld d,a
 ld a,l
 adc a,b
 ld c,a
 ; a<=32768 and multiplier<=511 imply an unsigned product below2^24.
 ld b,#0
 jp 055$

; HL=index0..65535, returns Q(index) in HLDE. Only ROM0 IRQ code may run
; while the table bank is selected, as with any ordinary banked data copy.
100$:
 ld a,h
 swap a
 and a,#15
 add a,#20
 ld (#0x2000),a
 sla l
 rl h
 sla l
 rl h
 ld a,h
 and a,#0x3f
 or a,#0x40
 ld h,a
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld h,(hl)
 ld l,c
 ret

080$:
 ld h,b
 ld l,c
 ld c,e
 ld d,h
 ld e,l
081$:
 call _riding_mul16u8_unsigned
 ld b,h
 ld c,l
 jp 055$

070$:
 ld h,b
 ld l,c
 jr 072$
071$:
 ld h,d
 ld l,e
072$:
 ; Unsigned magnitude x times16384 = (x<<16)>>2. Low byte stayszero.
 ld de,#0
 srl h
 rr l
 rr d
 srl h
 rr l
 rr d
 ld b,h
 ld c,l
 jp 055$
073$:
 ; Q(2*x)=x*x, one table read instead of Q(sum)-Q(diff).
 ld h,d
 ld l,e
 add hl,hl
 jr c,074$
 call 100$
 ld b,h
 ld c,l
 jp 055$
074$:
 ld bc,#0x4000
 ld de,#0
 jp 055$

math_mul16_zero:
 ld hl,#0
 ld de,#0
 ret

; Register ABI for ROM0 assembly callers; arguments DE=a, BC=b, resultHLDE.
; Identical zero/sign/table kernel and bank contract as the public stack ABI.
_riding_mul16_regs::
 ld a,d
 or a,e
 jp z,math_mul16_zero
 ld a,b
 or a,c
 jp z,math_mul16_zero
 jp math_mul16_loaded
