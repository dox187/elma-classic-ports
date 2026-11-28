; DE is the wheel. A = 255 delegates to the normal terrain solver.
.module corner_lookup
.area _CODE
_riding_corner_lookup::
 ld a,(#_physics_level_index)
 cp #10
 jp nz,_riding_sparse_lookup
_riding_corner_gravity::
 push de
 ld h,d
 ld l,e
 inc hl
 inc hl
 ld a,(hl)
 cp #168                  ; separate the two covered X ranges
 ld a,#<473
 jr c,corner_select
 inc a
corner_select:
 ld (#0x2000),a
 ld a,#1
 ld (#0x3000),a
 call 0x4000              ; identical entry address in banks 473 and 474
 ld b,a
 xor a
 ld (#0x3000),a
 ldh a,(#__current_bank)
 ld (#0x2000),a
 pop de
 ld a,b
 ret

.area _CODE_32
_riding_corner_select::
 ; The bank reader runs from RAM while the selected tile's ROM is mapped.
 ; Its internal branches are relative and its data addresses point to WRAM.
 ld hl,#corner_template
 ld de,#corner_ram
 ld bc,#corner_template_end-corner_template
 call corner_copy
 ld hl,#_riding_sparse_courses
 ld a,(#_physics_level_index)
 cp #54
 jp nc,corner_no_level
 ld c,a
 ld b,#0
 ; 11 bytes per course (two 24-bit coordinates, bank, two pointers).
 add hl,bc
 sla c
 rl b
 add hl,bc
 sla c
 rl b
 sla c
 rl b
 add hl,bc
 ld de,#corner_key
 ld bc,#11
 call corner_copy
 ld a,(#corner_key+1)
 ld (#corner_ram+1),a
 ld (#corner_quarter_old),a
 ld a,(#_physics_level_index)
 ld hl,#corner_secondary_keys
 ld c,a
 ld de,#11
corner_next_secondary:
 ld a,(hl+)
 cp #255
 ld a,c
 jr z,corner_level_ready
 dec hl
 cp (hl)
 inc hl
 jr z,corner_has_secondary
 add hl,de
 jr corner_next_secondary
corner_has_secondary:
 push af
 ld de,#corner_second
 ld bc,#11
 call corner_copy
 ld a,#0x18              ; JR to the two-strip binder on this course
 ld (#corner_ram),a
 ld a,#(corner_dual_bind-corner_bind_src-2)
 ld (#corner_ram+1),a
 ld a,#(corner_dual_check-corner_sparse_branch-2)
 ld (#corner_ram+(corner_sparse_branch-corner_template)+1),a
 pop af
corner_level_ready:
 .ifdef RIDING_DIRECT_TILES
 cp #31
 ld hl,#direct_steep
 jr z,corner_direct_install
 cp #47
 ld hl,#direct_course48
 jr nz,corner_not_direct
corner_direct_install:
 push hl
 ld hl,#direct_template_start
 ld de,#_riding_sparse_bind+1
 ld bc,#direct_template_size
 call corner_copy
 pop hl
 jp corner_disable_bind
corner_not_direct:
 .endif
 cp #37
 jr nz,corner_existing_level
 ld hl,#_riding_patch_wheel_inputs
 jr corner_disable_bind
corner_existing_level:
 cp #38
 ld hl,#_haircut_wheel_inputs
 jr z,corner_disable_bind
 cp #10
 jr z,corner_dense_target
 ; Check the first position after a course reset. Seeding the invalid
 ; cache X ensures the first later certificate rebinds either wheel.
 ld a,(#corner_key+1)
 ld (#_wheel_surface_cache),a
 ld (#(_wheel_surface_cache+29)),a
 ld hl,#_riding_sparse_wheel_inputs
 jr corner_set_target
corner_dense_target:
 ld hl,#_riding_corner_wheel_inputs
 jr corner_disable_bind
corner_no_level:
 ld hl,#_riding_wheel_inputs
corner_disable_bind:
 ld a,#0xc9
 ld (#corner_ram),a
corner_set_target:
 ld a,l
 ld (#step_solve_wheels+4),a
 ld (#step_solve_wheels+10),a
 ld a,h
 ld (#step_solve_wheels+5),a
 ld (#step_solve_wheels+11),a
 ret
corner_copy:
 ld a,(hl+)
 ld (de),a
 inc de
 dec bc
 ld a,b
 or c
 jr nz,corner_copy
 ret

corner_template:
corner_bind_src:
 ; A = new quarter X byte, (HL) = previous cached X, DE = wheel+2.
 ; Only rebind a wheel when entering or leaving this course's X strip.
 ; The complete signed 24-bit key is checked before consuming a result.
 cp #0
 jr z,corner_bind_change
 ld b,a
 ld a,(hl)
corner_old_compare:
 cp #0
 ld a,b
 ret nz
corner_bind_change:
 push af
 push hl
 push de
 ld b,l
 ld hl,#_riding_wheel_inputs
 ld c,a
 ld a,(#corner_key+1)
 cp c
 jr nz,corner_bind_write
 inc de
 inc de
 inc de
 inc de
 ld a,(de)
 ld c,a
 ld a,(#corner_key+4)
 cp c
 jr nz,corner_bind_write
 ld hl,#_riding_sparse_wheel_inputs
corner_bind_write:
 ld de,#step_solve_wheels+4
 ld a,b
 cp #<_wheel_surface_cache
 jr z,corner_bind_first
 ld de,#step_solve_wheels+10
corner_bind_first:
 ld a,l
 ld (de),a
 inc de
 ld a,h
 ld (de),a
 pop de
 pop hl
 pop af
 ret

corner_dual_bind:
 ; Ignore a quarter change that neither enters nor leaves the two X strips.
 ld c,a
 ld a,(#corner_key+1)
 cp c
 jr z,corner_dual_change
 cp (hl)
 jr z,corner_dual_change
 ld a,(#corner_second+1)
 cp c
 jr z,corner_dual_change
 cp (hl)
 ld a,c
 ret nz
corner_dual_change:
 ld a,c
 push af
 push hl
 push de
 ld b,l
 ld hl,#_riding_wheel_inputs
 ld a,(#corner_key+1)
 cp c
 ld a,(#corner_key+4)
 jr z,corner_dual_y
 ld a,(#corner_second+1)
 cp c
 jr nz,corner_bind_write
 ld a,(#corner_second+4)
corner_dual_y:
 ld c,a
 inc de
 inc de
 inc de
 inc de
 ld a,(de)
 cp c
 jr nz,corner_bind_write
 ld hl,#_riding_sparse_wheel_inputs
 jr corner_bind_write

corner_lookup_src:
 push de
 ld h,d
 ld l,e
 inc hl
 ld de,#corner_key
corner_sparse_branch:
 jr corner_sparse_check
corner_dual_check:
 inc hl
 ld a,(hl-)
 ld b,a
 ld a,(#corner_second+1)
 cp b
 jr nz,corner_sparse_check
 ld de,#corner_second
 jr corner_sparse_check
corner_sparse_miss:
 ld a,#255
 pop de
 ret
corner_sparse_check:
 ld a,(de)
 xor (hl)
 and #0xf0
 jr nz,corner_sparse_miss
 ld a,(hl+)
 and #15
 ld c,a                  ; X inside the tile
 inc de
 ld a,(de)
 cp (hl)
 jr nz,corner_sparse_miss
 inc de
 inc hl
 ld a,(de)
 cp (hl)
 jr nz,corner_sparse_miss
 inc de
 inc hl
 inc hl
 ld a,(de)
 xor (hl)
 and #0xf0
 jr nz,corner_sparse_miss
 ld a,(hl+)
 and #15
 ld b,a                  ; Y inside the tile
 inc de
 ld a,(de)
 cp (hl)
 jr nz,corner_sparse_miss
 inc de
 inc hl
 ld a,(de)
 cp (hl)
 jr nz,corner_sparse_miss
 ld h,d
 ld l,e
 inc hl
 ld a,(hl+)
 or a
 jr z,corner_sparse_miss
 ld (#0x2000),a
 ld a,#1
 ld (#0x3000),a
 ld a,(hl+)
 ld d,(hl)
 inc hl
 push hl                 ; pointer to this tile's dictionary address
 ld h,d
 ld l,a
 ld e,b
 ld d,#0
 push hl
 add hl,de
 ld a,(hl)
 or c
 ld e,a
 pop hl
 ld bc,#16
 add hl,bc
 add hl,de
 ld a,(hl)
 pop de
 or a
 jr z,corner_sparse_restore
 ld c,a
 ld a,(de)
 ld l,a
 inc de
 ld a,(de)
 ld h,a                   ; dictionary, with pair directory at entry zero
 ld a,c
 cp #255
 jr z,corner_sparse_pair
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 dec hl
 ld b,#0
 .rept 4
 add hl,bc
 .endm
 ld a,(hl+)
 ld (#_Ct),a
 ld a,(hl+)
 ld (#_Ct+2),a
 ld a,(hl+)
 ld (#_Ct+4),a
 ld c,(hl)
 ld h,d
 ld l,e
 .rept 3
 add hl,bc
 .endm
 ld a,(hl+)
 ld (#_Ct+1),a
 ld a,(hl+)
 ld (#_Ct+3),a
 ld a,(hl)
 ld (#_Ct+5),a
 ld a,#1
corner_sparse_restore:
 ld b,a
 xor a
 ld (#0x3000),a
 ldh a,(#__current_bank)
 ld (#0x2000),a
 ld a,b
 pop de
 ret
corner_sparse_pair:
 inc hl
 inc hl
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 pop de
 push de
 call _riding_corner_pair_map
 jr corner_sparse_restore
corner_pair_map:
 ld a,b
 or a
 ld a,#255
 ret z
 ld a,#<472
 ld (#0x2000),a
 jp _riding_corner_code_472
corner_template_end:

.area _DATA
corner_second: .ds 11
corner_key: .ds 11
corner_ram: .ds corner_template_end-corner_template
_riding_sparse_bind = corner_ram + (corner_bind_src-corner_template)
_riding_sparse_lookup = corner_ram + (corner_lookup_src-corner_template)
corner_quarter_old = corner_ram+(corner_old_compare-corner_template)+1
_riding_corner_pair_map = corner_ram+(corner_pair_map-corner_template)
.globl _riding_sparse_bind, _riding_sparse_lookup, _riding_corner_pair_map
_patch_sparse_y0 = corner_key+4
_patch_sparse_y1 = corner_second+4
.globl _patch_sparse_y0, _patch_sparse_y1

.area _CODE_32
