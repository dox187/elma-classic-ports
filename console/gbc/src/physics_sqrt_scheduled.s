; Exact floor(sqrt(n)), unsigned20 stack ABI. Each bucket stores its
; highest root and the first low digit that reaches that square.
.module riding_sqrt_scheduled
.area _CODE
_riding_isqrt20::
 ldhl sp,#4
 ld a,(hl-)
 and #15
 ld d,a
 ld a,(hl-)
 ld c,a
 ld e,(hl)
 ld a,d
 or a
 jr nz,sqrt_large
 ld a,c
 cp #64
 jr c,sqrt_small
sqrt_large:
 ld a,#15
 ld (#0x2000),a
 ld a,d
 add a,a
 add a,#>_riding_sqrt_large
 ld h,a
 ld l,c
 ld c,(hl)
 inc h
 ld a,e
 cp (hl)
 ld a,c
 sbc #0
 ld e,a
 ld l,d
 ld h,#>_riding_sqrt_upper
 ld a,(hl)
 sbc #0
 ld d,a
 jr sqrt_restore

sqrt_small:
; C:E is an unsigned 14-bit squared length. The root fits in E.
_riding_isqrt14_regs::
 ld a,#35
 ld (#0x2000),a
 ld a,c
 or a
 jr z,sqrt_byte
 ; Ten-bit bucket index = n >> 4. Build its page and low digit.
 swap a
 ld b,a
 and #15
 add a,a
 add a,#>_riding_sqrt_small
 ld h,a
 ld a,e
 swap a
 and #15
 ld l,a
 ld a,b
 and #0xf0
 or l
 ld l,a
 ld c,(hl)
 inc h
 ld a,e
 and #15
 cp (hl)
 ld a,c
 sbc #0
 ld e,a
 jr sqrt_restore
sqrt_byte:
 ld h,#>_riding_sqrt_byte
 ld l,e
 ld e,(hl)
sqrt_restore:
 ldh a,(#__current_bank)
 ld (#0x2000),a
 ret
