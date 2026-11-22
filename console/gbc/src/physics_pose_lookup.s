; Exact Q14 phase geometry, shared by the head, rider and suspension.
.module physics_pose_lookup
.area _DATA
pose_cos_ax: .ds 3
pose_neg_cos_ay: .ds 3
pose_sin_ax: .ds 3
pose_sin_ay: .ds 3

.area _CODE_1
b_riding_refresh_geometry = 1
.globl b_riding_refresh_geometry
_riding_refresh_geometry::
 ld hl,#_riding_pose_phase
 ld a,(hl+)
 ld e,a
 ld a,(hl)
 ld d,a
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
 bit 1,c
 push af
 call pose_read_pair
 pop af
 jr z,pose_trig_ready           ; forward sine, reflected cosine
 ld a,e
 ld e,c
 ld c,a
 ld a,d
 ld d,b
 ld b,a
 jr pose_trig_ready
pose_octant_endpoint:
 ; Eight phases can reach a quarter-wave endpoint outside the table.
 ; Keep the same canonical fixed-point endpoint handling as fsin.
 push de
 call _riding_sin16
 ld b,d
 ld c,e
 pop de
 ld a,d
 add a,#64
 ld d,a
 push bc
 push de
 call _riding_sin16
 add sp,#2
 pop bc
pose_trig_ready:
 push bc                        ; sine; cosine in DE
 ld hl,#_riding_pose_trig
 ld a,(hl+)
 cp e
 jr nz,pose_cos_changed
 ld a,(hl)
 cp d
 jr z,pose_get_sine
pose_cos_changed:
 ld (hl),d
 dec hl
 ld (hl),e
 call pose_cos_scale
pose_get_sine:
 pop de
 ld hl,#_riding_pose_trig+2
 ld a,(hl+)
 cp e
 jr nz,pose_sin_changed
 ld a,(hl)
 cp d
 jr z,pose_anchors
pose_sin_changed:
 ld (hl),d
 dec hl
 ld (hl),e
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
 ld hl,#center
 ld a,(hl+)
 sub a,c
 ld (#dest),a
 ld a,(hl+)
 sbc a,b
 ld (#dest+1),a
 ld a,(hl)
 sbc a,e
 ld (#dest+2),a
 rla
 sbc a,a
 ld (#dest+3),a
 ld hl,#center
 ld a,(hl+)
 add a,c
 ld (#dest+4),a
 ld a,(hl+)
 adc a,b
 ld (#dest+5),a
 ld a,(hl)
 adc a,e
 ld (#dest+6),a
 rla
 sbc a,a
 ld (#dest+7),a
.endm
pose_anchors:
 pose_pair pose_sin_ay,pose_cos_ax,_riding_pose_anchor
 pose_pair pose_neg_cos_ay,pose_sin_ax,_riding_pose_anchor+8
 ret

; Each octant reads one forward and one reflected quarter wave. The
; negative interpolation table has its own downward rounding.
pose_octant_banks:
 .db 16,17, 17,16, 18,17, 19,16, 18,19, 19,18, 16,19, 17,18

; DE is the signed trig input. Its high byte selects a sixteen-byte page
; with two row pointers and signed bases. The low byte indexes both rows.
pose_rows:
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
 ld c,a
 ld a,(hl+)
 ld b,a
 push hl
 ld d,#0
 ld h,d
 ld l,e
 add hl,hl
 add hl,bc
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 pop hl
 push bc
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 push hl
 ld h,d
 ld l,e
 add hl,hl
 add hl,hl
 add hl,hl
 add hl,bc
 ld d,h
 ld e,l
 pop hl
 pop bc
 ; HL signed page bases, DE suspension row, BC head row (Y:X).
 ret

.macro pose_head delta,dest
 ld a,(hl+)
 add a,delta
 ld (#dest),a
 ld a,(hl+)
 adc a,#0
 ld (#dest+1),a
.endm

.macro pose_anchor dest
 ld a,(de)
 inc de
 add a,(hl)
 inc hl
 ld (#dest),a
 ld a,(de)
 inc de
 adc a,(hl)
 inc hl
 ld (#dest+1),a
 ld a,(hl+)
 adc a,#0
 ld (#dest+2),a
.endm

.macro pose_scale pages,head,rest,ax,ay,sine
 ld bc,#pages
 call pose_rows
 pose_head c,head
 pose_head b,head+2
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

.area _CODE
; HL is the forward even address, D/E the physical sine banks. Restore
; bank 1 once after both reads. BC receives forward, DE receives reflected.
pose_read_pair:
 ld a,d
 ld (#0x2000),a
 ld c,(hl)
 inc l
 ld b,(hl)
 dec l
 ld a,e
 ld (#0x2000),a
 xor a
 sub a,l
 ld l,a
 ld a,#0xc0
 sbc a,h
 ld h,a                         ; reflected address = $c000 - forward
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ld a,#1
 ld (#0x2000),a
 ret
