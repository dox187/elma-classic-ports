; Exact scheduled packed circle_t motion, stack ABI0, fixed ROM0.
; Arguments: circle pointer, x residual slot (body 0, wheels 2/4).
; Layout rx0 ry4 vx8 vy12 alfa16 omega20. All additions wrap modulo 2^32.
; Shared phase helpers preserve their signed Q24 residual and bank contracts.
.module physics_circle_scheduled
.area _CODE
_riding_circle_scheduled::
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 ld de,#20
 add hl,de
 ld c,(hl)
 inc hl
 ld b,(hl)
 ld a,b
 add a,a
 sbc a,a
 ld e,a
 ld d,a
 ld a,#7
 push af
 inc sp
 call _phase_move
 ldhl sp,#0
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push de
 ld de,#16
 add hl,de
 pop de
 call circle_add
 ldhl sp,#6
 ld b,(hl)
 ld c,#2
 ldhl sp,#0
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#8
 add hl,de
 push bc
 call circle_load
 call _phase_advance
 ldhl sp,#0
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call circle_add
 ; circle_add leaves HL at the next position (ry).
 push hl
 ld de,#8
 add hl,de
 push hl
 ldhl sp,#10
 ld b,(hl)
 inc b
 ld c,#2
 pop hl
 push bc
 call circle_load
 call _phase_advance
 pop hl
 call circle_add
 pop hl
 ret
circle_load:
 ld c,(hl)
 inc hl
 ld b,(hl)
 inc hl
 ld e,(hl)
 inc hl
 ld d,(hl)
 ret
circle_add:
 ld a,(hl)
 add a,c
 ld (hl+),a
 ld a,(hl)
 adc a,b
 ld (hl+),a
 ld a,(hl)
 adc a,e
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld (hl+),a
 ret
_riding_circle_scheduled_end::
