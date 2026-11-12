; Reentrant unrolled signed16 x16 ->32, SDCC stack ABI0 return HLDE.
; Used by riding physics; diagnostic gbc_mul16 remains an independent vector oracle.
.module riding_mul16
.area _CODE
_riding_mul16::
 ldhl sp,#2
 ld a,(hl+)
 or a,(hl)
 jp z,300$
 inc hl
 ld a,(hl+)
 or a,(hl)
 jp z,300$
 ldhl sp,#4
 ld c,(hl)
 inc hl
 ld b,(hl)
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
 bit 0,c
 jr z,116$
 ld a,e
 add a,l
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 jr 117$
116$:
 xor a
117$:
 rr d
 rr e
 rr b
 rr c
 bit 0,c
 jr z,118$
 ld a,e
 add a,l
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 jr 119$
118$:
 xor a
119$:
 rr d
 rr e
 rr b
 rr c
 bit 0,c
 jr z,120$
 ld a,e
 add a,l
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 jr 121$
120$:
 xor a
121$:
 rr d
 rr e
 rr b
 rr c
 bit 0,c
 jr z,122$
 ld a,e
 add a,l
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 jr 123$
122$:
 xor a
123$:
 rr d
 rr e
 rr b
 rr c
 bit 0,c
 jr z,124$
 ld a,e
 add a,l
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 jr 125$
124$:
 xor a
125$:
 rr d
 rr e
 rr b
 rr c
 bit 0,c
 jr z,126$
 ld a,e
 add a,l
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 jr 127$
126$:
 xor a
127$:
 rr d
 rr e
 rr b
 rr c
 bit 0,c
 jr z,128$
 ld a,e
 add a,l
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 jr 129$
128$:
 xor a
129$:
 rr d
 rr e
 rr b
 rr c
 bit 0,c
 jr z,130$
 ld a,e
 add a,l
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 jr 131$
130$:
 xor a
131$:
 rr d
 rr e
 rr b
 rr c
 ldhl sp,#3
 bit 7,(hl)
 jr z,200$
 inc hl
 ld a,e
 sub a,(hl)
 ld e,a
 inc hl
 ld a,d
 sbc a,(hl)
 ld d,a
200$:
 ldhl sp,#5
 bit 7,(hl)
 jr z,201$
 ldhl sp,#2
 ld a,e
 sub a,(hl)
 ld e,a
 inc hl
 ld a,d
 sbc a,(hl)
 ld d,a
201$:
 ld h,d
 ld l,e
 ld d,b
 ld e,c
 ret
300$:
 ld hl,#0
 ld de,#0
 ret
