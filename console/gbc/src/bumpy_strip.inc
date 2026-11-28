; Put the leaf evaluator in the unused space before the rolling dispatch page.
.macro bumpy_resolver
bumpy_solve:
 ; DE and BC carry full low words of wheel X and Y. The tile lookup has
 ; already checked their upper bytes. All differences here fit signed16.
 cp #4
 jr nc,bumpy_plane
 dec a
 add a
 add a
 ld l,a
 ld h,#0
 push de
 ld de,#bumpy_vertices
 add hl,de
 pop de
 ld a,e
 sub (hl)
 ld e,a
 inc hl
 ld a,d
 sbc (hl)
 ld d,a
 inc hl
 ld a,c
 sub (hl)
 ld c,a
 inc hl
 ld a,b
 sbc (hl)
 ld b,a
 ; Express the center relative to its vertex. Both radial projections use
 ; those differences and the saved contact point bytes are restored.
 ld hl,#_riding_contact_qx
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ld (hl),c
 inc hl
 ld (hl),b
 xor a
 ld hl,#_riding_dense_vertex
 .rept 4
 ld (hl+),a
 .endm
 ld e,#5
 ld hl,#_riding_resolve_shared_cap
 jp ___sdcc_bcall_ehl
bumpy_plane:
 ld hl,#bumpy_planes
 cp #4
 jr z,bumpy_project
 .rept 8
 inc hl
 .endm
bumpy_project:
 ld a,e
 sub (hl)
 ld e,a
 inc hl
 ld a,d
 sbc (hl)
 ld d,a
 inc hl
 ld a,c
 sub (hl)
 ld c,a
 inc hl
 ld a,b
 sbc (hl)
 ld b,a
 inc hl
 push hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 inc hl
 inc hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 call _dotq14
 pop hl
 ; The stack supplied the two coefficients in reverse memory order.
 bit 7,b
 jr z,bumpy_positive
 xor a
 sub c
 ld c,a
 ld a,#0
 sbc b
 ld b,a
 ld e,#255
 jr bumpy_range
bumpy_positive:
 ld e,#0
bumpy_range:
 ld a,b
 cp #2
 jp nc,bumpy_empty
 or a
 jp z,bumpy_hit
 ld a,c
 cp #154
 jp nc,bumpy_empty
 jp bumpy_hit
.endm
.macro bumpy_hit_kernel
bumpy_hit:
 push bc
 push de
 inc hl
 inc hl
 call bumpy_word
 ld (#_Ct),a
 ld a,b
 ld (#_Ct+1),a
 .rept 4
 dec hl
 .endm
 pop de
 call bumpy_word
 ld (#_Ct+2),a
 ld a,b
 ld (#_Ct+3),a
 pop bc
 ld hl,#_Ct+4
 ld (hl),c
 inc hl
 ld (hl),b
 ld a,#1
 ret
bumpy_word:
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 bit 0,e
 ld a,c
 ret z
 xor a
 sub c
 ld c,a
 ld a,#0
 sbc b
 ld b,a
 ld a,c
 ret
bumpy_empty:
 xor a
 ret
.endm
; Read the complete signed center and find the six certified tiles in the
; column. The second strip runs vertically along the next face of the course.
.macro bumpy_reader
_bumpy_query::
 ld h,b
 ld l,c
 inc hl
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 push af                     ; X upper byte
 inc hl
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl)
 or a
 jr z,bumpy_vertical
 dec a
 jr nz,bumpy_miss_pop
 ld a,b
 sub #8                      ; (67584 >> 8) & 255
 cp #8
 jr nc,bumpy_miss_pop
 swap a
 ld l,a
 ld a,c
 swap a
 and #15
 or l
 ld h,a                      ; across tile
 pop af
 ld l,a
 ld a,d
 sub #254                    ; (65024 >> 8) & 255
 push af
 ld a,l
 sbc #0
 jr nz,bumpy_miss_pop
 pop af
 cp #4
 jr nc,bumpy_miss
 swap a
 ld l,a
 ld a,e
 swap a
 and #15
 or l
 add a
 add a
 ld l,a
 ld a,h
 ld h,#>bumpy_tiles
 jr bumpy_tile
bumpy_vertical:
 pop af
 or a
 jr nz,bumpy_miss
 ld a,d
 sub #245                    ; 62720 >> 8
 cp #8
 jr nc,bumpy_miss
 swap a
 ld l,a
 ld a,e
 swap a
 and #15
 or l
 ld h,a
 ld a,b
 sub #248                    ; 63488 >> 8
 cp #4
 jr nc,bumpy_miss
 swap a
 ld l,a
 ld a,c
 swap a
 and #15
 or l
 add a
 add a
 ld l,a
 ld a,h
 ld h,#>(bumpy_tiles+256)
bumpy_tile:
 sub (hl)
 cp #6
 jr nc,bumpy_miss
 inc hl
 srl a
 jr nc,bumpy_even
 add l
 ld l,a
 ld a,(hl)
 swap a
 jr bumpy_code
bumpy_even:
 add l
 ld l,a
 ld a,(hl)
bumpy_code:
 and #15
 ret z
 cp #15
 jp nz,bumpy_solve
bumpy_miss:
 ld a,#255
 ret
bumpy_miss_pop:
 pop af
 jr bumpy_miss
.endm
