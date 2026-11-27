; Coordinate safety bounds only; no changes to the physical simulation.
; ABI0 no arguments, uint8 result in E. The six Q16.16 wheel/rider deltas
; wrap modulo32. The live PC wheel reaches 7.081 m at 140 rad/s before
; the trajectory runs away. Eight metres fits the signed Q10 lever arm.
.module riding_bounds
WHEEL_BOUND_METRES = 8
RIDER_BOUND_METRES = 3
; The scheduled game calls this predicate only from the riding loop in bank 5.
.ifdef RIDING_BANKED_BOUNDS
.area _CODE_5
.else
.area _CODE
.endif
_gbc_bike_bounded::
 ld hl,#_gbc_bike+2
 call bounds_axis
 jr nc,bounds_no
 ld hl,#_gbc_bike+6
 call bounds_axis
 jr nc,bounds_no
 ld e,#1
 ret
bounds_no:
 ld e,#0
 ret

; An integer difference strictly inside (-limit,limit) is safe for every
; combination of fractions. Only the two endpoints need the low words.
; BC is the body integer plus the wheel limit, modulo 65536. HL walks the
; integer words of the three successive 10-byte records on this axis.
.macro bounds_part limit,distance,?edge,?valid
 ld de,#9
 add hl,de
 ld a,c
 sub (hl)
 inc hl
 ld e,a
 ld a,b
 sbc (hl)
 or a
 ret nz                          ; high byte outside the admissible range
 ld a,e
 sub #(WHEEL_BOUND_METRES-limit+1)
 cp #(2*limit-1)
 jr c,valid                      ; covers every strictly interior integer
 inc a                           ; integer difference plus this part's limit
 jr z,edge                       ; negative limit
 cp #(2*limit)
 ret nz                          ; all remaining non-endpoints are too large
edge:
 ld de,#-distance
 call bounds_fraction
 ret nc
valid:
.endm

bounds_axis:
 ld a,(hl+)
 add #WHEEL_BOUND_METRES
 ld c,a
 ld a,(hl)
 adc #0
 ld b,a
 bounds_part WHEEL_BOUND_METRES,10
 bounds_part WHEEL_BOUND_METRES,20
 bounds_part RIDER_BOUND_METRES,30
 ret

; HL is the part's top byte. Compare body >= part at the negative limit
; and part >= body at the positive limit, in unsigned 16-bit fractions.
bounds_fraction:
 push hl
 dec hl
 dec hl
 dec hl
 push hl
 add hl,de
 pop de
 or a
 jr nz,bounds_fraction_compare
 push hl
 ld h,d
 ld l,e
 pop de
bounds_fraction_compare:
 ld a,(de)
 sub (hl)
 inc de
 inc hl
 ld a,(de)
 sbc (hl)
 ccf
 pop hl
 ret
