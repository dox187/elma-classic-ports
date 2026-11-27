; Load the ordinary corner dispatch first, retaining its sparse lookup.
 ld hl,#_riding_corner_select
 ld e,#32
 call ___sdcc_bcall_ehl
 ld a,(#_physics_level_index)
 cp #45
 ret nz
 ld hl,#_riding_sparse_bind
 ld (hl),#0xc9
 inc hl
 ld d,h
 ld e,l
 ld hl,#bowling_stub
 ld b,#bowling_stub_end-bowling_stub
bowling_copy:
 ld a,(hl+)
 ld (de),a
 inc de
 dec b
 jr nz,bowling_copy
 ld hl,#_riding_sparse_bind+1
 ld a,l
 ld (#step_solve_wheels+4),a
 ld (#step_solve_wheels+10),a
 ld a,h
 ld (#step_solve_wheels+5),a
 ld (#step_solve_wheels+11),a
 ret
; The bridge enters in bank 9. The copied stub bypasses the quarter-square
; binder while preserving its separate sparse terrain reader and both ABI pointers.
bowling_stub:
 push hl
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 ld hl,#6
 add hl,bc
 ld a,(hl)
 add #2
 cp #6
 jr nc,bowling_unmapped
 push bc
 ld e,#86
 ld hl,#_bowling_flat
 call ___sdcc_bcall_ehl
 cp #255
 jp nz,_riding_patch_have_answer
 pop bc
bowling_unmapped:
 ld hl,#6
 add hl,bc
 ld a,(#_patch_sparse_y0)
 cp (hl)
 pop hl
 jp z,_riding_sparse_wheel_inputs
 jp _riding_wheel_inputs
bowling_stub_end:
bowling_stub_bytes == bowling_stub_end-bowling_stub
_bowling_flat::
 ld h,b
 ld l,c
 inc hl
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld a,(hl+)
 cp #2                     ; X in [131072,196607] solver units
 jr nz,bowling_miss
 inc hl
 ld a,(hl+)
 ld c,a
 ld a,(hl)
 cp #3
 jp nz,bowling_slope
 inc hl
 ld a,(hl)
 dec a
 jr nz,bowling_miss
 ld a,c
 sub #192
 jr c,bowling_miss
 ld c,a
 ; FLAT_Y through FLAT_Y+63. Each entry contains a lower inclusive and
 ; upper exclusive X followed by its initial distance code.
 ld hl,#bowling_ranges
bowling_range:
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 cp d
 jr c,bowling_upper
 jr nz,bowling_miss
 ld a,e
 cp b
 jr c,bowling_miss
bowling_upper:
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 cp d
 jr c,bowling_next
 jr nz,bowling_found
 ld a,e
 cp b
 jr c,bowling_found
bowling_next:
 inc hl
 ld a,(hl)
 inc hl
 or (hl)
 dec hl
 jr nz,bowling_range
bowling_miss:
 ld a,#255
 ret
bowling_found:
 ld a,(hl)
 or a
 ret z
 add c
 ld c,a
 cp #154                   ; 410 - 256
 jr nc,bowling_empty
 ld hl,#_Ct
 ld (hl),#50
 inc hl
 xor a
 ld (hl+),a
 ld (hl+),a
 ld (hl),#64
 inc hl
 ld (hl),c
 inc hl
 ld (hl),#1
 ld a,#1
 ret
bowling_empty:
 xor a
 ret
; DE = low sixteen X, HL points at the middle byte of Y, C = low Y.
; The low and high side of 65536 use different upper bytes of Q18.
bowling_slope:
 ld a,d
 sub #0x9f
 cp #2
 jp nc,bowling_miss
 ld a,(hl+)
 ld b,a
 inc a
 jr z,bowling_slope_low
 inc a
 jr z,bowling_diagonal
 ; Y is at or above 65536 only in page 0x100.
 ld a,b
 or a
 jp nz,bowling_miss
 ld a,(hl)
 dec a
 jp nz,bowling_miss
 jr bowling_plane
bowling_slope_low:
 ld a,(hl)
 or a
 jp nz,bowling_miss
 ld a,c
 cp #0x40
 jr nc,bowling_plane
 ; The narrower range approaches the lower end of this slope.
 ld a,d
 cp #0x9f
 jp nz,bowling_miss
 ld a,e
 cp #0xd0
 jp nc,bowling_miss
 jr bowling_plane
; In the last 96 X columns the second edge rules out part of the lower
; square. Admit only Y-X >= -106691, verified with both ordered records.
bowling_diagonal:
 ld a,(hl)
 or a
 jp nz,bowling_miss
 ld a,d
 cp #0x9f
 jp nz,bowling_miss
 ld a,e
 sub #112
 cp #96
 jp nc,bowling_miss
 ld a,c
 sub e
 jp c,bowling_miss
 cp #61
 jp c,bowling_miss
bowling_plane:
 ld a,e
 sub #<172885
 ld e,a
 ld a,d
 sbc #>172885
 ld d,a
 ld a,c
 sub #<65934
 ld c,a
 ld a,b
 sbc #>65934
 ld b,a
 ld hl,#-9217
 push hl
 ld hl,#13546
 push hl
 call _dotq14
 xor a
 sub c
 ld c,a
 ld a,#0
 sbc b
 cp #2
 jr nc,bowling_empty
 or a
 jr z,bowling_distance
 ld a,c
 cp #154
 jr nc,bowling_empty
 ld a,#1
bowling_distance:
 ld hl,#_Ct
 ld (hl),#<(-13546)
 inc hl
 ld (hl),#>(-13546)
 inc hl
 ld (hl),#<9217
 inc hl
 ld (hl),#>9217
 inc hl
 ld (hl),c
 inc hl
 ld (hl),a
 ld a,#1
 ret
