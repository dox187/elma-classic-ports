; Local to each data bank. Coordinates are in the same 1/1024 m units
; as the coarse contact iterator. The lower eight position bits still
; reach the ordinary fine contact test, pushout and rolling solver.
 ld h,d
 ld l,e
 inc hl
 ld a,(hl+)
 ld c,a                   ; low X byte
 ld a,(hl+)
 sub #CORNER_X_BLOCK
 cp #3
 jp nc,corner_outside
 swap a
 ld b,a
 ld a,c
 swap a
 and #15
 or b
 sub #CORNER_X_INSET
 cp #32
 jr nc,corner_outside
 ld b,a                   ; column in the 32 x 32 directory
 ld a,(hl+)
 or a
 jr nz,corner_outside
 inc hl
 ld a,c
 and #15
 ld e,a
 ld a,(hl+)
 ld c,a
 swap a
 and #0xf0
 or e
 ld e,a                   ; y-major pixel within one tile
 ld a,(hl+)
 sub #CORNER_Y_BLOCK
 cp #2
 jr nc,corner_outside
 swap a
 ld d,a
 ld a,(hl)
 or a
 jr nz,corner_outside
 ld a,c
 swap a
 and #15
 or d
 swap a
 rlca
 ld h,a
 and #0xe0
 or b
 ld l,a
 ld a,h
 and #3
 add #0x41
 ld h,a
 ld a,(hl)
 or a
 jr z,corner_outside
 add a                    ; carry selects a tile with shared rows
 ld l,a
 ld h,#0x45
 ld a,(hl+)
 ld h,(hl)
 ld l,a                   ; tile address
 jr c,corner_rows
 push hl
 ld d,#0
 add hl,de
 ld a,(hl)
 pop hl
 inc h                    ; raw tile dictionary follows the 256 indices
corner_index:
 or a
 ret z                    ; empty
 cp #255
 jr z,corner_ordered_pair
 dec a
 ld e,a
 .rept 4
 add hl,de
 .endm
 ld a,(hl+)
 ld c,a                   ; index into the three high-byte pages
 ld a,(hl+)
 ld (#_Ct),a
 ld a,(hl+)
 ld (#_Ct+2),a
 ld a,(hl)
 ld (#_Ct+4),a
 ld l,c
 ld h,#0x46
 ld a,(hl)
 ld (#_Ct+1),a
 inc h
 ld a,(hl)
 ld (#_Ct+3),a
 inc h
 ld a,(hl)
 ld (#_Ct+5),a
 ld a,#1
 ret
corner_outside:
 ld a,#255
 ret

; Compressed tiles store the dictionary address, a 16-byte row directory
; and one copy of each distinct row. E holds the y-major pixel index.
corner_rows:
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 push bc
 ld a,e
 and #15
 ld c,a
 xor e
 swap a
 ld e,a
 ld d,#0
 push hl
 add hl,de
 ld a,(hl)
 or c
 ld e,a
 pop hl
 ld bc,#16
 add hl,bc
 add hl,de
 ld a,(hl)
 pop hl
 jr corner_index

corner_ordered_pair:
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 ldhl sp,#2              ; caller saved the wheel before calling this bank
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 jp _riding_corner_pair_map
