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
 sra b
 rr c
 rr d
 rra
 ld hl,#(_gbc_bike+target)
 ld (hl+),a
 ld a,d
 ld (hl+),a
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
 ; The top bit of byte 0 becomes bit 0 of the exported angle.
 ; Loads and stores preserve carry between the two output bytes.
.macro export_angle7 source,target
 ld hl,#(_Bike+source)
 ld a,(hl+)
 rla
 ld a,(hl+)
 rla
 ld (#(_gbc_bike+target)),a
 ld a,(hl)
 rla
 ld (#(_gbc_bike+target+1)),a
.endm
 export_angle7 16,8
 export_angle7 40,18
 export_angle7 64,28
 jr export_finish
export_angles8:
.macro export_angle8 source,target
 ld hl,#(_Bike+source+1)
 ld a,(hl+)
 ld (#(_gbc_bike+target)),a
 ld a,(hl)
 ld (#(_gbc_bike+target+1)),a
.endm
 export_angle8 16,8
 export_angle8 40,18
 export_angle8 64,28
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
