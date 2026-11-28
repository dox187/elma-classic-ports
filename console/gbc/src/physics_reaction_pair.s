; Both arms of a wheel use the same torque. Map each of its two byte
; rows once. The stack holds the upper row of
; both unsigned products, with X on top.
.module physics_reaction_pair
.area _DATA
ss_pair_ready:: .ds 1
; The signed-background cartridge keeps SRAM bank 0 selected while riding.
; Its radial directory ends at AA51 and the map planes start at B000.
ss_pair_code = 0xab00
.area _CODE
ss_pair_entry::
 ld a,(#ss_pair_ready)
 or a
 jp z,ss_pair_fallback
 jp ss_pair_code
.area _CODE_13
ss_pair_init::
 ld a,#10
 ld (#0),a
 xor a
 ld (#0x4000),a
 ld hl,#ss_pair_image
 ld de,#ss_pair_code
 ld bc,#(ss_pair_end-ss_pair_image)
001$:
 ld a,(hl+)
 ld (de),a
 inc de
 dec bc
 ld a,b
 or c
 jr nz,001$
 inc a
 ld (#ss_pair_ready),a
 jp haircut_prepare_gate
ss_pair_image::
 ; BC:DE = torque. The small signed high word K is in [-3,2].
 ; A signed12 arm times a torque in this range, rounded at Q14, fits
 ; signed16. Larger arms and torques use the unchanged full projection.
 ld a,c
 add #3
 cp #6
 jp nc,ss_pair_fallback
 ld a,c
 add a
 sbc a
 cp b
 jp nz,ss_pair_fallback
 ld a,(#ss_coarse+1)
 add #8
 ld l,a
 ld a,(#ss_coarse+3)
 add #8
 or l
 and #0xf0
 jp nz,ss_pair_fallback

 ld a,e
 ld (#ss_tr),a
 ld a,d
 ld (#ss_tr+1),a
 ld a,c
 ld (#ss_tr+2),a
 .macro pair_row
 ld l,a
 ld h,#>_riding_scale_directory
 ld a,(hl)
 ld (#0x2000),a
 inc h
 ld h,(hl)
 .endm
 ld a,d
 pair_row
 .macro pair_upper arm
 ld a,(#ss_coarse+arm)
 ld l,a
 ld e,(hl)                    ; hi*arm_lo, low byte
 inc h
 ld d,(hl)
 ld a,(#ss_coarse+arm+1)
 ld l,a
 ld a,(hl)
 dec h
 ld c,a
 ld a,(hl)
 add d
 ld b,a
 ld a,c
 adc #0
 ld c,a
 push bc                       ; B then C = middle then top
 push de                       ; E = bottom
 .endm
 pair_upper 2
 pair_upper 0
 ld a,(#ss_tr)
 pair_row
 .macro pair_lower arm,dest,flip,?positive,?zero,?once,?plus,?corrected,?rounded
 ; floor(lo*arm/256) needs the high byte of lo*arm_lo and both
 ; bytes of lo*arm_hi. Product byte zero cannot affect Q14 rounding.
 inc h
 ld a,(#ss_coarse+arm)
 ld l,a
 ld d,(hl)
 ld a,(#ss_coarse+arm+1)
 ld l,a
 ld b,(hl)
 dec h
 ld a,(hl)
 add d
 ld c,a
 ld a,b
 adc #0
 ld b,a
 pop de
 ld a,c
 add e
 ld e,a                        ; complete product byte one
 ld a,b
 pop bc
 adc b
 ld d,a
 ld a,c
 adc #0
 ld c,a                        ; C:D is the upper word
 push hl                       ; preserve the shared table page
 bit 7,l
 jr z,positive
 ld hl,#ss_tr
 ld a,d
 sub (hl)
 ld d,a
 inc hl
 ld a,c
 sbc (hl)
 ld c,a
positive:
 ld h,c
 ld l,d
 ld a,(#ss_tr+2)
 or a
 jr z,corrected
 ld d,a
 ld a,(#ss_coarse+arm)
 ld c,a
 ld a,(#ss_coarse+arm+1)
 ld b,a
 bit 7,d
 jr z,once
 xor a
 sub c
 ld c,a
 sbc a
 sub b
 ld b,a
 inc d
 jr z,plus
 inc d
 jr z,zero
 add hl,bc
 jr zero
once:
 dec d
 jr z,plus
zero:
 add hl,bc
plus:
 add hl,bc
corrected:
 ld a,e
 add #32
 jr nc,rounded
 inc hl
rounded:
 rlca
 rlca
 and #3
 add hl,hl
 add hl,hl
 or l
 .if flip
 cpl
 ld l,a
 ld a,h
 cpl
 ld h,a
 inc hl
 ld a,l
 .endif
 ld e,a
 ld d,h
 ld a,h
 add a
 sbc a
 ld b,a
 ld c,a
 .ifnb dest
 ld hl,#dest
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,b
 ld (hl+),a
 ld (hl),a
 .endif
 pop hl
 .endm
 ; Negate the rounded X-arm projection for the Y force. The second
 ; projection remains in BC:DE for immediate publication to the wheel.
 pair_lower 0,ss_pair_y,1
 pair_lower 2,,0
 ldh a,(#__current_bank)
 ld (#0x2000),a
 ret
ss_pair_end::

.ifgt ss_pair_end-ss_pair_image-0x1a0
 .error 1
.endif
