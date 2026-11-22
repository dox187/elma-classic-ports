; Export Q18 native positions to Q16 world coordinates in bank 8.
; The upper half of each origin is part of every position. Original levels
; have integral origins, so their zero fractional halves require no addition.
.module riding_export_fast
.area _CODE_8

.macro export_axis source,target,origin
 ld hl,#(_Bike+source+3)
 ld a,(hl-)
 sra a
 ld b,a
 ld a,(hl-)
 rra
 ld c,a
 ld a,(hl-)
 rra
 ld d,a
 ld a,(hl)
 rra
 ld e,a
 sra b
 rr c
 rr d
 rr e
 ld hl,#(_gbc_bike+target)
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ld a,(#origin+2)
 add a,c
 ld (hl+),a
 ld a,(#origin+3)
 adc a,b
 ld (hl),a
.endm
_physics_export_state_fast::
 export_axis 0,0,_physics_level_origin_x
 export_axis 4,4,_physics_level_origin_y
 export_axis 24,10,_physics_level_origin_x
 export_axis 28,14,_physics_level_origin_y
 export_axis 48,20,_physics_level_origin_x
 export_axis 52,24,_physics_level_origin_y
 export_axis 72,30,_physics_level_origin_x
 export_axis 76,34,_physics_level_origin_y
 export_axis 88,40,_physics_level_origin_x
 export_axis 92,44,_physics_level_origin_y
 ld hl,#_physics_level_origin_x
 ld a,(hl+)
 or a,(hl)
 ld hl,#_physics_level_origin_y
 or a,(hl)
 inc hl
 or a,(hl)
 call nz,export_fractional_origins
 ld a,(#_physics_export_angle_shift)
 cp a,#8
 jr z,export_angles8
 ld a,(#_Bike+17)
 add a,a
 ld c,a
 ld a,(#_Bike+18)
 rla
 ld b,a
 ld a,(#_Bike+16)
 rlca
 and a,#1
 or a,c
 ld (#_gbc_bike+8),a
 ld a,b
 ld (#_gbc_bike+9),a
 ld a,(#_Bike+41)
 add a,a
 ld c,a
 ld a,(#_Bike+42)
 rla
 ld b,a
 ld a,(#_Bike+40)
 rlca
 and a,#1
 or a,c
 ld (#_gbc_bike+18),a
 ld a,b
 ld (#_gbc_bike+19),a
 ld a,(#_Bike+65)
 add a,a
 ld c,a
 ld a,(#_Bike+66)
 rla
 ld b,a
 ld a,(#_Bike+64)
 rlca
 and a,#1
 or a,c
 ld (#_gbc_bike+28),a
 ld a,b
 ld (#_gbc_bike+29),a
 jr export_finish
export_angles8:
 ld a,(#_Bike+17)
 ld (#_gbc_bike+8),a
 ld a,(#_Bike+18)
 ld (#_gbc_bike+9),a
 ld a,(#_Bike+41)
 ld (#_gbc_bike+18),a
 ld a,(#_Bike+42)
 ld (#_gbc_bike+19),a
 ld a,(#_Bike+65)
 ld (#_gbc_bike+28),a
 ld a,(#_Bike+66)
 ld (#_gbc_bike+29),a
export_finish:
 ld a,(#_gbc_bike+8)
 ld (#_gbc_bike+38),a
 ld (#_gbc_bike+48),a
 ld a,(#_gbc_bike+9)
 ld (#_gbc_bike+39),a
 ld (#_gbc_bike+49),a
 ld a,(#_Bike+96)
 ld (#_gbc_bike+51),a
 ret

; Add the remaining unsigned low half of each origin, including the carry
; into the high half. Offsets repeat every 10 bytes in the public pose.
export_fractional_origins:
 ld hl,#_physics_level_origin_x
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ld hl,#_gbc_bike
 call export_fractional_axis
 ld hl,#_physics_level_origin_y
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ld hl,#_gbc_bike+4
export_fractional_axis:
 ld e,#5
export_fractional_next:
 ld a,(hl)
 add a,c
 ld (hl+),a
 ld a,(hl)
 adc a,b
 ld (hl+),a
 ld a,(hl)
 adc a,#0
 ld (hl+),a
 ld a,(hl)
 adc a,#0
 ld (hl),a
 dec e
 ret z
 ld a,l
 add a,#7
 ld l,a
 jr nc,export_fractional_next
 inc h
 jr export_fractional_next
