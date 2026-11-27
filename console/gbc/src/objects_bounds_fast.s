; Coarse object bounds: signed integer parts of head and both wheels, +/-1.
; Store unsigned-biased words (signed xor8000), with inclusive saturation.
; Bounds helper: near bank5, ABI0 destination@SP+2; no bank/IRQ changes.
.module objects_bounds_fast
.area _CODE_5
; The wheel and head coordinates always occupy these three pose slots.
; Use their link-time addresses on each axis and keep the output on stack.
.macro gather_axis offset,ordered,check_max,ready
 ld hl,#(_gbc_bike+12+offset)
 ld a,(hl+)
 ld c,a
 ld a,(hl)
 xor #0x80
 ld b,a
 ld hl,#(_gbc_bike+22+offset)
 ld a,(hl+)
 ld e,a
 ld a,(hl)
 xor #0x80
 ld d,a
 ; Sort the two wheel coordinates with one comparison, then extend the
 ; interval only if the head lies below the minimum or above the maximum.
 ld a,c
 sub e
 ld a,b
 sbc d
 jr c,ordered
 ld a,e
 ld e,c
 ld c,a
 ld a,d
 ld d,b
 ld b,a
ordered:
 ld hl,#(_gbc_bike+42+offset)
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,h
 xor #0x80
 ld h,a
 ld a,l
 sub c
 ld a,h
 sbc b
 jr nc,check_max
 ld b,h
 ld c,l
 jr ready
check_max:
 ld a,e
 sub l
 ld a,d
 sbc h
 jr nc,ready
 ld d,h
 ld e,l
ready:
.endm
_gbc_objects_bounds::
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 gather_axis 0,x_ordered,x_check_max,x_ready
 pop hl
 call bounds_store
 push hl
 gather_axis 4,y_ordered,y_check_max,y_ready
 pop hl
 jr bounds_store

; Expand at full precision, saturate at the two ends and write once.
bounds_store:
 ld a,b
 or a,c
 jr z,bounds_min_ready
 dec bc
bounds_min_ready:
 ld a,d
 and a,e
 inc a
 jr z,bounds_max_ready
 inc de
bounds_max_ready:
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ret

; Inclusive coarse rectangle, with rejected points clipping an empty region.
; ABI0 object@2,bounds@4; E=boolean. The caller resets the empty region once
; per scan; cached candidate IDs cover eligible objects not excluded by it.
_gbc_object_near::
 ldhl sp,#2
 ld a,(hl+)
 ld d,(hl)
 add a,#7
 ld e,a
 jr nc,object_x_ptr
 inc d
object_x_ptr:
 ld a,(de)
 ld c,a
 inc de
 ld a,(de)
 xor a,#0x80
 ld b,a
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,c
 sub a,(hl)
 inc hl
 ld a,b
 sbc a,(hl)
 jr c,clip_x_min
 inc hl
 ld a,(hl+)
 sub a,c
 ld a,(hl)
 sbc a,b
 jr c,clip_x_max
 inc hl
 ld a,e
 add a,#3
 ld e,a
 jr nc,object_y_ptr
 inc d
object_y_ptr:
 ld a,(de)
 ld c,a
 inc de
 ld a,(de)
 xor a,#0x80
 ld b,a
 ld a,c
 sub a,(hl)
 inc hl
 ld a,b
 sbc a,(hl)
 jr c,clip_y_min
 inc hl
 ld a,(hl+)
 sub a,c
 ld a,(hl)
 sbc a,b
 jr c,clip_y_max
 ld e,#1
 ret
clip_x_min:
 ld hl,#_gbc_objects_empty_bounds
 jr clip_min
clip_x_max:
 ld hl,#_gbc_objects_empty_bounds+2
 jr clip_max
clip_y_min:
 ld hl,#_gbc_objects_empty_bounds+4
 jr clip_min
clip_y_max:
 ld hl,#_gbc_objects_empty_bounds+6
clip_max:
 ; A point above the current maximum cannot be zero.
 dec bc
 ld a,c
 sub a,(hl)
 inc hl
 ld a,b
 sbc a,(hl)
 jr c,clip_store
 ld e,#0
 ret
clip_min:
 ; A point below the current minimum cannot be 65535.
 inc bc
 ld a,(hl+)
 sub a,c
 ld a,(hl)
 sbc a,b
 jr nc,object_outside
clip_store:
 ld (hl),b
 dec hl
 ld (hl),c
object_outside:
 ld e,#0
 ret
