; Exact Q14 phase geometry, shared by the head, rider and suspension.
.module physics_pose_lookup
.area _HRAM
_riding_pose_cosine:: .ds 4
_riding_pose_sine:: .ds 4
pose_cos_ax: .ds 3
pose_neg_cos_ay: .ds 3
pose_sin_ax: .ds 3
pose_sin_ay: .ds 3

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

.area _CODE_1
pose_scale_pair:
 push bc                        ; sine; cosine in DE
 ld hl,#_riding_pose_trig
 ld a,e
 ld (hl+),a
 ld a,d
 ld (hl+),a
 ld a,c
 ld (hl+),a
 ld (hl),b
 call pose_cos_scale
 pop de
 call pose_sin_scale

; Both coordinate pairs are (center-span, center+span). Each operand and
; result fits signed24 throughout the Q14 domain. Publish signed32.
.macro pose_pair center,span,dest
 ld hl,#span
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld e,(hl)
 ld hl,#dest
 ldh a,(#center)
 sub a,c
 ld (hl+),a
 ldh a,(#center+1)
 sbc a,b
 ld (hl+),a
 ldh a,(#center+2)
 sbc a,e
 ld (hl+),a
 rla
 sbc a,a
 ld (hl+),a
 ldh a,(#center)
 add a,c
 ld (hl+),a
 ldh a,(#center+1)
 adc a,b
 ld (hl+),a
 ldh a,(#center+2)
 adc a,e
 ld (hl+),a
 rla
 sbc a,a
 ld (hl),a
.endm
 pose_pair pose_sin_ay,pose_cos_ax,_riding_pose_anchor
 pose_pair pose_neg_cos_ay,pose_sin_ax,_riding_pose_anchor+8
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
 ld d,#0
 sla e
 rl d
 ld a,(hl+)
 add a,e
 ld c,a
 ld a,(hl+)
 adc a,d
 ld b,a
 sla e
 rl d
 sla e
 rl d
 ld a,(hl+)
 add a,e
 ld e,a
 ld a,(hl+)
 adc a,d
 ld d,a
 ; BC and DE point at the head and suspension residuals. HL now
 ; points at the signed bases, in the order they are consumed.
.endm

.macro pose_head dest
 ld a,(bc)
 inc bc
 add a,(hl)
 inc hl
 ldh (#dest),a
 ld a,(hl+)
 adc a,#0
 ldh (#dest+1),a
.endm

.macro pose_anchor dest
 ld a,(de)
 inc de
 add a,(hl)
 inc hl
 ldh (#dest),a
 ld a,(de)
 inc de
 adc a,(hl)
 inc hl
 ldh (#dest+1),a
 ld a,(hl+)
 adc a,#0
 ldh (#dest+2),a
.endm

.macro pose_scale pages,head,rest,ax,ay,sine
 ld bc,#pages
 pose_rows
 pose_head head
 pose_head head+2
 .if sine
 inc de
 .endif
 ld a,(de)
 inc de
 add a,(hl)
 inc hl
 ld (#rest),a
 ld a,(hl+)
 adc a,#0
 ld (#rest+1),a
 .ifeq sine
 inc de
 .endif
 pose_anchor ax
 .ifeq sine
 inc de
 inc de
 .endif
 pose_anchor ay
 ret
.endm
pose_cos_scale:
 pose_scale _riding_pose_cos_pages,_riding_pose_cosine,_riding_pose_rest+2,pose_cos_ax,pose_neg_cos_ay,0
pose_sin_scale:
 pose_scale _riding_pose_sin_pages,_riding_pose_sine,_riding_pose_rest,pose_sin_ax,pose_sin_ay,1
