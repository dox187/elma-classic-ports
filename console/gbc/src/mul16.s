; Signed 16 x 16 -> 32, SM83 SDCC stack ABI 0, return HLDE.
; Keep the multiplicand in HL and the 32-bit product in DE:BC. Interrupts
; remain enabled; no shared scratch RAM or non-reentrant workspace is used.
    .module gbc_mul16
    .area _CODE
_gbc_mul16::
    ldhl sp, #4
    ld c, (hl)
    inc hl
    ld b, (hl)
    ldhl sp, #2
    ld a, (hl+)
    ld h, (hl)
    ld l, a
    ld de, #0
    ld a, #16
001$:
    push af
    bit 0, c
    jr z, 002$
    ld a, e
    add a, l
    ld e, a
    ld a, d
    adc a, h
    ld d, a
    jr 003$
002$:
    xor a
003$:
    rr d
    rr e
    rr b
    rr c
    pop af
    dec a
    jr nz, 001$
    ; Correct the high half for signed operands, modulo 2^32.
    ldhl sp, #3
    bit 7, (hl)
    jr z, 004$
    inc hl
    ld a, e
    sub a, (hl)
    ld e, a
    inc hl
    ld a, d
    sbc a, (hl)
    ld d, a
004$:
    ldhl sp, #5
    bit 7, (hl)
    jr z, 005$
    ldhl sp, #2
    ld a, e
    sub a, (hl)
    ld e, a
    inc hl
    ld a, d
    sbc a, (hl)
    ld d, a
005$:
    ld h, d
    ld l, e
    ld d, b
    ld e, c
    ret
