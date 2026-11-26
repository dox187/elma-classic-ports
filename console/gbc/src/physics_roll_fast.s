; Exact grounded rolling, bank 9. The public ABI0 entry takes
; k*, contact*, dvx32, dvy32, tq32. The resolver already owns those inputs.
.module physics_roll_fast
.area _CODE_9
_riding_roll32::
 ldhl sp,#2
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 jr roll_start
; HL -> k*,dvx32,dvy32,tq32. BC -> contact normal.
_riding_roll_inputs::
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
roll_start:
 push de
 push hl
 ld h,b
 ld l,c
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ; Tangent (-ny,nx), signed16 negation including INT16_MIN.
 push bc
 push de
 ; Stack: tangent 0, impulses pointer 4, wheel pointer 6.
 ; An exact unit tangent uses one coordinate on both projections.
 ld a,c
 or a,e
 jr nz,roll_input_dots
 ld a,b
 or a
 jr nz,roll_try_vertical
 ld a,d
 and #0x7f
 cp #0x40
 jr nz,roll_input_dots
 ld a,d
 and #0x80
 jr roll_axis_inputs
roll_try_vertical:
 ld a,d
 or a
 jr nz,roll_input_dots
 ld a,b
 and #0x7f
 cp #0x40
 jr nz,roll_input_dots
 ld a,b
 and #0x80
 or #4
roll_axis_inputs:
 ; Bit 2 selects Y and bit 7 requests saturated negation. Keep the
 ; pointer to the pending impulse until the projected velocity is stacked.
 ldhl sp,#4
 ld e,(hl)
 inc hl
 ld d,(hl)
 push de
 push af
 ldhl sp,#10
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#8
 add hl,de
 pop af
 push af
 call roll_axis_value
 pop af
 pop hl
 push de
 push bc
 call roll_axis_value
 jr roll_projected_inputs
roll_input_dots:
 ldhl sp,#6
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 ld hl,#8
 add hl,de
 ld d,h
 ld e,l
 ldhl sp,#0
 call _riding_dotq14_regs
 push hl
 push de
 ; Stack: vn 0, tangent 4, impulses pointer 8, wheel pointer 10.
 ldhl sp,#8
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 ldhl sp,#4
 call _riding_dotq14_regs
 ld b,d
 ld c,e
 ld d,h
 ld e,l
roll_projected_inputs:
 .ifdef RIDING_ROLL_TABLES
 ; The phase bank combines the two separately rounded Q24 operations for
 ; signed16 tangential impulse and torque sum, including variable braking.
 ; The following omega multiply publishes the last observable Q24 fraction.
 ldhl sp,#8
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push de
 ld de,#8
 add hl,de
 pop de
 ; With zero impulse and torque, both rounded operations yield zero.
 ld a,d
 or e
 or b
 or c
 jr nz,roll_lookup_delta
 ld a,(hl+)
 or (hl)
 inc hl
 or (hl)
 inc hl
 or (hl)
 jr z,roll_have_delta
 dec hl
 dec hl
 dec hl
roll_lookup_delta:
 call _riding_roll_table_delta
 jr c,roll_have_delta
 .endif
 ld hl,#_q24_index_C_ROLL_T
 dec sp
 call roll_coefficient
 ; t = tq + Q24(dvn, C_ROLL_T), modulo 2^32.
 ldhl sp,#8
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push de
 ld de,#8
 add hl,de
 pop de
 ld a,(hl+)
 add a,c
 ld c,a
 ld a,(hl+)
 adc a,b
 ld b,a
 ld a,(hl+)
 adc a,e
 ld e,a
 ld a,(hl)
 adc a,d
 ld d,a
 ld hl,#_q24_index_C_ROLL_DV
 dec sp
 call roll_coefficient
roll_have_delta:
 ; Update vn in place to the tangential speed and keep it in DEBC for omega.
 ldhl sp,#0
 ld a,(hl)
 add a,c
 ld (hl+),a
 ld c,a
 ld a,(hl)
 adc a,b
 ld (hl+),a
 ld b,a
 ld a,(hl)
 adc a,e
 ld (hl+),a
 ld e,a
 ld a,(hl)
 adc a,d
 ld (hl),a
 ld d,a
 .ifdef RIDING_ROLL_TABLES
 or e
 or b
 or c
 jr nz,roll_moving
 add sp,#10
 pop hl
 jp roll_stationary
roll_moving:
 .endif
 ld hl,#_q24_index_C_ROLL_W
 dec sp
 call roll_coefficient
 ldhl sp,#10
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push bc
 ld bc,#20
 add hl,bc
 pop bc
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld a,e
 ld (hl+),a
 ld (hl),d
 ; HL is at omega+3. The pair writes vx and vy directly into the wheel.
 ld de,#-15
 add hl,de
 call _riding_roll_project_pair
 add sp,#10
 pop hl
 jp _riding_wheel_move_hl

 .ifdef RIDING_ROLL_TABLES
.area _CODE
; The zero-speed wheel writes zero velocity and omega. Its two zero
; translations only sign-extend each residual's third byte. The omega
; coefficient (and the partial-step Y translation) publish zero Q24.
roll_stationary:
 ld de,#(_move_residual+18)
 ld a,l
 cp #<(_Bike+24)
 jr nz,roll_stationary_body
 ld a,h
 cp #>(_Bike+24)
 jr nz,roll_stationary_residual
 ld de,#(_move_residual+10)
 jr roll_stationary_residual
roll_stationary_body:
 cp #<_Bike
 jr nz,roll_stationary_residual
 ld a,h
 cp #>_Bike
 jr nz,roll_stationary_residual
 ld de,#(_move_residual+2)
roll_stationary_residual:
 push hl
 ld h,d
 ld l,e
 ld a,(hl+)
 add a
 sbc a
 ld (hl+),a
 inc hl
 inc hl
 ld a,(hl+)
 add a
 sbc a
 ld (hl),a
 pop hl
 ld de,#8
 add hl,de
 xor a
 .rept 8
 ld (hl+),a
 .endm
 inc hl
 inc hl
 inc hl
 inc hl
 .rept 4
 ld (hl+),a
 .endm
 ld hl,#_q24_fraction
 .rept 5
 ld (hl+),a
 .endm
 ret
 .endif

; HL points at two signed32 values. Return the selected Q14 cardinal
; projection in DEBC. Negative INT32_MIN rounds to saturated INT32_MAX.
roll_axis_value:
 bit 2,a
 jr z,roll_axis_load
 inc hl
 inc hl
 inc hl
 inc hl
roll_axis_load:
 bit 7,a
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ret z
 ld a,d
 xor #0x80
 or a,e
 or a,b
 or a,c
 jr nz,roll_axis_negate
 ld de,#0x7fff
 ld bc,#0xffff
 ret
roll_axis_negate:
 xor a
 sub a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
 ld a,#0
 sbc a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ret

.area _CODE_9
; HL -> two phase indices. The Q24 entry consumes its reserved argument byte
; and returns DEBC, including its normal fraction and saturation side effects.
roll_coefficient:
 ld a,(#_riding_subphase)
 or a
 jr z,roll_coefficient_ready
 inc hl
roll_coefficient_ready:
 ld a,(hl)
 jp _q24_apply_a

.area _CODE
; HL -> vx, vy. The caller's stack holds speed32, tangent x16, tangent y16.
; Both components use round-to-nearest with positive half ties, then saturate.
_riding_roll_project_pair::
 push hl
 .ifdef RIDING_ROLL_TABLES
 ldhl sp,#4
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 add a,a
 sbc a,a
 cp (hl)
 jp nz,roll_project_wide
 inc hl
 cp (hl)
 jp nz,roll_project_wide
 ld a,d
 or e
 jr z,roll_project_zero
 ; For the shallow rolling tangents, X is -speed and Y is one signed
 ; byte. The same two rounding-threshold rows used by the dot product
 ; give the exact Y without visiting a general projection bank.
 ldhl sp,#8
 ld a,(hl+)
 or a
 jr nz,roll_project_directory
 ld a,(hl+)
 cp #0xc0
 jr nz,roll_project_directory
 ld a,(hl+)
 ld c,a
 ld a,(hl)
 inc a
 jr nz,roll_project_directory
 ld a,c
 ld bc,#_riding_shallow_dot_61
 cp #195
 jr z,roll_project_shallow
 cp #247
 jr nz,roll_project_directory
 ld bc,#_riding_shallow_dot_9
 jr roll_project_shallow
roll_project_directory:
 ldhl sp,#8
 call roll_project_component
 ; The second component begins by reading the directory in bank 20.
 xor a
 ld (#0x3000),a
 pop hl
 call roll_store_regs
 push hl
 ldhl sp,#4
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 ldhl sp,#10
 call roll_project_component
 xor a
 ld (#0x3000),a
 ld a,(#__current_bank)
 ld (#0x2000),a
 jr roll_store_second
roll_project_zero:
 pop hl
 .rept 8
 ld (hl+),a
 .endm
 ret
roll_project_shallow:
 ld h,#0
 ld l,d
 add hl,bc
 ld a,#4
 ld (#0x2000),a
 ld b,(hl)
 inc h
 ld a,(hl)
 cp e
 ld a,b
 sbc #0
 ld c,a
 ld a,(#__current_bank)
 ld (#0x2000),a
 pop hl
 ld a,d
 cpl
 add a
 sbc a
 ld b,a                      ; sign extension of -speed (speed != 0)
 xor a
 sub e
 ld (hl+),a
 ld a,#0
 sbc d
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld (hl+),a
 ld a,c
 ld (hl+),a
 add a
 sbc a
 ld (hl+),a
 ld (hl+),a
 ld (hl),a
 ret
 .endif
roll_project_wide:
 ldhl sp,#8
 call roll_project_general
 pop hl
 call roll_store_regs
 push hl
 ldhl sp,#10
 call roll_project_general
roll_store_second:
 pop hl
roll_store_regs:
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ret
roll_project_general:
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 ldhl sp,#6
 call _riding_mulq14_regs
 ld b,h
 ld c,l
 ret

 .ifdef RIDING_ROLL_TABLES
; Signed16 speed in DE, HL -> signed16 coefficient. Return BCDE.
roll_project_component:
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 or a
 jr nz,roll_project_lookup
 ld a,b
 or a
 jr z,roll_component_zero
 cp #192
 jr z,roll_component_negate
 cp #64
 jr z,roll_component_unit
roll_project_lookup:
 ld a,#20
 ld (#0x2000),a
 ld h,#>_riding_projection_directory
 ld l,b
 ld h,(hl)
 ld l,c
 ld a,(hl)
 cp b
 jr nz,roll_component_miss
 inc h
 ld a,(hl)
 or a
 jr z,roll_component_miss
 inc h
 ld h,(hl)
 ld (#0x2000),a
 bit 7,a
 jr z,roll_project_lookup_mapped
 ld a,#1
 ld (#0x3000),a
roll_project_lookup_mapped:
 bit 7,h
 jr z,roll_project_rows
 res 7,h
 xor a
 sub e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 cp #128
 jr nz,roll_project_rows
 ld a,e
 or a
 jr z,roll_component_miss
roll_project_rows:
 ; U[lo] + (S[hi] << 8) is the signed product. Discard byte 0 and
 ; add the Q14 half at bit 5 of byte 1. U + 8192 fits its three planes
 ; for every signed16 coefficient and every unsigned low speed byte.
 ld l,e
 ld a,(hl)
 add a,#32
 ld c,a
 inc h
 ld a,(hl)
 adc a,#0
 ld b,a
 inc h
 ld l,d
 ld a,(hl)
 add a,c
 ld c,a
 inc h
 ld a,(hl)
 adc a,b
 ld e,a
 inc h
 ld a,(hl)
 adc a,#0
 ld d,a
 ; BC starts as the sign extension. Shifting the top sign bit into it
 ; would leave it unchanged; bit 6 supplies the final upper-word bit.
 add a,a
 sbc a,a
 ld b,a
 ld a,c
 ld c,b
 add a,a
 rl e
 rl d
 add a,a
 rl e
 rl d
 rl c
 ret
roll_component_unit:
 ld a,d
 add a,a
 sbc a,a
 ld b,a
 ld c,a
 ret
roll_component_negate:
 ; Speed is nonzero. -INT16_MIN is +32768 in the full-width output.
 ld a,d
 cpl
 add a,a
 sbc a,a
 ld b,a
 ld c,a
 xor a
 sub e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ret
roll_component_zero:
 ld de,#0
 ld bc,#0
 ret
roll_component_miss:
 ; A directory miss can have any signed16 coefficient, including -32768.
 xor a
 ld (#0x3000),a
 ld a,(#__current_bank)
 ld (#0x2000),a
 ldhl sp,#6
 call _riding_mulq14_regs
 ld b,h
 ld c,l
 ret

; DEBC holds dvn, HL points to the signed32 wheel torque. On a hit, DEBC is
; the final rolling speed delta. On a miss DEBC is preserved. Carry = hit.
_riding_roll_table_delta::
 ld a,b
 add a,a
 sbc a,a
 cp e
 jr nz,roll_table_wide
 cp d
 jr nz,roll_table_wide
 ld a,(#_riding_subphase)
 or a
 jr nz,roll_map_partial
 ld a,#roll_full_bank
 ld (#0x2000),a
 jp roll_delta_full
roll_map_partial:
 ld a,#roll_partial_bank
 ld (#0x2000),a
 jp roll_delta_partial
roll_table_wide:
 and a
 ret
roll_restore_bank:
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret

; BC=input, HL=seven coefficient planes (the base need not be page-aligned).
; Return the complete signed24 quotient sign-extended to DEBC.
roll_transform_word:
 push hl
 ld d,b
 ld b,#0
 add hl,bc
 ld e,(hl)
 inc h
 ld c,(hl)
 inc h
 ld b,(hl)
 pop hl
 ld a,d
 add l
 ld l,a
 ld a,h
 adc #3
 ld h,a
 ld a,e
 cp (hl)
 ccf
 inc h
 ld a,c
 adc (hl)
 ld c,a
 inc h
 ld a,b
 adc (hl)
 ld b,a
 inc h
 ld a,#0
 adc (hl)
 ld e,a
 add a
 sbc a
 ld d,a
 ret

; Each phase executes directly alongside its two coefficient tables.
.macro roll_phase_delta data,rows,?compose,?drop_torque,?torque_zero,?torque_gas,?table_valid,?table_sum,?table_positive,?compose_wide
 ld a,b
 add a,#roll_bias_pages
 cp #roll_pages
 jr nc,compose
 push hl
 ld a,(hl+)
 or a
 jr z,torque_zero
 cp #<roll_gas
 jr z,torque_gas
 cp #<(-roll_gas)
 jr nz,drop_torque
 ld a,(hl+)
 cp #>(-roll_gas)
 jr nz,drop_torque
 ld a,(hl+)
 and (hl)
 inc a
 jr nz,drop_torque
 ld a,#2
 jr table_valid
torque_gas:
 ld a,(hl+)
 cp #>roll_gas
 jr nz,drop_torque
 ld a,(hl+)
 or (hl)
 jr nz,drop_torque
 ld a,#1
 jr table_valid
torque_zero:
 ld a,(hl+)
 or (hl)
 inc hl
 or (hl)
 jr z,table_valid
drop_torque:
 pop hl
 jr compose
table_valid:
 pop hl
 push af
 ld a,b
 add a,#roll_bias_pages
 ld b,a
 ld hl,#data
 ld d,h
 ld e,l
 add hl,bc
 ld a,(hl)
 push af
 ; Two bytes per 32-input base, followed by independently rounded carries.
 ld a,b
 xor c
 and #15
 xor c
 swap a
 and #254
 ld l,a
 ld a,b
 swap a
 and #15
 ld h,a
 add hl,de
 ld de,#roll_data_size
 add hl,de
 pop bc
 ld a,b
 and #63
 ld c,a
 pop af
 or a
 jr z,table_sum
 dec a
 jr z,table_positive
 ld de,#(roll_group_bytes*2)
 add hl,de
 ld a,b
 rlca
 jr table_sum
table_positive:
 ld de,#roll_group_bytes
 add hl,de
 ld a,b
 rlca
 rlca
table_sum:
 ld a,c
 adc a,(hl)
 ld c,a
 inc hl
 ld a,(hl)
 adc a,#0
 ld b,a
 add a,a
 sbc a,a
 ld d,a
 ld e,a
 scf
 jp roll_restore_bank

; Reuse the phase bank for both separately rounded Q24 operations. Each byte
; of a signed16 input selects an integer contribution. A single comparison
; between the low fractional rank and high threshold supplies its exact carry.
compose:
 push bc                        ; original dvn for a wide intermediate
 push hl                        ; original torque pointer
 ld hl,#rows
 call roll_transform_word
 pop hl
 ld a,(hl+)
 add c
 ld c,a
 ld a,(hl+)
 adc b
 ld b,a
 ld a,(hl+)
 adc e
 ld e,a
 ld a,(hl)
 adc d
 ld d,a
 ld a,b
 add a
 sbc a
 cp e
 jr nz,compose_wide
 cp d
 jr nz,compose_wide
 ld hl,#(rows+7*256)
 call roll_transform_word
 pop hl
 scf
 jp roll_restore_bank
compose_wide:
 pop bc
 ld a,b
 add a
 sbc a
 ld d,a
 ld e,a
 and a
 jp roll_restore_bank
.endm

.area _CODE_14
roll_delta_full:
 roll_phase_delta roll_data_0,roll_transform_0
.area _CODE_6
roll_delta_partial:
 roll_phase_delta roll_data_1,roll_transform_1
.endif
