; Both unsigned digits are biased by 0x800000. The two upper signed planes
; remove the bias for a word input and supply the sign for a third digit.
.macro map_product read,page,?wide,?miss
read:
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 add a
 sbc a
 cp (hl)
 jr nz,wide
 inc hl
 cp (hl)
 jr nz,miss
 ld l,e
 ld h,#page
 ld c,(hl)
 inc h
 ld b,(hl)
 inc h
 ld e,(hl)
 ld l,d
 ld a,c
 add (hl)
 ld d,a
 inc h
 ld a,b
 adc (hl)
 ld c,a
 inc h
 ld a,#0
 adc (hl)
 ld h,a
 ld l,c
 add a
 sbc a
 ld b,a
 scf
 ret
wide:
 ld a,(hl+)
 ld c,a
 add a
 sbc a
 cp (hl)
 jr nz,miss
 push bc
 ld l,e
 ld h,#page
 ld c,(hl)
 inc h
 ld b,(hl)
 inc h
 ld e,(hl)
 ld l,d
 ld a,c
 add (hl)
 ld d,a
 dec h
 dec h
 ld a,b
 adc (hl)
 ld b,a
 inc h
 ld a,#0
 adc (hl)
 ld c,a
 pop hl
 ld h,#(page+2)
 ld a,b
 add (hl)
 ld b,a
 inc h
 ld a,c
 adc (hl)
 ld c,a
 inc h
 ld a,#0
 adc (hl)
 ld h,a
 ld a,b
 sub #128
 ld l,a
 ld a,c
 sbc #0
 ld c,a
 ld a,h
 sbc #0
 ld h,c
 ld b,a
 scf
 ret
miss:
 and a
 ret
.endm

.macro map_tangent inputs,project,xpage,read_x,read_y,?dot,?first_miss,?second_miss,?project_wide,?qx,?qy
; Compute both unrounded coordinate products, add, then round the dot once.
inputs::
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#8
 add hl,de
 call dot
 jp nc,slope_fallback_dots
 push de
 push bc
 ldhl sp,#8
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call dot
 jp c,ground_resume_deltas
 add sp,#4
 jp slope_fallback_dots
dot:
 push hl
 call read_x
 jr nc,first_miss
 push bc
 push hl
 push de
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#4
 add hl,de
 call read_y
 jr nc,second_miss
 jp rom_slope_sum
second_miss:
 add sp,#6
first_miss:
 add sp,#2
 and a
 ret
 map_product read_x,xpage
 map_product read_y,(xpage+5)
; A signed16 speed shares one width check across both output coordinates.
project::
 ldhl sp,#4
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 add a
 sbc a
 cp (hl)
 jr nz,project_wide
 inc hl
 cp (hl)
 jp nz,slope_pair_miss
 push de
 call qx
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call rom_slope_qstore
 pop de
 push hl
 call qy
 pop hl
 call rom_slope_qstore
 add sp,#2
 jp ground_return
project_wide:
 ldhl sp,#4
 call read_x
 jp nc,slope_pair_miss
 call rom_slope_round
 pop hl
 call rom_slope_store
 push hl
 ldhl sp,#4
 call read_y
 call rom_slope_round
 pop hl
 call rom_slope_store
 jp ground_return
qx:
 ld h,#xpage
 jp rom_slope_qword
qy:
 ld h,#(xpage+5)
 jp rom_slope_qword
.endm

rom_slope_sum:
 ld c,b
 ld b,h
 ld a,l
 ld h,d
 ld l,e
 pop de
 add hl,de
 ld d,h
 pop hl
 adc l
 ld l,a
 ld a,h
 adc b
 ld h,a
 ld e,c
 pop bc
 ld a,b
 adc e
 ld b,a
 add sp,#2
rom_slope_round:
 ld a,d
 add #32
 ld d,a
 jr nc,rom_slope_shift
 inc hl
 ld a,h
 or l
 jr nz,rom_slope_shift
 inc b
rom_slope_shift:
 ; The tangent magnitudes sum to at most 32767. The rounded signed24
 ; input dot therefore fits 25 bits, with the top byte set by its sign.
 ld a,b
 add a
 sbc a
 ld c,a
 ld a,d
 .rept 2
 add a
 rl l
 rl h
 rl b
 .endm
 ld d,c
 ld e,b
 ld b,h
 ld c,l
 scf
 ret
rom_slope_store:
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ret


rom_slope_qstore:
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld (hl+),a
 ret
; Rounded word projection. Bits below byte one cannot carry into the Q14 half.
rom_slope_qword:
 ld l,e
 ld a,(hl)
 add #32
 ld c,a
 inc h
 ld a,(hl)
 adc #0
 ld b,a
 inc h
 ld l,d
 ld a,(hl)
 add c
 ld c,a
 inc h
 ld a,(hl)
 adc b
 ld e,a
 inc h
 ld a,(hl)
 adc #0
 ld d,a
 add a
 sbc a
 ld b,a
 ld a,c
 .rept 2
 add a
 rl e
 rl d
 .endm
 ret
