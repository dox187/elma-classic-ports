; Stream the selected ordered program in the wheel solver's own ROM bank.
; Seg_cur and Seg_left retain the full leaf until the iterator returns.
.area _CODE_9
_riding_candidate_solve::
 ld e,a
 ld d,#0
 ld hl,#_riding_candidate_programs-1
 add hl,de
 ld e,(hl)
 ld hl,#_riding_candidate_payload
 add hl,de
 push hl
 xor a
 ld (#_riding_program_mode),a
 call contact_loop_init
 pop hl
 ld a,(hl+)
 ld b,a
 bit 7,b
 jr z,candidate_next
 res 7,b
 push hl                     ; program continues after the signed X/Y vertex
 push bc
 call corner_shared_vertex
 ld hl,#contact_loop_found
 ld (hl+),a
 ld (hl),#0
 or a
 jr z,candidate_shared_ready
 inc hl
 ld (hl),#<(_Ct+10)
 inc hl
 ld (hl),#>(_Ct+10)
candidate_shared_ready:
 pop bc
 pop hl
 .rept 4
 inc hl
 .endm
candidate_next:
 ld a,b
 or a
 jr z,candidate_exhausted
candidate_record:
 ld a,(hl+)
 ld c,a                      ; zero-based ordinal in the full leaf
 ld a,(hl+)
 push hl
 push bc
 ld b,a                      ; contact opcode
 call candidate_pointer
 push de                     ; the next source record follows this one by 18 bytes
 call candidate_try
 ; A distinct pair unwinds the contact call and resumes here.
 pop de
 pop bc
 pop hl
 inc c                       ; first unread record after the early pair
 ld a,(#_Seg_left)
 sub c
 ld (#_Seg_left),a
 ld hl,#18
 add hl,de
 ld d,h
 ld e,l
 call candidate_store
 ld a,#2
 ret
candidate_exhausted:
 ld a,(#_Seg_left)
 ld c,a
 xor a
 ld (#_Seg_left),a
 call candidate_pointer
 call candidate_store
 jp contact_loop_done

candidate_store:
 ld hl,#_Seg_cur
 ld (hl),e
 inc hl
 ld (hl),d
 ret
; DE = original leaf pointer + 18*C. B retains the operation.
candidate_pointer:
 ld e,c
 ld d,#0
 ld h,d
 ld l,e
 add hl,hl
 add hl,hl
 add hl,hl
 add hl,de
 add hl,hl
 ld a,(#_Seg_cur)
 add l
 ld e,a
 ld a,(#_Seg_cur+1)
 adc h
 ld d,a
 ret
candidate_try:
 call candidate_contact
 pop hl                      ; discard the early-pair return address
 pop de
 pop bc
 pop hl
 dec b
 jr nz,candidate_record
 jr candidate_exhausted
candidate_contact:
 ld a,b
 or a
 jp z,corner_general_record
 cp #3
 jp nc,corner_candidate_plane
 jp corner_cap_query
