; Bound a pivot's angular moment before doing its exact projection.
; U(v) is v for v>=0 and ~v otherwise. Form the signed dot P of
; U(v)//w and tangent>>8, with w=256 or 1024. The exact Q14 dot
; differs from (w/64)*P by at most (w/64)*(ux+uy+131).
;
; With contact length 384..447 and w=256, the inverse slope from P
; to angular moment lies in (1.81,2.12) for full slow pivots and
; (1.19,1.40) for partial slow pivots. Use -2*m or -1.25*m for
; the crossing center, with |m|/4 for its uncertainty. Divide both
; by four when w=1024. For fast pivots use w=1024, crossing center
; -16*m and radius 2*|m| (inverse slope in (14.39,16.76)).
; The remaining radius ux+uy+144 covers the dot error, signed floors,
; Q24 rounding and strict sign tests. A miss uses the exact kernel.
.module physics_pivot_bound
.area _DATA
bound_row_x: .ds 3
bound_row_y: .ds 3
bound_low: .ds 2
bound_high: .ds 2
bound_width: .ds 1
bound_known_side: .ds 1
bound_moment: .ds 2
bound_rejected_length: .ds 1
bound_rejected_sign: .ds 1
bound_ready: .ds 1
.area _CODE_9
_riding_pivot_bound::
 push hl
 push bc
 call bound_classify
 ld e,a
 pop bc
 pop hl
 ld a,e
 or a
 jp z,pair_exact_moment
 dec a
 jr nz,bound_defer_rejection
 pop af
 ld a,#13
 ld (#_riding_pair_moment_side),a
 ld a,#1
 ret
bound_defer_rejection:
 ld a,l                         ; all admitted lengths have high byte 1
 ld (#bound_rejected_length),a
 pop af
 ld (#bound_rejected_sign),a
 ld a,#16
 ld (#_riding_pair_moment_side),a
 jp pair_reject_moment

; DE is the surviving support. A successful support rolls and overwrites
; Q24, as does a nonzero free torque. On a free step with zero torque,
; materialize the deferred rejected pivot before the caller moves the wheel.
_riding_pair_last_support::
 call _riding_pair_supports
 or a
 ret nz
 ld a,(#_riding_pair_moment_side)
 and #16
 ret z
 ld hl,#_riding_pair_impulse
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld bc,#8
 add hl,bc
 ld a,(hl+)
 or (hl)
 inc hl
 or (hl)
 inc hl
 or (hl)
 jp nz,pair_reject_moment
 ld a,(#bound_rejected_sign)
 push af
 ld a,(#bound_rejected_length)
 ld l,a
 ld h,#1
 jp pair_exact_moment

bound_classify:
 ; Admit tangent high digits [-65,64], including slightly widened normals.
 ld a,h
 dec a
 jp nz,bound_miss
 ld a,l
 sub #128
 cp #64
 jp nc,bound_miss
 ld a,(#_riding_pair_tangent+1)
 add #65
 cp #130
 jp nc,bound_miss
 ld a,(#_riding_pair_tangent+3)
 add #65
 cp #130
 jp nc,bound_miss
 ld a,(#_riding_pair_moment_side)
 bit 3,a
 jr nz,bound_project
 call bound_prepare
 ret nc
bound_project:
 ld a,(#bound_known_side)
 or a
 jr nz,bound_choice
 call _riding_pair_bound_gate
 ld a,h
 xor #128
 ld h,a
 ld a,(#bound_low)
 ld c,a
 ld a,l
 sub c
 ld a,(#bound_low+1)
 ld c,a
 ld a,h
 sbc c
 jr c,bound_negative
 ld a,(#bound_high)
 sub l
 ld a,(#bound_high+1)
 sbc h
 jr nc,bound_miss
 ld a,#2
 jr bound_choice
bound_negative:
 ld a,#128
bound_choice:
 ldhl sp,#7
 cp (hl)
 jr nz,bound_reject
 ldhl sp,#2
 ld a,(hl)
 cp #<(_Ct+10)
 jr nz,bound_miss
 ld a,#1
 ret
bound_reject:
 ld a,#2
 ret
bound_miss:
 xor a
 ret

bound_prepare:
 xor a
 ld (#bound_known_side),a
 ld hl,#_riding_pair_moment
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 add a
 sbc a
 cp (hl)
 jp nz,bound_disable
 inc hl
 cp (hl)
 jp nz,bound_disable
 xor d
 cp #32
 jp nc,bound_disable
 ld a,e
 ld (#bound_moment),a
 ld a,d
 ld (#bound_moment+1),a

 ld hl,#_riding_pair_vector
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#bound_row_x+2
 call bound_digit
 jp nc,bound_disable
 ld b,a
 push bc
 ld de,#bound_row_y+2
 call bound_digit
 pop hl
 jp nc,bound_disable
 ld b,a
 ld d,c
 ld a,(#_riding_pair_shift)
 cp #10
 jr z,bound_wide_rows
 ld a,h
 or b
 jr z,bound_narrow_rows
bound_wide_rows:
 srl b
 rr d
 srl b
 rr d
 srl h
 rr l
 srl h
 rr l
 ld a,#1
bound_narrow_rows:
 ld (#bound_width),a
 ld c,l
 ld a,d
 call bound_bind
 ; Keep the signed P in [-32760,32760] even for both extreme digits.
 ld a,h
 or a
 jr z,bound_row_sum
 ld a,l
 cp #249
 jp nc,bound_disable
bound_row_sum:
 push hl
 ld a,(#bound_moment)
 ld e,a
 ld a,(#bound_moment+1)
 ld d,a
 add a
 sbc a
 ld c,a
 xor d
 ld b,a
 ld a,c
 xor e
 ld c,a
 xor a
 sub e
 ld e,a
 ld a,#0
 sbc d
 ld d,a                          ; DE=-m, BC=U(m)
 ld a,(#_riding_pair_shift)
 cp #10
 jr z,bound_fast_center
 ld h,d
 ld l,e
 ld a,(#_riding_subphase)
 or a
 jr z,bound_full_center
 sra d
 rr e
 sra d
 rr e
 add hl,de
 jr bound_slow_radius
bound_full_center:
 add hl,hl
bound_slow_radius:
 srl b
 rr c
 srl b
 rr c
 ld a,(#bound_width)
 or a
 jr z,bound_thresholds
 sra h
 rr l
 sra h
 rr l
 srl b
 rr c
 srl b
 rr c
 jr bound_thresholds

bound_fast_center:
 ; Even at the largest admitted length, each 1024 velocity units
 ; at maximum tangent magnitude contributes fewer than 4.5 angular
 ; units. (ux+uy+2)*5 dominates both rounded products.
 push bc
 ld bc,#2
 add hl,bc
 ld b,h
 ld c,l
 add hl,hl
 add hl,hl
 add hl,bc
 pop bc
 ld a,c
 sub l
 ld a,b
 sbc h
 jr nc,bound_fast_dominant
 ld a,b
 cp #4
 jr nc,bound_fast_unknown
 ld h,d
 ld l,e
 .rept 4
 add hl,hl
 .endm
 sla c
 rl b
bound_thresholds:
 ld d,h
 ld e,l
 pop hl
 add hl,bc
 ld bc,#144
 add hl,bc
 ld b,h
 ld c,l
 add hl,de
 ld a,l
 ld (#bound_high),a
 ld a,h
 xor #128
 ld (#bound_high+1),a
 ld a,e
 sub c
 ld (#bound_low),a
 ld a,d
 sbc b
 xor #128
 ld (#bound_low+1),a
 jr bound_activate
bound_fast_dominant:
 pop hl
 ld a,(#bound_moment+1)
 and #128
 jr nz,bound_store_side
 ld a,#2
bound_store_side:
 ld (#bound_known_side),a
bound_activate:
 ld a,#12
 ld (#_riding_pair_moment_side),a
 scf
 ret
bound_fast_unknown:
 pop hl
bound_disable:
 xor a
 ld (#_riding_pair_moment_side),a
 ret

; Compute U(v)>>8 up to ten bits, keeping the sign at DE.
bound_digit:
 inc hl
 ld c,(hl)
 inc hl
 ld a,(hl+)
 ld b,(hl)
 inc hl
 push af
 ld a,b
 inc a
 jr z,bound_digit_ok
 dec a
 jr z,bound_digit_ok
 pop af
 or a
 ret
bound_digit_ok:
 ld a,b
 ld (de),a
 xor c
 ld c,a
 pop af
 xor b
 cp #4
 ret
; A=Y magnitude, C=X magnitude. Return their sum, retaining the two
; directory rows for the subsequent pivot at this same wheel state.
bound_bind:
 ld b,a
 ld l,c
 ld h,#>_riding_scale_directory
 ld a,(hl)
 ld (#bound_row_x),a
 inc h
 ld a,(hl)
 ld (#bound_row_x+1),a
 ld l,b
 ld a,(hl)
 ld (#bound_row_y+1),a
 dec h
 ld a,(hl)
 ld (#bound_row_y),a
 ld h,#0
 ld l,c
 ld c,b
 ld b,h
 add hl,bc
 ret

.area _CODE
; Called by cold course setup and also by standalone wheel entry points.
; Fixed-ROM VBlank preserves registers and the hardware ROM/RAM windows.
_riding_prepare_pair_bound::
 ld a,(#bound_ready)
 or a
 ret nz
 push hl
 push bc
 ldh a,(#__current_bank)
 push af
 ld a,#251
 ld (#0x2000),a
 ld a,#1
 ld (#0x3000),a
 call pair_bound_install
 xor a
 ld (#0x3000),a
 pop af
 ld (#0x2000),a
 pop bc
 pop hl
 ret

.area _CODE_507
pair_bound_install::
 ld a,#10
 ld (#0),a
 xor a
 ld (#0x4000),a
 ld hl,#pair_bound_image
 ld de,#_riding_pair_bound_gate
 ld b,#(pair_bound_image_end-pair_bound_image)
bound_copy:
 ld a,(hl+)
 ld (de),a
 inc de
 dec b
 jr nz,bound_copy
 inc b
 ld a,b
 ld (#bound_ready),a
 ret

.globl _riding_pair_bound_gate
_riding_pair_bound_gate = 0xa570
; The SRAM reader maps both byte-product rows, then restores bank 9.
; The head maps that precede it stay at their linked offsets.
pair_bound_image::
bound_products_image:
 ld hl,#bound_row_x
 ld a,(#_riding_pair_tangent+1)
 call bound_term
 push bc
 ld hl,#bound_row_y
 ld a,(#_riding_pair_tangent+3)
 call bound_term
 pop hl
 add hl,bc
 ld a,#9
 ld (#0x2000),a
 ret
bound_term_image:
 ld c,a
 ld a,(hl+)
 ld (#0x2000),a
 ld a,(hl+)
 ld b,(hl)
 ld h,a
 ld a,c
 xor b
 ld b,a
 ld a,c
 bit 7,a
 jr z,bound_magnitude
 cpl
 inc a
bound_magnitude:
 ld l,a
 ld c,(hl)
 inc h
 ld a,(hl)
 bit 7,b
 ld b,a
 ret z
 xor a
 sub c
 ld c,a
 ld a,#0
 sbc b
 ld b,a
 ret
pair_bound_image_end::
.ifgt pair_bound_image_end-pair_bound_image-144
 .error 1
.endif
bound_term = (bound_term_image-pair_bound_image)+0xa570
