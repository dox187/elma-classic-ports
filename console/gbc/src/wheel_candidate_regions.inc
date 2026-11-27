.area _CODE_80
; Verify the full FIFO pointer, course cell, optional metre subdivision,
; count and exact tile. Partial windows and foreign pointers just miss.
_riding_candidate_select::
 ld a,(#_Seg_cur)
 ld c,a
 ld a,(#_Seg_cur+1)
 ld b,a
 ld hl,#_candidate_slots
 ld e,#0
candidate_check_slot:
 ld a,(hl+)
 cp c
 jr nz,candidate_slot_skip
 ld a,(hl)
 cp b
 jr z,candidate_slot
candidate_slot_skip:
 inc hl
 inc e
 ld a,e
 cp #3
 jr nz,candidate_check_slot
 xor a
 ret
candidate_slot:
 ld d,#0
 ld hl,#_candidate_subcells
 add hl,de
 ld a,(hl)
 cp #255
 jr z,candidate_cell
 ld c,a
 ld a,(#_riding_contact_qx+1)
 rrca
 rrca
 and #3
 ld b,a
 ld a,(#_riding_contact_qy+1)
 and #12
 or b
 cp c
 jr nz,candidate_miss
candidate_cell:
 ld hl,#_candidate_cell_ids
 add hl,de
 add hl,de
 ld a,(hl+)
 ld b,a
 ld c,(hl)
 ld a,(#_riding_contact_qx+1)
 ld e,a
 ld a,(#_riding_contact_qy+1)
 or e
 and #0xf0
 jr nz,candidate_miss
 jr candidate_read
candidate_miss:
 xor a
 ret

candidate_read:
 ld hl,#_riding_candidate_leaves
candidate_leaf:
 ld a,(hl+)
 cp #255
 jp z,candidate_read_miss
 ld d,a
 ld a,(#_physics_level_index)
 cp d
 jr nz,candidate_leaf_skip5
 ld a,(hl+)
 cp b
 jr nz,candidate_leaf_skip4
 ld a,(hl+)
 cp c
 jr nz,candidate_leaf_skip3
 ld a,(#_Seg_left)
 cp (hl)
 inc hl
 jr z,candidate_region_start
 inc hl
 inc hl
 jr candidate_leaf
candidate_leaf_skip5:
 inc hl
candidate_leaf_skip4:
 inc hl
candidate_leaf_skip3:
 inc hl
 inc hl
 inc hl
 jr candidate_leaf
candidate_region_start:
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 ld hl,#_riding_contact_qx
 call candidate_tile
 ld b,a
 ld hl,#_riding_contact_qy
 call candidate_tile
 ld c,a
 pop hl
candidate_region:
 ld a,(hl+)
 or a
 jp z,candidate_read_miss
 ld e,a
 ld a,b
 sub (hl)
 inc hl
 cp e
 jr nc,candidate_region_skip4
 ld d,a
 ld a,c
 sub (hl)
 inc hl
 cp (hl)
 inc hl
 jr nc,candidate_region_skip2
 push de
 ld d,a
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,h
 or a
 jr nz,candidate_table
 pop de
 ld a,l
 jr candidate_program_id
candidate_table:
 inc e
 srl e
 ld a,d
 ld d,#0
 or a
 jr z,candidate_column
candidate_row:
 add hl,de
 dec a
 jr nz,candidate_row
candidate_column:
 pop de
 ld e,d
 srl e
 ld d,#0
 push af
 add hl,de
 pop af
 ld a,(hl)
 jr nc,candidate_nibble
 swap a
candidate_nibble:
 and #15
 ret z
candidate_program_id:
 ld c,a
 ld hl,#_riding_candidate_decode
 ld e,#5
 jp ___sdcc_bcall_ehl
candidate_region_skip4:
 inc hl
 inc hl
candidate_region_skip2:
 inc hl
 inc hl
 jr candidate_region
candidate_read_miss:
 xor a
 ret
candidate_tile:
 ld a,(hl+)
 swap a
 and #15
 ld e,a
 ld a,(hl)
 swap a
 or e
 ret
