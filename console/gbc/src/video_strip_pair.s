; Publish both planes of a hidden map strip. ABI0 x2,y3,vertical4,count5,
; tiles6,attrs8. The IRQ sees bank zero and a completed pair of planes.
.module video_strip_pair
.area _CODE_6

.macro stat_window
1$:
 ldh a,(#0x41)
 and #2
 jr nz,1$
.endm

.macro row_byte
 ld a,(de)
 inc de
 ld (hl+),a
.endm

.macro column_byte
 ld a,(de)
 inc de
 ld (hl),a
 add hl,bc
.endm

_gbc_video_strip_pair::
 ldhl sp,#5
 ld a,(hl)
 or a
 jr z,pair_empty
 ldhl sp,#2
 ld a,(hl+)
 and #31
 ld c,a
 ld a,(hl+)
 and #31
 ld b,a
 ld a,(hl+)
 or a
 ld a,c
 jr z,pair_first_length
 ld a,b
pair_first_length:
 ; Split exactly once if a strip wraps the 32x32 tile map. Both passes
 ; share the origin and lengths. C = first span, B = wrapped span.
 cpl
 add #33
 cp (hl)
 jr c,pair_wrap
 ld a,(hl)
pair_wrap:
 push bc                         ; x/y
 ld c,a
 ld a,(hl)
 sub c
 ld b,a
 pop hl                          ; H = y, L = x
 push bc                         ; lengths on stack
 ld a,h
 rrca
 rrca
 rrca
 ld b,a
 and #0xe0
 or l
 ld l,a
 ld a,b
 and #3
 or #0x98
 ld h,a
 push hl                         ; starting destination
 ldhl sp,#12
 ld a,(hl+)
 ld d,(hl)
 ld e,a                          ; attribute source
 di
 ld a,#1
 ldh (#0x4f),a
 call pair_plane
 xor a
 ldh (#0x4f),a
 ldhl sp,#10
 ld a,(hl+)
 ld d,(hl)
 ld e,a                          ; tile source
 call pair_plane
 add sp,#4
 ei
 ret
pair_empty:
 xor a
 ldh (#0x4f),a
 ret

pair_plane:
 ldhl sp,#4                      ; first, wrapped counts
 ld b,(hl)
 ldhl sp,#10                     ; original vertical flag
 ld a,(hl)
 or a
 ld a,b
 push af                         ; retain orientation (Z) and first count
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a                          ; destination
 pop af
 jr nz,pair_column
 call pair_row_span
 ldhl sp,#5
 ld a,(hl)
 or a
 ret z
 push af
 ldhl sp,#4                      ; original row, x = 0
 ld a,(hl+)
 and #0xe0
 ld h,(hl)
 ld l,a
 pop af
 jr pair_row_span

pair_column:
 ld bc,#32
 call pair_column_span
 ldhl sp,#5
 ld a,(hl)
 or a
 ret z
 push af
 ldhl sp,#4                      ; original column, y = 0
 ld a,(hl)
 and #31
 ld l,a
 ld h,#0x98
 pop af
 jr pair_column_span

; Each span stays in one row/column of the hardware map. A poll accepts
; mode 0/1, leaving at least 160 fast T-cycles before VRAM closes. Four
; row writes use 124 T, or four column writes 156 T including the final
; pointer advance. Loop control occurs before the next poll.
pair_row_span:
 cp #4
 jr c,pair_row_tail
 sub #4
 push af
 stat_window
 .rept 4
 row_byte
 .endm
 pop af
 jr pair_row_span
pair_row_tail:
 or a
 ret z
 dec a
 jr z,pair_row_one
 dec a
 jr z,pair_row_two
 stat_window
 row_byte
 row_byte
 row_byte
 ret
pair_row_two:
 stat_window
 row_byte
 row_byte
 ret
pair_row_one:
 stat_window
 row_byte
 ret

pair_column_span:
 cp #4
 jr c,pair_column_tail
 sub #4
 push af
 stat_window
 .rept 4
 column_byte
 .endm
 pop af
 jr pair_column_span
pair_column_tail:
 or a
 ret z
 dec a
 jr z,pair_col_one
 dec a
 jr z,pair_col_two
 stat_window
 column_byte
 column_byte
 column_byte
 ret
pair_col_two:
 stat_window
 column_byte
 column_byte
 ret
pair_col_one:
 stat_window
 column_byte
 ret
_gbc_video_strip_pair_end::
