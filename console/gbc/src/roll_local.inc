; A signed20 coordinate is lo + 256*mid + 65536*top. Two unsigned
; byte products carry the common 0x80800000 bias. The signed top table
; supplies top*k - 0x8080 in the upper three bytes of the product.
.macro local_product entry,p0,p1,p2,upper,?miss
entry:
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 add #8
 ld c,a
 sbc a
 cp (hl)
 jr nz,miss
 ld a,c
 cp #16
 jr nc,miss
 push bc
 ld l,e
 ld h,#p0
 ld e,(hl)
 ld h,#p1
 ld b,(hl)
 ld h,#p2
 ld c,(hl)
 ld l,d
 ld h,#p0
 ld a,b
 add (hl)
 ld d,a
 ld h,#p1
 ld a,c
 adc (hl)
 ld b,a
 ld h,#p2
 ld a,#0
 adc (hl)
 ld c,a
 pop hl
 set 7,l
 ld h,#upper
 ld a,b
 add (hl)
 ld b,a
 set 4,l
 ld a,c
 adc (hl)
 ld c,a
 res 4,l
 set 5,l
 ld a,#0
 adc (hl)
 ld h,c
 ld l,b
 ld b,a
 scf
 ret
miss:
 and a
 ret
.endm

; Both dots and the output pair execute alongside their byte-product pages.
.macro local_tangent inputs,project,read_x,read_y,sum,round,store,?dot,?first_miss,?second_miss
inputs:
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
 jp sum
second_miss:
 add sp,#6
first_miss:
 add sp,#2
 and a
 ret
project:
 ldhl sp,#4
 call read_x
 jp nc,slope_pair_miss
 ; The Y reader has the identical width test on the same speed.
 ld c,d
 call round
 pop hl
 call store
 push hl
 ldhl sp,#4
 call read_y
 ld c,d
 call round
 pop hl
 call store
 jp ground_return
.endm

.macro local_finish sum,round,store,?ready
; B:HL:DE holds Y, and the stack holds X as its low, middle, high words.
sum:
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
 ld c,d
round:
 ld a,c
 add #32
 ld d,a
 jr nc,ready
 inc hl
 ld a,h
 or l
 jr nz,ready
 inc b
ready:
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
 rl c
 .endm
 ld d,c
 ld e,b
 ld b,h
 ld c,l
 scf
 ret
store:
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ret
.endm
