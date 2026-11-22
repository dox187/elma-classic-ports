; Native contact candidate iteration. Near bank9, ABI1 qx=DE,qy=BC -> A.
; Retains ordered box iterator and existing exact projection/normal/merge math.
.module physics_contact_loop
.area _DATA
contact_loop_box: .ds 2
contact_loop_found: .ds 1
contact_loop_seg: .ds 2
contact_loop_k: .ds 2
contact_loop_x: .ds 2
contact_loop_y: .ds 2
contact_loop_d: .ds 2
.area _CODE_9
_riding_contacts_loop::
 ld a,(#_Seg_left)
 or a,a
 ret z
 ld hl,#_riding_contact_qx
 ld a,e
 ld (hl+),a
 ld (hl),d
 ld hl,#_riding_contact_qy
 ld a,c
 ld (hl+),a
 ld (hl),b
 ; q is0..4095; rotate its low byte and shift its high byte for q>>6.
 ld a,e
 rlca
 rlca
 and a,#3
 ld e,a
 ld a,d
 add a,a
 add a,a
 or a,e
 add a,#128
 ld (#contact_loop_box),a
 ld a,c
 rlca
 rlca
 and a,#3
 ld c,a
 ld a,b
 add a,a
 add a,a
 or a,c
 add a,#128
 ld (#contact_loop_box+1),a
 xor a,a
 ld (#contact_loop_found),a
 ld hl,#contact_loop_k
 ld (hl),#<_Ct
 inc hl
 ld (hl),#>_Ct
contact_loop_next:
 ld hl,#contact_loop_box
 ld c,(hl)
 inc hl
 ld b,(hl)
 push bc
 call _riding_segment_box
 pop hl
 ld a,d
 or a,e
 jr nz,contact_loop_record
 ld a,(#contact_loop_found)
 ret
contact_loop_record:
 ld hl,#contact_loop_seg
 ld a,e
 ld (hl+),a
 ld (hl),d
 ld h,d
 ld l,e
 ld a,(#_riding_contact_qx)
 sub a,(hl)
 inc hl
 ld (#contact_loop_x),a
 ld a,(#_riding_contact_qx+1)
 sbc a,(hl)
 inc hl
 ld (#contact_loop_x+1),a
 ld a,(#_riding_contact_qy)
 sub a,(hl)
 inc hl
 ld (#contact_loop_y),a
 ld a,(#_riding_contact_qy+1)
 sbc a,(hl)
 inc hl
 ld (#contact_loop_y+1),a
 ld de,#4
 add hl,de
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ; Exact Q14 unit axes project by selecting a signed coordinate. All other
 ; normals, including nearly horizontal or vertical ones, use the full dot.
 ld a,c
 or a,e
 jr nz,contact_loop_general
 ld a,b
 or a,a
 jr z,contact_loop_vertical
 ld a,d
 or a,a
 jr nz,contact_loop_general
 ld a,b
 cp #0x40
 jr z,contact_loop_axis_right
 cp #0xc0
 jr nz,contact_loop_general
 call contact_loop_xy
 call contact_loop_neg_pos
 call contact_loop_neg_distance
 jr contact_loop_axis_ready
contact_loop_axis_right:
 call contact_loop_xy
 jr contact_loop_axis_ready
contact_loop_vertical:
 ld a,d
 cp #0x40
 jr z,contact_loop_axis_up
 cp #0xc0
 jr nz,contact_loop_general
 call contact_loop_yx
 call contact_loop_neg_pos
 jr contact_loop_axis_ready
contact_loop_axis_up:
 call contact_loop_yx
 call contact_loop_neg_distance
contact_loop_axis_ready:
 push de
 call contact_loop_in_radius
 pop bc
 jp nc,contact_loop_next
 jr contact_loop_position
contact_loop_general:
 push bc
 xor a,a
 sub a,e
 ld e,a
 sbc a,a
 sub a,d
 ld d,a
 push de
 call contact_loop_xy
 call _dotq14
 call contact_loop_in_radius
 jp nc,contact_loop_next
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#8
 add hl,de
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 push bc
 push de
 call contact_loop_xy
 call _dotq14
contact_loop_position:
 ; Low14 length; high bits identify synthetic endpoints.
 bit 7,b
 jp nz,contact_loop_endpoint
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#12
 add hl,de
 ld a,(hl+)
 ld e,a
 ld a,(hl)
 and a,#0x3f
 ld d,a
 ld a,e
 sub a,c
 ld a,d
 sbc a,b
 jp c,contact_loop_endpoint
 ; An artificial end belongs to the next piece, avoiding duplicate normals.
 ld a,e
 cp a,c
 jr nz,contact_loop_interior
 ld a,d
 cp a,b
 jr nz,contact_loop_interior
 bit 7,(hl)
 jp nz,contact_loop_next
contact_loop_interior:
 ; Write nx,ny,l directly into the selected ten-byte Ct record.
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#8
 add hl,de
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ld a,(#contact_loop_d+1)
 bit 7,a
 jr nz,contact_loop_negative
 xor a,a
 sub a,e
 ld e,a
 sbc a,a
 sub a,d
 ld d,a
 jr contact_loop_write_normal
contact_loop_negative:
 xor a,a
 sub a,c
 ld c,a
 sbc a,a
 sub a,b
 ld b,a
contact_loop_write_normal:
 ld hl,#contact_loop_k
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld a,(#contact_loop_d)
 ld e,a
 ld a,(#contact_loop_d+1)
 ld d,a
 bit 7,d
 jr z,contact_loop_write_length
 xor a,a
 sub a,e
 ld e,a
 sbc a,a
 sub a,d
 ld d,a
contact_loop_write_length:
 ld a,e
 ld (hl+),a
 ld (hl),d
 jp contact_loop_accept
contact_loop_endpoint:
 ; BC is projected position: negative selects start, positive selects end.
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#13
 add hl,de
 bit 7,b
 jr z,contact_loop_check_end
 bit 6,(hl)
 jp nz,contact_loop_next
 jr contact_loop_original_endpoint
contact_loop_check_end:
 bit 7,(hl)
 jp nz,contact_loop_next
contact_loop_original_endpoint:
 bit 7,b
 jr nz,contact_loop_endpoint_ready
 ld a,b
 or a,c
 jr z,contact_loop_endpoint_ready
 ld hl,#contact_loop_seg
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#4
 add hl,de
 ld a,(#contact_loop_x)
 sub a,(hl)
 inc hl
 ld (#contact_loop_x),a
 ld a,(#contact_loop_x+1)
 sbc a,(hl)
 inc hl
 ld (#contact_loop_x+1),a
 ld a,(#contact_loop_y)
 sub a,(hl)
 inc hl
 ld (#contact_loop_y),a
 ld a,(#contact_loop_y+1)
 sbc a,(hl)
 ld (#contact_loop_y+1),a
contact_loop_endpoint_ready:
 call contact_loop_xy
 ld a,e
 add a,#0x99
 ld l,a
 ld a,d
 adc a,#1
 ld h,a
 ld a,l
 sub a,#0x33
 ld a,h
 sbc a,#3
 jp nc,contact_loop_next
 ld a,c
 add a,#0x99
 ld l,a
 ld a,b
 adc a,#1
 ld h,a
 ld a,l
 sub a,#0x33
 ld a,h
 sbc a,#3
 jp nc,contact_loop_next
 .ifdef RIDING_NORMAL_ATLAS
 ; Coordinates are bounded to [-409,409]. An atlas hit proves d2 < 410^2.
 ld hl,#contact_loop_k
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call _riding_normal_ring
 or a
 jr nz,contact_loop_accept
 call contact_loop_xy
 .endif
 ; Existing exact multiply kernel, with its register entry avoiding ABI spills.
 ld hl,#contact_loop_k
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 ld b,d
 ld c,e
 call _riding_mul16_regs
 push hl
 push de
 ld hl,#contact_loop_y
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ld b,d
 ld c,e
 call _riding_mul16_regs
 pop bc
 ld a,e
 add a,c
 ld c,a
 ld a,d
 adc a,b
 ld b,a
 pop de
 ld a,l
 adc a,e
 ld e,a
 ld a,h
 adc a,d
 ld d,a
 ; d2 is nonnegative after the strict coordinate guards above.
 ld a,c
 sub a,#0xa4
 ld a,b
 sbc a,#0x90
 ld a,e
 sbc a,#2
 ld a,d
 sbc a,#0
 jr c,contact_loop_normalize
 pop hl
 jp contact_loop_next
contact_loop_normalize:
 push de
 push bc
 call contact_loop_xy
 push bc
 push de
 call _riding_normal_fast
 add sp,#10
contact_loop_accept:
 ld a,(#contact_loop_found)
 or a,a
 jr nz,contact_loop_merge
 inc a
 ld (#contact_loop_found),a
 ld hl,#contact_loop_k
 ld (hl),#<(_Ct+10)
 inc hl
 ld (hl),#>(_Ct+10)
 jp contact_loop_next
contact_loop_merge:
 call _riding_contact_merge
 or a,a
 jp z,contact_loop_next
 ret
contact_loop_xy:
 ld hl,#contact_loop_x
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ld hl,#contact_loop_y
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ret
contact_loop_yx:
 ld hl,#contact_loop_y
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ld hl,#contact_loop_x
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ret
contact_loop_neg_pos:
 ; dotq14 saturates -(-32768) to +32767.
 xor a,a
 sub a,e
 ld e,a
 sbc a,a
 sub a,d
 ld d,a
 cp #0x80
 ret nz
 ld a,e
 or a,a
 ret nz
 dec de
 ret
contact_loop_neg_distance:
 ; Either signed extreme lies outside the wheel radius.
 xor a,a
 sub a,c
 ld c,a
 sbc a,a
 sub a,b
 ld b,a
 ret
contact_loop_in_radius:
 ld hl,#contact_loop_d
 ld a,c
 ld (hl+),a
 ld (hl),b
 ; -410<d<410 iff uint16(d+409)<819, including signed extremes.
 ld a,c
 add a,#0x99
 ld e,a
 ld a,b
 adc a,#1
 ld d,a
 ld a,e
 sub a,#0x33
 ld a,d
 sbc a,#3
 ret
