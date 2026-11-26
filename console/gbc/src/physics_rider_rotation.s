; Each signed displacement in [-511,511] has a high byte in {-2,-1,0,1}.
; Share its low-byte product row between cosine and sine. The signed high
; byte contributes at most two additions to the middle and high bytes.
.area _DATA
rider_rotate_y: .ds 6
rider_rotate_x: .ds 6

.area _CODE
rider_rotate_bank:
 ld a,#31
 ld (#0x2000),a
 call _riding_rotate_local
 ld a,#8
 ld (#0x2000),a
 ret

; C selects the multiplier. DE advances over two signed 24-bit products.
.macro rider_trig_product trig,?positive
 ld a,(#trig)
 ld l,a
 ld a,(hl)
 ld (de),a
 inc de
 inc h
 ld b,(hl)
 ld a,(#trig+1)
 ld l,a
 dec h
 ld a,(hl)
 add b
 ld (de),a
 inc de
 inc h
 ld a,(hl)
 adc #0
 bit 7,l
 jr z,positive
 sub c
positive:
 ld (de),a
 inc de
 dec h
.endm
rider_rotate_low:
 ld l,c
 ld h,#>_riding_scale_directory
 ld a,(hl)
 ld (#0x2000),a
 inc h
 ld h,(hl)
 rider_trig_product _riding_pose_trig
 rider_trig_product _riding_pose_trig+2
 ld a,#31
 ld (#0x2000),a
 ret

.area _CODE_31
; HL is the next displacement, DE its pair of signed 24-bit products.
rider_rotate_axis:
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 push hl
 push de
 push af
 call rider_rotate_low
 pop af
 pop de
 or a
 jr z,rider_axis_done
 ld hl,#_riding_pose_trig
 bit 7,a
 jr z,rider_axis_add
 bit 0,a
 jr nz,rider_axis_sub
 push de
 call rider_axis_subtract
 pop de
 ld hl,#_riding_pose_trig
rider_axis_sub:
 call rider_axis_subtract
 jr rider_axis_done
rider_axis_add:
 .rept 2
 inc de
 ld a,(de)
 add (hl)
 ld (de),a
 inc hl
 inc de
 ld a,(de)
 adc (hl)
 ld (de),a
 inc hl
 inc de
 .endm
rider_axis_done:
 pop hl
 ret
rider_axis_subtract:
 .rept 2
 inc de
 ld a,(de)
 sub (hl)
 ld (de),a
 inc hl
 inc de
 ld a,(de)
 sbc (hl)
 ld (de),a
 inc hl
 inc de
 .endm
 ret

; Bias bit 23 of both products before combining them. For addition the
; outgoing carry cancels that bias. For subtraction the bias cancels in
; the operands and the borrow supplies the sign. |sum| < 2^24.
.macro rider_mix x,y,subtract,?rounded
 ld a,(#x+2)
 xor #0x80
 ld b,a
 ld a,(#y+2)
 xor #0x80
 ld c,a
 ld hl,#y
 ld a,(#x)
 .if subtract
 sub (hl)
 .else
 add (hl)
 .endif
 inc hl
 ld a,(#x+1)
 .if subtract
 sbc (hl)
 .else
 adc (hl)
 .endif
 ld e,a
 ld a,b
 .if subtract
 sbc c
 .else
 adc c
 .endif
 ld l,a
 sbc a,a
 .ifeq subtract
 cpl
 .endif
 ld h,a
 ; Add 2^13 and pack the high bits after division by 2^14.
 ld a,e
 add #32
 jr nc,rounded
 inc hl
rounded:
 add hl,hl
 add hl,hl
 rlca
 rlca
 and #3
 or l
 ld l,a
.endm

_riding_rotate_local::
 ld h,d
 ld l,e
 ld de,#rider_rotate_y
 call rider_rotate_axis
 ld de,#rider_rotate_x
 call rider_rotate_axis
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 rider_mix rider_rotate_x,rider_rotate_y+3,0
 ld d,h
 ld e,l
 pop hl
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 push hl
 rider_mix rider_rotate_y,rider_rotate_x+3,1
 ld d,h
 ld e,l
 pop hl
 ld (hl),e
 inc hl
 ld (hl),d
 ret

.area _CODE_8
; Applying the forward rotation to (y,x) gives the inverse result in
; (world_y,world_x) order, including the independent Q14 dot rounding.
_riding_restore_small::
 ld a,b
 add #2
 cp #4
 jr nc,rider_restore_wide
 or c
 jr z,rider_restore_wide
 ld a,d
 add #2
 cp #4
 jr nc,rider_restore_wide
 or e
 jr z,rider_restore_wide
 add sp,#-4
 ldhl sp,#0
 push hl
 push bc
 push de
 ldhl sp,#0
 ld d,h
 ld e,l
 call rider_rotate_bank
 add sp,#6
 pop bc
 pop de
 .macro rider_restore_axis offset,lo,hi,?positive
 ld hl,#_Bike+offset
 ld a,(hl+)
 ld (#_Bike+72+offset),a
 ld a,(hl+)
 add lo
 ld (#_Bike+73+offset),a
 ld a,(hl+)
 adc hi
 ld (#_Bike+74+offset),a
 ld a,(hl)
 adc #0
 bit 7,hi
 jr z,positive
 dec a
positive:
 ld (#_Bike+75+offset),a
 .endm
 rider_restore_axis 0,e,d
 rider_restore_axis 4,c,b
 ld a,#1
 ret
rider_restore_wide:
 xor a
 ret
