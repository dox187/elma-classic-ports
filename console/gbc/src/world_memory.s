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
 ; A contiguous row uses the same forward copy for either direction.
 ; Keep the ring-aware path for a row that crosses the 32-cell boundary.
 ld a,c
 and #63
 rrca
 add a,b
 cp #33
 jr nc,399$
 jp mirror_words
399$:
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
 ; A contiguous row uses the same forward copy for either direction.
 ; Keep the ring-aware path for a row that crosses the 32-cell boundary.
 ld a,c
 and #63
 rrca
 add a,b
 cp #33
 jr nc,499$
 push hl
 ld h,d
 ld l,e
 pop de
 jp mirror_words
499$:
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

; B words, HL source, DE destination. Both spans are contiguous.
mirror_words:
 ld a,b
 cp #4
 jr c,mirror_word_tail
 sub #4
 ld b,a
 .rept 8
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 jr mirror_words
mirror_word_tail:
 or a
 ret z
mirror_word_next:
 .rept 2
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 dec b
 jr nz,mirror_word_next
 ret

; Three independent destination arrays, map planes separated by 512 bytes.
; bank@2 source@4 low@6 high@8 attrs@10 count@12 stride@13.
; Count zero is a no-op; source fragments cannot cross the ROM window.
_world_far_gather3::
 ldhl sp,#12
 ld b,(hl)
 inc hl
 ld c,(hl)
 ld a,b
 or a,a
 ret z
 ; Select one entry for all three planes. Each production row or column
 ; fragment has at most 21 bytes. Enter at the final count instructions
 ; to remove all per-byte tests, including the strided address carry.
 ld hl,#gather_long
 cp #22
 jr nc,gather_selected
 ld e,a
 ld a,c
 dec a
 ld a,e
 jr nz,gather_choose_stride
 add a,a
 add a,e                     ; three instruction bytes per row cell
 ld hl,#gather_row_end
 jr gather_offset
gather_choose_stride:
 add a,a
 add a,a                     ; four instruction bytes per strided cell
 ld hl,#gather_stride_end
gather_offset:
 ld e,a
 ld a,l
 sub e
 ld l,a
 jr nc,gather_selected
 dec h
gather_selected:
 ld a,(#__current_bank)
 push af
 push hl
 ldhl sp,#6
 ld a,(hl+)
 ld (#0x2000),a
 ld a,(hl)
 and a,#1
 ld (#0x3000),a
 ldhl sp,#10                  ; low destination
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld b,#0
 call gather_plane
 ldhl sp,#12                  ; high destination
 ld e,(hl)
 inc hl
 ld d,(hl)
 ldhl sp,#7
 bit 7,(hl)
 jr z,gather_raw_high
 ld a,(hl)
 rra
 and #63
 ldhl sp,#16
 ld b,(hl)                    ; fragment length
gather_fill_high:
 ld (de),a
 inc de
 dec b
 jr nz,gather_fill_high
 ld b,#2                      ; attributes follow the low ID plane
 jr gather_attributes
gather_raw_high:
 ld b,#2
 call gather_plane
 ld b,#4
gather_attributes:
 ldhl sp,#14                  ; attributes destination
 ld e,(hl)
 inc hl
 ld d,(hl)
 call gather_plane
 add sp,#2
 xor a,a
 ld (#0x3000),a
 pop af
 ld (#0x2000),a
 ld (#__current_bank),a
 ret

; DE = destination, C = stride, B = added source pages (0, 2, 4).
; Put the selected routine on the stack, then tail-call it with HL=source.
gather_plane:
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 ldhl sp,#12
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,b
 add a,h
 ld h,a
 ld b,#0
 ret

 .rept 21
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
gather_row_end:
 ret

 .rept 21
 ld a,(hl)
 ld (de),a
 inc de
 add hl,bc
 .endm
gather_stride_end:
 ret

; Keep the complete byte-sized count and arbitrary stride for longer reads.
gather_long:
 push hl
 ldhl sp,#20
 ld b,(hl)
 pop hl
gather_long_loop:
 ld a,(hl)
 ld (de),a
 inc de
 ld a,l
 add a,c
 ld l,a
 jr nc,gather_long_advance
 inc h
gather_long_advance:
 dec b
 jr nz,gather_long_loop
 ret
