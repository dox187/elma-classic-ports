; ABI1 DE=circle, BC=contact. Return signed32 push in DE:BC. A proven
; accepted contact that needs no push can return zero (see the guard below).
.module physics_contact_filter
.area _CODE
; The unsigned 16x8 table reader temporarily selects a lookup bank.
; This short ROM0 call restores the caller's bank before returning to bank9.
fine_unsigned_product:
 call _riding_mul16u8_unsigned
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret
.area _CODE_9
_riding_contact_push::
 ; For lengths 405..408, an exact distance in [103547,104857] is
 ; accepted and needs no push. With both normals in [-4096,16639]
 ; and one <=8191, every possible pair of fractional bytes gives a
 ; rounded dot in [-128,386]. Thus 405*256-128 >= 103547 and
 ; 408*256+386 < 104858. Zero has the same two comparisons here.
 ld h,b
 ld l,c
 inc hl
 inc hl
 inc hl
 inc hl
 ld a,(hl+)
 sub a,#149
 cp a,#4
 jr nc,fine_calculate
 ld a,(hl-)
 dec a
 jr nz,fine_calculate
 dec hl
 ld a,(hl-)
 add a,#16
 cp a,#81
 jr nc,fine_calculate
 cp a,#48
 jr c,fine_check_wider_x
 dec hl
 ld a,(hl)
 add a,#16
 cp a,#48
 jr c,fine_in_band
 jr fine_calculate
fine_check_wider_x:
 dec hl
 ld a,(hl)
 add a,#16
 cp a,#81
 jr nc,fine_calculate
fine_in_band:
 ld de,#0
 ld bc,#0
 ret
fine_calculate:
 ld h,d
 ld l,e
 ld e,(hl)
 inc hl
 inc hl
 inc hl
 inc hl
 ld d,(hl)
 push de  ; fractional Y,X
 ld h,b
 ld l,c
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 push hl  ; ny, followed by length
 ldhl sp,#2
 ld c,(hl)
 call fine_product
 push hl
 push de
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 push hl
 ldhl sp,#9
 ld c,(hl)
 call fine_product
 ; Both raw products are signed32. Byte 0 only contributes its carry
 ; into byte 1. Add the half-unit before extracting bits 14..29.
 ld b,h
 ld c,l
 ldhl sp,#2
 ld a,(hl+)
 add a,e
 ld a,(hl+)
 adc a,d
 ld d,a
 ld a,(hl+)
 adc a,c
 ld e,a
 ld a,(hl)
 adc a,b
 ld b,a
 ld a,d
 add a,#0x20
 ld d,a
 ld a,e
 adc a,#0
 ld c,a
 ld a,b
 adc a,#0
 ld b,a
 sla d
 rl c
 rl b
 sla d
 rl c
 rl b
 ; push=(404-length)*256 + (123-fraction). For all signed16 normals
 ; the rounded fraction fits [-1020,1020]. Its remainder's high byte
 ; is in [-4,4], so adding it to 0x0194 only changes the low byte.
 ld a,#123
 sub a,c
 ld c,a
 ld a,#0
 sbc a,b
 add a,#0x94
 pop hl
 sub a,(hl)
 ld b,a
 inc hl
 ld a,#1
 sbc a,(hl)
 ld e,a
 ld d,#0
 bit 7,(hl)
 jr z,fine_length_positive
 dec d
fine_length_positive:
 ld a,#0
 sbc a,d
 ld d,a
 add sp,#8
 ret

; DE=signed normal, C=unsigned coordinate. Convert the unsigned table
; product to signed by subtracting C from its high byte for a negative
; normal. Each positive or negative product fits signed24.
fine_product:
 ld a,c
 or a,a
 jr z,fine_product_zero
 bit 7,d
 jr z,fine_unsigned_product_jump
 push bc
 call fine_unsigned_product
 pop bc
 ld a,l
 sub a,c
 ld l,a
 ld h,#255
 ret
fine_unsigned_product_jump:
 jp fine_unsigned_product
fine_product_zero:
 ld hl,#0
 ld de,#0
 ret
