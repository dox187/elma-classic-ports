; Exact arithmetic shift by8, SDCC default ABI1 DEBC -> DEBC.
; This drops one low byte and sign-extends the original high byte.
.module physics_shift_fast
.area _CODE
_riding_sra8::
 ld c,b
 ld b,e
 ld e,d
 ld a,d
 add a,a
 sbc a,a
 ld d,a
 ret
