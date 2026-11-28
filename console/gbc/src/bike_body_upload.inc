; The two banked arguments are the new and previous body frame numbers.
.globl b_bike_body_upload
b_bike_body_upload = 13
_bike_body_upload::
 ldhl sp,#6
 ld a,(hl+)
 ld e,a
 xor (hl)
 ld c,a
 ld b,#0
 ld hl,#body_xor_slots
 add hl,bc
 ld a,(hl)
 cp #16
 jr nc,body_full
 ld c,a
 ld a,e
 swap a
 ld b,a
 and #0xf0
 or c
 ld c,a
 ld a,b
 and #15
 ld b,a
 ld hl,#body_plan_ids
 add hl,bc
 ld c,(hl)
 ld b,#0
 ld hl,#body_spans
 add hl,bc
 add hl,bc
 ld a,(hl+)
 cp #255
 ret z
 ld c,(hl)
 inc c
 jr z,body_send_span
 dec c
 push bc
 push de
 call body_send_span
 pop de
 pop bc
 ld a,c
 jr body_send_span
body_full:
 ld a,#15
body_send_span:
 ; High nibble = starting tile, low nibble = count minus one.
 ; Each raw 256-byte body starts on a page in banks 10..12.
 ld c,a
 and #15
 inc a
 ld b,a
 ld a,e
 and #63
 or #0x40
 ld h,a
 ld a,c
 and #0xf0
 ld l,a
 ld d,#0x84                    ; signed-background body tiles 64..79
 ld a,e
 rlca
 rlca
 and #3
 add #10
 ld e,l
 jp _bike_body_dma
