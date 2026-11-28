.module haircut_gate
.area _CODE_13
; Enter the fine terrain reader only for a repeated, unresolved 256u square.
; The ordinary per-wheel cache handles new squares and cheap plane hits.
.globl _haircut_wheel_inputs
_haircut_wheel_inputs = 0xaca0
haircut_prepare_gate::
 ld a,#10
 ld (#0),a
 xor a
 ld (#0x4000),a
 ld hl,#haircut_gate_image
 ld de,#_haircut_wheel_inputs
 ld b,#(haircut_gate_end-haircut_gate_image)
haircut_copy_gate:
 ld a,(hl+)
 ld (de),a
 inc de
 dec b
 jr nz,haircut_copy_gate
 ret
haircut_gate_image::
 push hl
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 ld hl,#6
 add hl,bc
 ld a,(hl)
 sub #100
 cp #8
 jr nc,haircut_fallback
 ld de,#_wheel_surface_cache
 ld a,c
 cp #<(_Bike+24)
 jr z,haircut_cache
 ld de,#(_wheel_surface_cache+29)
haircut_cache:
 ld a,(de)
 ld hl,#2
 add hl,bc
 cp (hl)
 jr nz,haircut_fallback
 inc de
 inc de
 ld a,(de)
 inc hl
 inc hl
 inc hl
 inc hl
 cp (hl)
 jr nz,haircut_fallback
 inc de
 inc de
 ld a,(de)
 cp #4
 jr c,haircut_fallback
 sub #9
 cp #3
 jr c,haircut_fallback
 push bc
 ld hl,#_haircut_query
 ld e,#29
 call ___sdcc_bcall_ehl
 cp #255
 jp nz,_riding_patch_have_answer
 pop bc
haircut_fallback:
 ld hl,#6
 add hl,bc
 ld a,(#_patch_sparse_y0)
 cp (hl)
 pop hl
 jp z,_riding_sparse_wheel_inputs
 jp _riding_wheel_inputs
haircut_gate_end::
.ifgt haircut_gate_end-haircut_gate_image-0x60
 .error 1
.endif
