; MBC5 scratch-SRAM and nine-bit ROM data access. All entry points use ABI0
; and remain in ROM0. Interrupts stay enabled; handlers must not bank switch.
.module gbc_world_memory
.area _CODE

; id@SP+2. uint16 result in DE. Cartridge RAM was enabled by lookup_clear.
_world_lookup_get::
 ldhl sp,#2
 ld a,(hl+)
 ld e,a
 ld a,(hl)
 ld d,a
 swap a
 and a,#15
 ld (#0x4000),a
 sla e
 rl d
 ld a,d
 and a,#31
 or a,#0xa0
 ld h,a
 ld l,e
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 xor a,a
 ld (#0x4000),a
 ret

; id@SP+2, slot@SP+4. Preserve no registers, leave RAM bank zero selected.
_world_lookup_set::
 ldhl sp,#4
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#2
 ld a,(hl+)
 ld e,a
 ld a,(hl)
 ld d,a
 swap a
 and a,#15
 ld (#0x4000),a
 sla e
 rl d
 ld a,d
 and a,#31
 or a,#0xa0
 ld h,a
 ld l,e
 ld (hl),c
 inc hl
 ld (hl),b
 xor a,a
 ld (#0x4000),a
 ret

; count@SP+2. Set exactly the first count words to the missing-slot sentinel.
_world_lookup_clear::
 ldhl sp,#2
 ld c,(hl)
 inc hl
 ld b,(hl)
 ld a,#0x0a
 ld (#0x0000),a
 xor a,a
 ld (#0x4000),a
 ld e,a
 ld hl,#0xa000
 ld a,b
 or a,c
 jr z,120$
100$:
 ld a,#0xff
 ld (hl+),a
 ld (hl+),a
 dec bc
 ld a,b
 or a,c
 jr z,120$
 ld a,h
 cp a,#0xc0
 jr nz,100$
 inc e
 ld a,e
 ld (#0x4000),a
 ld hl,#0xa000
 jr 100$
120$:
 xor a,a
 ld (#0x4000),a
 ret

; bank@SP+2, source@4, dest@6, length@8. The caller splits bank crossings.
_world_far_copy::
 ld a,(#__current_bank)
 push af
 ldhl sp,#4
 ld a,(hl+)
 ld (#0x2000),a
 ld a,(hl)
 and a,#1
 ld (#0x3000),a
 ldhl sp,#10
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#8
 ld e,(hl)
 inc hl
 ld d,(hl)
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,b
 or a,c
 jr z,220$
200$:
 ld a,(hl+)
 ld (de),a
 inc de
 dec bc
 ld a,b
 or a,c
 jr nz,200$
220$:
 xor a,a
 ld (#0x3000),a
 pop af
 ld (#0x2000),a
 ld (#__current_bank),a
 ret

; bank@SP+2, source@4, dest@6, count@8, stride@9. No window crossing.
_world_far_gather::
 ld a,(#__current_bank)
 push af
 ldhl sp,#4
 ld a,(hl+)
 ld (#0x2000),a
 ld a,(hl)
 and a,#1
 ld (#0x3000),a
 ldhl sp,#10
 ld b,(hl)
 inc hl
 ld c,(hl)
 ldhl sp,#8
 ld e,(hl)
 inc hl
 ld d,(hl)
 ldhl sp,#6
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,b
 or a,a
 jr z,330$
300$:
 ld a,(hl)
 ld (de),a
 inc de
 ld a,l
 add a,c
 ld l,a
 jr nc,310$
 inc h
310$:
 dec b
 jr nz,300$
330$:
 xor a,a
 ld (#0x3000),a
 pop af
 ld (#0x2000),a
 ld (#__current_bank),a
 ret

; x@SP+2,y@3,vertical@4,count@5,WRAM slots@6. Bank8 word map,32x32.
_world_slot_strip_get::
 ldhl sp,#6
 ld e,(hl)
 inc hl
 ld d,(hl)
 ldhl sp,#5
 ld b,(hl)
 dec hl
 ld a,(hl)
 push af
 ldhl sp,#4
 ld a,(hl+)
 and a,#31
 add a,a
 ld c,a
 ld a,(hl)
 and a,#31
 ld l,a
 rrca
 rrca
 and a,#0xc0
 or a,c
 ld c,a
 ld a,l
 srl a
 srl a
 or a,#0xa0
 ld h,a
 ld l,c
 pop af
 inc b
 dec b
 jr z,430$
 or a,a
 jr nz,420$
 ld a,c
 and a,#0xc0
 ld c,a
 ld a,#8
 ld (#0x4000),a
400$:
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl)
 ld (de),a
 inc de
 dec b
 jr z,430$
 ld a,l
 inc a
 and a,#63
 or a,c
 ld l,a
 jr 400$
420$:
 ld c,#63
 ld a,#8
 ld (#0x4000),a
421$:
 ld a,(hl+)
 ld (de),a
 inc de
 ld a,(hl)
 ld (de),a
 inc de
 dec b
 jr z,430$
 ld a,l
 add a,c
 ld l,a
 jr nc,421$
 inc h
 ld a,h
 and a,#7
 or a,#0xa0
 ld h,a
 jr 421$
430$:
 xor a,a
 ld (#0x4000),a
 ret

_world_slot_strip_set::
 ldhl sp,#6
 ld e,(hl)
 inc hl
 ld d,(hl)
 ldhl sp,#5
 ld b,(hl)
 dec hl
 ld a,(hl)
 push af
 ldhl sp,#4
 ld a,(hl+)
 and a,#31
 add a,a
 ld c,a
 ld a,(hl)
 and a,#31
 ld l,a
 rrca
 rrca
 and a,#0xc0
 or a,c
 ld c,a
 ld a,l
 srl a
 srl a
 or a,#0xa0
 ld h,a
 ld l,c
 pop af
 inc b
 dec b
 jr z,530$
 or a,a
 jr nz,520$
 ld a,c
 and a,#0xc0
 ld c,a
 ld a,#8
 ld (#0x4000),a
500$:
 ld a,(de)
 ld (hl+),a
 inc de
 ld a,(de)
 ld (hl),a
 inc de
 dec b
 jr z,530$
 ld a,l
 inc a
 and a,#63
 or a,c
 ld l,a
 jr 500$
520$:
 ld c,#63
 ld a,#8
 ld (#0x4000),a
521$:
 ld a,(de)
 ld (hl+),a
 inc de
 ld a,(de)
 ld (hl),a
 inc de
 dec b
 jr z,530$
 ld a,l
 add a,c
 ld l,a
 jr nc,521$
 inc h
 ld a,h
 and a,#7
 or a,#0xa0
 ld h,a
 jr 521$
530$:
 xor a,a
 ld (#0x4000),a
 ret
