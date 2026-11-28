; Exact wheel expressions for certified rectangles. BC points to the wheel.
; Each macro fits between two existing aligned rolling tables in bank 29.
.macro wheel_rect_query
_haircut_query::
 push bc
 ld h,b
 ld l,c
 inc hl
 ld a,(hl+)
 rlca
 rlca
 rlca
 and #7
 ld e,a
 ld a,(hl+)
 sub #88                  ; X origin 153600 and width 2304, in 32-unit tiles
 cp #9
 jr nc,rect_miss
 add a
 add a
 add a
 or e
 ld b,a
 ld a,(hl+)
 cp #2
 jr nz,rect_miss
 inc hl
 ld a,(hl+)
 rlca
 rlca
 rlca
 and #7
 ld e,a
 ld a,(hl+)
 sub #100                 ; Y origin 25600 and height 2048
 cp #8
 jr nc,rect_miss
 add a
 add a
 add a
 or e
 ld c,a
 ld a,(hl)
 or a
 jr nz,rect_miss
 ld a,c
 rrca
 rrca
 rrca
 and #7
 ld e,a
 add a
 add a
 add a
 add e
 ld e,a
 ld a,b
 rrca
 rrca
 rrca
 and #15
 add e
 ld e,a
 ld d,#0
 ld hl,#haircut_directory
 add hl,de
 ld d,(hl)
 ld e,#30
 ld hl,#haircut_tile_code
 call ___sdcc_bcall_ehl
 pop bc
 cp #15
 jr z,rect_no_code
 or a
 ret z
 cp #1
 jp z,haircut_cap
 jp haircut_plane
rect_no_code:
 ld a,#255
 ret
rect_miss:
 pop bc
 ld a,#255
 ret
.endm

.macro wheel_rect_plane
haircut_plane:
 push af
 call haircut_center
 pop af
 sub #2
 add a
 add a
 add a
 ld l,a
 ld h,#0
 push de
 ld de,#haircut_planes
 add hl,de
 pop de
 ld a,e
 sub (hl)
 ld e,a
 inc hl
 ld a,d
 sbc (hl)
 ld d,a
 inc hl
 ld a,c
 sub (hl)
 ld c,a
 inc hl
 ld a,b
 sbc (hl)
 ld b,a
 inc hl
 push hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl                  ; Y coefficient
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 inc hl
 inc hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl                  ; X coefficient
 call _riding_terrain_dotq14
 pop hl                   ; original Y coefficient
 ld e,#0
 bit 7,b
 jr z,rect_check_range
 dec e
 xor a
 sub c
 ld c,a
 ld a,#0
 sbc b
 ld b,a
rect_check_range:
 ld a,b
 cp #2
 jr nc,rect_empty
 or a
 jr z,rect_plane_hit
 ld a,c
 cp #154
 jr nc,rect_empty
rect_plane_hit:
 push bc
 inc hl
 inc hl
 call rect_signed_word
 ld (#_Ct),a
 ld a,b
 ld (#_Ct+1),a
 .rept 4
 dec hl
 .endm
 call rect_signed_word
 ld (#_Ct+2),a
 ld a,b
 ld (#_Ct+3),a
 pop bc
 ld hl,#_Ct+4
 ld (hl),c
 inc hl
 ld (hl),b
 ld a,#1
 ret
rect_empty:
 xor a
 ret
.endm

.macro wheel_rect_cap
; Unsigned low words of the signed center. The caller checked both high bytes.
haircut_center:
 ld h,b
 ld l,c
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
 ret
rect_signed_word:
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 bit 0,e
 ld a,c
 ret z
 xor a
 sub c
 ld c,a
 ld a,#0
 sbc b
 ld b,a
 ld a,c
 ret
haircut_cap:
 call haircut_center
 ld hl,#_riding_contact_qx
 ld a,e
 sub #<154144
 ld (hl+),a
 ld a,d
 sbc #>154144
 ld (hl+),a
 ld a,c
 sub #<27204
 ld (hl+),a
 ld a,b
 sbc #>27204
 ld (hl),a
 xor a
 ld hl,#_riding_dense_vertex
 .rept 4
 ld (hl+),a
 .endm
 ld hl,#_riding_resolve_shared_cap
 ld e,#5
 jp ___sdcc_bcall_ehl
.endm

.macro wheel_rect_tile_code
haircut_tile_code:
 ld a,d
 ld hl,#haircut_pages0
 cp #16
 jr c,rect_page
 ld hl,#haircut_pages1
 cp #32
 jr c,rect_page
 ld hl,#haircut_pages2
rect_page:
 and #15
 add a
 add a
 add a
 ld e,a
 ld a,c
 and #6
 or e
 ld e,a
 ld a,b
 rrca
 rrca
 and #1
 or e
 ld e,a
 ld d,#0
 add hl,de
 ld a,(hl)
 ld hl,#haircut_blocks0
 bit 5,a
 jr z,rect_blocks
 ld hl,#haircut_blocks1
rect_blocks:
 and #31
 add a
 add a
 ld e,a
 ld a,c
 and #1
 add a
 or e
 ld e,a
 ld a,b
 rrca
 and #1
 or e
 ld e,a
 add hl,de
 ld a,(hl)
 bit 0,b
 jr z,rect_nibble
 swap a
rect_nibble:
 and #15
 ret
.endm
