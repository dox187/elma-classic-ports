; ABI0, destination at SP+2, near call with bank 5 selected.
; A batch shares each full Q16.16 origin and its pixel camera offset.
.module video_screen_fast
.area _CODE_5

; A marked byte holds the upper candidate. The two thresholds are
; ceil(16384/3)-0x1500 and ceil(32768/3)-0x2a00 respectively.
.macro quarter_pixels base
 .rept 21
 .db base
 .endm
 .db (0x80+base+1)
 .rept 20
 .db (base+1)
 .endm
 .db (0xc0+base+2)
 .rept 21
 .db (base+2)
 .endm
.endm
.ifdef SCREEN_FRACTION_PAGE
screen_fraction_page == 1
.endif
fraction_pixels::
 quarter_pixels 0
 quarter_pixels 3
 quarter_pixels 6
 quarter_pixels 9

.macro load_origin offset
 ld hl,#(_game_world+offset)
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
.endm

; The fractional projector consumes BCDE. Preserve the origin when another
; point on the same axis follows. Both variants leave a pixel on the stack.
.macro project_part offset,project
 push bc
 push de
 ld hl,#(_gbc_bike+offset)
 call project
 pop de
 pop bc
 push hl
.endm

.macro project_and_push offset,project
 ld hl,#(_gbc_bike+offset)
 call project
 push hl
.endm

; Three projected words precede the return address and the destination.
.macro screen_destination offset,camera
 ldhl sp,#8
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld bc,#offset
 add hl,bc
 ld a,(#camera)
 ld c,a
 ld a,(#camera+1)
 ld b,a
.endm

.macro store_pixel
 pop de
 ld a,e
 sub c
 ld (hl+),a
 ld a,d
 sbc b
 ld (hl+),a
.endm

; The complete projection adds the two rider words before sharing the three
; visible parts. The 8x16 renderer takes its rider pose from the body atlas.
_gbc_video_parts_screen::
 load_origin 4
 ld hl,#(_gbc_bike+30)
 call project_x
 push hl
 load_origin 8
 ld hl,#(_gbc_bike+34)
 call project_y
 push hl
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld bc,#6
 add hl,bc
 ld a,(#_game_camera_y)
 ld c,a
 ld a,(#_game_camera_y+1)
 ld b,a
 store_pixel
 dec hl
 dec hl
 dec hl
 dec hl
 ld a,(#_game_camera_x)
 ld c,a
 ld a,(#_game_camera_x+1)
 ld b,a
 store_pixel
_gbc_video_sprite_screen::
 load_origin 4
 ld a,d
 or e
 jr nz,sprite_fractional_x
 project_and_push 20,integral_x
 project_and_push 10,integral_x
 project_and_push 40,integral_x
 jr sprite_store_x
sprite_fractional_x:
 project_part 20,project_x
 project_part 10,project_x
 project_and_push 40,project_x
sprite_store_x:
 screen_destination 8,_game_camera_x
 store_pixel            ; head.x
 inc hl
 inc hl
 store_pixel            ; wheel_x[0]
 store_pixel            ; wheel_x[1]

 load_origin 8
 ld a,d
 or e
 jr nz,sprite_fractional_y
 project_and_push 24,integral_y
 project_and_push 14,integral_y
 project_and_push 44,integral_y
 jr sprite_store_y
sprite_fractional_y:
 project_part 24,project_y
 project_part 14,project_y
 project_and_push 44,project_y
sprite_store_y:
 screen_destination 10,_game_camera_y
 store_pixel            ; head.y
 inc hl
 inc hl
 inc hl
 inc hl
 store_pixel            ; wheel_y[0]
 store_pixel            ; wheel_y[1]
_gbc_video_parts_screen_end::
 ret

; The camera uses the body's two clamped level pixels before it can scroll.
_gbc_video_body_world::
 load_origin 8
 ld hl,#(_gbc_bike+4)
 ld a,d
 or e
 jr nz,body_fractional_y
 call integral_y
 jr body_store_y
body_fractional_y:
 call project_y
body_store_y:
 push hl
 load_origin 4
 ld hl,#_gbc_bike
 ld a,d
 or e
 jr nz,body_fractional_x
 call integral_x
 jr body_store_x
body_fractional_x:
 call project_x
body_store_x:
 push hl
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 .rept 2
 pop de
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 .endm
_gbc_video_body_world_end::
 ret

; In every shipped level the origin's fractional word is zero. Leave the
; integer origin in BC and read the low fraction byte only at a rounding
; boundary on X. DE is free between points in an integral batch.
.macro lookup_fraction boundary
 .ifdef SCREEN_FRACTION_PAGE
 ld e,a
 ld d,#>fraction_pixels
 .else
 add a,#<fraction_pixels
 ld e,a
 ld a,#>fraction_pixels
 adc a,#0
 ld d,a
 .endif
 ld a,(de)
 bit 7,a
 jr nz,boundary
.endm
integral_x:
 inc hl
 ld a,(hl+)
 lookup_fraction integral_x_boundary
integral_x_whole:
 ld e,a
 ld a,(hl+)
 sub c
 ld h,(hl)
 ld l,a
 ld a,h
 sbc b
 jr integral_pixels

integral_y:
 xor a
 sub (hl)
 inc hl
 ld a,#0
 sbc (hl)
 inc hl
 jr nc,integral_y_zero
 lookup_fraction integral_y_boundary
integral_y_nonzero:
 scf                  ; subtract the borrow from negating the fraction
integral_y_whole:
 ld e,a
 ld a,c
 sbc (hl)
 inc hl
 ld l,(hl)
 ld h,a
 ld a,b
 sbc l
 ld l,h
integral_pixels:
 ld h,a
 inc a
 cp #2
 jr nc,integral_clip
 ld a,e
 ld d,h
 ld e,l
 add hl,hl
 add hl,de
 add hl,hl
 add hl,hl
 add a,l
 ld l,a
 ret nc
 inc h
 ret
integral_clip:
 bit 7,h
 ld hl,#3072
 ret z
 ld hl,#-3072
 ret
integral_y_zero:
 xor a
 jr integral_y_whole

; The shared thresholds apply to the fractional word in the direction
; being projected. HL returns to the integer word before its subtraction.
integral_x_boundary:
 ld d,a
 dec hl
 dec hl
 ld a,(hl+)
 inc hl
 call integral_round
 jr integral_x_whole
integral_y_boundary:
 ld d,a
 dec hl
 dec hl
 xor a
 sub (hl)
 inc hl
 inc hl
 call integral_round
 jr integral_y_nonzero
integral_round:
 ld e,#86
 bit 6,d
 jr z,integral_compare
 ld e,#171
integral_compare:
 cp e
 ld a,d
 ; Strip the boundary marker after the borrow adjusts the candidate.
 sbc a,#0
 and #15
 ret

; HL points at a little-endian position, BCDE holds the origin.
; Subtract all four bytes, including unsigned wrap at the signed32 limits.
project_x:
 ld a,(hl+)
 sub e
 ld e,a
 ld a,(hl+)
 sbc d
 ld d,a
 ld a,(hl+)
 sbc c
 ld c,a
 ld a,(hl)
 sbc b
 jr project_pixels

project_y:
 ld a,e
 sub (hl)
 inc hl
 ld e,a
 ld a,d
 sbc (hl)
 inc hl
 ld d,a
 ld a,c
 sbc (hl)
 inc hl
 ld c,a
 ld a,b
 sbc (hl)

; A:C:D:E is the signed Q16.16 displacement. Outside [-256,256) metres
; the result clips. Otherwise 12*floor(delta/65536) fits in signed16.
project_pixels:
 ld b,a
 inc a
 cp #2
 jr nc,clip_pixel
 ld h,b
 ld l,c
 add hl,hl
 add hl,hl
 ld b,h
 ld c,l
 add hl,hl
 add hl,bc

 ; At 12 px/m, the high fractional byte selects the pixel except at
 ; 0x15xx and 0x2axx within each quarter, where the low byte breaks the tie.
 .ifdef SCREEN_FRACTION_PAGE
 ld c,d
 ld b,#>fraction_pixels
 .else
 ld a,d
 add a,#<fraction_pixels
 ld c,a
 ld a,#>fraction_pixels
 adc a,#0
 ld b,a
 .endif
 ld a,(bc)
 bit 7,a
 jr nz,fraction_boundary
add_fraction:
 add a,l
 ld l,a
 ret nc
 inc h
 ret

fraction_boundary:
 bit 6,a
 ld d,#86
 jr z,have_threshold
 ld d,#171
have_threshold:
 and #15
 ld b,a
 ld a,e
 cp d
 ld a,b
 sbc a,#0
 jr add_fraction

clip_pixel:
 bit 7,b
 ld hl,#3072
 ret z
 ld hl,#-3072
 ret
