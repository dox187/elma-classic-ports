.module extended_wheel

.area _HEAP
_riding_extended_contacts::
 .ds extended_ram_end-extended_ram
extended_bank::
 .ds 1
extended_reader::
 .ds 2

extended_min_y = _riding_extended_contacts + (extended_min_y_src-extended_ram)
extended_span_y = _riding_extended_contacts + (extended_span_y_src-extended_ram)
.globl extended_min_y, extended_span_y

.area _CODE_33
_riding_extended_install::
 ld hl,#extended_ram
 ld de,#_riding_extended_contacts
 ld b,#extended_ram_end-extended_ram
extended_copy:
 ld a,(hl+)
 ld (de),a
 inc de
 dec b
 jr nz,extended_copy
 ld hl,#extended_course_params
 ld a,#<465
 jp extended_map

; Like contacts(), X arrives in DE:BC and Y arrives on the stack. The
; wheel pointer follows Y in the caller's frame. Keep the original ABI
; intact until we know the tile contains this center.
extended_ram:
 ldhl sp,#3
 ld a,(hl)
extended_min_y_src = .+1
 sub #0
extended_span_y_src = .+1
 cp #0
 jp nc,_riding_contacts_fallback
 ld a,#33
 ld (#0x2000),a
 jp extended_query
extended_ram_end::

extended_query:
 ldh (#__current_bank),a
 push bc
 push de
 ldhl sp,#10
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld hl,#extended_reader
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld a,(#extended_bank)
 call extended_map
 cp #255
 jr z,extended_fallback
 cp #2
 jr nz,extended_answer
 ld hl,#direct_project_pair
 ld e,#28
 call ___sdcc_bcall_ehl
 ld a,#2
extended_answer:
 pop de
 pop bc
 pop hl
 add sp,#4
 jp extended_restore
extended_fallback:
 pop de
 pop bc
 ld hl,#_riding_contacts_fallback
 jp extended_restore

; Share the fixed-ROM MBC5 high-bank trampoline used by Gravity Ride.
extended_map:
 push de
 jp _riding_corner_map

.area _CODE
extended_restore:
 push af
 ld a,#9
 ldh (#__current_bank),a
 ld (#0x2000),a
 pop af
 jp (hl)
