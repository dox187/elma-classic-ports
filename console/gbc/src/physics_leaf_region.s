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
wheel_leaf_empty:
 xor a
 ret
wheel_leaf_distance:
 ld h,d
 ld l,e
 jp _riding_plane_distance

.area _CODE_31
wheel_leaf_request:
 call wheel_leaf_lookup
 ld hl,#_riding_leaf_general
 cp #3
 ret c
 ld hl,#wheel_leaf_empty
 ret z
 cp #5
 jr z,wheel_leaf_unit_y
 bit 3,a
 ld hl,#_riding_plane_fill
 ret z
 ld hl,#_riding_plane_affine
 ret
wheel_leaf_unit_y:
 ; A signed unit Y axis and a small X coefficient use the exact shallow
 ; dot directly. The table reader restores the tracked caller bank.
 ld hl,#5
 add hl,de
 ld a,c
 add (hl)
 inc hl
 ld e,a
 ld a,#0
 adc (hl)
 inc hl
 ld d,a
 ld a,b
 add (hl)
 inc hl
 ld c,a
 ld a,#0
 adc (hl)
 inc hl
 ld b,a
 push hl
 inc hl
 inc hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 call _riding_terrain_dotq14
 pop de
 ld hl,#wheel_leaf_distance
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
 xor (hl)
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
 ld (hl),a
 ld a,#2
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
