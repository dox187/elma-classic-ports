; MBC5 scratch-SRAM and nine-bit ROM data access. All entry points use ABI0
; and remain in ROM0. Interrupts stay enabled; handlers must not bank switch.
.module gbc_world_memory
.area _CODE

; bank@SP+2, source@3, dest@5, count@7, stride@8. SRAM already enabled.
_world_sram_gather::
 ldhl sp,#2
 ld a,(hl)
 ld (#0x4000),a
 ldhl sp,#7
 ld b,(hl)
 inc hl
 ld c,(hl)
 ldhl sp,#5
 ld e,(hl)
 inc hl
 ld d,(hl)
 ldhl sp,#3
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,b
 or a,a
 jr z,020$
010$:
 ld a,(hl)
 ld (de),a
 inc de
 ld a,l
 add a,c
 ld l,a
 jr nc,015$
 inc h
015$:
 dec b
 jr nz,010$
020$:
 xor a,a
 ld (#0x4000),a
 ret

; id@SP+2. uint16 result in DE. Cartridge RAM was enabled by lookup_clear.
_world_lookup_get::
 xor a,a
 ld (#0x4000),a
 ldhl sp,#2
 ld c,(hl)
 inc hl
 ld b,(hl)
 jp lookup_find

; id@SP+2, slot@SP+4. Preserve no registers, leave RAM bank zero selected.
_world_lookup_set::
 xor a,a
 ld (#0x4000),a
 ldhl sp,#2
 ld c,(hl)
 inc hl
 ld b,(hl)
 call lookup_find
 ld a,d
 inc a
 jr z,lookup_insert
 ; Unlink the old entry, retaining its predecessor's link address.
 push hl
 call lookup_entry
 inc hl
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 pop hl
 ld (hl),c
 inc hl
 ld (hl),b
 dec hl
lookup_insert:
 push hl
 ldhl sp,#6
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld a,d
 inc a
 jr z,lookup_removed
 pop hl
 ; Replace this link with the requested slot, preserving its successor.
 ld c,(hl)
 ld (hl),e
 inc hl
 ld b,(hl)
 ld (hl),d
 call lookup_entry
 push hl
 ldhl sp,#4
 ld e,(hl)
 inc hl
 ld d,(hl)
 pop hl
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ld (hl),c
 inc hl
 ld (hl),b
 ret
lookup_removed:
 pop hl
 ret

; BC=id. Return DE=slot (FFFF absent), HL=its predecessor's link address.
; Hash low10 ID bits; full16bit comparisons distinguish colliding IDs.
lookup_find:
 ld a,b
 and a,#3
 ld h,a
 ld l,c
 add hl,hl
 ld a,h
 or a,#0xa0
 ld h,a
lookup_chain:
 ld e,(hl)
 inc hl
 ld d,(hl)
 dec hl
 ld a,d
 inc a
 ret z
 push hl
 call lookup_entry
 ld a,(hl+)
 cp a,c
 jr nz,lookup_next
 ld a,(hl)
 cp a,b
 jr z,lookup_found
lookup_next:
 inc hl
 pop de
 jr lookup_chain
lookup_found:
 pop hl
 ret

; DE=slot0..443 -> HL=entry; preserve BC and DE.
lookup_entry:
 ld h,d
 ld l,e
 add hl,hl
 add hl,hl
 ld a,h
 add a,#0xa8
 ld h,a
 ret

; count is ignored: clear only the fixed A000-AEEF table, never mirror/save.
_world_lookup_clear::
 ld a,#0x0a
 ld (#0x0000),a
 xor a,a
 ld (#0x4000),a
 ld hl,#0xa000
 ld bc,#0x0ef0
100$:
 ld a,#0xff
 ld (hl+),a
 dec bc
 ld a,b
 or a,c
 jr nz,100$
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

; x@SP+2,y@3,vertical@4,count@5,WRAM slots@6. Bank0 B000 word map,32x32.
_world_slot_strip_get::
 xor a,a
 ld (#0x4000),a
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
 or a,#0xb0
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
 or a,#0xb0
 ld h,a
 jr 421$
430$:
 ret

_world_slot_strip_set::
 xor a,a
 ld (#0x4000),a
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
 or a,#0xb0
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
 or a,#0xb0
 ld h,a
 jr 521$
530$:
 ret
