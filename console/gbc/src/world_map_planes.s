; Raw world map planes, SRAM bank 0 B000..B3FF tiles and B400..B7FF attributes.
; The world always publishes 21 cells in an entering row. Columns contain
; 1..19 cells, and their rows have already been installed. Callers run on
; the double-speed CGB main loop with interrupts enabled and RAM enabled.
.module world_map_planes
.area _CODE_6
.macro wait_vram
1$:
 ldh a,(#0x41)
 and #2
 jr nz,1$
.endm
; ABI0 x@2, y@3, orientation@4, count@5. All calls originate in bank 6.
; Map origin HL = B000 + 32*(y&31)+(x&31). BC = count and orientation.
.macro map_origin
 xor a
 ld (#0x4000),a
 ldhl sp,#2
 ld a,(hl+)
 and #31
 ld e,a
 ld a,(hl+)
 and #31
 rrca
 rrca
 rrca
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ld a,d
 and #0xe0
 or e
 ld l,a
 ld a,d
 and #3
 or #0xb0
 ld h,a
.endm
.macro plane_get_word
 ; VBK0 slots 0..251 store their own tile index. VBK1 slots 252..443
 ; store slot-252. Recover the original 16-bit reference exactly.
 ld a,(hl)
 and a
 set 2,h
 bit 3,(hl)
 res 2,h
 jr z,2$
 add #252
2$:
 ld (de),a
 inc de
 ld a,#0
 adc #0
 ld (de),a
 inc de
.endm
_world_plane_slots::
 map_origin
 push hl
 ldhl sp,#8
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 pop hl
 ld a,c
 or a
 jr nz,plane_get_column
 ld a,l
 and #0xe0
 ld c,a
plane_get_row:
 plane_get_word
 ld a,l
 inc a
 and #31
 or c
 ld l,a
 dec b
 jr nz,plane_get_row
 ret
plane_get_column:
 plane_get_word
 ld a,l
 add #32
 ld l,a
 jr nc,plane_get_next
 inc h
 res 2,h
plane_get_next:
 dec b
 jr nz,plane_get_column
 ret

_gbc_video_world_strip_pair::
 map_origin
 push hl
 ldhl sp,#10
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 ldhl sp,#8
 ld a,(hl+)
 ld h,(hl)
 ld l,a
; The exact SRAM origin is on the stack, HL/DE are tiles/attributes,
; and B/C are count/orientation. Both paths consume the pushed origin.
_world_write_planes::
 ld a,c
 or a
 jr nz,plane_put_column
 ld b,h
 ld c,l
 pop hl
 push hl
 push bc
 set 2,h
 call plane_write_row
 pop de
 pop hl
 push hl
 call plane_write_row
 pop hl
 ld a,l
 and #0xe0
 ld l,a
 di
 ld a,#1
 ldh (#0x4f),a
 set 2,h
 call plane_dma_row
 res 2,h
 xor a
 ldh (#0x4f),a
 call plane_dma_row
 ei
 ret
plane_put_column:
 push bc
 push hl
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 set 2,h
 di
 ld a,#1
 ldh (#0x4f),a
 call plane_column_copy
 pop de
 pop bc
 pop hl
 xor a
 ldh (#0x4f),a
 call plane_column_copy
 ei
 ret
; HL starts at the SRAM cell, DE at input. B/C hold the paired SRAM
; and VRAM high bytes. Both map addresses always share L. On a carry,
; XOR their common change in bits 0..1 into the SRAM address.
.macro plane_col_byte done
 ld a,(de)
 inc de
 ld (hl),a
 ld h,b
 ld (hl),a
 ld h,c
 ld a,l
 add #32
 ld l,a
 jr nc,done
 inc c
 res 2,c
 ld a,h
 xor c
 xor b
 ld b,a
 ld h,c
done:
.endm
plane_column_copy:
 ; Every column cell belongs to a row already installed in both VRAM and
 ; SRAM. Consume an unchanged prefix without waiting for the LCD.
plane_column_prefix:
 ld a,(de)
 cp (hl)
 jr nz,plane_column_changed
plane_column_same:
 inc de
 ld a,l
 add #32
 ld l,a
 jr nc,plane_prefix_next
 ld a,h
 inc a
 xor h
 and #3
 xor h
 ld h,a
plane_prefix_next:
 dec b
 jr nz,plane_column_prefix
 ret
plane_column_changed:
 ld a,b
 push af
 ld b,h
 ld a,h
 and #3
 or #0x98
 ld c,a
 ld h,a
 pop af
plane_column_loop:
 cp #2
 jr c,plane_column_last
 sub #2
 push af
 wait_vram
 plane_col_byte plane_col_mid
 plane_col_byte plane_col_end
 pop af
 or a
 ret z
 ld h,b
 ld b,a
 ld a,(de)
 cp (hl)
 jr z,plane_column_same
 ld a,b
 ld b,h
 ld h,c
 jr plane_column_loop
plane_column_last:
 or a
 ret z
 wait_vram
 ld a,(de)
 ld (hl),a
 ld h,b
 ld (hl),a
 ret

; Two spans at most. Skip a prefix of 21 unrolled copies using a byte
; offset, then wrap to the beginning of this SRAM row.
plane_write_row:
 ld a,l
 and #31
 cp #12
 jr nc,plane_row_wrap
 jr plane_row_21
plane_row_wrap:
 sub #11                       ; cells following x=31
 push af
 ld c,l
 ld a,c
 and #0xe0
 ld c,a
 ld b,h
 push bc
 ld a,l
 and #31
 sub #11                       ; skip this many copies of first span
 call plane_short_span
 pop bc
 ld h,b
 ld l,c
 pop af
 ld b,a
 ld a,#21
 sub b
plane_short_span:
 ; HL destination and DE source remain live while the return address
 ; transfers control to the appropriate unrolled suffix.
 push hl
 ld l,a
 add a,a
 add a,l
 ld l,a
 ld h,#0
 ld bc,#plane_row_21
 add hl,bc
 ld b,h
 ld c,l
 pop hl
 push bc
 ret
plane_row_21:
 .rept 21
 ld a,(de)
 inc de
 ld (hl+),a
 .endm
 ret

plane_dma_row:
 ld a,h
 ldh (#0x51),a
 ld a,l
 ldh (#0x52),a
 ld a,h
 and #3
 or #0x18
 ldh (#0x53),a
 ld a,l
 ldh (#0x54),a
 ; A sampled mode 2/3 will flow through an entire rendering phase
 ; before VRAM reopens. Catch its end and spend both blocks inside the
 ; fresh HBlank plus the subsequent 80-dot OAM scan.
 ldh a,(#0x41)
 and #2
 jr nz,plane_dma_transition
 ; An already-open window may be about to end. Keep each block inside
 ; the following 160 fast T-cycles and recheck for the second block.
 xor a
_world_row_dma_first::
 ldh (#0x55),a
 ; A 32-byte-aligned row never crosses a 256-byte page. Only the two
 ; low address registers can change during the first sixteen bytes.
 ld a,l
 or #16
 ldh (#0x52),a
 ldh (#0x54),a
 wait_vram
 xor a
_world_row_dma_second::
 ldh (#0x55),a
 ret
plane_dma_transition:
 wait_vram
 ld a,#1
_world_row_dma_burst::
 ldh (#0x55),a
 ret

; On course entry or return from the menu, capture both entire 32x32
; hardware maps. The eleven unused cells of a newly published row then
; survive bit for bit, including cells last changed by menu drawing.
_world_map_snapshot::
 xor a
 ld (#0x4000),a
 ld de,#0xb000
 ld c,a
plane_snapshot_bank:
 ld hl,#0x9800
 ld b,#0
plane_snapshot_group:
 di
 ld a,c
 ldh (#0x4f),a
 wait_vram
 .rept 4
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 xor a
 ldh (#0x4f),a
 ei
 dec b
 jr nz,plane_snapshot_group
 inc c
 bit 1,c
 jr z,plane_snapshot_bank
 ret
