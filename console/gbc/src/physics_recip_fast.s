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
_riding_recip_index_regs::
 call recip_square
 push hl
 ld d,b
 ld e,c
 call recip_square
 pop de
 add hl,de
 ld a,h
 cp #32
 jr nc,recip_max
 ld a,l
 rlca
 rlca
 rlca
 and #7
 ld e,a
 ld a,h
 add a,a
 add a,a
 add a,a
 or e
 ld e,a
 ret
recip_max:
 ld e,#255
 ret
recip_square:
 ; If DE >> 4 cannot fit a signed byte, its square alone saturates
 ; the index. Otherwise the middle two nibbles are its exact low byte.
 ld a,d
 add a,#8
 cp #16
 jr nc,recip_limit
 ld a,d
 xor e
 and #15
 xor e
 swap a
 bit 7,a
 jr z,recip_magnitude
 cpl
 inc a
recip_magnitude:
 ; 90^2 >> 5 = 253, while 91^2 >> 5 already exceeds 255.
 cp #91
 jr nc,recip_limit
 ld e,a
 ld d,#0
 sla e
 rl d
 ld hl,#recip_squares
 add hl,de
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ret
recip_limit:
 ld hl,#8192
 ret
recip_squares:
 .dw 0,1,4,9,16,25,36,49
 .dw 64,81,100,121,144,169,196,225
 .dw 256,289,324,361,400,441,484,529
 .dw 576,625,676,729,784,841,900,961
 .dw 1024,1089,1156,1225,1296,1369,1444,1521
 .dw 1600,1681,1764,1849,1936,2025,2116,2209
 .dw 2304,2401,2500,2601,2704,2809,2916,3025
 .dw 3136,3249,3364,3481,3600,3721,3844,3969
 .dw 4096,4225,4356,4489,4624,4761,4900,5041
 .dw 5184,5329,5476,5625,5776,5929,6084,6241
 .dw 6400,6561,6724,6889,7056,7225,7396,7569
 .dw 7744,7921,8100
