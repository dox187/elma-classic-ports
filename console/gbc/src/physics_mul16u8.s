.module mul16u8
.area _CODE
; Unsigned16 DE times unsigned8 C, raw32 return HLDE. Leaves table bank
; selected for the wide multiplier to restore once, after its sign correction.
_riding_mul16u8_unsigned::
 .ifdef RIDING_SCALE_DIRECTORY
 ld l,c
 ld h,#>_riding_scale_directory
 ld a,(hl)
 ld (#0x2000),a
 inc h
 ld h,(hl)
 .else
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
 .endif
 ld l,e
 ld e,(hl)
 inc h
 ld a,(hl)
 ld l,d
 ld b,(hl)
 dec h
 add a,(hl)
 ld d,a
 ld a,b
 adc a,#0
 ld l,a
 ld h,#0
 ret
