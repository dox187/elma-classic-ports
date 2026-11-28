; Full-phase slow wheel pivot. With U(a)=a for a>=0 and ~a otherwise,
; w is 256, or 1024 if either impulse needs a wider digit. u=U(v)//w.
; Multiply both signed u digits by their signed tangent high bytes and sum
; to P. In these units the original dot differs from P by at most
; ux+uy+131: each discarded velocity magnitude <= w, each omitted Q14
; byte <256, each high coefficient is in [-64,64], and the dot rounds once.
;
; For w=256 the moment increment per unit P is
; alpha=4*length*C_OLD[0]/(64*2^24). Inside the checked length range and
; build coefficient range, 1/alpha is strictly between 2-1/8 and 2+1/8.
; Thus -2*tq bounds the zero crossing to within U(tq)//8+ux+uy+136.
; The extra units cover the signed floors, positive-half Q24 tie and strict
; sign test. At w=1024 divide the torque center and its radius by four.
; An interval hit can defer the first accepted pivot or reject either one.
; A second accepted pivot always publishes its exact Q24 fraction. If its
; geometry separation rounds to zero the existing replay restores the first.
.module physics_pivot_bound
.area _DATA
; Each bound row stores the multiply-table bank, page and velocity sign.
bound_row_x: .ds 3
bound_row_y: .ds 3
bound_low: .ds 2
bound_high: .ds 2
bound_ready: .ds 1
.area _CODE_476
_riding_pivot_bound::
 ; HL=length, checked before accessing the current pair's cached interval.
 ld a,h
 dec a
 jp nz,bound_miss
 ld a,l
 sub #128
 cp #32
 jp nc,bound_miss
 ld a,(#_riding_pair_moment_side)
 bit 3,a
 jr nz,bound_project
 call bound_prepare
 ret nc
bound_project:
 ld a,(#_riding_pair_tangent+1)
 add #64
 cp #129
 jp nc,bound_miss
 ld a,(#_riding_pair_tangent+3)
 add #64
 cp #129
 jp nc,bound_miss
 call bound_products
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
 ; Limit |tq| so the signed interval endpoints fit a word.
 ld hl,#_riding_pair_moment
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 add #32
 cp #64
 jp nc,bound_disable
 ld a,d
 add a
 sbc a
 cp (hl)
 jp nz,bound_disable
 inc hl
 cp (hl)
 jp nz,bound_disable
 ; T=-2*tq, R=floor(U(tq)/8)+ux+uy+136.
 xor d
 ld b,a
 ld a,d
 add a
 sbc a
 xor e
 ld c,a
 srl b
 rr c
 srl b
 rr c
 srl b
 rr c
 push bc
 xor a
 sub e
 ld l,a
 ld a,#0
 sbc d
 ld h,a
 add hl,hl
 push hl
 ld hl,#_riding_pair_vector
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#bound_row_x+2
 call bound_digit
 jr nc,bound_failed
 ld b,a
 push bc
 ld de,#bound_row_y+2
 call bound_digit
 pop hl                          ; X magnitude, in units of 256
 jr nc,bound_failed
 ld b,a
 ld d,c                          ; Y magnitude, in the same units
 ld a,h
 or b
 jr z,bound_narrow_rows
 srl b
 rr d
 srl b
 rr d
 srl h
 rr l
 srl h
 rr l
 ld c,l
 ld a,d
 call bound_bind
 pop de
 sra d
 rr e
 sra d
 rr e
 pop bc
 srl b
 rr c
 srl b
 rr c
 jr bound_thresholds
bound_narrow_rows:
 ld c,l
 ld a,d
 call bound_bind
 pop de
 pop bc
bound_thresholds:
 add hl,bc
 ld bc,#136
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
 ld a,#12
 ld (#_riding_pair_moment_side),a
 scf
 ret
bound_failed:
 add sp,#4
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

_riding_pair_bound_end::
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
; SRAM0 holds the mapped call and both byte-product reads. The image also
; addresses two entry points in bank 9 after restoring the low and high
; MBC5 registers. The head maps that precede it stay at their linked offsets.
pair_bound_image::
 push hl
 push bc
 ld a,#220
 ld (#0x2000),a
 ld a,#1
 ld (#0x3000),a
 call _riding_pivot_bound
 ld e,a
 xor a
 ld (#0x3000),a
 ld a,#9
 ld (#0x2000),a
 pop bc
 pop hl
 ld a,e
 or a
 jp z,pair_exact_moment
 pop bc
 dec a
 jp nz,pair_reject_moment
 ld a,#13
 ld (#_riding_pair_moment_side),a
 ld a,#1
 ret
bound_products_image:
 xor a
 ld (#0x3000),a
 ld hl,#bound_row_x
 ld a,(#_riding_pair_tangent+1)
 call bound_term
 push bc
 ld hl,#bound_row_y
 ld a,(#_riding_pair_tangent+3)
 call bound_term
 pop hl
 add hl,bc
 ld a,#220
 ld (#0x2000),a
 ld a,#1
 ld (#0x3000),a
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
bound_products = (bound_products_image-pair_bound_image)+0xa570
bound_term = (bound_term_image-pair_bound_image)+0xa570
