; Rider acceleration consumes only the rounded spring/damper impulse.
; When the input fits signed16, the two byte contributions and their exact
; fractional carry fit a small table. Wider inputs use the full Q24 kernel.
.module physics_rider_coeff
.area _CODE
_riding_rider_s::
 ld c,#0                       ; two seven-page spring tables
 ld hl,#_riding_rider_s_wide
 jr rider_check_input
_riding_rider_f::
 ld c,#14                      ; two damper tables follow the spring
 ld hl,#_riding_rider_f_wide
rider_check_input:
 push hl
 ldhl sp,#4
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 add a,a
 sbc a,a
 cp a,(hl)
 jr nz,rider_wide
 inc hl
 cp a,(hl)
 jr nz,rider_wide
 pop hl
 ld a,#2
 ld (#0x2000),a
 call rider_lookup
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret
rider_wide:
 ret                          ; tail-call the saved full-width entry

.area _CODE_2
rider_lookup:
 ld a,(#_riding_subphase)
 or a
 jr z,rider_full
 ld a,#7
rider_full:
 add a,c
 ld hl,#_riding_rider_rows
 add a,h
 ld h,a
 push hl
 ld c,e
 ld b,#0
 add hl,bc
 ld e,(hl)                    ; low fractional rank
 inc h
 ld c,(hl)
 inc h
 ld b,(hl)                    ; low integer contribution in BC
 pop hl
 ld a,d                       ; signed high byte as its raw table index
 add a,l
 ld l,a
 ld a,h
 adc a,#3
 ld h,a
 ld a,e
 cp a,(hl)
 ccf                          ; carry iff low rank reaches the threshold
 inc h
 ld a,c
 adc a,(hl)
 ld e,a
 inc h
 ld a,b
 adc a,(hl)
 ld d,a
 inc h
 ld a,#0
 adc a,(hl)
 ld l,a
 rla
 sbc a,a
 ld h,a                       ; signed24 result extended to ABI0 HL:DE
 ret
