; BC identifies a sixteen-entry block directory. DE points at the wheel.
; Called only for an already verified two-contact center with this tile key.
 push de
 inc de
 ld a,(de)
 and #15
 ld h,a
 inc de
 inc de
 inc de
 inc de
 ld a,(de)
 and #15
 ld d,a
 ld e,h
 and #12
 ld l,a
 ld a,e
 rrca
 rrca
 and #3
 or l
 add a
 ld l,a
 ld h,#0
 add hl,bc
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,h
 or a
 jr nz,pair_block_hit
 pop de
 ld a,#255
 ret
pair_block_hit:
 ld a,d
 and #3
 add a
 add a
 ld d,a
 ld a,e
 and #3
 or d
 ld e,a                   ; pixel in the four-by-four block
 ld a,(hl+)
 ld c,a                   ; bytes varying across the block
 ld b,#0
 push hl
 ld a,e
 or a
 jr z,pair_have_pixel
pair_skip_pixel:
 add hl,bc
 dec a
 jr nz,pair_skip_pixel
pair_have_pixel:
 ld d,h
 ld e,l
 pop hl
 push de
 ld a,c
 swap a
 ld e,a
 and #15
 ld d,a
 xor e
 ld e,a
 add hl,de                ; template after sixteen packed pixel records
 ld de,#_Ct
 ; The reader page has room to copy the fixed-size contact pair inline.
 .rept 20
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 pop de
 ld a,c
 or a
 jr z,pair_return
pair_overlay:
 ld a,(hl+)
 push hl
 ld h,#0
 ld l,a
 ld a,(de)
 inc de
 push de
 ld de,#_Ct
 add hl,de
 ld (hl),a
 pop de
 pop hl
 dec c
 jr nz,pair_overlay
pair_return:
 ; A prepared pair may later retain only the low halves of this center.
 ; Bind its full square key first, invalidating the previous geometry kind.
 pop de
 ld hl,#_wheel_surface_cache
 ld a,e
 cp #<(_Bike+48)
 jr nz,pair_bind_key
 ld hl,#(_wheel_surface_cache+29)
pair_bind_key:
 push de
 push hl
 inc de
 inc de
 ld a,(de)
 cp (hl)
 jr nz,pair_changed_square
 inc de
 inc hl
 ld a,(de)
 cp (hl)
 jr nz,pair_changed_square
 inc de
 inc de
 inc de
 inc hl
 ld a,(de)
 cp (hl)
 jr nz,pair_changed_square
 inc de
 inc hl
 ld a,(de)
 cp (hl)
 jr nz,pair_changed_square
 add sp,#4
 ld a,#2
 ret
pair_changed_square:
 pop hl
 pop de
 inc de
 inc de
 ld a,(de)
 ld (hl+),a
 inc de
 ld a,(de)
 ld (hl+),a
 inc de
 inc de
 inc de
 ld a,(de)
 ld (hl+),a
 inc de
 ld a,(de)
 ld (hl+),a
 ld (hl),#0
 ld a,#2
 ret
