; Exact signed40 Euclidean division. A:BCDE is the numerator; return HLDE
; modulo 2^32 and the remainder in A. Leading sign bytes already equal the
; matching quotient bytes. A negative prefix starts with remainder 19 because
; -1 = (-1)*20 + 19. All following bytes use the ordinary unsigned rows.
.module riding_scheduled_div20
.area _CODE

; H is the quotient page for the prefix remainder. Each transition byte
; directly selects the next quotient page, including when the prefix is
; negative. The final transition encodes the ordinary remainder in bits 1..5.
.macro divide_digit digit
 ld l,digit
 ld digit,(hl)
 inc h
 ld h,(hl)
.endm

_riding_floor_div20::
 ldhl sp,#2
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ld a,b
 add a,a
 sbc a,a
_riding_force_divmod20::
 ld h,a
 ld a,#35
 ld (#0x2000),a
 ld a,h
 call _riding_force_divmod20_mapped
 ld h,b
 ld l,c
 ld b,a
 ldh a,(#__current_bank)
 ld (#0x2000),a
 ld a,b
 ret

; A:BCDE is signed40. Return its quotient modulo 2^32 in BCDE and
; its remainder in A. Bank 35 stays selected across adjacent axes.
_riding_force_divmod20_mapped::
 ld h,#>div20_rows
 or a
 jr z,div20_skip
 inc a
 jr nz,div20_full
 dec a
 ld h,#>(div20_rows+38*256)       ; signed prefix -1 = -1*20 + 19
div20_skip:
 cp b
 jr nz,div20_four
 cp c
 jr nz,div20_three
 cp d
 jr z,div20_one
 jr div20_two
div20_full:
 ; A signed fifth digit is itself a byte following either zero or -1.
 ; Its quotient lies above bit 31. Only its remainder page survives.
 dec a
 ld l,a
 ld h,#>(div20_rows+256)
 bit 7,a
 jr z,div20_prefix
 ld h,#>(div20_rows+39*256)
div20_prefix:
 ld h,(hl)
div20_four:
 divide_digit b
div20_three:
 divide_digit c
div20_two:
 divide_digit d
div20_one:
 ld l,e
 ld e,(hl)
 inc h
 ld a,(hl)
 rrca
 sub a,#0x20
 ret

.area _CODE_35
_riding_div20_rows::
div20_rows:
row = 0
.rept 20
 digit = 0
 .rept 256
  .db (row*256 + digit)/20
  digit = digit + 1
 .endm
 digit = 0
 .rept 256
  .db 0x40 + 2*((row*256 + digit)%20)
  digit = digit + 1
 .endm
 row = row + 1
.endm
