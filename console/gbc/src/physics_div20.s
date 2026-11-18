.module div20
.area _CODE
_riding_floor_div20::
 ldhl sp,#2
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,h
 and a,#128
 push af
 jr z,div20_positive
 ld a,e
 cpl
 ld e,a
 ld a,d
 cpl
 ld d,a
 ld a,l
 cpl
 ld l,a
 ld a,h
 cpl
 ld h,a
div20_positive:
 ; Complementing a negative input above maps floor(x/20) to
 ; ~floor(~x/20). Skip known-zero leading bytes without changing rounding.
 ld a,h
 or a,l
 jr nz,div20_full
 ld a,d
 or a,a
 jr nz,div20_word
 ld b,#8
 ld c,#0
div20_byte_loop:
 sla e
 ld a,c
 rla
 cp a,#20
 jr c,div20_byte_keep
 sub a,#20
 inc e
div20_byte_keep:
 ld c,a
 dec b
 jr nz,div20_byte_loop
 jr div20_sign
div20_word:
 ld b,#16
 ld c,#0
div20_word_loop:
 sla e
 rl d
 ld a,c
 rla
 cp a,#20
 jr c,div20_word_keep
 sub a,#20
 inc e
div20_word_keep:
 ld c,a
 dec b
 jr nz,div20_word_loop
 jr div20_sign
div20_full:
 ld b,#32
 ld c,#0
div20_loop:
 sla e
 rl d
 rl l
 rl h
 ld a,c
 rla
 cp a,#20
 jr c,div20_keep
 sub a,#20
 inc e
div20_keep:
 ld c,a
 dec b
 jr nz,div20_loop
div20_sign:
 pop af
 or a,a
 ret z
 ld a,e
 cpl
 ld e,a
 ld a,d
 cpl
 ld d,a
 ld a,l
 cpl
 ld l,a
 ld a,h
 cpl
 ld h,a
 ret
