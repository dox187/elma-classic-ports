; Exact rider vectors and motion, packed bike119, stack ABI0, ROM bank8.
; Bike: body.rx0 ry4, rider_x72 y76 vx80 vy84.
; Vectors(restx,resty,out) writes dirx,diry,dx,dy as signed16.
; dir = sat16((wrap32(body-rider) >> 4) + signed16(rest));
; delta = sat16(wrap32(rider-body) >> 4).
; Keep the unshifted difference on the stack: negation must precede the
; arithmetic shift, including negative low nibbles and INT32_MIN.
; Move(ax,ay) adds accelerations, then advances scheduled motion and residuals.
; All motion arithmetic wraps modulo2^32. No mutable global scratch.
.module physics_rider_fast
.area _CODE_8

; For displacements fitting signed20, q = floor(displacement/16) fits
; signed16. The reverse displacement is ~q plus one exactly when the low
; nibble is zero. Compute both vectors from this one quotient.
.macro rider_narrow_axis rest_offset, out_offset, wide, neg_ok, store, finish
 ld a,c
 add a,#8
 and #0xf0
 jr nz,wide
 ld a,c
 rlca
 sbc a,a
 cp b
 jr nz,wide
 ld a,e
 and #0x0f
 ld h,a
 ; Merge adjacent nibbles to divide the signed20 displacement by sixteen.
 ld a,d
 xor a,e
 and #0x0f
 xor a,e
 swap a
 ld e,a
 ld a,c
 xor a,d
 and #0x0f
 xor a,d
 swap a
 ld d,a
 ld a,h
 sub a,#1
 ld a,e
 cpl
 adc a,#0
 ld c,a
 ld a,d
 cpl
 adc a,#0
 ld b,a
 ; Only -524288 can give a positive reverse quotient of 32768.
 and a,d
 bit 7,a
 jr z,neg_ok
 ld bc,#0x7fff
neg_ok:
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 .rept 4+out_offset
 inc hl
 .endm
 ld (hl),c
 inc hl
 ld (hl),b
 ; Saturating signed16 addition of the rest vector.
 ldhl sp,#rest_offset
 ld a,(hl+)
 add a,e
 ld e,a
 ld c,(hl)
 ld a,c
 adc a,d
 ld b,a
 xor a,c
 ld c,a
 ld a,b
 xor a,d
 and a,c
 ld d,b
 bit 7,a
 jr z,store
 ld de,#0x7fff
 bit 7,b
 jr nz,store
 inc de
store:
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 .rept out_offset
 inc hl
 .endm
 ld (hl),e
 inc hl
 ld (hl),d
 jp finish
wide:
.endm

_riding_rider_vectors32::
 ld hl,#_Bike+72
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 ld hl,#_Bike
 ld a,(hl+)
 sub a,e
 ld e,a
 ld a,(hl+)
 sbc a,d
 ld d,a
 ld a,(hl+)
 sbc a,c
 ld c,a
 ld a,(hl)
 sbc a,b
 ld b,a
 rider_narrow_axis 2,0,rider_x_wide,rider_x_negative_ok,rider_x_store,rider_axis_y
 push bc
 push de
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ld a,#0
 sbc a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
 sra b
 rr c
 rr d
 rr e
 sra b
 rr c
 rr d
 rr e
 sra b
 rr c
 rr d
 rr e
 sra b
 rr c
 rr d
 rr e
 call rider_sat16
 ldhl sp,#10
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 inc hl
 inc hl
 inc hl
 inc hl
 ld (hl),e
 inc hl
 ld (hl),d
 pop de
 pop bc
 sra b
 rr c
 rr d
 rr e
 sra b
 rr c
 rr d
 rr e
 sra b
 rr c
 rr d
 rr e
 sra b
 rr c
 rr d
 rr e
 push bc
 push de
 ldhl sp,#6
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld a,d
 add a,a
 sbc a,a
 ld b,a
 ld c,a
 ldhl sp,#0
 ld a,(hl+)
 add a,e
 ld e,a
 ld a,(hl+)
 adc a,d
 ld d,a
 ld a,(hl+)
 adc a,c
 ld c,a
 ld a,(hl)
 adc a,b
 ld b,a
 add sp,#4
 call rider_sat16
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld (hl),e
 inc hl
 ld (hl),d

rider_axis_y:
 ld hl,#_Bike+76
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 ld hl,#_Bike+4
 ld a,(hl+)
 sub a,e
 ld e,a
 ld a,(hl+)
 sbc a,d
 ld d,a
 ld a,(hl+)
 sbc a,c
 ld c,a
 ld a,(hl)
 sbc a,b
 ld b,a
 rider_narrow_axis 4,2,rider_y_wide,rider_y_negative_ok,rider_y_store,rider_vectors_done
 push bc
 push de
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ld a,#0
 sbc a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
 sra b
 rr c
 rr d
 rr e
 sra b
 rr c
 rr d
 rr e
 sra b
 rr c
 rr d
 rr e
 sra b
 rr c
 rr d
 rr e
 call rider_sat16
 ldhl sp,#10
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 inc hl
 inc hl
 inc hl
 inc hl
 inc hl
 inc hl
 ld (hl),e
 inc hl
 ld (hl),d
 pop de
 pop bc
 sra b
 rr c
 rr d
 rr e
 sra b
 rr c
 rr d
 rr e
 sra b
 rr c
 rr d
 rr e
 sra b
 rr c
 rr d
 rr e
 push bc
 push de
 ldhl sp,#8
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld a,d
 add a,a
 sbc a,a
 ld b,a
 ld c,a
 ldhl sp,#0
 ld a,(hl+)
 add a,e
 ld e,a
 ld a,(hl+)
 adc a,d
 ld d,a
 ld a,(hl+)
 adc a,c
 ld c,a
 ld a,(hl)
 adc a,b
 ld b,a
 add sp,#4
 call rider_sat16
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 inc hl
 inc hl
 ld (hl),e
 inc hl
 ld (hl),d
rider_vectors_done:
 ret

rider_sat16:
 ld a,d
 add a,a
 sbc a,a
 cp c
 jr nz,rider_clamp
 cp b
 ret z
rider_clamp:
 bit 7,b
 jr nz,rider_negative
 ld de,#0x7fff
 ret
rider_negative:
 ld de,#0x8000
 ret

; Add one acceleration to its velocity, advance the matching signed Q24
; residual, and commit the resulting position in the phase helper's DEBC ABI.
.macro rider_move_argument argument
 ldhl sp,#argument
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
.endm

.macro rider_move_axis position, velocity, residual
 ld hl,#(_Bike+velocity)
 ld a,(hl)
 add a,c
 ld c,a
 ld (hl+),a
 ld a,(hl)
 adc a,b
 ld b,a
 ld (hl+),a
 ld a,(hl)
 adc a,e
 ld e,a
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld d,a
 ld (hl),a
 ld hl,#(_move_residual+residual*4+2)
 call _riding_phase_advance_hl
 ld hl,#(_Bike+position)
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
 ld (hl),a
.endm

_riding_rider_move32::
 rider_move_argument 2
 call _riding_rider_move_x_regs
 rider_move_argument 6
 jr _riding_rider_move_y_regs

; Both the stack entry and the response pass the acceleration in DEBC.
_riding_rider_move_x_regs::
 rider_move_axis 72,80,6
 ret
_riding_rider_move_y_regs::
 rider_move_axis 76,84,7
 ret
