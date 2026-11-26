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
 .ifdef ROLL_DIRECTORY_BANK
 ; Six factored near-horizontal tangents have low X byte 1 or 2.
 ; For other inputs the packed directory is the first exact tag check.
 ldhl sp,#0
 ld a,(hl)
 dec a
 cp #2
 jp nc,rom_slope_begin
 .endif
 ld a,#35
 ld (#0x2000),a
 .ifdef ROLL_DIRECTORY_BANK
 jp near_check
 .else
 jp slope_inputs
 .endif
slope_fallback_dots:
 call ground_restore
 jp roll_default_dots

slope_read_word:
 ld a,b
 ld (#0x2000),a
 rlca
 ld (#0x3000),a
 ; The sign-extended raw word product feeds the full dot accumulator.
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

slope_read_product:
 ; U[lo] + (U[mid] << 8) + (S[top] << 16) is the exact
 ; signed24 product plus 0x800000. The signed upper planes share
 ; byte zero with U. Remove the fixed bias from the accumulated digits.
 push af
 ld a,b
 ld (#0x2000),a
 rlca
 ld (#0x3000),a
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
slope_restore_high:
 xor a
 ld (#0x3000),a
 ret

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
 .ifdef ROLL_DIRECTORY_BANK
 jp rom_slope_begin
rom_slope_legacy_inputs:
 .endif
 call slope_find
 .ifdef ROLL_DIRECTORY_BANK
 jp nc,slope_word_inputs
 .else
 jp nc,slope_fallback_dots
 .endif
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
 call slope_install_rows
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#8
 add hl,de
 jp slope_generic_inputs

.area _CODE
slope_generic_inputs:
 call slope_dot
 jr nc,slope_generic_fallback
 push de
 push bc
 ldhl sp,#8
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call slope_dot
 jr c,slope_generic_resume
 add sp,#4
slope_generic_fallback:
 call slope_restore_high
 jp slope_fallback_dots
slope_generic_resume:
 call slope_restore_high
 jp ground_resume_deltas

.area _CODE_35

; Keep the verified pair for both input dots and the projection of
; the resulting speed. The standalone pair entry installs its own rows.
slope_install_rows:
 ld a,(hl+)
 ldh (#slope_x_row),a
 ld a,(hl+)
 ldh (#slope_x_row+1),a
 ld a,(hl+)
 ldh (#slope_y_row),a
 ld a,(hl)
 ldh (#slope_y_row+1),a
 ret

.area _CODE
slope_dot:
 push hl
 call slope_x_product
 jr nc,slope_drop_vector
 push bc
 push hl
 push de
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#4
 add hl,de
 call slope_y_product
 jr nc,slope_drop_product
slope_dot_sum:
 ; Add the five signed product bytes before applying the one Q14 half.
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
slope_drop_product:
 add sp,#6
slope_drop_vector:
 add sp,#2
 and a
 ret

slope_x_product:
 ldh a,(#slope_x_row)
 ld c,a
 ldh a,(#slope_x_row+1)
 jr slope_product
slope_y_product:
 ldh a,(#slope_y_row)
 ld c,a
 ldh a,(#slope_y_row+1)
slope_product:
 cp #30
 jp z,slope_map_extra
 ld b,a
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 add a
 sbc a
 cp (hl)
 jr nz,slope_three_digits
 inc hl
 cp (hl)
 jp z,slope_read_word
 and a
 ret
slope_three_digits:
 ld a,(hl+)
 add a
 sbc a
 cp (hl)
 jr nz,slope_product_miss
 dec hl
 ld a,(hl)
 jp slope_read_product
slope_product_miss:
 and a
 ret
slope_map_extra:
 ld (#0x2000),a
 xor a
 ld (#0x3000),a
 jp slope_extra_product_30

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
 ld a,(hl)
 cp #2
 jr c,slope_project_known
 call slope_install_rows
 jp slope_project_rows
slope_project_known:
 ld a,(hl)
 or a
 jp z,slope_vertical_project
 cp #1
 jr z,slope_local_pair
 jp slope_project_rows

.area _CODE
slope_project_rows:
 ldhl sp,#4
 call slope_x_product
 jp nc,slope_pair_miss
 call slope_round
 pop hl
 call slope_store
 push hl
 ldhl sp,#4
 call slope_y_product
 call slope_round
 pop hl
 call slope_store
 call slope_restore_high
 jp ground_return
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

.area _CODE_35
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
slope_probe:
 ld a,(hl)
 or a
 ret z
 push hl
 ld l,a
 ld h,#>slope_addresses
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(hl+)
 cp e
 jr nz,slope_next
 ld a,(hl+)
 cp d
 jr nz,slope_next
 ld a,(hl+)
 cp c
 jr nz,slope_next
 ld a,(hl+)
 cp b
 jr nz,slope_next
 pop de
 scf
 ret
slope_next:
 pop hl
 inc l
 jr slope_probe

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
slope_x_row: .ds 2
slope_y_row: .ds 2
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
.area _CODE_9
near_project_select:
 ldh a,(#near_page)
 or a
 jp z,_riding_roll_project_pair
 cp #2
 jp c,slope_cached_pair
 jp z,ground_cached_pair
 cp #3
 jp z,ground_cached_flat
 .ifdef ROLL_DIRECTORY_BANK
 cp #4
 jp z,rom_slope_cached
 cp #5
 jp z,slope_word_project_entry
 .endif
 jp near_project_map
.area _CODE
near_project_map:
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

; The supplemental coefficients occupy three unsigned product planes in
; bank 30. The biased top digit and constant correction reconstruct the
; same signed24 product as the five-plane reader.
.area _CODE_30
slope_extra_product_30:
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld b,a
 add a
 sbc a
 cp (hl)
 jr nz,slope_extra_miss
 ld a,c
 add #(<slope_extra_bias - 0x6d)
 push af
 ld a,b
 xor #128
 push af
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
 ld h,a
 pop af
 ld l,a
 ld a,h
 ld h,#>slope_extra_bias
 push af
 ld a,(hl+)
 add b
 ld b,a
 ld a,(hl+)
 adc c
 ld c,a
 ld a,(hl)
 ld h,c
 ld l,b
 pop bc
 adc b
 ld b,a
 scf
 ret
slope_extra_miss:
 and a
 ret

.ifdef ROLL_DIRECTORY_BANK

; The missing terrain tangent shares each multiplier row across the
; velocity and impulse. Each pair returns two signed 32-bit products.
.area _DATA
batch_code: .ds batch_end-batch_start
batch_installed: .ds 1
.area _HRAM
batch_scalar: .ds 2
batch_high: .ds 6
.area _CODE
slope_word_project_entry:
 push hl
 ld a,#35
 ld (#0x2000),a
 jp slope_word_project

.area _CODE_35
batch_legacy_guard:
 ; DE:BC still holds the full tangent on a packed-directory miss.
 ; Legacy-only rows have low X bytes 1, 2, 3, 15 and 20. A skipped
 ; row still uses the exact word or wide projection.
 ld a,e
 dec a
 cp #3
 jr c,batch_maybe_legacy
 cp #14
 jr z,batch_maybe_legacy
 cp #19
 jr nz,slope_word_inputs
batch_maybe_legacy:
 ldhl sp,#0
 jp rom_slope_legacy_inputs
slope_word_inputs:
 ; Handle the X pair first. A later Y width miss drops the two
 ; temporary products before resuming the original full-width dot.
 ld a,(#batch_installed)
 or a
 jr nz,batch_ready
 ld hl,#batch_start
 ld de,#batch_code
 ld b,#(batch_end-batch_start)
batch_copy:
 ld a,(hl+)
 ld (de),a
 inc de
 dec b
 jr nz,batch_copy
 inc b
 ld a,b
 ld (#batch_installed),a
batch_ready:
 .macro batch_word lo,hi,lnext
 ld a,(hl+)
 ld lo,a
 ld a,(hl+)
 ld hi,a
 add a
 sbc a
 cp (hl)
 jp nz,lnext
 inc hl
 cp (hl)
 jp nz,lnext
 .endm
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#8
 add hl,de
 batch_word e,d,slope_fallback_dots
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 batch_word c,b,slope_fallback_dots
 ldhl sp,#0
 add sp,#-4
 call batch_code
 push hl
 push de
 ldhl sp,#14
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld de,#12
 add hl,de
 batch_word e,d,batch_wide_y
 ldhl sp,#12
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld bc,#4
 add hl,bc
 batch_word c,b,batch_wide_y
 ldhl sp,#10
 add sp,#-4
 call batch_code
 push hl
 push de
 ; Stack contains impulse Y, velocity Y, impulse X and velocity X.
 ldhl sp,#4
 ld d,h
 ld e,l
 ldhl sp,#12
 call batch_sum
 ldhl sp,#12
 call slope_store
 ldhl sp,#0
 ld d,h
 ld e,l
 ldhl sp,#8
 call batch_sum
 add sp,#12
 ld a,#5
 ldh (#near_page),a
 jp ground_resume_deltas

batch_wide_y:
 add sp,#8
 jp slope_fallback_dots

; The sum of the two signed products has 33 bits before Q14 rounding.
batch_sum:
 ld a,(de)
 add (hl)
 inc de
 inc hl
 ld a,(de)
 adc (hl)
 ld c,a
 inc de
 inc hl
 ld a,(de)
 adc (hl)
 ld b,a
 inc de
 inc hl
 ld a,(de)
 ld e,a
 adc (hl)
 ld d,a
 ; XOR the two input signs and the carry above bit 31 to get bit 32.
 ld a,#0
 rra
 xor (hl)
 xor e
 add a
 sbc a
 ld h,d
 ld l,b
 ld d,c
 ld b,a
 jp slope_round

slope_word_project:
 ldhl sp,#4
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 add a
 sbc a
 cp (hl)
 jp nz,slope_pair_miss
 inc hl
 cp (hl)
 jp nz,slope_pair_miss
 ldhl sp,#8
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 ldhl sp,#4
 add sp,#-4
 call batch_code
 call batch_round_regs
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 inc hl
 inc hl
 inc hl
 inc hl
 call slope_store
 pop de
 pop hl
 call batch_round_regs
 pop hl
 call slope_store
 jp ground_return
batch_round_regs:
 ld a,h
 add a
 sbc a
 ld b,a
 jp slope_round

; The row reader runs from WRAM while switching the low ROM-bank byte.
; Interrupts keep their normal stack. Relative branches stay within the copy.
batch_start:
 ld a,(hl+)
 ldh (#batch_scalar),a
 ld a,(hl)
 ldh (#batch_scalar+1),a
 .macro batch_map
 ld l,a
 ld h,#>_riding_scale_directory
 ld a,(hl)
 ld (#0x2000),a
 inc h
 ld h,(hl)
 .endm
 batch_map
 .macro batch_high_lane lo,hi,off
 ld l,lo
 ld a,(hl)
 ldh (#batch_high+off),a
 inc h
 ld a,(hl)
 ld l,hi
 dec h
 add (hl)
 ldh (#batch_high+off+1),a
 inc h
 ld a,(hl)
 adc #0
 ldh (#batch_high+off+2),a
 .endm
 batch_high_lane e,d,0
 dec h
 batch_high_lane c,b,3
 ldh a,(#batch_scalar)
 batch_map
 push bc
 push hl
 ; DE holds the first input, then the second. The upper-word
 ; corrections convert the unsigned multiply to signed modulo 2^32.
 .macro batch_low_lane off,lpos,lval
 ld b,d
 ld c,e
 ld l,e
 ld e,(hl)
 inc h
 ld a,(hl)
 ld l,d
 dec h
 add (hl)
 ld d,a
 inc h
 ld a,(hl)
 adc #0
 ld h,a
 ldh a,(#batch_high+off)
 add d
 ld d,a
 ldh a,(#batch_high+off+1)
 adc h
 ld l,a
 ldh a,(#batch_high+off+2)
 adc #0
 ld h,a
 ldh a,(#batch_scalar+1)
 add a
 jr nc,lpos
 ld a,l
 sub c
 ld l,a
 ld a,h
 sbc b
 ld h,a
lpos:
 bit 7,b
 jr z,lval
 ldh a,(#batch_scalar)
 ld c,a
 ld a,l
 sub c
 ld l,a
 ldh a,(#batch_scalar+1)
 ld b,a
 ld a,h
 sbc b
 ld h,a
lval:
 .endm
 batch_low_lane 0,batch_pos1,batch_val1
 ; The caller reserved the first result above its return address.
 ld b,h
 ld c,l
 ldhl sp,#6
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld (hl),b
 pop hl
 pop de
 batch_low_lane 3,batch_pos2,batch_val2
 ld a,#35
 ld (#0x2000),a
 ret
batch_end:

.area _CODE
.globl ground_projection_bank
.globl slope_descriptor
.globl near_page
.globl rom_slope_find
.globl slope_fallback_dots
.globl slope_pair_miss
.globl ground_resume_deltas
.globl ground_return
rom_slope_begin:
 ld a,#ROLL_DIRECTORY_BANK
 ld (#0x2000),a
 jp rom_slope_find
rom_slope_miss::
 ld a,#35
 ld (#0x2000),a
 jp batch_legacy_guard
rom_slope_map::
 ld (#0x2000),a
 jp (hl)
rom_slope_cached:
 push hl
 ldh a,(#slope_descriptor+1)
 ld h,a
 ldh a,(#slope_descriptor)
 ld l,a
 ldh a,(#ground_projection_bank)
 jr rom_slope_map
.endif
