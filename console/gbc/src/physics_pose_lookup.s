; Exact Q14 phase geometry, shared by the head, rider and suspension.
.module physics_pose_lookup
.area _HRAM
_riding_pose_cosine:: .ds 4
_riding_pose_sine:: .ds 4
pose_cos_ax: .ds 3
pose_neg_cos_ay: .ds 3
pose_sin_ax: .ds 3

.area _CODE
; A selects the other quarter wave. Its word address is $c000-HL.
.macro pose_reflect
 ld (#0x2000),a
 xor a
 sub a,l
 ld l,a
 ld a,#0xc0
 sbc a,h
 ld h,a
.endm

; Bank 8 supplies the rounded phase in DE. Start both wave reads here so
; the scale table bank only needs to be selected once.
_riding_refresh_geometry::
 ld a,d
 rlca
 rlca
 rlca
 and a,#7
 ld c,a                         ; full-turn octant
 ld b,#0
 ld a,d
 and a,#31
 ld h,a
 or a,e
 jr z,pose_octant_endpoint
 ld l,e
 add hl,hl
 set 6,h                        ; $4000 + 2 * (phase modulo 8192)
 push hl
 ld hl,#pose_octant_banks
 add hl,bc
 add hl,bc
 ld a,(hl+)
 ld d,a
 ld e,(hl)
 pop hl
 ld a,d
 ld (#0x2000),a
 bit 1,c
 jr nz,pose_forward_cos
 ld c,(hl)
 inc l
 ld b,(hl)
 dec l
 ld a,e
 pose_reflect
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 jr pose_trig_ready
pose_forward_cos:
 ld a,e
 ld e,(hl)
 inc l
 ld d,(hl)
 dec l
 pose_reflect
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 jr pose_trig_ready
pose_octant_endpoint:
 ; At a quarter or eighth turn the positive and negative interpolation
 ; tables meet. Read the exact Q14 endpoint pair by octant.
 ld hl,#pose_endpoints
 add hl,bc
 add hl,bc
 add hl,bc
 add hl,bc
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
pose_trig_ready:
 ld a,#1
 ldh (#__current_bank),a
 ld (#0x2000),a
 call pose_scale_pair
 ld a,#8
 ldh (#__current_bank),a
 ld (#0x2000),a
 ret

.area _CODE
; Each octant reads one forward and one reflected quarter wave. The
; negative interpolation table has its own downward rounding.
pose_octant_banks:
 .db 16,17, 17,16, 18,17, 19,16, 18,19, 19,18, 16,19, 17,18

pose_endpoints:
 .dw 0,16384,11585,11585,16384,0,11585,-11585
 .dw 0,-16384,-11585,-11585,-16384,0,-11585,11585

.area _CODE_1
; DE is the signed trig input. Its high byte selects a sixteen-byte page
; with two row pointers and signed bases. The low byte indexes both rows.
.macro pose_rows
 ld a,d
 add a,#64
 swap a
 ld h,a
 and a,#0xf0
 ld l,a
 xor a,h
 ld h,a
 add hl,bc
 ld a,(hl+)
 add a,e
 ld c,a
 ld a,(hl+)
 adc a,#0
 ld b,a
 ld a,(hl+)
 add a,e
 ld e,a
 ld a,(hl+)
 adc a,#0
 ld d,a
 ; BC and DE point at the head and suspension residuals. HL now
 ; points at the signed bases, in the order they are consumed.
.endm

.macro pose_head dest
 ld a,(bc)
 add a,(hl)
 inc hl
 ldh (#dest),a
 ld a,(hl+)
 adc a,#0
 ldh (#dest+1),a
.endm

; AX is always positive-scale. The Y and rest bases store B-1 so both
; signs share each page. (B-1)+R+1 gives B+R; ~R-(B-1) gives -(B+R).
.macro pose_anchor_x dest
 ld a,(de)
 add a,(hl)
 inc hl
 ldh (#dest),a
 inc d
 inc d
 ld a,(de)
 adc a,(hl)
 inc hl
 ldh (#dest+1),a
 ld a,(hl+)
 adc a,#0
 ldh (#dest+2),a
.endm

.macro pose_anchor_y sine
 ld a,(de)
 .if sine
 scf
 adc a,(hl)
 ld c,a
 .else
 cpl
 sub a,(hl)
 ldh (#pose_neg_cos_ay),a
 .endif
 inc hl
 inc d
 inc d
 ld a,(de)
 .if sine
 adc a,(hl)
 ld b,a
 .else
 cpl
 sbc a,(hl)
 ldh (#pose_neg_cos_ay+1),a
 .endif
 inc hl
 .if sine
 ld a,(hl)
 adc a,#0
 ld e,a
 .else
 ld a,#255
 sbc a,(hl)
 ldh (#pose_neg_cos_ay+2),a
 .endif
.endm

.macro pose_scale head,rest,ax,sine
 ld bc,#_riding_pose_pages
 pose_rows
 pose_head head
 ld a,b
 add a,#8
 ld b,a
 pose_head head+2
 ld a,(de)
 .if sine
 cpl
 sub a,(hl)
 .else
 scf
 adc a,(hl)
 .endif
 inc hl
 ld (#rest),a
 .if sine
 ld a,#255
 sbc a,(hl)
 inc hl
 .else
 ld a,(hl+)
 adc a,#0
 .endif
 ld (#rest+1),a
 inc d
 inc d
 pose_anchor_x ax
 inc d
 inc d
 pose_anchor_y sine
.endm

; BC,E hold one signed24 operand and HRAM holds the other. Publish both
; center-span and center+span as signed32. The newly decoded sine Y stays
; in registers for the first pair.
.macro pose_pair memory,dest,center_in_regs
 ld hl,#dest
 ldh a,(#memory)
 .if center_in_regs
 cpl
 scf
 adc a,c
 .else
 sub a,c
 .endif
 ld (hl+),a
 ldh a,(#memory+1)
 .if center_in_regs
 cpl
 adc a,b
 .else
 sbc a,b
 .endif
 ld (hl+),a
 ldh a,(#memory+2)
 .if center_in_regs
 cpl
 adc a,e
 .else
 sbc a,e
 .endif
 ld (hl+),a
 rla
 sbc a,a
 ld (hl+),a
 ldh a,(#memory)
 add a,c
 ld (hl+),a
 ldh a,(#memory+1)
 adc a,b
 ld (hl+),a
 ldh a,(#memory+2)
 adc a,e
 ld (hl+),a
 rla
 sbc a,a
 ld (hl),a
.endm

pose_scale_pair:
 push bc
 ld hl,#_riding_pose_trig
 ld a,(hl+)
 cp e
 jr nz,pose_update_cosine
 ld a,(hl)
 cp d
 jr nz,pose_update_cosine
 or e                           ; the first zero can precede a valid cache
 jp nz,pose_keep_cosine
pose_update_cosine:
 ld (hl),d
 dec hl
 ld (hl),e
 ld a,d
 sub #63
 cp #2
 jr nc,pose_read_cosine
 ; Upright riding frequently selects cosine $3f00..$4000. These eight-byte
 ; records omit the invariant high bytes verified by the table generator.
 ld h,d
 ld l,e
 add hl,hl
 add hl,hl
 add hl,hl
 ld bc,#(_riding_pose_hot_rows-(0x3f00*8))
 add hl,bc
 ld a,(hl+)
 ldh (#_riding_pose_cosine),a
 xor a
 ldh (#_riding_pose_cosine+1),a
 ld a,(hl+)
 ldh (#_riding_pose_cosine+2),a
 ld a,#2
 ldh (#_riding_pose_cosine+3),a
 ld a,(hl+)
 ld (#_riding_pose_rest+2),a
 ld a,(hl+)
 ld (#_riding_pose_rest+3),a
 ld a,(hl+)
 ldh (#pose_cos_ax),a
 ld a,(hl+)
 ldh (#pose_cos_ax+1),a
 ld a,#3
 ldh (#pose_cos_ax+2),a
 ld a,(hl+)
 ldh (#pose_neg_cos_ay),a
 ld a,(hl)
 ldh (#pose_neg_cos_ay+1),a
 ld a,#0xfd
 ldh (#pose_neg_cos_ay+2),a
 jr pose_keep_cosine
pose_read_cosine:
 pose_scale _riding_pose_cosine,_riding_pose_rest+2,pose_cos_ax,0
pose_keep_cosine:
 pop de
 ld hl,#_riding_pose_trig+2
 ld a,e
 ld (hl+),a
 ld (hl),d
 pose_scale _riding_pose_sine,_riding_pose_rest,pose_sin_ax,1
 pose_pair pose_cos_ax,_riding_pose_anchor,1
 ld hl,#pose_sin_ax
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld e,(hl)
 pose_pair pose_neg_cos_ay,_riding_pose_anchor+8,0
 ret
