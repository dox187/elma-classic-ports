.globl near_rows_negative_120
.globl near_rows_negative_123
.globl near_rows_negative_163
.globl near_rows_negative_170
.globl near_rows_negative_169
.globl near_rows_positive_134
.globl near_upper_digits
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
 ld a,(hl)
 dec a
 cp #2
 jp c,near_check
slope_original_inputs:
 call slope_find
 jp nc,slope_fallback_dots
 ld a,h
 ldh (#slope_descriptor+1),a
 ld a,l
 ldh (#slope_descriptor),a
 ld a,#1
 ldh (#near_page),a
 ld a,(hl)
 or a
 jp z,slope_vertical_inputs
 cp #1
 jp z,slope_local_inputs
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
slope_pair_narrow:
 ; HL is the X row descriptor. The speed must fit signed16 and both
 ; coefficients must have signed high-digit planes.
 push hl
 ldhl sp,#8
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 add a
 sbc a
 cp (hl)
 jr nz,slope_pair_full
 inc hl
 cp (hl)
 jr nz,slope_pair_full
 pop hl
 push hl
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 cp #30
 jr z,slope_pair_full
 ld b,a
 inc hl
 ld a,(hl)
 cp #30
 jr z,slope_pair_full
 push de
 call slope_word_coordinate
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call roll_store_regs
 pop de
 pop hl
 inc hl
 inc hl
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 call slope_word_coordinate
 add sp,#2
 pop hl
 .rept 4
 inc hl
 .endm
 call roll_store_regs
 jp ground_return
slope_pair_full:
 pop hl
 ret
slope_word_coordinate:
 ; Signed word * Q14 coefficient fits signed32. Round at bit 13
 ; before shifting the high word and extending its sign.
 call slope_read_word
 ld a,d
 add #32
 jr nc,slope_coordinate_shift
 inc hl
slope_coordinate_shift:
 ld d,h
 ld e,l
 ld l,a
 ld a,d
 add a
 sbc a
 ld c,a
 ld b,a
 ld a,l
 add a
 rl e
 rl d
 add a
 rl e
 rl d
 rl c
 ret

.area _CODE_35
slope_local_inputs:
 inc hl
 ld a,(hl+)
 jr slope_local_jump
slope_local_pair:
 inc hl
 ld a,(hl+)
 inc hl
 inc hl
slope_local_jump:
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld h,d
 ld l,e
 jp slope_local_map
.area _CODE
slope_local_map:
 ld (#0x2000),a
 jp (hl)
.area _CODE_35
slope_project:
 ldhl sp,#8
 call slope_find
 jp nc,slope_pair_miss
slope_project_known:
 ld a,(hl)
 or a
 jp z,slope_vertical_project
 cp #1
 jr z,slope_local_pair
 call slope_pair_narrow

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

.area _HRAM
ground_projection_bank: .ds 1
slope_descriptor: .ds 2
near_page: .ds 1
near_slot: .ds 1
near_round: .ds 1
.area _CODE_35
; The low X byte has selected e=1 or 2. Check the remaining three
; tangent bytes before entering a factored path, including hash aliases.
near_check:
 ld a,(hl+)
 cp #2
 ld a,(hl+)
 jr z,near_e2
 cp #192
 jr nz,near_original
 ld a,(hl+)
 ld c,(hl)
 ld b,a
 ld a,c
 or a
 jr nz,near_e1_negative
 ld a,b
 cp #134
 jr nz,near_original
 ld a,#>near_rows_positive_134
 ld c,#32
 jp near_map_inputs
near_e1_negative:
 inc a
 jr nz,near_original
 ld c,#33
 ld a,b
 cp #87
 ld a,#>near_rows_negative_169
 jp z,near_map_inputs
 ld a,b
 cp #86
 ld a,#>near_rows_negative_170
 jp z,near_map_inputs
 ld a,b
 cp #93
 jr nz,near_original
 ld a,#>near_rows_negative_163
 jp near_map_inputs
near_e2:
 cp #192
 jr nz,near_original
 ld a,(hl+)
 ld b,a
 ld a,(hl)
 inc a
 jr nz,near_original
 ld c,#17
 ld a,b
 cp #10
 ld a,#>near_rows_negative_123
 jp z,near_map_inputs
 ld a,b
 cp #16
 ld a,#>near_rows_negative_120
 jp z,near_map_inputs
 ld a,b
 or a
 jr nz,near_original
 ld c,#16
 ld a,#255
 jp near_map_inputs
near_original:
 ldhl sp,#0
 jp slope_original_inputs
.area _CODE
; Six row pairs occupy consecutive 512-byte slots. Their top-digit
; records occupy consecutive 32-byte slots. Page 255 selects -128*y.
near_map_inputs:
 ldh (#near_page),a
 sub #>near_rows_positive_134
 swap a
 ldh (#near_slot),a
 ld a,c
 ldh (#near_round),a
 ld a,#13
 ld (#0x2000),a
 jp near_inputs

; Only a roll which selected a coefficient here can reuse it. Direct
; callers of the public output-pair ABI retain its complete tangent check.
near_project_select:
 ldh a,(#near_page)
 or a
 jp z,_riding_roll_project_pair
 cp #2
 jr c,slope_cached_pair
 jr z,ground_cached_pair
 cp #3
 jr z,ground_cached_flat
 ld a,#13
 ld (#0x2000),a
 jp near_project
; These continuations belong to the roll whose input dispatcher verified
; the tangent. Standalone callers still enter the public pair dispatcher.
ground_cached_flat:
 push hl
 jp ground_flat_pair
ground_cached_pair:
 push hl
 ldh a,(#ground_projection_bank)
 ld (#0x2000),a
 ldh a,(#near_slot)
 jp ground_project_29
slope_cached_pair:
 push hl
 ld a,#35
 ld (#0x2000),a
 ldh a,(#slope_descriptor+1)
 ld h,a
 ldh a,(#slope_descriptor)
 ld l,a
 jp slope_project_known
near_project_miss:
 call ground_restore
 jp _riding_roll_project_pair

.area _CODE_13
; With tangent (-16384+e,e*m), e=1 or 2, the input dot is exactly
; -x + round((x+m*y)/(16384/e)). The output pair uses the same denominator
; and signed m for (-s+round(s/(16384/e)),round(m*s/(16384/e))).
near_inputs:
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld bc,#8
 add hl,bc
 call near_dot
 jp nc,slope_fallback_dots
 push de
 push bc
 ldhl sp,#8
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call near_dot
 jp c,ground_resume_deltas
 add sp,#4
 jp slope_fallback_dots

near_dot:
 push hl
 inc hl
 inc hl
 ld a,(hl+)
 add a
 sbc a
 cp (hl)
 jr nz,near_dot_miss
 inc hl
 call near_product
 jr nc,near_dot_miss
 pop hl
 push hl
 ld a,(hl+)
 add c
 ld a,(hl+)
 adc b
 ld b,a
 ld a,(hl+)
 adc e
 ld e,a
 ld a,(hl)
 adc d
 ld d,a
 call near_shift
 pop hl
near_subtract:
 ld a,c
 sub (hl)
 ld c,a
 inc hl
 ld a,b
 sbc (hl)
 ld b,a
 inc hl
 ld a,e
 sbc (hl)
 ld e,a
 inc hl
 ld a,d
 sbc (hl)
 ld d,a
 scf
 ret
near_dot_miss:
 pop hl
 and a
 ret

; U[y0]+256*U[y1]+65536*S[y2] is m*y, biased by -256 for negative
; table factors. Full signed20 Y and signed24 X fit the factored sum.
; The signed top digit occupies one of sixteen slots in the shared page.
near_product:
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 add #8
 ld b,a
 sbc a
 cp (hl)
 jr nz,near_product_miss
 ld a,b
 cp #16
 jr nc,near_product_miss
 ldh a,(#near_page)
 inc a
 jr z,near_power
 ldh a,(#near_slot)
 or b
 ld b,a
 ldh a,(#near_page)
 ld h,a
 ld l,e
 ld c,(hl)
 inc h
 ld a,(hl)
 ld l,d
 ld e,(hl)
 dec h
 add (hl)
 ld d,a
 ld l,b
 ld h,#>near_upper_digits
 ld a,e
 adc (hl)
 ld e,a
 set 4,l
 ld a,#0
 adc (hl)
 ld b,d
 ld d,a
 scf
 ret
near_power:
 ; Multiply by -128 by putting -y in the upper three bytes and
 ; shifting right once. The width check above bounds the negation.
 ld a,b
 sub #8
 ld b,a
 xor a
 sub e
 ld c,a
 ld a,#0
 sbc d
 ld e,a
 ld a,#0
 sbc b
 ld d,a
 ld b,c
 ld c,#0
 sra d
 rr e
 rr b
 rr c
 scf
 ret
near_product_miss:
 and a
 ret

; The rounding byte supplies the Q13 or Q14 half and compensates the
; -256 table bias when present. The lowest product byte already contributed
; its carry to byte one.
near_shift:
 ldh a,(#near_round)
 add b
 ld b,a
 ld a,e
 adc #0
 ld e,a
 ld a,d
 adc #0
 ld d,a
near_shift_biased:
 add a
 sbc a
 ld l,a
 ld h,a
 ldh a,(#near_round)
 cp #32
 ld a,b
 jr nc,near_shift14
 add a
 rl e
 rl d
 rl l
near_shift14:
 .rept 2
 add a
 rl e
 rl d
 rl l
 .endm
 ld c,e
 ld b,d
 ld e,l
 ld d,h
 ret

near_project:
 push hl
 ldhl sp,#4
 call near_product
 jr nc,near_project_wide
 call near_shift
 pop hl
 push hl
 inc hl
 inc hl
 inc hl
 inc hl
 call near_store
 ldhl sp,#4
 inc hl
 ldh a,(#near_round)
 and #48
 add (hl)
 inc hl
 ld b,a
 ld a,(hl+)
 adc #0
 ld e,a
 ld a,(hl)
 adc #0
 ld d,a
 call near_shift_biased
 ldhl sp,#4
 call near_subtract
 pop hl
 call near_store
 jp ground_return
near_project_wide:
 pop hl
 jp near_project_miss
near_store:
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld a,e
 ld (hl+),a
 ld (hl),d
 ret
