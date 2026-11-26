; Exact rider acceleration orchestration in bank8, stack ABI0.
; restx16,resty16,Oms32,gx32,gy32. Existing vector/math/move kernels
; retain their signed narrowing, rounded products and wrapping32 updates.
; The vectors use eight stack bytes. Each acceleration goes straight to motion.
.module physics_rider_response
.area _CODE_8
_riding_rider_response32::
 add sp,#-8
 ldhl sp,#0
 push hl
 ldhl sp,#14
 ld e,(hl)
 inc hl
 ld d,(hl)
 push de
 ldhl sp,#14
 ld e,(hl)
 inc hl
 ld d,(hl)
 push de
 call _riding_rider_vectors32
 add sp,#6
; The spring displacement always fits signed16. If relative velocity
; also fits, compute the independently rounded spring and damper products
; in one bank visit. Wider velocities retain the full Q24 damper.
.macro rider_response_axis tangent,invert,body_velocity,rider_velocity,direction,gravity,wide,combine
 ldhl sp,#tangent
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 .if invert
 xor a
 sub c
 ld c,a
 ld a,#0
 sbc b
 ld b,a
 .endif
 ldhl sp,#14
 call _riding_mulq14_regs
 ld b,h
 ld c,l
 ld hl,#(_Bike+body_velocity)
 ld a,(hl+)
 add a,e
 ld e,a
 ld a,(hl+)
 adc a,d
 ld d,a
 ld a,(hl+)
 adc a,c
 ld c,a
 ld a,(hl)
 adc a,b
 ld b,a
 ld hl,#(_Bike+rider_velocity)
 ld a,(hl+)
 sub a,e
 ld e,a
 ld a,(hl+)
 sbc a,d
 ld d,a
 ld a,(hl+)
 sbc a,c
 ld c,a
 ld a,(hl)
 sbc a,b
 ld b,a
 ld a,d
 add a,a
 sbc a,a
 cp a,c
 jr nz,wide
 cp a,b
 jr nz,wide
 ldhl sp,#direction
 call _riding_rider_pair16
 jr combine
wide:
 push bc
 push de
 call _riding_rider_f_wide
 add sp,#4
 push hl
 push de
 ldhl sp,#(direction+4)
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ld a,d
 add a,a
 sbc a,a
 ld h,a
 ld l,a
 push hl
 push de
 call _riding_rider_s
 add sp,#4
 ld b,h
 ld c,l
 ldhl sp,#0
 ld a,e
 sub a,(hl)
 ld e,a
 inc hl
 ld a,d
 sbc a,(hl)
 ld d,a
 inc hl
 ld a,c
 sbc a,(hl)
 ld c,a
 inc hl
 ld a,b
 sbc a,(hl)
 ld h,a
 ld l,c
 add sp,#4
combine:
 ld b,h
 ld c,l
 ldhl sp,#gravity
 ld a,(hl+)
 add a,e
 ld e,a
 ld a,(hl+)
 adc a,d
 ld d,a
 ld a,(hl+)
 adc a,c
 ld c,e
 ld e,a
 ld a,(hl)
 adc a,b
 ld b,d
 ld d,a
.endm

 ; The y response uses the saved dx and the original y velocity. Advancing
 ; x here keeps both its velocity and its independent residual in order.
 rider_response_axis 6,1,8,80,0,18,rider_wide_x,rider_combine_x
 call _riding_rider_move_x_regs
 rider_response_axis 4,0,12,84,2,22,rider_wide_y,rider_combine_y
 add sp,#8
 jp _riding_rider_move_y_regs

; The private caller passes the xy output pointer in DE (SDCC ABI1).
; The phase and Q14 pair come from the same cached pose. Each phase byte
; selects one of 32 symmetric sets of world-space strips. A certified
; strip can return without either rounded dot or the later constraints.
; The original wrapped, saturated deltas remain on the stack for every miss.
.macro rider_delta rider,body,done
 ld hl,#_Bike+body
 ld a,(#_Bike+rider)
 sub a,(hl)
 inc hl
 ld a,(#_Bike+rider+1)
 sbc a,(hl)
 ld e,a
 inc hl
 ld a,(#_Bike+rider+2)
 sbc a,(hl)
 ld d,a
 inc hl
 ld a,(#_Bike+rider+3)
 sbc a,(hl)
 ld c,a
 ld a,d
 add a,a
 sbc a,a
 cp c
 jr z,done
 ld de,#0x7fff
 bit 7,c
 jr z,done
 inc de
done:
 push de
.endm

.macro rider_neg_u
 xor a
 sub a,c
 ld c,a
 sbc a,a
 sub a,b
 ld b,a
.endm
.macro rider_neg_v
 xor a
 sub a,e
 ld e,a
 sbc a,a
 sub a,d
 ld d,a
.endm
.macro rider_swap_uv
 ld h,b
 ld l,c
 ld b,d
 ld c,e
 ld d,h
 ld e,l
.endm

_riding_rider_phase_local::
 push de
 rider_delta 72,0,rider_saved_x
 rider_delta 76,4,rider_saved_y
 ldhl sp,#2
 ld a,(hl+)
 ld b,(hl)
 ld c,a
 ld a,(#_riding_pose_phase+1)
 or a,a
 jr nz,rider_axes
 ld hl,#rider_strip_0
 jr rider_strip_check

rider_axes:
 ; Rotate to the closest cardinal direction, then reflect transverse
 ; displacement for the negative half of that octant. Signed -32768
 ; wraps on a reflection, but either representation lies outside the grid.
 bit 7,a
 jr nz,rider_axes_4_to_7
 bit 6,a
 jr nz,rider_axes_2_or_3
 bit 5,a
 jr z,rider_strip_lookup
 ; Octant 1 = (-dy,-dx).
 rider_swap_uv
 rider_neg_u
 jr rider_flip_v
rider_axes_2_or_3:
 bit 5,a
 jr nz,rider_flip_v
 ; Octant 2 = (dy,-dx), octant 3 = (dx,-dy).
 rider_swap_uv
rider_flip_v:
 rider_neg_v
 jr rider_strip_lookup
rider_axes_4_to_7:
 bit 6,a
 jr nz,rider_axes_6_or_7
 bit 5,a
 jr z,rider_axes_4
 ; Octant 5 = (dy,dx), octant 4 = (-dx,-dy).
 rider_swap_uv
 jr rider_strip_lookup
rider_axes_4:
 rider_neg_u
 jr rider_flip_v
rider_axes_6_or_7:
 bit 5,a
 jr nz,rider_flip_u
 ; Octant 6 = (-dy,dx), octant 7 = (-dx,dy).
 rider_swap_uv
rider_flip_u:
 rider_neg_u
rider_strip_lookup:
 ld a,(#_riding_pose_phase+1)
 bit 5,a
 jr z,rider_strip_index
 cpl
rider_strip_index:
 and #31
 add a,a
 add a,#<rider_strip_directory
 ld l,a
 ld a,#>rider_strip_directory
 adc a,#0
 ld h,a
 ld a,(hl+)
 ld h,(hl)
 ld l,a

rider_strip_check:
 ; E = v/2; a valid vertical displacement is in [0,511].
 ld a,d
 srl a
 jr nz,rider_project
 ld a,e
 rra
 ld e,a
 ; A = (u+512)/16, valid for u in [-512,511].
 ld a,b
 add a,#2
 cp #4
 jr nc,rider_project
 xor a,c
 and #15
 xor a,c
 swap a
 sub a,(hl)
 inc hl
 cp (hl)
 jr nc,rider_project
 inc hl
 add a,a
 add a,l
 ld l,a
 jr nc,rider_strip_cell
 inc h
rider_strip_cell:
 ld a,e
 cp (hl)
 jr c,rider_project
 inc hl
 ld a,(hl)
 cp e
 jr c,rider_project
 ld a,#1
 add sp,#6
 ret

rider_project:
 ; On exact quarter turns the dots are just a swap and saturated signs.
 ld a,(#_riding_pose_phase)
 or a,a
 jr nz,rider_project_dots
 ld a,(#_riding_pose_phase+1)
 ld l,a
 and #63
 jr nz,rider_project_dots
 pop de
 pop bc
 bit 6,l
 jr z,rider_project_even
 bit 7,l
 rider_swap_uv
 jr nz,rider_project_neg_x
 call rider_neg_v_sat
 jr rider_project_store
rider_project_even:
 bit 7,l
 jr z,rider_project_store
 call rider_neg_v_sat
rider_project_neg_x:
 ld a,b
 xor #0x80
 or c
 jr nz,rider_project_flip_x
 ld bc,#0x7fff
 jr rider_project_store
rider_project_flip_x:
 rider_neg_u
rider_project_store:
 pop hl
 ld (hl),c
 inc hl
 ld (hl),b
 inc hl
 ld (hl),e
 inc hl
 ld (hl),d
 xor a
 ret

rider_neg_v_sat:
 ld a,d
 xor #0x80
 or e
 jr nz,rider_project_flip_y
 ld de,#0x7fff
 ret
rider_project_flip_y:
 rider_neg_v
 ret

rider_project_dots:
 ld hl,#_riding_pose_trig+2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 ld hl,#_riding_pose_trig
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 ldhl sp,#4
 ld a,(hl+)
 ld c,a
 ld a,(hl+)
 ld b,a
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 call _dotq14
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld (hl),c
 inc hl
 ld (hl),b
 ld hl,#_riding_pose_trig+2
 xor a
 sub a,(hl)
 ld e,a
 inc hl
 sbc a,a
 sub a,(hl)
 ld d,a
 push de
 ld hl,#_riding_pose_trig
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 push hl
 ldhl sp,#4
 ld a,(hl+)
 ld e,a
 ld a,(hl+)
 ld d,a
 ld a,(hl+)
 ld c,a
 ld b,(hl)
 call _dotq14
 add sp,#4
 pop hl
 inc hl
 inc hl
 ld (hl),c
 inc hl
 ld (hl),b
 xor a
 ret

; Generated by tools/rider_clearance.py. Each row stores the first
; transverse bin, its count and inclusive vertical bins (two units each).
rider_strip_directory:
 .dw rider_strip_0,rider_strip_1,rider_strip_2,rider_strip_3,rider_strip_4,rider_strip_5,rider_strip_6,rider_strip_7
 .dw rider_strip_8,rider_strip_9,rider_strip_10,rider_strip_11,rider_strip_12,rider_strip_13,rider_strip_14,rider_strip_15
 .dw rider_strip_16,rider_strip_17,rider_strip_18,rider_strip_19,rider_strip_20,rider_strip_21,rider_strip_22,rider_strip_23
 .dw rider_strip_24,rider_strip_25,rider_strip_26,rider_strip_27,rider_strip_28,rider_strip_29,rider_strip_30,rider_strip_31
rider_strip_0:
 .db 22,19
 .db 189,194,185,204,181,213,177,221,173,228,169,233,166,237,162,240,158,243,155,245,156,244,161,242
 .db 164,239,169,235,172,231,176,225,181,218,184,210,189,201
rider_strip_1:
 .db 22,19
 .db 185,198,181,208,178,217,174,224,171,230,167,235,163,239,160,242,157,244,154,244,159,242,163,240
 .db 167,237,171,232,175,228,180,221,184,214,188,206,192,196
rider_strip_2:
 .db 21,19
 .db 185,192,181,203,178,212,175,220,171,227,168,233,165,237,161,240,158,243,155,243,157,242,161,241
 .db 165,238,170,234,175,230,179,224,183,217,188,210,192,201
rider_strip_3:
 .db 20,20
 .db 184,184,181,196,178,207,175,216,171,223,168,229,166,234,162,238,159,241,156,243,154,242,158,241
 .db 163,239,169,236,173,232,178,227,182,221,188,213,192,206,197,197
rider_strip_4:
 .db 20,19
 .db 180,189,177,201,174,211,172,219,168,226,166,232,164,236,160,240,157,242,155,242,156,241,161,239
 .db 166,237,171,233,176,228,181,223,186,217,191,210,197,201
rider_strip_5:
 .db 19,19
 .db 179,180,176,194,174,205,171,215,169,222,166,229,164,233,161,237,158,240,156,241,153,241,158,239
 .db 163,237,169,234,174,230,180,225,185,220,190,213,196,206
rider_strip_6:
 .db 19,19
 .db 176,186,173,198,170,209,169,218,166,225,163,230,162,235,159,238,156,240,154,240,156,239,161,238
 .db 166,235,172,232,178,227,183,222,189,216,194,209,200,202
rider_strip_7:
 .db 18,19
 .db 174,177,172,191,170,204,168,213,165,221,163,227,161,232,158,236,157,239,155,239,152,239,158,237
 .db 163,235,169,233,175,229,181,224,187,219,193,212,199,205
rider_strip_8:
 .db 18,18
 .db 170,183,169,196,167,207,165,216,163,223,161,229,159,233,157,237,155,238,153,238,155,237,160,236
 .db 166,233,172,229,179,226,185,221,191,215,197,208
rider_strip_9:
 .db 17,19
 .db 169,171,167,188,166,200,164,211,161,219,160,225,158,230,157,234,155,236,153,237,151,236,157,235
 .db 163,233,170,230,176,227,182,223,189,218,195,211,202,205
rider_strip_10:
 .db 17,18
 .db 165,178,164,193,162,205,161,214,159,221,157,227,156,232,154,235,152,235,151,235,153,235,160,233
 .db 166,230,173,227,180,224,186,219,193,214,200,208
rider_strip_11:
 .db 16,18
 .db 164,166,162,184,161,198,159,208,157,217,156,223,155,228,154,232,152,234,151,234,149,233,155,233
 .db 162,230,170,228,177,224,183,220,191,216,198,211
rider_strip_12:
 .db 16,18
 .db 160,173,159,190,157,202,156,211,155,219,154,224,153,229,152,232,150,232,149,232,151,232,158,230
 .db 165,228,173,225,180,222,188,218,195,213,203,207
rider_strip_13:
 .db 15,18
 .db 158,158,156,180,156,194,154,205,153,214,152,221,151,226,150,229,150,230,149,231,147,231,153,229
 .db 161,227,169,225,177,222,184,218,192,214,200,209
rider_strip_14:
 .db 15,18
 .db 154,168,153,186,152,198,152,208,151,216,149,222,149,226,148,228,148,229,147,229,148,229,157,227
 .db 164,225,173,222,181,219,189,215,197,211,205,206
rider_strip_15:
 .db 14,18
 .db 151,151,150,174,150,191,149,201,148,211,148,218,148,222,147,225,146,227,146,228,145,227,151,226
 .db 159,224,168,222,177,220,185,216,194,212,202,207
rider_strip_16:
 .db 14,17
 .db 148,161,147,180,147,194,146,205,146,213,146,218,145,222,145,224,144,225,144,225,144,225,154,224
 .db 163,222,171,220,180,217,190,213,198,209
rider_strip_17:
 .db 14,17
 .db 144,169,144,186,144,198,143,207,143,214,143,219,143,221,143,223,143,223,142,224,148,223,157,221
 .db 167,219,176,217,186,213,195,210,205,206
rider_strip_18:
 .db 13,17
 .db 140,152,140,175,141,190,141,201,141,208,141,215,140,218,140,220,141,222,141,222,141,221,151,220
 .db 161,219,171,217,181,214,191,211,201,207
rider_strip_19:
 .db 13,16
 .db 137,161,137,180,138,193,138,203,138,210,138,214,138,217,138,218,138,219,139,220,144,219,155,218
 .db 165,216,175,214,186,211,196,208
rider_strip_20:
 .db 12,17
 .db 133,142,133,169,134,185,135,196,135,204,135,211,136,213,136,216,137,217,137,218,137,217,147,216
 .db 158,215,169,213,181,211,192,208,202,204
rider_strip_21:
 .db 12,16
 .db 129,152,130,174,130,188,132,198,132,205,133,210,134,212,134,214,134,215,135,215,140,215,151,214
 .db 162,212,174,210,186,208,197,204
rider_strip_22:
 .db 12,15
 .db 126,161,127,179,128,190,129,200,129,206,130,208,131,211,132,212,133,213,133,213,143,212,154,211
 .db 168,209,180,207,192,205
rider_strip_23:
 .db 11,16
 .db 122,142,123,168,124,182,125,193,126,200,127,205,128,207,129,209,130,210,131,211,133,211,147,210
 .db 160,208,173,206,185,205,198,202
rider_strip_24:
 .db 11,15
 .db 118,153,119,172,120,185,122,194,123,200,124,203,126,205,127,207,128,208,129,208,138,208,151,207
 .db 165,206,179,204,192,202
rider_strip_25:
 .db 10,15
 .db 113,119,114,160,116,176,118,187,119,195,120,199,122,201,123,204,124,205,126,206,127,206,142,206
 .db 156,205,171,203,185,201
rider_strip_26:
 .db 10,15
 .db 109,140,111,165,113,179,114,188,116,194,117,197,120,200,121,202,122,203,125,204,131,203,146,203
 .db 162,202,177,200,192,198
rider_strip_27:
 .db 10,14
 .db 105,149,108,169,110,180,111,188,113,192,115,196,117,198,119,200,121,201,122,201,135,201,151,200
 .db 168,199,184,197
rider_strip_28:
 .db 9,15
 .db 101,121,102,157,105,172,107,182,108,187,110,191,112,194,114,196,117,197,119,198,122,199,141,198
 .db 158,197,175,196,193,194
rider_strip_29:
 .db 9,14
 .db 96,139,99,161,101,173,103,181,106,186,108,189,110,192,113,194,114,195,117,196,127,196,147,195
 .db 165,195,184,193
rider_strip_30:
 .db 9,13
 .db 93,147,95,164,98,174,100,180,103,184,105,188,107,190,110,192,113,193,115,193,133,193,153,193
 .db 173,192
rider_strip_31:
 .db 8,14
 .db 94,118,89,151,92,165,95,174,97,179,100,183,103,186,105,188,108,189,111,190,117,191,139,191
 .db 161,190,183,189
