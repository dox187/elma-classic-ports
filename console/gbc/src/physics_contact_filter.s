; Exact fine contact filter. ABI1 DE=circle, A=count (0..2), result A.
; Packed contact layout is asserted by physics_contacts.c. Bank9 only.
; Locals: circle0, contact2, remaining4, accepted5.
.module physics_contact_filter
.area _CODE_9
_riding_contact_filter::
 or a,a
 ret z
 add sp,#-6
 ldhl sp,#0
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ld (hl),#<_Ct
 inc hl
 ld (hl),#>_Ct
 inc hl
 ld (hl+),a
 ld (hl),#0
filter_next:
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld bc,#4
 add hl,bc
 ld c,(hl)
 inc hl
 ld b,(hl)
 ; |dot((rx&255),(ry&255),nx,ny)| <=1020 for all signed16 normals.
 ; Therefore l<=405 accepts and l>=414 rejects without rounding changes.
 bit 7,b
 jr nz,filter_accept
 ld a,b
 or a,a
 jr z,filter_accept
 cp #1
 jp nz,filter_reject
 ld a,c
 cp #150
 jr c,filter_accept
 cp #158
 jp nc,filter_reject
 ; Ambiguous band: compute the complete rounded fine projection.
 ld a,#14
 push af
 inc sp
 ldhl sp,#3
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 push bc
 push de
 ldhl sp,#5
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld c,(hl)
 ld de,#4
 add hl,de
 ld e,(hl)
 ld d,#0
 ld hl,#0
 push hl
 push de
 ld e,c
 push hl
 push de
 call _riding_dotq32
 add sp,#13
 ; Add signed16 l*256 to the projection, preserving all four bytes.
 push hl
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld bc,#4
 add hl,bc
 ld c,(hl)
 inc hl
 ld b,(hl)
 pop hl
 ld a,d
 add a,c
 ld d,a
 ld a,l
 adc a,b
 ld l,a
 ld a,h
 adc a,#0
 ld h,a
 ; Signed comparison with104858 (0x0001999a).
 bit 7,h
 jr nz,filter_accept
 ld a,h
 or a,a
 jr nz,filter_reject
 ld a,l
 cp #1
 jr c,filter_accept
 jr nz,filter_reject
 ld a,d
 cp #0x99
 jr c,filter_accept
 jr nz,filter_reject
 ld a,e
 cp #0x9a
 jr nc,filter_reject
filter_accept:
 ldhl sp,#5
 ld a,(hl)
 inc (hl)
 or a,a
 jr nz,filter_reject
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 cp #<_Ct
 jr z,filter_reject
 ld de,#_Ct
 ld b,#10
filter_copy:
 ld a,(hl+)
 ld (de),a
 inc de
 dec b
 jr nz,filter_copy
filter_reject:
 ldhl sp,#4
 dec (hl)
 jr z,filter_done
 ldhl sp,#2
 ld a,(hl)
 add a,#10
 ld (hl+),a
 jr nc,filter_next_jump
 inc (hl)
filter_next_jump:
 jp filter_next
filter_done:
 inc hl
 ld a,(hl)
 add sp,#6
 ret
