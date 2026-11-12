; Exact cache acquisition. Near bank6, ABI0 id@SP+2 -> slotDE.
; Cached ids/refs and circular allocation match the C reference. No shared
; scratch RAM; external calls restore bank6 before this routine resumes.
.module world_acquire_fast
.area _CODE_6
_world_acquire_fast::
 ldhl sp,#2
 ld e,(hl)
 inc hl
 ld d,(hl)
 push de
 call _world_lookup_get
 add sp,#2
 ld a,d
 or a
 jr z,acquire_hit
 cp #1
 jr nz,acquire_miss
 ld a,e
 cp #188
 jr nc,acquire_miss
acquire_hit:
 ld h,d
 ld l,e
 add hl,hl
 ld bc,#_world_cache_references
 add hl,bc
 ld a,(hl+)
 ld b,a
 ld a,(hl)
 or b
 jr z,acquire_hit_zero
 dec hl
 inc (hl)
 ret nz
 inc hl
 inc (hl)
 ret
acquire_hit_zero:
 dec hl
 ld (hl),#1
 jp acquire_clear_free
acquire_miss:
 ld a,(#_world_cache_next)
 ld e,a
 ld a,(#_world_cache_next+1)
 ld d,a
 ld h,d
 ld l,e
 add hl,hl
 ld bc,#_world_cache_references
 add hl,bc
 ld a,(hl+)
 or (hl)
 jr z,acquire_direct_free
 ld hl,#_world_cache_free_bits
 push hl
 push de
 call _world_find_free
 add sp,#4
 ld a,d
 cp #255
 jr nz,acquire_chosen
 ld hl,#_world_cache_failures
 inc (hl)
 jr nz,acquire_failed
 inc hl
 inc (hl)
acquire_failed:
 ld de,#0
 ret
acquire_direct_free:
 call acquire_clear_free
acquire_chosen:
 push de
 ld h,d
 ld l,e
 inc hl
 ld a,h
 cp #1
 jr nz,acquire_next_ready
 ld a,l
 cp #188
 jr nz,acquire_next_ready
 ld hl,#0
acquire_next_ready:
 ld a,l
 ld (#_world_cache_next),a
 ld a,h
 ld (#_world_cache_next+1),a
 ld h,d
 ld l,e
 add hl,hl
 ld bc,#_world_cache_ids
 add hl,bc
 ld a,(hl+)
 ld e,a
 ld d,(hl)
 ld a,d
 and e
 inc a
 jr z,acquire_upload
 ld hl,#65535
 push hl
 push de
 call _world_lookup_set
 add sp,#4
acquire_upload:
 ldhl sp,#4
 ld c,(hl)
 inc hl
 ld b,(hl)
 push bc
 ldhl sp,#2
 ld e,(hl)
 inc hl
 ld d,(hl)
 push de
 call _world_cache_upload
 add sp,#4
 ; Retain id while constructing the cached-id destination pointer.
 ldhl sp,#4
 ld c,(hl)
 inc hl
 ld b,(hl)
 ldhl sp,#0
 ld e,(hl)
 inc hl
 ld d,(hl)
 push bc
 ld h,d
 ld l,e
 add hl,hl
 ld bc,#_world_cache_ids
 add hl,bc
 pop bc
 ld (hl),c
 inc hl
 ld (hl),b
 ld h,d
 ld l,e
 add hl,hl
 ld bc,#_world_cache_references
 add hl,bc
 ld (hl),#1
 inc hl
 ld (hl),#0
 push de
 ldhl sp,#6
 ld c,(hl)
 inc hl
 ld b,(hl)
 push bc
 call _world_lookup_set
 add sp,#4
 pop de
 ret

; Clear this slot's free bit and preserve its DE index.
acquire_clear_free:
 push de
 ld a,e
 and #7
 ld c,a
 ld b,#0
 ld hl,#acquire_clear_masks
 add hl,bc
 ld b,(hl)
 ld h,d
 ld l,e
 srl h
 rr l
 srl h
 rr l
 srl h
 rr l
 ld de,#_world_cache_free_bits
 add hl,de
 ld a,(hl)
 and b
 ld (hl),a
 pop de
 ret
acquire_clear_masks:
 .db 254,253,251,247,239,223,191,127
