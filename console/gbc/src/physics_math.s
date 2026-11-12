; Signed16 x unsigned8, rounded arithmetic shift, saturated16 result.
; Stack ABI0 x@sp+2,m@sp+4,e@sp+5; returns DE. Reentrant, no scratch RAM.
.module gbc_physics_math
.area _CODE
_riding_kmul_serial::
 ldhl sp,#4
 ld c,(hl)
 ld b,#0
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#0
 bit 0,c
 jr z,100$
 ld a,e
 add a,l
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 jr 101$
100$:
 xor a
101$:
 rr d
 rr e
 rr b
 rr c
 bit 0,c
 jr z,102$
 ld a,e
 add a,l
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 jr 103$
102$:
 xor a
103$:
 rr d
 rr e
 rr b
 rr c
 bit 0,c
 jr z,104$
 ld a,e
 add a,l
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 jr 105$
104$:
 xor a
105$:
 rr d
 rr e
 rr b
 rr c
 bit 0,c
 jr z,106$
 ld a,e
 add a,l
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 jr 107$
106$:
 xor a
107$:
 rr d
 rr e
 rr b
 rr c
 bit 0,c
 jr z,108$
 ld a,e
 add a,l
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 jr 109$
108$:
 xor a
109$:
 rr d
 rr e
 rr b
 rr c
 bit 0,c
 jr z,110$
 ld a,e
 add a,l
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 jr 111$
110$:
 xor a
111$:
 rr d
 rr e
 rr b
 rr c
 bit 0,c
 jr z,112$
 ld a,e
 add a,l
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 jr 113$
112$:
 xor a
113$:
 rr d
 rr e
 rr b
 rr c
 bit 0,c
 jr z,114$
 ld a,e
 add a,l
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 jr 115$
114$:
 xor a
115$:
 rr d
 rr e
 rr b
 rr c
 ; After8 bits DEBC is product<<8; correct high24 byte for signed x.
 ldhl sp,#3
 bit 7,(hl)
 jr z,200$
 inc hl
 ld a,d
 sub a,(hl)
 ld d,a
200$:
 ld l,d
 ld a,d
 rlca
 sbc a,a
 ld h,a
 ld d,e
 ld e,b
 push hl
 ldhl sp,#7
 ld c,(hl)
 pop hl
 ; With E>=8 the quotient fits signed16 before rounding. Discard a
 ; complete byte first, then shift16 rather than shifting32 E times.
 ld a,c
 sub a,#8
 jr c,201$
 ld c,a
 ld b,e
 ld e,d
 ld d,l
 or a,a
 jr z,210$
209$:
 sra d
 rr e
 dec c
 jr nz,209$
 jr nc,212$
211$:
 inc de
212$:
 ret
210$:
 bit 7,b
 jr nz,211$
 ret
201$:
 sra h
 rr l
 rr d
 rr e
 dec c
 jr nz,201$
 jr nc,204$
 inc e
 jr nz,204$
 inc d
 jr nz,204$
 inc l
 jr nz,204$
 inc h
204$:
 ld a,h
 or a,l
 jr z,205$
 ld a,h
 and a,l
 inc a
 jr nz,206$
 bit 7,d
 jr nz,207$
206$:
 bit 7,h
 jr z,208$
 ld de,#0x8000
 ret
208$:
 ld de,#0x7fff
 ret
205$:
 bit 7,d
 jr nz,208$
207$:
 ret

; Exact scaled vector products. SDCC register ABI1; dot callee cleans stack c,d.
_mulq14::
 call _riding_mul16_regs
 ld a,d
 add a,#32
 ld d,a
 ld a,l
 adc a,#0
 ld l,a
 ld a,h
 adc a,#0
 ld h,a
 ; bits14..29 are the result: shift toward the high end twice.
 ; First check that the unshifted high byte is within signed[-32,31].
 ld a,h
 add a,#32
 cp a,#64
 jr nc,scale_mulq14_sat
 sla d
 rl l
 rl h
 sla d
 rl l
 rl h
 ld b,h
 ld c,l
 jr scale_mulq14_done
scale_mulq14_sat:
 bit 7,h
 jr z,scale_mulq14_pos
 ld bc,#0x8000
 jr scale_mulq14_done
scale_mulq14_pos:
 ld bc,#0x7fff
scale_mulq14_done:
 ret
_mulq10::
 call _riding_mul16_regs
 ld a,d
 add a,#2
 ld d,a
 ld a,l
 adc a,#0
 ld l,a
 ld a,h
 adc a,#0
 ld h,a
 ld b,#2
scale_mulq10:
 sra h
 rr l
 rr d
 dec b
 jr nz,scale_mulq10
 ld e,d
 ld d,l
 ld a,h
 or a,a
 jr z,scale_mulq10P
 inc a
 jr nz,scale_mulq10S
 bit 7,d
 jr nz,scale_mulq10R
scale_mulq10S:
 bit 7,h
 jr z,scale_mulq10U
 ld de,#0x8000
 jr scale_mulq10R
scale_mulq10U:
 ld de,#0x7fff
 jr scale_mulq10R
scale_mulq10P:
 bit 7,d
 jr nz,scale_mulq10U
scale_mulq10R:
 ld b,d
 ld c,e
 ret
_dotq14::
 push bc
 ldhl sp,#4
 ld c,(hl)
 inc hl
 ld b,(hl)
 call _riding_mul16_regs
 push hl
 push de
 ldhl sp,#10
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#4
 ld e,(hl)
 inc hl
 ld d,(hl)
 call _riding_mul16_regs
 ld b,h
 ld c,l
 ldhl sp,#0
 ld a,e
 add a,(hl)
 ld e,a
 inc hl
 ld a,d
 adc a,(hl)
 ld d,a
 inc hl
 ld a,c
 adc a,(hl)
 ld c,a
 inc hl
 ld a,b
 adc a,(hl)
 ld b,a
 ld h,b
 ld l,c
 add sp,#6
 ld a,d
 add a,#32
 ld d,a
 ld a,l
 adc a,#0
 ld l,a
 ld a,h
 adc a,#0
 ld h,a
 ; bits14..29 are the result: shift toward the high end twice.
 ; First check that the unshifted high byte is within signed[-32,31].
 ld a,h
 add a,#32
 cp a,#64
 jr nc,scale_dot_sat
 sla d
 rl l
 rl h
 sla d
 rl l
 rl h
 ld b,h
 ld c,l
 jr scale_dot_done
scale_dot_sat:
 bit 7,h
 jr z,scale_dot_pos
 ld bc,#0x8000
 jr scale_dot_done
scale_dot_pos:
 ld bc,#0x7fff
scale_dot_done:
 pop hl
 add sp,#4
 jp (hl)

; ABI1 signed32 highDE+lowBC, saturated signed16 returnBC.
_sat16::
 ld a,d
 or a,e
 jr z,010$
 ld a,d
 and a,e
 inc a
 jr nz,020$
 bit 7,b
 ret nz
020$:
 bit 7,d
 jr z,030$
 ld bc,#0x8000
 ret
010$:
 bit 7,b
 ret z
030$:
 ld bc,#0x7fff
 ret
