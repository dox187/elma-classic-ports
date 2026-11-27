; Two prepared contacts are resolved in iterator order. Ct and the wheel
; query are serial. Velocities, impulses and their wide projections stay
; signed32; the separation sign belongs only to the geometry.
.module physics_ordered_pair
.area _DATA
pair_tangent: .ds 4
_riding_pair_normal::
pair_normal: .ds 2
pair_nv: .ds 4

.area _CODE_9
; DE = pivot (Ct[0] or Ct[1]), BC = its rounded separation-sign cell.
_riding_pair_sure::
 push bc
 push de
 ld h,d
 ld l,e
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 xor a
 sub e
 ld e,a
 ld a,#0
 sbc d
 ld d,a
 ld hl,#pair_tangent
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ld (hl),c
 inc hl
 ld (hl),b
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(hl)
 or a
 jr nz,pair_have_sign
 ; Form both signed16 differences with the same wrap as the C ABI.
 pop hl
 push hl
 ld de,#6
 add hl,de
 ld de,#(_Ct+6)
 ld a,l
 cp e
 jr nz,pair_other_point
 ld de,#(_Ct+16)
pair_other_point:
 ld a,(de)
 sub (hl)
 ld c,a
 inc de
 inc hl
 ld a,(de)
 sbc (hl)
 ld b,a
 push bc
 inc de
 inc hl
 ld a,(de)
 sub (hl)
 ld c,a
 inc de
 inc hl
 ld a,(de)
 sbc (hl)
 ld b,a
 pop de
 push de
 push bc
 call pair_separation_bound
 pop bc
 pop de
 or a
 jr nz,pair_store_sign
 ld hl,#pair_tangent+2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 ld hl,#pair_tangent
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 jp pair_geometry_dot
pair_geometry_sign:
 bit 7,b
 ld a,#128
 jr nz,pair_store_sign
 ld a,b
 or c
 ld a,#1
 jr z,pair_store_sign
 inc a
pair_store_sign:
 ld c,a
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld (hl),c
 ld a,c
pair_have_sign:
 cp #1
 jr nz,pair_project
 ; Rounded zero does not evaluate Q24 or change its reported fraction.
 add sp,#4
 ret
pair_project:
 pop hl
 pop bc
 ; HL=pivot, A=separation sign. Save the length and sign through the dot.
 push af
 inc hl
 inc hl
 inc hl
 inc hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ; A proved rejection ends in rolling or a free response that replaces
 ; Q24. Accepted pivots still publish their exact fraction in case two
 ; supports eventually hold.
 ld a,h
 cp #2
 jr nc,pair_exact_moment
 ld a,(#_riding_pair_moment_side)
 or a
 jr z,pair_exact_moment
 ld b,a
 pop af
 cp b
 jr nz,pair_reject_moment
 push af
pair_exact_moment:
 push hl
 ld hl,#_riding_pair_vector
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 ld hl,#pair_tangent
 call _riding_dotq14_regs
 pop bc
 call pair_length_scale
 ld a,(#_riding_pair_coefficient)
 dec sp
 call _q24_apply_a
 ld hl,#_riding_pair_moment
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(hl+)
 add c
 ld c,a
 ld a,(hl+)
 adc b
 ld b,a
 ld a,(hl+)
 adc e
 ld e,a
 ld a,(hl)
 adc d
 ld d,a
 pop af
 ; m=0 is supported on either side. Otherwise the signs must agree.
 xor d
 bit 7,a
 jr z,pair_true
 ld a,d
 or e
 or b
 or c
 jr z,pair_true
 xor a
 ret
pair_reject_moment:
 xor a
 ret
pair_true:
 ld a,#1
 ret

.area _CODE
 ; DE=dx and BC=dy. U(v) is v for v>=0 and ~v otherwise, so
 ; U(v)<=abs(v)<=U(v)+1. A strictly larger U identifies a coordinate
 ; at least as large in magnitude. Limit both U values to 16383 to
 ; exclude signed32 overflow in the reference geometry dot.
pair_separation_bound:
 ld a,d
 add a
 sbc a
 ld h,a
 xor e
 ld e,a
 ld a,h
 xor d
 ld d,a
 ld a,b
 add a
 sbc a
 ld l,a
 xor c
 ld c,a
 ld a,l
 xor b
 ld b,a
 ld a,c
 sub e
 ld a,b
 sbc d
 jr c,pair_larger_x
 ld a,b
 xor d
 jr nz,pair_larger_y
 ld a,c
 cp e
 jr z,pair_bound_unknown
pair_larger_y:
 ld a,h
 ld h,l
 ld l,a
 ld a,(#pair_tangent+3)
 ld d,a
 ld a,(#pair_tangent+1)
 ld e,a
 jr pair_compare_terms
pair_larger_x:
 ld b,d
 ld c,e
 ld a,(#pair_tangent+1)
 ld d,a
 ld a,(#pair_tangent+3)
 ld e,a
pair_compare_terms:
 ld a,b
 cp #64
 jr nc,pair_bound_unknown
 or a
 jr nz,pair_compare_normals
 ld a,c
 cp #33
 jr c,pair_bound_unknown
pair_compare_normals:
 ; The dominant coordinate has magnitude at least 33. With like-signed
 ; terms a coefficient of at least 256 already exceeds the half-Q14 tie.
 ; With opposite signs, a two-bin lead in U(coefficient)>>8 gives a
 ; coefficient difference of at least 256, with the same strict margin.
 ld a,d
 xor h
 ld b,a
 ld a,d
 add a
 sbc a
 xor d
 jr z,pair_bound_unknown
 ld d,a
 ld a,e
 xor l
 xor b
 bit 7,a
 jr z,pair_bound_known
 ld a,e
 add a
 sbc a
 xor e
 inc a
 inc a
 cp d
 jr z,pair_bound_known
 jr nc,pair_bound_unknown
pair_bound_known:
 ld a,b
 and #128
 ret nz
 ld a,#2
 ret
pair_bound_unknown:
 xor a
 ret

; A signed 18-bit tangent times 256+k fits signed32. Look up low16*k once,
; then add low16<<8 and the signed high word times the contact length.
.area _CODE_9
pair_length_scale::
 ld a,b
 dec a
 jr nz,pair_length_general
 ld a,h
 inc a
 cp #2
 jr nc,pair_length_general
 ld a,h
 xor l
 cp #2
 jr nc,pair_length_general
 ld a,l
 jp pair_length_product

.area _CODE
pair_length_product:
 push af
 push bc
 push de
 call _riding_mul16u8_unsigned
 ld a,#9
 ld (#0x2000),a
 pop bc
 ld a,d
 add c
 ld d,a
 ld a,l
 adc b
 ld l,a
 ld a,h
 adc #0
 ld h,a
 pop bc
 pop af
 or a
 jp z,pair_length_shift
 bit 7,a
 jr z,pair_add_length
 inc a
 jr z,pair_sub_length
 sla c
 rl b
pair_sub_length:
 ld a,l
 sub c
 ld l,a
 ld a,h
 sbc b
 ld h,a
 jp pair_length_shift
pair_add_length:
 add hl,bc
 jp pair_length_shift
.area _CODE_9
pair_length_general:
 ld a,d
 add a
 sbc a
 cp h
 jr nz,pair_wide_product
 cp l
 jr nz,pair_wide_product
 call _riding_mul16_regs
pair_length_shift:
 ld a,(#_riding_pair_shift)
 cp #6
 jr nz,pair_new_product
 ; arshift32(product,6) = signed integer above the lowest byte of 4*product.
 ld a,h
 add a
 sbc a
 sla e
 rl d
 rl l
 rl h
 rla
 sla e
 rl d
 rl l
 rl h
 rla
 jr pair_narrow_result
pair_new_product:
 sra h
 rr l
 rr d
 sra h
 rr l
 rr d
 ld a,h
 add a
 sbc a
pair_narrow_result:
 ld c,d
 ld b,l
 ld e,h
 ld d,a
 ret
pair_wide_product:
 ld a,(#_riding_pair_shift)
 push af
 inc sp
 push bc
 push hl
 push de
 call _riding_mulshift32
 add sp,#7
 ld b,d
 ld c,e
 ld d,h
 ld e,l
 ret

.area _CODE_9
; DE=contact. Accept and remove its inward normal velocity, or reject
; without mutation. Each call reads the velocity left by the previous one.
_riding_pair_supports::
 ld hl,#pair_normal
 ld (hl),e
 inc hl
 ld (hl),d
 ld a,(#_riding_pair_stopped)
 or a
 jr nz,pair_zero_velocity
 ld hl,#_riding_pair_velocity
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld b,d
 ld c,e
 ld d,h
 ld e,l
 ld h,b
 ld l,c
 call _riding_dotq14_regs
 ld a,h
 or l
 or d
 or e
 jr z,pair_zero_velocity
 ld b,h
 ld c,l
 ld hl,#pair_nv
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ld (hl),c
 inc hl
 ld (hl),b
 ; nv <= -ELSZ accepts even when the impulse points outward.
 bit 7,b
 jr z,pair_nonzero_velocity
 ld a,b
 and c
 and d
 inc a
 jr nz,pair_remove
 ld a,(#_riding_supports_threshold)
 or a
 jr z,pair_remove
 cp e
 jr z,pair_nonzero_velocity
 jr nc,pair_remove
pair_nonzero_velocity:
 call pair_inward_impulse
 or a
 ret z
pair_remove:
 ld hl,#pair_normal
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 push hl
 ld hl,#pair_nv
 call _riding_mulq14_regs
 ld b,h
 ld c,l
 ld hl,#_riding_pair_velocity
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call pair_subtract
 inc hl
 pop bc
 push hl
 ld h,b
 ld l,c
 ld c,(hl)
 inc hl
 ld b,(hl)
 ld hl,#pair_nv
 call _riding_mulq14_regs
 ld b,h
 ld c,l
 pop hl
 call pair_subtract
 jp pair_true
pair_subtract:
 ld a,(hl)
 sub e
 ld (hl+),a
 ld a,(hl)
 sbc d
 ld (hl+),a
 ld a,(hl)
 sbc c
 ld (hl+),a
 ld a,(hl)
 sbc b
 ld (hl),a
 ret
pair_zero_velocity:
 ; nv=0 changes neither component. A rounded nonpositive impulse supports.
pair_inward_impulse:
 ld hl,#_riding_pair_impulse
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 ld hl,#pair_normal
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push de
 push hl
 inc de
 inc de
 inc de
 ld c,(hl)
 inc hl
 ld b,(hl)
 ld a,(de)
 xor b
 bit 7,a
 jr nz,pair_impulse_y
 ld a,b
 or c
 jr nz,pair_impulse_dot
pair_impulse_y:
 inc de
 inc de
 inc de
 inc de
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 ld a,(de)
 xor b
 bit 7,a
 jr nz,pair_inward
 ld a,b
 or c
 jr z,pair_inward
pair_impulse_dot:
 add sp,#4
 ld e,#93
 ld hl,#_riding_pair_impulse_bound
 jp ___sdcc_bcall_ehl
pair_inward:
 add sp,#4
pair_supported:
 ld a,#1
 ret

.area _CODE
; The ordered terrain dot takes and removes both tangent words on the
; stack. Return through fixed ROM before continuing in the wheel bank.
pair_geometry_dot:
 ld a,#93
 ld (#__current_bank),a
 ld (#0x2000),a
 call terrain_record_dot
 ld a,#9
 ld (#__current_bank),a
 ld (#0x2000),a
 jp pair_geometry_sign
