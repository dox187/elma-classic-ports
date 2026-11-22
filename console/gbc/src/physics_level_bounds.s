; Original scheduled brush/grid exit checks, in Q18. Wheels are checked
; before integration; the head and body use their post-integration positions.
.module physics_level_bounds
.area _CODE_8

; Carry if the signed position at HL is below the limit at DE. Both point at
; the most significant byte. Only exact ties need the lower coordinate bytes.
bounds_before:
 ld a,(de)
 xor #0x80
 ld b,a
 ld a,(hl-)
 xor #0x80
 cp b
 ret nz
 .rept 2
 dec de
 ld a,(de)
 ld b,a
 ld a,(hl-)
 cp b
 ret nz
 .endm
 dec de
 ld a,(de)
 ld b,a
 ld a,(hl)
 cp b
 ret

.macro bounds_compare pos,limit
 ld hl,#(_Bike+pos+3)
 ld de,#(_riding_level+limit+3)
 call bounds_before
.endm

_wheels_in_grid::
 bounds_compare 24,24
 jr nc,bounds_out
 bounds_compare 28,28
 jr nc,bounds_out
 bounds_compare 48,24
 jr nc,bounds_out
 bounds_compare 52,28
 jr nc,bounds_out
 ld a,#1
 ret
_head_body_in_level::
 bounds_compare 88,24
 jr nc,bounds_out
 bounds_compare 92,28
 jr nc,bounds_out
 bounds_compare 0,32
 jr c,bounds_out
 bounds_compare 0,36
 jr nc,bounds_out
 bounds_compare 4,40
 jr c,bounds_out
 bounds_compare 4,44
 jr nc,bounds_out
 ld a,#1
 ret
bounds_out:
 xor a
 ret
