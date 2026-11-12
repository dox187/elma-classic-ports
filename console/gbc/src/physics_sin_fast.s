; Exact full-phase sine with separate positive/negative interpolation tables.
; Stack ABI0 uint16 angle@sp2 -> signed16 DE, ROM0, no scratch RAM/stack.
; Banks 16/17 contain fsin(t), banks 18/19 fsin(32768+t), t=0..16383.
; CURRENT_BANK stays the caller; IRQ code must be ROM0 and never switch banks.
; Entry ROMB1=0, matching the exact multiplication data-window contract.
.module physics_sin_fast
.area _CODE
_riding_sin16::
 ldhl sp,#2
 ld e,(hl)
 inc hl
 ld d,(hl)
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
 ld a,(#__current_bank)
 ld c,a
 ld a,b
 ld (#0x2000),a
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld a,c
 ld (#0x2000),a
 ret
sine_endpoint:
 ld de,#0x4000
 bit 1,b
 ret z
 ld de,#0xc000
 ret
