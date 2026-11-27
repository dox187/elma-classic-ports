; Native contact candidate iteration. Near bank9, ABI1 qx=DE,qy=BC -> A.
; Retains ordered box iterator and existing exact projection/normal/merge math.
.module physics_contact_loop
.area _DATA
_riding_leaf_box::
contact_loop_box:: .ds 2
 .ifdef RIDING_LEAF_REGION
_riding_record_program:: .ds 2
_riding_program_mode:: .ds 1
 .endif
; The initializer clears the count and reuse flag before publishing Ct[0].
contact_loop_found: .ds 1
 .ifdef RIDING_NORMAL_ATLAS
_riding_first_point_ready:: .ds 1
 .endif
contact_loop_k: .ds 2
contact_loop_seg:: .ds 2
contact_loop_x:: .ds 2
contact_loop_y: .ds 2
contact_loop_d:: .ds 2
 .ifdef RIDING_NORMAL_ATLAS
contact_region_cap_kind:: .ds 1
; Sixteen direct-mapped entries. A zero kind invalidates its entire entry.
; Each key contains the record pointer and both within-cell box coordinates.
_riding_contact_regions::
contact_regions:: .ds 128
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
 xor a
 ld (#_riding_program_mode),a
 .endif
 call contact_loop_init
 jr contact_loop_next
contact_loop_init:
 ld hl,#contact_loop_found
 xor a
 ld (hl+),a
 .ifdef RIDING_NORMAL_ATLAS
 ld (hl+),a
 .endif
 ld a,#<_Ct
 ld (hl+),a
 ld (hl),#>_Ct
 ret
contact_loop_next:
 ld a,(#_Seg_left)
 or a
 jr z,contact_loop_done
 ld hl,#contact_loop_box
 ld b,(hl)
 inc hl
 ld c,(hl)
 call _riding_segment_box_regs
 jr nc,contact_loop_done
 call corner_general_record
 jr contact_loop_next
contact_loop_done:
 ld a,(#contact_loop_found)
 ret
corner_general_record:
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
 ret nc
 jr contact_loop_position
contact_loop_general:
 .ifdef RIDING_NORMAL_ATLAS
 call contact_region_dispatch
 or a
 ret z
 dec a
 .ifdef RIDING_LEAF_REGION
 jr nz,corner_not_known_plane
 ld a,(#_riding_program_mode)
 dec a
 call z,corner_store_plane
 jp contact_loop_interior
corner_not_known_plane:
 .else
 jr z,contact_loop_interior
 .endif
 dec a
 jr nz,contact_loop_position
 ; An endpoint certificate supplies a representative position with the
 ; correct sign. The original endpoint flags and radial solver follow.
 .ifdef RIDING_LEAF_REGION
 ld a,(#_riding_program_mode)
 dec a
 call z,corner_cached_cap
 .endif
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
 ret nc
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
 .ifdef RIDING_LEAF_REGION
 ld a,(#_riding_program_mode)
 dec a
 call z,corner_position
 .endif
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
 ret nz
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
 ret nz
 jr contact_loop_original_endpoint
contact_loop_check_end:
 bit 7,(hl)
 ret nz
contact_loop_original_endpoint:
 bit 7,b
 jr nz,contact_loop_endpoint_ready
 ld a,b
 or a,c
 jr z,contact_loop_endpoint_ready
 ; Keep the vector in registers until a rare atlas miss needs the slow normal.
 call contact_loop_xy
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 .rept 4
 inc hl
 .endm
 ld a,e
 sub (hl)
 inc hl
 ld e,a
 ld a,d
 sbc (hl)
 inc hl
 ld d,a
 ld a,c
 sub (hl)
 inc hl
 ld c,a
 ld a,b
 sbc (hl)
 ld b,a
 jr contact_loop_radial
contact_loop_endpoint_ready:
 call contact_loop_xy
contact_loop_radial:
 .ifndef RIDING_NORMAL_ATLAS
 ld hl,#contact_loop_x
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld (hl),b
 .endif
 .ifdef RIDING_NORMAL_ATLAS
 ; A physical atlas hit is always inside the strict disk. A definite
 ; outside result is final. A miss preserves the full signed input.
 ld hl,#contact_loop_k
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call _riding_normal_ring
 ret c
 or a
 jr nz,contact_loop_accept_radial
 .endif
contact_loop_radial_miss:
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
 ret nc
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
 ret nc
 .ifdef RIDING_NORMAL_ATLAS
 ld hl,#contact_loop_k
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 ld hl,#contact_loop_x
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld (hl),b
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
 ret
contact_loop_normalize:
 push de
 push bc
 call contact_loop_xy
 push bc
 push de
 call _riding_normal_fast
 add sp,#10
 .ifdef RIDING_NORMAL_ATLAS
 jp contact_mark_radial
contact_loop_accept_radial:
 ld b,#1
 jr contact_loop_accept_kind
 .endif
contact_loop_accept:
 .ifdef RIDING_NORMAL_ATLAS
 ld b,#0
contact_loop_accept_kind:
 .endif
 ld a,(#contact_loop_found)
 or a,a
 jr nz,contact_loop_merge
 inc a
 ld (#contact_loop_found),a
 ld hl,#contact_loop_k
 ld (hl),#<(_Ct+10)
 inc hl
 ld (hl),#>(_Ct+10)
 ret
contact_loop_merge:
 .ifdef RIDING_LEAF_REGION
 ld (#_riding_dense_merged),a   ; nonzero first-contact flag
 .endif
 .ifdef RIDING_NORMAL_ATLAS
 call _riding_contact_merge_kind
 .else
 call _riding_contact_merge
 .endif
 or a,a
 ret z
 pop hl                      ; leave the enclosing iterator on an early pair
 ret
 .ifdef RIDING_NORMAL_ATLAS
; Every endpoint which reaches normalize supplied its physical squared length.
; Tag 2 reuses the normalized vector; tag 64 also certifies both contact points.
contact_mark_radial:
 ld hl,#normal_cache_key+6
 ld a,(hl-)
 or a
 jr nz,contact_read_root
 ld a,(hl)
 cp #64
 jr c,contact_exact_vector
contact_read_root:
 ; The strict disk bounds the reciprocal table index to 0..296.
 ld a,(hl+)
 and #254
 ld e,a
 ld d,(hl)
 ld hl,#(_riding_normal_rsqrt-64)
 add hl,de
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ld e,#33
 ld hl,#contact_root_certificate
 call ___sdcc_bcall_ehl
 jr contact_vector_tag
contact_exact_vector:
 ; The deep quotient truncates by less than one Q14 unit on either axis.
 ; Multiplying this error by the radius (<=127) still rounds to the input.
 ld a,#64
contact_vector_tag:
 ld (#normal_cache_valid),a
 jp contact_loop_accept_radial
 .endif
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
; The projection and region certificates share the tail of terrain bank 93.
contact_region_dispatch:
 ld a,#93
 ld (#0x2000),a
 ld (#__current_bank),a
 call contact_region_query
 ld h,a
 ld a,#9
 ld (#0x2000),a
 ld (#__current_bank),a
 ld a,h
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
 ; A nonzero second low byte rules out both unit-axis shortcuts.
 jp nz,_riding_terrain_products
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
; The cached intercept includes the Q14 bias at offset (0,0). Later
; products use the unsigned byte offsets within the same 256u square.
_riding_plane_fill::
 push bc
 push de
 ld a,#6
 ld (#0x2000),a
 ld (#__current_bank),a
 call terrain_plane_setup
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
 add hl,de                    ; biased dot at the origin of the cache square
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
 ; Only biased high words -103..102 can produce an accepted
 ; rounded distance. At -103 the low two bits must be 3. At 102 they
 ; must be 0 or 1. Wider saturated projections also reject here.
 ld a,h
 or a
 jr z,plane_raw_positive
 inc a
 jr nz,plane_raw_out
 ld a,l
 cp #153
 jr c,plane_raw_out
 jr nz,plane_raw_inside
 ld a,d
 cp #192
 jr c,plane_raw_out
 jr plane_raw_inside
plane_raw_positive:
 ld a,l
 cp #102
 jr c,plane_raw_inside
 jr nz,plane_raw_out
 ld a,d
 cp #128
 jr nc,plane_raw_out
plane_raw_inside:
 ld a,d
 rlca
 rlca
 and #3
 add hl,hl
 add hl,hl
 or l
 ld c,a
 ld b,h
 pop hl
 bit 7,b
 jp nz,_riding_plane_negative
 jp _riding_plane_positive
plane_raw_out:
 pop hl
 xor a
 ret

.area _CODE_6
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
 add #32                     ; include the single Q14 rounding bias here
 ld (hl+),a
 ld a,c
 adc #0
 ld (hl+),a
 ld a,b
 adc #0
 ld (hl),a

 ; HL points at the final intercept byte. A signed unit Y plane
 ; can finish the X threshold setup while the same ROM bank is selected.
 inc hl
 ld (hl),#0
 ld de,#-12
 add hl,de                    ; normal at entry+9
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
 ; HL points at the signed major coefficient's high byte.
 ld de,#-12
 add hl,de
 ld d,h
 ld e,l
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
 ld d,a
 ld a,(hl+)
 ld h,(hl)
 ld l,a
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

 .ifdef RIDING_LEAF_REGION
.area _CODE_9
; DE names an accepted box, irrespective of the two radius and tangent
; decisions which follow it. Advance in exactly the native record order.
_riding_leaf_program::
 call contact_loop_init
corner_program_next:
 ld hl,#_Seg_left
 dec (hl)
 ld hl,#_Seg_cur
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 add #18
 dec hl
 ld (hl+),a
 jr nc,corner_program_record
 inc (hl)
corner_program_record:
 call corner_record
 ld a,(#_Seg_left)
 or a
 jr nz,corner_program_next
 jp contact_loop_done
corner_record:
 ld hl,#_riding_record_program
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(hl+)
 push af
 ld a,l
 ld (#_riding_record_program),a
 ld a,h
 ld (#_riding_record_program+1),a
 pop af
 or a
 jp z,corner_general_record
 cp #4
 jp z,corner_plane_dispatch
 dec a
 ret z
 ld b,a
 jp corner_cap_dispatch

.area _CODE_2
corner_cap_query:
 ; Start/end cap: derive the exact center-relative vector. The program
 ; proves tangent and normal guards. The regular strict disk test follows.
 ld h,d
 ld l,e
 ld a,(#_riding_contact_qx)
 sub (hl)
 inc hl
 ld e,a
 ld a,(#_riding_contact_qx+1)
 sbc (hl)
 inc hl
 ld d,a
 ld a,(#_riding_contact_qy)
 sub (hl)
 inc hl
 ld c,a
 ld a,(#_riding_contact_qy+1)
 sbc (hl)
 inc hl
 dec b
 ld b,a
 jr z,corner_cap_vector
 ld a,e
 sub (hl)
 inc hl
 ld e,a
 ld a,d
 sbc (hl)
 inc hl
 ld d,a
 ld a,c
 sub (hl)
 inc hl
 ld c,a
 ld a,b
 sbc (hl)
 ld b,a
corner_cap_vector:
 ret

.area _CODE
corner_cap_dispatch:
 ld a,#2
 ld (#0x2000),a
 call corner_cap_query
 ld a,#9
 ld (#0x2000),a
 jp contact_loop_radial

.area _CODE_9
corner_position:
 ld hl,#corner_position_inner
 jr corner_learn_banked
corner_cached_cap:
 ld hl,#corner_cached_cap_inner
corner_learn_banked:
 ld e,#2
 jp ___sdcc_bcall_ehl

.area _CODE
corner_store_plane:
 ld hl,#_riding_record_program
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 dec hl
 ld (hl),#4
 ret

.area _CODE_9
corner_plane_dispatch:
 ld hl,#contact_loop_seg
 ld (hl),e
 inc hl
 ld (hl),d
 ld e,#2
 ld hl,#corner_plane_query
 call ___sdcc_bcall_ehl
 call contact_loop_in_radius
 ret nc
 jp contact_loop_interior

.area _CODE_2
; Traversing a 16u tile changes a rounded projection by at most
; ceil(15 * (sqrt(2) + 1/16384)) = 22. An interior artificial endpoint
; has no cap. A real cap also needs the perpendicular guard everywhere.
corner_position_inner:
 bit 7,b
 jr z,corner_after_end
 ld a,b
 inc a
 jr nz,corner_start
 ld a,c
 cp #<(-22)
 jr nc,corner_tight_try
corner_start:
 ld a,#2
 jp corner_guard
corner_after_end:
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
 ; BC has the tangent. Distinguish a whole interior from a whole cap.
 ld a,c
 sub e
 ld e,a
 ld a,b
 sbc d
 jr nc,corner_beyond
 inc a
 jr nz,corner_interior_start
 ld a,e
 cp #<(-22)
 jr nc,corner_tight_try
corner_interior_start:
 ld a,b
 or a
 jp nz,corner_store_plane
 ld a,c
 cp #22
 jr c,corner_tight_try
 jp corner_store_plane
corner_beyond:
 or a
 jr nz,corner_beyond_sure
 ld a,e
 cp #23
 jr c,corner_tight_try
corner_beyond_sure:
 ld a,#3
 jr corner_guard
corner_tight_try:
 ld e,#1
 ld hl,#corner_tight
 call ___sdcc_bcall_ehl
 or a
 ret z
 cp #4
 jp z,corner_store_plane
corner_guard:
 push af
 ld hl,#contact_loop_d
 ld a,(hl+)
 add #<387
 ld e,a
 ld a,(hl)
 adc #>387
 cp #>775
 jr c,corner_guard_ok
 jr nz,corner_guard_fail
 ld a,e
 cp #<775
 jr c,corner_guard_ok
corner_guard_fail:
 ; For an axial cap the strict disk itself proves the perpendicular
 ; guard. An end cap additionally needs its vertex on the source line.
 ; Check both packed coefficients, including the signed unit magnitude.
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#8
 add hl,de
 ld a,(hl+)
 or a
 jr nz,corner_guard_no
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 or a
 jr nz,corner_guard_no
 ld a,(hl)
 or a
 jr nz,corner_guard_vertical_cap
 ld a,e
 and #127
 cp #64
 jr nz,corner_guard_no
 ld de,#-5                 ; dy at offset 6
 jr corner_axis_endpoint
corner_guard_vertical_cap:
 and #127
 cp #64
 jr nz,corner_guard_no
 ld a,e
 or a
 jr nz,corner_guard_no
 ld de,#-7                 ; dx at offset 4
corner_axis_endpoint:
 pop af
 cp #2
 jr z,corner_install        ; original start is on its own line
 add hl,de
 ld a,(hl+)
 or (hl)
 ret nz
 ld a,#3
 jr corner_install
corner_guard_no:
 pop af
 ret
corner_guard_ok:
 pop af
corner_install:
 ld e,a
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,#13
 add l
 ld l,a
 jr nc,corner_flags
 inc h
corner_flags:
 ld a,(hl)
 bit 0,e
 jr nz,corner_end_flag
 add a
corner_end_flag:
 rlca
 jr nc,corner_store
 ld e,#1
corner_store:
 ld hl,#_riding_record_program
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 dec hl
 ld (hl),e
 ret

corner_cached_cap_inner:
 ; Kinds 3/4 imply the perpendicular guard over the whole 64u box.
 ; Kinds 5/6 re-evaluated distance for this center at contact_region_distance.
 ld a,(#contact_region_cap_kind)   ; last matched kind minus two
 cp #3
 jr c,corner_cached_proven
 dec a
 jp corner_guard
corner_cached_proven:
 inc a
 jr corner_install

; The source-order plane retains its exact unrounded signed32 numerator.
; Updating by the two integer center differences before a single final
; rounding is algebraically identical to the native pair of products.
.area _DATA
corner_planes: .ds 64       ; 4 entries: record, previous XY bytes, nx,ny, raw
corner_plane_work: .ds 2
corner_plane_dxy: .ds 2
.area _CODE_2
corner_plane_query:
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 push de
 ld hl,#_riding_dense_slot
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,l
 sub #<_riding_leaf_regions
 srl a
 ld c,a
 ld b,#0
 ld de,#27
 add hl,de
 ld a,(hl)
 ld (hl),#1
 ld hl,#corner_planes
 add hl,bc
 push af
 ld a,l
 ld (#corner_plane_work),a
 ld a,h
 ld (#corner_plane_work+1),a
 pop af
 pop de
 or a
 jr z,corner_plane_new
 ld a,(hl+)
 cp e
 jr nz,corner_plane_new
 ld a,(hl+)
 cp d
 jr nz,corner_plane_new
 ld a,(#_riding_contact_qx)
 sub (hl)
 inc hl
 add #4
 cp #9
 jr nc,corner_plane_new
 sub #4
 ld (#corner_plane_dxy),a
 ld a,(#_riding_contact_qy)
 sub (hl)
 inc hl
 add #4
 cp #9
 jr nc,corner_plane_new
 sub #4
 ld (#corner_plane_dxy+1),a
 ; HL names the cached X normal; raw begins four bytes later.
 ld a,(#corner_plane_dxy)
 call corner_plane_add
 ld a,(#corner_plane_dxy+1)
 call corner_plane_add
 jr corner_plane_result
corner_plane_new:
 ; Install the source record and its -ey,ex normal.
 call corner_plane_address
 ld a,e
 ld (hl+),a
 ld (hl),d
 push hl
 ld hl,#8
 add hl,de
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 xor a
 sub (hl)
 inc hl
 ld e,a
 ld a,#0
 sbc (hl)
 ld d,a
 pop hl
 inc hl
 inc hl
 inc hl
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld (hl),b
 push bc
 ld b,d
 ld c,e
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(#_riding_contact_qx)
 sub (hl)
 inc hl
 ld e,a
 ld a,(#_riding_contact_qx+1)
 sbc (hl)
 inc hl
 ld d,a
 push hl
 call _riding_projection_signed16
 pop bc
 push hl
 push de
 ld h,b
 ld l,c
 ld a,(#_riding_contact_qy)
 sub (hl)
 inc hl
 ld e,a
 ld a,(#_riding_contact_qy+1)
 sbc (hl)
 ld d,a
 ldhl sp,#4
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 call _riding_projection_signed16
 pop bc
 ld a,e
 add c
 ld e,a
 ld a,d
 adc b
 ld d,a
 pop bc
 ld a,l
 adc c
 ld l,a
 ld a,h
 adc b
 ld b,a
 ld c,l
 add sp,#2
 call corner_plane_address
 ld a,#8
 add l
 ld l,a
 jr nc,corner_plane_install
 inc h
corner_plane_install:
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld (hl),b
corner_plane_result:
 call corner_plane_address
 inc hl
 inc hl
 ld a,(#_riding_contact_qx)
 ld (hl+),a
 ld a,(#_riding_contact_qy)
 ld (hl+),a
 inc hl
 inc hl
 inc hl
 inc hl
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 jp _riding_terrain_reduce_q14

corner_plane_address:
 ld hl,#corner_plane_work
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ret
corner_plane_add:
 ; A is an exact signed center difference in [-4,4].
 ld c,a
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,c
 or a
 ret z
 bit 7,a
 jr z,corner_plane_positive
 cpl
 inc a
 ld c,a
 xor a
 sub e
 ld e,a
 ld a,#0
 sbc d
 ld d,a
corner_plane_positive:
 push hl
 ld a,d
 add a
 sbc a
 ld b,a
 call corner_plane_address
 ld a,#8
 add l
 ld l,a
 jr nc,corner_plane_delta
 inc h
corner_plane_delta:
 push hl
 ld a,(hl)
 add e
 ld (hl+),a
 ld a,(hl)
 adc d
 ld (hl+),a
 ld a,(hl)
 adc b
 ld (hl+),a
 ld a,(hl)
 adc b
 ld (hl),a
 pop hl
 dec c
 jr nz,corner_plane_delta
 pop hl
 ret
 .endif

.ifdef RIDING_LEAF_REGION
.area _CODE_1
; BC is the sampled tangent. For a given sign pair, the nearest and
; farthest tile corners use complementary X/Y extents. Cauchy bounds
; the change of a rounded projection by ceil(norm(delta)*16385/16384).
corner_tight::
 push bc
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#9
 add hl,de
 ld a,(hl+)                     ; tangent X sign
 add a
 sbc a
 ld e,a
 ld a,(#_riding_contact_qx)
 xor e
 and #15
 swap a
 ld e,a
 inc hl
 ld a,(hl+)                     ; tangent Y sign
 add a
 sbc a
 ld d,a
 ld a,(#_riding_contact_qy)
 xor d
 and #15
 or e
 push hl                        ; length field
 ld l,a
 ld h,#0
 ld de,#corner_max_projection
 add hl,de
 ld a,(hl)
 ld d,a                         ; maximum decrease
 ; The opposite corner has index 255-index. The table may be unaligned.
 ld a,l
 sub #<corner_max_projection
 cpl
 add #<corner_max_projection
 ld l,a
 ld a,#>corner_max_projection
 adc #0
 ld h,a
 ld a,(hl)
 ld e,a                         ; maximum increase
 pop hl
 bit 7,b
 jr z,corner_tight_after
 ; All sampled negative tangents here are close to zero. Even at the
 ; positive corner a strictly negative tangent must choose the start.
 ld a,c
 add e
 ld a,b
 adc #0
 bit 7,a
 jr z,corner_tight_unknown
 ld a,#2
 jr corner_tight_done
corner_tight_after:
 ld a,(hl+)
 ld l,(hl)
 res 7,l
 res 6,l
 ld h,l
 ld l,a                         ; original 14-bit segment length
 ld a,c
 sub d
 ld d,a
 ld a,b
 sbc #0
 jr c,corner_tight_unknown
 cp h
 jr c,corner_tight_max
 jr nz,corner_tight_end
 ld a,d
 cp l
 jr z,corner_tight_max
 jr nc,corner_tight_end
corner_tight_max:
 ld a,c
 add e
 ld e,a
 ld a,b
 adc #0
 cp h
 jr c,corner_tight_interior
 jr nz,corner_tight_unknown
 ld a,e
 cp l
 jr nc,corner_tight_unknown     ; an artificial end rejects exact equality
corner_tight_interior:
 ld a,#4
 jr corner_tight_done
corner_tight_end:
 ld a,#3
 jr corner_tight_done
corner_tight_unknown:
 xor a
corner_tight_done:
 pop bc
 ret
; Each entry is ceil(sqrt(x*x+y*y)*16385/16384), indexed by 16*x+y.
corner_max_projection::
 .db 0,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16
 .db 2,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16
 .db 3,3,3,4,5,6,7,8,9,10,11,12,13,14,15,16
 .db 4,4,4,5,6,6,7,8,9,10,11,12,13,14,15,16
 .db 5,5,5,6,6,7,8,9,9,10,11,12,13,14,15,16
 .db 6,6,6,6,7,8,8,9,10,11,12,13,14,14,15,16
 .db 7,7,7,7,8,8,9,10,11,11,12,13,14,15,16,17
 .db 8,8,8,8,9,9,10,10,11,12,13,14,14,15,16,17
 .db 9,9,9,9,9,10,11,11,12,13,13,14,15,16,17,18
 .db 10,10,10,10,10,11,11,12,13,13,14,15,16,16,17,18
 .db 11,11,11,11,11,12,12,13,13,14,15,15,16,17,18,19
 .db 12,12,12,12,12,13,13,14,14,15,15,16,17,18,18,19
 .db 13,13,13,13,13,14,14,14,15,16,16,17,17,18,19,20
 .db 14,14,14,14,14,14,15,15,16,16,17,18,18,19,20,20
 .db 15,15,15,15,15,15,16,16,17,17,18,18,19,20,20,21
 .db 16,16,16,16,16,16,17,17,18,18,19,19,20,20,21,22
.endif
