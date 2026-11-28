.module physics_impact_bound
.area _CODE_3
; BC points at the wheel. Return 1 when the audio impact threshold
; cannot be reached, or 0 to request the exact projection.
_riding_impact_projection::
 ld hl,#8
 add hl,bc
 ld d,h
 ld e,l
 ld hl,#_Ct

; Bound each unscaled term in units of 2^20. For the magnitude
; complement U(x)=x or ~x, F=floor(U(x)/4096), N=floor(U(n)/256)
; imply F*N <= abs(x*n)/2^20 <= (F+1)*(N+1).
; The signed lower bound is sufficient because impacts use a strict
; lower threshold. The two products use the ordinary scale tables.
 inc hl
 inc de
 inc de
 inc de
 push hl
 push de
 call impact_term
 pop de
 pop hl
 ret nc
 push bc
 inc hl
 inc hl
 .rept 4
 inc de
 .endm
 call impact_term
 pop hl
 ret nc
 add hl,bc
 ; For the scheduled build, impact is nv < -138412.  -2162*64 =
 ; -138368 leaves a strictly safe margin through the Q14 rounding.
 bit 7,h
 jr z,impact_quiet
 ld a,h
 cp #247
 jr c,impact_unknown
 jr nz,impact_quiet
 ld a,l
 cp #142
 jr nc,impact_quiet
impact_unknown:
 xor a
 ret
impact_quiet:
 ld a,#1
 ret

; HL=normal high byte, DE=velocity high byte. Return a signed lower
; bound in BC, carry set. Larger velocities retain the original dot.
impact_term:
 ld a,(de)
 ld b,a
 add a
 sbc a
 cp b
 jr nz,impact_unknown
 ld b,a
 dec de
 ld a,(de)
 xor b
 cp #8
 jr nc,impact_unknown
 swap a
 ld c,a
 dec de
 ld a,(de)
 xor b
 swap a
 and #15
 or c
 ld c,a
 ld a,(hl)
 xor b
 push af
 ld a,(hl)
 add a
 sbc a
 xor (hl)
 ld e,a
 ld d,#0
 push bc
 push de
 call _riding_unsigned_byte_product
 ; Positive products use the lower corner. For negatives subtract
 ; the product and both digits plus one to reach the upper corner.
 pop hl
 pop bc
 pop af
 bit 7,a
 jr z,impact_term_ready
 ld a,e
 add l
 ld e,a
 ld a,d
 adc #0
 ld d,a
 ld a,e
 add c
 cpl
 ld e,a
 ld a,d
 adc #0
 cpl
 ld d,a
impact_term_ready:
 ld b,d
 ld c,e
 scf
 ret
