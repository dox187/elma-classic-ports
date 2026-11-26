; DE,BC are the upper unsigned words of the two Q18 coordinates. One
; quarter metre is one unit. A=0 empty, 1..63 plane, 64..254 ordered window, 255 unknown.
.module wheel_terrain
.area _CODE_9
_riding_wheel_lookup::
 jp wheel_refinement_lookup
wheel_initial_lookup:
 ld a,d
 or b
 and #0xf0
 jr nz,wheel_unknown
 ; Pack the within-cell quarter-metre coordinates in one byte, X high.
 ld a,e
 and #15
 swap a
 ld h,a
 ld a,c
 and #15
 or h
 push af
 ; Collapse the remaining upper 8 bits of each coordinate to a coarse cell.
 ld a,e
 swap a
 and #15
 swap d
 or d
 ld e,a
 ld a,c
 swap a
 and #15
 swap b
 or b
 ld c,a
 ld a,(#_physics_level_index)
 cp #_wheel_terrain_levels
 jr nc,wheel_outside
 ld l,a
 ld h,#0
 add hl,hl
 add hl,hl
 ; Preserve the cell coordinates while forming the map pointer.
 push de
 ld de,#_wheel_terrain_maps
 add hl,de
 pop de
 ld d,(hl)
 ld a,e
 cp d
 jr nc,wheel_outside
 inc hl
 ld a,c
 cp (hl)
 jr nc,wheel_outside
 inc hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ; Address the current 3-byte row descriptor.
 ld b,#0
 add hl,bc
 add hl,bc
 add hl,bc
 ld a,(hl+)
 ld b,(hl)
 inc hl
 ld c,(hl)
 ld l,a
 ld h,b
 ld a,h
 or a
 jr nz,wheel_real_row
 ; Row 0 contains only empty cells. Row 1 is the general-query fallback.
 pop bc
 ld a,l
 or a
 ret z
wheel_unknown:
 ld a,#255
 ret
wheel_outside:
 pop bc
 jr wheel_unknown
wheel_real_row:
 ; DE is width:cx, C is low bank byte. Keep the half-metre selector
 ; across the ROM0 read. HL includes the high bank bit in bit 15.
 pop af
 push af
 ld b,a
 rlca
 rlca
 and #3
 push de
 ld e,a
 ld a,b
 and #12
 or e
 pop de
 ld b,a
 ld a,c
 ld c,b
 jp _riding_wheel_read_map
wheel_half_pattern:
 ; BA indexes four row-major half-metre certificates in bank 9.
 ld l,a
 ld h,b
 add hl,hl
 add hl,hl
 ld de,#_wheel_terrain_patterns
 add hl,de
 pop af
 ld b,a
 and #2
 ld c,a
 ld a,b
 swap a
 rrca
 and #1
 or c
 ld e,a
 ld d,#0
 add hl,de
 ld a,(hl)
 ret

.area _CODE
; HL is the row's tagged address, DE is width:cx, C is the 1m index.
; Game IRQ handlers stay in ROM0 and preserve the MBC5 registers.
_riding_wheel_read_map::
 ld (#0x2000),a
 xor a
 bit 7,h
 jr z,wheel_bank_ready
 inc a
 res 7,h
wheel_bank_ready:
 ld (#0x3000),a
 push hl
 ld a,e
 add l
 ld l,a
 jr nc,wheel_cell_addr
 inc h
wheel_cell_addr:
 ld a,(hl)
 pop hl
 ld b,#0
 or a
 jr z,wheel_read_done
 cp #64
 jr nc,wheel_tagged_layout
wheel_plain_layout:
 dec a
 ld e,d
 ld d,#0
 add hl,de
 ld e,c
 add hl,de
 swap a
 ld d,a
 and #240
 ld e,a
 ld a,d
 and #15
 ld d,a
 add hl,de
 ld a,(hl)
 bit 0,b
 jr z,wheel_read_done
 ld b,#0
 bit 7,a
 jr z,wheel_read_done
 res 7,a
 jp _riding_wheel_read_quarter

wheel_tagged_layout:
 bit 7,a
 jr nz,wheel_read_extended
 and #63
 inc b
 jr wheel_plain_layout

wheel_read_extended:
 ; This layout starts 18*abs(index) bytes before the row's cell IDs.
 cpl
 inc a
 ld e,a
 ld d,#0
 push hl
 ld l,e
 ld h,d
 add hl,hl
 add hl,hl
 add hl,hl
 add hl,de
 add hl,hl
 ld d,h
 ld e,l
 pop hl
 ld a,l
 sub e
 ld l,a
 ld a,h
 sbc d
 ld h,a
 ld d,#0
 ld e,c
 add hl,de
 ld e,(hl)
 ; Select one of sixteen bits at layout+16 after reading layout[sub].
 ld a,#16
 sub c
 bit 3,c
 jr z,wheel_page_byte
 inc a
wheel_page_byte:
 add l
 ld l,a
 jr nc,wheel_page_bit
 inc h
wheel_page_bit:
 ld a,(hl)
 bit 2,c
 jr z,wheel_low_nibble
 swap a
wheel_low_nibble:
 bit 1,c
 jr z,wheel_low_pair
 rrca
 rrca
wheel_low_pair:
 bit 0,c
 jr z,wheel_low_bit
 rrca
wheel_low_bit:
 and #1
 ld b,a
 ld a,e
wheel_read_done:
 ld c,a
 xor a
 ld (#0x3000),a
 ld a,#9
 ld (#0x2000),a
 ld a,c
 jp wheel_half_pattern

; Only quarter-coded entries come here, with the graphics bank still mapped.
; Skip an intermediate switch to bank 9 and return directly to the game.
_riding_wheel_read_quarter::
 ld l,a
 ld h,#0
 add hl,hl
 add hl,hl
 add hl,hl
 add hl,hl
 pop af
 ld b,a
 and #3
 add a,a
 add a,a
 ld c,a
 ld a,b
 swap a
 and #3
 or c
 ld e,a
 ld d,#0
 add hl,de
 ld de,#_wheel_quarter_patterns
 add hl,de
 xor a
 ld (#0x3000),a
 ld a,#5
 ld (#0x2000),a
 ld c,(hl)
 ld a,#9
 ld (#0x2000),a
 ld a,c
 ret

.area _CODE_9
; On a new quarter-metre square the normal cache has already recorded its
; complete key and armed the fallback countdown. DE is the wheel, BC its entry.
_riding_compiled_surface::
 push de
 push bc
 ld h,b
 ld l,c
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 call _riding_wheel_lookup
 cp #255
 jr z,wheel_fallback
 or a
 jr z,wheel_clear
 ld c,a
 pop hl
 push hl
wheel_query:
 push bc
 ; seg_query(cx,cy,subcell) takes cx in A, cy in E and one stack byte.
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 swap a
 ld e,a
 ld a,b
 swap a
 and #15
 or e
 ld d,a
 ld a,b
 rrca
 rrca
 and #3
 ld b,a
 ld a,(hl+)
 ld c,a
 and #12
 or b
 ld b,a
 ld a,(hl)
 swap a
 ld e,a
 ld a,c
 swap a
 and #15
 or e
 ld e,a
 ld a,d
 push bc
 inc sp
 call _seg_query
 pop bc
 ld a,c
 cp #64
 jr nc,wheel_window
 ld a,(#_Seg_left)
 cp c
 jr c,wheel_fallback
 dec c
 ld b,#0
 ld l,c
 ld h,b
 add hl,hl
 add hl,hl
 add hl,hl
 add hl,bc
 add hl,hl
 ld a,(#_Seg_cur)
 ld e,a
 ld a,(#_Seg_cur+1)
 ld d,a
 add hl,de
 jp wheel_install
wheel_fallback:
 pop bc
 pop de
 ld a,#255
 ret
wheel_clear:
 pop hl
 ld de,#4
 add hl,de
 ld (hl),#1
 pop de
 xor a
 ret

 ; Reacquire the leaf on every revisit. The three collision slots can
 ; be evicted by the other wheel or the swept head between two queries.
_riding_wheel_cached_window::
 ld c,a
 pop hl
 push hl
 jr wheel_query

wheel_window:
 ; C = 64 + 4*start + (count-1). Verify the entire interval before
 ; installing it, and leave the fallback countdown armed on failure.
 sub #64
 ld b,a
 and #3
 inc a
 ld e,a
 ld a,b
 rrca
 rrca
 and #63
 ld l,a
 add e
 ld d,a
 ld a,(#_Seg_left)
 sub d
 jr c,wheel_fallback
 ld b,a                   ; number of trailing records
 ld a,e
 ld (#_Seg_left),a
 ld h,#0
 ld d,h
 ld e,l
 add hl,hl
 add hl,hl
 add hl,hl
 add hl,de
 add hl,hl
 ld a,(#_Seg_cur)
 add l
 ld (#_Seg_cur),a
 ld a,(#_Seg_cur+1)
 adc h
 ld (#_Seg_cur+1),a
 pop hl
 inc hl
 inc hl
 inc hl
 inc hl
 ld (hl),c                ; Store the index, never a leaf slot pointer.
 pop hl
 inc hl
 ld e,(hl)
 inc hl
 ld a,(hl+)
 and #15
 ld d,a
 inc hl
 inc hl
 ld c,(hl)
 inc hl
 ld a,(hl)
 and #15
 push bc                  ; preserve the skipped suffix count
 ld b,a
 call _riding_contacts_loop
 pop bc
 ; Preserve the public iterator state even on an early second contact.
 cp #2
 jr z,wheel_window_pair
 ld e,a
 ld a,b
 or a
 ld a,e
 ret z
 push af
 ld h,#0
 ld l,b
 ld d,h
 ld e,l
 add hl,hl
 add hl,hl
 add hl,hl
 add hl,de
 add hl,hl
 ld a,(#_Seg_cur)
 add l
 ld (#_Seg_cur),a
 ld a,(#_Seg_cur+1)
 adc h
 ld (#_Seg_cur+1),a
 pop af
 ret
wheel_window_pair:
 ld a,(#_Seg_left)
 add b
 ld (#_Seg_left),a
 ld a,#2
 ret

wheel_install:
 ; HL is the sole possible interior. Store the plane relative to the same
 ; 256u square used by the warm cache. The leaf slot may then be evicted.
 pop de
 push de
 ld a,(de)
 and #15
 ld b,a
 inc de
 inc de
 ld a,(de)
 and #15
 ld c,a
 inc de
 inc de
 push de
 inc de
 xor a
 sub (hl)
 ld (de),a
 inc de
 inc hl
 ld a,b
 sbc (hl)
 ld (de),a
 inc de
 inc hl
 xor a
 sub (hl)
 ld (de),a
 inc de
 inc hl
 ld a,c
 sbc (hl)
 ld (de),a
 inc de
 inc hl
 inc hl
 inc hl
 inc hl
 inc hl
 ; ex -> ny, -ey -> nx.
 inc de
 inc de
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 dec de
 dec de
 dec de
 xor a
 sub (hl)
 ld (de),a
 inc de
 inc hl
 ld a,#0
 sbc (hl)
 ld (de),a
 inc de
 inc de
 inc de
 inc hl
 inc hl
 inc hl
 ld a,b
 add a,a
 add a,a
 add #128
 ld b,a
 call wheel_clip_axis
 jr c,wheel_disjoint
 ld a,c
 add a,a
 add a,a
 add #128
 ld b,a
 call wheel_clip_axis
 jr c,wheel_disjoint
 ; A fully contained square needs no bounds checks on subsequent visits.
 pop hl
 ld de,#9
 add hl,de
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 cpl
 or b
 or (hl)
 inc hl
 ld b,a
 ld a,(hl)
 cpl
 or b
 ld a,#2
 jr z,wheel_kind_ready
 inc a
wheel_kind_ready:
 ld de,#-12
 add hl,de
 ld (hl),a
 jp _riding_wheel_cached_plane
wheel_disjoint:
 pop hl
 ld (hl),#1
 pop hl
 pop de
 xor a
 ret

; Clip a record's inclusive 64u boxes to this quarter-metre square. The
; cached endpoints are unsigned offsets 0..255. Carry means disjoint.
wheel_clip_axis:
 ld a,(hl+)
 sub b
 jr c,wheel_clip_min_zero
 cp #4
 jr nc,wheel_clip_outside
 rrca
 rrca
 jr wheel_clip_min_store
wheel_clip_min_zero:
 xor a
wheel_clip_min_store:
 ld (de),a
 inc de
 ld a,(hl+)
 sub b
 ret c
 cp #3
 jr nc,wheel_clip_max_full
 rrca
 rrca
 or #63
 jr wheel_clip_max_store
wheel_clip_max_full:
 ld a,#255
wheel_clip_max_store:
 ld (de),a
 inc de
 or a
 ret
wheel_clip_outside:
 scf
 ret

.area _CODE
; Preserve the complete quarter-square coordinates across the base map.
; Only an ordered window or an unresolved region can benefit from refinement.
wheel_refinement_lookup:
 push bc
 push de
 call wheel_initial_lookup
 cp #64
 jr c,wheel_refinement_done
 push af
 ldhl sp,#2
 ld a,#20
 ld (#0x2000),a
_riding_wheel_refinement_mapped::
 call _riding_wheel_refinement
 ld e,a
 ld a,#9
 ld (#0x2000),a
 ld a,e
 inc a
 jr z,wheel_refinement_fallback
 pop af
 ld a,e
 jr wheel_refinement_done
wheel_refinement_fallback:
 pop af
wheel_refinement_done:
 add sp,#4
 ret

.area _CODE_20
_riding_wheel_refinement::
 ; Map the two unsigned quarter-metre values to the coarse cell and its
 ; one-metre subcell. Queries outside the collision grid use the old answer.
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 cp #16
 jr nc,wheel_refinement_out
 swap a
 ld d,a
 ld a,e
 swap a
 and #15
 or d
 ld d,a
 ld a,(hl+)
 ld c,a
 ld a,(hl)
 cp #16
 jr nc,wheel_refinement_out
 swap a
 ld b,a
 ld a,c
 swap a
 and #15
 or b
 ld b,a
 ld a,e
 and #3
 ld h,a
 ld a,c
 and #3
 add a
 add a
 or h
 push af
 ld a,e
 rrca
 rrca
 and #3
 ld e,a
 ld a,c
 and #12
 or e
 ld c,a
 ld e,b
 ld a,(#_physics_level_index)
 cp #_wheel_terrain_levels
 jr nc,wheel_refinement_miss
 ld l,a
 ld h,#0
 add hl,hl
 add l
 ld l,a
 ld a,h
 adc #0
 ld h,a
 push de
 ld de,#_wheel_refinement_levels
 add hl,de
 pop de
 ld a,(hl+)
 ld b,a
 or a
 jr z,wheel_refinement_miss
 ld a,(hl+)
 ld h,(hl)
 ld l,a
wheel_refinement_record:
 ld a,d
 cp (hl)
 inc hl
 jr c,wheel_refinement_miss
 jr nz,wheel_refinement_skip7
 ld a,(hl+)
 cp e
 jr nz,wheel_refinement_skip6
 ld a,(hl+)
 cp c
 jr z,wheel_refinement_found
 inc hl
wheel_refinement_skip4:
 inc hl
 inc hl
 inc hl
 inc hl
 dec b
 jr nz,wheel_refinement_record
wheel_refinement_miss:
 pop af
wheel_refinement_out:
 ld a,#255
 ret
wheel_refinement_skip7:
 inc hl
wheel_refinement_skip6:
 inc hl
 inc hl
 jr wheel_refinement_skip4
wheel_refinement_found:
 pop af
 ld c,a
 ld a,(hl+)
 bit 3,c
 jr z,wheel_refinement_pair
 rrca
 rrca
wheel_refinement_pair:
 bit 2,c
 jr z,wheel_refinement_page
 rrca
wheel_refinement_page:
 and #1
 ld b,a
 ld a,c
 rrca
 rrca
 and #3
 add l
 ld l,a
 jr nc,wheel_refinement_row
 inc h
wheel_refinement_row:
 ld l,(hl)
 ld h,b
 add hl,hl
 add hl,hl
 ld a,c
 and #3
 ld e,a
 ld d,#0
 add hl,de
 ld de,#_wheel_refinement_rows
 add hl,de
 ld a,(hl)
 ret
