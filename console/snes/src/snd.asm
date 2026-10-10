; The sounds on the APU. snd_init uploads the driver of the SPC700
; (spc/driver.asm) through the IPL and the image of the sound memory (the
; samples of build/gen/snd.asm) through the driver's loader. Then the
; functions tell the driver what to play through the ports, without waiting
; for it:
;   $2140  the pitch index of the engine (snd_omega_tab), every frame
;   $2141  bit 7 the gas, bits 0-6 the volume of the friction, every frame
;   $2142  the argument of a command
;   $2143  a command (sequence number << 3 | command), after $2142; the
;          driver echoes it in $2143 when it took it
; Commands wait in a small queue while the driver has not taken the last
; one; every call sends what it can.

.include "hdr.asm"
.include "core.inc"
.include "snd.inc"

.DEFINE SND_READY $A5

.RAMSECTION ".snd_vars" BANK 0 SLOT 1
snd_ready   db          ; SND_READY when the driver runs (RAM is not cleared)
snd_running db          ; 1 from the start of a level's sounds to snd_stop
snd_seq     db          ; the last command written to $2143
snd_qhead   db          ; the queue of commands: next to send
snd_qtail   db          ; next free
snd_q       dsb 16      ; (command, argument) pairs
snd_w       dw
snd_cnt     db          ; the step of the loader
.ENDS

.SECTION ".snd_text" SUPERFREE

;---------------------------------------------------------------------------
; void snd_init(void): the driver through the IPL, then the image through
; the driver's loader (3 bytes a step). About a second.
snd_init:
	php
	phb
	sep #$20
	lda #$80
	pha
	plb
	lda snd_ready
	cmp #SND_READY
	bne +
	jmp _init_end               ; the driver runs already
+	rep #$30
-	lda $2140                   ; the IPL is ready: $AA $BB
	cmp #$BBAA
	bne -
	lda #SND_DRIVER_ADDR
	sta $2142
	sep #$20
	lda #$01                    ; a block to load
	sta $2141
	lda #$CC
	sta $2140
-	cmp $2140
	bne -
	ldx #0
_drv:
	lda.l snd_driver,x
	sta $2141
	txa
	sta $2140
-	cmp $2140
	bne -
	inx
	cpx #SND_DRIVER_SIZE
	bne _drv
	rep #$20                    ; run it
	lda #SND_DRIVER_ADDR
	sta $2142
	sep #$20
	stz $2141
	txa
	inc a                       ; the last index + 2 (the loader waits for 1)
	cmp #2
	bcs +
	lda #2
+	sta $2140
-	cmp $2140
	bne -

	; The loader: the number of chunks, then the pieces of the image.
	rep #$20
	lda #SND_IMAGE_CHUNKS
	sta $2141
	sep #$20
	lda #1
	sta $2140
-	cmp $2140
	bne -
	inc a
	sta snd_cnt
	ldx #0
_piece:
	rep #$20
	lda.l snd_pieces+3,x        ; chunks of 255 bytes
	xba
	sec
	sbc.l snd_pieces+3,x        ; * 255
	clc
	adc.l snd_pieces,x
	pha                         ; the end of the piece
	lda.l snd_pieces,x
	tay
	sep #$20
	lda.l snd_pieces+2,x
	phx
	pha
	lda snd_cnt
	tax                         ; the step counter
	plb                         ; the bank of the piece
	phd
	rep #$20
	tsc
	tcd                         ; the direct page on the stack: the end at 5
	sep #$20
_step:
	rep #$20
	lda $0000,y
	sta.l $002141
	sep #$20
	lda $0002,y
	sta.l $002143
	txa
	sta.l $002140
	iny
	iny
	iny
	inx
-	cmp.l $002140
	bne -
	cpy.b $05
	bne _step
	pld
	txa
	sta.l snd_cnt
	lda #$80
	pha
	plb
	plx
	ply
	inx
	inx
	inx
	inx
	inx
	cpx #SND_PIECES*5
	bne _piece

	; The last step: the driver starts and echoes it when ready.
	rep #$20
	stz $2141
	sep #$20
	stz $2143
	lda snd_cnt
	sta $2140
-	cmp $2140
	bne -
	stz $2140
	stz $2141
	stz snd_seq
	stz snd_qhead
	stz snd_qtail
	stz snd_running
	lda #SND_READY
	sta snd_ready
_init_end:
	plb
	plp
	rtl

;---------------------------------------------------------------------------
; void snd_frame(u8 gas, u16 wheel_omega, u16 friction): the state of the
; game for the engine and the friction (setmotor, setsurlodas).
snd_frame:
	php
	phb
	sep #$20
	lda #$80
	pha
	plb
	lda snd_ready
	cmp #SND_READY
	bne _frame_end
	lda snd_running
	bne +
	jsr snd_start
+	rep #$30
	lda 7,s                     ; wheel_omega
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	lsr a
	tax
	sep #$20
	lda.l snd_omega_tab,x
	sta $2140
	rep #$20
	lda 9,s                     ; friction
	lsr a
	cmp #128
	bcc +
	lda #127
+	sep #$20
	sta snd_w
	lda 6,s                     ; gas
	beq +
	lda #$80
+	ora snd_w
	sta $2141
	ldy #8
	jsr snd_pump
_frame_end:
	plb
	plp
	rtl

;---------------------------------------------------------------------------
; void snd_effect(u16 id, u16 volume): an effect (startwave).
snd_effect:
	php
	phb
	sep #$20
	lda #$80
	pha
	plb
	lda snd_ready
	cmp #SND_READY
	bne _effect_end
	lda snd_running
	bne +
	jsr snd_start
+	rep #$30
	lda 8,s                     ; volume
	lsr a
	cmp #128
	bcc +
	lda #127
+	sep #$20
	xba
	lda 6,s                     ; id
	and #7
	beq _effect_end
	jsr snd_put
	ldy #1                      ; sent if the driver took the last one
	jsr snd_pump
_effect_end:
	plb
	plp
	rtl

;---------------------------------------------------------------------------
; void snd_stop(void): every sound off; what was queued is dropped.
snd_stop:
	php
	phb
	sep #$20
	lda #$80
	pha
	plb
	lda snd_ready
	cmp #SND_READY
	bne _stop_end
	stz snd_qhead
	stz snd_qtail
	stz snd_running
	stz $2140
	stz $2141
	lda #0
	xba
	lda #0
	rep #$10
	jsr snd_put
	ldx #4000                   ; until it is sent, or the driver is dead
-	ldy #1
	jsr snd_pump
	lda snd_qhead
	cmp snd_qtail
	beq _stop_end
	dex
	bne -
_stop_end:
	plb
	plp
	rtl

; The start of a level's sounds (8-bit A, DB $80).
snd_start:
	lda #1
	sta snd_running
	xba
	lda #0
	jsr snd_put
	rts

; Queues command A with argument B (8-bit A, 16-bit X, DB $80).
snd_put:
	sta snd_w
	xba
	sta snd_w+1
	lda snd_qtail
	inc a
	and #7
	cmp snd_qhead
	beq +                       ; full: dropped
	pha
	lda snd_qtail
	asl a
	rep #$20
	and #$00FF
	tax
	lda snd_w
	sta snd_q,x
	sep #$20
	pla
	sta snd_qtail
+	rts

; Sends the queued commands while the driver takes them, looking at its
; echo Y times at most (8-bit A, 16-bit X and Y, DB $80).
snd_pump:
_pump:
	lda snd_qhead
	cmp snd_qtail
	beq _pump_end
-	lda $2143
	cmp $2143
	bne -
	cmp snd_seq
	beq _send
	dey
	bne _pump
	rts
_send:
	lda snd_qhead
	asl a
	rep #$20
	and #$00FF
	tax
	lda snd_q,x                 ; command, argument
	sep #$20
	xba
	sta $2142
	xba
	sta snd_w
	lda snd_seq
	clc
	adc #8
	and #$F8
	ora snd_w
	sta $2143
	sta snd_seq
	lda snd_qhead
	inc a
	and #7
	sta snd_qhead
	bra _pump
_pump_end:
	rts

.ENDS
