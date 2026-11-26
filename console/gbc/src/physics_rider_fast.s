; Exact rider vectors and motion, packed bike119, stack ABI0, ROM bank8.
; Bike: body.rx0 ry4, rider_x72 y76 vx80 vy84.
; Vectors(restx,resty,out) writes dirx,diry,dx,dy as signed16.
; dir = sat16((wrap32(body-rider) >> 4) + signed16(rest));
; delta = sat16(wrap32(rider-body) >> 4).
; Move(ax,ay) adds accelerations, then advances scheduled motion and residuals.
; All motion arithmetic wraps modulo2^32. No mutable global scratch.
.module physics_rider_fast
.area _CODE_8

; The response reserves its four vectors on the stack. The public ABI
; adapter uses the same frame then copies it to the supplied buffer.
_riding_rider_vectors32::
 add sp,#-8
 call _riding_rider_vectors_frame
 ldhl sp,#14
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ldhl sp,#0
 .rept 8
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 add sp,#8
 ret

; Both callers have eight local bytes followed by their return address
; and restx/resty. Each axis reads the two positions only once.
_riding_rider_vectors_frame::
.macro rider_vector_axis position,rider,rest,output
 ld hl,#(_Bike+rider)
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ld hl,#(_Bike+position)
 ld a,(hl+)
 sub e
 ld e,a
 ld a,(hl+)
 sbc d
 ld d,a
 ld a,(hl+)
 sbc c
 ld c,a
 ld a,(hl)
 sbc b
 ld b,a
 ldhl sp,#rest
 call rider_vector_axis_regs
 ldhl sp,#output
 ld (hl),e
 inc hl
 ld (hl),d
 ldhl sp,#(output+4)
 ld (hl),c
 inc hl
 ld (hl),b
.endm
 rider_vector_axis 0,72,12,2
 rider_vector_axis 4,76,14,4
 ret

; Input BCDE is body minus rider modulo 2^32, HL points to signed rest.
; Return spring displacement in DE, reverse displacement in BC.
rider_vector_axis_regs:
 push hl
 ld a,c
 add #8
 and #0xf0
 jr nz,rider_vector_wide
 ld a,c
 rlca
 sbc a,a
 cp b
 jr nz,rider_vector_wide
 ld a,e
 and #15
 ld h,a
.macro rider_drop_nibble low,high
 ld a,high
 xor low
 and #15
 xor low
 swap a
 ld low,a
.endm
 rider_drop_nibble e,d
 rider_drop_nibble d,c
 ; Reverse quotient = ~q + (remainder == 0). Only the narrow endpoint
 ; -524288 needs positive saturation after negating the displacement.
 ld a,h
 sub #1
 ld a,e
 cpl
 adc #0
 ld c,a
 ld a,d
 cpl
 adc #0
 ld b,a
 and d
 bit 7,a
 jr z,rider_vector_sum
 ld bc,#0x7fff
rider_vector_sum:
 pop hl
 ld a,(hl+)
 add e
 ld e,a
 ld a,(hl)
 ld h,a
 adc d
 ld l,a
 xor d
 ld d,a
 ld a,h
 xor l
 and d
 ld d,l
 bit 7,a
 ret z
 ld de,#0x7fff
 bit 7,l
 ret nz
 inc de
 ret

rider_vector_wide:
 ; Outside signed20 the reverse quotient always clamps. INT32_MIN
 ; negates to itself under the wrapped subtraction and clamps negative.
 ld hl,#0x8000
 bit 7,b
 jr z,rider_vector_clamped
 ld a,b
 xor #0x80
 or c
 or d
 or e
 jr z,rider_vector_clamped
 dec hl
rider_vector_clamped:
 push hl
 rider_drop_nibble e,d
 rider_drop_nibble d,c
 rider_drop_nibble c,b
 ld a,b
 swap a
 and #15
 bit 7,b
 jr z,rider_vector_shifted
 or #0xf0
rider_vector_shifted:
 ld b,a
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(hl+)
 add e
 ld e,a
 ld a,(hl)
 ld h,a
 adc d
 ld d,a
 bit 7,h
 ld a,#0
 jr z,rider_vector_extend
 dec a
rider_vector_extend:
 ld h,a
 adc c
 ld c,a
 ld a,h
 adc b
 ld b,a
 call rider_sat16
 pop bc
 add sp,#2
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
