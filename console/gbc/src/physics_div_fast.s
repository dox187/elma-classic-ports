; Exact unsigned32 / unsigned16 -> unsigned16, when the quotient fits16.
; ABI0 numerator@sp+2,divisor@sp+6; returns DE. Divisor must be nonzero.
; Unrolled restoring division starts with the high16 numerator as remainder.
.module riding_div_fast
.area _CODE
_riding_div_u32_u16::
 ldhl sp,#6
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#2
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 sla e
 rl d
 rl l
 rl h
 jr c,100$
 ld a,l
 sub a,c
 ld a,h
 sbc a,b
 jr c,101$
100$:
 ld a,l
 sub a,c
 ld l,a
 ld a,h
 sbc a,b
 ld h,a
 inc e
101$:
 sla e
 rl d
 rl l
 rl h
 jr c,102$
 ld a,l
 sub a,c
 ld a,h
 sbc a,b
 jr c,103$
102$:
 ld a,l
 sub a,c
 ld l,a
 ld a,h
 sbc a,b
 ld h,a
 inc e
103$:
 sla e
 rl d
 rl l
 rl h
 jr c,104$
 ld a,l
 sub a,c
 ld a,h
 sbc a,b
 jr c,105$
104$:
 ld a,l
 sub a,c
 ld l,a
 ld a,h
 sbc a,b
 ld h,a
 inc e
105$:
 sla e
 rl d
 rl l
 rl h
 jr c,106$
 ld a,l
 sub a,c
 ld a,h
 sbc a,b
 jr c,107$
106$:
 ld a,l
 sub a,c
 ld l,a
 ld a,h
 sbc a,b
 ld h,a
 inc e
107$:
 sla e
 rl d
 rl l
 rl h
 jr c,108$
 ld a,l
 sub a,c
 ld a,h
 sbc a,b
 jr c,109$
108$:
 ld a,l
 sub a,c
 ld l,a
 ld a,h
 sbc a,b
 ld h,a
 inc e
109$:
 sla e
 rl d
 rl l
 rl h
 jr c,110$
 ld a,l
 sub a,c
 ld a,h
 sbc a,b
 jr c,111$
110$:
 ld a,l
 sub a,c
 ld l,a
 ld a,h
 sbc a,b
 ld h,a
 inc e
111$:
 sla e
 rl d
 rl l
 rl h
 jr c,112$
 ld a,l
 sub a,c
 ld a,h
 sbc a,b
 jr c,113$
112$:
 ld a,l
 sub a,c
 ld l,a
 ld a,h
 sbc a,b
 ld h,a
 inc e
113$:
 sla e
 rl d
 rl l
 rl h
 jr c,114$
 ld a,l
 sub a,c
 ld a,h
 sbc a,b
 jr c,115$
114$:
 ld a,l
 sub a,c
 ld l,a
 ld a,h
 sbc a,b
 ld h,a
 inc e
115$:
 sla e
 rl d
 rl l
 rl h
 jr c,116$
 ld a,l
 sub a,c
 ld a,h
 sbc a,b
 jr c,117$
116$:
 ld a,l
 sub a,c
 ld l,a
 ld a,h
 sbc a,b
 ld h,a
 inc e
117$:
 sla e
 rl d
 rl l
 rl h
 jr c,118$
 ld a,l
 sub a,c
 ld a,h
 sbc a,b
 jr c,119$
118$:
 ld a,l
 sub a,c
 ld l,a
 ld a,h
 sbc a,b
 ld h,a
 inc e
119$:
 sla e
 rl d
 rl l
 rl h
 jr c,120$
 ld a,l
 sub a,c
 ld a,h
 sbc a,b
 jr c,121$
120$:
 ld a,l
 sub a,c
 ld l,a
 ld a,h
 sbc a,b
 ld h,a
 inc e
121$:
 sla e
 rl d
 rl l
 rl h
 jr c,122$
 ld a,l
 sub a,c
 ld a,h
 sbc a,b
 jr c,123$
122$:
 ld a,l
 sub a,c
 ld l,a
 ld a,h
 sbc a,b
 ld h,a
 inc e
123$:
 sla e
 rl d
 rl l
 rl h
 jr c,124$
 ld a,l
 sub a,c
 ld a,h
 sbc a,b
 jr c,125$
124$:
 ld a,l
 sub a,c
 ld l,a
 ld a,h
 sbc a,b
 ld h,a
 inc e
125$:
 sla e
 rl d
 rl l
 rl h
 jr c,126$
 ld a,l
 sub a,c
 ld a,h
 sbc a,b
 jr c,127$
126$:
 ld a,l
 sub a,c
 ld l,a
 ld a,h
 sbc a,b
 ld h,a
 inc e
127$:
 sla e
 rl d
 rl l
 rl h
 jr c,128$
 ld a,l
 sub a,c
 ld a,h
 sbc a,b
 jr c,129$
128$:
 ld a,l
 sub a,c
 ld l,a
 ld a,h
 sbc a,b
 ld h,a
 inc e
129$:
 sla e
 rl d
 rl l
 rl h
 jr c,130$
 ld a,l
 sub a,c
 ld a,h
 sbc a,b
 jr c,131$
130$:
 ld a,l
 sub a,c
 ld l,a
 ld a,h
 sbc a,b
 ld h,a
 inc e
131$:
 ret
