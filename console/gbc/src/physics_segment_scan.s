; Exact inclusive unsigned box iterator over packed18 seg_t records.
; Near bank9, stack ABI0: bx@SP+2, by@SP+3, result pointer in DE.
; Only Seg_cur/Seg_left are written; no bank/IRQ changes or shared scratch.
; Empty input preserves Seg_cur. Every consumed record advances it by18,
; including rejected records and the last record of an exhausted query.
.module physics_segment_scan
.area _CODE_9
_riding_segment_box::
 ld a,(#_Seg_left)
 or a,a
 jr z,segment_empty
 ld d,a
 ldhl sp,#2
 ld b,(hl)
 inc hl
 ld c,(hl)
 ld hl,#_Seg_cur
 ld a,(hl+)
 ld h,(hl)
 ld l,a
segment_scan:
 ; HL starts at the record. The four box bytes are at14..17.
 ld a,l
 add a,#14
 ld l,a
 jr nc,segment_box
 inc h
segment_box:
 dec d
 ld a,b
 cp a,(hl)
 inc hl
 jr c,segment_reject_x0
 ld a,(hl+)
 cp a,b
 jr c,segment_reject_x1
 ld a,c
 cp a,(hl)
 inc hl
 jr c,segment_reject_y0
 ld a,(hl+)
 cp a,c
 jr nc,segment_found
 jr segment_rejected
segment_reject_x0:
 inc hl
segment_reject_x1:
 inc hl
segment_reject_y0:
 inc hl
segment_rejected:
 ; All rejection paths now point to the following record.
 ld a,d
 or a,a
 jr nz,segment_scan
 ld a,l
 ld (#_Seg_cur),a
 ld a,h
 ld (#_Seg_cur+1),a
 xor a,a
 ld (#_Seg_left),a
segment_empty:
 ld de,#0
 ret
segment_found:
 ld a,d
 ld (#_Seg_left),a
 ld a,l
 ld (#_Seg_cur),a
 ld a,h
 ld (#_Seg_cur+1),a
 ; Return the accepted record, leaving the cursor at the following one.
 ld a,l
 sub a,#18
 ld e,a
 ld a,h
 sbc a,#0
 ld d,a
 ret
