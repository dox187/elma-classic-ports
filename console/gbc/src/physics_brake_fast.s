; Exact two-wheel brake spring and angular damping. The cartridge selects
; bank 93 for its signed16 lookup rows and restores the caller in bank 8.
; Both torque outputs wrap to signed32. Bike is read-only.
.module physics_brake_fast
.area _CODE_8
; HL points at the pair of generated phase indices.
.macro brake_phase_index ready
 ld a,(#_riding_subphase)
 or a,a
 jr z,ready
 inc hl
ready:
 ld a,(hl)
.endm

.macro brake_store
 ld (hl),c
 inc hl
 ld (hl),b
 inc hl
 ld (hl),e
 inc hl
 ld (hl),d
.endm

_riding_brake32::
 ldhl sp,#2
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 ld hl,#4
 add hl,de
 ld b,h
 ld c,l
; DE and BC point to the separate scheduled torque fields.
_riding_brake_fields::
 .ifdef brake_tables
 jp brake_switch
.area _CODE
brake_switch:
 ld a,#93
 ld (#__current_bank),a
 ld (#0x2000),a
 call brake_fields
 ld a,#8
 ld (#__current_bank),a
 ld (#0x2000),a
 ret
.area _CODE_93
 ; GENERATED BRAKE PAGES
; Both wheel angles and velocities have fixed locations. Keeping their
; addresses in the instruction saves the wheel pointer across Q24 calls.
.macro brake_wheel offset,dbrake,damping,?lower_nonzero
 ld hl,#(_Bike+dbrake)
 ld a,(#_Bike+16)
 add (hl)
 ld e,a
 inc hl
 ld a,(#_Bike+17)
 adc (hl)
 ld c,a
 inc hl
 ld a,(#_Bike+18)
 adc (hl)
 ld b,a
 inc hl
 ld a,(#_Bike+19)
 adc (hl)
 ld d,a
 ld hl,#(_Bike+40+offset)
 ld a,(hl+)
 sub e
 ld a,(hl+)
 sbc c
 ld c,a
 ld a,(hl+)
 sbc b
 ld b,a
 ld a,(hl)
 sbc d
 ld e,a
 call brake_angle_value
 ; The two's complement of spring+damping equals ~(spring-1+damping).
 ld a,b
 or c
 jr nz,lower_nonzero
 dec de
lower_nonzero:
 dec bc
 push de
 push bc
 ld hl,#(_Bike+20)
 .irp i,0,1,2,3
 ld a,(#(_Bike+44+offset+i))
 .if i
 sbc (hl)
 .else
 sub (hl)
 .endif
 .ifeq i
 ld c,a
 .endif
 .ifeq i-1
 ld b,a
 .endif
 .ifeq i-2
 ld e,a
 .endif
 .ifeq i-3
 ld d,a
 .else
 inc hl
 .endif
 .endm
 call damping
 pop hl
 ld a,c
 add l
 cpl
 ld c,a
 ld a,b
 adc h
 cpl
 ld b,a
 pop hl
 ld a,e
 adc l
 cpl
 ld e,a
 ld a,d
 adc h
 cpl
 ld d,a
 pop hl
 brake_store
.endm
brake_fields:
 push bc
 push de
 brake_wheel 0,101,brake_damp_first
 brake_wheel 24,105,brake_damp_last
 ret
 .else
 push bc
 push de
 .ifndef brake_damping_index
 ld a,(#_riding_landing_contact)
 .endif
 ld hl,#_Bike+40
 ld de,#_Bike+101
 call brake_one
 pop hl
 brake_store
 .ifndef brake_damping_index
 ld a,(#_riding_landing_contact+1)
 .endif
 ld hl,#_Bike+64
 ld de,#_Bike+105
 call brake_one
 pop hl
 brake_store
 ret

; HL wheel.alfa, DE dbrake, A contact when the damping indices differ.
; Q24 operates on DEBC throughout (low byte C).
brake_one:
 .ifndef brake_damping_index
 push af
 .endif
 push hl
 ld h,d
 ld l,e
 ld a,(#_Bike+16)
 add a,(hl)
 ld e,a
 inc hl
 ld a,(#_Bike+17)
 adc a,(hl)
 ld c,a
 inc hl
 ld a,(#_Bike+18)
 adc a,(hl)
 ld b,a
 inc hl
 ld a,(#_Bike+19)
 adc a,(hl)
 ld d,a
 pop hl
 ; Subtract all four angle bytes. Discard the low result after its borrow.
 ld a,(hl+)
 sub a,e
 ld a,(hl+)
 sbc a,c
 ld c,a
 ld a,(hl+)
 sbc a,b
 ld b,a
 ld a,(hl+)
 sbc a,d
 ld e,a
 add a,a
 sbc a,a
 ld d,a
 push hl                     ; wheel.omega immediately follows alfa
 .ifdef brake_angle_index
 ld a,#brake_angle_index
 .else
 ld hl,#_q24_index_C_BRAKE_A
 brake_phase_index brake_angle_ready
 .endif
 dec sp                      ; _q24_apply_a consumes its one-byte ABI slot
 call _q24_apply_a
 pop hl

 ; Save spring-1 modulo 2^32. Complementing the sum with damping later
 ; gives -(spring+damping), with one carry chain over the result.
 ld a,b
 or a,c
 jr nz,brake_spring_low
 dec de
brake_spring_low:
 dec bc
 push de
 push bc
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ld hl,#_Bike+20
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
 ld d,a
 .ifdef brake_damping_index
 ld a,#brake_damping_index
 .else
 ldhl sp,#5                  ; saved contact above the four spring bytes
 ld a,(hl)
 or a,a
 ld hl,#_q24_index_C_BRAKE_W
 jr z,brake_damping_phase
 ld hl,#_q24_index_C_BRAKE_GW
brake_damping_phase:
 brake_phase_index brake_damping_ready
 .endif
 dec sp
 call _q24_apply_a

 ; CPL preserves the carry between bytes.
 pop hl
 ld a,c
 add a,l
 cpl
 ld c,a
 ld a,b
 adc a,h
 cpl
 ld b,a
 pop hl
 ld a,e
 adc a,l
 cpl
 ld e,a
 ld a,d
 adc a,h
 cpl
 ld d,a
 .ifndef brake_damping_index
 pop af
 .endif
 ret

 .endif

.ifdef brake_tables
; The angle difference has already been arithmetically shifted by one
; byte. Its fourth byte is therefore the sign extension of E.
brake_angle_value:
 ld a,b
 add a,a
 sbc a,a
 cp e
 jr nz,brake_angle_wide
 ld l,c
 ld h,#>brake_angle_rows
 ld e,(hl)
 inc h
 ld c,(hl)
 ld l,b
 inc h
 ld a,e
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
 add a,a
 sbc a,a
 ld d,a
 ld e,a
 ret
brake_angle_wide:
 ld a,e
 add a,a
 sbc a,a
 ld d,a
 ld a,#brake_angle_index
 jp brake_wide

; Only the second wheel's damping publishes a residual at this ABI.
; The byte rows give the exact signed 24-bit remainder and quotient.
.macro brake_damping residual,?word,?wide
 ld a,b
 add a,a
 sbc a,a
 cp e
 jr nz,wide
 cp d
 jr nz,wide
 ld a,c
 add a,a
 sbc a,a
 cp b
 jr nz,word
 ld l,c
 .if residual
 ld h,#>brake_damp_byte
 ld a,(hl)
 ldh (#_q24_fraction),a
 inc h
 ld a,(hl)
 ldh (#_q24_fraction+1),a
 inc h
 ld a,(hl)
 ldh (#_q24_fraction+2),a
 add a,a
 sbc a,a
 ldh (#_q24_fraction+3),a
 inc h
 .else
 ld h,#>(brake_damp_byte+768)
 .endif
 ld c,(hl)
 inc h
 ld b,(hl)
 ld a,b
 add a,a
 sbc a,a
 ld d,a
 ld e,a
 .if residual
 xor a
 ldh (#_q24_saturated),a
 .endif
 ret
wide:
 ld a,#brake_damping_index
 jp brake_wide
word:
 ld d,#>brake_damp_low
 ld e,c
 ld h,#>brake_damp_high
 ld l,b
 .if residual
 ld a,(de)
 ldh (#_q24_fraction),a
 .endif
 inc d
 ld a,(de)
 add (hl)
 .if residual
 ldh (#_q24_fraction+1),a
 .endif
 inc d
 inc h
 ld a,(de)
 adc (hl)
 .if residual
 push af
 xor #0x80
 ldh (#_q24_fraction+2),a
 add a,a
 sbc a,a
 ldh (#_q24_fraction+3),a
 pop af
 .endif
 inc d
 inc h
 ld a,(de)
 adc (hl)
 ld c,a
 inc d
 inc h
 ld a,(de)
 adc (hl)
 ld b,a
 inc h
 ld a,#0
 adc (hl)
 ld e,a
 add a,a
 sbc a,a
 ld d,a
 .if residual
 xor a
 ldh (#_q24_saturated),a
 .endif
 ret
.endm
brake_damp_first:
 brake_damping 0
brake_damp_last:
 brake_damping 1
brake_wide:
 dec sp
 call _q24_apply_a
 ret
.endif
