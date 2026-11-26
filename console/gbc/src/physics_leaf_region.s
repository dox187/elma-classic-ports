.module physics_leaf_region_lookup

; Both the full iterator and an ordered window enter with the exact 64u
; broad-phase box and local coordinates installed. The first visit just
; records its key. Build a geometric certificate on the first repeat.
.area _CODE
_riding_leaf_dispatch::
 ld a,#31
 ld (#0x2000),a
 ld (#__current_bank),a
 call wheel_leaf_request
 ld a,#9
 ld (#0x2000),a
 ld (#__current_bank),a
 jp (hl)
wheel_leaf_result:
 ld a,c
 ret

.area _CODE_31
wheel_leaf_request:
 call wheel_leaf_lookup
 ld hl,#_riding_leaf_general
 cp #3
 jr nc,wheel_leaf_certified
; Only warm windows install the dense index. A moving query gets the
; ordinary iterator on first visit without measuring all its boxes twice.
 cp #2
 ret nz
 jp dense_leaf_query
wheel_leaf_certified:
 jr nz,wheel_leaf_surface
 ld c,#0
 ld hl,#wheel_leaf_result
 ret
wheel_leaf_surface:
 bit 3,a
 ld hl,#_riding_plane_fill
 ret z
 ld hl,#_riding_plane_affine
 ret
wheel_leaf_lookup:
 ld a,(#_riding_leaf_regions_dirty)
 or a
 jr z,wheel_leaf_key
 xor a
 ld (#_riding_leaf_regions_dirty),a
 ld (#_riding_leaf_regions+4),a
 ld (#_riding_leaf_regions+36),a
 ld (#_riding_leaf_regions+68),a
 ld (#_riding_leaf_regions+100),a
wheel_leaf_key:
 ld hl,#_riding_leaf_box
 ld a,(hl+)
 ld c,a
 ; Index by the 256-unit X strip. Both wheels frequently occupy the
 ; same ordered leaf while contacting different corners.
 rrca
 rrca
 ld b,(hl)
 and #3
 swap a
 add a
 ld l,a
 ld h,#0
 ld de,#_riding_leaf_regions
 add hl,de
 push hl
 ld a,(hl+)
 cp c
 jr nz,wheel_leaf_miss
 ld a,(hl+)
 cp b
 jr nz,wheel_leaf_miss
 ld a,(#_Seg_cur)
 cp (hl)
 inc hl
 jr nz,wheel_leaf_miss
 ld a,(#_Seg_cur+1)
 cp (hl)
 inc hl
 jr nz,wheel_leaf_miss
 ld a,(hl)
 or a
 jr z,wheel_leaf_miss
 ld de,#9
 add hl,de
 ld a,(#_Seg_left)
 cp (hl)
 jr nz,wheel_leaf_miss
 pop de
 ld hl,#4
 add hl,de
 ld a,(hl)
 cp #2
 ret z
 jr nc,wheel_leaf_answer
 push de
 call wheel_leaf_scan
 pop de
 ld hl,#4
 add hl,de
 ld a,(hl)
 cp #2
 ret z
wheel_leaf_answer:
 ; Empty or one interior exhausts the original window without a merge.
 push af
 ld hl,#14
 add hl,de
 ld a,(hl+)
 ld (#_Seg_cur),a
 ld a,(hl)
 ld (#_Seg_cur+1),a
 xor a
 ld (#_Seg_left),a
 ld a,(#_riding_contact_qx)
 and #63
 ld c,a
 ld a,(#_riding_contact_qy)
 and #63
 ld b,a
 pop af
 ret
wheel_leaf_miss:
 pop hl
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld a,(#_Seg_cur)
 ld (hl+),a
 ld a,(#_Seg_cur+1)
 ld (hl+),a
 ld (hl),#1
 ld de,#9
 add hl,de
 ld a,(#_Seg_left)
 ld (hl+),a
 inc hl
 inc hl
 ld (hl),#0                 ; clear the ambiguous-window admission state
 ld a,#1
 ret

; Classify the entire ordered window at once. The previous query already
; recorded which individual records are clear, interiors or endpoint caps.
; Keep at most one unresolved record, and prove its tangent only if needed.
.area _DATA
wheel_leaf_left: .ds 1

.area _CODE_31
wheel_leaf_scan:
 push de
 ld hl,#4
 add hl,de
 ld (hl),#2                ; General unless the complete scan proves otherwise.
 xor a
 ld (#_riding_leaf_one+1),a
 ld hl,#_riding_leaf_box
 ld b,(hl)
 inc hl
 ld c,(hl)
 ld a,(#_Seg_left)
 ld (#wheel_leaf_left),a
 ld hl,#_Seg_cur
 ld a,(hl+)
 ld h,(hl)
 ld l,a
wheel_leaf_record:
 ld de,#14
 add hl,de
 ld a,b
 cp (hl)
 inc hl
 jr c,wheel_leaf_skip3
 ld a,(hl+)
 cp b
 jr c,wheel_leaf_skip2
 ld a,c
 cp (hl)
 inc hl
 jr c,wheel_leaf_skip1
 ld a,(hl+)
 cp c
 jr c,wheel_leaf_next
 push hl
 ld a,l
 sub #18
 ld e,a
 ld a,h
 sbc #0
 ld d,a
 ld a,(#_riding_contact_regions_dirty)
 or a
 jr nz,wheel_leaf_unproven
 ld a,e
 and #30
 add a
 add a
 ld l,a
 ld h,#0
 push de
 ld de,#_riding_contact_regions
 add hl,de
 pop de
 ld a,(hl+)
 or a
 jr z,wheel_leaf_unproven
 push af
 ld a,(hl+)
 cp e
 jr nz,wheel_leaf_wrong_record
 ld a,(hl+)
 cp d
 jr nz,wheel_leaf_wrong_record
 ld a,(hl+)
 cp b
 jr nz,wheel_leaf_wrong_record
 ld a,(hl)
 cp c
 jr nz,wheel_leaf_wrong_record
 pop af
 dec a
 jr z,wheel_leaf_rejected
 dec a
 jr z,wheel_leaf_interior
 ; Cap kinds 3/5 name the start and 4/6 the end. Interior subdivision
 ; points have no radial contact. A real cap stays with the general loop.
 ld hl,#13
 add hl,de
 bit 0,a
 jr z,wheel_leaf_end
 bit 6,(hl)
 jr nz,wheel_leaf_rejected
 jr wheel_leaf_general
wheel_leaf_end:
 bit 7,(hl)
 jr nz,wheel_leaf_rejected
 jr wheel_leaf_general
wheel_leaf_wrong_record:
 pop af
wheel_leaf_unproven:
 xor a
 jr wheel_leaf_candidate
wheel_leaf_interior:
 inc a
wheel_leaf_candidate:
 ld (#_riding_leaf_proven),a
 ld a,(#_riding_leaf_one+1)
 or a
 jr nz,wheel_leaf_general
 ld a,e
 ld (#_riding_leaf_one),a
 ld a,d
 ld (#_riding_leaf_one+1),a
wheel_leaf_rejected:
 pop hl
 jr wheel_leaf_next
wheel_leaf_skip3:
 inc hl
wheel_leaf_skip2:
 inc hl
wheel_leaf_skip1:
 inc hl
wheel_leaf_next:
 ld a,(#wheel_leaf_left)
 dec a
 ld (#wheel_leaf_left),a
 jp nz,wheel_leaf_record
 ld b,h
 ld c,l
 pop de
 ld hl,#14
 add hl,de
 ld a,c
 ld (hl+),a
 ld (hl),b
 ld a,(#_riding_leaf_one+1)
 or a
 jp nz,_riding_leaf_classify
 ld hl,#4
 add hl,de
 ld (hl),#3
 ret
wheel_leaf_general:
 pop hl
 pop de
 ret

; Dense windows retain the ordered first-to-last box matches, including
; their original suffix. Repeating an integer center reuses the complete
; solved result. Each slot stores the exact cursor and the number of bytes
; the reference writes into Ct (0, 6, or 20 when a merge was attempted).
.area _DATA
dense_contacts: .ds 80       ; two ten-byte contacts per leaf slot
dense_slot: .ds 2
_riding_dense_merged:: .ds 1

.area _CODE_31
; The geometric leaf key already matches DE. Byte 16 is 0 on replacement,
; 1 after observing an ambiguous center, and 2 when the index is complete.
; Wait for spatial reuse before spending time on another ordered scan.
dense_leaf_query:
 ld hl,#16
 add hl,de
 ld a,(hl)
 cp #2
 jr z,dense_leaf_cached
 or a
 jr nz,dense_leaf_probe
 inc (hl)
dense_leaf_note:
 inc hl
 ld a,(#_riding_contact_qx)
 ld (hl+),a
 ld a,(#_riding_contact_qy)
 ld (hl),a
 ld hl,#_riding_leaf_general
 ret
dense_leaf_probe:
 inc hl
 ld a,(#_riding_contact_qx)
 xor (hl)
 inc hl
 ld b,a
 ld a,(#_riding_contact_qy)
 xor (hl)
 or b
 and #0xf8                 ; both centers lie in the same 8-unit square
 dec hl
 dec hl
 jr nz,dense_leaf_note
 inc (hl)
 call dense_leaf_select
 jr dense_leaf_build
dense_leaf_cached:
 call dense_leaf_select
 ld hl,#9
 add hl,de
 ld a,(#_riding_contact_qx)
 cp (hl)
 inc hl
 jr nz,dense_leaf_changed
 ld a,(#_riding_contact_qx+1)
 cp (hl)
 inc hl
 jr nz,dense_leaf_changed
 ld a,(#_riding_contact_qy)
 cp (hl)
 inc hl
 jr nz,dense_leaf_changed
 ld a,(#_riding_contact_qy+1)
 cp (hl)
 jr nz,dense_leaf_changed
 ld hl,#17
 add hl,de
 ld b,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld a,(hl+)
 ld (#_Seg_cur),a
 ld a,(hl+)
 ld (#_Seg_cur+1),a
 ld a,(hl)
 ld (#_Seg_left),a
 call dense_leaf_contacts
 ld de,#_Ct
 call dense_leaf_copy
 ld hl,#wheel_leaf_result
 ret
dense_leaf_changed:
 ld hl,#5
 add hl,de
 jp dense_leaf_solve
dense_leaf_select:
 ld a,e
 ld (#dense_slot),a
 ld a,d
 ld (#dense_slot+1),a
 ret

dense_leaf_build:
 ld hl,#5
 add hl,de
 push hl                     ; destination for narrowed pointer and count
 ld a,(#_Seg_left)
 ld d,a                      ; remaining records
 ld a,(#_riding_leaf_box)
 ld b,a
 ld a,(#_riding_leaf_box+1)
 ld c,a
 ld hl,#_Seg_cur
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld e,#0                     ; remaining at first match, inclusive
dense_leaf_record:
 push de
 ld de,#14
 add hl,de
 pop de
 ld a,b
 cp (hl)
 inc hl
 jr c,dense_leaf_skip3
 ld a,(hl+)
 cp b
 jr c,dense_leaf_skip2
 ld a,c
 cp (hl)
 inc hl
 jr c,dense_leaf_skip1
 ld a,(hl+)
 cp c
 jr c,dense_leaf_next
 ld a,e
 or a
 jr nz,dense_leaf_last
 ; Install the first accepted pointer while keeping the scan cursor in HL.
 ld e,d
 push hl
 call dense_leaf_address
 inc hl
 inc hl
 inc hl
 inc hl
 inc hl
 pop bc
 ld a,c
 sub #18
 ld (hl+),a
 ld a,b
 sbc #0
 ld (hl),a
 ld h,b
 ld l,c
 ld a,(#_riding_leaf_box)
 ld b,a
 ld a,(#_riding_leaf_box+1)
 ld c,a
dense_leaf_last:
 push hl
 call dense_leaf_address
 ld a,#8
 add l
 ld l,a
 jr nc,dense_leaf_store_suffix
 inc h
dense_leaf_store_suffix:
 ld a,d
 dec a
 ld (hl),a
 pop hl
 jr dense_leaf_next
dense_leaf_skip3:
 inc hl
dense_leaf_skip2:
 inc hl
dense_leaf_skip1:
 inc hl
dense_leaf_next:
 dec d
 jr nz,dense_leaf_record
 ld b,h
 ld c,l                      ; original end
 pop hl                      ; narrowed pointer
 push hl
 inc hl
 inc hl
 inc hl                      ; suffix
 ld a,e
 or a
 jr nz,dense_leaf_count
 ld (hl),a
dense_leaf_count:
 sub (hl)
 dec hl
 ld (hl+),a                  ; narrowed count
 ld de,#6
 add hl,de                   ; original window end at offset 14
 ld (hl),c
 inc hl
 ld (hl),b
 pop hl

dense_leaf_solve:
 ld a,(hl+)
 ld (#_Seg_cur),a
 ld a,(hl+)
 ld (#_Seg_cur+1),a
 ld a,(hl)
 ld (#_Seg_left),a
 ld b,a
 xor a
 ld (#_riding_dense_merged),a
 or b
 jr z,dense_leaf_finish
 ld e,#9
 ld hl,#_riding_leaf_general
 call ___sdcc_bcall_ehl
dense_leaf_finish:
 ld c,a
 call dense_leaf_address
 ld d,h
 ld e,l
 ld hl,#8                    ; suffix length
 add hl,de
 ld a,c
 cp #2
 jr z,dense_leaf_early
 ld hl,#14                   ; exhausting the window must consume the suffix
 add hl,de
 ld a,(hl+)
 ld (#_Seg_cur),a
 ld a,(hl)
 ld (#_Seg_cur+1),a
 xor a
 ld (#_Seg_left),a
 jr dense_leaf_save
dense_leaf_early:
 ld a,(#_Seg_left)           ; early return keeps the original unread suffix
 add (hl)
 ld (#_Seg_left),a
dense_leaf_save:
 ld hl,#9
 add hl,de
 ld a,(#_riding_contact_qx)
 ld (hl+),a
 ld a,(#_riding_contact_qx+1)
 ld (hl+),a
 ld a,(#_riding_contact_qy)
 ld (hl+),a
 ld a,(#_riding_contact_qy+1)
 ld (hl),a
 ld hl,#17
 add hl,de
 ld a,(#_riding_dense_merged)
 or a
 ld b,#20
 jr nz,dense_leaf_have_length
 ld b,c                      ; zero for empty
 ld a,c
 or a
 jr z,dense_leaf_have_length
 ld b,#6
dense_leaf_have_length:
 ld a,b
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld a,(#_Seg_cur)
 ld (hl+),a
 ld a,(#_Seg_cur+1)
 ld (hl+),a
 ld a,(#_Seg_left)
 ld (hl),a
 call dense_leaf_contacts
 ld d,h
 ld e,l
 ld hl,#_Ct
 call dense_leaf_copy
 ld hl,#wheel_leaf_result
 ret

; DE points to one of four 32-byte leaf entries. The result slots share
; their collision-reset, FIFO replacement and ordered-window identity.
dense_leaf_contacts:
 ld a,e
 sub #<_riding_leaf_regions
 rrca
 ld e,a                       ; 16*slot
 rrca
 rrca
 add e                        ; 20*slot
 ld e,a
 ld d,#0
 ld hl,#dense_contacts
 add hl,de
 ret
dense_leaf_address:
 ld hl,#dense_slot
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ret
dense_leaf_copy:
 ld a,b
 or a
 ret z
 cp #20
 jr nz,dense_leaf_copy_six
 .rept 14
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
dense_leaf_copy_six:
 .rept 6
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 ret
