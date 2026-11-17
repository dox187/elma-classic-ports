; Compact linked SRAM0 pattern-ID lookup. ROM0, ABI0.
.module gbc_world_lookup_linked
.area _CODE
; id@SP+2. uint16 result in DE. Cartridge RAM was enabled by lookup_clear.
_world_lookup_get::
 xor a,a
 ld (#0x4000),a
 ldhl sp,#2
 ld c,(hl)
 inc hl
 ld b,(hl)
 jp lookup_find

; id@SP+2 is known absent, slot@SP+4 is unlinked. Insert at the bucket head
; without searching the same missing ID again. Acquisition has just checked
; absence and removed this slot's old ID; IRQs never modify this table.
_world_lookup_insert_absent::
 xor a,a
 ld (#0x4000),a
 ldhl sp,#2
 ld a,(hl+)
 ld c,a
 ld a,(hl)
 ; Form A000 + 2*(id & 1023), retaining no source registers.
 and a,#3
 ld h,a
 ld l,c
 add hl,hl
 ld a,h
 or a,#0xa0
 ld h,a
 jr lookup_insert

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
