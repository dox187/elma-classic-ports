; Commit a scheduled substep directly from the suspension workspace. Gravity
; affects one axis. Its three contributions share the same sign extension.
.module physics_step_scheduled
.area _CODE_8

step_oms = 4
step_wheel0 = 8
step_wheel1 = 22
step_wheel_stride = 14
step_dvx = 10
step_dvy = 14
step_dvbx = 36
step_dvby = 40
step_dwb = 44
step_fraction = 48

; BC:DE holds one signed32 contribution, low byte in E.
.macro step_load32 address
 ld hl,#(address)
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
.endm
.macro step_sub32 address
 ld hl,#(address)
 ld a,e
 sub a,(hl)
 ld e,a
 inc hl
 ld a,d
 sbc a,(hl)
 ld d,a
 inc hl
 ld a,c
 sbc a,(hl)
 ld c,a
 inc hl
 ld a,b
 sbc a,(hl)
 ld b,a
.endm
.macro step_add32 address
 ld hl,#(address)
 ld a,(hl)
 add a,e
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld (hl+),a
 ld a,(hl)
 adc a,c
 ld (hl+),a
 ld a,(hl)
 adc a,b
 ld (hl),a
.endm
.macro step_push32 address
 step_load32 address
 push bc
 push de
.endm

; Before the volt/rider paths can overwrite q24_fraction, combine both
; sub-unit torque terms. Store the new signed24 residual in the consumed
; spring field. The rider still observes the previous angular_residual.
_riding_step_fraction::
 step_load32 _angular_residual
 step_sub32 _riding_suspension_state+step_fraction
 step_sub32 _q24_fraction
 ld hl,#_riding_suspension_state+step_fraction
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ld a,c
 ld (hl+),a
 add a,a
 sbc a,a
 ld (hl),a
 ld a,c
 add a,a
 ld a,b
 adc a,#0
 ret z
 ; The rounded carry is +1 or -1. Add with its full sign extension.
 ld e,a
 add a,a
 sbc a,a
 ld d,a
 ld c,a
 ld b,a
 step_add32 _riding_suspension_state+step_dwb
 ret

; DE is the positive gravity magnitude (including accumulated fraction).
; Apply it to the three pending impulses on the selected axis and place
; both gravity components directly on the rider-response argument stack.
_riding_step_apply::
 ld a,(#_Bike+97)
 cp a,#3
 jr z,step_gravity_x
 cp a,#2
 jr z,step_gravity_left
 or a
 jr z,step_gravity_y
 call step_neg_gravity
 jr step_gravity_y
step_gravity_left:
 call step_neg_gravity
step_gravity_x:
 call step_extend_gravity
 step_add32 _riding_suspension_state+step_dvx
 step_add32 _riding_suspension_state+step_dvx+step_wheel_stride
 step_add32 _riding_suspension_state+step_dvbx
 ld hl,#0
 push hl
 push hl
 push bc
 push de
 jr step_rider_response
step_gravity_y:
 call step_extend_gravity
 step_add32 _riding_suspension_state+step_dvy
 step_add32 _riding_suspension_state+step_dvy+step_wheel_stride
 step_add32 _riding_suspension_state+step_dvby
 push bc
 push de
 ld hl,#0
 push hl
 push hl
step_rider_response:
 step_push32 _riding_suspension_state+step_oms
 step_push32 _riding_pose_rest
 call _riding_rider_response32
 add sp,#16
 ; Only now can the rider's old body velocity and residual be replaced.
 step_load32 _riding_suspension_state+step_dwb
 step_add32 _Bike+20
 step_load32 _riding_suspension_state+step_fraction
 ld hl,#_angular_residual
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ld (hl),c
 inc hl
 ld (hl),b
 step_load32 _riding_suspension_state+step_dvbx
 step_add32 _Bike+8
 step_load32 _riding_suspension_state+step_dvby
 step_add32 _Bike+12
 ret
step_neg_gravity:
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ret
step_extend_gravity:
 ld a,d
 add a,a
 sbc a,a
 ld b,a
 ld c,a
 ret

; Both records already contain the full impulses. Keep bank 9 mapped until
; the right wheel has observed all effects of the left wheel's solve.
_riding_step_wheels::
 ld e,#b_riding_wheel
 ld hl,#step_solve_wheels
 jp ___sdcc_bcall_ehl

.area _CODE_9
step_solve_wheels:
 ld hl,#_riding_suspension_state+step_wheel0
 call _riding_wheel_inputs
 ld hl,#_riding_suspension_state+step_wheel1
 jp _riding_wheel_inputs

.area _CODE_8

; Convert F to u by dropping the low byte and sign-extending the upper 24.
.macro step_push_head address
 ld hl,#(address+1)
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl)
 ld c,a
 add a,a
 sbc a,a
 ld b,a
 push bc
 push de
.endm
.macro step_write_head
 ld a,(de)
 inc de
 ld (hl+),a
 ld a,(de)
 inc de
 ld (hl+),a
 ld a,(de)
 inc de
 ld (hl+),a
 add a,a
 sbc a,a
 ld (hl+),a
.endm
_riding_step_head::
 ; The stored head is the previous endpoint until head_position runs.
 add sp,#-8
 step_push_head _Bike+92
 step_push_head _Bike+88
 call _riding_step_head_position
 ldhl sp,#8
 ld de,#_Bike+89
 step_write_head
 inc de
 step_write_head
 ld e,#b_riding_swept_head
 ld hl,#_riding_swept_head
 call ___sdcc_bcall_ehl
 add sp,#16
 sub a,#1
 ld a,#0
 rla
 ret
