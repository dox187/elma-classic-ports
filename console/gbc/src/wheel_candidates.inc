; Ordered contact programs for exact integer tiles in a resident collision leaf.
.area _DATA
candidate_shared: .ds 1
candidate_steps: .ds 4*9    ; at most eight actual records, then the exhausted cursor

.area _CODE_9
; Each step publishes the original cursor before evaluating its record. The
; native second-contact return bypasses candidate_single and carries A=2.
_riding_candidate_solve::
 ld hl,#candidate_steps
candidate_next:
 ld a,(hl+)
 ld (#_Seg_left),a
 ld a,(hl+)
 ld e,a
 ld (#_Seg_cur),a
 ld a,(hl+)
 ld d,a
 ld (#_Seg_cur+1),a
 ld a,(hl+)
 cp #255
 jp z,contact_loop_done
 ld b,a
 ld a,e
 sub #18
 ld e,a
 jr nc,candidate_record
 dec d
candidate_record:
 push hl
 call candidate_single
 pop hl
 cp #2
 ret z
 jr candidate_next
candidate_single:
 call candidate_contact
 xor a
 ret
candidate_contact:
 ld a,b
 or a
 jp z,corner_general_record
 jp corner_cap_dispatch

.area _CODE_5
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
 jr z,candidate_read_miss
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
 jr z,candidate_read_miss
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
 add a
 ld c,a
 ld hl,#candidate_decode
 ld e,#7
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
.area _CODE_7
candidate_decode:
 ld e,c
 ld d,#0
 ld hl,#_riding_candidate_programs-2
 add hl,de
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(hl+)
 ld (#candidate_shared),a
 or a
 jr z,candidate_count
 ld de,#_riding_dense_vertex
 .rept 4
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
candidate_count:
 ld a,(hl+)
 ld b,a
 ld de,#candidate_steps
candidate_decode_record:
 ld a,b
 or a
 jr z,candidate_decode_end
 ld a,(hl+)
 inc a
 ld c,a
 ld a,(#_Seg_left)
 sub c
 ld (de),a
 inc de
 push hl
 call candidate_after
 ld a,l
 ld (de),a
 inc de
 ld a,h
 ld (de),a
 inc de
 pop hl
 ld a,(hl+)
 ld (de),a
 inc de
 dec b
 jr candidate_decode_record
candidate_decode_end:
 ; A final silent step exhausts the original full leaf if no early pair returned.
 xor a
 ld (de),a
 inc de
 ld a,(#_Seg_left)
 ld c,a
 call candidate_after
 ld a,l
 ld (de),a
 inc de
 ld a,h
 ld (de),a
 inc de
 ld a,#255
 ld (de),a
 xor a
 ld (#_riding_program_mode),a
 ld hl,#contact_loop_init
 ld e,#9
 call ___sdcc_bcall_ehl
 ld a,(#candidate_shared)
 or a
 jr z,candidate_ready
 ld hl,#_riding_shared_cap
 ld e,#9
 call ___sdcc_bcall_ehl
 ld hl,#contact_loop_found
 ld (hl+),a
 ld (hl),#0
 or a
 jr z,candidate_ready
 inc hl
 ld (hl),#<(_Ct+10)
 inc hl
 ld (hl),#>(_Ct+10)
candidate_ready:
 ld a,#1
 ret
candidate_after:
 push bc
 ld b,#0
 ld h,b
 ld l,c
 add hl,hl
 add hl,hl
 add hl,hl
 add hl,bc
 add hl,hl
 ld a,(#_Seg_cur)
 ld c,a
 ld a,(#_Seg_cur+1)
 ld b,a
 add hl,bc
 pop bc
 ret
