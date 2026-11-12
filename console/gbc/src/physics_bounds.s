; Coordinate safety bounds only; no changes to the physical simulation.
; ABI0 no arguments, uint8 result in E. The six Q16.16 wheel/rider deltas
; must each lie in inclusive[-3m,+3m]. Arithmetic wraps modulo32, as before.
.module riding_bounds
.area _CODE
_gbc_bike_bounded::
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

; Subtract part from body: the interval is symmetric. BC is the high word
; and DE the fractional low word. Carry set means the coordinate is valid.
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
 ld b,a
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
 ld b,a
bounds_delta:
 ; High word -3..2 always passes; +3 passes only with low word zero.
 ld a,c
 add a,#3
 ld c,a
 ld a,b
 adc a,#0
 or a,a
 jr nz,bounds_invalid
 ld a,c
 cp a,#6
 ret c
 jr nz,bounds_invalid
 ld a,d
 or a,e
 jr nz,bounds_invalid
 scf
 ret
bounds_invalid:
 and a,a
 ret
