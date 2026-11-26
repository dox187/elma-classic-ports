; Exact signed40 Euclidean division. A:BCDE is the numerator; return HLDE
; modulo 2^32 and the remainder in A. Leading sign bytes already equal the
; matching quotient bytes. A negative prefix starts with remainder 19 because
; -1 = (-1)*20 + 19. All following bytes use the ordinary unsigned rows.
.module riding_scheduled_div20
.area _CODE

.macro divide_digit digit
 add a,a
 add a,#>div20_rows
 ld h,a
 ld l,digit
 ld digit,(hl)
 inc h
 ld a,(hl)
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
 or a
 jr z,div20_positive
 inc a
 jr z,div20_negative
 ; A genuine fifth digit contributes only its remainder to the quotient.
 ld l,h
 ld h,#>div20_top
 ld a,(hl)
 jr div20_four
div20_positive:
 cp b
 jr nz,div20_four
 cp c
 jr nz,div20_three
 cp d
 jr nz,div20_two
 jr div20_one
div20_negative:
 dec a
 cp b
 ld h,#19
 jr nz,div20_four_negative
 cp c
 jr nz,div20_three_negative
 cp d
 ld a,h
 jr z,div20_one
 jr div20_two
div20_four_negative:
 ld a,h
 jr div20_four
div20_three_negative:
 ld a,h
 jr div20_three
div20_four:
 divide_digit b
div20_three:
 divide_digit c
div20_two:
 divide_digit d
div20_one:
 divide_digit e
 ld h,b
 ld l,c
 ld b,a
 ld a,(#__current_bank)
 ld (#0x2000),a
 ld a,b
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
  .db (row*256 + digit)%20
  digit = digit + 1
 .endm
 row = row + 1
.endm
div20_top:
digit = 0
.rept 128
 .db digit%20
 digit = digit + 1
.endm
digit = 0
.rept 128
 ; -128..-1 modulo 20 = 12..19 cyclically.
 .db (digit+12)%20
 digit = digit + 1
.endm
