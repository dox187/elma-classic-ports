; DE,BC are the upper unsigned words of the two Q18 coordinates. One
; quarter metre is one unit. A=0 empty, 1..254 ordered leaf index, 255 unknown.
.module wheel_terrain
.area _CODE_9
_riding_wheel_lookup::
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
 call _riding_wheel_read_map
 ; A indexes four row-major half-metre certificates in bank 9.
 ld l,a
 ld h,#0
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
 or a
 jr z,wheel_read_done
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
wheel_read_done:
 ld c,a
 xor a
 ld (#0x3000),a
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
 jr wheel_install
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
