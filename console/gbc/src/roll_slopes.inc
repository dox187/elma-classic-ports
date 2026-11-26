; Bank 35 resolves each tangent once for the two rolling input vectors.
; The fixed reader can visit all product banks without changing __current_bank.
; Each descriptor packs the mapped bank's low byte in B and its page in C.
.area _CODE
slope_begin_dots:
 ld a,#35
 ld (#0x2000),a
 jp slope_inputs
slope_fallback_dots:
 call ground_restore
 jp roll_default_dots

slope_read_word:
 ld a,b
 ld (#0x2000),a
 bit 7,b
 jr z,slope_word_mapped
 ld a,#1
 ld (#0x3000),a
slope_word_mapped:
 ld h,c
 call _riding_projection_read_signed
 jr slope_restore_reader

slope_read_product:
 ; Each little-endian input digit selects U[i] = 0x800000 + i*coefficient.
 ; Accumulate U[lo] + 256*U[mid] + 65536*U[high^128] modulo 2^40.
 ; The descriptor supplies the common bias for the two products.
 ; C=page, B=bank, DE=lower word, A=biased high digit.
 push af
 ld a,b
 ld (#0x2000),a
 bit 7,b
 jr z,slope_read
 ld a,#1
 ld (#0x3000),a
slope_read:
 ld h,c
 ld l,e
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
 pop af
 ld l,a
 inc h
 ld a,b
 add (hl)
 ld b,a
 dec h
 dec h
 ld a,c
 adc (hl)
 ld c,a
 inc h
 ld a,#0
 adc (hl)
 ld h,c
 ld l,b
 ld b,a
slope_restore_reader:
 xor a
 ld (#0x3000),a
 ld a,#35
 ld (#0x2000),a
 scf
 ret

.area _DATA
slope_bias: .ds 3
.area _CODE_35
; One validated row descriptor per coefficient serves both dot products.
slope_inputs:
 ; Hash the low bytes. Compare all four tangent bytes before using a row.
 ldhl sp,#0
 call slope_find
 jp nc,slope_fallback_dots
 ld a,(hl)
 or a
 jp z,slope_vertical_inputs
 add sp,#-4
 ld a,(hl+)
 ld b,(hl)
 inc hl
 ld c,a
 push bc
 ld a,(hl+)
 ld b,(hl)
 inc hl
 ld c,a
 push bc
 call slope_install_bias
 ldhl sp,#14
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#8
 add hl,de
 call slope_dot
 jr nc,slope_drop_both
 ldhl sp,#4
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld a,e
 ld (hl+),a
 ld (hl),d
 ldhl sp,#12
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call slope_dot
 jr nc,slope_drop_both
 add sp,#4
 jp ground_resume_deltas
slope_drop_both:
 add sp,#8
 jp slope_fallback_dots

; HL points at consecutive x32,y32. Caller has Y,X descriptors on stack.
slope_dot:
 ; Full five-plane rows also admit a shorter signed16 product. The
 ; supplemental three-plane rows always use the raw digit reader.
 push hl
 ldhl sp,#5
 ld a,(hl+)
 cp #30
 jr z,slope_dot_wider
 inc hl
 ld a,(hl)
 cp #30
 jr z,slope_dot_wider
 pop hl
 push hl
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 add a
 sbc a
 cp (hl)
 jr nz,slope_dot_wider
 inc hl
 cp (hl)
 jr nz,slope_dot_wider
 inc hl
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 add a
 sbc a
 cp (hl)
 jr nz,slope_dot_wider
 inc hl
 cp (hl)
 jr nz,slope_dot_wider
 push de
 ld d,b
 ld e,c
 ldhl sp,#8
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 call slope_read_word
 push hl
 push de
 ldhl sp,#10
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 ldhl sp,#4
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 call slope_read_word
 ld c,l
 ld b,h
 pop hl
 add hl,de
 pop de
 ld a,e
 adc c
 ld e,a
 ld a,d
 adc b
 ld d,a
 ld a,h
 add #32
 jr nc,slope_word_shift
 inc de
slope_word_shift:
 ld h,d
 ld l,e
 ld b,a
 ld a,d
 add a
 sbc a
 ld d,a
 ld e,a
 ld a,b
 .rept 2
 add a
 rl l
 rl h
 rl e
 .endm
 ld b,h
 ld c,l
 add sp,#4
 scf
 ret
slope_dot_wider:
 pop hl
 push hl
 ldhl sp,#6
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 pop hl
 push hl
 call slope_product
 jr nc,slope_drop_vector
 push bc
 push hl
 push de
 ldhl sp,#10
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#4
 add hl,de
 call slope_product
 jr nc,slope_drop_product
 ; Add both unrounded signed40 products, carrying byte 0 into byte 1.
 push hl
 ldhl sp,#2
 ld a,(hl+)
 add e
 ld a,(hl)
 adc d
 ld (hl+),a
 pop de
 ld a,(hl+)
 adc e
 ld e,a
 ld a,(hl+)
 adc d
 ld d,a
 inc hl
 ld a,(hl)
 adc b
 ld b,a
 ldhl sp,#1
 ld a,(hl)
 ld h,d
 ld l,e
 ld d,a
 add sp,#8
 jr slope_round
slope_drop_product:
 add sp,#6
slope_drop_vector:
 add sp,#2
 and a
 ret

; Remove the table bias and round the complete sum, including carry from
; its second byte. Signed20 inputs keep the true quotient within signed24.
slope_round:
 ld a,d
 add #32
 ld d,a
 jr nc,slope_shift
 inc hl
 ld a,h
 or l
 jr nz,slope_shift
 inc b
slope_shift:
 ld a,(#slope_bias)
 add l
 ld l,a
 ld a,(#slope_bias+1)
 adc h
 ld h,a
 ld a,(#slope_bias+2)
 adc b
 ld b,a
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

slope_product:
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ; Exact width check, with enough headroom for both products in signed40.
 add #8
 push bc
 ld b,a
 sbc a
 cp (hl)
 ld a,b
 pop bc
 jr nz,slope_product_wide
 cp #16
 jr nc,slope_product_wide
 add #120
 jp slope_read_product
slope_product_wide:
 and a
 ret

; Match the complete tangent before selecting the wide speed projection.
.area _CODE
slope_begin_pair:
 ld a,#35
 ld (#0x2000),a
 jp slope_project
slope_pair_miss:
 call ground_restore
 jp roll_default_pair

.area _CODE_35
slope_project:
 ldhl sp,#8
 call slope_find
 jp nc,slope_pair_miss
 ld a,(hl)
 or a
 jp z,slope_vertical_project
 ; Descriptor holds four product-page bytes, three dot bias bytes, then
 ; the independent X,Y bias corrections for a single product.
 push hl
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 ldhl sp,#6
 call slope_product
 jr nc,slope_project_wide
 push bc
 push hl
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld bc,#7
 add hl,bc
 call slope_install_bias
 pop hl
 pop bc
 call slope_round
 push de
 push bc
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 inc hl
 inc hl
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 ldhl sp,#10
 call slope_product
 jr nc,slope_project_second_miss
 push bc
 push hl
 ldhl sp,#8
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld bc,#10
 add hl,bc
 call slope_install_bias
 pop hl
 pop bc
 call slope_round
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push bc
 ld bc,#4
 add hl,bc
 pop bc
 call slope_store
 ld de,#-8
 add hl,de
 pop bc
 pop de
 call slope_store
 add sp,#4
 jp ground_return
slope_project_second_miss:
 add sp,#4
slope_project_wide:
 add sp,#2
 jp slope_pair_miss
slope_store:
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ret
slope_install_bias:
 ld a,(hl+)
 ld (#slope_bias),a
 ld a,(hl+)
 ld (#slope_bias+1),a
 ld a,(hl)
 ld (#slope_bias+2),a
 ret

slope_find:
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 xor e
 rlca
 rlca
 rlca
 xor d
 ld l,a
 ld h,#>slope_hash
 ld a,(hl)
 or a
 jr z,slope_absent
 ld l,a
 ld h,#>slope_addresses
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(hl+)
 cp e
 jr nz,slope_absent
 ld a,(hl+)
 cp d
 jr nz,slope_absent
 ld a,(hl+)
 cp c
 jr nz,slope_absent
 ld a,(hl+)
 cp b
 jr nz,slope_absent
 scf
 ret
slope_absent:
 and a
 ret

; On a positive unit-Y tangent the two projections are y + round(20*x/2^14).
slope_vertical_inputs:
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#8
 add hl,de
 call slope_vertical_dot
 jp nc,slope_fallback_dots
 push de
 push bc
 ldhl sp,#8
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call slope_vertical_dot
 jp c,ground_resume_deltas
 add sp,#4
 jp slope_fallback_dots
slope_vertical_dot:
 push hl
 call slope_vertical_component
 pop hl
 ret nc
 .rept 4
 inc hl
 .endm
 ld a,d
 add a
 sbc a
 ld b,a
 ld a,(hl+)
 add e
 ld c,a
 ld a,(hl+)
 adc d
 ld d,a
 ld a,(hl+)
 adc b
 ld e,a
 ld a,(hl)
 adc b
 ld h,(hl)
 ld l,a
 xor b
 bit 7,a
 jr z,slope_vertical_done
 ld a,h
 xor b
 bit 7,a
 jr nz,slope_vertical_done
 bit 7,b
 jr nz,slope_vertical_min
 ld de,#0x7fff
 ld bc,#0xffff
 scf
 ret
slope_vertical_min:
 ld de,#0x8000
 ld bc,#0
 scf
 ret
slope_vertical_done:
 ld b,d
 ld d,l
 scf
 ret

slope_vertical_component:
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 add a
 ld a,(hl+)
 adc #16
 ld b,a
 sbc a
 cp (hl)
 jr nz,slope_vertical_wide
 ld a,b
 cp #32
 jr nc,slope_vertical_wide
 ld h,#>slope_vertical_rows
 ld l,d
 ld d,(hl)
 inc h
 ld a,(hl)
 cp e
 ld a,d
 adc #0
 ld e,a
 add a
 sbc a
 ld d,a
 ld a,b
 cp #16
 jr z,slope_vertical_narrow
 inc h
 ld l,b
 ld a,e
 add (hl)
 ld e,a
 set 5,l
 ld a,d
 adc (hl)
 ld d,a
slope_vertical_narrow:
 scf
 ret
slope_vertical_wide:
 and a
 ret
slope_vertical_project:
 ldhl sp,#4
 call slope_vertical_component
 jp nc,slope_pair_miss
 pop hl
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 add a
 sbc a
 ld (hl+),a
 ld (hl+),a
 ld d,h
 ld e,l
 ldhl sp,#2
 .rept 4
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 jp ground_return
