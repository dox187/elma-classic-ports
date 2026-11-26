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
 .ifdef RIDING_BANKED_DIVISION
 ld a,#35
 ld (#0x2000),a
 call divide_body
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret
.area _CODE_35
divide_body:
 ; When n >> 8 is below the divisor, the first eight quotient bits
 ; are zero. Install their exact remainder and start at bit seven.
 ld a,h
 or a
 jr nz,divide_sixteen
 ld a,d
 sub c
 ld a,l
 sbc b
 jr nc,divide_sixteen
 ld h,l
 ld l,d
 ld d,e
 ld e,#0
 jp divide_eight
divide_sixteen:
 .endif

.macro divide_bit ?subtract,?done
 sla e
 rl d
 rl l
 rl h
 jr c,subtract
 ld a,l
 sub c
 ld a,h
 sbc b
 jr c,done
subtract:
 ld a,l
 sub c
 ld l,a
 ld a,h
 sbc b
 ld h,a
 inc e
done:
.endm

.rept 8
 divide_bit
.endm
divide_eight:
.rept 8
 divide_bit
.endm
 ret
