.module bumpy_setup
.area _CODE_87
_bumpy_wheel_select::
 call _hang_wheel_select
 ld a,(#_physics_level_index)
 cp #33
 ret nz
 ld hl,#bumpy_template
 ld de,#_riding_sparse_bind
 ld b,#bumpy_end-bumpy_template
bumpy_copy:
 ld a,(hl+)
 ld (de),a
 inc de
 dec b
 jr nz,bumpy_copy
 ret

; The ordinary quarter-change hook sees A = wheel's new X page and DE =
; wheel + 2. Keep the original sparse tile available across this course.
bumpy_template:
 push af
 push hl
 push de
 ld b,l
 ld c,a
 inc de
 inc de
 inc de
 inc de
 ld a,(de)
 ld hl,#(_riding_sparse_bind+bumpy_input_offset)
 sub #8
 cp #8
 jr nc,bumpy_vertical_band
 ld a,c
 add #2
 cp #4
 jr c,bumpy_bind
bumpy_vertical_band:
 ld a,(de)
 sub #248
 cp #4
 jr nc,bumpy_sparse
 ld a,c
 sub #245
 cp #8
 jr c,bumpy_bind
bumpy_sparse:
 ld hl,#_riding_wheel_inputs
 ld a,(#_patch_sparse_y0-3)
 cp c
 jr nz,bumpy_bind
 ld a,(#_patch_sparse_y0)
 ld c,a
 ld a,(de)
 cp c
 jr nz,bumpy_bind
 ld hl,#_riding_sparse_wheel_inputs
bumpy_bind:
 ld de,#step_solve_wheels+4
 ld a,b
 cp #<_wheel_surface_cache
 jr z,bumpy_first
 ld de,#step_solve_wheels+10
bumpy_first:
 ld a,l
 ld (de),a
 inc de
 ld a,h
 ld (de),a
 pop de
 pop hl
 pop af
 ret

bumpy_stub:
 push hl
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 push bc
 ld hl,#_bumpy_query
 ld e,#bumpy_bank
 call ___sdcc_bcall_ehl
 cp #255
 jp nz,_riding_patch_have_answer
 pop bc
 pop hl
 jp _riding_wheel_inputs
bumpy_end:
bumpy_input_offset = bumpy_stub-bumpy_template
bumpy_stub_bytes == bumpy_end-bumpy_template

.area _CODE_5
_riding_resolve_shared_cap::
 ; The shared resolver uses both contacts as scratch, while this wheel
 ; query publishes only the first six bytes of a single active contact.
 ld hl,#(_Ct+6)
 ld b,#7
shared_save_contacts:
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 push de
 dec b
 jr nz,shared_save_contacts
 ld hl,#_riding_shared_cap
 ld e,#9
 call ___sdcc_bcall_ehl
 ld c,a
 ld b,#7
 ld hl,#(_Ct+19)
shared_restore_contacts:
 pop de
 ld a,d
 ld (hl-),a
 ld a,e
 ld (hl-),a
 dec b
 jr nz,shared_restore_contacts
 ld a,c
 ret
