; Exact normalize(dx,dy,d2,contact*) table branch. Near bank9, stack ABI0.
; Original 10-byte contact has nx0,ny2,length4; tx6/ty8 are untouched.
.module physics_normal_fast
; One-entry exact normalization cache, including the full supplied d2 key.
; Only the six normalized output bytes are stored; contact tx/ty stay intact.
; The pure result is valid across level/reset/gravity changes.
; Mainline-only helper: IRQ handlers do not normalize contacts.
.area _DATA
normal_cache_valid: .ds 1
normal_cache_key: .ds 8
normal_cache_value: .ds 6
 .ifdef RIDING_NORMAL_ATLAS
 .globl normal_cache_key,normal_cache_value,normal_cache_valid
 .endif
.area _CODE_9
 .ifdef RIDING_NORMAL_ATLAS
.area _DATA
normal_length_tag:: .ds 1   ; consumed only by the immediate endpoint caller
normal_physical: .ds 1      ; the caller formed d2 from these exact coordinates
.area _CODE_9
_riding_normal_physical::
 ld a,#1
 jr normal_source
_riding_normal_fast::
 xor a
normal_source:
 ld (#normal_physical),a
 .else
_riding_normal_fast::
 .endif
 ld a,(#normal_cache_valid)
 or a
 jr z,normal_cache_miss
 ldhl sp,#2
 ld de,#normal_cache_key
 .rept 8
 ld a,(de)
 cp (hl)
 jr nz,normal_cache_miss
 inc de
 inc hl
 .endm
normal_cached_destination:
 ldhl sp,#10
 ld a,(hl+)
 ld d,(hl)
 ld e,a
normal_cache_copy:
 ld hl,#normal_cache_value
 .rept 6
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 .ifdef RIDING_NORMAL_ATLAS
 ld a,#1
 or a                        ; a cached hit is inside the wheel radius
 .endif
 ret
normal_cache_miss:
 ldhl sp,#2
 ld de,#normal_cache_key
 .rept 8
 ld a,(hl+)
 ld (de),a
 inc de
 .endm
 ; Table misses retain the caller's original ABI0 stack.
 ldhl sp,#9
 bit 7,(hl)
 jp nz,normal_cache_deep
 ld a,(hl-)
 or (hl)
 jr nz,normal_table
 dec hl
 ld a,(hl)
 cp #64
 jp c,normal_cache_deep
normal_table:
 ; uint16((d2-16384)>>9), including its original uint16 wrapping.
 ldhl sp,#7
 ld a,(hl+)
 and #254
 sub #64
 ld e,a
 ld a,(hl+)
 sbc a,#0
 ld d,a
 ld a,(hl)
 sbc a,#0
 rrca                     ; bit 16 of the doubled index
 jr c,normal_last
 ld a,d
 cp #2
 jr c,normal_index_ready
 jr nz,normal_last
 ld a,e
 cp #81
 jr c,normal_index_ready
normal_last:
 ld de,#592
normal_index_ready:
 ld hl,#_riding_normal_rsqrt
 add hl,de
 ld c,(hl)
 inc hl
 ld b,(hl)
 push bc
 ldhl sp,#4
 ld e,(hl)
 inc hl
 ld d,(hl)
 .ifdef RIDING_NORMAL_ATLAS
 call normal_scaled_axis
 .else
 call _riding_mul16_regs
 call normal_scale4
 .endif
 ld hl,#normal_cache_value
 ld (hl),e
 inc hl
 ld (hl),d
 ldhl sp,#0
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#6
 ld e,(hl)
 inc hl
 ld d,(hl)
 .ifdef RIDING_NORMAL_ATLAS
 call normal_scaled_axis
 .else
 call _riding_mul16_regs
 call normal_scale4
 .endif
 ld hl,#(normal_cache_value+2)
 ld (hl),e
 inc hl
 ld (hl),d
 .ifdef RIDING_NORMAL_ATLAS
 ld a,(#normal_physical)
 or a
 jr z,normal_dot_length
 call normal_physical_length
 jr c,normal_have_length
normal_dot_length:
 .endif
 ; Place the small wheel offsets in the multiplier's coordinate registers.
 ; Stack coefficients are callee-cleaned. The sum is rounded once as before.
 ld hl,#normal_cache_value
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 push bc
 push de
 ldhl sp,#8
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 call _dotq14
normal_have_length:
 ld hl,#(normal_cache_value+4)
 ld (hl),c
 inc hl
 ld (hl),b
 add sp,#2
 ld a,#1
 ld (#normal_cache_valid),a
 jp normal_cached_destination

 .ifdef RIDING_NORMAL_ATLAS
; A wheel offset in [-512,511] is its low byte plus -2,-1,0 or 1
; times 256. The reciprocal is positive. Keep the full product until
; the ordinary signed saturation, including for arbitrary d2 inputs.
normal_scaled_axis:
 ld a,d
 add #2
 cp #4
 jr nc,normal_wide_axis
 push af
 ld a,e
 ld d,b
 ld e,c
 ld c,a
 push de
 call _riding_unsigned_byte_product
 pop bc
 pop af
 cp #2
 jr z,normal_scale4
 jr nc,normal_plus_high
 or a
 jr nz,normal_minus_high
 sla c
 rl b
normal_minus_high:
 ld a,d
 sub c
 ld d,a
 ld a,l
 sbc b
 ld l,a
 sbc a
 ld h,a
 jr normal_scale4
normal_plus_high:
 ld a,d
 add c
 ld d,a
 ld a,l
 adc b
 ld l,a
 jr normal_scale4
normal_wide_axis:
 call _riding_projection_signed16
 jr normal_scale4
 .endif

; sat16(signed32 HLDE>>4). Fits exactly iff signed highword is[-8,7].
normal_scale4:
 ld a,l
 add a,#8
 ld b,a
 ld a,h
 adc a,#0
 jr nz,normal_saturated
 ld a,b
 cp #16
 jr nc,normal_saturated
 ; Join adjacent nibbles before swapping: E receives bits 4..11,
 ; D bits 12..19. The range check above already handled saturation.
 ld a,e
 xor d
 and #0xf0
 xor d
 swap a
 ld e,a
 ld a,d
 xor l
 and #0xf0
 xor l
 swap a
 ld d,a
 ret
normal_saturated:
 bit 7,h
 jr nz,normal_negative
 ld de,#32767
 ret
normal_negative:
 ld de,#0x8000
 ret

normal_cache_deep:
 .ifdef RIDING_NORMAL_ATLAS
 ld e,#33
 ld hl,#normal_fraction
 call ___sdcc_bcall_ehl
 or a
 jp nz,normal_cached_destination
 ; Only arbitrary inputs outside the narrow domain need the general divide.
 ld c,#5
normal_deep_argument:
 ldhl sp,#10
 ld e,(hl)
 inc hl
 ld d,(hl)
 push de
 dec c
 jr nz,normal_deep_argument
 .else
 ; Copy five words right-to-left, retaining the caller's ABI0 arguments.
 .rept 5
 ldhl sp,#10
 ld e,(hl)
 inc hl
 ld d,(hl)
 push de
 .endm
 .endif
 call _riding_normalize_deep
 add sp,#10
normal_cache_store_result:
 ldhl sp,#10
 ld a,(hl+)
 ld d,(hl)
 ld e,a
 ld hl,#normal_cache_value
 .rept 6
 ld a,(de)
 inc de
 ld (hl+),a
 .endm
 ld a,#1
 ld (#normal_cache_valid),a
 ret

 .ifdef RIDING_NORMAL_ATLAS
.area _CODE_9
; Physical squared lengths select a conservative slot at the matching depth.
; A zero return requests the full normalized-vector dot.
normal_physical_length:
 ld a,(#normal_cache_key+7)
 or a
 ret nz
 ld a,(#normal_cache_key+6)
 or a
 jr z,normal_inner_range
 dec a
 jr z,normal_low_range
 dec a
 jr nz,normal_length_miss
 ld a,(#normal_cache_key+5)
 cp #146                 ; 73 reciprocal bins above 131072
 jr nc,normal_length_miss
 ld hl,#normal_read_upper
 jr normal_read
normal_low_range:
 ld hl,#normal_read_lower
normal_read:
 ld e,#5
normal_length_lookup:
 call ___sdcc_bcall_ehl
 ld a,c
 or a
 ret z
 add #160
 ld c,a
 ld a,#0
 adc #0
 ld b,a
 scf
 ret
normal_inner_range:
 ld a,(#normal_cache_key+5)
 cp #128
 jr c,normal_length_miss
 ld e,#93
 ld hl,#normal_read_inner
 jr normal_length_lookup
normal_length_miss:
 or a
 ret
 .endif
