; Original scheduled brush/grid exit checks, in Q18. Wheels are checked
; before integration; the head and body use their post-integration positions.
.module physics_level_bounds
.area _CODE_8

; Carry if the signed position at HL is below the limit at DE. Both point at
; the most significant byte. Only exact ties need the lower coordinate bytes.
_riding_bounds_before::
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
 call _riding_bounds_before
.endm

; The common rectangle starts at zero and ends at the high-word
; floor of the tighter grid or upper brush bound. Each coordinate is
; treated as unsigned here: negatives cannot pass a positive ceiling.
; If either pair cannot be certified, apply the original signed tests.
.area _DATA
bounds_inner:
 .ds 4
.area _CODE_14
.globl b_riding_prepare_level_bounds
b_riding_prepare_level_bounds = 14
_riding_prepare_level_bounds::
 ld hl,#(_riding_level+35)
 ld de,#(_riding_level+26)
 call bounds_inner_axis
 ld a,l
 ld (#bounds_inner),a
 ld a,h
 ld (#bounds_inner+1),a
 ld hl,#(_riding_level+43)
 ld de,#(_riding_level+30)
 call bounds_inner_axis
 ld a,l
 ld (#bounds_inner+2),a
 ld a,h
 ld (#bounds_inner+3),a
 ret

; HL points to the lower brush sign byte. DE points to the upper grid word.
bounds_inner_axis:
 bit 7,(hl)
 jr z,bounds_inner_empty
 inc hl
 inc hl
 inc hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 bit 7,h
 jr nz,bounds_inner_empty
 ld a,(de)
 ld c,a
 inc de
 ld a,(de)
 bit 7,a
 jr nz,bounds_inner_empty
 cp h
 jr c,bounds_take_grid
 ret nz
 ld a,c
 cp l
 ret nc
 ld l,c
 ret
bounds_take_grid:
 ld h,a
 ld l,c
 ret
bounds_inner_empty:
 ld hl,#0
 ret

.area _CODE_8
; The OR of the top bytes is an upper bound for both. In the ceiling's
; top-byte band compare the next byte of each point separately.
.macro bounds_inner_pair p,q,axis,slow,accepted
 ld hl,#(_Bike+q+axis+3)
 ld a,(#_Bike+p+axis+3)
 or (hl)
 ld hl,#(bounds_inner+axis/2+1)
 cp (hl)
 jr c,accepted
 jr nz,slow
 dec hl
 ld a,(#_Bike+p+axis+2)
 cp (hl)
 jr nc,slow
 ld a,(#_Bike+q+axis+2)
 cp (hl)
 jr nc,slow
accepted:
.endm

_wheels_in_grid::
 bounds_inner_pair 24,48,0,bounds_wheel_x,wx
bounds_wheel_y_test:
 bounds_inner_pair 24,48,4,bounds_wheel_y,wy
 ld a,#1
 ret
bounds_wheel_x:
 bounds_compare 24,24
 jr nc,bounds_out
 bounds_compare 48,24
 jr c,bounds_wheel_y_test
bounds_out:
 xor a
 ret
bounds_wheel_y:
 bounds_compare 28,28
 jr nc,bounds_out
 bounds_compare 52,28
 jr nc,bounds_out
 ld a,#1
 ret

_head_body_in_level::
 bounds_inner_pair 0,88,0,bounds_head_body_x,bx
bounds_head_body_y_test:
 bounds_inner_pair 0,88,4,bounds_head_body_y,by
 ld a,#1
 ret
bounds_head_body_x:
 bounds_compare 88,24
 jr nc,bounds_body_out
 bounds_compare 0,32
 jr c,bounds_body_out
 bounds_compare 0,36
 jr c,bounds_head_body_y_test
bounds_body_out:
 xor a
 ret
bounds_head_body_y:
 bounds_compare 92,28
 jr nc,bounds_body_out
 bounds_compare 4,40
 jr c,bounds_body_out
 bounds_compare 4,44
 jr nc,bounds_body_out
 ld a,#1
 ret
