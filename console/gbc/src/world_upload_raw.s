; Raw pattern address preparation. Near bank6, ABI0 slot2,id4.
; Preserve the lossless 1024-pattern bank layout and physical slot252 gap.
; world_upload_tile remains responsible for bank restore and safe DMA timing.
.module world_upload_raw
.area _CODE_6
_world_cache_upload_raw::
 ldhl sp,#2
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 inc hl
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 push de
 ; Bank = patterns.bank + (id >> 10).
 ld a,b
 rrca
 rrca
 and a,#63
 ld e,a
 ld d,#0
 ld hl,#_game_world+14
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 add hl,de
 push hl
 ; Offset = patterns.address + ((id & 1023) << 4).
 ld a,b
 and a,#3
 ld h,a
 ld l,c
 add hl,hl
 add hl,hl
 add hl,hl
 add hl,hl
 ld a,(#_game_world+16)
 ld e,a
 ld a,(#_game_world+17)
 ld d,a
 add hl,de
 ld b,h
 ld c,l
 pop de
 ; A partial starting bank can require the following bank.
 bit 7,b
 jr z,raw_bank_ready
 ld a,b
 sub a,#64
 ld b,a
 inc de
raw_bank_ready:
 pop hl
 ld a,h
 or a
 jr nz,raw_slot_gap
 ld a,l
 cp a,#252
 jr c,raw_slot_ready
raw_slot_gap:
 inc hl
 inc hl
 inc hl
 inc hl
raw_slot_ready:
 ; NONBANKED ABI1: bankDE, sourceBC, pattern@SP+2 (callee cleanup).
 push hl
 call _world_upload_tile
 ld hl,#_world_uploads
 inc (hl)
 ret nz
 inc hl
 inc (hl)
 ret
