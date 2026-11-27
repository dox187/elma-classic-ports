; ABI1 DE=circle, BC=contact. DE:BC is the signed32 push. A also
; classifies the result: 0 rejected, 1 accepted without push, 2 push.
; A proven accepted contact that needs no push may return DE:BC=0.
.module physics_contact_filter
.area _CODE
; DE: fractional Y,X. HL: contact. Keep execution in ROM0 across both
; table reads, including the adjustment for each signed coefficient.
fine_fraction:
 ld c,e
 ld b,d
 push hl
 call _riding_fraction_pair
 pop hl
 .rept 4
 inc hl
 .endm
 ; DE is the raw low word and BC the signed high word. The component
 ; pointer now addresses length. The low product bytes already propagated.
 ld a,d
 add #32
 ld d,a
 ld a,c
 adc #0
 ld c,a
 ld a,b
 adc #0
 ld b,a
 sla d
 rl c
 rl b
 sla d
 rl c
 rl b
 jp fine_length

; Positive push 1..255, no other contact. DE=wheel, BC=contact, A=push.
; Both rounded projections share the same unsigned-byte-product table row.
; The low product byte cannot reach the rounding bit and is never fetched.
_riding_push_byte::
 push de
 ld d,b
 ld e,c
 ld c,a
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
 ld b,a
 call fine_push_component
 push hl
 call fine_push_component
 bit 7,c
 jr z,fine_push_length_done
 ld a,(de)
 inc a
 ld (de),a
 jr nz,fine_push_length_done
 inc de
 ld a,(de)
 inc a
 ld (de),a
fine_push_length_done:
 ldh a,(#__current_bank)
 ld (#0x2000),a
 pop bc
 pop de
 push hl
 ld h,d
 ld l,e
 call fine_add_position
 pop bc
 jp fine_add_position

; B=table page, C=push, DE advances over each signed normal, HL=result.
fine_push_component:
 ld a,(de)
 inc de
 ld l,a
 ld h,b
 inc h
 ld a,(de)
 inc de
 push de
 ld d,(hl)
 ld l,a
 dec h
 ld a,(hl)
 add a,d
 ld d,a
 inc h
 ld a,(hl)
 adc a,#0
 bit 7,l
 jr z,fine_push_unsigned
 sub a,c
fine_push_unsigned:
 ld l,a
 add a,a
 sbc a,a
 ld h,a
 ld a,d
 add a,#0x20
 jr nc,fine_push_round
 inc hl
fine_push_round:
 add a,a
 rl l
 rl h
 add a,a
 rl l
 rl h
 pop de
 ret

; With ny=16384 and nx in [-64,32], the exact fractional dot is
; fy or fy-1. A negative half tie rounds up. For |nx| <=32 even fx=255
; cannot cross the half-unit boundary. Carry reports a certified result.
fine_shallow_fraction:
 ld h,b
 ld l,c
 inc hl
 inc hl
 ld a,(hl+)
 or a
 ret nz
 ld a,(hl-)
 cp #64
 jr nz,fine_shallow_miss
 dec hl
 ld a,(hl-)
 or a
 jr z,fine_minor_positive
 inc a
 jr nz,fine_shallow_miss
 ld a,(hl)
 cp #192
 jr c,fine_shallow_miss
 jr fine_minor_position
fine_minor_positive:
 ld a,(hl)
 cp #33
 jr nc,fine_shallow_miss
 ld a,#255                     ; |nx| <=32 contributes exactly zero
fine_minor_position:
 push hl
 ld h,d
 ld l,e
 ld e,(hl)
 .rept 4
 inc hl
 .endm
 ld d,(hl)
 cp #224
 jr nc,fine_shallow_result
 sub #192
 add a,#<fine_shallow_cut
 ld l,a
 ld a,#>fine_shallow_cut
 adc a,#0
 ld h,a
 ld a,(hl)
 cp e
fine_shallow_result:
 ld a,d
 sbc a,#0
 ld c,a
 sbc a,a
 ld b,a
 pop hl
 .rept 4
 inc hl
 .endm
 scf
 ret
fine_shallow_miss:
 or a
 ret

fine_shallow_cut:
 ; floor(8192/abs(nx)), indexed by nx+64. nx=-32..-1 takes no correction.
 .db 128,130,132,134,136,138,141,143,146,148,151,154,157,160,163,167,170,174,178,182,186,190,195,199,204,210,215,221,227,234,240,248
.area _CODE_9
_riding_contact_push::
 ld h,b
 ld l,c
 inc hl
 inc hl
 inc hl
 inc hl
 ld a,(hl+)
 sub a,#148
 cp a,#5
 jp nc,fine_calculate
 ld a,(hl-)
 dec a
 jp nz,fine_calculate
 ld a,(hl-)
 cp a,#148
 jr z,fine_surface

 ; For lengths 405..408 the accepted no-push interval contains every
 ; rounded fractional dot in [-133,409]. Each coordinate in [-4096,
 ; 16639] contributes at least -64. If both coefficients are positive,
 ; their high-byte sum <=100 bounds their sum by 26110 and the rounded
 ; dot by 406. A negative term leaves at most one positive contribution.
 ld a,(hl-)
 add #16
 cp #81
 jr nc,fine_calculate
 dec hl
 add (hl)                     ; ny high + 16 + signed nx high, modulo 256
 cp #117
 jr nc,fine_calculate
 ld a,(hl)
 add #16
 cp #81
 jr nc,fine_calculate
fine_in_band:
 xor a
 ld d,a
 ld e,a
 ld b,a
 ld c,a
 inc a
 ret

fine_surface:
 ; At length 404 even the full signed16 maximum dot cannot reject.
 ; If a major normal >=16368 and the other >=-512, the rounded dot
 ; is >= major_byte-floor((other_byte+23)/32), since major_byte<=255.
 ; Check either major direction. Equality at 123 needs no push.
 ld a,(hl-)
 bit 7,a
 jr nz,fine_surface_x
 cp a,#0x3f
 jr c,fine_surface_x
 jr nz,fine_surface_y_high
 ld a,(hl)
 cp a,#0xf0
 jr c,fine_surface_x
fine_surface_y_high:
 dec hl
 ld a,(hl)
 bit 7,a
 jr nz,fine_surface_y_negative
 ; At fy=123, even the smallest admitted positive major rounds to
 ; 123. Any nonnegative minor can only increase the fractional dot.
 ld hl,#4
 add hl,de
 ld a,(hl)
 cp #123
 jr nc,fine_in_band
 jr fine_calculate
fine_surface_y_negative:
 add a,#2
 cp a,#130
 jr nc,fine_calculate
 ld hl,#4
 add hl,de
 ld a,(de)
 jr fine_surface_bound
fine_surface_x:
 ; HL points to ny low. The high byte bounds the complete signed minor.
 inc hl
 ld a,(hl-)
 add a,#2
 cp a,#130
 jr nc,fine_calculate
 dec hl
 ld a,(hl-)
 bit 7,a
 jr nz,fine_calculate
 cp a,#0x3f
 jr c,fine_calculate
 jr nz,fine_surface_x_high
 ld a,(hl)
 cp a,#0xf0
 jr c,fine_calculate
fine_surface_x_high:
 ld hl,#4
 add hl,de
 ld a,(hl)
 ld h,d
 ld l,e
fine_surface_bound:
 ; floor((byte+23)/32) including the ninth bit.
 add a,#23
 rra
 rrca
 rrca
 rrca
 rrca
 and a,#15
 add a,#123
 cp a,(hl)
 jr c,fine_in_band
 jr z,fine_in_band
fine_calculate:
 call fine_shallow_fraction
 jr c,fine_length
 ld hl,#4
 add hl,de
 ld a,(de)
 ld e,a
 ld d,(hl)
 ld h,b
 ld l,c
 jp fine_fraction

fine_length:
 ; push=(404-length)*256 + (123-fraction). For all signed16 normals,
 ; 123-fraction is in [-897,1143]. Its high byte is in [-4,4].
 ld a,#123
 sub a,c
 ld c,a
 ld a,#0
 sbc a,b
 add a,#0x94
 sub a,(hl)
 ld b,a
 inc hl
 ld a,#1
 sbc a,(hl)
 ld e,a
 ld a,#0
 sbc a                         ; sign-extend the borrowed length high byte
 bit 7,(hl)
 jr z,fine_length_positive
 inc a                         ; subtracting a negative length adds 65536
fine_length_positive:
 ld d,a
 bit 7,d
 jr nz,fine_negative
 or a,e
 or a,b
 or a,c
 ld a,#2
 ret nz
 dec a
 ret
fine_negative:
 ; The strict acceptance boundary is push > -1311 (0xfffffae1).
 and a,e
 inc a
 jr nz,fine_reject
 ld a,b
 cp a,#0xfa
 jr c,fine_reject
 jr nz,fine_no_push
 ld a,#0xe1
 cp a,c
 jr nc,fine_reject
fine_no_push:
 ld a,#1
 ret
fine_reject:
 xor a,a
 ret

; Add signed16 BC to the signed32 position and leave HL at the next axis.
fine_add_position:
 ld a,b
 add a,a
 sbc a,a
 ld d,a
 ld a,(hl)
 add a,c
 ld (hl+),a
 ld a,(hl)
 adc a,b
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld (hl+),a
 ret
