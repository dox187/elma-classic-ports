; Exact terrain-endpoint annulus. Both physical callers are near in bank 9.
; The arbitrary-d2 ABI keeps the original path and invalidates the physical
; cache tag on replacement. An atlas hit installs the full original key.
.area _DATA
normal_octant: .ds 1
normal_entry: .ds 8

.area _CODE_9
_riding_normal_merge_ring::
 ld hl,#_Ct
_riding_normal_ring::
 ; DE = signed x, BC = signed y, HL = destination. A = 1 on hit.
 push hl
 ld a,(#normal_cache_valid)
 cp #2
 jr nz,ring_lookup
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
 ld a,#0
 rla
 add a,a
 add a,a
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
 cp c                          ; both rows end at or below this value
 jr c,ring_outside
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
 pop bc
 pop de
 ld hl,#normal_cache_key
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ld (hl),c
 inc hl
 ld (hl),b
 inc hl
 ld a,(#normal_entry+6)
 ld (hl+),a
 ld a,(#normal_entry+7)
 ld (hl+),a
 ld (hl),#2
 inc hl
 ld (hl),#0
 ld hl,#normal_entry
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(#normal_octant)
 ld h,a
 ld a,(#normal_entry+5)
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
 ld a,(#normal_entry+4)
 adc a,#0
 ld (#normal_cache_value+4),a
 ld a,#1
 ld (#normal_cache_value+5),a
 bit 2,h
 jr z,ring_axes
 push bc
 ld b,d
 ld c,e
 pop de
ring_axes:
 ld hl,#normal_cache_value
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ld (hl),c
 inc hl
 ld (hl),b
 inc a                     ; tag 2 certifies d2 = x*x + y*y
 ld (#normal_cache_valid),a
ring_copy:
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
 ld de,#normal_entry
 .rept 8
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 ld c,#1
 jr ring_restore
ring_above:
 ld c,#2
 jr ring_restore
ring_unmapped:
 ld c,#0
ring_restore:
 xor a
 ld (#0x3000),a
 ld a,#9
 ld (#0x2000),a
 ld a,c
 cp #2
 ccf
 ret
