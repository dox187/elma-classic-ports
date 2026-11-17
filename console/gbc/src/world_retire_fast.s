; Retire production cache references. Near bank6, ABI0 slots@SP+2,count@4.
; Count0, repeated slots and zero references are valid. No bank/IRQ changes.
; Full uint16_t references; the caller supplies valid slots in [0,444).
.module world_refs_retire_fixed
.area _CODE_6
_world_refs_retire_fixed::
 ldhl sp,#4
 ld b,(hl)
 ld a,b
 or a
 ret z
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
retire_next:
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 push hl
 ld hl,#_world_cache_references
 add hl,de
 add hl,de
 ld a,(hl)
 or a
 jr z,retire_low_zero
 dec (hl)
 jr nz,retire_advance
 inc hl
 ld a,(hl)
 or a
 jr nz,retire_advance
 ; Only an exact transition 1 -> 0 marks the slot free.
 ld a,e
 and #7
 add a,#<retire_masks
 ld l,a
 ld a,#>retire_masks
 adc a,#0
 ld h,a
 ld c,(hl)
 srl d
 rr e
 srl d
 rr e
 srl d
 rr e
 ld hl,#_world_cache_free_bits
 add hl,de
 ld a,(hl)
 or c
 ld (hl),a
retire_advance:
 pop hl
 dec b
 jr nz,retire_next
 ret
retire_low_zero:
 inc hl
 ld a,(hl)
 or a
 jr z,retire_advance
 dec (hl)
 dec hl
 ld (hl),#255
 jr retire_advance
retire_masks:
 .db 1,2,4,8,16,32,64,128
