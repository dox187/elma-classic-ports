; Exact signed32 x Q24 multiply, round-to-nearest with ties toward +infinity.
; SDCC register ABI: x=DEBC, index=(SP+2), return=DEBC; callee drops index.
; Table rows: rounded low byte [0..4], unsigned byte1 [5..10],
; negative narrow byte1 [11..16], unsigned byte2 [17..21],
; signed byte3 [22..25], saturation metadata [26], negative byte [27..31].
; Low-byte quotients fit signed16. Their two upper sign bytes are implicit.
.module q24_coeff
.globl _q24_first_bank_low
.area _HRAM
_q24_fraction:: .ds 4
_q24_saturated:: .ds 1
q_input_high: .ds 2
q_page: .ds 1
.area _CODE
; DE points to the rounded low product and HL to the shifted high product.
.macro q_combine_pair final_fraction
 ld a,(de)
 ldh (#_q24_fraction),a
 inc d
 ld a,(de)
 add a,(hl)
 ldh (#_q24_fraction+1),a
 inc d
 inc h
 ld a,(de)
 adc a,(hl)
 .if final_fraction
 ; Complement the fraction sign bit and extend it while saving the carry
 ; into the integer. The following RRA reinstates that carry.
 rla
 ld b,a
 ccf
 sbc a,a
 ldh (#_q24_fraction+3),a
 ld a,b
 rra
 .endif
 ldh (#_q24_fraction+2),a
 inc d
 inc h
 ld a,(de)
 adc a,(hl)
 ld c,a
 inc d
 inc h
 ld a,(de)
 ; Save the incoming carry in bit 0 while extending the low quotient's
 ; sign. RRA then recovers both the original byte and the pending carry.
 rla
 ld e,a
 sbc a,a
 ld d,a
 ld a,e
 rra
 adc a,(hl)
 ld b,a
 inc h
 ld a,d
 adc a,(hl)
 ld e,a
 inc h
 ld a,d
 adc a,(hl)
 ld d,a
.endm

_q24_apply::
 ld a,b
 or a,c
 or a,e
 or a,d
 jr z,q_zero
 ldhl sp,#2
 ld l,(hl)
q_map:
 srl l
 ld h,#0x40
 jr nc,q_page_set
 ld h,#0x60
q_page_set:
 ld a,(#_q24_first_bank_low)
 add a,l
 ld (#0x2000),a
 ld a,#1
 ld (#0x3000),a
 dec a
 ldh (#_q24_saturated),a
 ld a,d
 or a,e
 jr z,q_positive
 ld a,d
 and a,e
 inc a
 jp nz,q_wide
 ld a,b
 inc a
 jr nz,q_negative16
 ld a,c
 or a,a
 jr z,q_negative16
 ld a,h
 add a,#27
 ld h,a
 jr q_narrow8
q_positive:
 ld a,b
 or a,a
 jr nz,q_positive16
q_narrow8:
 ld l,c
 ld a,(hl)
 ldh (#_q24_fraction),a
 inc h
 ld a,(hl)
 ldh (#_q24_fraction+1),a
 inc h
 ld a,(hl)
 xor a,#128
 ldh (#_q24_fraction+2),a
 rlca
 sbc a,a
 ldh (#_q24_fraction+3),a
 inc h
 ld c,(hl)
 inc h
 ld b,(hl)
 ld a,b
 add a,a
 sbc a,a
 ld e,a
 ld d,a
 jp q_restore
; Assembly entry: A=index, x/result=DEBC. Both entries consume one stack byte
; after the return address. A register caller can reserve this with DEC SP.
_q24_apply_a::
 ld l,a
 ld a,b
 or a,c
 or a,e
 or a,d
 jr nz,q_map
q_zero:
 ld hl,#_q24_fraction
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl),a
 pop hl
 inc sp
 jp (hl)
q_positive16:
 ld a,#5
 jr q_narrow16
q_negative16:
 ld a,#11
q_narrow16:
 ; DE walks the low byte's rounded product, HL walks the shifted high byte.
 ld d,h
 add a,h
 ld h,a
 ld l,b
 ld e,c
 q_combine_pair 1
 jp q_restore
q_wide:
 ; Keep original bytes in registers through the range check. Only a full
 ; signed32 input needs the fourth partial product.
 ld a,h
 ldh (#q_page),a
 ld a,d
 ldh (#q_input_high+1),a
 ld a,e
 ldh (#q_input_high),a
 ld a,d
 or a,a
 jr z,q_wide_parts
 inc a
 jr nz,q_wide_bounds
 ld a,e
 or a,a
 jr nz,q_wide_parts
 ; -2^24 times INT32_MIN can reach +2^31.
q_wide_bounds:
 ld a,h
 add a,#26
 ld h,a
 ld l,#14
 ld a,(hl)
 or a,a
 jr z,q_wide_parts
 ld a,d
 xor a,#128
 ld d,a
 ld l,#18
 call q_compare_limit
 jr z,q_wide_lower_ok
 jr c,q_wide_lower_ok
 ld l,#23
 ld a,(hl)
 xor a,#1
 jp q_saturate
q_wide_lower_ok:
 ld l,#22
 call q_compare_limit
 jr nc,q_wide_parts
 ld l,#23
 ld a,(hl)
 jp q_saturate
q_wide_parts:
 ldh a,(#q_page)
 ld d,a
 add a,#5
 ld h,a
 ld l,b
 ld e,c
 q_combine_pair 0
 ldh a,(#q_input_high+1)
 inc a
 ldh a,(#q_page)
 jr nz,q_wide_u2
 ; Negative 24-bit values use (byte2-256)*m. Its first five bytes
 ; are exactly the negative byte1 node, shifted one more byte.
 add a,#11
 jr q_wide_add2
q_wide_u2:
 add a,#17
q_wide_add2:
 ld h,a
 ldh a,(#q_input_high)
 ld l,a
 ldh a,(#_q24_fraction+2)
 add a,(hl)
 ldh (#_q24_fraction+2),a
 inc h
 ld a,(hl)
 adc a,c
 ld c,a
 inc h
 ld a,(hl)
 adc a,b
 ld b,a
 inc h
 ld a,(hl)
 adc a,e
 ld e,a
 inc h
 ld a,(hl)
 adc a,d
 ld d,a
 ldh a,(#q_input_high+1)
 inc a
 jr z,q_return
 dec a
 jr z,q_return
 ld l,a
 ldh a,(#q_page)
 add a,#22
 ld h,a
 ld a,(hl)
 add a,c
 ld c,a
 inc h
 ld a,(hl)
 adc a,b
 ld b,a
 inc h
 ld a,(hl)
 adc a,e
 ld e,a
 inc h
 ld a,(hl)
 adc a,d
 ld d,a
q_return:
 ldh a,(#_q24_fraction+2)
 xor a,#128
 ldh (#_q24_fraction+2),a
 rlca
 sbc a,a
 ldh (#_q24_fraction+3),a
q_restore:
 xor a
 ld (#0x3000),a
 ld a,(#__current_bank)
 ld (#0x2000),a
 pop hl
 inc sp
 jp (hl)
; Return comparison flags for signed limit - input, high byte first.
q_compare_limit:
 ld a,(hl)
 xor a,#128
 cp a,d
 ret nz
 dec hl
 ld a,(hl)
 cp a,e
 ret nz
 dec hl
 ld a,(hl)
 cp a,b
 ret nz
 dec hl
 ld a,(hl)
 cp a,c
 ret
; A!=0 selects INT32_MIN; otherwise INT32_MAX.
q_saturate:
 or a,a
 ld bc,#0
 ld de,#0x8000
 jr nz,q_saturated
 dec bc
 ld de,#0x7fff
q_saturated:
 ld a,#1
 ldh (#_q24_saturated),a
 xor a
 ld hl,#_q24_fraction
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl),a
 jr q_restore
_q24_end::
