; ABI1 DE=circle, BC=contact. DE:BC is the signed32 push. A also
; classifies the result: 0 rejected, 1 accepted without push, 2 push.
; A proven accepted contact that needs no push may return DE:BC=0.
.module physics_contact_filter
.area _CODE
; DE: fractional Y,X. HL: contact. Keep execution in ROM0 across both
; table reads, including the adjustment for each signed coefficient.
fine_fraction:
 ld c,e
 push de
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 push hl
 call fine_product
 pop bc
 push hl
 push de
 ld h,b
 ld l,c
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 push hl             ; length
 ldhl sp,#7
 ld c,(hl)
 call fine_product
 ld a,(#__current_bank)
 ld (#0x2000),a
 jp fine_sum

_riding_fraction_product::
fine_product:
 ld a,c
 or a,a
 jr z,fine_product_zero
 ld a,d
 or a,e
 jr z,fine_product_zero
 bit 7,d
 jp z,_riding_mul16u8_unsigned
 call _riding_mul16u8_unsigned
 ld a,l
 sub a,c             ; unsigned16 minus 65536, times the coordinate
 ld l,a
 ld h,#255
 ret
fine_product_zero:
 ld de,#0
 ld hl,#0
 ret

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
 ld a,(#__current_bank)
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

; With ny=16384 and nx in [-64,-1], the exact fractional dot is
; fy or fy-1. A negative half tie rounds up. For |nx| <=32 even fx=255
; cannot cross the half-unit boundary. Carry reports a certified result.
fine_shallow_fraction:
 ld h,b
 ld l,c
 inc hl
 ld a,(hl+)
 inc a
 jr nz,fine_shallow_miss
 ld a,(hl+)
 or a
 ret nz
 ld a,(hl)
 cp #64
 jr nz,fine_shallow_miss
 ld h,b
 ld l,c
 ld a,(hl)
 cp #192
 jr c,fine_shallow_miss
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

.area _CODE_9
fine_shallow_cut:
 ; floor(8192/abs(nx)), indexed by nx+64. nx=-32..-1 takes no correction.
 .db 128,130,132,134,136,138,141,143,146,148,151,154,157,160,163,167,170,174,178,182,186,190,195,199,204,210,215,221,227,234,240,248
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

 ; For 405..408, both normals in [-4096,16639] and one <=8191 bound
 ; the rounded fraction to [-128,386]. Every such combination is inside
 ; the accepted, no-push band [103547,104857].
 ld a,(hl-)
 add a,#16
 cp a,#81
 jr nc,fine_calculate
 cp a,#48
 jr c,fine_check_wider_x
 dec hl
 ld a,(hl)
 add a,#16
 cp a,#48
 jr c,fine_in_band
 jr fine_calculate
fine_check_wider_x:
 dec hl
 ld a,(hl)
 add a,#16
 cp a,#81
 jr nc,fine_calculate
fine_in_band:
 ld de,#0
 ld bc,#0
 ld a,#1
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
 add a,#2
 cp a,#130
 jr nc,fine_calculate
 ld h,d
 ld l,e
 ld a,(hl)
 inc hl
 inc hl
 inc hl
 inc hl
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
 ld h,d
 ld l,e
 ld e,(hl)
 inc hl
 inc hl
 inc hl
 inc hl
 ld d,(hl)
 ld h,b
 ld l,c
 jp fine_fraction

fine_sum:
 ; Stack: length pointer, raw X product low and high words, fractions.
 ; Both signed products fit signed24. Sum before rounding, including the
 ; carry from their low bytes. BC will hold the rounded Q14 fraction.
 ld b,h
 ld c,l
 ldhl sp,#2
 ld a,(hl+)
 add a,e
 ld a,(hl+)
 adc a,d
 ld d,a
 ld a,(hl+)
 adc a,c
 ld c,a
 ld a,(hl)
 adc a,b
 ld b,a
 ld a,d
 add a,#0x20
 ld d,a
 ld a,c
 adc a,#0
 ld c,a
 ld a,b
 adc a,#0
 ld b,a
 sla d
 rl c
 rl b
 sla d
 rl c
 rl b
 pop hl
 add sp,#6
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
 ld d,#0
 bit 7,(hl)
 jr z,fine_length_positive
 dec d
fine_length_positive:
 ld a,#0
 sbc a,d
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
