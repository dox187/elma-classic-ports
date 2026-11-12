; Retire cached tile references and mark newly free slots.
; ABI0 refs@SP+2, retired@4, count@6, free_bits@7. Count0 is a no-op.
; Duplicate slots and zero references are valid; no bank or IRQ changes.
.module world_retire_fast
.area _CODE
_world_refs_retire::
 ldhl sp,#6
 ld b,(hl)
 ld a,b
 or a,a
 ret z
 ldhl sp,#4
 ld a,(hl+)
 ld d,(hl)
 ld e,a
100$:
 push bc
 ld a,(de)
 ld l,a
 inc de
 ld a,(de)
 ld h,a
 inc de
 push de
 push hl
 add hl,hl
 ld d,h
 ld e,l
 ldhl sp,#8
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 add hl,de
 ld a,(hl+)
 ld c,a
 ld a,(hl)
 or a,c
 jr z,200$
 ld a,c
 sub a,#1
 ld c,a
 dec hl
 ld (hl+),a
 ld a,(hl)
 sbc a,#0
 ld (hl),a
 or a,c
 jr nz,200$
 pop hl
 ld d,h
 ld e,l
 ld a,l
 and a,#7
 ld c,a
 ld b,#0
 ld hl,#300$
 add hl,bc
 ld b,(hl)
 ld h,d
 ld l,e
 srl h
 rr l
 srl h
 rr l
 srl h
 rr l
 ld d,h
 ld e,l
 ldhl sp,#11
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 add hl,de
 ld a,(hl)
 or a,b
 ld (hl),a
 jr 210$
200$:
 pop hl
210$:
 pop de
 pop bc
 dec b
 jr nz,100$
 ret
300$:
 .db 1,2,4,8,16,32,64,128
