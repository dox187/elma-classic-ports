; HL points to a wheel input, whose first word is the wheel.
.area _CODE_9
direct_steep::
 ld bc,#direct_steep_tiles
 ld de,#DIRECT_STEEP_BOUNDS
 jr direct_choose
direct_course48::
 ld bc,#direct_course48_tiles
 ld de,#DIRECT_COURSE48_BOUNDS
direct_choose:
 push hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 .rept 6
 inc hl
 .endm
 ld a,(hl)
 sub d
 cp e
 pop de
 jr nc,direct_fast_miss
 push de
 ld h,b
 ld l,c
 jp _riding_sparse_bind+1
direct_fast_miss:
 ld hl,#6
 add hl,de
 ld c,(hl)
 ld a,(#_patch_sparse_y0)
 cp c
 jr z,direct_use_sparse
 ld a,(#_patch_sparse_y1)
 cp c
direct_use_sparse:
 pop hl
 jp z,_riding_sparse_wheel_inputs
 jp _riding_wheel_inputs

.area _CODE_32
direct_template_start::
 ld a,#<DIRECT_BANK
 ld (#0x2000),a
 ld a,#1
 ld (#0x3000),a
 call direct_query
 ld b,a
 xor a
 ld (#0x3000),a
 ldh a,(#__current_bank)
 ld (#0x2000),a
 ld a,b
 cp #2
 jr z,direct_points
 cp #255
 jp nz,_riding_patch_have_answer
 pop de
 jp direct_fast_miss

direct_points:
 ld hl,#direct_project_pair
 ld e,#28
 call ___sdcc_bcall_ehl
 ld a,#2
 jp _riding_patch_have_answer
direct_template_end::
direct_template_size = direct_template_end-direct_template_start
.globl direct_template_size
.area _CODE_28
direct_project_pair::
 ld bc,#_Ct
 call _riding_contact_length_point
 ld bc,#(_Ct+10)
 jp _riding_contact_length_point

.area _CODE_503
; Jump through the course's selected root. Each root checks all six
; integer coordinate bytes before selecting the center in a whole tile.
direct_data_start::
direct_query::
 jp (hl)
direct_known::
 ; BC is the tile's native reader. Preserve a fully filtered pair when
 ; the position may still match its certificate, including both fractions.
 ld hl,#(_wheel_surface_cache+4)
 ld a,e
 cp #<(_Bike+48)
 jr nz,direct_kind
 ld hl,#(_wheel_surface_cache+29+4)
direct_kind:
 ld a,(hl+)
 cp #9
 jr nz,direct_read
 ld a,(de)
 cp (hl)
 jr z,direct_miss
direct_read::
 push de
 push bc
 ld h,d
 ld l,e
 inc hl
 ld a,(hl+)
 and #15
 ld c,a
 inc hl
 inc hl
 inc hl
 ld a,(hl)
 and #15
 swap a
 or c
 ld c,a
 ld b,#0
 ld d,b
 ret
direct_decoded::
 pop de
 cp #2
 ret nz
 ld h,d
 ld l,e
 inc hl
 ld a,(hl+)
 ld (#_riding_contact_qx),a
 ld a,(hl+)
 and #15
 ld (#_riding_contact_qx+1),a
 inc hl
 inc hl
 ld a,(hl+)
 ld (#_riding_contact_qy),a
 ld a,(hl)
 and #15
 ld (#_riding_contact_qy+1),a
 ld hl,#_wheel_surface_cache
 ld a,e
 cp #<(_Bike+48)
 jr nz,direct_key
 ld hl,#(_wheel_surface_cache+29)
direct_key:
 ; Do not invalidate this square's prepared record on a fresh fraction.
 push hl
 push de
 inc de
 inc de
 .rept 2
 ld a,(de)
 cp (hl)
 jr nz,direct_new_key
 inc de
 inc hl
 .endm
 inc de
 inc de
 .rept 2
 ld a,(de)
 cp (hl)
 jr nz,direct_new_key
 inc de
 inc hl
 .endm
 add sp,#4
 ld a,#2
 ret
direct_new_key:
 pop de
 pop hl
 inc de
 inc de
 .rept 2
 ld a,(de)
 ld (hl+),a
 inc de
 .endm
 inc de
 inc de
 .rept 2
 ld a,(de)
 ld (hl+),a
 inc de
 .endm
 ld (hl),#0
 ld a,#2
 ret
direct_miss::
 ld a,#255
 ret
