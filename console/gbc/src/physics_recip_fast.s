; Exact clamp((kx>>4)^2+(ky>>4)^2)>>5 index for the reaction table.
; Inputs signed16 stack ABI0; returns uint8 E. Fixed bank8 near entry.
.module physics_recip_fast
.area _CODE_8
_riding_recip_index::
 ldhl sp,#2
 ld e,(hl)
 inc hl
 ld d,(hl)
 call recip_square
 push hl
 ldhl sp,#6
 ld e,(hl)
 inc hl
 ld d,(hl)
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
 sra d
 rr e
 sra d
 rr e
 sra d
 rr e
 sra d
 rr e
 bit 7,d
 jr z,recip_positive
 xor a
 sub a,e
 ld e,a
 ld a,#0
 sbc a,d
 ld d,a
recip_positive:
 ld a,d
 or a
 jr nz,recip_limit
 ld a,e
 cp #127
 jr c,recip_load
recip_limit:
 ld e,#127
recip_load:
 ld d,#0
 sla e
 rl d
 ld hl,#recip_squares
 add hl,de
 ld a,(hl+)
 ld h,(hl)
 ld l,a
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
 .dw 7744,7921,8100,8281,8464,8649,8836,9025
 .dw 9216,9409,9604,9801,10000,10201,10404,10609
 .dw 10816,11025,11236,11449,11664,11881,12100,12321
 .dw 12544,12769,12996,13225,13456,13689,13924,14161
 .dw 14400,14641,14884,15129,15376,15625,15876,16129
