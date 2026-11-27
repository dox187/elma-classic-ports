.module normal_deep
.area _CODE_33
; Deep physical vectors have 0 <= abs(axis) <= floor(sqrt(d2)) <= 127.
; At that size each fractional quotient digit needs one byte of remainder.
; Keep the full signed solver for callers supplying a nonphysical d2.
normal_fraction::
 ld hl,#normal_cache_key+7
 ld d,(hl)
 dec hl
 ld e,(hl)
 push de
 dec hl
 ld d,(hl)
 dec hl
 ld e,(hl)
 push de
 call _riding_isqrt20
 add sp,#4
 ld a,d
 or a
 jr nz,normal_fraction_miss
 ld a,e
 cp #128
 jr nc,normal_fraction_miss
 ld c,a
 or a
 jr z,normal_fraction_zero
 ld hl,#normal_cache_key
 call normal_fraction_axis
 or a
 ret z
 push hl
 ld hl,#normal_cache_key+2
 call normal_fraction_axis
 pop de
 or a
 ret z
normal_fraction_store:
 ld a,l
 ld (#normal_cache_value+2),a
 ld a,h
 ld (#normal_cache_value+3),a
 ld hl,#normal_cache_value
 ld a,e
 ld (hl+),a
 ld (hl),d
 ld a,c
 ld (#normal_cache_value+4),a
 xor a
 ld (#normal_cache_value+5),a
 ld a,#1
 ld (#normal_cache_valid),a
 ret
normal_fraction_zero:
 ld de,#0
 ld hl,#16384
 jr normal_fraction_store
normal_fraction_miss:
 xor a
 ret

normal_fraction_axis:
 ld a,(hl+)
 ld e,a
 ld a,(hl)
 ld b,a
 or a
 jr z,normal_fraction_unsigned
 inc a
 jr nz,normal_fraction_miss
 xor a
 sub e
 jr z,normal_fraction_miss      ; -256, outside the narrow domain
 ld e,a
normal_fraction_unsigned:
 ld a,c
 sub e
 jr c,normal_fraction_miss
 ld hl,#16384
 jr z,normal_fraction_sign
 ld hl,#0
 ld a,e
 ; After each digit, 0 <= remainder < C. Hence doubling also fits A.
 .macro normal_fraction_bit byte,digit,?next
 add a
 cp c
 jr c,next
 sub c
 set digit,byte
next:
 .endm
 .irp digit,5,4,3,2,1,0
 normal_fraction_bit h,digit
 .endm
 .irp digit,7,6,5,4,3,2,1,0
 normal_fraction_bit l,digit
 .endm
normal_fraction_sign:
 bit 7,b
 jr z,normal_fraction_done
 xor a
 sub l
 ld l,a
 sbc a,a
 sub h
 ld h,a
normal_fraction_done:
 ld a,#1
 ret
