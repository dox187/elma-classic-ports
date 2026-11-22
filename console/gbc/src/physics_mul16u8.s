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
 or a,#>_physics_scale_planes_36
 ld h,a
 ld l,e
 ld e,(hl)
 inc h
 ld d,(hl)
 ld l,b
 dec h
 ld a,(hl)
 add a,d
 ld d,a
 inc h
 ld a,(hl)
 adc a,#0
 ld l,a
 ld h,#0
 ret
