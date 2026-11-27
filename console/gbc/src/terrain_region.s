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

contact_region_query::
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
 call terrain_record_dot
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
