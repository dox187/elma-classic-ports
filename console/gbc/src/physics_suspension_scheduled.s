; Damping uses full Q18 arms. The reciprocal reaction uses rounded Q10 arms.
; Each force coefficient bank supplies four Q24 products. The wheels receive
; rounded impulses while the body retains their signed fractions. Both wheels
; contribute before the complete spring and damping moments are narrowed.
.module physics_suspension_scheduled
.area _DATA
; Completed work for the next full substep: 1 arms, 2 spin, 3 wheel inputs,
; 4 first moment, 5 both moments, 6 spring products, 7 damper products,
; 8 certified angular damping moment, 9 base wheel and body forces.
_riding_spring_ready:: .ds 1
ss_damping: .ds 32                 ; relx[2], rely[2], arm_x[2], arm_y[2]
ss_spin_mid: .ds 16
ss_spin_top: .ds 16
ss_product_upper: .ds 2
ss_moment: .ds 9
ss_ts: .ds 4
ss_coarse: .ds 4
ss_tr: .ds 4
ss_reaction_high: .ds 1
ss_paired: .ds 1
ss_damp_long: .ds 1                 ; 0 certified, 1 wide, 2 prepared moment
ss_prepared_damping: .ds 4
; The 18-byte split body sums and four wheel impulses are input-independent.
; Only the consumer publishes them after the next control sample.
ss_prepared_sums: .ds 18
ss_prepared_wheels: .ds 16
_riding_spring_scratch_end::

ss_wheel_dvx = 10
ss_wheel_dvy = 14
ss_wheel_tq = 18
ss_wheel_stride = 14

; Scheduled register convention is BC:DE, high word first.
; Synthetic levels share bank 8 with the generic math kernels. These near
; entries run with bank 8 already mapped, so they can also live in ROM0.
; The cartridge's table-backed layout keeps them beside the main solver.
.macro ss_near_area
 .ifdef RIDING_GAS_REACTION
 .area _CODE_8
 .else
 .area _CODE
 .endif
.endm

.macro ss_read address
 ld hl,#(address)
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
.endm
.macro ss_write address
 ld hl,#(address)
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ld (hl),c
 inc hl
 ld (hl),b
.endm
; These callers have consumed A. The incrementing store keeps BC:DE intact.
.macro ss_store address
 ld hl,#(address)
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld (hl),b
.endm
.macro ss_sub address
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
; R = memory - R. Useful for body_velocity - (wheel_velocity + spin).
.macro ss_reverse_sub_hl
 ld a,(hl+)
 sub a,e
 ld e,a
 ld a,(hl+)
 sbc a,d
 ld d,a
 ld a,(hl+)
 sbc a,c
 ld c,a
 ld a,(hl)
 sbc a,b
 ld b,a
.endm
.macro ss_reverse_sub address
 ld hl,#(address)
 ss_reverse_sub_hl
.endm
.macro ss_add address
 ld hl,#(address)
 ld a,(hl+)
 add a,e
 ld e,a
 ld a,(hl+)
 adc a,d
 ld d,a
 ld a,(hl+)
 adc a,c
 ld c,a
 ld a,(hl)
 adc a,b
 ld b,a
.endm
; Add the contribution to the wheel while keeping the same value in
; registers for the opposite body force.
.macro ss_accumulate address
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
.macro ss_negate
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ld a,#0
 sbc a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
.endm
; Q24 native ABI is DE:BC. The register entry consumes one scratch stack
; byte after its return address. The shuffle preserves the index in A.
.macro ss_q24
 dec sp
 ld h,b
 ld l,c
 ld b,d
 ld c,e
 ld d,h
 ld e,l
 call _q24_apply_a
 ld h,b
 ld l,c
 ld b,d
 ld c,e
 ld d,h
 ld e,l
.endm
.macro ss_q24_phase coefficient,selected
 ld hl,#coefficient
 ld a,(#_riding_subphase)
 or a
 jr z,selected
 inc hl
selected:
 ld a,(hl)
 ss_q24
.endm
; Both source addresses are known. Read their difference one digit at a
; time, keeping only the result in registers. INC HL preserves borrow.
.macro ss_delta32 left,right
 ld hl,#(right)
 ld a,(#(left))
 sub (hl)
 ld e,a
 inc hl
 ld a,(#(left+1))
 sbc (hl)
 ld d,a
 inc hl
 ld a,(#(left+2))
 sbc (hl)
 ld c,a
 inc hl
 ld a,(#(left+3))
 sbc (hl)
 ld b,a
.endm
.macro ss_arm body,wheel,destination
 ld hl,#(_Bike+body)
 .irp digit,0,1,2,3
 ld a,(#(_Bike+wheel+digit))
 .if digit
 sbc (hl)
 .else
 sub (hl)
 .endif
 ld (#(destination+digit)),a
 .if digit-3
 inc hl
 .endif
 .endm
.endm
; The native table products are (raw + 2^23) = integer*2^24 + biased.
; The wheel uses only the integer. The body gets both pieces, and four
; such biased fractions per axis account for exactly two whole units.
; Add the unsigned fractions before subtracting them from the residual.
; HRAM loads leave both the register sum and its carry live across digits.
.macro ss_add_fraction product
 ldh a,(ss_force_products+product)
 add a,e
 ld e,a
 ldh a,(ss_force_products+product+1)
 adc a,d
 ld d,a
 ldh a,(ss_force_products+product+2)
 adc a,c
 ld c,a
 ld a,b
 adc a,#0
 ld b,a
.endm

.macro ss_force_fraction pair,axis,sums,live
 ld hl,#(ss_force_products+pair)
 ldh a,(ss_force_products+pair+7)
 add a,(hl)
 ld e,a
 inc l
 ldh a,(ss_force_products+pair+8)
 adc a,(hl)
 ld d,a
 inc l
 ldh a,(ss_force_products+pair+9)
 adc a,(hl)
 ld c,a
 ld a,#0
 rla
 ld b,a
 ss_add_fraction pair+28
 ss_add_fraction pair+35
 ld hl,#(_force_residual+axis*8)
 ld a,(hl)
 sub a,e
 .if live
 ld (hl+),a
 .else
 inc hl
 .endif
 ld e,a
 ld a,(hl)
 sbc a,d
 .if live
 ld (hl+),a
 .else
 inc hl
 .endif
 ld d,a
 ld a,(hl)
 sbc a,c
 .if live
 ld (hl),a
 .endif
 ld c,a
 ld a,#2
 sbc a,b
 ld b,a
 ss_store sums+axis*9
.endm

; Return a full signed33 spring+damper in A:BCDE and publish its wrapped
; low 32 bits for the wheel. Carry out of bit 31 and both operand signs
; determine byte 4, including for oppositely signed products.
.macro ss_force_pair product,destination,positive,?spring_positive
 ld hl,#(ss_force_products+product+3)
 ldh a,(ss_force_products+product+28+3)
 add a,(hl)
 ld e,a
 inc l
 ldh a,(ss_force_products+product+28+4)
 adc a,(hl)
 ld d,a
 inc l
 ldh a,(ss_force_products+product+28+5)
 adc a,(hl)
 ld c,a
 inc l
 ldh a,(ss_force_products+product+28+6)
 adc a,(hl)
 ld b,a
 ld a,#0
 rla
 bit 7,(hl)
 jr z,spring_positive
 dec a
spring_positive:
 ld l,#<(ss_force_products+product+28+6)
 bit 7,(hl)
 jr z,positive
 dec a
positive:
 ss_write _riding_suspension_state+destination
.endm

.macro ss_force_wide_axis pair,axis,first_pos,second_pos
 ss_force_pair pair,ss_wheel_dvx+axis*4,first_pos
 ld h,a
 ld a,(#_force_residual+axis*8+7)
 sub a,h
 push af
 ss_reverse_sub _force_residual+axis*8+3
 pop hl
 ld a,h
 sbc a,#0
 push af
 push bc
 push de

 ss_force_pair pair+7,ss_wheel_dvx+axis*4+ss_wheel_stride,second_pos
 push af
 ; Stack now has the second sign, the first difference in two words,
 ; and its fifth byte in the A slot of the final saved AF.
 ldhl sp,#2
 ld a,(hl+)
 sub a,e
 ld e,a
 ld a,(hl+)
 sbc a,d
 ld d,a
 ld a,(hl+)
 sbc a,c
 ld c,a
 ld a,(hl+)
 sbc a,b
 ld b,a
 inc hl
 ld a,(hl)
 sbc a,#0
 pop hl
 sub a,h
 ld (#_riding_force_sums+axis*9+8),a
 ss_write _riding_force_sums+axis*9+4
 add sp,#6
.endm
; All fast inputs lie in [-2^21,2^21) with coefficients in [0,1].
; Three sum bytes cover both rounded wheel terms, including carries across
; bit 15. The fourth wheel byte is the sign extension of their true sum.
.macro ss_narrow_force_pair product,destination
 ld hl,#(ss_force_products+product+3)
 ldh a,(ss_force_products+product+28+3)
 add a,(hl)
 ld e,a
 inc l
 ldh a,(ss_force_products+product+28+4)
 adc a,(hl)
 ld d,a
 inc l
 ldh a,(ss_force_products+product+28+5)
 adc a,(hl)
 ld c,a
 add a,a
 sbc a,a
 ld b,a
 ss_store destination
.endm

.macro ss_narrow_force_axis pair,axis,sums,wheel0,wheel1
 ss_narrow_force_pair pair,wheel0
 push de
 ss_narrow_force_pair pair+7,wheel1
 pop hl
 add hl,de
 ld a,(#wheel0+2)
 adc a,c
 ld c,a
 add a,a
 sbc a,a
 ld b,a
 ; HL and C hold the summed signed24 wheel impulse. The saved B sign
 ; extends through both remaining digits of the original signed40 residue.
 ld d,h
 ld e,l
 ld hl,#(_force_residual+axis*8+3)
 ld a,(hl+)
 sub a,e
 ld e,a
 ld a,(hl+)
 sbc a,d
 ld d,a
 ld a,(hl+)
 sbc a,c
 ld c,a
 ld a,(hl+)
 sbc a,b
 ld h,(hl)
 ld l,a
 ld a,h
 sbc a,b
 ld (#sums+axis*9+8),a
 ld b,l
 ss_store sums+axis*9+4
.endm

; Divide the integer force and the signed carry from the fractional sum. The
; register divider supplies a Euclidean remainder and a wrapped HL:DE quotient.
.macro ss_finish_force axis
 ; Fraction subtraction has already stored the three Euclidean digits.
 ld hl,#(_riding_force_sums+axis*9+3)
 ld a,(hl+)
 add a,#10
 add a,(hl)
 ld e,a
 inc hl
 ld a,(hl+)
 adc a,#0
 ld d,a
 ld a,(hl+)
 adc a,#0
 ld c,a
 ld a,(hl+)
 adc a,#0
 ld b,a
 ld a,(hl)
 adc a,#0
 call _riding_force_divmod20
 ld b,h
 ld c,l
 sub a,#10
 ld hl,#(_force_residual+axis*8+3)
 ld (hl+),a
 add a,a
 sbc a,a
 .rept 3
 ld (hl+),a
 .endm
 ld (hl),a
 ss_store _riding_suspension_state+36+axis*4
.endm

.macro ss_reaction_product arm
 ld hl,#(ss_coarse+arm)
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 call ss_reaction_q14
 ld b,h
 ld c,l
.endm
; In the ordinary range, split the two signed operands into unsigned
; low words and upper digits of zero or -1. The unsigned row product
; is corrected by the anchor at bit 16 and the displacement at bit 24.
.macro ss_raw_product label,arm,disp,rows,fold,?upper_arm,?arm_done,?positive_arm,?positive_disp,?upper_disp,?maybe_neg,?have_middle,?rows_done
.area _CODE_8
label:
 ld hl,#arm
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld b,(hl)
 ldh a,(disp)
 ld c,a
 jp rows
fold:
 ; Byte zero is stacked. D,C,B,E hold unsigned product bytes 1..4.
 ld a,(#arm+3)
 or a
 jr z,positive_arm
 inc a
 jr nz,upper_arm
 ld hl,#disp
 ld a,b
 sub a,(hl)
 ld b,a
 inc hl
 ld a,e
 sbc a,(hl)
 ld e,a
 sbc a,a
positive_arm:
 ld l,e                        ; byte four
 ld h,a                        ; byte five
arm_done:
 ldh a,(disp+2)
 inc a
 jr z,maybe_neg
 dec a
 jr nz,upper_disp
 ldh a,(disp+3)
 or a
 jr z,positive_disp
 jr upper_disp
maybe_neg:
 ldh a,(disp+3)
 inc a
 jr nz,upper_disp
 push de
 ld d,h
 ld e,l
 ld hl,#arm
 ld a,c
 sub a,(hl)
 ld c,a
 inc hl
 ld a,b
 sbc a,(hl)
 ld b,a
 inc hl
 ld a,e
 sbc a,(hl)
 ld e,a
 inc hl
 ld a,d
 sbc a,(hl)
 ld h,a
 ld l,e
 pop de
positive_disp:
 ld a,d
 pop de
 ld d,a
 ret
upper_arm:
 ld hl,#disp
 call ss_spring_extend_arm
 jr arm_done
upper_disp:
 push de
 push hl
 push bc
 ld hl,#(disp+2)
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 ld hl,#arm
 call ss_spring_upper_disp
 pop bc
 pop hl
 pop de
 jr positive_disp

.area _CODE
rows:
 call _riding_product24x8_row
 push de                       ; final byte zero
 ldh a,(disp+1)
 or a
 jr nz,have_middle
 ld e,a
 jr rows_done
have_middle:
 .ifdef RIDING_GAS_REACTION
 ld l,a
 ld h,#>_riding_scale_directory
 ld a,(hl)
 ld (#0x2000),a
 inc h
 ld h,(hl)
 .else
 ld h,a
 call ss_damp_map
 .endif
 ld a,(#arm)
 ld l,a
 ld a,(hl)
 add a,d
 ld d,a
 inc h
 ld a,(hl)
 adc a,c
 ld c,a
 ld a,(#arm+1)
 ld l,a
 ld a,(hl)
 adc a,b
 ld b,a
 ld a,#0
 rla
 ld e,a
 dec h
 ld a,(hl)
 add a,c
 ld c,a
 ld a,(#arm+2)
 call ss_spring_last_digit
rows_done:
 ldh a,(#__current_bank)
 ld (#0x2000),a
 jp fold
.area _CODE_8
.endm

.macro ss_spring_pair first,second
 call first
 push hl
 push bc
 push de
 call second
 call ss_spring_difference
 add sp,#6
.endm
; The four spring displacements occupy the future damper-product rows.
; The spring batch consumes all four before the damper batch fills its rows.
.macro ss_displacement_axis anchor,arm,destination
 ld hl,#(ss_damping+arm)
 .irp digit,0,1,2,3
 ld a,(#(_riding_pose_anchor+anchor+digit))
 .if digit
 sbc (hl)
 .else
 sub (hl)
 .endif
 ldh (#(ss_force_products+destination+digit)),a
 .if digit-3
 inc hl
 .endif
 .endm
.endm
.macro ss_wheel_displacement offset
 ss_displacement_axis offset,(16+offset),(28+offset)
 ss_displacement_axis (8+offset),(24+offset),(36+offset)
.endm
.macro ss_wheel_spring offset
 .if offset
 ss_spring_pair ss_spring_x1,ss_spring_y1
 .else
 ss_spring_pair ss_spring_x0,ss_spring_y0
 .endif
 .if offset
 ss_accumulate ss_ts
 .else
 ss_write ss_ts
 .endif
.endm
.macro ss_wheel_relative_velocity wheel,offset
 ; The spin workspace becomes the relative velocity. Subtract the same
 ; unsigned words modulo 2^32 in place, retaining the original X/Y signs.
 ss_delta32 (_Bike+8),(_Bike+wheel+8)
 ld hl,#(ss_damping+offset)
 ld a,e
 sub (hl)
 ld (hl+),a
 ld a,d
 sbc (hl)
 ld (hl+),a
 ld a,c
 sbc (hl)
 ld (hl+),a
 ld a,b
 sbc (hl)
 ld (hl),a
 ss_delta32 (_Bike+12),(_Bike+wheel+12)
 ss_accumulate ss_damping+8+offset
.endm
.macro ss_wheel_reaction offset,record,next_wheel,reaction_index,ordinary,have_reaction
 ; Round coarse arms only when this wheel has a reaction torque.
 ld hl,#_riding_suspension_state+ss_wheel_tq+record
 ld a,(hl+)
 or a,(hl)
 inc hl
 or a,(hl)
 inc hl
 or a,(hl)
 jp z,next_wheel
 ld hl,#ss_damping+24+offset
 call ss_coarse_arm
 ld hl,#ss_coarse+2
 ld (hl),e
 inc hl
 ld (hl),d
 push de
 ld hl,#ss_damping+16+offset
 call ss_coarse_arm
 ld hl,#ss_coarse
 ld (hl),e
 inc hl
 ld (hl),d
 push de
 ss_read _riding_suspension_state+ss_wheel_tq+record
 push bc
 push de
 .ifdef RIDING_GAS_REACTION
 call _riding_gas_reaction
 jr nc,ordinary
 add sp,#8
 jr have_reaction
ordinary:
 .endif
 call ss_reaction_input
 add sp,#8
 ld b,h
 ld c,l
 ss_q24_phase _q24_index_C_REACT,reaction_index
 .ifdef RIDING_GAS_REACTION
have_reaction:
 .endif
 call ss_prepare_reaction
 ss_reaction_product 2
 ss_accumulate _riding_suspension_state+ss_wheel_dvx+record
 xor a
 call _riding_force_sub_integer_regs
 ss_reaction_product 0
 ss_negate
 ss_accumulate _riding_suspension_state+ss_wheel_dvy+record
 ld a,#1
 call _riding_force_sub_integer_regs
.endm

.area _CODE_8
; The source state belongs to the single main-thread Bike. Reset, turn and
; level/menu transitions revoke the prefix. Between two completed updates
; controls only set wheel torque before suspension. Volts run afterwards.
; The producer writes private suspension scratch. The consumer owns all
; state updates, including Q24 fractions, wheel torques and audio flags.
.globl b_physics_prepare_spring
b_physics_prepare_spring = 8
_physics_prepare_spring::
 ldhl sp,#6                      ; GBDK banked stack ABI
 ld a,(hl+)
 ld d,(hl)
 ld e,a                         ; next-input deadline is start + 2
 ld a,#13                       ; complete lines required by geometry
 call _riding_spring_budget
 ret nc
 push de
 call _riding_spring_geometry
 ld a,#1
 jp c,ss_prepared_wide
 inc a
 ld (#_riding_spring_ready),a
 pop de
 ld a,#6                        ; displacements, relative speeds and symmetry
 call _riding_spring_budget
 ret nc
 push de
 call ss_wheel_values
 call ss_try_mirrored
 pop de
 jr z,ss_prepared_moments
 ld a,#3
 ld (#_riding_spring_ready),a
 ld a,#10                       ; first wheel, including the wide product
 call _riding_spring_budget
 ret nc
 push de
 call ss_first_moment
 pop de
 ld a,#4
 ld (#_riding_spring_ready),a
 ld a,#10                       ; second wheel and sum
 call _riding_spring_budget
 ret nc
 push de
 call ss_second_moment
 pop de
ss_prepared_moments:
 ld a,#5
 ld (#_riding_spring_ready),a
 ld a,#6
 call _riding_spring_budget
 ret nc
 push de
 call _riding_prepare_spring_products
 pop de
 ret c
 ld a,#6
 ld (#_riding_spring_ready),a
 ld a,#6
 call _riding_spring_budget
 ret nc
 push de
 call _riding_prepare_damper_products
 pop de
 ret c
 ld a,#7
 ld (#_riding_spring_ready),a
 ; The two equal springs require no angular force. For the certified
 ; four-term case every relative speed has already supplied its wheel
 ; force. Its final consumer can run in the remaining idle interval.
 ld a,(#ss_paired)
 or a
 ret nz
 ld a,(#ss_damp_long)
 or a
 ret nz
 ld a,#12                       ; 8,908 T plus two reserved LCD lines
 call _riding_spring_budget
 ret nc
 push de
 call ss_damp_cert_entry
 ld b,h
 ld c,l
 ss_store ss_prepared_damping
 ld a,#2
 ld (#ss_damp_long),a
 ld a,#8
 ld (#_riding_spring_ready),a
 pop de
 ldh a,(ss_force_wide_used)
 or a
 ret nz
 ld a,#5                        ; 2,208 T plus two reserved LCD lines
 call _riding_spring_budget
 ret nc
 ld e,#15
 ld hl,#ss_prepare_base_forces
 call ___sdcc_bcall_ehl
 ld a,#9
 ld (#_riding_spring_ready),a
 ret
ss_prepared_wide:
 ld (#_riding_spring_ready),a
 pop de
 ret

; CGB runs 912 CPU T-cycles per LCD line. A visible LY below the cutoff
; leaves the complete lines through 143. LY=144..153 leaves a full visible
; frame. Refuse pending VBlank or a changing LY during the epoch snapshot.
; check_spring_prepare.py walks every reachable SM83 branch of each block.
; The budgets reserve two full lines for guard, bank return, frame counter
; and entry to the normal wait. Only VBlank interrupts run during gameplay.
_riding_spring_budget::
 ld b,a
 ldh a,(#0x44)
 ld c,a
 ld a,(#_sys_time)
 sub a,e
 ld l,a
 ld a,(#_sys_time+1)
 sbc a,d
 ld h,a
 ldh a,(#0x0f)
 rra
 jr c,ss_prepare_late
 ldh a,(#0x44)
 cp a,c
 jr nz,ss_prepare_late
 ld a,h
 or a
 ret nz
 ld a,l
 or a
 jr z,ss_prepare_ok
 dec a
 jr nz,ss_prepare_late
 ld a,c
 cp a,#144
 jr nc,ss_prepare_ok
 ld a,#143
 sub a,c
 cp a,b
 jr c,ss_prepare_late
ss_prepare_ok:
 scf
 ret
ss_prepare_late:
 or a
 ret

_riding_spring_geometry::
 ld e,#b_body_oms
 ld hl,#_body_oms
 call ___sdcc_bcall_ehl
 ld hl,#_riding_suspension_state+4
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld a,e
 ld (hl+),a
 ld (hl),d
 ss_arm 0,24,ss_damping+16
 ss_arm 0,48,ss_damping+20
 ss_arm 4,28,ss_damping+24
 ss_arm 4,52,ss_damping+28
 jp ss_spin_narrow

_riding_spring_inputs::
 call ss_wheel_values
 jp ss_spring_total
ss_wheel_values:
 ss_wheel_displacement 0
 ss_wheel_displacement 4
 ss_wheel_relative_velocity 24,0
 ss_wheel_relative_velocity 48,4
 ret

; At a level pose both wheel springs often have identical vertical
; displacement and opposite horizontal anchors. With no horizontal
; displacement their unshifted moments are P and -P. The sum of the
; two floors is zero when P is divisible by 4096, and -1 otherwise.
ss_spring_total:
 call ss_try_mirrored
 ret z
ss_both_moments:
 call ss_first_moment
ss_second_moment:
 ss_wheel_spring 4
 ret
ss_first_moment:
 ss_wheel_spring 0
 ret

; Z means both moments were committed. A miss leaves ss_ts untouched.
ss_try_mirrored:
 xor a
 ld (#ss_paired),a
 ld (#ss_damp_long),a
 ldh (ss_force_wide_used),a
 ld hl,#ss_force_products+28
 ld a,(hl+)
 or a,(hl)
 ret nz
 .rept 6
 inc hl
 or a,(hl)
 .endm
 ret nz
 ld hl,#ss_force_products+40
 .irp offset,0,1,2,3
 ld a,(#ss_force_products+36+offset)
 cp a,(hl)
 ret nz
 .if offset-3
 inc hl
 .endif
 .endm
 ; Compare the sum in all four bytes. Constrain one top byte to 00/ff
 ; to exclude the wrapped equality INT32_MIN + INT32_MIN = 0.
 ld a,(#_riding_pose_anchor+3)
 inc a
 and a,#0xfe
 ret nz
 ld hl,#_riding_pose_anchor+4
 ld a,(#_riding_pose_anchor)
 add a,(hl)
 ret nz
 .irp offset,1,2,3
 inc hl
 ld a,(#_riding_pose_anchor+offset)
 adc a,(hl)
 ret nz
 .endm
 ; A shared set bit among bits 0..5 puts both trailing-zero counts
 ; below six. Otherwise count the factors of two in the low 12 bits.
 ld hl,#ss_force_products+36
 ld a,(#_riding_pose_anchor)
 and a,(hl)
 and a,#63
 jr nz,ss_spring_mirror_fraction
 call ss_spring_twos
 ld b,a
 ld hl,#_riding_pose_anchor
 call ss_spring_twos
 add a,b
 cp a,#12
 sbc a,a
 jr ss_spring_mirror_write
ss_spring_mirror_fraction:
 ld a,#0xff
ss_spring_mirror_write:
 ld hl,#ss_ts
 .rept 4
 ld (hl+),a
 .endm
 ; The spring displacements are (0,0,y,y) and the actual X arms equal
 ; their opposite pose anchors. Matching damping speeds give the same
 ; vertical impulse to both wheels and an exactly cancelling damping moment.
 ld hl,#ss_damping
 ld a,(hl+)
 .rept 6
 or a,(hl)
 inc hl
 .endm
 or a,(hl)
 jr nz,ss_mirror_done
 ld hl,#ss_damping+12
 .irp offset,0,1,2,3
 ld a,(#ss_damping+8+offset)
 cp a,(hl)
 jr nz,ss_mirror_done
 .if offset-3
 inc hl
 .endif
 .endm
 ld a,#1
 ld (#ss_paired),a
ss_mirror_done:
 xor a
 ret

; Count trailing zeros up to twelve using the first nonzero nibble.
ss_spring_twos:
 ld a,(hl+)
 ld e,a
 and a,#15
 ld c,#0
 jr nz,ss_spring_nibble
 ld a,e
 swap a
 and a,#15
 ld c,#4
 jr nz,ss_spring_nibble
 ld a,(hl)
 and a,#15
 ld c,#8
ss_spring_nibble:
 ld e,a
 ld d,#0
 ld hl,#ss_spring_nibble_twos
 add hl,de
 ld a,(hl)
 add a,c
 ret
ss_spring_nibble_twos:
 .db 4,0,1,0,2,0,1,0,3,0,1,0,2,0,1,0

; Preparation is always for the first subphase of the next riding update.
; Its predecessor can leave riding_subphase set to the fractional interval.
_riding_prepare_spring_products::
 ld a,(#_q24_index_C_SPRING_FW)
 ld hl,#ss_force_products+28
 ld de,#ss_force_products
 jp ss_force_try
_riding_prepare_damper_products::
 ld a,(#_q24_index_C_FRIC_W)
 ld hl,#ss_damping
 ld de,#ss_force_products+28
 jp ss_force_try

_riding_suspension_scheduled::
 ld hl,#_riding_spring_ready
 ld a,(hl)
 or a
 jr z,ss_need_geometry
 ld (hl),#0
 ld b,a
 ld a,(#_riding_subphase)
 or a
 jr nz,ss_need_geometry
 dec b
 jr z,ss_need_wide
 dec b
 jr z,ss_need_inputs
 dec b
 jr z,ss_need_both_moments
 dec b
 jr z,ss_need_second_moment
 dec b
 jr z,ss_have_inputs
 dec b
 jr z,ss_have_spring_products
 ld a,b
 cp #3
 jr nz,ss_have_products
 call ss_publish_base_forces
 jr ss_reactions
ss_need_both_moments:
 call ss_both_moments
 jr ss_have_inputs
ss_need_second_moment:
 call ss_second_moment
 jr ss_have_inputs
ss_need_geometry:
 call _riding_spring_geometry
 jr nc,ss_need_inputs
ss_need_wide:
 call ss_spin_full
ss_need_inputs:
 call _riding_spring_inputs
ss_have_inputs:
 ld hl,#_q24_index_C_SPRING_FW
 ld a,(#_riding_subphase)
 or a
 jr z,ss_spring_selected
 inc hl
ss_spring_selected:
 ld a,(hl)
 ld hl,#ss_force_products+28
 ld de,#ss_force_products
 call ss_force_four
ss_have_spring_products:
 ld hl,#_q24_index_C_FRIC_W
 ld a,(#_riding_subphase)
 or a
 jr z,ss_damper_selected
 inc hl
ss_damper_selected:
 ld a,(hl)
 ld hl,#ss_damping
 ld de,#ss_force_products+28
 call ss_force_four
ss_have_products:
 ld a,(#ss_paired)
 or a
 jr z,ss_general_forces
 ld e,#15
 ld hl,#ss_paired_forces
 call ___sdcc_bcall_ehl
 jp ss_reactions
ss_general_forces:
 call ss_general_force_sums
ss_reactions:
 ss_wheel_reaction 0,0,ss_wheel1,ss_reaction0_index,ss_ordinary0,ss_reaction_ready0
ss_wheel1:
 ss_wheel_reaction 4,ss_wheel_stride,ss_wheels_done,ss_reaction1_index,ss_ordinary1,ss_reaction_ready1
ss_wheels_done:
 ss_finish_force 0
 ss_finish_force 1
 ld a,(#ss_paired)
 or a
 jr z,ss_angular_forces
 ; The paired spring moment is zero or -1 before rounding by 2^10.
 ; Both rounded angular forces and both signed Q24 fractions are zero.
 xor a
 ld hl,#_riding_suspension_state+44
 .rept 4
 ld (hl+),a
 .endm
 ld hl,#_q24_fraction
 .rept 4
 ld (hl+),a
 .endm
 ld (#_q24_saturated),a
 ss_read _angular_residual
 jp _riding_step_commit_fraction_regs
ss_angular_forces:
 ld hl,#ss_ts+1
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 sra c
 rr d
 rr e
 sra c
 rr d
 rr e
 jr nc,ss_spring_rounded
 inc de
 ld a,d
 or a,e
 jr nz,ss_spring_rounded
 inc c
ss_spring_rounded:
 ld a,c
 add a,a
 sbc a,a
 ld b,a
 ss_q24_phase _q24_index_C_SPRING_T,ss_c_spring_t_index
 ss_negate
 push bc
 push de
 ; Consume the spring fraction before damping reuses the Q24 result.
 ss_delta32 _angular_residual,_q24_fraction
 push bc
 push de
 call ss_damping_scheduled
 ld b,h
 ld c,l
 ss_q24_phase _q24_index_C_FRIC_T,ss_c_fric_t_index
 ldhl sp,#4
 ss_reverse_sub_hl
 ss_store _riding_suspension_state+44
 pop de
 pop bc
 add sp,#4
 ss_sub _q24_fraction
 jp _riding_step_commit_fraction_regs

.macro ss_join_nibbles low,high,out
 ld a,low
 xor a,high
 and a,#0x0f
 xor a,low
 swap a
 ld out,a
.endm
; Subtract the two full products before flooring this wheel's Q12 moment.
 ss_raw_product ss_spring_x0,_riding_pose_anchor,ss_force_products+36,ss_spring_x0_rows,ss_spring_x0_fold
 ss_raw_product ss_spring_y0,_riding_pose_anchor+8,ss_force_products+28,ss_spring_y0_rows,ss_spring_y0_fold
 ss_raw_product ss_spring_x1,_riding_pose_anchor+4,ss_force_products+40,ss_spring_x1_rows,ss_spring_x1_fold
 ss_raw_product ss_spring_y1,_riding_pose_anchor+12,ss_force_products+32,ss_spring_y1_rows,ss_spring_y1_fold
ss_spring_difference:
 push hl
 ldhl sp,#4
 ld a,(hl+)
 sub a,e
 ld a,(hl+)
 sbc a,d
 pop de
 push af
 ld a,(hl+)
 sbc a,c
 ld c,a
 ld a,(hl+)
 sbc a,b
 ld b,a
 ld a,(hl+)
 sbc a,e
 ld e,a
 ld a,(hl)
 sbc a,d
 ld d,a
 pop af
 ld h,a
 ss_join_nibbles e,d,l
 ss_join_nibbles b,e,d
 ss_join_nibbles c,b,e
 ss_join_nibbles h,c,h
 ld c,d
 ld d,e
 ld e,h
 ld b,l
 ret

ss_near_area
ss_prepare_reaction:
 ss_write ss_tr
 ; tr = (int16_t)tr + H*65536. Cache H once for both axes.
 ld a,d
 add a,a
 ld a,c
 adc a,#0
 ld c,a
 ld a,b
 adc a,#0
 or a
 ld a,c
 jr z,ss_reaction_high_ready
 ld a,#255
ss_reaction_high_ready:
 ld (#ss_reaction_high),a
 ret

; round(tr*arm/16384) = round((int16_t)tr*arm/16384) + 4*H*arm.
; For H=1..3 and a signed12 arm the complete sum fits signed16.
; All other widths take the original full signed48 product.
ss_reaction_q14:
 ld a,(#ss_reaction_high)
 or a
 jr z,ss_reaction_q14_word
 cp a,#4
 jr nc,ss_reaction_q14_wide
 ld e,a
 ld a,b
 add a,#8
 cp a,#16
 jr nc,ss_reaction_q14_wide
 ld h,b
 ld l,c
 dec e
 jr z,ss_reaction_q14_scale
 add hl,hl
 dec e
 jr z,ss_reaction_q14_scale
 add hl,bc
ss_reaction_q14_scale:
 add hl,hl
 add hl,hl
 push hl
 call ss_reaction_q14_word
 pop hl
 add hl,de
 ld d,h
 ld e,l
 ld a,h
 add a,a
 sbc a,a
 ld h,a
 ld l,a
 ret
ss_reaction_q14_word:
 ld hl,#ss_tr
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 jp _riding_q14_word_regs
ss_reaction_q14_wide:
 ld hl,#ss_tr
 jp _riding_mulq14_regs

ss_coarse_arm:
 ; The low byte supplies the rounding carry. If the top result byte is
 ; not the sign extension of D, the original signed32 selects the clamp.
 ld a,(hl+)
 add a,a
 ld a,(hl+)
 adc a,#0
 ld e,a
 ld a,(hl+)
 adc a,#0
 ld d,a
 ld a,(hl)
 adc a,#0
 ld b,a
 ld a,d
 add a,a
 sbc a,a
 cp a,b
 ret z
 bit 7,(hl)
 ld de,#0x7fff
 ret z
 ld de,#0x8000
 ret

; Ordinary braking torque typically fits signed16. In this range the
; full product fits signed32, so Q8 is exactly its upper three bytes.
; The original input routine handles close separation and wide torque.
ss_reaction_input:
 ldhl sp,#3
 ld a,(hl+)
 add a,a
 sbc a,a
 cp (hl)
 jp nz,_riding_reaction_input32
 inc hl
 cp (hl)
 jp nz,_riding_reaction_input32
 inc hl
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 call _riding_recip_index_regs
 ld a,e
 cp #16
 jp c,_riding_reaction_input32
 ld l,e
 ld h,#0
 add hl,hl
 ld de,#_Recip_d2
 add hl,de
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ldhl sp,#2
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 call _riding_mul16_regs
 ld e,d
 ld d,l
 ld l,h
 ld a,h
 add a,a
 sbc a,a
 ld h,a
 ret
.area _CODE_8
; HL -> signed32 arm, DE -> signed32 speed. Return all 64 product bits in
; ss_product_upper:BC:HL:DE. Most speeds need just one signed32 x signed16
; product. The ROM0 multiplier restores the caller bank after table reads.
ss_lever_product:
 push hl
 ld a,(de)
 inc de
 ld c,a
 ld a,(de)
 inc de
 ld b,a
 ld a,(de)
 inc de
 ld l,a
 ld a,(de)
 ld h,a
 ; speed = signed_low + 65536 * (signed_high + signbit(low)).
 bit 7,b
 jr z,ss_check_speed_high
 inc hl
 ld a,h
 xor a,#0x80
 or a,l
 jr z,ss_positive_32768
ss_check_speed_high:
 ld a,h
 or a,l
 jr nz,ss_wide_speed
 pop hl
 call _riding_product32x16_regs
 ld a,b
 add a,a
 sbc a,a
 ld (#ss_product_upper),a
 ld (#ss_product_upper+1),a
 ret

ss_positive_32768:
 ; The adjusted high digit is +32768. Double the full 16384 product.
 push bc
 ld bc,#16384
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call _riding_product32x16_regs
 sla e
 rl d
 rl l
 rl h
 rl c
 rl b
 jr ss_combine_products
ss_wide_speed:
 push bc
 ld b,h
 ld c,l
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call _riding_product32x16_regs
ss_combine_products:
 push bc
 push hl
 push de
 ldhl sp,#6
 ld c,(hl)
 inc hl
 ld b,(hl)
 inc hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call _riding_product32x16_regs
 ; Add high_product << 16 to the sign-extended low_product.
 ld a,b
 add a,a
 sbc a,a
 ld (#ss_product_upper),a
 ld (#ss_product_upper+1),a
 push de
 ld d,h
 ld e,l
 ldhl sp,#2
 ld a,(hl+)
 add a,e
 ld e,a
 ld a,(hl+)
 adc a,d
 ld d,a
 ld a,(hl+)
 adc a,c
 ld c,a
 ld a,(hl+)
 adc a,b
 ld b,a
 ld a,(#ss_product_upper)
 adc a,(hl)
 inc hl
 ld (#ss_product_upper),a
 ld a,(#ss_product_upper+1)
 adc a,(hl)
 ld (#ss_product_upper+1),a
 ld h,d
 ld l,e
 pop de
 add sp,#10
 ret

; A nonzero top anchor digit other than -1 contributes signed8*unsigned16
; at byte three. The common case never allocates this temporary partial.
ss_spring_extend_arm:
 push de
 push hl
 ld h,#0
 ld l,e
 push hl
 push bc
 dec a
 ld c,a
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 call ss_spring_upper_arm
 pop bc
 pop hl
 add sp,#2
 pop de
 ret

; Add signed8(C)*unsigned16(DE) at byte three of the caller's partial.
; The unsigned product needs subtracting the low word at bit eight when
; C is negative. Both corrections are performed modulo 24 bits.
.area _CODE
ss_spring_upper_arm:
 push de
 push bc
 ld b,#0
 call ss_byte_positive
 ld a,c
 pop hl
 bit 7,l
 pop hl
 jr z,ss_upper_arm_add
 ld b,a
 ld a,d
 sub a,l
 ld d,a
 ld a,b
 sbc a,h
ss_upper_arm_add:
 ld c,a
 ldhl sp,#3
 ld a,(hl)
 add a,e
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld (hl+),a
 ld a,(hl)
 adc a,c
 ld (hl),a
 ret

.area _CODE_8
; Add the low 32 bits of A * signed16(D>>16) to bytes two through five.
; The unsigned low digit uses four anchor bytes, the signed upper digit
; needs only three. The two discarded top bytes cannot affect the moment.
ss_spring_upper_disp:
 ld a,b
 or a
 jr z,ss_upper_disp_byte
 inc a
 jr nz,ss_upper_disp_word
 ld a,c
 cpl
 inc a
 jr z,ss_upper_disp_word
 ld c,a
 call ss_upper_disp_byte_row
 ldhl sp,#2
 ld a,(hl)
 sub a,e
 ld (hl+),a
 ld a,(hl)
 sbc a,d
 ld (hl+),a
 ld a,(hl)
 sbc a,c
 ld (hl+),a
 ld a,(hl)
 sbc a,b
 ld (hl),a
 ret
ss_upper_disp_byte:
 call ss_upper_disp_byte_row
 ldhl sp,#2
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
 ret
.area _CODE
ss_upper_disp_byte_row:
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld b,a
 ld a,(hl)
 dec c
 jr nz,ss_upper_disp_more
 ld c,b
 ld b,a
 ret
ss_upper_disp_more:
 dec c
 jr nz,ss_upper_disp_table
 ld c,b
 ld b,a
 sla e
 rl d
 rl c
 rl b
 ret
ss_upper_disp_table:
 inc c
 inc c
 jp ss_spring_u32_row
.area _CODE_8
ss_upper_disp_word:
 push hl
 ld e,#15
 ld hl,#ss_spring_upper_disp_wide
 call ___sdcc_bcall_ehl
 add sp,#2
 ret
.area _CODE_15
ss_spring_upper_disp_wide:
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl                        ; anchor
 push bc                        ; word multiplier
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld b,a
 ld a,(hl)
 call ss_spring_u32_row
 ldhl sp,#14
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
 pop bc
 pop hl
 ld c,b
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld b,(hl)
 push de
 push bc
 call ss_byte_positive
 pop hl
 bit 7,l
 pop hl
 jr z,ss_upper_disp_add
 ld a,d
 sub a,l
 ld d,a
 ld a,c
 sbc a,h
 ld c,a
ss_upper_disp_add:
 ldhl sp,#11
 ld a,(hl)
 add a,e
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld (hl+),a
 ld a,(hl)
 adc a,c
 ld (hl),a
 ret

.area _CODE
ss_spring_last_digit:
 ld l,a
 ld a,(hl)
 adc a,b
 ld b,a
 inc h
 ld a,(hl)
 adc a,e
 ld e,a
 ret
ss_spring_u32_row:
 push af
 call _riding_product24x8_row
 pop af
 ld l,a
 dec h                          ; low product plane of the same row
 ld a,(hl)
 add a,b
 ld b,a
 jp ss_mt_product_done
.area _CODE_8

; The four products share omega. For signed24 operands write it as
; lo + 256*mid + 65536*top, with a signed top byte. Each byte selects a
; multiplication-table bank just once for all four independent arms.
; A wide operand falls back synchronously. No wide spin is ever started
; during the optional geometry block. Carry reports the deferred work.
ss_spin_four:
 call ss_spin_narrow
 ret nc
 jp ss_spin_full
ss_spin_defer:
 scf
 ret
ss_spin_narrow:
 ld hl,#_riding_suspension_state+4
 ld a,(hl+)
 or a,(hl)
 inc hl
 or a,(hl)
 inc hl
 or a,(hl)
 jr nz,ss_spin_nonzero
 ld hl,#ss_damping
 .rept 16
 ld (hl+),a
 .endm
 or a
 ret
ss_spin_nonzero:
 dec hl
 ld a,(hl+)
 add a,a
 sbc a,a
 cp a,(hl)
 jp nz,ss_spin_defer
.macro ss_arm_width offset
 ld hl,#ss_damping+16+offset+2
 ld a,(hl+)
 add a,a
 sbc a,a
 cp a,(hl)
 jp nz,ss_spin_defer
.endm
 ss_arm_width 0
 ss_arm_width 4
 ss_arm_width 8
 ss_arm_width 12
 ; Each signed24 arm times a digit in [-255,255] fits signed32.
 ; Use one table row for either sign, including at rounding boundaries.
 ld hl,#_riding_suspension_state+5
 ld a,(hl+)
 or a,(hl)
 jr z,ss_spin_positive_digit
 ld a,(hl-)
 and a,(hl)
 inc a
 jr nz,ss_spin_unsigned_rows
 ld a,(#_riding_suspension_state+4)
 cpl
 inc a
 jr z,ss_spin_unsigned_rows      ; -256 still needs two digits
 ld b,#0x80
 jr ss_spin_short
ss_spin_positive_digit:
 ld a,(#_riding_suspension_state+4)
 ld b,#0
ss_spin_short:
 cp a,#3
 jp c,ss_spin_unit
 push bc
 ld de,#ss_damping
 call ss_spin_rows
 pop bc
 .irp offset,0,4,8,12
 ld hl,#ss_damping+offset
 call ss_spin_reduce_byte
 .endm
 or a
 ret
ss_spin_unsigned_rows:
 ld a,(#_riding_suspension_state+4)
 ld de,#ss_damping
 call ss_spin_rows
 ; A negative high digit below 65536 in magnitude can be subtracted
 ; directly. This saves four full arm subtractions after the merge.
 ld a,(#_riding_suspension_state+6)
 inc a
 jr nz,ss_spin_middle_unsigned
 ld a,(#_riding_suspension_state+5)
 or a
 jp nz,ss_spin_negative_middle
ss_spin_middle_unsigned:
 ld a,(#_riding_suspension_state+5)
 ld de,#ss_spin_mid
 call ss_spin_rows
 ld a,(#_riding_suspension_state+6)
 or a
 jr z,ss_spin_top_ready
 inc a
 jr z,ss_spin_top_ready
 dec a
 bit 7,a
 jr z,ss_spin_top_digit
 cpl
 inc a
ss_spin_top_digit:
 ld de,#ss_spin_top
 call ss_spin_rows
ss_spin_top_ready:
 ; L and M are signed32 rows. Their first two product bytes affect only
 ; the carry into floor((L + 256*M) / 65536). The remaining result of
 ; this unsigned16 by signed24 product fits signed24, including minima.
.macro ss_spin_merge label,offset,arm
label:
 ld hl,#ss_spin_mid+offset
 ld a,(#ss_damping+offset+1)
 add a,(hl)
 inc hl
 ld a,(#ss_damping+offset+2)
 adc a,(hl)
 ld e,a
 inc hl
 ld a,(#ss_damping+offset+3)
 adc a,(hl)
 ld d,a
 inc hl
 ; Sign of L equals sign of its arm when lo is nonzero. Use the
 ; actual high bit of L to cover a zero low row as well.
 ld a,(#ss_damping+offset+3)
 bit 7,a
 ld a,#0
 jr z,001$
 dec a
001$:
 adc a,(hl)
 ld c,a
 add a,a
 sbc a,a
 ld b,a
 ld a,(#_riding_suspension_state+6)
 or a
 jr z,004$
 inc a
 jr nz,002$
 ss_sub ss_damping+arm
 jr 004$
002$:
 ld a,(#_riding_suspension_state+6)
 bit 7,a
 jr z,005$
 ss_sub ss_spin_top+offset
 jr 004$
005$:
 ss_add ss_spin_top+offset
004$:
 ; Round the full signed product once after the Q18 shift.
 sra b
 rr c
 rr d
 rr e
 sra b
 rr c
 rr d
 rr e
 jr nc,006$
 inc de
 ld a,d
 or a,e
 jr nz,006$
 inc bc
006$:
 ss_write ss_damping+offset
.endm
 ss_spin_merge ss_merge_0,0,24
 ss_spin_merge ss_merge_4,4,28
 ss_spin_merge ss_merge_8,8,16
 ss_spin_merge ss_merge_12,12,20
 or a
 ret

ss_near_area
ss_spin_negative_middle:
 cpl
 inc a
 ld de,#ss_spin_mid
 call ss_spin_rows
 ; P = lo*arm - 256*abs(mid)*arm. Byte zero cannot borrow.
 ; The signed24 floor(P/65536) fits because abs(omega)<65536.
 .macro ss_spin_subtract_lane offset,?nonnegative,?rounded
 ld hl,#ss_spin_mid+offset
 ld a,(#ss_damping+offset+1)
 sub (hl)
 inc hl
 ld a,(#ss_damping+offset+2)
 sbc (hl)
 ld e,a
 inc hl
 ld a,(#ss_damping+offset+3)
 sbc (hl)
 ld d,a
 inc hl
 ld a,(#ss_damping+offset+3)
 bit 7,a
 ld a,#0
 jr z,nonnegative
 dec a
nonnegative:
 sbc (hl)
 ld c,a
 sra c
 rr d
 rr e
 sra c
 rr d
 rr e
 jr nc,rounded
 inc de
 ld a,d
 or e
 jr nz,rounded
 inc c
rounded:
 ld a,c
 add a,a
 sbc a,a
 ld b,a
 ss_store ss_damping+offset
 .endm
 .irp i,0,4,8,12
 ss_spin_subtract_lane i
 .endm
 or a
 ret

.area _CODE_8
; For omega +/-1 or +/-2, use each arm directly. Bit 7 of B records
; the sign and bit 0 selects the 17-bit shift for a magnitude of two.
ss_spin_unit:
 dec a
 or a,b
 ld b,a
 ld hl,#ss_damping+24
 ld de,#ss_damping
 call ss_spin_unit_lane
 call ss_spin_unit_lane
 ld hl,#ss_damping+16
 call ss_spin_unit_lane
 call ss_spin_unit_lane
 or a
 ret

; A signed24 arm shifted by at least 17 bits rounds to a signed byte.
ss_spin_unit_lane:
 bit 7,b
 jr nz,ss_spin_unit_negative
 inc hl
 inc hl
 ld a,(hl+)
 inc hl
 sra a
 jr ss_spin_unit_last
ss_spin_unit_negative:
 ld a,(hl+)
 or a,(hl)
 inc hl
 sub a,#1
 ld a,(hl+)
 cpl
 adc a,#0
 ld c,a
 ld a,(hl+)
 cpl
 adc a,#0
 rra
 ld a,c
 rra
ss_spin_unit_last:
 bit 0,b
 jr nz,ss_spin_unit_round
 sra a
ss_spin_unit_round:
 adc a,#0
 ld (de),a
 inc de
 add a,a
 sbc a,a
 .rept 3
 ld (de),a
 inc de
 .endm
 ret

; Round the signed32 table product in place. For a negative multiplier,
; the high half of -P is ~high + (low == 0), including at a Q18 tie.
ss_spin_reduce_byte:
 bit 7,b
 jr nz,ss_spin_negate_high
 inc hl
 inc hl
 ld a,(hl+)
 ld c,a
 ld a,(hl)
 jr ss_spin_shift_byte
ss_spin_negate_high:
 ld a,(hl+)
 or a,(hl)
 inc hl
 sub a,#1
 ld a,(hl+)
 cpl
 adc a,#0
 ld c,a
 ld a,(hl)
 cpl
 adc a,#0
ss_spin_shift_byte:
 sra a
 rr c
 sra a
 rr c
 jr nc,ss_spin_emit_byte
 inc c
 jr nz,ss_spin_emit_byte
 inc a
ss_spin_emit_byte:
 ld d,a
 add a,a
 sbc a,a
 ld (hl-),a
 ld (hl-),a
 ld (hl),d
 dec hl
 ld (hl),c
 ret
ss_spin_full:
.macro ss_spin_fallback offset,arm
 ld hl,#ss_damping+arm
 ld de,#_riding_suspension_state+4
 call ss_lever_spin18
 ld b,h
 ld c,l
 ss_write ss_damping+offset
.endm
 ss_spin_fallback 0,24
 ss_spin_fallback 4,28
 ss_spin_fallback 8,16
 ss_spin_fallback 12,20
 ret

; Return clamp32((speed * arm + 2^17) >> 18) in HLDE.
ss_lever_spin18:
 ; A signed16 speed produces a signed48 product, which always fits signed32
 ; after the Q18 shift. Zero is frequent when the bike is at rest.
 push hl
 ld h,d
 ld l,e
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 add a,a
 sbc a,a
 cp a,(hl)
 jr nz,ss_spin_wide
 inc hl
 cp a,(hl)
 jr nz,ss_spin_wide
 pop hl
 ld a,b
 or a,c
 jr z,ss_spin_zero
 call _riding_product32x16_regs
 sra b
 rr c
 rr h
 rr l
 sra b
 rr c
 rr h
 rr l
 ld d,h
 ld e,l
 ld h,b
 ld l,c
 ret nc
 inc de
 ld a,d
 or a,e
 ret nz
 inc hl
 ret
ss_spin_zero:
 ld hl,#0
 ld de,#0
 ret
ss_spin_wide:
 pop hl
 call ss_lever_product
 ld a,l
 add a,#2
 ld e,a
 ld a,h
 adc a,#0
 ld d,a
 ld a,c
 adc a,#0
 ld l,a
 ld a,b
 adc a,#0
 ld h,a
 ld a,(#ss_product_upper)
 adc a,#0
 ld c,a
 ld a,(#ss_product_upper+1)
 adc a,#0
 ld b,a
 add a,a
 sbc a,a
 jp ss_reduce18

; Add or subtract one signed24 by signed24 product. With a wider input,
; extend the partial sum and let the wide routine finish the remaining terms.
.macro ss_moment_term label,speed,arm,subtract,partial,wide
label:
 ld hl,#ss_damping+speed
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld d,a
 add a,a
 sbc a,a
 cp a,(hl)
 .if partial
 jp nz,004$
 .else
 jp nz,wide
 .endif
 ld a,c
 or a,b
 or a,d
 .if partial
 jr z,006$
 .else
 jp z,ss_mt_first_zero
 .endif
 bit 7,d
 jr z,001$
 xor a
 sub a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
 ld a,#0
 sbc a,d
 ld d,a
001$:
 ld e,b
 push de
 ld hl,#ss_damping+arm
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld b,a
 add a,a
 sbc a,a
 cp a,(hl)
 jr nz,003$
 pop hl
 ld a,b
 or a
 jr nz,007$
 ld a,d
 or a,e
 .if partial
 jr z,006$
 .else
 jp z,ss_mt_first_zero
 .endif
007$:
 ld a,(#ss_damping+speed+3)
 xor a,b
 push af
 bit 7,b
 jr z,002$
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ld a,#0
 sbc a,b
 ld b,a
002$:
 call ss_mt_product
 pop af
 bit 7,a
 .if subtract
 jr z,005$
 .else
 jr nz,005$
 .endif
 .if partial
 call ss_magnitude_add
 .else
 call ss_mt_seed_positive
 .endif
 jr 006$
003$:
 pop hl
 .if partial
004$:
 ld hl,#ss_moment+6
 ld a,(hl+)
 add a,a
 sbc a,a
 ld (hl+),a
 ld (hl),a
 .endif
 jp wide
005$:
 .if partial
 call ss_magnitude_sub
 .else
 call ss_mt_seed_negative
 .endif
006$:
.endm

.area _CODE_15
; The first product seeds all seven accumulator bytes, including its sign.
ss_mt_first_zero:
 xor a
 ld hl,#ss_moment
 .rept 7
 ld (hl+),a
 .endm
 jp ss_mt_mid_y0
ss_mt_seed_positive:
 push hl
 ld hl,#ss_moment
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 pop de
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 xor a
 ld (hl),a
 ret
ss_mt_seed_negative:
 push hl
 ld hl,#ss_moment
 xor a
 sub a,e
 ld (hl+),a
 ld a,#0
 sbc a,d
 ld (hl+),a
 pop de
 ld a,#0
 sbc a,e
 ld (hl+),a
 ld a,#0
 sbc a,d
 ld (hl+),a
 ld a,#0
 sbc a,c
 ld (hl+),a
 ld a,#0
 sbc a,b
 ld (hl+),a
 sbc a,a
 ld (hl),a
 ret

.area _CODE_8
.macro ss_damp_fold low,high,first,minus
 .if first
 .if minus
 ld h,a
 ss_negate
 ld a,#0
 sbc a,h
 .endif
 ld (#ss_moment+4),a
 ss_store ss_moment
 .else
 ld h,a
 push hl
 ld hl,#ss_moment
 ld a,(hl)
 low a,e
 ld (hl+),a
 ld a,(hl)
 high a,d
 ld (hl+),a
 ld a,(hl)
 high a,c
 ld (hl+),a
 ld a,(hl)
 high a,b
 ld (hl+),a
 pop de
 ld a,(hl)
 high a,d
 ld (hl),a
 .endif
.endm

ss_damping_scheduled:
 ld a,(#ss_damp_long)
 or a
 jr z,ss_damp_cert_entry
 dec a
 jp z,ss_damping_torque18
 ss_read ss_prepared_damping
 ld h,b
 ld l,c
 ret
ss_damp_cert_entry:
 ; Each axis of a rotated pose anchor has magnitude at most
 ; 222822 + 157286 + 2. Adding the certified spring displacement
 ; (magnitude <= 2^17) leaves a signed20 wheel arm. Each individual
 ; product has magnitude below 2^36. The exact four-term sum fits
 ; signed40 even when the two horizontal speeds are merged.
 ld hl,#ss_damping+28
 .irp j,0,1,2,3
 ld a,(#ss_damping+24+j)
 cp a,(hl)
 jr nz,ss_cert_normal
 .if j-3
 inc hl
 .endif
 .endm
 ld hl,#ss_damping
 .irp j,0,1,2,3
 ld a,(#ss_damping+4+j)
 .ifeq j
 add a,(hl)
 .else
 adc a,(hl)
 .endif
 ld (hl+),a
 .endm
 xor a
 .rept 4
 ld (hl+),a
 .endm
ss_cert_normal:
.macro ss_damp_term label,speed,arm,minus,first,next,word,?ready,?two,?tables,?fold,?reverse,?zero,?large
label:
 ld hl,#ss_damping+speed+2
 ld a,(hl-)
 inc a
 cp #2
 jp nc,large
 dec a
 ld a,(hl-)
 ld c,(hl)
 jr z,ready
 ld d,a
 xor a
 sub a,c
 ld c,a
 ld a,#0
 sbc a,d
 jp nc,large
ready:
 ld l,a
 or c
 .if first
 jp z,zero
 .else
 jp z,next
 .endif
 ld a,(#ss_damping+arm)
 ld e,a
 ld a,(#ss_damping+arm+1)
 ld d,a
 ld a,(#ss_damping+arm+2)
 ld b,a
 ld a,l
 or a
 jr nz,two
 call ss_byte_product
 ld a,b
 add a,a
 sbc a,a
 jr fold
two:
 dec a
 jr nz,tables
 call ss_short_word
 jr fold
tables:
 call word
fold:
 ld hl,#ss_damping+speed+2
 bit 7,(hl)
 .if minus
 jr z,reverse
 .else
 jr nz,reverse
 .endif
 ss_damp_fold add,adc,first,0
 jp next
reverse:
 ss_damp_fold sub,sbc,first,1
 jp next
 .if first
zero:
 xor a
 ld hl,#ss_moment
 .rept 5
 ld (hl+),a
 .endm
 jr next
 .endif
large:
 ; A third magnitude digit contributes at byte two of the product.
 ld hl,#ss_damping+speed
 ld de,#ss_damping+arm
 call ss_damp_three_digit
 jr fold
.endm
 ss_damp_term ss_damp_x0,8,16,0,1,ss_damp_y0,ss_damp_word0
 ss_damp_term ss_damp_y0,0,24,1,0,ss_damp_x1,ss_damp_word1
 ss_damp_term ss_damp_x1,12,20,0,0,ss_damp_y1,ss_damp_word2
 ss_damp_term ss_damp_y1,4,28,1,0,ss_damp_terms_done,ss_damp_word3
ss_damp_terms_done:
 jp ss_short_finish
; The speed magnitude in H:L:C and the arm magnitude in B:DE share the
; unsigned 24-bit product. Restore the arm sign for the caller's fold.
ss_damp_three_digit:
 push de
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld b,(hl)
 bit 7,b
 jr z,ss_damp_speed_magnitude
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ld a,#0
 sbc a,b
 ld b,a
ss_damp_speed_magnitude:
 push bc
 push de
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld b,a
 bit 7,b
 jr z,ss_damp_arm_magnitude
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ld a,#0
 sbc a,b
 ld b,a
ss_damp_arm_magnitude:
 pop hl
 ld c,l
 ld l,h
 pop af
 ld h,a
 call ss_mt_product
 ; Product in BC:HL:DE. The arm sign remains in memory.
 ld a,c
 ld b,h
 ld c,l
 pop hl
 inc hl
 inc hl
 bit 7,(hl)
 jr z,ss_damp_product_ready
 ld h,a
 ss_negate
 ld a,#0
 sbc a,h
ss_damp_product_ready:
 ret

; Return clamp32(sum(arm_x * rely - arm_y * relx) >> 18) in HLDE.
; The signed24 path preserves every fractional bit. A wider operand transfers
; the existing partial sum to the nine-byte accumulator before its product.
ss_damping_torque18:
 ; Both horizontal speeds must vanish for these two zero cases. Either
 ; all speeds vanish, or equal vertical speeds act on opposite x arms.
 ld hl,#ss_damping
 ld a,(hl+)
 or a,(hl)
 jr nz,ss_mt_general
 inc hl
 .rept 6
 or a,(hl)
 inc hl
 .endm
 jr nz,ss_mt_general
 ld a,(hl+)
 or a,(hl)
 inc hl
 or a,(hl)
 inc hl
 or a,(hl)
 inc hl
 jr nz,ss_mt_vertical
 .rept 3
 or a,(hl)
 inc hl
 .endm
 or a,(hl)
 jr nz,ss_mt_general
ss_mt_zero:
 ld hl,#0
 ld de,#0
 ret
ss_mt_vertical:
 ; Compare both full-width vertical speeds.
 ld hl,#ss_damping+8
 ld de,#ss_damping+12
 .rept 4
 ld a,(de)
 inc de
 cp a,(hl)
 jr nz,ss_mt_general
 inc hl
 .endm
 ; Opposite signs exclude the same-sign pair INT_MIN, INT_MIN.
 ld hl,#ss_damping+19
 ld a,(#ss_damping+23)
 xor a,(hl)
 bit 7,a
 jr z,ss_mt_general
 ld hl,#ss_damping+20
 ld a,(#ss_damping+16)
 add a,(hl)
 jr nz,ss_mt_general
 inc hl
 ld a,(#ss_damping+17)
 adc a,(hl)
 jr nz,ss_mt_general
 inc hl
 ld a,(#ss_damping+18)
 adc a,(hl)
 jr nz,ss_mt_general
 inc hl
 ld a,(#ss_damping+19)
 adc a,(hl)
 jr z,ss_mt_zero
ss_mt_general:
 ; Equal vertical arms combine the two horizontal terms before multiplication.
 ; The top-byte bound keeps the signed sum within int32. These velocities
 ; are private scratch and their last consumer is this damping moment.
 ld hl,#ss_damping+28
 .irp i,0,1,2,3
 ld a,(#ss_damping+24+i)
 cp a,(hl)
 jr nz,ss_mt_unmerged
 .if i-3
 inc hl
 .endif
 .endm
 ld a,(#ss_damping+3)
 inc a
 cp a,#2
 jr nc,ss_mt_unmerged
 ld a,(#ss_damping+7)
 inc a
 cp a,#2
 jr nc,ss_mt_unmerged
 ld hl,#ss_damping
 .irp i,0,1,2,3
 ld a,(#ss_damping+4+i)
 .ifeq i
 add a,(hl)
 .else
 adc a,(hl)
 .endif
 ld (hl+),a
 .endm
 xor a
 .rept 4
 ld (hl+),a
 .endm
ss_mt_unmerged:
; A signed22 arm times a speed magnitude below 65536 has magnitude below
; 2^37. Four terms fit signed40. Extend the partial sum to signed56 when
; transferring to the first term whose operands exceed those bounds.
.macro ss_short_term label,speed,arm,minus,first,wide,next,readword,?positive,?ready,?word,?addterm,?slow
label:
 ld hl,#ss_damping+speed+2
 ld a,(hl+)
 cp a,(hl)
 jr nz,slow
 or a
 jr z,positive
 inc a
 jr nz,slow
 ld hl,#ss_damping+speed
 xor a
 sub a,(hl)
 ld c,a
 inc hl
 ld a,#0
 sbc a,(hl)
 jr nc,slow                     ; -65536
 jr ready
positive:
 dec hl
 dec hl
 ld a,(hl-)
 ld c,(hl)
ready:
 ld d,a                         ; high digit of the speed magnitude
 ld hl,#ss_damping+arm+3
 ld a,(hl-)
 or a
 jr z,002$
 inc a
 jr nz,slow
 ld a,(hl-)
 cp a,#224
 jr c,slow
 jr 003$
002$:
 ld a,(hl-)
 cp a,#32
 jr nc,slow
003$:
 ld b,a
 ld a,(hl-)
 ld e,(hl)
 ld l,d
 ld d,a
 ld a,l
 or a
 jr nz,word
 ld a,c
 or a
 .if first
 jp z,ss_short_zero
 .else
 jp z,next
 .endif
 call ss_byte_product
 ld a,b
 add a,a
 sbc a,a
 jr addterm
word:
 dec a
 jr nz,004$
 call ss_short_word
 jr addterm
004$:
 call readword
addterm:
 ld hl,#ss_damping+speed+3
 bit 7,(hl)
 .if minus
 jr z,001$
 .else
 jr nz,001$
 .endif
 .if first
 call ss_short_seed
 .else
 call ss_short_add
 .endif
 jr next
001$:
 .if first
 call ss_short_negative_seed
 .else
 call ss_short_sub
 .endif
 jr next
slow:
 .ifeq first
 ld hl,#ss_moment+4
 ld a,(hl+)
 add a,a
 sbc a,a
 ld (hl+),a
 ld (hl),a
 .endif
 jp wide
.endm
 ss_short_term ss_short_x0,8,16,0,1,ss_mt_x0,ss_short_y0,ss_damp_word0
 ss_short_term ss_short_y0,0,24,1,0,ss_mt_y0,ss_short_x1,ss_damp_word1
 ss_short_term ss_short_x1,12,20,0,0,ss_mt_x1,ss_short_y1,ss_damp_word2
 ss_short_term ss_short_y1,4,28,1,0,ss_mt_y1,ss_short_finish,ss_damp_word3
ss_short_finish:
 ld hl,#ss_moment+2
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld l,(hl)
 ld a,l
 add a,a
 sbc a,a
 ld h,a
 jp ss_shift18
ss_short_zero:
 xor a
 ld hl,#ss_moment
 .rept 5
 ld (hl+),a
 .endm
 jp ss_short_y0
ss_short_word:
 bit 7,b
 jr z,ss_short_unsigned
 ld h,l
 ld l,c
 push hl
 ld l,h
 call ss_spring_rows
 ld b,c
 ld c,l
 ld a,h
 pop hl
 sub a,l
 ld l,a
 ld a,b
 sbc a,h
 ld b,l
 ret
ss_short_unsigned:
 call ss_spring_rows
 ld a,c
 ld b,h
 ld c,l
 ret
ss_short_negative_seed:
 ld h,a
 ss_negate
 ld a,#0
 sbc a,h
ss_short_seed:
 ld (#ss_moment+4),a
 ss_write ss_moment
 ret
.macro ss_short_fold label,lo,hi
label:
 push af
 ld hl,#ss_moment
 ld a,(hl)
 lo a,e
 ld (hl+),a
 ld a,(hl)
 hi a,d
 ld (hl+),a
 ld a,(hl)
 hi a,c
 ld (hl+),a
 ld a,(hl)
 hi a,b
 ld (hl+),a
 pop de
 ld a,(hl)
 hi a,d
 ld (hl),a
 ret
.endm
 ss_short_fold ss_short_add,add,adc
 ss_short_fold ss_short_sub,sub,sbc

; The first four positive scalars need no table reads or bank changes.
ss_byte_product:
 ld a,c
 cp a,#4
 jr z,ss_byte_four
 jp nc,ss_byte_table
 dec a
 jr z,ss_byte_one
 dec a
 jr z,ss_byte_two
 ; 3*arm = 2*arm + arm. Both addends have the original sign above
 ; bit 23, and the last byte addition supplies the carry into bit 24.
 ld h,d
 ld l,e
 add hl,hl
 ld a,b
 rla
 ld c,a
 add hl,de
 ld a,c
 adc a,b
 ld c,a
 ld a,#0
 bit 7,b
 jr z,ss_byte_triple_high
 ld a,#0xfe
ss_byte_triple_high:
 adc a,#0
 ld b,a
 ld d,h
 ld e,l
 ret
ss_byte_one:
 ld c,b
 ld a,b
 add a,a
 sbc a,a
 ld b,a
 ret
ss_byte_four:
 ld h,d
 ld l,e
 add hl,hl
 rl b
 sbc a,a
 add hl,hl
 rl b
 rla
 ld c,b
 ld b,a
 ld d,h
 ld e,l
 ret
ss_byte_two:
 sla e
 rl d
 rl b
 ld c,b
 sbc a,a
 ld b,a
 ret

; A width miss transfers the remaining terms together. Both the signed56
; and signed72 paths leave a sign-extended result in the same accumulator.
ss_mt_x0:
 ld hl,#ss_mt_mid_x0
 jr ss_damp_remaining
ss_mt_y0:
 ld hl,#ss_mt_mid_y0
 jr ss_damp_remaining
ss_mt_x1:
 ld hl,#ss_mt_mid_x1
 jr ss_damp_remaining
ss_mt_y1:
 ld hl,#ss_mt_mid_y1
ss_damp_remaining:
 ld e,#15
 call ___sdcc_bcall_ehl
 ld hl,#ss_moment+2
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld a,(hl+)
 ld b,(hl)
 ld l,a
 ld h,b
 ld a,(#ss_moment+6)
 ld c,a
 ld a,(#ss_moment+7)
 ld b,a
 ld a,(#ss_moment+8)
 jp ss_reduce18

.area _CODE_15
 ; Four signed24 products of magnitude at most 2^46 fit a signed56
 ; accumulator, and their Q18 result fits signed32 without saturation.
 ss_moment_term ss_mt_mid_x0,8,16,0,0,ss_moment_wide
 ss_moment_term ss_mt_mid_y0,0,24,1,1,ss_mt_wide_term1
 ss_moment_term ss_mt_mid_x1,12,20,0,1,ss_mt_wide_term2
 ss_moment_term ss_mt_mid_y1,4,28,1,1,ss_mt_wide_term3
 ld hl,#ss_moment+6
 ld a,(hl+)
 add a,a
 sbc a,a
 ld (hl+),a
 ld (hl),a
 ret

; A wide operand still uses at most four byte-table rows. Fold each exact
; magnitude into the signed nine-byte sum before moving to the next term.
ss_moment_wide:
 xor a
 ld hl,#ss_moment
 .rept 9
 ld (hl+),a
 .endm
.macro ss_mt_wide label,speed,arm,subtraction
label:
 ld hl,#ss_damping+speed
 ld de,#ss_damping+arm
 .if subtraction
 ld a,#0x80
 .else
 xor a
 .endif
 call ss_mt_wide_mac
.endm
 ss_mt_wide ss_mt_wide_term0,8,16,0
 ss_mt_wide ss_mt_wide_term1,0,24,1
 ss_mt_wide ss_mt_wide_term2,12,20,0
 ss_mt_wide ss_mt_wide_term3,4,28,1
 ret

.area _CODE_8
ss_reduce18:
 ; A:BC is the signed upper portion above the four result bytes (HLDE).
 ; Two final right shifts fit signed32 exactly when A:BC is -2..1.
 or a,a
 jr nz,ss_reduce_negative
 ld a,b
 or a,a
 jr nz,ss_max32
 ld a,c
 cp a,#2
 jr nc,ss_max32
 jr ss_shift18
ss_reduce_negative:
 bit 7,a
 jr z,ss_max32
 inc a
 jr nz,ss_min32
 ld a,b
 inc a
 jr nz,ss_min32
 ld a,c
 cp a,#0xfe
 jr c,ss_min32
ss_shift18:
 sra a
 rr h
 rr l
 rr d
 rr e
 sra a
 rr h
 rr l
 rr d
 rr e
 ret
ss_min32:
 ld hl,#0x8000
 ld de,#0
 ret
ss_max32:
 ld hl,#0x7fff
 ld de,#0xffff
 ret

.macro ss_add_low48
 push hl
 ld hl,#ss_moment
 ld a,(hl)
 add a,e
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld (hl+),a
 pop de
 ld a,(hl)
 adc a,e
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld (hl+),a
 ld a,(hl)
 adc a,c
 ld (hl+),a
 ld a,(hl)
 adc a,b
 ld (hl+),a
.endm
.macro ss_sub_low48
 push hl
 ld hl,#ss_moment
 ld a,(hl)
 sub a,e
 ld (hl+),a
 ld a,(hl)
 sbc a,d
 ld (hl+),a
 pop de
 ld a,(hl)
 sbc a,e
 ld (hl+),a
 ld a,(hl)
 sbc a,d
 ld (hl+),a
 ld a,(hl)
 sbc a,c
 ld (hl+),a
 ld a,(hl)
 sbc a,b
 ld (hl+),a
.endm

.area _CODE_15
; Source pointers are consumed while copying their unsigned magnitudes.
; Zero and INT32_MIN both fit this representation.
ss_mt_abs_copy:
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 bit 7,b
 ret z
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
 ld a,#0
 sbc a,c
 ld c,a
 ld a,#0
 sbc a,b
 ld b,a
 ret

ss_mt_skip_arm:
 add sp,#4
 ret

ss_mt_wide_mac:
 push af
 push de
 call ss_mt_abs_copy
 ld a,(hl)
 ss_write ss_spin_mid+4
 ld h,a
 ld a,b
 or a,c
 or a,d
 or a,e
 jr z,ss_mt_skip_arm
 ld a,h
 pop hl
 push af
 call ss_mt_abs_copy
 ld a,(hl)
 ld l,a
 ld a,b
 or a,c
 or a,d
 or a,e
 jr z,ss_mt_skip_arm
 ld a,l
 pop hl
 xor a,h
 pop hl
 xor a,h
 push af
 ss_write ss_spin_mid
 xor a
 ld hl,#ss_spin_top
 .rept 8
 ld (hl+),a
 .endm
 call ss_mt_wide_rows
 pop af
 bit 7,a
 ld de,#ss_spin_top
 ld hl,#ss_moment
 jr nz,ss_mt_fold_sub
 or a
 .rept 8
 ld a,(de)
 adc a,(hl)
 ld (hl+),a
 inc de
 .endm
 ret nc
 inc (hl)
 ret
ss_mt_fold_sub:
 or a
 .rept 8
 ld a,(de)
 ld c,a
 ld a,(hl)
 sbc a,c
 ld (hl+),a
 inc de
 .endm
 ret nc
 dec (hl)
 ret

ss_magnitude_add:
 ss_add_low48
 ret nc
 inc (hl)
 ret
ss_magnitude_sub:
 ss_sub_low48
 ret nc
 dec (hl)
 ret

.area _CODE_8
; A is an unsigned omega digit, DE points to four signed32 row results.
ss_spin_rows:
 or a
 jr nz,ss_spin_select
 ld h,d
 ld l,e
 .rept 16
 ld (hl+),a
 .endm
 ret
ss_spin_select:
 ld c,a
 and a,#31
 add a,a
 or a,#>_physics_scale_planes_36
 ld h,a
 ld a,c
 rlca
 rlca
 rlca
 and a,#7
 add a,#36
 jp ss_spin_rows_mapped

.area _CODE
; Read the same two pages for all four arms. B is the carry byte between
; successive digits, and C retains the row multiplier for sign correction.
.macro ss_spin_row label,arm
 ld a,(#ss_damping+arm)
 ld l,a
 ld a,(hl)
 ld (de),a
 inc de
 inc h
 ld b,(hl)
 ld a,(#ss_damping+arm+1)
 ld l,a
 dec h
 ld a,(hl)
 add a,b
 ld (de),a
 inc de
 inc h
 ld a,(hl)
 adc a,#0
 ld b,a
 ld a,(#ss_damping+arm+2)
 ld l,a
 dec h
 ld a,(hl)
 add a,b
 ld (de),a
 inc de
 inc h
 ld a,(hl)
 adc a,#0
 bit 7,l
 jr z,label
 ; A negative arm is unsigned_low24 - 2^24.
 sub a,c
label:
 ld (de),a
 inc de
 dec h
.endm
ss_spin_rows_mapped:
 ld (#0x2000),a
 ss_spin_row ss_spin_row_y0,24
 ss_spin_row ss_spin_row_y1,28
 ss_spin_row ss_spin_row_x0,16
 ss_spin_row ss_spin_row_x1,20
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret

; The low speed digit seeds the accumulator in BC:DE. Add the upper
; digit's three 16-bit products directly at offsets 1, 2 and 3. The
; accumulator stays in registers throughout both table reads.
.macro ss_damp_map_digit digit
 .ifdef RIDING_GAS_REACTION
 ld l,digit
 ld h,#>_riding_scale_directory
 ld a,(hl)
 ld (#0x2000),a
 inc h
 ld h,(hl)
 .else
 ld a,digit
 rlca
 rlca
 rlca
 and a,#7
 add a,#36
 ld (#0x2000),a
 ld a,digit
 and a,#31
 add a,a
 or a,#>_physics_scale_planes_36
 ld h,a
 .endif
.endm

.macro ss_damp_word label,arm,?unsigned
label:
 ld h,l
 ld l,c
 push hl
 ss_damp_map_digit c
 ld l,e
 ld e,(hl)
 inc h
 ld a,(hl)
 ld l,d
 ld c,(hl)
 dec h
 add a,(hl)
 ld d,a
 ld l,b
 ld a,c
 adc a,(hl)
 ld c,a
 inc h
 ld a,(hl)
 adc a,#0
 ld b,a

 pop hl                         ; H:L = speed magnitude
 ld a,(#ss_damping+arm+3)
 or a
 jr z,unsigned
 ; Subtract magnitude << 24 from the five-byte unsigned product.
 ld a,b
 sub a,l
 ld b,a
 ld a,#0
 sbc a,h
unsigned:
 push de                        ; retain final byte zero
 ld e,a                         ; signed adjustment to byte four
 ss_damp_map_digit h
 ld a,(#ss_damping+arm)
 ld l,a
 ld a,(hl)
 add a,d
 ld d,a                         ; final byte one
 inc h
 ld a,(hl)
 adc a,c
 ld c,a
 ld a,(#ss_damping+arm+1)
 ld l,a
 ld a,(hl)
 adc a,b
 ld b,a
 ld a,e
 adc a,#0
 ld e,a
 dec h
 ld a,(hl)
 add a,c
 ld c,a                         ; final byte two
 ld a,(#ss_damping+arm+2)
 ld l,a
 ld a,(hl)
 adc a,b
 ld b,a                         ; final byte three
 jp ss_damp_finish
.endm
 ss_damp_word ss_damp_word0,16
 ss_damp_word ss_damp_word1,24
 ss_damp_word ss_damp_word2,20
 ss_damp_word ss_damp_word3,28

ss_damp_map:
 ss_damp_map_digit h
 ret
ss_damp_finish:
 inc h
 ld a,(hl)
 adc a,e
 ld l,a
 ld h,d
 pop de
 ld d,h
 ld a,(#__current_bank)
 ld (#0x2000),a
 ld a,l
 ret

; A unit high byte contributes the arm directly at byte offset one.
; All larger magnitudes use the existing unsigned two-row table kernel.
ss_spring_rows:
 push bc
 push de
 call _riding_product24x8_row
 pop hl
 ld a,d
 add a,l
 ld d,a
 ld a,c
 adc a,h
 ld c,a
 pop hl
 ld a,b
 adc a,h
 ld h,a
 ld l,c
 ld a,#0
 adc a,#0
 ld c,a
 ld b,#0
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret

; B:DE is signed24, C is an unsigned speed digit. The unsigned table
; product for a negative arm includes 2^24 * C. Correct its fourth byte
; and return signed32 in BC:DE with the calling bank mapped.
ss_byte_table:
 bit 7,b
 jr z,ss_byte_positive
 push bc
 call _riding_product24x8_row
 pop hl
 ld a,b
 sub a,l
 ld b,a
 jr ss_byte_mapped_done
ss_byte_positive:
 call _riding_product24x8_row
ss_byte_mapped_done:
 jp ss_mt_product_done


; The two lower speed digits always use the same pair of rows. A third
; digit contributes four bytes at offset two. The first and second
; multiples are obtained without accessing a multiplication table.
ss_mt_product:
 ld a,h
 or a
 jp z,ss_mt_product_low
 dec a
 jr nz,ss_mt_high_multiple
 ld a,e
 ld (#ss_spin_mid),a
 ld a,d
 ld (#ss_spin_mid+1),a
 ld a,b
 ld (#ss_spin_mid+2),a
 xor a
 ld (#ss_spin_mid+3),a
 jr ss_mt_merge_high
ss_mt_high_multiple:
 dec a
 jr nz,ss_mt_table_high
 ld a,e
 add a,e
 ld (#ss_spin_mid),a
 ld a,d
 adc a,d
 ld (#ss_spin_mid+1),a
 ld a,b
 adc a,b
 ld (#ss_spin_mid+2),a
 ld a,#0
 rla
 ld (#ss_spin_mid+3),a
 jr ss_mt_merge_high
ss_mt_table_high:
 push hl
 push bc
 push de
 ld c,h
 call ss_mt_save_high
 pop de
 pop bc
 pop hl
ss_mt_merge_high:
 call ss_mt_product_low
 ld a,(#ss_spin_mid)
 add a,l
 ld l,a
 ld a,(#ss_spin_mid+1)
 adc a,h
 ld h,a
 ld a,(#ss_spin_mid+2)
 adc a,c
 ld c,a
 ld a,(#ss_spin_mid+3)
 adc a,b
 ld b,a
 ret
.area _CODE
ss_mt_save_high:
 call _riding_product24x8_row
 ss_store ss_spin_mid
 jp ss_mt_product_done
ss_mt_product_low:
 ld a,l
 or a
 jr z,ss_mt_product_single
 ld l,a
 rlca
 rlca
 rlca
 and a,#7
 add a,#36
 ld (#0x2000),a
 ld a,l
 and a,#31
 add a,a
 or a,#>_physics_scale_planes_36
 ld h,a
 ld l,e
 ld a,(hl)
 ld (#ss_spin_top),a
 inc h
 ld a,(hl)
 ld l,d
 dec h
 add a,(hl)
 ld (#ss_spin_top+1),a
 inc h
 ld a,(hl)
 adc a,#0
 ld l,b
 dec h
 add a,(hl)
 ld (#ss_spin_top+2),a
 inc h
 ld a,(hl)
 adc a,#0
 ld (#ss_spin_top+3),a
 call _riding_product24x8_row
 ld hl,#ss_spin_top
 ld a,(hl+)
 add a,d
 ld d,a
 ld a,(hl+)
 adc a,c
 ld c,a
 ld a,(hl+)
 adc a,b
 ld h,a
 ld a,(#ss_spin_top+3)
 adc a,#0
 ld l,c
 ld c,a
 ld b,#0
 jr ss_mt_product_done
ss_mt_product_single:
 call _riding_product24x8_row
 ld h,b
 ld l,c
 ld bc,#0
ss_mt_product_done:
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret

; Each row leaves DE at the next byte of the product. A 24-by-8 table
; product also covers a full-width arm by reading its last digit from the
; same table pages. Restore ROMB0 only after the last nonzero speed digit.
ss_mt_wide_rows:
 ld de,#ss_spin_top
 ld a,(#ss_spin_mid+4)
 call ss_mt_wide_row
 ld a,(#ss_spin_mid+5)
 call ss_mt_wide_row
 ld a,(#ss_spin_mid+6)
 or a
 jr z,001$
 call ss_mt_wide_row
 jr 002$
001$:
 inc de
002$:
 ld a,(#ss_spin_mid+7)
 or a
 call nz,ss_mt_wide_row
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret
ss_mt_wide_row:
 or a
 jr nz,003$
 inc de
 ret
003$:
 push de
 push de
 ld c,a
 ld hl,#ss_spin_mid
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld b,(hl)
 call _riding_product24x8_row
 ld a,(#ss_spin_mid+3)
 or a
 jr z,ss_mt_accum4
 ld l,a
 dec h
 ld a,(hl)
 add a,b
 ld b,a
 inc h
 ld a,(hl)
 adc a,#0

.macro ss_mt_accum_low4
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
 ld (hl+),a
.endm
ss_mt_accum5:
 pop hl
 push af
 ss_mt_accum_low4
 pop de
 ld a,(hl)
 adc a,d
 ld (hl+),a
 jr ss_mt_carry
ss_mt_accum4:
 pop hl
 ss_mt_accum_low4
ss_mt_carry:
 jr nc,ss_mt_row_done
ss_mt_carry_loop:
 inc (hl)
 jr nz,ss_mt_row_done
 inc hl
 jr ss_mt_carry_loop
ss_mt_row_done:
 pop de
 inc de
 ret

.area _CODE_15
ss_wide_force_sums:
 ss_force_wide_axis 0,0,ss_x0_pos,ss_x1_pos
 ss_force_wide_axis 14,1,ss_y0_pos,ss_y1_pos
 ret

.area _CODE_8
ss_near_area
ss_publish_base_forces:
 ; Stream both adjacent split sums. Their low three digits also become
 ; the persistent fractional remainder before any reaction torque.
 ld hl,#ss_prepared_sums
 ld de,#_riding_force_sums
 .irp axis,0,1
 .irp digit,0,1,2
 ld a,(hl+)
 ld (#_force_residual+axis*8+digit),a
 ld (de),a
 inc de
 .endm
 .rept 6
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 .endm
 ld hl,#ss_prepared_wheels
 .irp wheel,0,1
 ld de,#(_riding_suspension_state+ss_wheel_dvx+wheel*ss_wheel_stride)
 .rept 8
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 .endm
 ret

.area _CODE_8
.area _CODE_15
ss_prepare_base_forces:
 ss_force_fraction 0,0,ss_prepared_sums,0
 ss_force_fraction 14,1,ss_prepared_sums,0
 ss_narrow_force_axis 0,0,ss_prepared_sums,ss_prepared_wheels,(ss_prepared_wheels+8)
 ss_narrow_force_axis 14,1,ss_prepared_sums,(ss_prepared_wheels+4),(ss_prepared_wheels+12)
 ret

.area _CODE_8
ss_general_force_sums:
 ss_force_fraction 0,0,_riding_force_sums,1
 ss_force_fraction 14,1,_riding_force_sums,1
 ldh a,(ss_force_wide_used)
 or a
 jp nz,ss_need_wide_sums
 ss_narrow_force_axis 0,0,_riding_force_sums,(_riding_suspension_state+ss_wheel_dvx+0),(_riding_suspension_state+ss_wheel_dvx+ss_wheel_stride+0)
 ss_narrow_force_axis 14,1,_riding_force_sums,(_riding_suspension_state+ss_wheel_dvx+4),(_riding_suspension_state+ss_wheel_dvx+ss_wheel_stride+4)
 ret
ss_need_wide_sums:
 ld e,#15
 ld hl,#ss_wide_force_sums
 jp ___sdcc_bcall_ehl

; Both X forces vanish, and wheel one's Y spring and damping match wheel
; zero's. Form their signed33 sum once. Doubling it retains both high sign
; bits for the body, including the carry out of the wheel's wrapped word.
.area _CODE_15
ss_paired_forces:
 xor a
 ld hl,#_riding_suspension_state+ss_wheel_dvx
 .rept 4
 ld (hl+),a
 .endm
 ld hl,#_riding_suspension_state+ss_wheel_dvx+ss_wheel_stride
 .rept 4
 ld (hl+),a
 .endm
 ; Copy X residual into the split representation with a zero fraction carry.
 ld hl,#_force_residual
 ld de,#_riding_force_sums
 .rept 3
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 xor a
 ld (de),a
 inc de
 .rept 5
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 ; The four biased fractions are two copies of each vertical product.
 ; Sum each pair and subtract it twice from (residual_low + 2*2^24).
 ld hl,#(ss_force_products+14)
 ldh a,(ss_force_products+42)
 add a,(hl)
 ld e,a
 inc l
 ldh a,(ss_force_products+43)
 adc a,(hl)
 ld d,a
 inc l
 ldh a,(ss_force_products+44)
 adc a,(hl)
 ld c,a
 ld a,#0
 rla
 sla e
 rl d
 rl c
 rla
 ld b,a
 ld hl,#(_force_residual+8)
 ld a,(hl)
 sub a,e
 ld (hl+),a
 ld e,a
 ld a,(hl)
 sbc a,d
 ld (hl+),a
 ld d,a
 ld a,(hl)
 sbc a,c
 ld (hl),a
 ld c,a
 ld a,#2
 sbc a,b
 ld b,a
 ss_write _riding_force_sums+9

 ss_force_pair 14,ss_wheel_dvy,ss_pair_positive
 ss_write _riding_suspension_state+ss_wheel_dvy+ss_wheel_stride
 sla e
 rl d
 rl c
 rl b
 rla
 ld h,a
 ld a,(#_force_residual+15)
 sub a,h
 push af
 ss_reverse_sub _force_residual+11
 pop hl
 ld a,h
 sbc a,#0
 ld (#_riding_force_sums+17),a
 ss_write _riding_force_sums+13
 ret

; The caller supplies four signed inputs in HL, seven-byte output records in
; DE, and a coefficient index in A. All four products share one bank mapping.
; For the positive suspension scales at most one, the low byte contributes
; only one quotient byte and an unsigned 16-bit prefix contributes at most
; two. Inputs of every width retain the table's full biased low 24 bits.
.area _HRAM
; One HRAM page holds all eight records. C can advance through the records
; independently of the table pointers DE/HL and the third input digit in B.
_riding_spring_product_rows::
ss_force_products: .ds 56
ss_force_wide_used: .ds 1
ss_force_page: .ds 1
ss_force_byte2: .ds 1
ss_force_byte3: .ds 1
ss_force_index: .ds 1

.area _CODE_8
ss_force_four:
 call ss_force_try
 ret nc
 jp ss_force_generic

; DE and HL walk the low and high input-byte rows. Emit the first two
; biased fraction digits and preserve their carry for digit two.
.macro ss_force_first_two
 ld a,(de)
 ldh (c),a
 inc c
 inc d
 ld a,(de)
 add a,(hl)
 ldh (c),a
 inc c
 inc d
 inc h
.endm
; Inline the common -65536..65535 case once per lane. Each wider case
; uses the saved input cursor to select its signed or full-width row.
.macro ss_force_lane ?positive,?narrow,?wide,?done
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 push hl
 or a
 jr z,positive
 inc a
 jr nz,wide
 ld a,b
 inc a
 jr nz,wide
 ld l,d
 ldh a,(#ss_force_page)
 ld d,a
 add a,#11
 jr narrow
wide:
 call ss_force_wider_lane
 jr done
positive:
 ld a,b
 or a
 jr nz,wide
 ld l,d
 ldh a,(#ss_force_page)
 ld d,a
 add a,#5
narrow:
 ld h,a
 ss_force_first_two
 ld a,(de)
 adc a,(hl)
 ldh (c),a
 inc c
 inc d
 inc h
 ld a,(de)
 adc a,(hl)
 ldh (c),a
 inc c
 inc h
 ld a,(hl)
 adc a,#0
 ldh (c),a
 inc c
 inc h
 ld a,(hl)
 adc a,#0
 ldh (c),a
 inc c
 ldh (c),a
 inc c
done:
 pop hl
.endm

; The private batch leaves q24_fraction and q24_saturated untouched.
; Unsupported scale metadata returns carry before lane zero.
.area _CODE
ss_force_try:
 push hl
 ld c,e
 ldh (#ss_force_index),a
 srl a
 ld d,a
 ld e,#0x40
 jr nc,ss_force_page_set
 ld e,#0x60
ss_force_page_set:
 ld a,(#_q24_first_bank_low)
 add a,d
 ld (#0x2000),a
 ld a,#1
 ld (#0x3000),a
 ld a,e
 ldh (#ss_force_page),a
 add a,#26
 ld h,a
 ; The metadata flags cover coefficients that saturate or have negative sign.
 ; Keep the scalar path available to different generated coefficient sets.
 ld l,#14
 ld a,(hl)
 ld l,#23
 or a,(hl)
 pop hl
 jp nz,ss_force_unsupported
 ld a,(#ss_paired)
 or a
 jr z,ss_force_all_lanes
 ; Only wheel zero's Y record is consumed by ss_paired_forces.
 ld de,#8
 add hl,de
 ld a,c
 add a,#14
 ld c,a
 jp ss_force_last_lane
ss_force_all_lanes:
 ss_force_lane
 ss_force_lane
 ss_force_lane
ss_force_last_lane:
 ss_force_lane
ss_force_restore:
 xor a
 ld (#0x3000),a
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret

ss_force_unsupported:
 ld b,#>ss_force_products
 call ss_force_restore
 scf
 ret

.macro ss_force_word_prefix
 ld l,d
 ldh a,(#ss_force_page)
 ld d,a
 add a,#5
 ld h,a
 ss_force_first_two
 ; Bytes 3 and 4 of the low-word product stay in DE until the third
 ; table row is added. Only byte 2 needs the HRAM scratch slot at C.
 ld a,(de)
 adc a,(hl)
 ldh (c),a
 inc d
 inc h
 ld a,(de)
 adc a,(hl)
 ld e,a
 inc h
 ld a,(hl)
 adc a,#0
 ld d,a
.endm
ss_force_wider_lane:
 dec hl
 ld a,(hl)
 or a
 jr z,ss_force_positive24
 inc a
 jr z,ss_force_negative24
 dec a
 ldh (ss_force_byte3),a
 ldh (ss_force_wide_used),a
 ld a,#1
 ld (#ss_damp_long),a
 ss_force_word_prefix
 ; A non-extended fourth digit needs both upper rows. Keep bytes 3..6
 ; of the three-digit prefix in registers and add the last row once.
 ld l,b
 ldh a,(ss_force_page)
 add a,#17
 ld h,a
 ldh a,(c)
 add a,(hl)
 ldh (c),a
 inc c
 inc h
 ld a,e
 adc a,(hl)
 ld e,a
 inc h
 ld a,d
 adc a,(hl)
 ld d,a
 inc h
 ld a,(hl)
 adc a,#0
 ld b,a
 inc h
 ld a,(hl)
 adc a,#0
 push af
 ldh a,(ss_force_byte3)
 ld l,a
 ldh a,(ss_force_page)
 add a,#22
 ld h,a
 ld a,e
 add a,(hl)
 ldh (c),a
 inc c
 inc h
 ld a,d
 adc a,(hl)
 ldh (c),a
 inc c
 inc h
 ld a,b
 adc a,(hl)
 ldh (c),a
 inc c
 inc h
 pop de
 ld a,d
 adc a,(hl)
 ldh (c),a
 inc c
 ret
ss_force_negative24:
 ld a,#255
 jr ss_force_width24
ss_force_positive24:
 xor a
ss_force_width24:
 ldh (ss_force_byte3),a
 xor a,b
 and a,#0xe0
 jr nz,ss_force_mark_wide
 ldh a,(ss_force_byte3)
 xor a,b
 and a,#0xfe                     ; high word is -2, -1, 0 or 1
 jr z,ss_force_wide
 jr ss_force_long
ss_force_mark_wide:
 ldh (ss_force_wide_used),a
ss_force_long:
 ld a,#1
 ld (#ss_damp_long),a
ss_force_wide:
 ss_force_word_prefix
 ldh a,(#ss_force_byte3)
 inc a
 ldh a,(#ss_force_page)
 jr nz,ss_force_unsigned2
 add a,#11
 jr ss_force_row2
ss_force_unsigned2:
 add a,#17
ss_force_row2:
 ld h,a
 ld a,b
 ld l,a
 ldh a,(c)
 add a,(hl)
 ldh (c),a
 inc c
 inc h
 ld a,e
 adc a,(hl)
 ldh (c),a
 inc c
 inc h
 ld a,d
 adc a,(hl)
 ldh (c),a
 inc c
 inc h
 .rept 2
 ld a,(hl)
 adc a,#0
 ldh (c),a
 inc c
 inc h
 .endm
 ret

; Unsupported generated scales use the scalar saturation and fractional rules.
.area _CODE_8
ss_force_generic:
 ld a,#1
 ld (#ss_damp_long),a
 ldh (ss_force_wide_used),a
 call ss_force_generic_lane
 call ss_force_generic_lane
 call ss_force_generic_lane
ss_force_generic_lane:
 push bc
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 push hl
 dec sp
 ldh a,(#ss_force_index)
 call _q24_apply_a
 ; Stack holds the next input and the destination for this record.
 pop hl
 ld a,l
 ldh (#ss_force_byte2),a
 ld a,h
 ldh (#ss_force_byte3),a
 pop hl
 ldh a,(#_q24_fraction)
 ld (hl+),a
 ldh a,(#_q24_fraction+1)
 ld (hl+),a
 ldh a,(#_q24_fraction+2)
 xor a,#128
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld b,h
 ld c,l
 ldh a,(#ss_force_byte2)
 ld l,a
 ldh a,(#ss_force_byte3)
 ld h,a
 ret

.ifdef RIDING_GAS_REACTION
.area _CODE_8
; Stack ABI0 tq32,kx16,ky16. The generated row includes both rounding
; operations. Close separation keeps its full distance-squared division.
_riding_gas_reaction::
 ldhl sp,#2
 ld a,(hl+)
 cp #<reaction_gas
 jr z,gas_positive
 cp #<(-reaction_gas)
 jr nz,gas_other
 ld a,(hl+)
 cp #>(-reaction_gas)
 jr nz,gas_other
 ld a,(hl+)
 and (hl)
 inc a
 jr nz,gas_other
 ld a,#3
 jr gas_mode
gas_positive:
 ld a,(hl+)
 cp #>reaction_gas
 jr nz,gas_other
 ld a,(hl+)
 or (hl)
 jr nz,gas_other
gas_mode:
 ld c,a
 ld a,(#_riding_subphase)
 or a
 ld a,c
 jr z,gas_page
 add a,#6
gas_page:
 push af
 ldhl sp,#8
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 call _riding_recip_index_regs
 ld c,e
 pop af
 ld b,a
 ld a,c
 cp #16
 jr nc,gas_read
gas_other:
 and a
 ret
gas_read:
 jp gas_read_fixed

.area _CODE
gas_read_fixed:
 ld hl,#_riding_gas_rows
 add hl,bc                    ; B is the phase/sign page, C the distance index
 ld a,#7
 ld (#0x2000),a
 ld e,(hl)
 inc h
 ld d,(hl)
 inc h
 ld c,(hl)
 ld a,c
 add a,a
 sbc a,a
 ld b,a
 ld a,(#__current_bank)
 ld (#0x2000),a
 scf
 ret
.endif
