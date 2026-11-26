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
rider_restore:
 ld a,(#__current_bank)
 ld (#0x2000),a
 ret
rider_wide:
 ret                          ; tail-call the saved full-width entry

; DE is the signed16 relative velocity and HL points to the signed16
; spring displacement. Both products use the same physical ROM bank.
_riding_rider_pair16::
  .ifdef RIDING_DIRECT_RIDER_BANK
 ; Both rounded values in these intervals, and their difference, fit signed16.
 ; Each of four damper ranges shares a bank with the direct spring pages.
 ld a,d
 add a,#32
 cp #64
 jr nc,rider_pair_general
 ld a,(hl+)
 ld c,a
 ld a,(hl-)
 ld b,a
 add a,#4
 cp #8
 jr nc,rider_pair_general
 ld a,(#_riding_subphase)
 sub #1
 sbc a,a
 and #4
 xor #(RIDING_DIRECT_RIDER_BANK+4)
 ld h,a
 ld a,d
 swap a
 and #3
 or h
 ld (#0x2000),a
 ld a,d
 and #15
 add a,a
 add a,#0x50
 ld h,a
 ld l,e
 ld e,(hl)
 inc h
 ld d,(hl)
 ld a,b
 and #7
 add a,a
 add a,#0x40
 ld h,a
 ld l,c
 ld a,(hl)
 sub a,e
 ld e,a
 inc h
 ld a,(hl)
 sbc a,d
 ld d,a
 add a,a
 sbc a,a
 ld h,a
 ld l,a
 jr rider_restore
rider_pair_general:
 .endif
 ld a,#2
 ld (#0x2000),a
 call rider_pair_lookup
 jr rider_restore

.area _CODE_2
rider_lookup:
 ld a,(#_riding_subphase)
 or a
 jr z,rider_full
 ld a,#7
rider_full:
 add a,c
rider_lookup_page:
 .ifdef RIDING_ALIGNED_RIDER_ROWS
 ; Page-aligned planes use each raw input byte directly as L.
 add a,#>_riding_rider_rows
 ld h,a
 ld l,e
 ld e,(hl)
 inc h
 ld c,(hl)
 inc h
 ld b,(hl)
 inc h
 ld l,d
 .else
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
 .endif
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

rider_pair_lookup:
 push hl
 ld a,(#_riding_subphase)
 or a
 jr z,rider_pair_phase
 ld a,#7
rider_pair_phase:
 ld c,a
 ld a,d
 or e
 jr z,rider_pair_spring_only
 ld a,c
 push af
 add a,#14
 call rider_lookup_page       ; signed24 damper in HL:DE
 ld b,h
 ld c,l
 pop af
 pop hl
 push bc
 push de
 ld e,(hl)
 inc hl
 ld d,(hl)
 call rider_lookup_page       ; signed24 spring in HL:DE
 ld b,h
 ld c,l
 ldhl sp,#0
 ld a,e
 sub (hl)
 ld e,a
 inc hl
 ld a,d
 sbc (hl)
 ld d,a
 inc hl
 ld a,c
 sbc (hl)
 ld c,a
 inc hl
 ld a,b
 sbc (hl)
 ld h,a
 ld l,c
 add sp,#4
 ret
rider_pair_spring_only:
 pop hl
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld a,c
 jp rider_lookup_page
