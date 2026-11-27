; Bank 9. The two ordered cap operations refer to the same original vertex.
; dense_vertex holds the two matching 16-bit coordinates established by the
; ordered leaf program. Both radial vectors therefore have the same input.
.area _CODE_9
_riding_shared_cap::
 ld hl,#_riding_dense_vertex
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
 ld b,a
 call _riding_normal_merge_ring
 jr c,corner_pair_empty
 or a
 jr nz,corner_pair_copy
 ; Use the ordinary strict-disk guard and exact square-root solver once for
 ; both caps. Initialization only changes HL and A, preserving the vector.
 call contact_loop_init
 call contact_loop_radial_miss
 ld a,(#contact_loop_found)
 or a
 ret z
corner_pair_copy:
 ld hl,#_Ct
 ld de,#(_Ct+10)
 ld b,#6
corner_pair_copy_next:
 ld a,(hl+)
 ld (de),a
 inc de
 dec b
 jr nz,corner_pair_copy_next
 ld a,#1
 ld (#_riding_dense_merged),a
 ; Both six-byte results are identical. The ring helper checks whether its
 ; last atlas entry can reconstruct the rounded point, performing the second
 ; normalization when rounding changed the offset. Arithmetic misses have
 ; an invalid ring tag and follow the ordinary exact merge.
 call _riding_contact_merge_equal_known
 ld a,#1
 ret
corner_pair_empty:
 xor a
 ret
