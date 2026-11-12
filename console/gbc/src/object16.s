; Two8x16 sprite columns reproduce one16x16 original object.
; ABI0 sprite@2,x@3,y@4,tile@5,prop@6. Tile bit0 selects right-column
; priority first; the physical tile indices remain even. This alternates
; which half wins when the hardware10-object scanline limit is reached.
.module gbc_object16
.area _CODE
_gbc_video_object16::
 ldhl sp,#2
 ld a,(hl+)
 add a,a
 add a,a
 ld e,a
 ld b,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld a,(hl+)
 ld d,(hl)
 push af
 ld hl,#_shadow_OAM
 ld a,l
 add a,e
 ld l,a
 jr nc,010$
 inc h
010$:
 pop af
 bit 0,a
 jr nz,100$
 and a,#0xfe
 ld e,a
 call 200$
 ld a,b
 add a,#8
 ld b,a
 inc e
 inc e
 jp 200$
100$:
 and a,#0xfe
 add a,#2
 ld e,a
 ld a,b
 add a,#8
 ld b,a
 call 200$
 ld a,b
 sub a,#8
 ld b,a
 dec e
 dec e
200$:
 ld (hl),c
 inc hl
 ld (hl),b
 inc hl
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 ret
