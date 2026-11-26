; Raw-only direct SRAM1..3 pattern-ID lookup with linked fallback.
.module gbc_world_lookup_raw
; DE is a valid direct ID. Select its SRAM bank and return the word pointer
; in HL. Preserve BC (used for stores) and DE (used by strip acquisition).
.macro lookup_direct_address
 ld h,d
 ld l,e
 add hl,hl
 ld a,h
 and a,#0x1f
 or a,#0xa0
 ld h,a
 ld a,d
 swap a
 and a,#3
 inc a
 ld (#0x4000),a
.endm

.area _DATA
_world_lookup_direct::
 .ds 1
.ifdef WORLD_RAW_STREAM_BANK6
.area _CODE_6
.else
.area _CODE
.endif
; id@SP+2. uint16 result in DE. Cartridge RAM was enabled by lookup_clear.
_world_lookup_get::
 ld a,(#_world_lookup_direct)
 or a,a
 jp nz,lookup_direct_get
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
 ld a,(#_world_lookup_direct)
 or a,a
 jp nz,lookup_direct_set
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
 ld a,(#_world_lookup_direct)
 or a,a
 jp nz,lookup_direct_set
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
 xor a,a
 ld (#_world_lookup_direct),a
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

; Raw profiles can dedicate SRAM1..3 to 12,288 exact uint16 entries.
; Raw clear selects this path only when the entire level fits. The normal
; clear entry always selects linked SRAM0 lookup for compressed profiles.
_world_lookup_raw_clear::
 ldhl sp,#3
 ld a,(hl-)
 cp a,#0x30
 jp c,lookup_direct_clear
 jp nz,_world_lookup_clear
 ld a,(hl)
 or a,a
 jp nz,_world_lookup_clear
lookup_direct_clear:
 ld a,#0x0a
 ld (#0x0000),a
 ld a,#1
 ld (#_world_lookup_direct),a
 ld e,a
lookup_direct_clear_bank:
 ld a,e
 ld (#0x4000),a
 ld hl,#0xa000
 ld b,#4
 ld c,#0
 ld a,#0xff
lookup_direct_clear_byte:
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 ld (hl+),a
 dec c
 jr nz,lookup_direct_clear_byte
 dec b
 jr nz,lookup_direct_clear_byte
 inc e
 ld a,e
 cp a,#4
 jr nz,lookup_direct_clear_bank
 xor a,a
 ld (#0x4000),a
 ret

; Every exit restores bank0, including invalid IDs. Use a complete ID check
; before converting its high nibble to an SRAM bank, preventing aliasing.
lookup_direct_get:
 ldhl sp,#3
 ld a,(hl-)
 cp a,#0x30
 jr nc,lookup_direct_invalid
 ld e,(hl)
 ld d,a
 lookup_direct_address
 ld e,(hl)
 inc hl
 ld d,(hl)
 xor a,a
 ld (#0x4000),a
 ret
lookup_direct_invalid:
 ld de,#0xffff
 xor a,a
 ld (#0x4000),a
 ret
lookup_direct_set:
 ldhl sp,#2
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 cp a,#0x30
 jr nc,lookup_direct_invalid
 ld d,a
 ld c,(hl)
 inc hl
 ld b,(hl)
 lookup_direct_address
 ld (hl),c
 inc hl
 ld (hl),b
 xor a,a
 ld (#0x4000),a
 ret

.area _CODE_6
.ifndef WORLD_RAW_STREAM_BANK6
; Private bank6 entry for one raw acquisition. Carry means HL points to
; the selected direct SRAM entry. The caller may use the WRAM allocator
; while it is selected and must restore SRAM0 before upload or yield. Otherwise the ordinary lookup
; handles the full ID, including the linked course and invalid direct IDs.
_world_lookup_open_raw::
 ld a,(#_world_lookup_direct)
 or a
 ret z
 ld a,d
 cp a,#0x30
 ret nc
 lookup_direct_address
 scf
 ret
.endif
