; Tile/attribute strip copy to the 32x32 map at 9800, wrapping each axis.
; ABI0: x@SP+2,y@3,vertical@4,count@5,data@6. Main-loop use only: enters
; with interrupts enabled. Mask interrupts during the short VRAM transaction
; so a STAT check and its write cannot be separated by a VBlank handler.
.module gbc_video
.area _CODE
_gbc_video_strip::
 ldhl sp,#2
 ld a,(hl+)
 and a,#31
 ld c,a
 ld a,(hl+)
 and a,#31
 ld e,a
 ld d,#0
 sla e
 rl d
 sla e
 rl d
 sla e
 rl d
 sla e
 rl d
 sla e
 rl d
 ld a,d
 or a,#0x98
 ld d,a
 ld a,e
 or a,c
 ld e,a
 ld a,(hl+)
 push af
 ld b,(hl)
 inc hl
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 pop af
 or a,a
 jr nz,200$
 di
100$:
 ld a,(hl+)
 ld c,a
110$:
 ldh a,(#0x41)
 and a,#2
 jr nz,110$
 ld a,c
 ld (de),a
 inc e
 ld a,e
 and a,#31
 jr nz,120$
 ld a,e
 sub a,#32
 ld e,a
120$:
 dec b
 jr nz,100$
 ei
 ret
200$:
 di
210$:
 ld a,(hl+)
 ld c,a
220$:
 ldh a,(#0x41)
 and a,#2
 jr nz,220$
 ld a,c
 ld (de),a
 ld a,e
 add a,#32
 ld e,a
 jr nc,230$
 inc d
 res 2,d
230$:
 dec b
 jr nz,210$
 ei
 ret

; Copy count bytes from one ROM chunk to contiguous RAM, source stride1/32.
; ABI0 source@SP+2,dest@4,count@6,stride@7. ROM bank is selected by caller.
_gbc_video_gather::
 ldhl sp,#6
 ld b,(hl)
 inc hl
 ld c,(hl)
 ldhl sp,#4
 ld e,(hl)
 inc hl
 ld d,(hl)
 ldhl sp,#2
 ld a,(hl+)
 ld h,(hl)
 ld l,a
300$:
 ld a,(hl)
 ld (de),a
 inc de
 ld a,l
 add a,c
 ld l,a
 jr nc,310$
 inc h
310$:
 dec b
 jr nz,300$
 ret

; Interior 4x4 body: preserve pattern/properties and write only shadow X/Y.
; ABI0 x@SP+2,y@3,mask@4. Hidden mask entries retain their normal X.
_gbc_video_body::
 ldhl sp,#2
 ld d,(hl)
 inc hl
 ld e,(hl)
 inc hl
 ld b,(hl)
 inc hl
 ld c,(hl)
 ld hl,#_shadow_OAM
 srl c
 rr b
 ld a,#0
 jr nc,400$
 ld a,e
400$:
 ld (hl+),a
 ld (hl),d
 inc hl
 inc hl
 inc hl
 ld a,d
 add a,#8
 ld d,a
 srl c
 rr b
 ld a,#0
 jr nc,401$
 ld a,e
401$:
 ld (hl+),a
 ld (hl),d
 inc hl
 inc hl
 inc hl
 ld a,d
 add a,#8
 ld d,a
 srl c
 rr b
 ld a,#0
 jr nc,402$
 ld a,e
402$:
 ld (hl+),a
 ld (hl),d
 inc hl
 inc hl
 inc hl
 ld a,d
 add a,#8
 ld d,a
 srl c
 rr b
 ld a,#0
 jr nc,403$
 ld a,e
403$:
 ld (hl+),a
 ld (hl),d
 inc hl
 inc hl
 inc hl
 ld a,d
 add a,#8
 ld d,a
 ld a,d
 sub a,#32
 ld d,a
 ld a,e
 add a,#8
 ld e,a
 srl c
 rr b
 ld a,#0
 jr nc,404$
 ld a,e
404$:
 ld (hl+),a
 ld (hl),d
 inc hl
 inc hl
 inc hl
 ld a,d
 add a,#8
 ld d,a
 srl c
 rr b
 ld a,#0
 jr nc,405$
 ld a,e
405$:
 ld (hl+),a
 ld (hl),d
 inc hl
 inc hl
 inc hl
 ld a,d
 add a,#8
 ld d,a
 srl c
 rr b
 ld a,#0
 jr nc,406$
 ld a,e
406$:
 ld (hl+),a
 ld (hl),d
 inc hl
 inc hl
 inc hl
 ld a,d
 add a,#8
 ld d,a
 srl c
 rr b
 ld a,#0
 jr nc,407$
 ld a,e
407$:
 ld (hl+),a
 ld (hl),d
 inc hl
 inc hl
 inc hl
 ld a,d
 add a,#8
 ld d,a
 ld a,d
 sub a,#32
 ld d,a
 ld a,e
 add a,#8
 ld e,a
 srl c
 rr b
 ld a,#0
 jr nc,408$
 ld a,e
408$:
 ld (hl+),a
 ld (hl),d
 inc hl
 inc hl
 inc hl
 ld a,d
 add a,#8
 ld d,a
 srl c
 rr b
 ld a,#0
 jr nc,409$
 ld a,e
409$:
 ld (hl+),a
 ld (hl),d
 inc hl
 inc hl
 inc hl
 ld a,d
 add a,#8
 ld d,a
 srl c
 rr b
 ld a,#0
 jr nc,410$
 ld a,e
410$:
 ld (hl+),a
 ld (hl),d
 inc hl
 inc hl
 inc hl
 ld a,d
 add a,#8
 ld d,a
 srl c
 rr b
 ld a,#0
 jr nc,411$
 ld a,e
411$:
 ld (hl+),a
 ld (hl),d
 inc hl
 inc hl
 inc hl
 ld a,d
 add a,#8
 ld d,a
 ld a,d
 sub a,#32
 ld d,a
 ld a,e
 add a,#8
 ld e,a
 srl c
 rr b
 ld a,#0
 jr nc,412$
 ld a,e
412$:
 ld (hl+),a
 ld (hl),d
 inc hl
 inc hl
 inc hl
 ld a,d
 add a,#8
 ld d,a
 srl c
 rr b
 ld a,#0
 jr nc,413$
 ld a,e
413$:
 ld (hl+),a
 ld (hl),d
 inc hl
 inc hl
 inc hl
 ld a,d
 add a,#8
 ld d,a
 srl c
 rr b
 ld a,#0
 jr nc,414$
 ld a,e
414$:
 ld (hl+),a
 ld (hl),d
 inc hl
 inc hl
 inc hl
 ld a,d
 add a,#8
 ld d,a
 srl c
 rr b
 ld a,#0
 jr nc,415$
 ld a,e
415$:
 ld (hl+),a
 ld (hl),d
 inc hl
 inc hl
 inc hl
 ld a,d
 add a,#8
 ld d,a
 ld a,d
 sub a,#32
 ld d,a
 ld a,e
 add a,#8
 ld e,a
 ret

; Exact clamped floor(delta*3/16384), Q16.16 meters to12 pixels/meter.
; ABI0 delta@SP+2, int16 resultDE. Split integer/fraction avoids long shifts.
_gbc_video_pixels::
 ldhl sp,#4
 ld e,(hl)
 inc hl
 ld d,(hl)
 ld a,d
 or a,a
 jr z,520$
 inc a
 jr z,520$
 bit 7,d
 jr nz,540$
 jr 550$
520$:
 ld h,d
 ld l,e
 add hl,hl
 add hl,hl
 ld d,h
 ld e,l
 add hl,hl
 add hl,de
 push hl
 ldhl sp,#4
 ld a,(hl+)
 ld h,(hl)
 ld l,a
 ld d,h
 ld e,l
 add hl,hl
 ld a,#0
 adc a,#0
 add hl,de
 adc a,#0
 add a,a
 add a,a
 ld e,a
 ld a,h
 rlca
 rlca
 and a,#3
 add a,e
 ld e,a
 ld d,#0
 pop hl
 add hl,de
 ld e,l
 ld d,h
 ret
540$:
 ld de,#0xf400
 ret
550$:
 ld de,#3072
 ret

; Four 8x8 object tiles in a2x2 square. ABI0 sprite@2,x@3,y@4,tile@5,prop@6.
_gbc_video_object::
 ldhl sp,#2
 ld a,(hl+)
 add a,a
 add a,a
 ld e,a
 ld d,#0
 ld b,(hl)
 inc hl
 ld c,(hl)
 inc hl
 ld a,(hl+)
 ld d,(hl)
 ld hl,#_shadow_OAM
 push af
 ld a,l
 add a,e
 ld l,a
 jr nc,600$
 inc h
600$:
 pop af
 ld e,a
 ld (hl),c
 inc hl
 ld (hl),b
 inc hl
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 inc e
 ld a,b
 add a,#8
 ld b,a
 ld (hl),c
 inc hl
 ld (hl),b
 inc hl
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 inc e
 ld a,b
 sub a,#8
 ld b,a
 ld a,c
 add a,#8
 ld c,a
 ld (hl),c
 inc hl
 ld (hl),b
 inc hl
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 inc e
 ld a,b
 add a,#8
 ld b,a
 ld (hl),c
 inc hl
 ld (hl),b
 inc hl
 ld (hl),e
 inc hl
 ld (hl),d
 inc hl
 inc e
 ret
