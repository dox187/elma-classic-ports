; Cache the angle-dependent geometry. A rider can turn or translate while
; the body phase is unchanged, so always apply the current facing and position.
.module physics_head_pose
.area _DATA
pose_valid: .ds 1
_riding_pose_phase:: .ds 2

.area _CODE_8
_riding_head_pose32::
 call _riding_step_head_position
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
 ret

; The game reads the cached trig pair directly.
_riding_step_head_position::
 ; Rounded Q16 phase, discarding the high turn bits.
 ld hl,#_Bike+16
 ld a,(hl+)
 add a,a                         ; carry = bit 7, B bit 7 = rounding bit 6
 ld b,a
 ld a,(hl+)
 rla
 ld e,a
 ld a,(hl)
 rla
 ld d,a
 bit 7,b
 jr z,pose_phase_rounded
 inc de
pose_phase_rounded:
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
 call _riding_refresh_geometry
pose_ready:
 ; The head's local X component changes sign when the rider turns.
 ; Read one component from HRAM and combine it with the other at HL.
 ld a,(#_Bike+96)
 or a
 jr z,pose_default_facing
 ld hl,#_riding_pose_sine+2
 ldh a,(#_riding_pose_cosine)
 sub a,(hl)
 ld e,a
 inc hl
 ldh a,(#_riding_pose_cosine+1)
 sbc a,(hl)
 ld d,a
 ld hl,#_riding_pose_sine
 ldh a,(#_riding_pose_cosine+2)
 add a,(hl)
 ld c,a
 inc hl
 ldh a,(#_riding_pose_cosine+3)
 adc a,(hl)
 ld b,a
 jr pose_facing_ready
pose_default_facing:
 ld hl,#_riding_pose_sine+2
 ldh a,(#_riding_pose_cosine)
 cpl
 sub a,(hl)
 ld e,a
 inc hl
 ldh a,(#_riding_pose_cosine+1)
 cpl
 sbc a,(hl)
 ld d,a
 inc de                         ; -cosine.x - sine.y
 ld hl,#_riding_pose_sine
 ldh a,(#_riding_pose_cosine+2)
 sub a,(hl)
 ld c,a
 inc hl
 ldh a,(#_riding_pose_cosine+3)
 sbc a,(hl)
 ld b,a
pose_facing_ready:
 ; Both offsets now fit in registers. Rider and head coordinates are
 ; consecutive, so one source pointer advances through both axes.
.macro pose_coordinate low,high,destination,?positive
 ld a,(hl+)
 ld (#destination),a
 ld a,(hl+)
 add a,low
 ld (#destination+1),a
 ld a,(hl+)
 adc a,high
 ld (#destination+2),a
 ld a,(hl+)
 adc a,#0
 bit 7,high
 jr z,positive
 dec a
positive:
 ld (#destination+3),a
.endm
 ld hl,#_Bike+72
 pose_coordinate e,d,_Bike+88
 pose_coordinate c,b,_Bike+92
 ret
