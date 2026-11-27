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
_riding_normal_fast::
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
 sub #64
 ld e,a
 ld a,(hl+)
 sbc a,#0
 ld d,a
 ld a,(hl)
 sbc a,#0
 rra
 rr d
 rr e
 ld a,d
 or a
 jr z,normal_index_ready
 cp #1
 jr nz,normal_last
 ld a,e
 cp #41
 jr c,normal_index_ready
normal_last:
 ld de,#296
normal_index_ready:
 ld h,d
 ld l,e
 add hl,hl
 ld bc,#_riding_normal_rsqrt
 add hl,bc
 ld c,(hl)
 inc hl
 ld b,(hl)
 push bc
 ldhl sp,#4
 ld e,(hl)
 inc hl
 ld d,(hl)
 .ifdef RIDING_NORMAL_ATLAS
 call _riding_projection_signed16
 .else
 call _riding_mul16_regs
 .endif
 call normal_scale4
 ldhl sp,#12
 ld a,(hl+)
 ld h,(hl)
 ld l,a
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
 call _riding_projection_signed16
 .else
 call _riding_mul16_regs
 .endif
 call normal_scale4
 ldhl sp,#12
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 inc hl
 inc hl
 ld (hl),e
 inc hl
 ld (hl),d
 ; Place the small wheel offsets in the multiplier's coordinate registers.
 ; Stack coefficients are callee-cleaned. The sum is rounded once as before.
 ldhl sp,#12
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
 ldhl sp,#8
 ld e,(hl)
 inc hl
 ld d,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld b,(hl)
 call _dotq14
 ldhl sp,#12
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 inc hl
 inc hl
 inc hl
 inc hl
 ld (hl),c
 inc hl
 ld (hl),b
 add sp,#2
 jp normal_cache_store_result

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
