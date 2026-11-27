; Install a course-specific wheel reader after the ordinary terrain selection.
_hang_wheel_select::
 ld hl,#_bowling_wheel_select
 ld e,#86
 call ___sdcc_bcall_ehl
 ld a,(#_physics_level_index)
 cp #51
 ret nz
 ld hl,#_riding_sparse_bind
 ld (hl),#0xc9
 inc hl
 ld d,h
 ld e,l
 ld hl,#hang_stub
 ld b,#hang_stub_end-hang_stub
hang_copy:
 ld a,(hl+)
 ld (de),a
 inc de
 dec b
 jr nz,hang_copy
 ld hl,#_riding_sparse_bind+1
 ld a,l
 ld (#step_solve_wheels+4),a
 ld (#step_solve_wheels+10),a
 ld a,h
 ld (#step_solve_wheels+5),a
 ld (#step_solve_wheels+11),a
 ret
hang_stub:
 push hl
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 ld hl,#6
 add hl,bc
 ld a,(hl)
 sub #107
 cp #5
 jr nc,hang_fallback
 push bc
 ld hl,#_hang_query
 ld e,#7
 call ___sdcc_bcall_ehl
 cp #255
 jp nz,_riding_patch_have_answer
 pop bc
hang_fallback:
 ld hl,#6
 add hl,bc
 ld a,(#_patch_sparse_y0)
 cp (hl)
 pop hl
 jp z,_riding_sparse_wheel_inputs
 jp _riding_wheel_inputs
hang_stub_end:
hang_stub_bytes == hang_stub_end-hang_stub

.area _CODE_7
; X and Y are signed Q24.8. Admit only the 48 columns and full signed
; coordinates covered by the generated bounds. BC names the wheel.
_hang_query::
 ld h,b
 ld l,c
 inc hl
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld a,(hl+)
 dec a
 jr nz,hang_miss
 inc hl
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 and #0xf0
 cp #0x60
 jr nz,hang_miss
 ld a,(hl)
 or a
 jr nz,hang_miss
 ld a,d
 cp #7
 jr nc,hang_miss
 ld a,e
 rlca
 rlca
 rlca
 and #7
 ld l,a
 ld a,d
 add a
 add a
 add a
 or l
 sub #8
 jr c,hang_miss
 ld l,a
 ld h,#0
 add hl,hl
 push de
 ld de,#hang_bounds
 add hl,de
 ld a,c
 swap a
 and #15
 ld e,a
 ld a,b
 swap a
 and #0xf0
 or e
 sub (hl)
 inc hl
 ld d,a
 ld a,(hl)
 and #0x3f
 dec a
 cp d
 ld a,(hl)
 pop de
 jr c,hang_miss
 and #0xc0
 jr z,hang_west
 cp #128
 jr c,hang_east
 ; Both ordered edges use the same cap. The general radial resolver
 ; performs the strict disk check and the original post-merge normalization.
 ld hl,#_riding_contact_qx
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ld (hl),c
 inc hl
 ld (hl),b
 ld hl,#hang_west_plane
 jr z,hang_vertex
 ld hl,#hang_east_plane
hang_vertex:
 ld de,#_riding_dense_vertex
 ld b,#4
hang_copy_vertex:
 ld a,(hl+)
 ld (de),a
 inc de
 dec b
 jr nz,hang_copy_vertex
 ld hl,#_riding_shared_cap
 ld e,#9
 jp ___sdcc_bcall_ehl
hang_miss:
 ld a,#255
 ret
hang_west:
 ld hl,#hang_west_plane
 jr hang_plane
hang_east:
 ld hl,#hang_east_plane
hang_plane:
 ld a,e
 sub (hl)
 inc hl
 ld e,a
 ld a,d
 sbc (hl)
 inc hl
 ld d,a
 ld a,c
 sub (hl)
 inc hl
 ld c,a
 ld a,b
 sbc (hl)
 inc hl
 ld b,a
 ; Save the table position beyond the input words. Dot takes X in DE,
 ; Y in BC, then the two normal coefficients in X,Y stack order.
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
 .rept 4
 inc hl
 .endm
 xor a
 sub c
 ld c,a
 ld a,#0
 sbc b
 cp #2
 jr nc,hang_empty
 or a
 jr z,hang_hit
 ld a,c
 cp #154
 jr nc,hang_empty
 ld a,#1
hang_hit:
 ld b,a
 push bc
 ld de,#_Ct
 ld b,#4
hang_copy_normal:
 ld a,(hl+)
 ld (de),a
 inc de
 dec b
 jr nz,hang_copy_normal
 pop bc
 ld a,c
 ld (de),a
 inc de
 ld a,b
 ld (de),a
 ld a,#1
 ret
hang_empty:
 xor a
 ret
hang_west_plane: .dw 905,28019,-11872,11292,-11292,11872
hang_east_plane: .dw 1312,27631,-11859,-11305,11305,11859
