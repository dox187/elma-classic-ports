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
 ld c,a
 and #7
 rrca
 rrca
 rrca
 or b
 ld l,a
 ld a,c
 rrca
 rrca
 rrca
 and #3
 add #0x41
 ld h,a
 ld a,(hl)
 or a
 jr z,corner_outside
 add a
 ld l,a
 ld h,#0x45
 ld a,(hl+)
 ld h,(hl)
 ld l,a                   ; tile address
 push hl
 ld d,#0
 add hl,de
 ld a,(hl)
 pop hl
 or a
 ret z                    ; empty
 cp #255
 ret z                    ; two supports: use the ordered pair solver
 dec a
 ld e,a
 inc h                    ; dictionary immediately after the 256 indices
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
