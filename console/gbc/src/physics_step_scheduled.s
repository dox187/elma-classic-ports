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
; Gravity is signed16. A carry into the upper half from a negative
; impulse cancels its sign extension; a positive impulse needs a carry.
.macro step_add_gravity address,?done
 ld hl,#(address)
 ld a,(hl)
 add e
 ld (hl+),a
 ld a,(hl)
 adc d
 ld (hl+),a
 ld a,c
 adc #0
 jr z,done
 add (hl)
 ld (hl+),a
 ld a,b
 adc (hl)
 ld (hl),a
done:
.endm
.macro step_push32 address
 step_load32 address
 push bc
 push de
.endm

; Set both torques once. Braking supersedes throttle in the PC solver.
; On the first brake substep, capture each angle relative to the body.
.macro step_brake_origin wheel_angle,destination
 ld hl,#(_Bike+16)
 ld de,#(_Bike+destination)
 .irp offset,0,1,2,3
 ld a,(#(_Bike+wheel_angle+offset))
 .if offset
 sbc a,(hl)
 .else
 sub a,(hl)
 .endif
 ld (de),a
 inc de
 inc hl
 .endm
.endm
_riding_step_controls::
 bit 1,a
 jr z,step_drive
 ld hl,#(_Bike+98)
 ld a,(hl)
 ld (hl),#2
 or a
 jr nz,step_brake
 step_brake_origin 40,101
 step_brake_origin 64,105
step_brake:
 ld de,#(_riding_suspension_state+18)
 ld bc,#(_riding_suspension_state+32)
 jp _riding_brake_fields
step_drive:
 ld b,a
 xor a
 ld (#(_Bike+98)),a
 ld hl,#(_riding_suspension_state+18)
 .rept 3
 ld (hl+),a
 .endm
 ld (hl),a
 ld hl,#(_riding_suspension_state+32)
 .rept 3
 ld (hl+),a
 .endm
 ld (hl),a
 bit 0,b
 ret z
 ld a,(#(_Bike+96))
 or a
 jr nz,step_left_drive
 ld hl,#(_Bike+68+3)
 ld de,#(_riding_drive_bounds+3)
 call _riding_bounds_before
 ret nc
 ld hl,#_riding_drive_torque
 ld de,#(_riding_suspension_state+32)
 jr step_store_torque
step_left_drive:
 ld hl,#(_riding_drive_bounds+7)
 ld de,#(_Bike+44+3)
 call _riding_bounds_before
 ret nc
 ld hl,#(_riding_drive_torque+4)
 ld de,#(_riding_suspension_state+18)
step_store_torque:
 .rept 3
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 ld a,(hl)
 ld (de),a
 ret

; DE and BC point to the two generated int32 rows for gravity. Its integer
; part fits int16, its fraction fits uint8. Return the magnitude in BC.
_riding_step_gravity::
 ld a,(#_riding_subphase)
 or a
 jr z,step_gravity_row
 ld hl,#4
 add hl,de
 ld d,h
 ld e,l
 ld hl,#4
 add hl,bc
 ld b,h
 ld c,l
step_gravity_row:
 ld hl,#(_Bike+99)
 inc (hl)
 inc hl
 ld a,(bc)
 add a,(hl)
 ld (hl),a
 ld a,(de)
 adc a,#0
 ld c,a
 inc de
 ld a,(de)
 adc a,#0
 ld b,a
 ret

; BCDE is the previous angular residual less both signed Q24 fractions.
; Publish the pending value for the body after the rider observes the old one.
_riding_step_commit_fraction_regs::
 ld hl,#_riding_suspension_state+step_fraction
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
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
 ; Only a low-byte wrap reaches the upper bytes of the impulse.
 ld hl,#_riding_suspension_state+step_dwb
 inc a
 jr z,step_decrement_impulse
 .rept 3
 inc (hl)
 ret nz
 inc hl
 .endm
 inc (hl)
 ret
step_decrement_impulse:
 .rept 3
 ld a,(hl)
 sub #1
 ld (hl+),a
 ret nc
 .endm
 dec (hl)
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
 step_add_gravity _riding_suspension_state+step_dvx
 step_add_gravity _riding_suspension_state+step_dvx+step_wheel_stride
 step_add_gravity _riding_suspension_state+step_dvbx
 ld hl,#0
 push hl
 push hl
 push bc
 push de
 jr step_rider_response
step_gravity_y:
 call step_extend_gravity
 step_add_gravity _riding_suspension_state+step_dvy
 step_add_gravity _riding_suspension_state+step_dvy+step_wheel_stride
 step_add_gravity _riding_suspension_state+step_dvby
 push bc
 push de
 ld hl,#0
 push hl
 push hl
step_rider_response:
 step_push32 _riding_suspension_state+step_oms
 step_push32 _riding_pose_rest
 call _riding_rider_response_after_limit
 add sp,#16
 ; Only now can the rider's old body velocity and residual be replaced.
 step_load32 _riding_suspension_state+step_dwb
 step_add32 _Bike+20
 step_load32 _riding_suspension_state+step_fraction
 ld hl,#_angular_residual
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,c
 ld (hl+),a
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

 .ifdef RIDING_CORNER_CELLS
; The CRT installs two ordinary bank-9 calls. Course resets and quarter-square
; changes replace the two operands independently, between wheel solves.
.area _INITIALIZED
step_solve_wheels:: .ds 12
.area _INITIALIZER
 .else
.area _CODE_9
step_solve_wheels::
 .endif
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
; A Q18 bike coordinate becomes a signed 24-bit Q10 coordinate. Its
; two upper bytes fully identify the cached region after applying the
; 4 m, 1 m or quarter-metre mask. The shifted sign byte follows bit 23.
.macro step_head_region coord,old,cache
 ld hl,#cache
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ldhl sp,#old
 ld a,(hl+)
 and c
 cp e
 jr nz,step_head_terrain
 ld a,(hl)
 cp d
 jr nz,step_head_terrain
 ld hl,#coord
 ld a,(hl+)
 and c
 cp e
 jr nz,step_head_terrain
 ld a,(hl)
 cp d
 jr nz,step_head_terrain
.endm
_riding_step_head::
 ; The stored head is the previous endpoint until head_position runs.
 add sp,#-8
 step_push_head _Bike+92
 step_push_head _Bike+88
 call _riding_step_head_position
 ; Both endpoints inside the same certified rectangle prove the path
 ; clear. Most substeps finish here before packing the new endpoint.
 ld a,(#_riding_head_clear_mask)
 or a
 jr z,step_head_terrain
 .ifdef RIDING_CORNER_CELLS
 ; Mask 1 carries an eight-unit proof. Match bits 3..7 of both endpoints
 ; before the shared comparison of the two upper Q10 bytes.
 cp #1
 jr nz,step_head_mask
 ld a,(#_riding_head_near_xlow)
 ld e,a
 ldhl sp,#0
 ld a,(hl)
 xor e
 and #0xf8
 jr nz,step_head_terrain
 ld a,(#_Bike+89)
 xor e
 and #0xf8
 jr nz,step_head_terrain
 ld a,(#_riding_head_near_ylow)
 ld e,a
 ldhl sp,#4
 ld a,(hl)
 xor e
 and #0xf8
 jr nz,step_head_terrain
 ld a,(#_Bike+93)
 xor e
 and #0xf8
 jr nz,step_head_terrain
 ld a,#255
step_head_mask:
 .endif
 ld c,a
 step_head_region _Bike+90,1,_riding_head_clear_x
 step_head_region _Bike+94,5,_riding_head_clear_y
 add sp,#16
 ld a,#1
 ret
step_head_terrain:
 ldhl sp,#8
 ld de,#_Bike+89
 step_write_head
 inc de
 step_write_head
 ld e,#b_riding_swept_head
 ld hl,#_riding_head_terrain_query
 call ___sdcc_bcall_ehl
 add sp,#16
 sub a,#1
 ld a,#0
 rla
 ret

; Three PC integration intervals per outer update. B holds the controls
; for the current interval; DE accumulates each wheel's impacts. A volt
; only survives the first interval. A grid exit still runs its final
; interval before reporting death and publishing the accumulated impacts.
_riding_scheduled_frame::
 and #15
 add a,#<frame_controls
 ld l,a
 ld a,#>frame_controls
 adc a,#0
 ld h,a
 ld b,(hl)
 ld a,(#_gbc_bike+50)
 or a
 ret z
 xor a
 ld (#_riding_subphase),a
 ld de,#0
 call frame_interval
 jr z,frame_publish
 ld a,b
 and #3
 ld b,a
 call frame_interval
 jr z,frame_publish
 ld a,#1
 ld (#_riding_subphase),a
 call frame_interval
frame_publish:
 ld hl,#_riding_audio_impact
 ld (hl),e
 inc hl
 ld (hl),d
 jp _physics_export_state_fast

frame_interval:
 push de
 push bc
 call _wheels_in_grid
 ld c,a
 ldhl sp,#1
 ld a,(hl)
 push bc
 call _ph_step
 pop bc
 or a
 jr z,frame_alive
 ld a,c
 or a
 call nz,_head_body_in_level
frame_alive:
 ld (#_gbc_bike+50),a
 pop bc
 pop de
 ld c,a
 ld hl,#_riding_audio_impact
 ld a,(hl+)
 or e
 ld e,a
 ld a,(hl)
 or d
 ld d,a
 ld a,c
 or a
 ret

frame_controls:
 .db 0,1,2,3,8,9,10,11,4,5,6,7,12,13,14,15
