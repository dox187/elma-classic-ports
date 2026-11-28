; The two banked arguments are the new and previous body frame numbers.
.globl b_bike_body_upload
b_bike_body_upload = 13
.area _DATA
_bike_body_slot:: .ds 1
body_stream_pose: .ds 1
body_oam_slot: .ds 1
.area _CODE_13
_bike_body_upload::
 ldhl sp,#6
 ld a,(hl+)
 ld e,a
 ld a,(hl)
 inc a
 jr nz,body_select_pose
 ; Course entry and restoring from a menu both call this with the LCD off.
 ; The signed BG map leaves tiles 0..111 free in OBJ bank 0 and 0..63
 ; in OBJ bank 1. Eleven common body poses fit there until the next menu.
 push de
 ld hl,#_body_preload_poses
 ld b,#11
body_preload:
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 push hl
 push bc
 ld (#_bike_body_slot),a
 rlca
 and #1
 ldh (#0x4f),a
 ld a,#15
 call body_send_span
 pop bc
 pop hl
 dec b
 jr nz,body_preload
 ld a,#1
 ldh (#0x4f),a
 ld a,#255
 ld (#body_stream_pose),a
 ld (#body_oam_slot),a
 pop de
body_select_pose:
 ld a,e
 sub #32
 cp #32
 jr nc,body_stream
 ld c,a
 ld b,#0
 ld hl,#body_resident_slots
 add hl,bc
 ld a,(hl)
 cp #0x84
 jr nz,body_publish
body_stream:
 ld a,#0x84
 ld (#_bike_body_slot),a
 ld hl,#body_stream_pose
 ld a,(hl)
 cp e
 jr z,body_publish_stream
 ld (hl),e
 xor e
 call body_transfer
body_publish_stream:
 ld a,#0x84
body_publish:
 ld (#_bike_body_slot),a
 ld hl,#body_oam_slot
 cp (hl)
 ret z
 ld (hl),a
 ; Hardware tile and OBJ bank change together after the pixels are resident.
 ld c,a
 rlca
 rlca
 rlca
 rlca
 and #8
 ld b,a
 ld a,c
 swap a
 and #0x70
 ld c,a
 ld hl,#(_shadow_OAM+2)
 di
 .rept 8
 ld a,c
 ld (hl+),a
 ld a,b
 ld (hl+),a
 inc hl
 inc hl
 inc c
 inc c
 .endm
 ei
 ret
body_transfer:
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
 .ifdef BODY_PACKED_PLANS
 srl b
 rr c
 jr c,body_plan_odd
 add hl,bc
 ld a,(hl)
 add a
 jr body_plan_pair
body_plan_odd:
 add hl,bc
 ld a,(hl)
 scf
 rla
body_plan_pair:
 ld c,a
 ld a,#0
 adc a
 ld b,a
 ld hl,#body_plan_pairs
 .endif
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
 ld a,(#_bike_body_slot)
 and #7
 or #0x80
 ld d,a
 ld a,e
 rlca
 rlca
 and #3
 add #10
 ld e,l
 jp _bike_body_dma
