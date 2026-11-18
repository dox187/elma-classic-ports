; Exact signed32 x Q24 multiply, round-to-nearest with ties toward +infinity.
; SDCC register ABI: x=DEBC, index=(SP+2), return=DEBC; callee drops index.
; Table rows: rounded low byte [0..4], unsigned byte1 [5..10],
; negative narrow byte1 [11..16], unsigned byte2 [17..21],
; signed byte3 [22..25], saturation metadata [26], negative byte [27..31].
; Low-byte quotients fit signed16. Their two upper sign bytes are implicit.
.module q24_coeff
.globl _q24_first_bank_low
.area _DATA
_q24_fraction:: .ds 4
_q24_saturated:: .ds 1
q_input: .ds 4
q_page: .ds 1
q_count: .ds 1
.area _CODE
_q24_apply::
 ld a,b
 or a,c
 or a,d
 or a,e
 jr nz,q_nonzero
 ld hl,#_q24_fraction
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl),a
 ld (#_q24_saturated),a
 pop hl
 inc sp
 jp (hl)
q_nonzero:
; Dispatch before spilling wide-input scratch; both narrow classes cannot saturate.
 ld a,d
 or a,e
 jr z,q_narrow_positive
 ld a,d
 and a,e
 inc a
 jr z,q_narrow_negative
 jp q_wide
q_narrow_positive:
 ld d,#5
 ld a,b
 or a,a
 jr nz,q_narrow_map
 ld d,#0
 jr q_narrow_map
q_narrow_negative:
 ld a,b
 inc a
 jr nz,q_narrow_negative16
 ld a,c
 or a,a
 jr z,q_narrow_negative16
 jp q_negative8_map
q_narrow_negative16:
 ld d,#11
q_narrow_map:
 ld e,b
 xor a
 ld (#_q24_saturated),a
 ldhl sp,#2
 ld a,(hl)
 srl a
 ld h,#0x40
 jr nc,q_narrow_page
 ld h,#0x60
q_narrow_page:
 ld b,a
 ld a,(#_q24_first_bank_low)
 add a,b
 ld (#0x2000),a
 ld a,#1
 ld (#0x3000),a
 ld l,c
 ld a,d
 or a,a
 jr z,q_narrow8
 add a,h
 ld d,a
 push de
 ld a,(hl)
 ld (#_q24_fraction+0),a
 inc h
 ld a,(hl)
 ld (#_q24_fraction+1),a
 inc h
 ld a,(hl)
 ld (#_q24_fraction+2),a
 inc h
 ld a,(hl)
 ld c,a
 inc h
 ld a,(hl)
 ld b,a
 ; A rounded unsigned-byte product always fits signed16.
 ld a,b
 add a,a
 sbc a,a
 ld e,a
 ld d,a
 pop hl
 or a,a
 ld a,(#_q24_fraction+1)
 adc a,(hl)
 ld (#_q24_fraction+1),a
 inc h
 ld a,(#_q24_fraction+2)
 adc a,(hl)
 ld (#_q24_fraction+2),a
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
 jp q_return
q_narrow8:
 ld a,(hl)
 ld (#_q24_fraction+0),a
 inc h
 ld a,(hl)
 ld (#_q24_fraction+1),a
 inc h
 ld a,(hl)
 ld (#_q24_fraction+2),a
 inc h
 ld a,(hl)
 ld c,a
 inc h
 ld a,(hl)
 ld b,a
 ; A rounded unsigned-byte product always fits signed16.
 ld a,b
 add a,a
 sbc a,a
 ld e,a
 ld d,a
 jp q_return
q_negative8_map:
 xor a
 ld (#_q24_saturated),a
 ldhl sp,#2
 ld a,(hl)
 srl a
 ld h,#0x5b
 jr nc,q_negative8_page
 ld h,#0x7b
q_negative8_page:
 ld b,a
 ld a,(#_q24_first_bank_low)
 add a,b
 ld (#0x2000),a
 ld a,#1
 ld (#0x3000),a
 ld l,c
 jp q_narrow8
q_wide:
 ld a,c
 ld (#q_input),a
 ld a,b
 ld (#q_input+1),a
 ld a,e
 ld (#q_input+2),a
 ld a,d
 ld (#q_input+3),a
 xor a
 ld (#_q24_saturated),a
 ldhl sp,#2
 ld a,(hl)
 srl a
 ld h,#0x40
 jr nc,q_page_set
 ld h,#0x60
q_page_set:
 ld b,a
 ld a,(#_q24_first_bank_low)
 add a,b
 ld (#0x2000),a
 ld a,#1
 ld (#0x3000),a
 ld a,h
 ld (#q_page),a
; All signed32 Q24 coefficients are safe for x in [-65536,65535].
; Inputs with magnitude below 2^24 are also safe for signed32 coefficients.
; Count 2 selects unsigned byte1; count 1 selects its negative bias table.
 ld c,#4
 ld a,d
 or a,a
 jr z,q_positive
 inc a
 jr nz,q_classified
 ld a,e
 inc a
 jr z,q_negative_narrow
 dec a
 jr nz,q_seed
 jr q_classified
q_negative_narrow:
 ld c,#1
 jr q_seed
q_positive:
 ld c,#3
 ld a,e
 or a,a
 jr nz,q_seed
 ld c,#2
 jr q_seed
q_classified:
 push bc
 ld a,h
 add a,#26
 ld h,a
 ld l,#14
 ld a,(hl)
 or a,a
 jr z,q_bounds_done
 ld l,#18
 call q_compare_limit
 jr z,q_lower_ok
 jr c,q_lower_ok
 ld l,#23
 ld a,(hl)
 xor a,#1
 pop bc
 jp q_saturate
q_lower_ok:
 ld l,#22
 call q_compare_limit
 jr nc,q_bounds_done
 ld l,#23
 ld a,(hl)
 pop bc
 jp q_saturate
q_bounds_done:
 pop bc
q_seed:
 ld a,c
 ld (#q_count),a
 ld a,(#q_page)
 ld h,a
 ld a,(#q_input)
 ld l,a
 ld a,(hl)
 ld (#_q24_fraction+0),a
 inc h
 ld a,(hl)
 ld (#_q24_fraction+1),a
 inc h
 ld a,(hl)
 ld (#_q24_fraction+2),a
 inc h
 ld a,(hl)
 ld c,a
 inc h
 ld a,(hl)
 ld b,a
 ; A rounded unsigned-byte product always fits signed16.
 ld a,b
 add a,a
 sbc a,a
 ld e,a
 ld d,a
 ld a,(#q_count)
 cp a,#1
 ld a,h
 jr nz,q_unsigned1
 add a,#7
 jr q_page1
q_unsigned1:
 inc a
q_page1:
 ld h,a
 ld a,(#q_input+1)
 ld l,a
; The biased negative node must be included even when input byte1 is zero.
 or a,a
 jr nz,q_add1
 ld a,(#q_count)
 cp a,#1
 jr nz,q_done1
 or a,a
q_add1:
 ld a,(#_q24_fraction+1)
 adc a,(hl)
 ld (#_q24_fraction+1),a
 inc h
 ld a,(#_q24_fraction+2)
 adc a,(hl)
 ld (#_q24_fraction+2),a
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
q_done1:
 ld a,(#q_count)
 cp a,#3
 jp c,q_return
 ld a,(#q_page)
 add a,#17
 ld h,a
 ld a,(#q_input+2)
 ld l,a
 or a,a
 jr z,q_done2
 ld a,(#_q24_fraction+2)
 adc a,(hl)
 ld (#_q24_fraction+2),a
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
q_done2:
 ld a,(#q_count)
 cp a,#3
 jr z,q_return
 ld a,(#q_page)
 add a,#22
 ld h,a
 ld a,(#q_input+3)
 ld l,a
 or a,a
 jr z,q_return
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
q_return:
 ld a,(#_q24_fraction+2)
 xor a,#128
 ld (#_q24_fraction+2),a
 rlca
 sbc a,a
 ld (#_q24_fraction+3),a
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
 ld a,(#q_input+3)
 xor a,#128
 ld b,a
 ld a,(hl)
 xor a,#128
 cp a,b
 ret nz
 dec hl
 ld a,(#q_input+2)
 ld b,a
 ld a,(hl)
 cp a,b
 ret nz
 dec hl
 ld a,(#q_input+1)
 ld b,a
 ld a,(hl)
 cp a,b
 ret nz
 dec hl
 ld a,(#q_input)
 ld b,a
 ld a,(hl)
 cp a,b
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
 ld (#_q24_saturated),a
 xor a
 ld hl,#_q24_fraction
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl),a
 jr q_restore
_q24_end::
