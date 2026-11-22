; Exact scaled Q14 trig. The upper byte selects the period base and row
; pointer. The low byte addresses an eight-byte row in the same ROM bank.
.module physics_pose_lookup
.area _CODE_1

.macro pose_byte
 ld a,(de)
 inc de
 adc a,(hl)
 inc hl
 ld (bc),a
 inc bc
.endm
.macro pose_extend
 ld a,(hl+)
 adc a,#0
 ld (bc),a
 inc bc
.endm
.macro pose_field width,extension
 or a,a
 .rept width
 pose_byte
 .endm
 .rept extension
 pose_extend
 .endm
.endm

_riding_scaled_trig::
 ldhl sp,#2
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 bit 7,d
 push af
 jr z,pose_magnitude
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
pose_magnitude:
 ld h,#0
 ld l,d
 add hl,hl
 add hl,hl
 ld bc,#_riding_pose_pages
 add hl,bc
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 ld h,#0
 ld l,e
 add hl,hl
 add hl,hl
 add hl,hl
 add hl,bc
 ld d,h
 ld e,l
 ldhl sp,#8
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 pop hl
 ; HL is the block increment, DE is the row, BC is the output.
 pose_field 1,1
 pose_field 1,1
 pose_field 2,0
 pose_field 2,2
 pose_field 2,2
 pop af
 ret z
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 .rept 3
 xor a
 sub a,(hl)
 ld (hl+),a
 ld a,#0
 sbc a,(hl)
 ld (hl+),a
 .endm
 .rept 2
 xor a
 sub a,(hl)
 ld (hl+),a
 .rept 3
 ld a,#0
 sbc a,(hl)
 ld (hl+),a
 .endm
 .endm
 ret
