.module mul16u8
.area _CODE
; Unsigned16 DE times unsigned8 C, raw32 return HLDE. Leaves table bank
; selected for the wide multiplier to restore once, after its sign correction.
_riding_mul16u8_unsigned::
 ld b,d
 ld a,c
 rlca
 rlca
 rlca
 and a,#7
 add a,#36
 ld (#0x2000),a
 ld a,c
 and a,#31
 add a,a
 or a,#0x40
 ld h,a
 ld a,e
 add a,a
 ld l,a
 jr nc,500$
 inc h
500$:
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ld a,c
 and a,#31
 add a,a
 or a,#0x40
 ld h,a
 ld a,b
 add a,a
 ld l,a
 jr nc,510$
 inc h
510$:
 ld a,(hl+)
 add a,d
 ld d,a
 ld a,(hl)
 adc a,#0
 ld l,a
 ld h,#0
 ret
