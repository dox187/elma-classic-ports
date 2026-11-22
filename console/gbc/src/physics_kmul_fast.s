; Exact signed16 x unsigned8, rounded arithmetic shift and saturated16.
; ABI0 x@sp+2,m@sp+4,e@sp+5; returns DE. Product rows in banks36..43.
; Both unsigned byte products use one bank; preserve caller's ROM bank.
; CURRENT_BANK remains the caller while ROM0 reads table data; interrupts
; must remain in ROM0 without banked calls, as for the far-data readers.
.module riding_kmul_fast
.area _CODE
_kmul::
 ldhl sp,#4
 ld c,(hl)
 ldhl sp,#2
 ld e,(hl)
 inc hl
 ld d,(hl)
 push de
 ld a,(#__current_bank)
 push af
 ld a,c
 rlca
 rlca
 rlca
 and a,#7
 add a,#36
 ld (#0x2000),a
 ; Input low byte times multiplier: table row is512 bytes.
 ld a,c
 and a,#31
 add a,a
 or a,#>_physics_scale_planes_36
 ld h,a
 ld l,e
 ld e,(hl)
 inc h
 ld b,d
 ld d,(hl)
 ld l,b
 dec h
 ld a,(hl)
 add a,d
 ld d,a
 inc h
 ld a,(hl)
 adc a,#0
 ld l,a
 bit 7,b
 jr z,030$
 ld a,l
 sub a,c
 ld l,a
030$:
 ld a,l
 rlca
 sbc a,a
 ld h,a
 pop af
 ld (#0x2000),a
 add sp,#2
 push hl
 ldhl sp,#7
 ld c,(hl)
 pop hl
 ; For E>=8 the rounded quotient always fits signed16.
 ld a,c
 sub a,#8
 jr c,100$
 ld c,a
 ld b,e
 ld e,d
 ld d,l
 or a,a
 jr z,120$
110$:
 sra d
 rr e
 dec c
 jr nz,110$
 jr nc,140$
130$:
 inc de
140$:
 ret
120$:
 bit 7,b
 jr nz,130$
 ret
100$:
 sra h
 rr l
 rr d
 rr e
 dec c
 jr nz,100$
 jr nc,200$
 inc e
 jr nz,200$
 inc d
 jr nz,200$
 inc l
 jr nz,200$
 inc h
200$:
 ld a,h
 or a,l
 jr z,210$
 ld a,h
 and a,l
 inc a
 jr nz,220$
 bit 7,d
 jr nz,230$
220$:
 bit 7,h
 jr z,240$
 ld de,#0x8000
 ret
240$:
 ld de,#0x7fff
 ret
210$:
 bit 7,d
 jr nz,240$
230$:
 ret

; Unsigned16 DE times unsigned8 C, raw32 return HLDE. Leaves table bank
; selected for the wide multiplier to restore once, after its sign correction.
_riding_mul16u8_unsigned::
 ld b,d
 ld a,c
 rlca
 rlca
 rlca
 and a,#7
 add a,#36
 ld (#0x2000),a
 ld a,c
 and a,#31
 add a,a
 or a,#>_physics_scale_planes_36
 ld h,a
 ld l,e
 ld e,(hl)
 inc h
 ld d,(hl)
 ld l,b
 dec h
 ld a,(hl)
 add a,d
 ld d,a
 inc h
 ld a,(hl)
 adc a,#0
 ld l,a
 ld h,#0
 ret
