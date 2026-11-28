; Stationary ordered contacts. Bank 5 holds the signed margins and reader.
; Return 0 for an unproved input, 2 for positive first-pivot moment or 128
; for negative. Each nonzero result also proves both normal impulses <= 0.
.module physics_stopped_pair
.area _CODE_5
.globl b_riding_stopped_pair_proof
b_riding_stopped_pair_proof = 5
_riding_stopped_pair_proof::
 ld hl,#(_Ct+14)
 ld a,(hl+)
 and #192
 cp #128
 jp nz,stopped_unknown
 ld a,(hl)
 dec a
 jp nz,stopped_unknown
 jp stopped_match

stopped_check:
 ld hl,#_Ct
 call stopped_four_bytes
 jp nz,stopped_unknown
 ld hl,#(_Ct+10)
 call stopped_four_bytes
 jp nz,stopped_unknown
 ld a,(de)
 ld c,a
 inc de
 ld a,(de)
 ld b,a
stopped_table:
 push bc                       ; geometry's first table row
 ld hl,#_riding_pair_impulse
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 inc hl
 call stopped_digit
 sub #16                       ; x in [-65536,32767], 24 columns
 cp #24
 jr nc,stopped_drop
 ld e,a
 sub #15
 cp #2
 jr nc,stopped_x_ready
 ; Split the two cells nearest zero into four exact 1024-unit columns each.
 ; HL points to dy; byte 1 of dx supplies bits 10 and 11.
 add a,a
 add a,a
 add #24
 ld e,a
 dec hl
 dec hl
 dec hl
 ld a,(hl+)
 inc hl
 inc hl
 rrca
 rrca
 and #3
 add e
 ld e,a
stopped_x_ready:
 inc hl
 call stopped_digit
 sub #12                       ; y in [-81920,-1], 20 rows
 cp #20
 jr nc,stopped_drop
 ; HL now points to the four torque bytes. Save the bounded signed word.
 ld c,(hl)
 inc hl
 ld b,(hl)
 inc hl
 ld d,a
 ld a,b
 add a,a
 sbc a,a
 cp (hl)
 jr nz,stopped_drop
 inc hl
 cp (hl)
 jr nz,stopped_drop
 pop hl
 push bc
 ld c,e
 ld b,#0
 add hl,bc
 ld c,d
 ld e,l
 ld d,h
 ld l,c
 ld h,b
 .rept 5                      ; 32 columns per row
 add hl,hl
 .endm
 add hl,de
 ld a,(hl)
 pop bc
 or a
 ret z
 ld d,#2
 bit 7,a
 jr z,stopped_positive
 ld d,#128
 bit 7,b
 jr nz,stopped_proven          ; both moment and applied torque negative
 cpl                           ; abs(margin)-1
 jr stopped_limit
stopped_positive:
 bit 7,b
 jr z,stopped_proven
 dec a
 ld e,a
 xor a
 sub c
 ld c,a
 ld a,#0
 sbc b
 ld b,a
 ld a,e
stopped_limit:
 ; An opposing torque of at most (abs(margin)-1)*32 preserves strict sign.
 ld l,a
 ld h,#0
 .rept 5
 add hl,hl
 .endm
 ld a,l
 sub c
 ld a,h
 sbc b
 jr c,stopped_unknown
stopped_proven:
 ld a,d
 ret
stopped_drop:
 pop hl
stopped_unknown:
 xor a
 ret

stopped_four_bytes:
 .rept 3
 ld a,(de)
 cp (hl)
 ret nz
 inc de
 inc hl
 .endm
 ld a,(de)
 cp (hl)
 inc de
 ret

; HL starts at byte 1 of a signed32 value and ends at the next value.
; Map [-131072,65535] to 48 cells. Return 255 outside that range.
stopped_digit:
 ld a,(hl+)
 swap a
 and #15
 ld c,a
 ld a,(hl+)
 add #2
 ld b,a
 inc hl
 ld a,b
 cp #3
 jr nc,stopped_invalid
 cp #2
 sbc a,a                       ; original byte 2 was FE, FF or 00
 dec hl
 cp (hl)
 inc hl
 jr nz,stopped_invalid
 ld a,b
 swap a
 or c
 ret
stopped_invalid:
 ld a,#255
 ret

.area _CODE
_riding_pair_fast_side::
 ; Full-substep free motion with zero torque can leave the last Q24
 ; fraction observable even on rejection. Use the original evaluation.
 ld a,(#_riding_subphase)
 or a
 jr nz,pair_bound_eligible
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
 ret z
pair_bound_eligible:
 ld b,d
 ld c,e
 ld e,#13
 ld hl,#pair_bound_start
 jp ___sdcc_bcall_ehl
.area _CODE_13
pair_bound_start:
 ld d,b
 ld e,c
 .if PAIR_TIGHT_BOUND
 ; q bounds |vx|+|vy| in multiples of 4096. For physical Q14
 ; coefficients of magnitude at most one and contact length <=410,
 ; the two shift/round stages change angular speed by at most 17*q.
 ld hl,#1
 add hl,de
 call pair_speed_bucket
 ret nc
 ld d,a
 call pair_speed_bucket
 ret nc
 add d
 jr c,pair_speed_unknown
 add #2
 jr c,pair_speed_unknown
 ld b,h
 ld c,l
 ld d,a
 ld e,#2
 ld hl,#pair_bound_omega
 jp ___sdcc_bcall_ehl
.area _CODE_2
pair_bound_omega:
 ld a,d
 ld d,b
 ld e,c
 ld c,a
 ld b,#0
 ld h,b
 ld l,c
 .rept 4
 add hl,hl
 .endm
 add hl,bc
 push hl                        ; 17*q
 ld hl,#4
 add hl,de
 ld a,(hl)
 add a
 sbc a
 ld c,a
 ld a,(hl-)
 xor c
 ld b,a
 ld a,(hl+)
 xor c
 inc hl
 ld e,a
 inc hl
 ; Only signed-word angular speeds qualify, ruling out signed32 wrap.
 ld a,(hl-)
 xor c
 jr nz,pair_side_pop_unknown
 ld a,(hl)
 xor c
 jr nz,pair_side_pop_unknown
 pop hl
 ld a,e
 scf
 sbc l
 ld a,b
 sbc h
 jr c,pair_side_unknown
 ; Both pivots share this proof. Their directions and lengths are
 ; public inputs, including in the full-width wheel fixture.
 push bc
 call pair_normal_bounds
 pop bc
 or a
 ret z
 ld a,c
 and #128
 ret nz
 ld a,#2
 ret
.area _CODE_2
pair_side_pop_unknown:
 pop hl
pair_side_unknown:
 xor a
 ret
 ; Return floor(U(v)/4096), U(v)=v for nonnegative v and ~v otherwise.
 ; The top byte and three magnitude bits admit at most 127 buckets.
 ; Advance HL from byte one to byte one of the next velocity.
.area _CODE_13
pair_speed_bucket:
 ld a,(hl+)
 swap a
 and #15
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 inc a
 cp #2
 jr nc,pair_speed_unknown
 dec a
 ld e,a
 xor b
 cp #8
 jr nc,pair_speed_unknown
 ld a,b
 swap a
 and #240
 or c
 xor e
 inc hl
 scf
 ret
pair_speed_unknown:
 xor a
 ret
.area _CODE_2
pair_normal_bounds:
 ld hl,#_Ct
 call pair_normal_bound
 ret nc
 .rept 4
 inc hl
 .endm
pair_normal_bound:
 .rept 2
 inc hl
 ld a,(hl+)
 add #64
 cp #128
 jr nc,pair_normal_unknown ; includes -16384, excludes +16384
 .endm
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 or a
 jr z,pair_normal_known
 dec a
 jr nz,pair_normal_unknown
 ld a,c
 cp #155
 jr nc,pair_normal_unknown
pair_normal_known:
 ld a,#1
 scf
 ret
pair_normal_unknown:
 xor a
 ret
 .else
 xor a
 ret
 .endif

.area _CODE_5
