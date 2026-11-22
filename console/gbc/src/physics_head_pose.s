; Cache the angle-dependent geometry. A rider can turn or translate while
; the body phase is unchanged, so always apply the current facing and position.
.module physics_head_pose
.area _DATA
pose_valid: .ds 1
_riding_pose_phase:: .ds 2

.area _CODE_8
_riding_head_pose32::
 ; Rounded Q16 phase, discarding the high turn bits.
 ld hl,#_Bike+16
 ld a,(hl+)
 add a,#64
 ld b,a
 ld a,(hl+)
 adc a,#0
 ld e,a
 ld a,(hl)
 adc a,#0
 ld d,a
 sla b
 rl e
 rl d
 ld hl,#_riding_pose_phase
 ld a,(hl+)
 cp e
 jr nz,pose_refresh
 ld a,(hl)
 cp d
 jr nz,pose_refresh
 ld a,(#pose_valid)
 or a,a
 jr nz,pose_ready
pose_refresh:
 ld hl,#_riding_pose_phase
 ld a,e
 ld (hl+),a
 ld (hl),d
 ld a,#1
 ld (#pose_valid),a
 ld e,#b_riding_refresh_geometry
 ld hl,#_riding_refresh_geometry
 call ___sdcc_bcall_ehl
pose_ready:
 ; Stack ABI0: publish cosine and sine to the calling physics context.
 ldhl sp,#2
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(#_riding_pose_trig)
 ld (bc),a
 inc bc
 ld a,(#_riding_pose_trig+1)
 ld (bc),a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ld a,(#_riding_pose_trig+2)
 ld (bc),a
 inc bc
 ld a,(#_riding_pose_trig+3)
 ld (bc),a

 ; DE and BC hold the two facing-dependent head displacements.
 ld hl,#_riding_pose_cosine
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ld hl,#_riding_pose_sine
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ld a,(#_Bike+96)
 or a,a
 jr nz,pose_facing_ready
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 xor a
 sub a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
pose_facing_ready:
 ld hl,#_riding_pose_sine+2
 ld a,e
 sub a,(hl)
 inc hl
 ld e,a
 ld a,d
 sbc a,(hl)
 ld d,a
 push bc
 ld hl,#_Bike+72
 ld bc,#_Bike+88
 call pose_coordinate
 pop de
 ld hl,#_riding_pose_cosine+2
 ld a,e
 add a,(hl)
 inc hl
 ld e,a
 ld a,d
 adc a,(hl)
 ld d,a
 ld hl,#_Bike+76
 ld bc,#_Bike+92
pose_coordinate:
 ; Copy rider + signextended offset*256 modulo 2^32.
 ld a,(hl+)
 ld (bc),a
 inc bc
 ld a,(hl+)
 add a,e
 ld (bc),a
 inc bc
 ld a,(hl+)
 adc a,d
 ld (bc),a
 inc bc
 ld a,(hl)
 bit 7,d
 jr z,pose_positive
 adc a,#255
 ld (bc),a
 ret
pose_positive:
 adc a,#0
 ld (bc),a
 ret
