; ABI0, destination at SP+2, near call with bank 5 selected.
; A batch shares each full Q16.16 origin and its pixel camera offset.
.module video_screen_fast
.area _CODE_5

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

; Preserve the origin for the next point. Leave this pixel on the stack.
.macro project_part offset,project
 push bc
 push de
 ld hl,#(_gbc_bike+offset)
 call project
 pop de
 pop bc
 push hl
.endm

.macro project_last offset,project
 ld hl,#(_gbc_bike+offset)
 call project
 push hl
.endm

; Four projected words precede the return address and the destination.
.macro screen_destination offset,camera
 ldhl sp,#10
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

_gbc_video_parts_screen::
 load_origin 4
 project_part 20,project_x
 project_part 10,project_x
 project_part 40,project_x
 project_last 30,project_x
 screen_destination 4,_game_camera_x
 store_pixel            ; rider.x
 inc hl
 inc hl
 store_pixel            ; head.x
 inc hl
 inc hl
 store_pixel            ; wheel_x[0]
 store_pixel            ; wheel_x[1]

 load_origin 8
 project_part 24,project_y
 project_part 14,project_y
 project_part 44,project_y
 project_last 34,project_y
 screen_destination 6,_game_camera_y
 store_pixel            ; rider.y
 inc hl
 inc hl
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
 project_last 4,project_y
 load_origin 4
 project_last 0,project_x
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
 ld a,d
 add a,#<fraction_pixels
 ld c,a
 ld a,#>fraction_pixels
 adc a,#0
 ld b,a
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
fraction_pixels:
 quarter_pixels 0
 quarter_pixels 3
 quarter_pixels 6
 quarter_pixels 9
