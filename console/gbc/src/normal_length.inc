; A physical squared length in [65536,168447] selected this bank. One
; reciprocal spans 512 squared units. Its two-byte row holds the base
; length minus 250 and two ascending cuts in the sixteen 32-unit slots.
; A cut and its successor reserve the uncertainty on either side of a
; rounded-length transition. Slot 0 or 15 may border a third transition.
.macro normal_length_reader table, ?second, ?accepted, ?miss
 ld a,(#normal_cache_key+5)
 ld c,a
 and #254
 ld l,a
 ld h,#0
 ld de,#table
 add hl,de
 ld a,(hl+)
 ld b,a
 ld e,(hl)
 ld a,(#normal_cache_key+4)
 rr c
 rra
 rrca
 rrca
 rrca
 rrca
 and #15
 ld c,a
 jr z,miss
 cp #15
 jr z,miss
 ld a,e
 and #15
 ld d,a
 ld a,c
 sub d
 jr c,second
 cp #2
 jr c,miss
 inc b
second:
 swap e
 ld a,e
 and #15
 ld e,a
 ld a,c
 sub e
 jr c,accepted
 cp #2
 jr c,miss
 inc b
accepted:
 ld c,b
 ret
miss:
 ld c,#0
 ret
.endm
