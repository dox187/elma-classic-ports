; Read the exact packed signed wave with the ordinary sine ABI.
.module physics_sin_fast
.area _CODE
_riding_sin16::
 ldhl sp,#2
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld a,(#__current_bank)
 push af
 ld a,#1
 ld (#0x2000),a
 call sine_reduce
 pop af
 ld (#0x2000),a
 ret
.area _CODE_1
sine_reduce:
 ld a,d
 rlca
 and a,#1
 add a,a
 add a,#16
 ld b,a
 res 7,d
 bit 6,d
 jr z,sine_phase_ready
 xor a
 sub a,e
 ld e,a
 ld a,#0x80
 sbc a,d
 ld d,a
sine_phase_ready:
 bit 6,d
 jr nz,sine_endpoint
 bit 5,d
 jr z,sine_bank_ready
 inc b
sine_bank_ready:
 ld h,d
 ld l,e
 add hl,hl
 ld a,h
 and a,#0x3f
 or a,#0x40
 ld h,a
 call sine_read
 bit 1,b
 jr nz,sine_negative_word
 res 7,d
 jr sine_word_ready
sine_negative_word:
 ld a,d
 rlca
 ld a,e
 cpl
 adc a,#0
 ld e,a
 ld a,d
 res 7,a
 cpl
 adc a,#0
 ld d,a
sine_word_ready:
 ret
.area _CODE_1
sine_endpoint:
 ld de,#0x4000
 bit 1,b
 ret z
 ld de,#0xc000
 ret

.area _CODE
sine_read:
 ld a,b
 and a,#0xfd
 ld (#0x2000),a
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld a,#1
 ld (#0x2000),a
 ret
