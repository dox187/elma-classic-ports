; Paired tile/attribute copy to 9800, both axes wrap modulo 32.
; Near bank 6, ABI0 x2,y3,vertical4,count5,tiles6,attrs8; count 1..32.
; Enters/returns IRQ enabled, ends with VBK=0. Count 0 changes only VBK to 0.
; A table selects an unrolled entry to avoid per-cell count spills.
; Final STAT sample through both writes is 100 fast T-cycles, less than mode 2's 160 T-cycles.
.module video_strip_pair
.area _CODE_6
.macro pair_bytes
 ld a,(de)
 inc de
 push af
 ld a,(bc)
 inc bc
 push af
1$:
 ldh a,(#0x41)
 and a,#2
 jr nz,1$
 inc a
 ldh (#0x4f),a
 pop af
 ld (hl),a
 xor a
 ldh (#0x4f),a
 pop af
 ld (hl),a
.endm
.macro pair_horizontal_advance
 ld a,l
 inc a
 xor a,l
 and a,#31
 xor a,l
 ld l,a
.endm
.macro pair_vertical_advance
 ld a,l
 add a,#32
 ld l,a
 jr nc,2$
 inc h
 res 2,h
2$:
.endm
_gbc_video_strip_pair::
 ldhl sp,#2
 ld a,(hl+)
 and a,#31
 ld c,a
 ld a,(hl+)
 and a,#31
 rrca
 rrca
 rrca
 ld e,a
 and a,#3
 or a,#0x98
 ld d,a
 ld a,e
 and a,#0xe0
 or a,c
 ld e,a
 ld a,(hl+)
 ld b,(hl)
 inc b
 dec b
 jp z,pair_zero
 push de
 or a,a
 ld a,b
 push af
 ldhl sp,#10
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 push bc
 ldhl sp,#2
 bit 7,(hl)
 ld bc,#pair_horizontal_entries
 jr nz,pair_entry_table_ready
 ld bc,#pair_vertical_entries
pair_entry_table_ready:
 ldhl sp,#3
 ld a,(hl)
 dec a
 add a,a
 ld l,a
 ld h,#0
 add hl,bc
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 pop bc
 pop af
 push hl
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 di
 ret
pair_horizontal_32:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_31:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_30:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_29:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_28:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_27:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_26:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_25:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_24:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_23:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_22:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_21:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_20:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_19:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_18:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_17:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_16:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_15:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_14:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_13:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_12:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_11:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_10:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_9:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_8:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_7:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_6:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_5:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_4:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_3:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_2:
 pair_bytes
 pair_horizontal_advance
pair_horizontal_1:
 pair_bytes
 add sp,#2
 ei
 ret
pair_vertical_32:
 pair_bytes
 pair_vertical_advance
pair_vertical_31:
 pair_bytes
 pair_vertical_advance
pair_vertical_30:
 pair_bytes
 pair_vertical_advance
pair_vertical_29:
 pair_bytes
 pair_vertical_advance
pair_vertical_28:
 pair_bytes
 pair_vertical_advance
pair_vertical_27:
 pair_bytes
 pair_vertical_advance
pair_vertical_26:
 pair_bytes
 pair_vertical_advance
pair_vertical_25:
 pair_bytes
 pair_vertical_advance
pair_vertical_24:
 pair_bytes
 pair_vertical_advance
pair_vertical_23:
 pair_bytes
 pair_vertical_advance
pair_vertical_22:
 pair_bytes
 pair_vertical_advance
pair_vertical_21:
 pair_bytes
 pair_vertical_advance
pair_vertical_20:
 pair_bytes
 pair_vertical_advance
pair_vertical_19:
 pair_bytes
 pair_vertical_advance
pair_vertical_18:
 pair_bytes
 pair_vertical_advance
pair_vertical_17:
 pair_bytes
 pair_vertical_advance
pair_vertical_16:
 pair_bytes
 pair_vertical_advance
pair_vertical_15:
 pair_bytes
 pair_vertical_advance
pair_vertical_14:
 pair_bytes
 pair_vertical_advance
pair_vertical_13:
 pair_bytes
 pair_vertical_advance
pair_vertical_12:
 pair_bytes
 pair_vertical_advance
pair_vertical_11:
 pair_bytes
 pair_vertical_advance
pair_vertical_10:
 pair_bytes
 pair_vertical_advance
pair_vertical_9:
 pair_bytes
 pair_vertical_advance
pair_vertical_8:
 pair_bytes
 pair_vertical_advance
pair_vertical_7:
 pair_bytes
 pair_vertical_advance
pair_vertical_6:
 pair_bytes
 pair_vertical_advance
pair_vertical_5:
 pair_bytes
 pair_vertical_advance
pair_vertical_4:
 pair_bytes
 pair_vertical_advance
pair_vertical_3:
 pair_bytes
 pair_vertical_advance
pair_vertical_2:
 pair_bytes
 pair_vertical_advance
pair_vertical_1:
 pair_bytes
 add sp,#2
 ei
 ret
pair_zero:
 xor a
 ldh (#0x4f),a
 ret
pair_horizontal_entries:
 .dw pair_horizontal_1,pair_horizontal_2,pair_horizontal_3,pair_horizontal_4,pair_horizontal_5,pair_horizontal_6,pair_horizontal_7,pair_horizontal_8,pair_horizontal_9,pair_horizontal_10,pair_horizontal_11,pair_horizontal_12,pair_horizontal_13,pair_horizontal_14,pair_horizontal_15,pair_horizontal_16,pair_horizontal_17,pair_horizontal_18,pair_horizontal_19,pair_horizontal_20,pair_horizontal_21,pair_horizontal_22,pair_horizontal_23,pair_horizontal_24,pair_horizontal_25,pair_horizontal_26,pair_horizontal_27,pair_horizontal_28,pair_horizontal_29,pair_horizontal_30,pair_horizontal_31,pair_horizontal_32
pair_vertical_entries:
 .dw pair_vertical_1,pair_vertical_2,pair_vertical_3,pair_vertical_4,pair_vertical_5,pair_vertical_6,pair_vertical_7,pair_vertical_8,pair_vertical_9,pair_vertical_10,pair_vertical_11,pair_vertical_12,pair_vertical_13,pair_vertical_14,pair_vertical_15,pair_vertical_16,pair_vertical_17,pair_vertical_18,pair_vertical_19,pair_vertical_20,pair_vertical_21,pair_vertical_22,pair_vertical_23,pair_vertical_24,pair_vertical_25,pair_vertical_26,pair_vertical_27,pair_vertical_28,pair_vertical_29,pair_vertical_30,pair_vertical_31,pair_vertical_32
_gbc_video_strip_pair_end::
