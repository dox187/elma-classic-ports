; Coarse object bounds: signed integer parts of head and both wheels, +/-1.
; Store unsigned-biased words (signed xor8000), with inclusive saturation.
; Near bank5, ABI0 destination@SP+2. No shared RAM or bank/IRQ changes.
.module objects_bounds_fast
.area _CODE_5
_gbc_objects_bounds::
 ld a,(#_gbc_bike+42)
 ld e,a
 ld a,(#_gbc_bike+43)
 xor a,#0x80
 ld d,a
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ld (hl),e
 inc hl
 ld (hl),d
 ld a,(#_gbc_bike+46)
 ld e,a
 ld a,(#_gbc_bike+47)
 xor a,#0x80
 ld d,a
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld bc,#4
 add hl,bc
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ld (hl),e
 inc hl
 ld (hl),d
 ld a,(#_gbc_bike+12)
 ld e,a
 ld a,(#_gbc_bike+13)
 xor a,#0x80
 ld d,a
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call update_bounds
 ld a,(#_gbc_bike+16)
 ld e,a
 ld a,(#_gbc_bike+17)
 xor a,#0x80
 ld d,a
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld bc,#4
 add hl,bc
 call update_bounds
 ld a,(#_gbc_bike+22)
 ld e,a
 ld a,(#_gbc_bike+23)
 xor a,#0x80
 ld d,a
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call update_bounds
 ld a,(#_gbc_bike+26)
 ld e,a
 ld a,(#_gbc_bike+27)
 xor a,#0x80
 ld d,a
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld bc,#4
 add hl,bc
 call update_bounds
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld b,#2
expand_axis:
 ld a,(hl+)
 or a,(hl)
 jr z,min_saturated
 dec hl
 ld a,(hl)
 sub a,#1
 ld (hl+),a
 ld a,(hl)
 sbc a,#0
 ld (hl),a
min_saturated:
 inc hl
 ld a,(hl+)
 and a,(hl)
 inc a
 jr z,max_saturated
 dec hl
 inc (hl)
 jr nz,max_no_carry
 inc hl
 inc (hl)
 jr max_saturated
max_no_carry:
 inc hl
max_saturated:
 inc hl
 dec b
 jr nz,expand_axis
 ret

; DE=biased candidate, HL=minimum low byte; maximum follows minimum.
update_bounds:
 ld a,e
 sub a,(hl)
 inc hl
 ld a,d
 sbc a,(hl)
 jr nc,keep_min
 ld (hl),d
 dec hl
 ld (hl),e
 inc hl
keep_min:
 inc hl
 ld a,(hl+)
 sub a,e
 ld a,(hl)
 sbc a,d
 ret nc
 ld (hl),d
 dec hl
 ld (hl),e
 ret

; Inclusive coarse rectangle. ABI0 object@2,bounds@4; E=boolean.
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
 push de
 call inside_axis
 pop de
 or a,a
 jr z,object_outside
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
 call inside_axis
 ld e,a
 ret
object_outside:
 ld e,#0
 ret
inside_axis:
 ld a,c
 sub a,(hl)
 inc hl
 ld a,b
 sbc a,(hl)
 jr c,axis_outside
 inc hl
 ld a,(hl+)
 sub a,c
 ld a,(hl)
 sbc a,b
 jr c,axis_outside
 ld a,#1
 ret
axis_outside:
 xor a
 ret
