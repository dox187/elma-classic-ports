; A is the low byte of MBC5 bank 506 or 507. HL points into the directory,
; DE addresses this cell's word in pattern zero. Called only from sweep bank 4.
; As with the other far readers, interrupt handlers stay in fixed ROM.
.module physics_head_map
.area _CODE
_riding_head_read_map::
 ld (#0x2000),a
 ld a,#1
 ld (#0x3000),a
 ld a,(hl)
 ld (#_head_group_index),a
 ld l,a
 ld h,#0
 add hl,hl
 add hl,hl
 add hl,hl
 add hl,de
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 xor a
 ld (#0x3000),a
 ld a,#4
 ld (#0x2000),a
 ret

.area _DATA
_head_group_index:: .ds 1
_head_cache_x::
head_cache_x: .ds 1
_head_cache_y::
head_cache_y: .ds 1
head_cache_mask: .ds 2
; Store index+1. Copy its zero initializer even on a warm reset.
.area _INITIALIZED
_head_cache_level::
head_cache_level: .ds 1
.area _INITIALIZER
.db 0

.area _CODE_4
; A=cx, E=cy. BC=16 metre bits in row-major order. Returning all ones for
; an out-of-grid cell leaves the full sweep and level-boundary logic in charge.
_riding_head_cell_mask::
 ld b,a
 ld c,e
 ld a,(#_physics_level_index)
 ld hl,#_riding_head_level_count
 cp (hl)
 jr nc,head_no_certificate
 inc a
 ld hl,#head_cache_level
 cp (hl)
 jr nz,head_new_cell
 ld a,(#head_cache_x)
 cp b
 jr nz,head_new_cell
 ld a,(#head_cache_y)
 cp c
 jr nz,head_new_cell
 ld hl,#head_cache_mask
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 ret
head_no_certificate:
 ld bc,#0xffff
 ret
head_new_cell:
 ld a,(#_physics_level_index)
 ld l,a
 ld h,#0
 add hl,hl
 add hl,hl
 add hl,hl
 ld de,#_riding_head_maps
 add hl,de
 ld a,b
 cp (hl)
 jr nc,head_no_certificate
 inc hl
 ld a,c
 cp (hl)
 jr nc,head_no_certificate
 ld (#head_cache_y),a
 ld a,b
 ld (#head_cache_x),a
 ld a,(#_physics_level_index)
 inc a
 ld (#head_cache_level),a

 inc hl
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 push hl
 ld l,c
 ld h,#0
 add hl,hl
 add hl,de
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ; Directory byte address = row start + cx/4.
 ld a,b
 srl a
 srl a
 add a,l
 ld l,a
 jr nc,head_dir_ready
 inc h
head_dir_ready:
 ld d,h
 ld e,l
 pop hl
 ; Pattern byte address before the dictionary index = patterns + 2*(cx%4).
 ld a,b
 and #3
 add a,a
 add a,(hl)
 ld c,a
 inc hl
 ld a,#0
 adc a,(hl)
 ld b,a
 inc hl
 ld a,(hl)
 ld h,d
 ld l,e
 ld d,b
 ld e,c
 call _riding_head_read_map
 ld hl,#head_cache_mask
 ld (hl),e
 inc hl
 ld (hl),d
 ld c,e
 ld b,d
 ret

; ABI0 stack: tagged level base, physical bank low byte, group, cell, rank.
; Returns the palette index in E. Only called from sweep bank 4.
.area _CODE
_riding_head_quarter_code::
 ldhl sp,#2
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld a,(hl+)
 ld (#0x2000),a
 bit 7,d
 jr z,quarter_window
 res 7,d
 ld a,#1
 ld (#0x3000),a
quarter_window:
 ld l,(hl)
 ld h,#0
 add hl,hl
 add hl,de
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 add hl,de
 ld b,h
 ld c,l
 ; Three cumulative counts prefix the sparse codes for a group.
 ldhl sp,#6
 ld a,(hl+)
 ld e,(hl)
 or a
 jr z,quarter_rank
 dec a
 add a,c
 ld l,a
 ld a,b
 adc a,#0
 ld h,a
 ld a,(hl)
 add a,e
 ld e,a
quarter_rank:
 ld a,e
 srl a
 srl a
 ld d,a
 add a,a
 add a,d
 add a,#3
 ld l,a
 ld h,#0
 add hl,bc
 ld b,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld d,(hl)
 bit 1,e
 jr z,quarter_pair
 ld b,c
 swap d
quarter_pair:
 bit 0,e
 jr z,quarter_fields
 swap b
 rrc d
 rrc d
quarter_fields:
 ld a,b
 and #15
 ld b,a
 swap d
 ld a,d
 and #0x30
 or b
 ld e,a
 xor a
 ld (#0x3000),a
 ld a,#4
 ld (#0x2000),a
 ret
