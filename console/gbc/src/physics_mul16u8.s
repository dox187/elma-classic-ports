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

; Exact signed16 normal components times the unsigned-byte coordinates
; C,B. Return their signed32 sum in BC:DE.
; The low lookup digit carries into the next product before rounding.
_riding_fraction_pair::
 push bc
 call fraction_axis
 pop bc
 push af
 push de
 ld c,b
 call fraction_axis
 pop bc
 ld h,a                   ; second product, upper byte
 ld a,e
 add c
 ld e,a
 ld a,d
 adc b
 ld d,a
 pop bc                   ; first product's upper byte in B
 ld a,b
 adc h
 ld c,a
 ; Sum of both sign extensions and the carry from byte two.
 ld a,#0
 adc #0
 bit 7,b
 jr z,fraction_first_positive
 dec a
fraction_first_positive:
 bit 7,h
 jr z,fraction_second_positive
 dec a
fraction_second_positive:
 ld b,a
 ldh a,(#__current_bank)
 ld (#0x2000),a
 ret

; C is the unsigned coordinate. Obtain the low and high parts of both
; unsigned byte products in one selected bank. Correct the signed high
; digit modulo 256. Every signed16-by-byte product fits signed24.
fraction_axis:
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 push hl
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
 add (hl)
 ld d,a
 ld a,b
 adc #0
 bit 7,l
 jr z,fraction_axis_done
 sub c
fraction_axis_done:
 pop hl
 ret
