; Read the physical squared distance from the bank-9 cache key. Overlapping
; thresholds use the signed dot product. Each successful row supplies its endpoint tag.
normal_band_read::
 ; This path already excluded signed and unsigned d2 below 16384. The
 ; complete high-byte check also covers merged physical offsets beyond the disk.
 ld hl,#normal_cache_key+4
 ld a,(hl+)
 ld e,a
 add a
 ld a,(hl+)
 rla
 ld c,a
 ld a,(hl+)
 rla
 jr c,normal_band_uncertain
 ld b,a
 ld a,(hl)
 or a
 jr nz,normal_band_uncertain
 ld a,c
 sub #<(168448/128)
 ld a,b
 sbc #>(168448/128)
 jr nc,normal_band_uncertain
 ld l,c
 ld h,b
 add hl,hl
 add hl,hl
 ld bc,#(normal_length_bands-4*(16384/128))
 add hl,bc
 ld a,e
 and #127
 cp (hl)
 inc hl
 jr c,normal_band_low
 cp (hl)
 jr c,normal_band_uncertain
 inc hl
 ld c,(hl)
 inc hl
 ld a,(hl)
 and #1
 ld b,a
 inc bc
 ld a,(hl)
 rrca
 jr normal_band_tag
normal_band_low:
 inc hl
 ld c,(hl)
 inc hl
 ld a,(hl)
 and #1
 ld b,a
 ld a,(hl)
normal_band_tag:
 and #66
 ld (#normal_length_tag),a
 scf
 jp normal_ring_restore
normal_band_uncertain:
 xor a
 jp normal_ring_restore
