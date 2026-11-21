; Coordinate safety bounds only; no changes to the physical simulation.
; ABI0 no arguments, uint8 result in E. The six Q16.16 wheel/rider deltas
; wrap modulo32. The live PC wheel reaches 7.081 m at 140 rad/s before
; the trajectory runs away. Eight metres fits the signed Q10 lever arm.
.module riding_bounds
WHEEL_BOUND_METRES = 8
RIDER_BOUND_METRES = 3
.area _CODE
_gbc_bike_bounded::
 ld b,#WHEEL_BOUND_METRES
 ld hl,#_gbc_bike+10
 call bounds_x
 jr nc,bounds_no
 ld hl,#_gbc_bike+14
 call bounds_y
 jr nc,bounds_no
 ld hl,#_gbc_bike+20
 call bounds_x
 jr nc,bounds_no
 ld hl,#_gbc_bike+24
 call bounds_y
 jr nc,bounds_no
 ld b,#RIDER_BOUND_METRES
 ld hl,#_gbc_bike+30
 call bounds_x
 jr nc,bounds_no
 ld hl,#_gbc_bike+34
 call bounds_y
 jr nc,bounds_no
 ld e,#1
 ret
bounds_no:
 ld e,#0
 ret

; Subtract part from body: the interval is symmetric. Keep the high word
; in H:C and the fractional word in DE. B retains the inclusive metre limit.
; Carry set means the coordinate is valid.
bounds_x:
 ld a,(#_gbc_bike)
 sub a,(hl)
 ld e,a
 inc hl
 ld a,(#_gbc_bike+1)
 sbc a,(hl)
 ld d,a
 inc hl
 ld a,(#_gbc_bike+2)
 sbc a,(hl)
 ld c,a
 inc hl
 ld a,(#_gbc_bike+3)
 sbc a,(hl)
 ld h,a
 jr bounds_delta
bounds_y:
 ld a,(#_gbc_bike+4)
 sub a,(hl)
 ld e,a
 inc hl
 ld a,(#_gbc_bike+5)
 sbc a,(hl)
 ld d,a
 inc hl
 ld a,(#_gbc_bike+6)
 sbc a,(hl)
 ld c,a
 inc hl
 ld a,(#_gbc_bike+7)
 sbc a,(hl)
 ld h,a
bounds_delta:
 ; Bias the high word by the limit. Its upper endpoint must be integral.
 ld a,c
 add a,b
 ld c,a
 ld a,h
 adc a,#0
 or a,a
 jr nz,bounds_invalid
 ld a,b
 add a,a
 cp a,c
 jr c,bounds_invalid
 jr nz,bounds_valid
 ld a,d
 or a,e
 jr nz,bounds_invalid
bounds_valid:
 scf
 ret
bounds_invalid:
 and a,a
 ret
