; Exact wheel/head object overlap. Near bank5, ABI0 pose@2, object@4, head@6.
; World coordinates and squared-distance rules match the C touching predicate.
.module objects_touch_fast
.area _CODE_5
_gbc_object_touch::
 ; Reject distant Y integer parts before X; both predicates are unchanged.
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld bc,#6
 add hl,bc
 push hl
 ldhl sp,#6
 ld a,(hl+)
 ld d,(hl)
 add a,#11
 ld e,a
 jr nc,100$
 inc d
100$:
 pop hl
 call coarse
 or a,a
 jp z,failed
 ld bc,#-5
 add hl,bc
 ld a,e
 sub a,#5
 ld e,a
 jr nc,101$
 dec d
101$:
 call coarse
 or a,a
 jp z,failed
 ; Full X delta.
 ldhl sp,#4
 ld a,(hl+)
 ld d,(hl)
 add a,#5
 ld e,a
 jr nc,102$
 inc d
102$:
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 call axis
 or a,a
 jr z,failed
 push de
 ; Full Y delta. The saved X result shifts argument addresses by two.
 ldhl sp,#6
 ld a,(hl+)
 ld d,(hl)
 add a,#9
 ld e,a
 jr nc,103$
 inc d
103$:
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld bc,#4
 add hl,bc
 call axis
 or a,a
 jr nz,104$
 pop bc
 jr failed
104$:
 push de
 ld b,d
 ld c,e
 call _riding_mul16_regs
 push hl
 push de
 ldhl sp,#6
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld b,d
 ld c,e
 call _riding_mul16_regs
 pop bc
 ld a,e
 add a,c
 ld e,a
 ld a,d
 adc a,b
 ld d,a
 pop bc
 ld a,l
 adc a,c
 ld c,a
 ld a,h
 adc a,b
 ld b,a
 add sp,#4
 ldhl sp,#6
 ld a,(hl)
 or a,a
 jr z,wheel
 ld a,b
 or a,a
 jr nz,failed
 ld a,c
 cp a,#6
 jr c,passed
 jr nz,failed
 ld a,d
 cp a,#0x81
 jr c,passed
 jr nz,failed
 ld a,e
 cp a,#0xaa
 jr c,passed
 jr failed
wheel:
 ld a,b
 or a,a
 jr nz,failed
 ld a,c
 cp a,#10
 jr c,passed
 jr nz,failed
 ld a,d
 cp a,#0x3c
 jr c,passed
 jr nz,failed
 ld a,e
 cp a,#0x2a
 jr c,passed
failed:
 ld e,#0
 ret
passed:
 ld e,#1
 ret

; HL/DE point to unsigned integer-part low bytes. Leave each at its high byte.
coarse:
 ld a,(de)
 ld c,a
 ld a,(hl+)
 sub a,c
 ld c,a
 inc de
 ld a,(de)
 ld b,a
 ld a,(hl)
 sbc a,b
 ld b,a
 inc bc
 ld a,b
 or a,a
 jr nz,coarse_fail
 ld a,c
 cp a,#3
 jr nc,coarse_fail
 ld a,#1
 ret
coarse_fail:
 xor a
 ret

; HL/DE point to complete Q16.16 coordinates. Return A=1, DE=delta>>6
; only for inclusive [-52429,52429], otherwise A=0. No caller state is saved.
axis:
 ld b,#4
 and a,a
axis_read:
 ld a,(de)
 ld c,a
 ld a,(hl+)
 sbc a,c
 push af
 inc de
 dec b
 jr nz,axis_read
 pop bc
 pop de
 pop hl
 pop af
 ; Delta bytes are B,D,H,A from most significant to least.
 bit 7,b
 jr nz,axis_negative
 ld c,a
 ld a,b
 or a,d
 jr nz,axis_fail
 ld a,h
 cp a,#0xcc
 jr c,axis_positive_ok
 jr nz,axis_fail
 ld a,c
 cp a,#0xce
 jr nc,axis_fail
axis_positive_ok:
 ld a,c
 jr axis_quantize
axis_negative:
 ld c,a
 ld a,b
 and a,d
 inc a
 jr nz,axis_fail
 ld a,h
 cp a,#0x33
 jr c,axis_fail
 jr nz,axis_negative_ok
 ld a,c
 cp a,#0x33
 jr c,axis_fail
axis_negative_ok:
 ld a,c
axis_quantize:
 ld b,d
 ld c,h
 ld e,a
 sra b
 rr c
 rr e
 sra b
 rr c
 rr e
 sra b
 rr c
 rr e
 sra b
 rr c
 rr e
 sra b
 rr c
 rr e
 sra b
 rr c
 rr e
 ld d,c
 ld a,#1
 ret
axis_fail:
 xor a
 ret
