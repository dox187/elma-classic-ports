; Native contact candidate iteration. Near bank9, ABI1 qx=DE,qy=BC -> A.
; Retains ordered box iterator and existing exact projection/normal/merge math.
.module physics_contact_loop
.area _DATA
_riding_leaf_box::
contact_loop_box: .ds 2
contact_loop_found: .ds 1
contact_loop_seg: .ds 2
contact_loop_k: .ds 2
contact_loop_x: .ds 2
contact_loop_y: .ds 2
contact_loop_d: .ds 2
 .ifdef RIDING_NORMAL_ATLAS
; ceil(63 * (sqrt(2) * 16384 + 1) / 16384) for rounded unit tangents.
CONTACT_REGION_DELTA = 90
contact_region_slot: .ds 2
; Sixteen direct-mapped entries. A zero kind invalidates its entire entry.
; Each key contains the record pointer and both within-cell box coordinates.
_riding_contact_regions::
contact_regions: .ds 128
 .endif
.area _CODE_9
_riding_contacts_loop::
 ld a,(#_Seg_left)
 or a,a
 ret z
 ld hl,#_riding_contact_qx
 ld a,e
 ld (hl+),a
 ld (hl),d
 ld hl,#_riding_contact_qy
 ld a,c
 ld (hl+),a
 ld (hl),b
 ; The 64u broad-phase box also keys the tangent/normal certificates.
 ld a,e
 rlca
 rlca
 and #3
 ld e,a
 ld a,d
 add a
 add a
 or e
 add #128
 ld (#contact_loop_box),a
 ld a,c
 rlca
 rlca
 and #3
 ld c,a
 ld a,b
 add a
 add a
 or c
 add #128
 ld (#contact_loop_box+1),a
 .ifdef RIDING_LEAF_REGION
 jp _riding_leaf_dispatch
_riding_leaf_general::
 .endif
 xor a,a
 ld (#contact_loop_found),a
 ld hl,#contact_loop_k
 ld (hl),#<_Ct
 inc hl
 ld (hl),#>_Ct
contact_loop_next:
 ld a,(#_Seg_left)
 or a
 jr z,contact_loop_done
 ld hl,#contact_loop_box
 ld b,(hl)
 inc hl
 ld c,(hl)
 call _riding_segment_box_regs
 jr c,contact_loop_record
contact_loop_done:
 ld a,(#contact_loop_found)
 ret
contact_loop_record:
 ld hl,#contact_loop_seg
 ld a,e
 ld (hl+),a
 ld (hl),d
 ld h,d
 ld l,e
 ld a,(#_riding_contact_qx)
 sub a,(hl)
 inc hl
 ld (#contact_loop_x),a
 ld a,(#_riding_contact_qx+1)
 sbc a,(hl)
 inc hl
 ld (#contact_loop_x+1),a
 ld a,(#_riding_contact_qy)
 sub a,(hl)
 inc hl
 ld (#contact_loop_y),a
 ld a,(#_riding_contact_qy+1)
 sbc a,(hl)
 inc hl
 ld (#contact_loop_y+1),a
 ld de,#4
 add hl,de
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ; Exact Q14 unit axes project by selecting a signed coordinate. All other
 ; normals, including nearly horizontal or vertical ones, use the full dot.
 ld a,c
 or a,e
 jr nz,contact_loop_general
 ld a,b
 or a,a
 jr z,contact_loop_vertical
 ld a,d
 or a,a
 jr nz,contact_loop_general
 ld a,b
 cp #0x40
 jr z,contact_loop_axis_right
 cp #0xc0
 jr nz,contact_loop_general
 call contact_loop_xy
 call contact_loop_neg_pos
 call contact_loop_neg_distance
 jr contact_loop_axis_ready
contact_loop_axis_right:
 call contact_loop_xy
 jr contact_loop_axis_ready
contact_loop_vertical:
 ld a,d
 cp #0x40
 jr z,contact_loop_axis_up
 cp #0xc0
 jr nz,contact_loop_general
 call contact_loop_yx
 call contact_loop_neg_pos
 jr contact_loop_axis_ready
contact_loop_axis_up:
 call contact_loop_yx
 call contact_loop_neg_distance
contact_loop_axis_ready:
 push de
 call contact_loop_in_radius
 pop bc
 jp nc,contact_loop_next
 jr contact_loop_position
contact_loop_general:
 .ifdef RIDING_NORMAL_ATLAS
 call contact_region_dispatch
 or a
 jp z,contact_loop_next
 dec a
 jr z,contact_loop_interior
 dec a
 jr nz,contact_loop_position
 ; An endpoint certificate supplies a representative position with the
 ; correct sign. The original endpoint flags and radial solver follow.
 jp contact_loop_endpoint
 .else
 push bc
 xor a,a
 sub a,e
 ld e,a
 sbc a,a
 sub a,d
 ld d,a
 push de
 call contact_loop_xy
 call _dotq14
 call contact_loop_in_radius
 jp nc,contact_loop_next
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#8
 add hl,de
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 push bc
 push de
 call contact_loop_xy
 call _dotq14
 .endif
contact_loop_position:
 ; Low14 length; high bits identify synthetic endpoints.
 bit 7,b
 jp nz,contact_loop_endpoint
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#12
 add hl,de
 ld a,(hl+)
 ld e,a
 ld a,(hl)
 and a,#0x3f
 ld d,a
 ld a,e
 sub a,c
 ld a,d
 sbc a,b
 jp c,contact_loop_endpoint
 ; An artificial end belongs to the next piece, avoiding duplicate normals.
 ld a,e
 cp a,c
 jr nz,contact_loop_interior
 ld a,d
 cp a,b
 jr nz,contact_loop_interior
 bit 7,(hl)
 jp nz,contact_loop_next
contact_loop_interior:
 ; Write nx,ny,l directly into the selected ten-byte Ct record.
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#8
 add hl,de
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ld a,(#contact_loop_d+1)
 bit 7,a
 jr nz,contact_loop_negative
 xor a,a
 sub a,e
 ld e,a
 sbc a,a
 sub a,d
 ld d,a
 jr contact_loop_write_normal
contact_loop_negative:
 xor a,a
 sub a,c
 ld c,a
 sbc a,a
 sub a,b
 ld b,a
contact_loop_write_normal:
 ld hl,#contact_loop_k
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld a,(#contact_loop_d)
 ld e,a
 ld a,(#contact_loop_d+1)
 ld d,a
 bit 7,d
 jr z,contact_loop_write_length
 xor a,a
 sub a,e
 ld e,a
 sbc a,a
 sub a,d
 ld d,a
contact_loop_write_length:
 ld a,e
 ld (hl+),a
 ld (hl),d
 jp contact_loop_accept
contact_loop_endpoint:
 ; BC is projected position: negative selects start, positive selects end.
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#13
 add hl,de
 bit 7,b
 jr z,contact_loop_check_end
 bit 6,(hl)
 jp nz,contact_loop_next
 jr contact_loop_original_endpoint
contact_loop_check_end:
 bit 7,(hl)
 jp nz,contact_loop_next
contact_loop_original_endpoint:
 bit 7,b
 jr nz,contact_loop_endpoint_ready
 ld a,b
 or a,c
 jr z,contact_loop_endpoint_ready
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#4
 add hl,de
 ld a,(#contact_loop_x)
 sub a,(hl)
 inc hl
 ld (#contact_loop_x),a
 ld a,(#contact_loop_x+1)
 sbc a,(hl)
 inc hl
 ld (#contact_loop_x+1),a
 ld a,(#contact_loop_y)
 sub a,(hl)
 inc hl
 ld (#contact_loop_y),a
 ld a,(#contact_loop_y+1)
 sbc a,(hl)
 ld (#contact_loop_y+1),a
contact_loop_endpoint_ready:
 call contact_loop_xy
 ld a,e
 add a,#0x99
 ld l,a
 ld a,d
 adc a,#1
 ld h,a
 ld a,l
 sub a,#0x33
 ld a,h
 sbc a,#3
 jp nc,contact_loop_next
 ld a,c
 add a,#0x99
 ld l,a
 ld a,b
 adc a,#1
 ld h,a
 ld a,l
 sub a,#0x33
 ld a,h
 sbc a,#3
 jp nc,contact_loop_next
 .ifdef RIDING_NORMAL_ATLAS
 ; Coordinates are bounded to [-409,409]. An atlas hit proves d2 < 410^2.
 ld hl,#contact_loop_k
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call _riding_normal_ring
 jp c,contact_loop_next
 or a
 jr nz,contact_loop_accept
 push hl                      ; a miss restores the contact pointer and both coordinates
 call _riding_endpoint_squared
 .else
 ; Existing exact multiply kernel, with its register entry avoiding ABI spills.
 ld hl,#contact_loop_k
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 ld b,d
 ld c,e
 call _riding_mul16_regs
 push hl
 push de
 ld hl,#contact_loop_y
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ld b,d
 ld c,e
 call _riding_mul16_regs
 pop bc
 ld a,e
 add a,c
 ld c,a
 ld a,d
 adc a,b
 ld b,a
 pop de
 ld a,l
 adc a,e
 ld e,a
 ld a,h
 adc a,d
 ld d,a
 .endif
 ; d2 is nonnegative after the strict coordinate guards above.
 ld a,c
 sub a,#0xa4
 ld a,b
 sbc a,#0x90
 ld a,e
 sbc a,#2
 ld a,d
 sbc a,#0
 jr c,contact_loop_normalize
 pop hl
 jp contact_loop_next
contact_loop_normalize:
 push de
 push bc
 call contact_loop_xy
 push bc
 push de
 call _riding_normal_fast
 add sp,#10
contact_loop_accept:
 ld a,(#contact_loop_found)
 or a,a
 jr nz,contact_loop_merge
 inc a
 ld (#contact_loop_found),a
 ld hl,#contact_loop_k
 ld (hl),#<(_Ct+10)
 inc hl
 ld (hl),#>(_Ct+10)
 jp contact_loop_next
contact_loop_merge:
 .ifdef RIDING_LEAF_REGION
 ld (#_riding_dense_merged),a   ; nonzero first-contact flag
 .endif
 call _riding_contact_merge
 or a,a
 jp z,contact_loop_next
 ret
contact_loop_xy:
 ld hl,#contact_loop_x
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ret
contact_loop_yx:
 ld hl,#contact_loop_y
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ld hl,#contact_loop_x
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ret
contact_loop_neg_pos:
 ; dotq14 saturates -(-32768) to +32767.
 xor a,a
 sub a,e
 ld e,a
 sbc a,a
 sub a,d
 ld d,a
 cp #0x80
 ret nz
 ld a,e
 or a,a
 ret nz
 dec de
 ret
contact_loop_neg_distance:
 ; Either signed extreme lies outside the wheel radius.
 xor a,a
 sub a,c
 ld c,a
 sbc a,a
 sub a,b
 ld b,a
 ret
contact_loop_in_radius:
 ld hl,#contact_loop_d
 ld a,c
 ld (hl+),a
 ld (hl),b
 ; -410<d<410 iff uint16(d+409)<819, including signed extremes.
 ld a,c
 add a,#0x99
 ld e,a
 ld a,b
 adc a,#1
 ld d,a
 ld a,e
 sub a,#0x33
 ld a,d
 sbc a,#3
 ret

 .ifdef RIDING_NORMAL_ATLAS
.area _CODE
; These helpers run in bank 7 so the ordinary bank-9 geometry loop stays
; beside the merge and normal atlas. The product kernel restores CURRENT_BANK.
contact_region_dispatch:
 ld a,#7
 ld (#0x2000),a
 ld (#__current_bank),a
 call contact_region_query
 ld h,a
 ld a,#9
 ld (#0x2000),a
 ld (#__current_bank),a
 ld a,h
 ret

.area _CODE_7
contact_region_query:
 ld a,(#_riding_contact_regions_dirty)
 or a
 jr z,contact_region_select
 xor a
 ld (#_riding_contact_regions_dirty),a
 ld hl,#contact_regions
 ld de,#8
 ld b,#16
contact_region_clear:
 ld (hl),a
 add hl,de
 dec b
 jr nz,contact_region_clear
contact_region_select:
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 and #30
 add a
 add a
 ld l,a
 ld h,#0
 ld bc,#contact_regions
 add hl,bc
 ld a,l
 ld (#contact_region_slot),a
 ld a,h
 ld (#contact_region_slot+1),a
 ld a,(hl+)
 or a
 jr z,contact_region_miss
 ld b,a
 ld a,(hl+)
 cp e
 jr nz,contact_region_miss
 ld a,(hl+)
 cp d
 jr nz,contact_region_miss
 ld a,(#contact_loop_box)
 cp (hl)
 inc hl
 jr nz,contact_region_miss
 ld a,(#contact_loop_box+1)
 cp (hl)
 jr nz,contact_region_miss
 ; Kinds 1..6 mean reject, interior, start, end, guarded start/end.
 ld a,b
 dec a
 ret z
 dec a
 jr z,contact_region_plane
 cp #3
 jr c,contact_region_endpoint
 push af
 call contact_region_distance
 pop bc
 ret nc
 ld a,b
 sub #2
contact_region_endpoint:
 ld bc,#-1
 dec a
 jr z,contact_region_cap
 ld bc,#1
contact_region_cap:
 ld a,#2
 ret
contact_region_plane:
 call contact_region_distance
 ret nc
 ld a,#1
 ret

contact_region_miss:
 call contact_region_distance
 jr c,contact_region_inside
 ; Geometry divides each segment into <=8m pieces and rounds its unit
 ; direction to Q14. Thus |ex|+|ey| <= sqrt(2)*16384+1. Across this
 ; 64u square each relative coordinate changes by <=63 without wrapping,
 ; so either rounded dot changes by at most CONTACT_REGION_DELTA.
 ld a,c
 add #<(409+CONTACT_REGION_DELTA)
 ld e,a
 ld a,b
 adc #>(409+CONTACT_REGION_DELTA)
 cp #>(819+2*CONTACT_REGION_DELTA)
 jr c,contact_region_reject
 jr nz,contact_region_set_reject
 ld a,e
 cp #<(819+2*CONTACT_REGION_DELTA)
 jr c,contact_region_reject
contact_region_set_reject:
 ld a,#1
 call contact_region_save
contact_region_reject:
 xor a
 ret
contact_region_inside:
 ; The tangent dot is only needed on a miss. Save the exact position even
 ; on boundaries, including the artificial end's half-open ownership.
 call contact_region_coeffs
 push de
 push bc
 ; Put the tangent's X axis in the same major-axis position as a
 ; near-horizontal edge's cross-distance projection.
 ld hl,#contact_loop_x
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 call _riding_terrain_dotq14
 push bc
 ld a,b
 bit 7,a
 jr z,contact_region_nonnegative
 cp #255
 jr nz,contact_region_start
 ld a,c
 cp #<(-CONTACT_REGION_DELTA)
 jr nc,contact_region_boundary
contact_region_start:
 ld a,#3
 jr contact_region_cert_cap
contact_region_nonnegative:
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#12
 add hl,de
 ld a,(hl+)
 ld e,a
 ld a,(hl)
 and #63
 ld d,a
 ; An interior certificate stays at least DELTA from the near boundary
 ; and strictly more than DELTA from the far boundary. Equality
 ; at the near end is legal. Staying strictly below len handles every flag.
 ld a,c
 sub e
 ld l,a
 ld a,b
 sbc d
 ld h,a
 jr nc,contact_region_beyond
 ld a,h
 cp #255
 jr nz,contact_region_check_start
 ld a,l
 cp #<(-CONTACT_REGION_DELTA)
 jr nc,contact_region_boundary
contact_region_check_start:
 ld a,b
 or a
 jr nz,contact_region_set_plane
 ld a,c
 cp #CONTACT_REGION_DELTA
 jr c,contact_region_boundary
contact_region_set_plane:
 ld a,#2
 jr contact_region_install
contact_region_beyond:
 ld a,h
 or a
 jr nz,contact_region_end
 ld a,l
 cp #(CONTACT_REGION_DELTA+1)
 jr c,contact_region_boundary
contact_region_end:
 ld a,#4
contact_region_cert_cap:
 ld b,a
 ld hl,#contact_loop_d
 ld a,(hl+)
 add #<(409-CONTACT_REGION_DELTA)
 ld e,a
 ld a,(hl)
 adc #>(409-CONTACT_REGION_DELTA)
 cp #>(819-2*CONTACT_REGION_DELTA)
 jr c,contact_region_sure_cap
 jr nz,contact_region_guard_cap
 ld a,e
 cp #<(819-2*CONTACT_REGION_DELTA)
 jr c,contact_region_sure_cap
contact_region_guard_cap:
 inc b
 inc b
contact_region_sure_cap:
 ld a,b
contact_region_install:
 call contact_region_save
contact_region_boundary:
 pop bc
 ld a,#3
 ret

contact_region_save:
 ld hl,#contact_region_slot
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld h,d
 ld l,e
 ld (hl+),a
 ld a,(#contact_loop_seg)
 ld (hl+),a
 ld a,(#contact_loop_seg+1)
 ld (hl+),a
 ld a,(#contact_loop_box)
 ld (hl+),a
 ld a,(#contact_loop_box+1)
 ld (hl),a
 ret
contact_region_coeffs:
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#8
 add hl,de
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ret
contact_region_xy:
 ld hl,#contact_loop_x
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ret
contact_region_distance:
 call contact_region_coeffs
 push de
 xor a
 sub c
 ld c,a
 sbc a
 sub b
 ld b,a
 push bc
 call contact_region_xy
 call _riding_terrain_dotq14
 ld hl,#contact_loop_d
 ld a,c
 ld (hl+),a
 ld (hl),b
 ld a,c
 add #0x99
 ld e,a
 ld a,b
 adc #1
 cp #3
 jr c,contact_region_in
 jr nz,contact_region_out
 ld a,e
 cp #0x33
 jr c,contact_region_in
contact_region_out:
 xor a
 ret
contact_region_in:
 scf
 ret
 .endif

 .ifdef RIDING_NORMAL_ATLAS
.area _CODE
; ABI of dotq14. For a unit second axis the first product rounds
; independently, including a half tie. Preserve the full-dot fallback.
_riding_terrain_dotq14::
 ldhl sp,#4
 ld a,(hl+)
 or a
 jp nz,_dotq14
 ld a,(hl)
 and #127
 cp #64
 jp nz,_dotq14
 ldhl sp,#3
 ld a,(hl-)
 inc a
 cp #2
 jp nc,_dotq14
 ld a,#34
 ld (#0x2000),a
 call terrain_minor_lookup
 ld a,(#__current_bank)
 ld (#0x2000),a
 jp nc,_dotq14
 pop hl
 add sp,#4
 jp (hl)

.area _CODE_34
; BC is the major coordinate, DE the minor coordinate and HL its
; coefficient. Every failure preserves the incoming coordinates.
terrain_minor_lookup:
 ld a,b
 add #129
 cp #2
 jr c,terrain_miss       ; leave signed16 saturation to the full dot
 ld a,d
 add #31
 cp #63
 jr nc,terrain_miss      ; accepted minor magnitude is below 8192
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 bit 7,h
 jr z,terrain_magnitude
 cpl
 inc a
 jr z,terrain_miss       ; -256
terrain_magnitude:
 cp #128
 jr nc,terrain_miss
 cp #2
 jr c,terrain_zero
 ld l,a
 ld a,h
 xor d
 push af                 ; sign of minor product
 bit 7,d
 jr z,terrain_index
 xor a
 sub e
 ld e,a
 sbc a
 sub d
 ld d,a
terrain_index:
 ld a,l
 rrca
 ld h,a
 and #128
 ld l,a
 ld a,h
 and #63
 or #64
 ld h,a
 ld a,e
 add a
 ld a,d
 rla
 add a
 or l
 ld l,a
 ld a,(hl+)
 ld d,a
 ld a,e
 and #127
 ld e,a
 cp (hl)
 jr c,terrain_same_bin
 inc d
terrain_same_bin:
 pop af
 bit 7,a
 jr z,terrain_positive
 ; A half tie is possible only at an input divisible by 128 for
 ; coefficients 2..127. Round the negative half toward positive infinity.
 bit 7,d
 jr z,terrain_negative
 ld a,e
 or a
 jr nz,terrain_negative
 dec d
terrain_negative:
 ld a,d
 and #127
 cpl
 inc a
 jr terrain_extend
terrain_positive:
 ld a,d
 and #127
terrain_extend:
 ld e,a
 add a
 sbc a
 ld d,a
 jr terrain_major
terrain_zero:
 ld de,#0
terrain_major:
 ldhl sp,#7
 bit 7,(hl)
 jr z,terrain_add
 ld a,e
 sub c
 ld c,a
 ld a,d
 sbc b
 ld b,a
 scf
 ret
terrain_add:
 ld a,e
 add c
 ld c,a
 ld a,d
 adc b
 ld b,a
 scf
 ret
terrain_miss:
 or a
 ret

; DE is the cache entry. The original bases remain available for the
; first projection (and for the full coordinate-wrap fallback).
terrain_plane_setup:
 ld hl,#5
 add hl,de
 push hl
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 inc hl
 inc hl
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 call _riding_projection_signed16
 push hl
 push de
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 inc hl
 inc hl
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 inc hl
 inc hl
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 call _riding_projection_signed16
 pop bc
 ld a,c
 add e
 ld e,a
 ld a,b
 adc d
 ld d,a
 pop bc
 ld a,c
 adc l
 ld c,a
 ld a,b
 adc h
 ld b,a
 pop hl
 dec hl
 set 3,(hl)
 ld a,#13
 add l
 ld l,a
 jr nc,terrain_plane_store
 inc h
terrain_plane_store:
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld (hl),b
 ret
terrain_lookup_end:
 ; Two bytes for every 128 consecutive positive input magnitudes. Their
 ; rounded values differ by at most one. Store the initial value, a tie
 ; flag, and the first offset giving the next integer (128 if absent).
 .ds 256-(terrain_lookup_end-terrain_minor_lookup)
terrain_n = 2
 .rept 126
terrain_x = 0
 .rept 64
terrain_raw = terrain_x*terrain_n+8192
terrain_base = terrain_raw/16384
terrain_cut = (16384*(terrain_base+1)-terrain_raw+terrain_n-1)/terrain_n
 .ifeq (terrain_raw & 16383)
 .db terrain_base+128
 .else
 .db terrain_base
 .endif
 .ifgt (terrain_cut-128)
 .db 128
 .else
 .db terrain_cut
 .endif
terrain_x = terrain_x+128
 .endm
terrain_n = terrain_n+1
 .endm
 .endif

 .ifdef RIDING_NORMAL_ATLAS
.area _CODE
; The initial raw intercept is the dot at offset (0,0). All later
; products use the unsigned byte offsets within the same 256u square.
_riding_plane_fill::
 push bc
 push de
 ld a,#34
 ld (#0x2000),a
 ld (#__current_bank),a
 call terrain_plane_setup
 ld a,#6
 ld (#0x2000),a
 ld (#__current_bank),a
 ; The builder only reads the WRAM plane and writes its private tail.
 pop de
 push de
 call plane_shallow_build
 ld a,#9
 ld (#0x2000),a
 ld (#__current_bank),a
 pop de
 pop bc
_riding_plane_affine::
 ld hl,#21
 add hl,de
 ld a,(hl+)
 or a
 jr z,plane_general
 ; At most two integer crossings are possible in 255 local X units.
 ; The encoded thresholds are the last X values before each crossing.
 ld e,a                      ; flags: bit 7 selects negative X, bit 6 negative Y
 ld a,(hl+)
 cp c
 ld d,#0
 rl d
 ld a,(hl+)
 cp c
 ld a,d
 adc #0
 ld d,a
 bit 7,e
 ld a,(hl+)
 jr nz,plane_shallow_sub_x
 add d
 ld c,a
 ld a,(hl)
 adc #0
 jr plane_shallow_y
plane_shallow_sub_x:
 sub d
 ld c,a
 ld a,(hl)
 sbc #0
plane_shallow_y:
 ld d,a
 bit 6,e
 ld a,c
 jr nz,plane_shallow_sub_y
 add b
 ld c,a
 ld a,d
 adc #0
 jr plane_shallow_distance
plane_shallow_sub_y:
 sub b
 ld c,a
 ld a,d
 sbc #0
plane_shallow_distance:
 ld b,a
 ld de,#-16                  ; offset 25 back to 9
 add hl,de
 jp _riding_plane_distance
plane_general:
 ld hl,#9
 add hl,de
 push hl
 call _riding_fraction_pair
 pop hl
 push hl                      ; normal pointer for the contact writer
 push de
 ld de,#8
 add hl,de                    ; raw dot at the origin of the cache square
 pop de
 ld a,e
 add (hl)
 inc hl
 ld a,d
 adc (hl)
 ld d,a
 inc hl
 ld a,c
 adc (hl)
 ld c,a
 inc hl
 ld a,b
 adc (hl)
 ld h,a
 ld l,c
 call _riding_terrain_reduce_q14
 pop hl
 jp _riding_plane_distance

.area _CODE_6
; The full row uses d(0,0), signed Y and zero, one or two crossings in X.
; For a signed unit Y normal the Y term is exactly integral. A minor normal
; of magnitude <=127 changes the rounded result by at most two over 255u.
plane_shallow_build:
 ld hl,#21
 add hl,de
 ld (hl),#0
 ld hl,#9
 add hl,de
 ld a,(hl+)
 ld c,a
 add a
 sbc a
 cp (hl)                    ; signed 8-bit X coefficient
 ret nz
 inc hl
 ld a,(hl+)
 or a
 ret nz
 ld a,(hl)
 and #127
 cp #64
 ret nz
 ld b,#1
 bit 7,(hl)
 jr z,plane_shallow_check_x
 set 6,b
plane_shallow_check_x:
 bit 7,c
 jr z,plane_shallow_magnitude
 ld a,c
 cpl
 inc a
 cp #128
 ret z
 ld c,a
 set 7,b
plane_shallow_magnitude:
 ld hl,#21
 add hl,de
 ld a,b
 ld (hl+),a
 push hl                     ; first threshold address
 ld hl,#17
 add hl,de
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 add #32
 ld d,a
 ld a,(hl+)
 adc #0
 ld h,(hl)
 jr nc,plane_shallow_no_carry
 inc h
plane_shallow_no_carry:
 ld l,a                      ; high word of biased raw
 push de
 ld a,d
 rlca
 rlca
 and #3
 add hl,hl
 add hl,hl
 or l
 ld l,a                      ; signed D0 modulo 65536
 pop de
 push hl                     ; store D0 after thresholds
 ld a,d
 and #63
 ld h,a
 ld l,e
 bit 7,b
 jr nz,plane_shallow_first
 ; With positive X, the threshold is floor((16383-remainder)/n).
 ld a,h
 xor #63
 ld h,a
 ld a,l
 cpl
 ld l,a
plane_shallow_first:
 push hl
 call plane_shallow_div
 pop hl
 ld d,a
 add #1
 jr z,plane_shallow_single
 ld a,h
 add #64                     ; one more complete Q14 quantum
 ld h,a
 call plane_shallow_div
 jr plane_shallow_save
plane_shallow_single:
 ld a,#255
plane_shallow_save:
 pop bc                      ; D0
 pop hl
 ld (hl),d
 inc hl
 ld (hl+),a
 ld (hl),c
 inc hl
 ld (hl),b
 ret
; min(255, floor(HL / C)). The precheck also covers zero coefficient.
plane_shallow_div:
 ld a,h
 cp c
 ld a,#255
 ret nc
 ld b,#8
plane_shallow_bit:
 sla l
 ld a,h
 rla
 cp c
 jr c,plane_shallow_remainder
 sub c
 inc l
plane_shallow_remainder:
 ld h,a
 dec b
 jr nz,plane_shallow_bit
 ld a,l
 ret
 .endif
