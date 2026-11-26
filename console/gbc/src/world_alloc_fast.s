; Exact round-robin claim from a 444-slot free bitmap, stack ABI0.
; uint16 next@sp2, uint8 *bitmap@sp4 -> DE(slot), or FFFF with no change.
; Bytes 0..54 are full; only bits 0..3 of byte55 are valid. No shared RAM,
; bank-register writes or interrupt changes. Reentrant private stack only.
.module world_alloc_fast
.ifdef WORLD_RAW_STREAM_BANK6
.area _CODE_6
.else
.area _CODE
.endif
_world_find_free::
 ldhl sp,#2
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld a,e
 and a,#7
 ld b,a
 srl d
 rr e
 srl d
 rr e
 srl d
 rr e
 ld c,e
 ld e,b
 ld d,#0
 ld hl,#world_alloc_start_masks
 add hl,de
 ld b,(hl)
 ldhl sp,#4
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld h,d
 ld l,e
 ld a,l
 add a,c
 ld l,a
 jr nc,world_alloc_initial_pointer
 inc h
world_alloc_initial_pointer:
 ld a,(hl)
 and a,b
 ld e,a
 ld b,#57
 ld a,#56
 sub a,c
 ld d,a
 ld a,e
 jr world_alloc_fetched
world_alloc_advance:
 inc hl
 inc c
 dec d
 jr nz,world_alloc_fetched_byte
 ld c,#0
 ld d,#56
 ld a,l
 sub a,#56
 ld l,a
 jr nc,world_alloc_fetched_byte
 dec h
world_alloc_fetched_byte:
 ld a,(hl)
world_alloc_fetched:
 or a
 jr nz,world_alloc_candidate
world_alloc_empty:
 dec b
 jr nz,world_alloc_advance
 ld de,#0xffff
 ret
world_alloc_candidate:
 ld e,a
 ld a,c
 cp a,#55
 ld a,e
 jr nz,world_alloc_choose
 and a,#15
 jr z,world_alloc_empty
world_alloc_choose:
 ld b,#1
 ld e,#0
world_alloc_bit:
 rrca
 jr c,world_alloc_claim
 sla b
 inc e
 jr world_alloc_bit
world_alloc_claim:
 ld a,b
 cpl
 and a,(hl)
 ld (hl),a
 ld h,#0
 ld l,c
 add hl,hl
 add hl,hl
 add hl,hl
 ld a,l
 or a,e
 ld e,a
 ld d,h
 ret
world_alloc_start_masks:
 .db 255,254,252,248,240,224,192,128
