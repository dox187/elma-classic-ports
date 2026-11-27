; Bank 9. The two ordered cap operations refer to the same original vertex.
; dense_vertex holds the two matching 16-bit coordinates established by the
; ordered leaf program. Both radial vectors therefore have the same input.
.area _CODE_9
_riding_shared_cap::
 ld hl,#_riding_dense_vertex
corner_shared_vertex:
 ld b,#0
 jp corner_vertex_offset
corner_shared_radial:
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
 .rept 6
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
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
