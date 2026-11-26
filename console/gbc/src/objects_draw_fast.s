; Exact batched visible-object OAM publication. Near bank 5, stack ABI0:
; visibleptr@2,count@4,phase@5,n@6,right_first@7 -> ending sprite E.
; n<=13, count<=64; phase<count for nonempty lists. Count 0/n 0 return 13.
; Object layout:14 bytes, x@0,y@2,kind@4. Final uint8 OAM casts make
; the low-byte coordinate subtractions exact even across uint16 wrap.
; No shared state, bank/IRQ writes or mutation outside selected shadow OAM.
.module objects_draw_fast
.ifdef WORLD_SIGNED_BG
OBJECT_TILE_OFFSET = 128
.else
OBJECT_TILE_OFFSET = 0
.endif
.area _CODE_5
.macro object_column
 ld (hl),c
 inc hl
 ld (hl),b
 inc hl
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
.endm
_gbc_objects_draw::
 ldhl sp,#6
 ld a,(hl)
 or a
 jp z,objects_empty
 ld d,a
 ldhl sp,#4
 ld a,(hl)
 or a
 jp z,objects_empty
 ld e,a
 inc hl
 ld b,(hl)
 sub a,b
 ld e,a
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,l
 add a,b
 ld l,a
 jr nc,objects_cursor_ready
 inc h
objects_cursor_ready:
 push de
 ld de,#(_shadow_OAM+52)
 push de
 push hl
 ldhl sp,#13
 bit 0,(hl)
 jp nz,objects_right_loop
 jp objects_left_loop
objects_left_loop:
 pop hl
 ld a,(hl+)
 push hl
 ld e,a
 ld d,#0
 ld l,a
 ld h,#0
 add hl,hl
 add hl,de
 add hl,hl
 add hl,de
 add hl,hl
 ld de,#_game_objects
 add hl,de
 ld a,(#_game_camera_x)
 ld e,a
 ld a,(hl)
 sub a,e
 ld b,a
 inc hl
 inc hl
 ld a,(#_game_camera_y)
 ld e,a
 ld a,(hl)
 sub a,e
 add a,#8
 ld c,a
 inc hl
 inc hl
 ld a,(hl)
 ld de,#(2552-OBJECT_TILE_OFFSET)
 cp a,#2
 jr z,objects_left_fields_ready
 ld de,#(2812-OBJECT_TILE_OFFSET)
 cp a,#3
 jr nz,objects_left_fields_ready
 ld d,#5
objects_left_fields_ready:
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 object_column
 ld a,b
 add a,#8
 ld b,a
 inc e
 inc e
 object_column
 pop bc
 add sp,#2
 pop de
 dec d
 jp z,objects_done
 dec e
 jr nz,objects_left_no_wrap
 push hl
 ldhl sp,#4
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#6
 ld e,(hl)
 pop hl
objects_left_no_wrap:
 push de
 push hl
 push bc
 jp objects_left_loop
objects_right_loop:
 pop hl
 ld a,(hl+)
 push hl
 ld e,a
 ld d,#0
 ld l,a
 ld h,#0
 add hl,hl
 add hl,de
 add hl,hl
 add hl,de
 add hl,hl
 ld de,#_game_objects
 add hl,de
 ld a,(#_game_camera_x)
 ld e,a
 ld a,(hl)
 sub a,e
 add a,#8
 ld b,a
 inc hl
 inc hl
 ld a,(#_game_camera_y)
 ld e,a
 ld a,(hl)
 sub a,e
 add a,#8
 ld c,a
 inc hl
 inc hl
 ld a,(hl)
 ld de,#(2554-OBJECT_TILE_OFFSET)
 cp a,#2
 jr z,objects_right_fields_ready
 ld de,#(2814-OBJECT_TILE_OFFSET)
 cp a,#3
 jr nz,objects_right_fields_ready
 ld d,#5
objects_right_fields_ready:
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 object_column
 ld a,b
 sub a,#8
 ld b,a
 dec e
 dec e
 object_column
 pop bc
 add sp,#2
 pop de
 dec d
 jp z,objects_done
 dec e
 jr nz,objects_right_no_wrap
 push hl
 ldhl sp,#4
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#6
 ld e,(hl)
 pop hl
objects_right_no_wrap:
 push de
 push hl
 push bc
 jp objects_right_loop
objects_done:
 ldhl sp,#6
 ld a,(hl)
 add a,a
 add a,#13
 ld e,a
 ret
objects_empty:
 ld e,#13
 ret
_gbc_objects_draw_end::
