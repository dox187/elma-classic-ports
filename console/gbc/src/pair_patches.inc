; HL is the usual wheel input. A miss retains the ordinary sparse tile reader.
.area _CODE_9
_riding_patch_wheel_inputs::
 push hl
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 ld hl,#6
 add hl,bc
 ld a,(hl)
 sub #PATCH_Y_MIN
 cp #PATCH_Y_SPAN
 jr nc,patch_fallback
 push bc
 ld e,#15
 ld hl,#patch_lookup
 call ___sdcc_bcall_ehl
 cp #2
 jp z,_riding_patch_have_answer
 pop bc
patch_fallback:
 ; Only the existing two sparse Y strips need their full lookup.
 ld hl,#6
 add hl,bc
 ld c,(hl)
 ld a,(#_patch_sparse_y0)
 cp c
 jr z,patch_sparse
 ld a,(#_patch_sparse_y1)
 cp c
patch_sparse:
 pop hl
 jp z,_riding_sparse_wheel_inputs
 jp _riding_wheel_inputs

.area _CODE_15
; BC names a wheel. Only a block with two ordered contacts at all sixteen
; centers can occur in the directory, irrespective of fractional position.
_riding_patch_lookup::
patch_lookup:
 ld hl,#2
 add hl,bc
 ld a,(hl)
 sub #PATCH_X_MIN
 cp #PATCH_X_SPAN
 jr nc,patch_warm_miss
 ; A live pair also contains fractional filters and the ordered support signs.
 ; Let the normal certificate restore it only at its exact 32-bit XY key.
 ld hl,#(_wheel_surface_cache+4)
 ld a,c
 cp #<(_Bike+48)
 jr nz,patch_kind
 ld hl,#(_wheel_surface_cache+29+4)
patch_kind:
 ld a,(hl+)
 cp #9
 jr nz,patch_search
 push bc
 ld d,b
 ld e,c
 call patch_match_word
 jr nz,patch_cold
 inc de
 inc de
 call patch_match_word
 jr nz,patch_cold
 ; Both low words matched. Compare high Y first, then high X.
 ld bc,#-7
 add hl,bc
 call patch_match_word
 jr nz,patch_cold
 ld bc,#-4
 add hl,bc
 pop de
 inc de
 inc de
 ld b,d
 ld c,e
 call patch_match_word
 dec bc
 dec bc
 jr nz,patch_search
patch_warm_miss:
 ld a,#255
 ret
patch_match_word:
 ld a,(de)
 inc de
 cp (hl)
 inc hl
 ret nz
 ld a,(de)
 inc de
 cp (hl)
 inc hl
 ret
patch_cold:
 pop bc
patch_search:
 push bc
 ld h,b
 ld l,c
 inc hl
 ld a,(hl+)
 and #252
 ld b,a                  ; rounded X low byte
 ld a,(hl+)
 sub #PATCH_X_MIN        ; range checked at entry
 ld e,a
 ld a,(hl+)
 or a
 jr nz,patch_miss
 inc hl
 ld a,(hl+)
 and #252
 ld c,a                  ; rounded Y low byte
 ld a,(hl+)
 sub #PATCH_Y_MIN
 cp #PATCH_Y_SPAN
 jr nc,patch_miss
 swap a
 or e
 ld d,a                  ; both middle bytes in one strip key
 ld a,(hl)
 or a                    ; require the upper coordinate bytes to match, too
 jr nz,patch_miss
 ld hl,#patch_blocks
patch_next:
 ld a,(hl+)
 cp #255
 jr z,patch_miss
 cp d
 jr nz,patch_skip5
 ld a,(hl+)
 cp b
 jr nz,patch_skip4
 ld a,(hl+)
 cp c
 jr nz,patch_skip3
 ; Preserve the full cache key before the fine filter remembers the pair.
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 pop de
 push de
 inc de
 ld a,(de)
 and #3
 ld c,a
 inc de
 inc de
 inc de
 inc de
 ld a,(de)
 and #3
 add a
 add a
 or c
 ld c,a
 call patch_copy
 pop de
 ld hl,#_wheel_surface_cache
 ld a,e
 cp #<(_Bike+48)
 jr nz,patch_bind
 ld hl,#(_wheel_surface_cache+29)
patch_bind:
 ; Binding kind zero is safe even on a warm hit. All fractional tests and
 ; the normal response still run on the pair just reconstructed.
 inc de
 inc de
 ld a,(de)
 ld (hl+),a
 inc de
 ld a,(de)
 ld (hl+),a
 inc de
 inc de
 inc de
 ld a,(de)
 ld (hl+),a
 inc de
 ld a,(de)
 ld (hl+),a
 ld (hl),#0
 ld a,#2
 ret
patch_skip5:
 inc hl
patch_skip4:
 inc hl
patch_skip3:
 inc hl
 inc hl
 inc hl
 jr patch_next
patch_miss:
 pop bc
 ld a,#255
 ret

.area _CODE
; HL = template, B = low ROM bank, C = index in a 4-by-4 block.
patch_copy:
 ld a,b
 ldh (#__current_bank),a
 ld (#0x2000),a
 ld de,#_Ct
 ld b,#20
patch_base:
 ld a,(hl+)
 ld (de),a
 inc de
 dec b
 jr nz,patch_base
patch_column:
 ld a,(hl+)
 cp #255
 jr z,patch_done
 push hl
 ld hl,#_Ct
 add l
 ld e,a
 ld a,h
 adc #0
 ld d,a
 pop hl
 push hl
 add hl,bc
 ld a,(hl)
 ld (de),a
 pop hl
 ld de,#16
 add hl,de
 jr patch_column
patch_done:
 ld a,#15
 ldh (#__current_bank),a
 ld (#0x2000),a
 ret
