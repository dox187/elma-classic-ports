; Exact Q14 phase geometry, shared by the head, rider and suspension.
.module physics_pose_lookup
.area _HRAM
_riding_pose_cosine:: .ds 4
_riding_pose_sine:: .ds 4
pose_cos_ax:: .ds 3
pose_neg_cos_ay:: .ds 3
pose_sin_ax:: .ds 3

.area _CODE
; A selects the other quarter wave. Its word address is $c000-HL.
.macro pose_reflect
 ld (#0x2000),a
 xor a
 sub a,l
 ld l,a
 ld a,#0xc0
 sbc a,h
 ld h,a
.endm

; A negative non-integral wave is the complement of its positive sample.
; Bit 15 marks an exact sample, which needs the extra unit of negation.
.macro pose_negative high,low,pair,?ready
 ld a,(hl+)
 cpl
 ld low,a
 ld a,(hl)
 cpl
 ld high,a
 bit 7,a
 jr nz,ready
 set 7,high
 inc pair
ready:
.endm

; Enter in bank 8 with the rounded phase in DE. The temporary wave and
; scalar mappings run under the fixed-ROM interrupt handler.
.area _CODE_8
_riding_refresh_geometry::
 ld a,d
 rlca
 rlca
 rlca
 and a,#7
 ld c,a                         ; full-turn octant
 ld b,#0
 ld a,d
 and a,#31
 ld h,a
 or a,e
 jp z,pose_octant_endpoint
 ld l,e
 add hl,hl
 set 6,h                        ; $4000 + 2 * (phase modulo 8192)
 ld a,c
 and #1
 add #16
 jp pose_wave_read
.area _CODE
pose_wave_read:
 ld (#0x2000),a
 xor #1
 bit 1,c
 jr nz,pose_cos_forward
 bit 2,c
 jr nz,pose_both_negative
 ld d,a
 ld c,(hl)
 inc l
 ld b,(hl)
 res 7,b
 dec l
 ld a,d
 pose_reflect
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 res 7,d
 jp pose_trig_ready
pose_both_negative:
 ld d,a
 pose_negative b,c,bc
 dec l
 ld a,d
 pose_reflect
 pose_negative d,e,de
 jp pose_trig_ready
pose_cos_forward:
 bit 2,c
 jr nz,pose_negative_sine
 ld b,a
 pose_negative d,e,de
 dec l
 ld a,b
 pose_reflect
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 res 7,b
 jp pose_trig_ready
pose_negative_sine:
 ld b,a
 ld e,(hl)
 inc l
 ld d,(hl)
 res 7,d
 dec l
 ld a,b
 pose_reflect
 pose_negative b,c,bc
 jp pose_trig_ready
.area _CODE_8
pose_octant_endpoint:
 ; At a quarter or eighth turn the positive and negative interpolation
 ; tables meet. Read the exact Q14 endpoint pair by octant.
 ld hl,#pose_endpoints
 add hl,bc
 add hl,bc
 add hl,bc
 add hl,bc
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 jp pose_trig_ready
.area _CODE
pose_trig_ready:
 push bc
 ld hl,#_riding_pose_trig
 ld a,(hl+)
 cp e
 jr nz,pose_change_c
 ld a,(hl)
 cp d
 jr nz,pose_change_c
 or e
 jr nz,pose_done_c
pose_change_c:
 ld (hl),d
 dec hl
 ld (hl),e
 ld a,d
 sub #63
 cp #2
 jr nc,pose_general_c
 ld a,#1
 ld (#0x2000),a
 call pose_hot_cos
 jr pose_done_c
pose_general_c:
 ld a,d
 rlca
 and #1
 add #18
 ld (#0x2000),a
 call pose_scalar_cos
pose_done_c:
 pop de
 ld hl,#_riding_pose_trig+2
 ld a,e
 ld (hl+),a
 ld (hl),d
 ld a,d
 rlca
 and #1
 add #18
 ld (#0x2000),a
 call pose_scalar_sin
 ld a,#8
 ld (#0x2000),a
 jp pose_anchors
.area _CODE_8
; Exact octant endpoints in the caller bank.
pose_endpoints:
 .dw 0,16384,11585,11585,16384,0,11585,-11585
 .dw 0,-16384,-11585,-11585,-16384,0,-11585,11585

.area _CODE_1
pose_hot_cos:
 ld h,d
 ld l,e
 add hl,hl
 add hl,hl
 add hl,hl
 ld bc,#(_riding_pose_hot_rows-(0x3f00*8))
 add hl,bc
 ld a,(hl+)
 xor #128
 ldh (#_riding_pose_cosine),a
 ld a,(hl+)
 add #128
 ldh (#_riding_pose_cosine+2),a
 ld a,#2
 adc #0
 ldh (#_riding_pose_cosine+3),a
 ld a,(hl+)
 ld (#_riding_pose_rest+2),a
 ld a,(hl+)
 ld (#_riding_pose_rest+3),a
 ld a,(hl+)
 ldh (#pose_cos_ax),a
 ld a,(hl+)
 ldh (#pose_cos_ax+1),a
 ld a,#3
 ldh (#pose_cos_ax+2),a
 ld a,(hl+)
 ldh (#pose_neg_cos_ay),a
 ld a,(hl)
 ldh (#pose_neg_cos_ay+1),a
 ld a,#0xfd
 ldh (#pose_neg_cos_ay+2),a
 ret
.area _CODE_8
; BC,E hold one signed24 operand and HRAM holds the other. Publish both
; center-span and center+span as signed32. The newly decoded sine Y stays
; in registers for the first pair.
.macro pose_pair memory,dest,center_in_regs
 ld hl,#dest
 ldh a,(#memory)
 .if center_in_regs
 cpl
 scf
 adc a,c
 .else
 sub a,c
 .endif
 ld (hl+),a
 ldh a,(#memory+1)
 .if center_in_regs
 cpl
 adc a,b
 .else
 sbc a,b
 .endif
 ld (hl+),a
 ldh a,(#memory+2)
 .if center_in_regs
 cpl
 adc a,e
 .else
 sbc a,e
 .endif
 ld (hl+),a
 rla
 sbc a,a
 ld (hl+),a
 ldh a,(#memory)
 add a,c
 ld (hl+),a
 ldh a,(#memory+1)
 adc a,b
 ld (hl+),a
 ldh a,(#memory+2)
 adc a,e
 ld (hl+),a
 rla
 sbc a,a
 ld (hl),a
.endm

pose_anchors:
 pose_pair pose_cos_ax,_riding_pose_anchor,1
 ld hl,#pose_sin_ax
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld e,(hl)
 pose_pair pose_neg_cos_ay,_riding_pose_anchor+8,0
 ret
