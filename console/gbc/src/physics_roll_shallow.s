; Both tangent dots and the final projection use the same signed coefficient.
; Each bank contains twelve table slots, followed by this reader at $7c00.
; A slot includes the rounded signed16 product and the upper-word correction.
.macro ground_reader inputs,project,component,store,?dot,?miss,?done,?saturate_negative,?velocity_table,?have_velocity
inputs::
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld bc,#8
 add hl,bc
 push hl
 ld bc,#4
 add hl,bc
 ; The directory accepted a signed-byte Y coefficient. For |vy| <= 63,
 ; its product lies strictly within the zero Q14 rounding interval.
 ld a,(hl+)
 add #64
 jr z,velocity_table
 bit 7,a
 jr nz,velocity_table
 ld a,(hl+)
 adc #0
 jr nz,velocity_table
 ld a,(hl+)
 adc #0
 jr nz,velocity_table
 ld a,(hl)
 adc #0
 jr nz,velocity_table
 pop hl
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
 jr nz,have_velocity
 ld a,e
 or b
 or c
 jr nz,have_velocity
 ld de,#0x7fff
 ld bc,#0xffff
 jr have_velocity
velocity_table:
 pop hl
 ldh a,(#near_slot)
 call dot
 jp nc,ground_resume_dots
have_velocity:
 push de
 push bc
 ldhl sp,#8
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ldh a,(#near_slot)
 call dot
 jp c,ground_resume_deltas
 add sp,#4
 jp ground_resume_dots

; A selects the first page. HL points at x, y. Return DEBC = q(y)-x.
dot:
 push hl
 ld de,#4
 add hl,de
 call component
 pop hl
 ret nc
 ld a,d
 add a
 sbc a
 ld b,a
 ld a,e
 sub (hl)
 ld c,a
 inc hl
 ld a,d
 sbc (hl)
 ld d,a
 inc hl
 ld a,b
 sbc (hl)
 ld e,a
 inc hl
 ld a,b
 sbc (hl)
 ld h,(hl)
 ld l,a
 xor b
 bit 7,a
 jr z,done
 ld a,h
 xor b
 bit 7,a
 jr z,done
 bit 7,b
 jr nz,saturate_negative
 ld de,#0x7fff
 ld bc,#0xffff
 scf
 ret
saturate_negative:
 ld de,#0x8000
 ld bc,#0
 scf
 ret
done:
 ld b,d
 ld d,l
 scf
 ret

; Project a full vector component. With l,u the low two bytes, write
; v = l + 256*signed(u) + 65536*m. For m in [-16,15], the rounded
; result plus 4*m*coefficient fits signed16. Return it in DE.
component:
 ld c,a
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 add a
 ld a,(hl+)
 adc #16
 ld b,a
 sbc a
 cp (hl)
 jr nz,miss
 ld a,b
 cp #32
 jr nc,miss
 ; The correction page contains the exact reader for this coefficient.
 ld a,c
 add #4
 ld h,a
 ld l,#64
 jp (hl)
miss:
 and a
 ret

; The component proof also bounds the signed32 speed, so negating it
; cannot saturate. Stack: destination, return address, speed, tangent.
project::
 ldhl sp,#4
 call component
 jp nc,ground_resume_pair
store:
 pop hl
 push de
 ld d,h
 ld e,l
 ldhl sp,#4
 xor a
 .rept 3
 sbc (hl)
 ld (de),a
 inc de
 inc hl
 ld a,#0
 .endm
 sbc (hl)
 ld (de),a
 inc de
 pop bc
 ld a,c
 ld (de),a
 inc de
 ld a,b
 ld (de),a
 inc de
 add a
 sbc a
 ld (de),a
 inc de
 ld (de),a
 jp ground_return
.endm

; The unit-X axis with no Y component needs only saturated negation.
.macro ground_flat_kernel
ground_flat_29:
 ldhl sp,#7
 ld a,(hl-)
 cp #128
 jr nz,ground_flat_safe
 ld a,(hl-)
 or (hl)
 dec hl
 or (hl)
 jr nz,ground_flat_safe
 pop hl
 ld a,#255
 .rept 3
 ld (hl+),a
 .endm
 ld (hl),#127
 inc hl
 xor a
 .rept 4
 ld (hl+),a
 .endm
 jp ground_return
ground_flat_safe:
 ld de,#0
 jp ground_store_29
.endm

; Each fifth page holds 64 upper-word correction bytes followed by this
; coefficient's reader. Reverse the low digit for negative coefficients
; so every threshold crossing increases the quotient.
.macro ground_threshold_reader page,negative,narrow,?done
 .if negative
 ld a,e
 cpl
 ld e,a
 .endif
 ld h,#(page+1)
 ld l,d
 ld a,(hl)
 cp e
 .if narrow
 dec h
 ld a,(hl)
 adc #0
 ld e,a
 add a
 sbc a
 ld d,a
 .else
 ld a,#0
 adc #0
 ld c,a
 inc h
 ld a,(hl)
 cp e
 ld a,c
 adc #0
 ld h,#page
 add (hl)
 ld e,a
 ld a,#0
 adc #0
 ld c,a
 ; The signed high digit and coefficient give the base quotient's
 ; sign. Include the carry from adding the two threshold comparisons.
 ld a,l
 .if negative
 cpl
 .endif
 add a
 sbc a
 add c
 ld d,a
 .endif
 ld a,b
 cp #16
 jr z,done
 ld h,#(page+4)
 ld l,b
 ld a,e
 add (hl)
 ld e,a
 set 5,l
 ld a,d
 adc (hl)
 ld d,a
done:
 scf
 ret
.endm
