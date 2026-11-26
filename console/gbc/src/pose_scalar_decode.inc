; Read one signed block remainder, then fall through RET into its Q24
; base-specific decoder. The upper half-page of each directory holds the
; low byte of its target address and the lower half holds the high byte.
.macro pose_dispatch row,targets,negative
 ld h,#>row
 ld l,d
 .if negative
 nop
 nop
 .else
 set 7,l
 .endif
 ld a,(hl)
 ld h,#>targets
 ld c,(hl)
 res 7,l
 ld b,(hl)
 push bc
 ld h,#0
 ld l,e
 add hl,hl
 add hl,hl
 add hl,hl
 add a,h
 ld h,a
 ret
.endm

.macro pose_add_low value
 .if ((value)&255)
 add a,#((value)&255)
 .endif
.endm

; The remainder contains an unsigned low word. Its known upper byte only
; receives a carry when the low byte of the base can produce one.
.macro pose_high value
 ld a,#(((value)>>8)&255)
 .if ((value)&255)
 adc a,#0
 .endif
.endm

.macro pose_block head,rest,ax,sine,hx,hy,r,x,y
 ld a,(hl+)
 pose_add_low hx
 ldh (#head),a
 ld a,(hl+)
 pose_add_low hy
 ldh (#head+2),a
 pose_high hy
 ldh (#head+3),a
 ld a,(hl+)
 .if sine
 cpl
 .endif
 pose_add_low r
 ld (#rest),a
 ld a,(hl+)
 .if sine
 cpl
 .endif
 .if ((r)&255)
 adc a,#(((r)>>8)&255)
 .else
 pose_add_low ((r)>>8)
 .endif
 ld (#rest+1),a
 ld a,(hl+)
 ldh (#ax),a
 ld a,(hl+)
 pose_add_low x
 ldh (#ax+1),a
 pose_high x
 ldh (#ax+2),a
 ld a,(hl+)
 .if sine
 ld c,a
 ld a,(hl)
 pose_add_low y
 ld b,a
 pose_high y
 ld e,a
 .else
 cpl
 add a,#1
 ldh (#pose_neg_cos_ay),a
 ld a,(hl)
 cpl
 adc a,#((-(y))&255)
 ldh (#pose_neg_cos_ay+1),a
 ld a,#((((-(y))>>8)-1)&255)
 adc a,#0
 ldh (#pose_neg_cos_ay+2),a
 .endif
 ret
.endm
