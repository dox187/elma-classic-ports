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
 .ifdef RIDING_ROLL_TABLES
 ; For a bounded tangential impulse and the three constant wheel torques,
 ; one lookup returns exactly the two separately rounded Q24 operations.
 ; The following omega multiply publishes the last observable Q24 fraction.
 ldhl sp,#8
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push de
 ld de,#8
 add hl,de
 pop de
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
 ; Form vy first and save it so both components can be written consecutively.
 ldhl sp,#6
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#0
 call _riding_mulq14_regs
 push hl
 push de
 ldhl sp,#8
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#4
 call _riding_mulq14_regs
 ld b,h
 ld c,l
 ldhl sp,#14
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push de
 ld de,#8
 add hl,de
 pop de
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 pop de
 pop bc
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld (hl),b
 add sp,#10
 pop hl
 jp _riding_wheel_move_hl

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

.ifdef RIDING_ROLL_TABLES
.area _CODE
; DEBC holds dvn, HL points to the signed32 wheel torque. On a hit, DEBC is
; the final rolling speed delta. On a miss DEBC is preserved. Carry = hit.
_riding_roll_table_delta::
 ld a,b
 add a,a
 sbc a,a
 cp e
 jr nz,roll_table_miss
 cp d
 jr nz,roll_table_miss
 ld a,b
 add a,#roll_bias_pages
 cp #roll_pages
 jr nc,roll_table_miss
 ld a,(hl+)
 or a
 jr z,roll_torque_zero
 cp #<roll_gas
 jr z,roll_torque_gas
 cp #<(-roll_gas)
 jr nz,roll_table_miss
 ld a,(hl+)
 cp #>(-roll_gas)
 jr nz,roll_table_miss
 ld a,(hl+)
 and (hl)
 inc a
 jr nz,roll_table_miss
 ld a,#2
 jr roll_table_valid
roll_torque_gas:
 ld a,(hl+)
 cp #>roll_gas
 jr nz,roll_table_miss
 ld a,(hl+)
 or (hl)
 jr nz,roll_table_miss
 ld a,#1
 jr roll_table_valid
roll_torque_zero:
 ld a,(hl+)
 or (hl)
 inc hl
 or (hl)
 jr z,roll_table_valid
roll_table_miss:
 and a
 ret
roll_table_valid:
 push af
 ld a,b
 add a,#roll_bias_pages
 ld b,a
 ld a,(#_riding_subphase)
 or a
 jr nz,roll_table_partial
 ld hl,#roll_data_0
 ld a,#roll_full_bank
 jr roll_table_read
roll_table_partial:
 ld hl,#roll_data_1
 ld a,#roll_partial_bank
roll_table_read:
 ld (#0x2000),a
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
 jr z,roll_table_sum
 dec a
 jr z,roll_table_positive
 ld de,#(roll_group_bytes*2)
 add hl,de
 ld a,b
 rlca
 jr roll_table_sum
roll_table_positive:
 ld de,#roll_group_bytes
 add hl,de
 ld a,b
 rlca
 rlca
roll_table_sum:
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
 ld a,(#__current_bank)
 ld (#0x2000),a
 scf
 ret
.endif
