; Ordinary terrain-record region cache and exact rounded Q14 projections.
; Linked after bank 93's packed terrain and brake tables.
.module terrain_region
.area _CODE_93
; ceil(63 * (sqrt(2) * 16384 + 1) / 16384) for rounded unit tangents.
CONTACT_REGION_DELTA = 90

; Each coordinate is an unsigned low byte plus 256 times a signed high byte.
; Combine all partial products before the single rounding and saturation.
terrain_record_dot::
 ldhl sp,#4
 ld a,(hl)
 or a
 jp z,_riding_terrain_dotq14    ; includes the near-axis shortcut
 ld a,b
 add #4
 cp #9
 jp nc,_riding_terrain_dotq14
 ld a,d
 add #4
 cp #9
 jp nc,_riding_terrain_dotq14

 push bc
 push de
 ld b,c
 ld c,e
 ldhl sp,#6
 call _riding_fraction_pair     ; BC:D = low-byte numerator shifted right eight
 ldhl sp,#1                   ; signed high digit of DE
 ld a,(hl)
 ldhl sp,#6
 call terrain_small_digit
 ldhl sp,#3                   ; signed high digit of BC
 ld a,(hl)
 ldhl sp,#8
 call terrain_small_digit
 ld h,b
 ld l,c
 call _riding_terrain_reduce_q14
 add sp,#4
 pop hl
 add sp,#4
 jp (hl)
; Add the signed high digit A times signed16 (HL) to B:C:D. The caller
; has bounded A to -4..4, so shift-and-add uses at most two additions.
terrain_small_digit:
 or a
 ret z
 ld e,(hl)
 inc hl
 ld h,(hl)
 ld l,#0
 bit 7,h
 jr z,terrain_small_magnitude
 dec l
terrain_small_magnitude:
 bit 0,a
 jr z,terrain_small_shift
 cp #3
 jr z,terrain_small_plus3
 cp #253
 jr nz,terrain_small_sign
 call terrain_small_sub
 ld a,#254
 jr terrain_small_shift
terrain_small_plus3:
 call terrain_small_plus
 ld a,#2
terrain_small_shift:
 ; A is now +/-2 or +/-4. Bit 1 distinguishes them for either sign.
 sla e
 rl h
 rl l
 bit 1,a
 jr nz,terrain_small_sign
 sla e
 rl h
 rl l
terrain_small_sign:
 bit 7,a
 jr nz,terrain_small_sub
terrain_small_plus:
 ld a,d
 add e
 ld d,a
 ld a,c
 adc h
 ld c,a
 ld a,b
 adc l
 ld b,a
 ret
terrain_small_sub:
 ld a,d
 sub e
 ld d,a
 ld a,c
 sbc h
 ld c,a
 ld a,b
 sbc l
 ld b,a
 ret

; Selection leaves the record pointer in DE on both cache hits and misses.
.macro contact_region_read_coeffs
 ld hl,#8
 add hl,de
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
.endm
contact_region_query::
 ld a,(#_riding_contact_regions_dirty)
 or a
 jr z,contact_region_select
 xor a
 ld (#_riding_contact_regions_dirty),a
 ; Only the kind byte of each eight-byte entry needs invalidation.
 .irp offset,0,8,16,24,32,40,48,56,64,72,80,88,96,104,112,120
 ld (#contact_regions+offset),a
 .endm
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
 ; The spatial program only needs the cap kind on this path.
 ld (#contact_region_cap_kind),a
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
 ; Retain the source tangent coefficients for the second exact projection.
 ; Rejections discard this pair. An accepted distance uses it directly.
 contact_region_read_coeffs
 push de
 push bc
 call contact_region_distance_coeffs
 jr c,contact_region_inside
 add sp,#4
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
 call terrain_record_dot
 push bc
 ld a,b
 bit 7,a
 jr z,contact_region_nonnegative
 cp #255
 jr nz,contact_region_start
 ld a,c
 cp #<(-CONTACT_REGION_DELTA)
 jp nc,contact_region_boundary
contact_region_start:
 ; Across this square a rounded tangent changes by at most 90. Keeping
 ; at least 64 tangent units from the cap bounds its true normal below
 ; sqrt(410^2-63^2) < 406 everywhere inside the strict endpoint disk.
 ; Everything in this region projects beyond the start. A synthetic
 ; start cannot produce a cap contact at any center in the square.
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#13
 add hl,de
 bit 6,(hl)
 jr nz,contact_region_empty_cap
 ld a,b
 inc a
 jr nz,contact_region_start_proven
 ld a,c
 cp #<(-64-CONTACT_REGION_DELTA)
 jr nc,contact_region_start_guard
contact_region_start_proven:
 ld a,#3
 jr contact_region_install
contact_region_empty_cap:
 pop bc
 jp contact_region_set_reject
contact_region_start_guard:
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
 ld e,(hl)                    ; keep endpoint flags for an exterior region
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
 bit 7,e
 jr nz,contact_region_empty_cap
 ; An 8 m segment's rounded Q14 direction changes either endpoint
 ; projection by less than one unit. Allow two extra tangent units for
 ; its rounded length and projection; the normal still rounds below 410.
 ld a,h
 or a
 jr nz,contact_region_end_proven
 ld a,l
 cp #(67+CONTACT_REGION_DELTA)
 jr c,contact_region_end_guard
contact_region_end_proven:
 ld a,#4
 jr contact_region_install
contact_region_end_guard:
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
 ld c,a
 ld a,(#contact_loop_seg)
 ld b,a
 and #30
 add a
 add a
 ld e,a
 ld d,#0
 ld hl,#contact_regions
 add hl,de
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld a,(#contact_loop_seg+1)
 ld (hl+),a
 ld a,(#contact_loop_box)
 ld (hl+),a
 ld a,(#contact_loop_box+1)
 ld (hl),a
 ret
contact_region_distance:
 contact_region_read_coeffs
contact_region_distance_coeffs:
 push de
 xor a
 sub c
 ld c,a
 sbc a
 sub b
 ld b,a
 push bc
 ld hl,#contact_loop_x
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 call terrain_record_dot
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

.area _CODE_33
; For n=floor(x*R/16), the error projecting L*n/16384 back to x is
; <= (|x|*|L*R-262144|+16*L)/262144. The table keeps this below 1/2.
; To bound |x|, recall that L is the rounded dot of the vector and its
; normal. Thus R*(x*x+y*y) < 262144*(L+1): both floor errors together
; change its numerator by at most 16*(409+409), below half a unit.
; Every accepted R*L >= 262144-1024. Hence x*x+y*y < 256*L*(L+1)/255
; < (L+2)^2 throughout the table. The same bound applies to either axis.
contact_root_certificate::
 ld hl,#(normal_cache_value+4)
 ld a,(hl+)
 sub #126
 ld e,a
 ld a,(hl)
 sbc #0
 ld d,a
 ld a,e
 sub #<(411-126)
 ld a,d
 sbc #>(411-126)
 jr nc,contact_root_uncertain
 ld h,d
 ld l,e
 add hl,hl
 ld de,#contact_root_limits
 add hl,de
 ld a,(hl+)
 ld e,a
 ld a,(hl)
 and #15
 ld d,a
 ld a,c
 sub e
 ld e,a
 ld a,b
 sbc d
 jr nz,contact_root_uncertain
 ld a,(hl)
 swap a
 and #15
 cp e
 jr c,contact_root_uncertain
 ld a,#64
 ret
contact_root_uncertain:
 ld a,#2
 ret

contact_root_limits:
contact_length = 126
 .rept 411-126
contact_error = (131071-16*contact_length)/(contact_length+2)
 ; A four-bit width covers every admitted reciprocal at this tolerance.
 .ifgt (contact_error-940)
contact_error = 940
 .endif
contact_min = (262144-contact_error+contact_length-1)/contact_length
contact_max = (262144+contact_error)/contact_length
 .db <contact_min, (>contact_min) + 16*(contact_max-contact_min)
contact_length = contact_length+1
 .endm

.area _CODE_93
; Each operand stores the raw distance at (xbase+255, ybase). The
; complementary X and forward Y offsets multiply the packed ey and ex
; directly, retaining every product bit until the single Q14 reduction.
candidate_static_distance::
 ld a,c
 sub #3
 ld l,a
 ld h,#0
 ld e,l
 ld d,h
 add hl,hl
 add hl,hl
 add hl,de
 ld de,#_riding_candidate_intercepts
 add hl,de
 ld a,(hl+)
 ld c,a
 and #0xf0
 ld b,a
 ld a,(#_riding_contact_qx)
 sub b
 cpl
 ld b,a
 swap c
 ld a,c
 and #0xf0
 ld c,a
 ld a,(#_riding_contact_qy)
 sub c
 ld c,a
 push hl
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#8
 add hl,de
 call _riding_fraction_pair
 pop hl
 ld a,(hl+)
 add e
 ld a,(hl+)
 adc d
 ld d,a
 ld a,(hl+)
 adc c
 ld c,a
 ld a,(hl)
 adc b
 ld h,a
 ld l,c
 jp _riding_terrain_reduce_q14
