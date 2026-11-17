; Exact visible active IDs, ascending order. Near bank5, ABI0 ids@SP2 -> E.
; game_world.object_count@32 <=64; object records14 bytes, x0/y2.
; Visibility is u16(obj.x-camera_x+7)<175 and corresponding Y<151.
; The high-byte rejection is conservative across every uint16 wrap.
; Writes only the returned ID prefix; no shared RAM/bank/IRQ changes.
.module objects_visible_fast
.area _CODE_5
_gbc_objects_visible::
 ld a,(#(_game_world+32))
 or a,a
 jp z,visible_empty
 ld b,a
 ld a,#<(_game_object_active)
 add a,b
 push af
 ldhl sp,#4
 ld c,(hl)
 inc hl
 ld b,(hl)
 ld de,#_game_object_active
 ld hl,#_game_objects
visible_next:
 ld a,(de)
 inc de
 or a,a
 jr z,visible_advance
 push hl
 push bc
 inc hl
 ld a,(#(_game_camera_x+1))
 sub a,(hl)
 inc a
 cp a,#3
 jr nc,visible_restore
 dec hl
 ld a,(#_game_camera_x)
 sub a,#7
 ld c,a
 ld a,(#(_game_camera_x+1))
 sbc a,#0
 ld b,a
 ld a,(hl+)
 sub a,c
 ld c,a
 ld a,(hl+)
 sbc a,b
 or a,a
 jr nz,visible_restore
 ld a,c
 cp a,#175
 jr nc,visible_restore
 ld a,(#_game_camera_y)
 sub a,#7
 ld c,a
 ld a,(#(_game_camera_y+1))
 sbc a,#0
 ld b,a
 ld a,(hl+)
 sub a,c
 ld c,a
 ld a,(hl+)
 sbc a,b
 or a,a
 jr nz,visible_restore
 ld a,c
 cp a,#151
visible_restore:
 pop bc
 pop hl
 jr nc,visible_advance
 ld a,e
 sub a,#<(_game_object_active+1)
 ld (bc),a
 inc bc
visible_advance:
 ld a,l
 add a,#14
 ld l,a
 jr nc,visible_pointer_ready
 inc h
visible_pointer_ready:
 pop af
 cp a,e
 push af
 jr nz,visible_next
 pop af
 ldhl sp,#2
 ld a,c
 sub a,(hl)
 ld e,a
 ret
visible_empty:
 ld e,#0
 ret
_gbc_objects_visible_end::
