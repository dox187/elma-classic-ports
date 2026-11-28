; Exact terrain-endpoint annulus. Both physical callers are near in bank 9.
; The arbitrary-d2 ABI keeps the original path and invalidates the physical
; cache tag on replacement. An atlas hit installs the full original key.
.area _DATA
normal_octant: .ds 1
normal_shape_length: .ds 1
normal_shape_flags: .ds 1

.area _CODE_9
_riding_normal_merge_ring::
 ld hl,#_Ct
_riding_normal_ring::
 ; DE = signed x, BC = signed y, HL = destination. A = 1 on hit.
 push hl
 ld a,(#normal_cache_valid)
 cp #2
 jr c,ring_lookup
 ld hl,#normal_cache_key
 ld a,(hl+)
 cp e
 jr nz,ring_lookup
 ld a,(hl+)
 cp d
 jr nz,ring_lookup
 ld a,(hl+)
 cp c
 jr nz,ring_lookup
 ld a,(hl)
 cp b
 jp z,ring_copy
ring_lookup:
 push de
 push bc
 ld h,#0
 bit 7,d
 jr z,ring_x_unsigned
 set 0,h
 xor a
 sub e
 ld e,a
 sbc a,a
 sub d
 ld d,a
ring_x_unsigned:
 bit 7,b
 jr z,ring_y_unsigned
 set 1,h
 xor a
 sub c
 ld c,a
 sbc a,a
 sub b
 ld b,a
ring_y_unsigned:
 ; All shipped rows have 256 <= larger component <= 409. Check the
 ; high bytes before using their low bytes as unsigned directory indices.
 ld a,d
 or b
 cp #1
 jp nz,ring_miss
 ld a,c
 sub e
 ld a,b
 sbc d
 jr nc,ring_sorted
 push bc
 ld b,d
 ld c,e
 pop de
 ; Exchange the canonical signs and retain the axis permutation.
 ld a,h
 and #1
 add a,a
 bit 1,h
 jr z,ring_swap_signs
 inc a
ring_swap_signs:
 or #4
 ld h,a
ring_sorted:
 ld a,h
 ld (#normal_octant),a
 srl d
 rr e
 sbc a,a
 and #4
 ld d,a                     ; 4 * (smaller component & 1)
 ld a,e
 cp #145
 jr nc,ring_outside
 ld l,e
 ld h,#0
 add hl,hl
 add hl,hl
ring_descriptor:
 ld a,l
 add #<_riding_normal_groups
 ld l,a
 ld a,h
 adc #>_riding_normal_groups
 ld h,a
 ld a,(hl+)
 sub c                         ; both rows end at or below this value
 jr c,ring_outside
 cp #normal_ring_miss_span
 jr nc,ring_miss
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld l,(hl)
 or a
 jr z,ring_miss
 ld h,a
 ld a,l
 ld l,e
 ld e,c                     ; larger component minus 256
 ld c,d
 call _riding_normal_ring_read
 jr c,ring_outside
 or a
 jr nz,ring_install
ring_miss:
 pop bc
 pop de
 pop hl
 xor a
 ret

; Outside the strict 410-unit circle. The merge caller still sees a miss.
ring_outside:
 pop bc
 pop de
 pop hl
 xor a
 scf
 ret

ring_install:
 ; BCDE already hold the four canonical normal bytes. Copy the original
 ; arguments from the stack to the cache without disturbing the normal.
 ldhl sp,#0
 .irp offset,2,3,0,1
 ld a,(hl+)
 ld (#normal_cache_key+offset),a
 .endm
 add sp,#4
 ld hl,#normal_cache_key+6
 ld (hl),#2
 inc hl
 ld (hl),#0
 ld a,(#normal_octant)
 ld h,a
 ld a,(#normal_shape_flags)
 ld l,a
 ; A negative nonintegral Q4 product is bitwise complement of the
 ; positive floor. Exact multiples of 16 take one further increment.
 bit 0,h
 jr z,ring_small_signed
 ld a,e
 cpl
 ld e,a
 ld a,d
 cpl
 ld d,a
 bit 4,l
 jr z,ring_small_signed
 inc de
ring_small_signed:
 bit 1,h
 jr z,ring_large_signed
 ld a,c
 cpl
 ld c,a
 ld a,b
 cpl
 ld b,a
 bit 5,l
 jr z,ring_large_signed
 inc bc
ring_large_signed:
 ld a,l
 bit 0,h
 jr z,ring_lengths
 rrca
ring_lengths:
 bit 1,h
 jr z,ring_length_selected
 rrca
 rrca
ring_length_selected:
 rrca
 ld a,(#normal_shape_length)
 res 6,a
 adc a,#0
 ld (#normal_cache_value+4),a
 ld a,#1
 ld (#normal_cache_value+5),a
 ; The low octant bits select axis order and signs. A physical tag is
 ; at least eight; arbitrary-d2 cache entries retain tag one.
 ld a,l
 and #0xc0
 or h
 or #8
 ld (#normal_cache_valid),a
 bit 2,h
 jr z,ring_axes
 push bc
 ld b,d
 ld c,e
 pop de
ring_axes:
 pop hl
 ; The atlas reader restored bank 9 before returning its four digits.
ring_write_contact:
 .macro ring_write_digit digit,offset
 ld a,digit
 ld (#normal_cache_value+offset),a
 ld (hl+),a
 .endm
 ring_write_digit e,0
 ring_write_digit d,1
 ring_write_digit c,2
 ring_write_digit b,3
 ld a,(#normal_cache_value+4)
 ld (hl+),a
 ld (hl),#1
 ld c,#0                     ; the previous physical cache key was replaced
 ld a,#1
 or a
 ret
.area _CODE_9
ring_copy:
 ld c,#1                     ; the physical input and the cached normal survived
 pop de
 jp normal_cache_copy

.area _CODE
; All groups occupy banks 256..507. Game VBlank handlers stay in ROM0
; and preserve AF, BC, DE, HL and the hardware MBC5 bank registers.
; A = low bank byte, HL = group, C = row header offset, E = large - 256.
_riding_normal_ring_read::
 ld (#0x2000),a
 ld a,#1
 ld (#0x3000),a
_riding_normal_ring_mapped::
 ld b,#0
 add hl,bc
 ld a,e
 sub (hl)
 jr c,ring_unmapped
 inc hl
 cp (hl)
 jr nc,ring_above
 inc hl
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld l,a
 ld h,#0
 add hl,hl
 add hl,hl
 add hl,hl
 add hl,de
 ; Read the raw normal into registers. Length and sign metadata are
 ; used after unmapping, while the squared length belongs in the cache key.
 .irp digit,e,d,c,b
 ld a,(hl+)
 ld digit,a
 .endm
 .irp addr,normal_shape_length,normal_shape_flags,normal_cache_key+4,normal_cache_key+5
 ld a,(hl+)
 ld (#addr),a
 .endm
 ld a,#1
 or a
 jr ring_restore
ring_above:
 xor a
 scf
 jr ring_restore
ring_unmapped:
 xor a
ring_restore:
 push af
 xor a
 ld (#0x3000),a
 ld a,#9
 ld (#0x2000),a
 pop af
 ret

; DE points to a candidate's three normalized words. Compare all six bytes:
; a later merge, push or cache replacement may have changed any of them.
; Return A=1 for the original vector, 2 for a one-unit adjustment, 0 on miss.
; DE and BC are the exact rounded projections on success.
; Both cache consumers and the radial normalizer execute in contact bank 9.
.area _CODE_9
ring_cached_vector:
 ld a,(#normal_cache_valid)
 and #0xc0
 ret z
 ld hl,#normal_cache_value
 ld b,#6
ring_vector_compare:
 ld a,(de)
 cp (hl)
 jr nz,ring_vector_miss
 inc de
 inc hl
 dec b
 jr nz,ring_vector_compare
 jr ring_read_vector
ring_known_vector:
 ld a,(#normal_cache_valid)
 and #0xc0
 ret z
ring_read_vector:
 ld hl,#normal_cache_key
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ld a,(#normal_cache_valid)
 bit 7,a
 jp nz,ring_vector_adjust
 ld a,#1
 ret
.area _CODE
ring_vector_adjust:
 ld h,a
 ld a,(#normal_shape_length)
 bit 6,a
 jr z,ring_major_only
 ; The normalized vector shifts one unit along each canonical axis.
 ld a,h
 rlca
 rlca
 xor h
 bit 0,a                        ; grow XOR sign of the smaller coordinate
 jr nz,ring_grow_small
 bit 2,h
 jr z,ring_shrink_x
 dec bc
 jr ring_major_only
ring_shrink_x:
 dec de
 jr ring_major_only
ring_grow_small:
 bit 2,h
 jr z,ring_grow_x
 inc bc
 jr ring_major_only
ring_grow_x:
 inc de
ring_major_only:
 ld a,h
 rlca
 rlca
 rlca
 xor h
 bit 1,a                         ; grow XOR negative
 jr nz,ring_vector_increase
 bit 2,h
 jr z,ring_vector_decrease_y
 dec de
 jr ring_vector_changed
ring_vector_decrease_y:
 dec bc
 jr ring_vector_changed
ring_vector_increase:
 bit 2,h
 jr z,ring_vector_increase_y
 inc de
 jr ring_vector_changed
ring_vector_increase_y:
 inc bc
ring_vector_changed:
 ld a,#2
 ret
.area _CODE_9
ring_vector_miss:
 xor a
 ret

_riding_ring_equal_known::
 ; The unchanged certificate means both rounded endpoints are q - raw.
 ; Stream the signed little-endian offsets; each axis starts its own borrow.
 ld a,(#normal_cache_valid)
 bit 7,a
 jr nz,ring_equal_adjusted
 and #0x40
 ret z
 ld hl,#normal_cache_key
 .macro ring_equal_axis query,point
 ld a,(#query)
 sub (hl)
 inc hl
 ld (#_Ct+point),a
 ld (#_Ct+10+point),a
 ld a,(#query+1)
 sbc (hl)
 inc hl
 ld (#_Ct+point+1),a
 ld (#_Ct+10+point+1),a
 .endm
 ring_equal_axis _riding_contact_qx,6
 ring_equal_axis _riding_contact_qy,8
 ld a,#2
 ret
ring_equal_adjusted:
 call ring_read_vector
 jr ring_equal_result
_riding_ring_equal_points::
 ld de,#_Ct
 call ring_cached_vector
ring_equal_result:
 or a
 ret z
 push af
 ld hl,#_riding_contact_qx
 .irp digit,0,1
 ld a,(hl+)
 .if digit
 sbc d
 .else
 sub e
 .endif
 ld (#_Ct+6+digit),a
 ld (#_Ct+16+digit),a
 .endm
 ld hl,#_riding_contact_qy
 .irp digit,0,1
 ld a,(hl+)
 .if digit
 sbc b
 .else
 sub c
 .endif
 ld (#_Ct+8+digit),a
 ld (#_Ct+18+digit),a
 .endm
 pop af
 dec a
 jp nz,_riding_normal_merge_ring    ; returns 1 on renormalization, 0 on miss
 ld a,#2                          ; the original normal and its point both survived
 ret

_riding_ring_point_known::
 push de
 call ring_known_vector
 jr ring_project_vector
_riding_ring_cached_point::
 push de
 call ring_cached_vector
ring_project_vector:
 pop hl
 or a
 ret z
 .rept 6
 inc hl
 .endm
 ld a,(#_riding_contact_qx)
 sub e
 ld (hl+),a
 ld a,(#_riding_contact_qx+1)
 sbc d
 ld (hl+),a
 ld a,(#_riding_contact_qy)
 sub c
 ld (hl+),a
 ld a,(#_riding_contact_qy+1)
 sbc b
 ld (hl),a
 ld a,#1
 ret
