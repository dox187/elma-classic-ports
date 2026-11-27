; Exact grounded rolling, bank 9. The public ABI0 entry takes
; k*, contact*, dvx32, dvy32, tq32. The resolver already owns those inputs.
.module physics_roll_fast
.macro roll_axis_inputs_kernel target
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
 jp target
.endm

.macro roll_axis_value_kernel
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

.endm

.macro roll_stationary_kernel entry,banked
entry:
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
 .if banked
 jp ground_restore
 .else
 ret
 .endif
.endm

.macro roll_bank30_wheels
roll_axis_inputs_30:
 roll_axis_inputs_kernel ground_resume_deltas
 roll_axis_value_kernel
 roll_stationary_kernel roll_stationary_30,1
; The horizontal unit tangent needs only two saturated signed negations.
roll_flat_inputs:
 ld a,#3
 ldh (#near_page),a
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#8
 add hl,de
 call roll_flat_negate
 push de
 push bc
 ldhl sp,#8
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call roll_flat_negate
 jp ground_resume_deltas
roll_flat_negate:
 xor a
 sub (hl)
 ld c,a
 inc hl
 ld a,#0
 sbc (hl)
 ld b,a
 inc hl
 ld a,#0
 sbc (hl)
 ld e,a
 inc hl
 ld a,#0
 sbc (hl)
 ld d,a
 cp #128
 ret nz
 ld a,e
 or b
 or c
 ret nz
 ld de,#0x7fff
 ld bc,#0xffff
 ret
.endm

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
 .ifdef RIDING_GROUND_ROWS
 xor a
 ldh (#near_page),a
 .endif
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
 .ifdef RIDING_GROUND_ROWS
 jp nz,roll_map_flat
 .endif
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
 .ifdef RIDING_GROUND_ROWS
 jp roll_map_axis
 .else
 roll_axis_inputs_kernel roll_projected_inputs
 .endif
roll_input_dots:
 .ifdef RIDING_GROUND_ROWS
 ld a,e
 or a
 .ifdef ROLL_DIRECTORY_BANK
 jr nz,roll_check_near
 ld a,d
 cp #0xc0
 jp z,ground_try_dots
 jr roll_live_slope
roll_check_near:
 dec a
 cp #2
 jr c,roll_generic_dots
roll_live_slope:
 ; The ordinary wheel entry still has both signed tangent coefficients.
 ld hl,#rom_slope_find_regs
 ld a,#ROLL_DIRECTORY_BANK
 jp rom_slope_map
 .else
 jr nz,roll_generic_dots
 ld a,d
 cp #0xc0
 jp z,ground_try_dots
 .endif
roll_generic_dots:
 jp slope_begin_dots
roll_default_dots:
 .ifdef ROLL_DIRECTORY_BANK
 ld hl,#batch_extended_inputs
 ld a,#35
 jp rom_slope_map
roll_exact_dots:
 .endif
 .endif
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
 add #8
 ld h,(hl)
 ld l,a
 jr nc,roll_torque_address
 inc h
roll_torque_address:
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
 .ifdef RIDING_ROLL_OMEGA
 call roll_omega
 .else
 ld hl,#_q24_index_C_ROLL_W
 dec sp
 call roll_coefficient
 .endif
 ldhl sp,#10
 ld a,(hl+)
 add #20
 ld h,(hl)
 ld l,a
 jr nc,roll_omega_address
 inc h
roll_omega_address:
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
 .ifdef RIDING_GROUND_ROWS
 call near_project_select
 .else
 call _riding_roll_project_pair
 .endif
 add sp,#10
 pop hl
 jp _riding_wheel_move_hl

 .ifdef RIDING_ROLL_TABLES
.area _CODE
; The zero-speed wheel writes zero velocity and omega. Its two zero
; translations only sign-extend each residual's third byte. The omega
; coefficient (and the partial-step Y translation) publish zero Q24.
 .ifdef RIDING_GROUND_ROWS
roll_stationary:
 ld a,#30
 ld (#0x2000),a
 jp roll_stationary_30
roll_map_axis:
 ld c,a
 ld a,#30
 ld (#0x2000),a
 ld a,c
 jp roll_axis_inputs_30
roll_map_flat:
 ld a,#30
 ld (#0x2000),a
 jp roll_flat_inputs
 .else
 roll_stationary_kernel roll_stationary,0
 .endif
 .endif

; HL points at two signed32 values. Return the selected Q14 cardinal
; projection in DEBC. Negative INT32_MIN rounds to saturated INT32_MAX.
 .ifndef RIDING_GROUND_ROWS
 roll_axis_value_kernel
 .endif

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
 .ifdef RIDING_GROUND_ROWS
 ldhl sp,#8
 ld a,(hl+)
 or a
 jr nz,ground_generic_pair
 ld a,(hl+)
 cp #0xc0
 jr nz,ground_generic_pair
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 or b
 jp z,ground_flat_pair
 call ground_select
 jp nz,ground_project_29
ground_generic_pair:
 jp slope_begin_pair
 .else
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
 .ifndef RIDING_GROUND_ROWS
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
 .endif
roll_project_directory:
 ldhl sp,#8
 call roll_project_component
 ; Start the next row lookup with the ninth MBC5 bank bit clear.
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
 ldh a,(#__current_bank)
 ld (#0x2000),a
 jr roll_store_second
roll_project_zero:
 pop hl
 .rept 8
 ld (hl+),a
 .endm
 ret
 .ifndef RIDING_GROUND_ROWS
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
 ldh a,(#__current_bank)
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
 .endif
 .endif
roll_project_wide:
 .ifdef RIDING_GROUND_ROWS
 jp slope_begin_pair
roll_default_pair:
 .endif
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
 .ifndef RIDING_GROUND_ROWS
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
 push bc                        ; mirrored -32768 needs its original coefficient
 call _riding_map_projection_row
 pop bc
 jr nz,roll_component_miss
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
 ldh a,(#__current_bank)
 ld (#0x2000),a
 ldhl sp,#6
 call _riding_mulq14_regs
 ld b,h
 ld c,l
 ret

 .endif

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
 ldh a,(#__current_bank)
 ld (#0x2000),a
 ret

; Each table begins at a page boundary. The low digit supplies its integer
; contribution and fractional rank. The high digit supplies the threshold
; for rounding the full product and the remaining signed quotient.
.macro roll_phase_delta first,short,second,?large,?miss,?done
 push bc                        ; restore the original input on a wide sum
 push hl
 ld l,c
 ld h,#>first
 ld a,(hl)
 inc h
 ld c,(hl)
 inc h
 ld l,b
 cp (hl)
 ccf
 inc h
 ld a,c
 adc (hl)
 ld c,a
 inc h
 ld a,#0
 adc (hl)
 ld b,a
 add a
 sbc a
 ld e,a
 pop hl
 ld a,(hl+)
 add c
 ld c,a
 ld a,(hl+)
 adc b
 ld b,a
 ld a,(hl+)
 adc e
 ld d,a
 ld a,(hl)
 adc e
 ld e,a
 ld a,b
 add a
 sbc a
 cp d
 jr nz,miss
 cp e
 jr nz,miss
 ; For small net torques a direct signed word gives the second round.
 ld a,b
 add #4
 cp #8
 jr nc,large
 add #>short
 ld h,a
 ld l,c
 ld c,(hl)
 ld a,h
 add #8
 ld h,a
 ld a,(hl)
 ld b,a
 add a
 sbc a
 jr done
large:
 ld l,c
 ld h,#>second
 ld a,(hl)
 inc h
 ld c,(hl)
 inc h
 ld e,(hl)
 inc h
 ld l,b
 cp (hl)
 ccf
 inc h
 ld a,c
 adc (hl)
 ld c,a
 inc h
 ld a,e
 adc (hl)
 ld b,a
 inc h
 ld a,#0
 adc (hl)
done:
 ld e,a
 add a
 sbc a
 ld d,a
 pop hl
 scf
 jp roll_restore_bank
miss:
 pop bc
 ld a,b
 add a
 sbc a
 ld e,a
 ld d,a
 and a
 jp roll_restore_bank
.endm

.area _CODE_14
roll_delta_full:
 roll_phase_delta roll_first_0,roll_short_0,roll_second_0
.area _CODE_6
roll_delta_partial:
 roll_phase_delta roll_first_1,roll_short_1,roll_second_1
.endif

 .ifdef RIDING_GROUND_ROWS
.area _CODE
ground_flat_pair:
 ld a,#29
 ld (#0x2000),a
 jp ground_flat_29
ground_try_dots:
 call ground_select
 jr z,ground_dots_missed
 ldh (#near_slot),a
 ld a,#2
 ldh (#near_page),a
 ldh a,(#near_slot)
 jp ground_inputs_29
ground_dots_missed:
 jp roll_generic_dots
ground_resume_dots:
 call ground_restore
 jp roll_generic_dots
ground_resume_deltas:
 call ground_restore
 jp roll_projected_inputs
ground_resume_pair:
 call ground_restore
 jp ground_generic_pair
ground_return:
ground_restore:
 ldh a,(#__current_bank)
 ld (#0x2000),a
 ret

; On a hit, both banks have the same kernel addresses. A is the first
; product page. The directory verifies the complete signed coefficient.
ground_select:
 ld a,c
 add a
 sbc a
 cp b
 jr nz,ground_unknown
 ld a,#29
 ld (#0x2000),a
 jp ground_select_29
ground_second_bank:
 and #127
 ld l,a
 ld a,#30
 ldh (#ground_projection_bank),a
 ld (#0x2000),a
 ld a,l
 or a
 ret
ground_unknown_banked:
 jp ground_restore
ground_unknown:
 xor a
 ret
 .endif

.ifdef RIDING_ROLL_OMEGA
.area _CODE
; DEBC is the nonzero speed. The low-byte node is nonnegative, and the
; complete signed17 result fits signed16. The general multiplier handles
; wider speed inputs. Publish the identical rounded Q24 fraction on both
; substeps, including the full interval where translation leaves it live.
roll_omega::
 ld a,d
 or e
 jr z,roll_omega_positive
 ld a,d
 and e
 inc a
 jr nz,roll_omega_wide
 ld h,#(roll_omega_page+11)
 ld a,b
 inc a
 jr nz,roll_omega_map
 ld a,c
 or a
 jr z,roll_omega_map
 ld h,#(roll_omega_page+27)
 jr roll_omega_byte
roll_omega_positive:
 ld h,#(roll_omega_page+5)
 ld a,b
 or a
 jr nz,roll_omega_map
 ld h,#roll_omega_page
roll_omega_byte:
 ld a,#roll_omega_bank
 ld (#0x2000),a
 ld a,#roll_omega_high
 ld (#0x3000),a
 ld l,c
 ld a,(hl)
 ldh (#_q24_fraction),a
 inc h
 ld a,(hl)
 ldh (#_q24_fraction+1),a
 inc h
 ld a,(hl)
 xor #128
 ldh (#_q24_fraction+2),a
 rlca
 sbc a
 ldh (#_q24_fraction+3),a
 inc h
 ld c,(hl)
 inc h
 ld b,(hl)
 jr roll_omega_extend
roll_omega_wide:
 ld a,(#_q24_index_C_ROLL_W)
 dec sp
 call _q24_apply_a
 ret
roll_omega_map:
 ld a,#roll_omega_bank
 ld (#0x2000),a
 ld a,#roll_omega_high
 ld (#0x3000),a
 ld d,#roll_omega_page
 ld e,c
 ld l,b
 ld a,(de)
 ldh (#_q24_fraction),a
 inc d
 ld a,(de)
 add (hl)
 ldh (#_q24_fraction+1),a
 inc d
 inc h
 ld a,(de)
 adc (hl)
 rla
 ld b,a
 ccf
 sbc a
 ldh (#_q24_fraction+3),a
 ld a,b
 rra
 ldh (#_q24_fraction+2),a
 inc d
 inc h
 ld a,(de)
 adc (hl)
 ld c,a
 inc h
 ld a,#0
 adc (hl)
 ld b,a
roll_omega_extend:
 ld a,b
 add a
 sbc a
 ld d,a
 ld e,a
 xor a
 ldh (#_q24_saturated),a
 ld (#0x3000),a
 jp ground_restore
.endif

.macro ground_select_kernel
ground_select_29:
 ld h,#>ground_directory
 ld l,c
 ld a,(hl)
 or a
 jp z,ground_unknown_banked
 bit 7,a
 jp nz,ground_second_bank
 ld l,a
 ld a,#29
 ldh (#ground_projection_bank),a
 ld a,l
 or a
 ret
.endm
