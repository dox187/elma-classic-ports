; Exact clamp((kx>>4)^2+(ky>>4)^2)>>5 index for the reaction table.
; Inputs signed16 stack ABI0; returns uint8 E. Fixed bank8 near entry.
.module physics_recip_fast
.area _CODE_8
_riding_recip_index::
 ldhl sp,#2
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld b,(hl)
 ld c,a
; For signed 12-bit arms the middle two nibbles are the signed byte
; floor(arm/16). Beyond that range one square already saturates the sum.
; Each low page byte is (square mod 32)*8 so the addition's carry is
; exactly the rounding bit for the sum of the two square quotients.
.macro recip_offset high,low
 ld a,high
 xor low
 and #15
 xor low
 swap a
 ld low,a
 ld high,#0
.endm
_riding_recip_index_regs::
 ld a,d
 add a,#8
 cp #16
 jr nc,recip_max
 ld a,b
 add a,#8
 cp #16
 jr nc,recip_max
 recip_offset d,e
 recip_offset b,c
 ld hl,#recip_rows
 add hl,de
 ld d,h
 ld e,l
 ld hl,#recip_rows
 add hl,bc
 ld a,(de)
 add (hl)
 inc d
 inc h
 ld a,(de)
 adc (hl)
 ld e,a
 ret nc
recip_max:
 ld e,#255
 ret

recip_rows:

digit = 0
 .rept 256
 .db ((digit*digit)&31)*8
 digit = digit+1
 .ifeq digit-128
 digit = -128
 .endif
 .endm
recip_whole:
digit = 0
 .rept 256
 .ifgt (digit*digit)-8191
 .db 255
 .else
 .db (digit*digit)/32
 .endif
 digit = digit+1
 .ifeq digit-128
 digit = -128
 .endif
 .endm
