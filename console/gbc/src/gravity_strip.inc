; BC is a wheel pointer. The caller has checked the high X byte used to
; select this bank. Validate the remaining 24-bit key and preserve the
; center's fractional bytes for the normal pushout and rolling solver.
 ld h,b
 ld l,c
 inc hl
 ld a,(hl+)
 ld e,a
 and #0xf8
 rrca
 ld c,a                         ; four directory bytes per eight X units
 ld a,(hl+)
 sub #GRAVITY_X_PAGE
 rrca
 or c
 ld c,a
 ld a,(hl+)
 or a
 jr nz,gravity_miss
 inc hl
 ld a,(hl+)
 ld b,a                         ; low Y
 ld a,(hl+)
 ld d,a                         ; middle Y
 ld a,(hl)
 or a
 jr nz,gravity_miss
 ld h,#0
 ld l,c
 ld a,e
 and #7
 ld e,a                         ; X within strip
 ld a,b
 ld bc,#gravity_columns
 add hl,bc
 sub (hl)                       ; unsigned 16-bit Y minus strip origin
 ld b,a
 inc hl
 ld a,d
 sbc (hl)
 jr nz,gravity_miss
 ld a,b
 cp #8
 jr nc,gravity_miss
 ld b,a
 ld c,e
 inc hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,h
 or a
 jr z,gravity_miss
 ld e,b
 ld d,#0
 add hl,de
 ld a,(hl)
 cp #255
 ret z
 ld l,a
 ld h,d
 .rept 3
 add hl,hl
 .endm
 ld e,c
 add hl,de
 ld de,#gravity_rows
 add hl,de
 ld a,(hl)
 cp #255
 ret z                          ; two supports use the ordinary solver
 or a
 ret z
 dec a
 ld l,a
 ld h,#0
 add hl,hl
 add hl,hl
 ld de,#gravity_contacts
 add hl,de
 .irp offset,0,2,4
 ld a,(hl+)
 ld (#_Ct+offset),a
 .endm
 ld a,(hl)
 ld l,a
 ld h,#0
 ld d,h
 ld e,l
 add hl,hl
 add hl,de
 ld de,#gravity_high
 add hl,de
 .irp offset,1,3,5
 ld a,(hl+)
 ld (#_Ct+offset),a
 .endm
 ld a,#1
 ret
gravity_miss:
 ld a,#255
 ret
