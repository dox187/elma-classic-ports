; Stationary ordered contacts. Bank 5 holds the signed margins and reader.
; Return 0 for an unproved input, 2 for positive first-pivot moment or 128
; for negative. Each nonzero result also proves both normal impulses <= 0.
.module physics_stopped_pair
.area _CODE_5
.globl b_riding_stopped_pair_proof
b_riding_stopped_pair_proof = 5
_riding_stopped_pair_proof::
 ld hl,#(_Ct+14)
 ld a,(hl+)
 and #192
 cp #128
 jp nz,stopped_unknown
 ld a,(hl)
 dec a
 jp nz,stopped_unknown
 ; Identify the candidate from its low normal byte, then verify every byte.
 ld a,(#_Ct)
 jp stopped_match

stopped_check:
 ld hl,#_Ct
 call stopped_four_bytes
 jp nz,stopped_unknown
 ld hl,#(_Ct+10)
 call stopped_four_bytes
 jp nz,stopped_unknown
 ld a,(de)
 ld c,a
 inc de
 ld a,(de)
 ld b,a
 push bc                       ; geometry's first table row
 ld hl,#_riding_pair_impulse
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 inc hl
 call stopped_digit
 sub #16                       ; x in [-65536,32767], 24 columns
 cp #24
 jr nc,stopped_drop
 ld e,a
 sub #15
 cp #2
 jr nc,stopped_x_ready
 ; Split the two cells nearest zero into four exact 1024-unit columns each.
 ; HL points to dy; byte 1 of dx supplies bits 10 and 11.
 add a,a
 add a,a
 add #24
 ld e,a
 dec hl
 dec hl
 dec hl
 ld a,(hl+)
 inc hl
 inc hl
 rrca
 rrca
 and #3
 add e
 ld e,a
stopped_x_ready:
 inc hl
 call stopped_digit
 sub #12                       ; y in [-81920,-1], 20 rows
 cp #20
 jr nc,stopped_drop
 ; HL now points to the four torque bytes. Save the bounded signed word.
 ld c,(hl)
 inc hl
 ld b,(hl)
 inc hl
 ld d,a
 ld a,b
 add a,a
 sbc a,a
 cp (hl)
 jr nz,stopped_drop
 inc hl
 cp (hl)
 jr nz,stopped_drop
 pop hl
 push bc
 ld c,e
 ld b,#0
 add hl,bc
 ld c,d
 ld e,l
 ld d,h
 ld l,c
 ld h,b
 .rept 5                      ; 32 columns per row
 add hl,hl
 .endm
 add hl,de
 ld a,(hl)
 pop bc
 or a
 ret z
 ld d,#2
 bit 7,a
 jr z,stopped_positive
 ld d,#128
 bit 7,b
 jr nz,stopped_proven          ; both moment and applied torque negative
 cpl                           ; abs(margin)-1
 jr stopped_limit
stopped_positive:
 bit 7,b
 jr z,stopped_proven
 dec a
 ld e,a
 xor a
 sub c
 ld c,a
 ld a,#0
 sbc b
 ld b,a
 ld a,e
stopped_limit:
 ; An opposing torque of at most (abs(margin)-1)*32 preserves strict sign.
 ld l,a
 ld h,#0
 .rept 5
 add hl,hl
 .endm
 ld a,l
 sub c
 ld a,h
 sbc b
 jr c,stopped_unknown
stopped_proven:
 ld a,d
 ret
stopped_drop:
 pop hl
stopped_unknown:
 xor a
 ret

stopped_four_bytes:
 .rept 3
 ld a,(de)
 cp (hl)
 ret nz
 inc de
 inc hl
 .endm
 ld a,(de)
 cp (hl)
 inc de
 ret

; HL starts at byte 1 of a signed32 value and ends at the next value.
; Map [-131072,65535] to 48 cells. Return 255 outside that range.
stopped_digit:
 ld a,(hl+)
 swap a
 and #15
 ld c,a
 ld a,(hl+)
 add #2
 ld b,a
 inc hl
 ld a,b
 cp #3
 jr nc,stopped_invalid
 cp #2
 sbc a,a                       ; original byte 2 was FE, FF or 00
 dec hl
 cp (hl)
 inc hl
 jr nz,stopped_invalid
 ld a,b
 swap a
 or c
 ret
stopped_invalid:
 ld a,#255
 ret
