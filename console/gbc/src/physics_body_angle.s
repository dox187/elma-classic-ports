.module physics_body_angle

.area _CODE_8
; Full substep body angle: omega*32 + floor((residual + 2^18)/2^19).
; The signed Q24 residual's high byte supplies every bit used by this floor.
_riding_full_angle::
 ld hl,#_Bike+20
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ; Adjacent bytes supply the two pieces of omega << 5, modulo 2^32.
 .macro angle_shift_five upper,lower
 ld a,upper
 xor a,lower
 and a,#7
 xor a,lower
 rrca
 rrca
 rrca
 ld upper,a
 .endm
 angle_shift_five d,e
 angle_shift_five e,b
 angle_shift_five b,c
 ld a,c
 rrca
 rrca
 rrca
 and a,#0xe0
 ld c,a
 ld hl,#_angular_residual+2
 ld a,(hl+)
 add a,#4
 ld l,a
 ld a,(#_angular_residual+3)
 adc a,#0
 ; Rotate the 9-bit rounded high byte right three, with its true sign.
 rra
 rr l
 sra l
 sra l
 ld a,l
 add a,a
 sbc a,a
 ld h,a
 ld a,c
 add a,l
 ld c,a
 ld a,b
 adc a,h
 ld b,a
 ld a,e
 adc a,h
 ld e,a
 ld a,d
 adc a,h
 ld d,a
 ld hl,#_Bike+16
 ld a,(hl)
 add a,c
 ld (hl+),a
 ld a,(hl)
 adc a,b
 ld (hl+),a
 ld a,(hl)
 adc a,e
 ld (hl+),a
 ld a,(hl)
 adc a,d
 ld (hl),a
 ret

.area _CODE_3
; Each byte of omega selects an integer quotient and a remainder for
; omega*27007/1280. All remainders share a single final floor.
.macro angle_page table,offset
 ld a,(#_Bike+20+offset)
 add a,#<table
 ld l,a
 ld a,#>table
 adc a,#0
 ld h,a
.endm

; The accumulated quotient is BCDE, least significant byte in E.
; The pending remainder index, biased by 64, lives on the stack.
.macro angle_add_digit table,offset
 angle_page table,offset
 pop af
 add a,(hl)
 push af
 inc h
 ld a,e
 add a,(hl)
 ld e,a
 inc h
 ld a,d
 adc a,(hl)
 ld d,a
 inc h
 ld a,c
 adc a,(hl)
 ld c,a
 inc h
 ld a,b
 adc a,(hl)
 ld b,a
.endm

; A signed 24-bit angular residual contributes floor(residual*27007/2^24).
; Each discarded low byte contributes its carry to the next digit.
.macro angle_residual_page table,offset
 ld a,(#_angular_residual+offset)
 add a,#<table
 ld l,a
 ld a,#>table
 adc a,#0
 ld h,a
.endm
.globl b_riding_partial_body_angle
b_riding_partial_body_angle = 3
_riding_partial_body_angle::
 angle_residual_page _riding_angle_frac0,0
 ld e,(hl)
 inc h
 ld d,(hl)
 .macro angle_frac_digit table,offset
 angle_residual_page table,offset
 ld a,e
 add a,(hl)
 inc h
 ld a,d
 adc a,(hl)
 ld e,a
 inc h
 ld a,(hl)
 adc a,#0
 ld d,a
 .endm
 angle_frac_digit _riding_angle_frac1,1
 angle_frac_digit _riding_angle_frac2,2
 jr angle_omega_digits
.globl b_riding_partial_angle
b_riding_partial_angle = 3
_riding_partial_angle::
 ; GBDK banked ABI0 puts the signed fractional input at SP+6.
 ldhl sp,#6
 ld a,(hl+)
 ld e,a
 ld d,(hl)
angle_omega_digits:
 angle_page _riding_angle_digit0,0
 ld a,e
 add a,(hl)
 inc h
 ld a,d
 adc a,(hl)
 add a,#64
 push af
 inc h
 ld e,(hl)
 inc h
 ld d,(hl)
 angle_page _riding_angle_digit1,1
 pop af
 add a,(hl)
 push af
 inc h
 ld a,e
 add a,(hl)
 ld e,a
 inc h
 ld a,d
 adc a,(hl)
 ld d,a
 inc h
 ld a,(hl)
 adc a,#0
 ld c,a
 ld b,#0
 ld hl,#_Bike+22
 ld a,(hl+)
 or a,(hl)
 jr z,angle_finish
 ld a,(hl-)
 and a,(hl)
 inc a
 jr nz,angle_wide
 ld hl,#_riding_angle_negative
 pop af
 add a,(hl)
 push af
 inc hl
 ld a,e
 add a,(hl)
 ld e,a
 inc hl
 ld a,d
 adc a,(hl)
 ld d,a
 inc hl
 ld a,c
 adc a,(hl)
 ld c,a
 inc hl
 ld a,(hl)
 adc a,#0
 ld b,a
 jr angle_finish
angle_wide:
 angle_add_digit _riding_angle_digit2,2
 angle_add_digit _riding_angle_digit3,3
angle_finish:
 pop af
 add a,#<_riding_angle_carry
 ld l,a
 ld a,#>_riding_angle_carry
 adc a,#0
 ld h,a
 ld a,(hl)
 add a,a
 sbc a,a
 ld h,(hl)
 ld l,a
 ld a,e
 add a,h
 ld e,a
 ld a,d
 adc a,l
 ld d,a
 ld a,c
 adc a,l
 ld c,a
 ld a,b
 adc a,l
 ld b,a
 ld hl,#_Bike+16
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

.globl b_body_oms
b_body_oms = 3

; Select the five parallel bytes of digit*m. The table can start at any
; address in this bank. Incrementing H moves to the next product byte.
.macro oms_row
 add a,#<_riding_oms_product
 ld l,a
 ld a,#>_riding_oms_product
 adc a,#0
 ld h,a
.endm

; DEBC <- floor((digit*m + DEBC)/256). The low byte contributes its carry
; even when it does not appear in the final six-byte right shift.
.macro oms_digit
 oms_row
 ld a,(hl)
 add a,c
 inc h
 ld a,(hl)
 adc a,b
 ld c,a
 inc h
 ld a,(hl)
 adc a,e
 ld b,a
 inc h
 ld a,(hl)
 adc a,d
 ld e,a
 inc h
 ld a,(hl)
 adc a,#0
 ld d,a
.endm

.macro oms_subtract
 ld a,c
 sub a,(hl)
 ld c,a
 inc h
 ld a,b
 sbc a,(hl)
 ld b,a
 inc h
 ld a,e
 sbc a,(hl)
 ld e,a
 inc h
 ld a,d
 sbc a,(hl)
 ld d,a
.endm

; Round ((omega*2^24 + signed_residual)*m)/2^48 once. Normalize the
; signed residual to three unsigned fractional digits by borrowing from
; omega. After six base-256 digits DEBC holds the quotient from bits 0..47.
; The last signed digit scales by exactly m, including at the clamp edges.
_body_oms::
 ld hl,#_Bike+20
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ld a,d
 add a,#2
 cp a,#4
 jr c,oms_in_range
 bit 7,d
 jp nz,oms_min
 jp oms_max
oms_in_range:
 ld hl,#_angular_residual+2
 bit 7,(hl)
 jr z,oms_normalized
 ld a,c
 or a,b
 jr nz,oms_borrow
 dec de
oms_borrow:
 dec bc
oms_normalized:
 ld a,(hl-)
 or a,(hl)
 dec hl
 or a,(hl)
 jr nz,oms_fraction
 ld a,c
 or a,b
 or a,e
 or a,d
 ret z
 push de
 push bc
 ld de,#0
 ld bc,#0
 jr oms_whole
oms_fraction:
 push de
 push bc
 ld a,(hl)
 oms_row
 inc h
 ld c,(hl)
 inc h
 ld b,(hl)
 inc h
 ld e,(hl)
 inc h
 ld d,(hl)
 ld a,(#_angular_residual+1)
 oms_digit
 ld a,(#_angular_residual+2)
 oms_digit
oms_whole:
 ldhl sp,#0
 ld a,(hl)
 oms_digit
 ldhl sp,#1
 ld a,(hl)
 oms_digit

 ; The last dropped byte is rounded with a single 0x80 bias.
 ld a,c
 add a,#128
 ld c,a
 jr nc,oms_rounded
 inc b
 jr nz,oms_rounded
 inc de
oms_rounded:
 ldhl sp,#2
 ld a,(hl+)
 or a,(hl)
 jp z,oms_small_positive
 ld a,(hl-)
 and a,(hl)
 inc a
 jr z,oms_small_negative
 ld a,(hl)
 oms_digit
 ldhl sp,#3
 ld a,(hl)
 add sp,#4
 or a,a
 ret z
 cp a,#1
 jr z,oms_add_high
 cp a,#0xfd
 jr z,oms_min
 ; For high digits -1 and -2 the mathematical result is negative, except
 ; that rounding near zero can produce zero (handled by small_negative).
 cpl
 inc a
 oms_row
 oms_subtract
 bit 7,d
 ret nz
 jr oms_min
oms_add_high:
 ld hl,#_riding_oms_product+1
 ld a,c
 add a,(hl)
 ld c,a
 inc h
 ld a,b
 adc a,(hl)
 ld b,a
 inc h
 ld a,e
 adc a,(hl)
 ld e,a
 inc h
 ld a,d
 adc a,(hl)
 ld d,a
 bit 7,d
 ret z
oms_max:
 ld de,#0x7fff
 ld bc,#0xffff
 ret
oms_min:
 ld de,#0x8000
 ld bc,#0
 ret
oms_small_negative:
 ; The high 16 bits of the normalized omega are -1. Fold their -m
 ; contribution into the final byte shift with full sign extension.
 ld hl,#_riding_oms_product+1
 oms_subtract
 ld a,d
 add a,a
 sbc a,a
 jr oms_small_shift
oms_small_positive:
 xor a
oms_small_shift:
 ld c,b
 ld b,e
 ld e,d
 ld d,a
 add sp,#4
 ret
