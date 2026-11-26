; Both tangent dots and the final projection use the same signed coefficient.
; Each bank contains twelve table slots, followed by this reader at $7c00.
; A slot includes the rounded signed16 product and the upper-word correction.
.macro ground_reader inputs,project,component,store,?dot,?narrow,?miss,?done,?saturate_negative,?first_miss
inputs::
 push af
 ldhl sp,#8
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld bc,#8
 add hl,bc
 pop af
 push af
 call dot
 jr nc,first_miss
 pop af
 push de
 push bc
 ldhl sp,#8
 ld c,a
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,c
 call dot
 jp c,ground_resume_deltas
 inc sp
 inc sp
first_miss:
 inc sp
 inc sp
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
 ld h,c
 ld l,e
 ld e,(hl)
 ld a,e
 and #3
 ld c,a
 inc h
 ld l,d
 ld a,e
 add (hl)                     ; carry from the two six-bit fractions
 ld a,c
 inc h
 adc (hl)
 ld e,a
 inc h
 ld a,#0
 adc (hl)
 ld d,a
 ld a,b
 cp #16
 jr z,narrow
 inc h
 ld l,b
 ld a,e
 add (hl)
 ld e,a
 set 5,l
 ld a,d
 adc (hl)
 ld d,a
narrow:
 scf
 ret
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
