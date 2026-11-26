; The caller has exhausted the existing clear rectangle and quarter map.
; Accept a sweep when both endpoints' vertical bounds are clear across
; every intersected quarter-metre X strip. The full 32-bit inputs and
; original terrain remain available to the continuous fallback.
.module head_lane_filter
.area _CODE_4
_head_strip_filtered::
 ld e,#13
 ld hl,#lane_check
 call ___sdcc_bcall_ehl
 or a
 jp z,_riding_swept_head_uncached
 xor a
 ret
.area _INITIALIZER
 .db 0
.area _INITIALIZED
lane_level: .ds 1
.area _DATA
lane_xorigin: .ds 2
lane_yorigin: .ds 2
lane_last: .ds 1
lane_end_y: .ds 1
lane_span: .ds 1
lane_result: .ds 4
.area _CODE_13
_riding_head_lane_bank13::
lane_no:
 xor a
 ret
lane_check:
 ld a,(#_physics_level_index)
 cp #54
 jr nc,lane_no
 inc a
 ld hl,#lane_level
 cp (hl)
 jr z,lane_same_level
 ld (hl),a
 dec a
 ld l,a
 ld h,#0
 add hl,hl
 add hl,hl
 ld de,#strip_origins
 add hl,de
 ld de,#lane_xorigin
 .rept 4
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 ld a,#255
 ld (#lane_last),a
lane_same_level:
 ldhl sp,#13
 call lane_x
 jr nc,lane_no
 ld b,a
 ldhl sp,#21
 call lane_x
 jr nc,lane_no
 sub b
 jr z,lane_span_set
 cp #1
 jr z,lane_span_set
 inc a
 jr nz,lane_no
 dec b
 inc a
lane_span_set:
 ld (#lane_span),a
 ld a,(#lane_last)
 cp b
 jr z,lane_bounds
 ld a,b
 ld (#lane_last),a
 ; 112 bytes per level = 128 * level - 16 * level.
 ld a,(#_physics_level_index)
 ld l,a
 ld h,#0
 .rept 4
 add hl,hl
 .endm
 ld d,h
 ld e,l
 .rept 3
 add hl,hl
 .endm
 ld a,l
 sub e
 ld l,a
 ld a,h
 sbc d
 ld h,a
 ld c,b
 ld b,#0
 add hl,bc
 add hl,bc
 ld de,#0x6400
 add hl,de
 ; Copy the next strip as well. Adjacent sweeps use their intersection.
 ld de,#4
 push de
 ld de,#lane_result
 push de
 push hl
 ld de,#469
 push de
 call _world_far_copy
 add sp,#8
lane_bounds:
 ldhl sp,#16
 call lane_y
 jp nc,lane_no
 ld b,a
 ldhl sp,#24
 call lane_y
 jp nc,lane_no
 ld (#lane_end_y),a
 cp b
 jr c,lane_sorted
 ld c,a
 ld a,b
 ld b,c
lane_sorted:
 ; A/B are the inclusive min/max y bin across the swept rectangle.
 ld c,a
 ld hl,#lane_result
 cp (hl)
 jp c,lane_no
 inc hl
 ld a,(hl+)
 cp b
 jp c,lane_no
 ld a,(#lane_span)
 or a
 jr z,lane_clear
 ld a,c
 cp (hl)
 jp c,lane_no
 inc hl
 ld a,(hl)
 cp b
 jp c,lane_no
lane_clear:
 ; Reuse a complete quarter on the next substep only when its eight
 ; vertical bins are certified by the same lane bounds.
 ld a,(#lane_end_y)
 and #0xf8
 ld c,a
 or #7
 ld b,a
 ld hl,#lane_result
 ld a,c
 cp (hl)
 jr c,lane_done
 inc hl
 ld a,(hl+)
 cp b
 jr c,lane_done
 ld a,(#lane_span)
 or a
 jr z,lane_remember
 ld a,c
 cp (hl)
 jr c,lane_done
 inc hl
 ld a,(hl)
 cp b
 jr c,lane_done
lane_remember:
 ldhl sp,#21
 ld de,#_riding_head_clear_x
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl+)
 ld (de),a
 inc hl
 inc hl
 ld de,#_riding_head_clear_y
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl)
 ld (de),a
 ld a,#255
 ld (#_riding_head_clear_mask),a
lane_done:
 ld a,#1
 ret
; X is the whole unsigned quarter index. Reject out-of-range high bytes.
lane_x:
 ld a,(#lane_xorigin)
 ld e,a
 ld a,(hl+)
 sub e
 ld e,a
 ld a,(#lane_xorigin+1)
 ld d,a
 ld a,(hl+)
 sbc d
 or (hl)
 jr nz,lane_invalid
 ld a,e
 cp #56
 ret
lane_invalid:
 or a
 ret
; Y origin is quarter-aligned. The high three bits of the lowest
; coordinate byte distinguish the eight 32-unit vertical bins.
lane_y:
 ld a,(hl+)
 rlca
 rlca
 rlca
 and #7
 ld c,a
 ld a,(#lane_yorigin)
 ld e,a
 ld a,(hl+)
 sub e
 ld e,a
 ld a,(#lane_yorigin+1)
 ld d,a
 ld a,(hl+)
 sbc d
 or (hl)
 jr nz,lane_invalid
 ld a,e
 cp #32
 ret nc
 add a,a
 add a,a
 add a,a
 or c
 scf
 ret
