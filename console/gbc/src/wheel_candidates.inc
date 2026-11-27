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
 cp #3
 jp nc,corner_candidate_plane
 jp corner_cap_dispatch

.area _CODE_5
_riding_candidate_decode::
 ld e,c
 ld d,#0
 ld hl,#_riding_candidate_programs-1
 add hl,de
 ld e,(hl)
 ld hl,#_riding_candidate_payload
 add hl,de
 ld a,(hl+)
 ld b,a
 and #128
 ld (#candidate_shared),a
 jr z,candidate_count
 ld de,#_riding_dense_vertex
 .rept 4
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
candidate_count:
 res 7,b
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
