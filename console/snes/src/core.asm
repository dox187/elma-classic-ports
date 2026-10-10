; The frame loop of the program: the NMI handler writes what the main loop
; prepared for the frame (OAM, the queue of DMA transfers, scroll and other
; registers) during the vertical blank, counts the frames and reads the
; joypad.
;
; Gameplay publishes a frame with core_frame_submit, computes upcoming physics,
; then calls core_frame_wait before reusing the OAM/DMA buffers. Menus use the
; blocking core_frame_done API. An NMI without a ready picture repeats a frame.
;
; C calls these with 16-bit registers and the data bank $7E; arguments are on
; the stack after the 3 bytes of the return address (u8 is 1 byte, u16 is 2,
; pointers and u32 are 4), the result goes into tcc__r0.

.include "hdr.asm"
.include "core.inc"

.RAMSECTION ".core_vars" BANK 0 SLOT 1
core_frame_count    dw      ; NMIs since the start
core_lag_count      dw      ; NMIs that found no frame ready
core_frame_lines    dw      ; TV-system scanlines
core_work_frame     dw      ; NMI count at the start of gameplay work
core_work_active    db      ; deadline enabled outside forced-blank loads
core_dma_overruns   dw      ; queues exceeding DMAQ_COST_MAX
core_work_reserve   dw
core_dma_tmp        dw
core_m7_latch       dw      ; high byte: first coefficient write, restored after NMI scroll
core_frame_ready    db      ; 1: the main loop finished the frame
core_pad            dw      ; buttons held on joypad 1 (JOY_*)
core_pad_new        dw      ; pressed since core_pad_take last cleared it
core_pad_prev       dw
core_inidisp        db      ; INIDISP written at the next frame
core_dmaq_n         dw      ; entries in the queue, times 8
core_dmaq_bytes     dw      ; bytes queued for the next frame
core_dmaq           dsb DMAQ_MAX*8
core_regq_n         dw      ; register writes queued, times 4
core_regq           dsb REGQ_MAX*4
core_scroll         dsw 6   ; BG1HOFS BG1VOFS BG2HOFS BG2VOFS BG3HOFS BG3VOFS
core_oam_hi_dirty   db
.ENDS

; The shadow of the OAM, written to it at every frame (512 + 32 bytes):
.RAMSECTION ".core_oam" BANK 0 SLOT 1 ALIGN 2
core_oam            dsb 544
.ENDS

; The NMI vector points into bank 0; the handler runs from the FastROM
; mirror.
.SECTION ".core_nmi_vec" SEMIFREE BANK 0 ORGA $8000 FORCE
core_nmi:
	jml core_nmi_fast
core_irq:
	jml core_irq_fast
.ENDS

.SECTION ".core_text" SUPERFREE

core_irq_fast:
	rep #$20
	pha
	sep #$20
	lda.l $004211               ; acknowledge
	rep #$20
	pla
	rti

core_nmi_fast:
	rep #$30
	pha
	phx
	phy
	phb
	sep #$20
	lda #$80
	pha
	plb                         ; DB $80: I/O, low RAM and ROM
	lda $4210                   ; acknowledge the NMI
	lda core_frame_ready
	bne +
	jmp _lag
+
	; Diagnose the whole queue, including the setup of every transfer.
	; Producers use the same budget before allocating their buffers.
	rep #$20
	lda core_dmaq_n
	asl a
	asl a
	sta core_dma_tmp
	asl a
	clc
	adc core_dma_tmp
	clc
	adc core_dmaq_bytes
	cmp #DMAQ_COST_MAX+1
	bcc +
	inc core_dma_overruns
+	sep #$20
	; OAM:
	stz $2102
	stz $2103
	rep #$20
	lda #$0400                  ; one register, OAMDATA
	sta $4300
	lda #core_oam
	sta $4302
	lda #544
	sta $4305
	sep #$20
	stz $4304                   ; bank 0
	lda #$01
	sta $420B

	; The queue of DMA transfers, in order:
	rep #$30
	ldx #0
_dmaloop:
	cpx core_dmaq_n
	bcs _dmadone
	lda core_dmaq+1,x           ; source address
	sta $4302
	lda core_dmaq+4,x           ; size
	sta $4305
	sep #$20
	lda core_dmaq+3,x           ; source bank
	sta $4304
	lda core_dmaq,x             ; type
	cmp #DMAQ_CGRAM
	beq _cgram
	cmp #DMAQ_VRAM32
	beq _vram32
	lda #$80                    ; VRAM, the address grows by a word
	bra _vram
_vram32:
	lda #$81                    ; VRAM, the address grows by 32 words
_vram:
	sta $2115
	rep #$20
	lda core_dmaq+6,x           ; VRAM address (words)
	sta $2116
	lda #$1801                  ; two registers, VMDATAL/H
	sta $4300
	sep #$20
	lda #$01
	sta $420B
	bra _next
_cgram:
	lda core_dmaq+6,x           ; first color
	sta $2121
	rep #$20
	lda #$2200                  ; one register, CGDATA
	sta $4300
	sep #$20
	lda #$01
	sta $420B
_next:
	rep #$20
	txa
	clc
	adc #8
	tax
	bra _dmaloop
_dmadone:
	stz core_dmaq_n
	stz core_dmaq_bytes

	; Scroll registers, each written twice:
	rep #$20
	lda core_scroll+0
	sep #$20
	sta $210D
	xba
	sta $210D
	rep #$20
	lda core_scroll+2
	sep #$20
	sta $210E
	xba
	sta $210E
	rep #$20
	lda core_scroll+4
	sep #$20
	sta $210F
	xba
	sta $210F
	rep #$20
	lda core_scroll+6
	sep #$20
	sta $2110
	xba
	sta $2110
	rep #$20
	lda core_scroll+8
	sep #$20
	sta $2111
	xba
	sta $2111
	rep #$20
	lda core_scroll+10
	sep #$20
	sta $2112
	xba
	sta $2112

	; Queued writes of 8-bit registers (address, value):
	rep #$30
	ldx #0
_regloop:
	cpx core_regq_n
	bcs _regdone
	lda core_regq,x
	tay
	sep #$20
	lda core_regq+2,x
	sta $0000,y
	rep #$20
	inx
	inx
	inx
	inx
	bra _regloop
_regdone:
	stz core_regq_n

	; BG1 scroll and M7A share a write latch. A ready frame may interrupt
	; physics between the two M7A writes. Restore only the latch through
	; unused M7X; this does not alter M7A, M7B, or their current product.
	sep #$20
	lda core_m7_latch+1
	sta $211F
	sep #$20
	lda core_inidisp
	sta $2100
	stz core_frame_ready
	bra _count
_lag:
	rep #$20
	inc core_lag_count
_count:
	rep #$20
	inc core_frame_count

	; Joypad 1, after the automatic reading finished:
	sep #$20
-	lda $4212
	and #$01
	bne -
	rep #$20
	lda $4218
	sta core_pad
	eor core_pad_prev
	and core_pad
	ora core_pad_new
	sta core_pad_new
	lda core_pad
	sta core_pad_prev

	rep #$30
	plb
	ply
	plx
	pla
	rti

;---------------------------------------------------------------------------
; void core_init(void): call once after consoleInit, in forced blank. Clears
; the queues and the OAM shadow (all sprites off the screen) and turns the
; NMI and the reading of the joypad on.
core_init:
	php
	rep #$30
	lda #0
	sta.l core_dmaq_n
	sta.l core_dmaq_bytes
	sta.l core_regq_n
	sta.l core_pad_new
	sta.l core_pad
	sta.l core_pad_prev
	sta.l core_frame_count
	sta.l core_lag_count
	sta.l core_dma_overruns
	sta.l core_work_frame
	sta.l core_scroll+0
	sta.l core_scroll+2
	sta.l core_scroll+4
	sta.l core_scroll+6
	sta.l core_scroll+8
	sta.l core_scroll+10
	lda.l snes_50hz
	and #$00FF
	beq +
	lda #312
	bra ++
+	lda #262
++	sta.l core_frame_lines
	jsl core_oam_clear
	sep #$20
	lda #0
	sta.l core_frame_ready
	sta.l core_work_active
	lda #$80
	sta.l core_inidisp
	sta.l $002100
	lda #$81                    ; NMI and joypad
	sta.l $004200
	plp
	rtl

; Gameplay work shares one deadline, even when a producer starts late.
core_work_begin:
	php
	rep #$20
	lda.l core_frame_count
	sta.l core_work_frame
	sep #$20
	lda #1
	sta.l core_work_active
	plp
	rtl

core_work_end:
	php
	sep #$20
	lda #0
	sta.l core_work_active
	plp
	rtl

; A16 = reserved scanlines; carry set means no time remains. A and flags
; are scratch; X/Y, DB and D remain untouched. Vblank belongs to the work
; for the next visible picture, so a raster >=225 is allowed. If physics
; already missed an NMI, finish preparing that picture against the next
; deadline: starving the map for the rest of the following frame would
; leave visible rows stale even though CPU time is available.
core_work_over:
	rep #$20
	sta.l core_work_reserve
	lda.l core_work_active
	and #$00FF
	beq @room
	lda.l core_frame_count
	cmp.l core_work_frame
	beq +
	sta.l core_work_frame
+
	sep #$20
	lda.l $002137
	lda.l $00213F
	lda.l $00213D
	xba
	lda.l $00213D
	and #$01
	xba
	rep #$20
	cmp #225
	bcs @room
	clc
	adc.l core_work_reserve
	cmp #225
	bcs @over
@room:
	clc
	rtl
@over:
	sec
	rtl

; Remaining queue cost, 96 byte-times per entry plus the actual payload.
; This scratch is separate from the NMI diagnostic: no shared temporary
; is live across an interrupt.
core_dma_left:
	php
	rep #$30
	lda.l core_dmaq_n
	asl a
	asl a
	sta.l core_work_reserve
	asl a
	clc
	adc.l core_work_reserve
	clc
	adc.l core_dmaq_bytes
	cmp #DMAQ_COST_MAX
	bcs @none
	eor #$FFFF
	inc a
	clc
	adc #DMAQ_COST_MAX
	bra @done
@none:
	lda #0
@done:
	sta.l tcc__r0
	plp
	rtl

; void core_oam_clear(void): every sprite of the shadow below the screen.
core_oam_clear:
	php
	rep #$30
	ldx #0
	lda #$E000                  ; x 0, y 224
-	sta.l core_oam,x
	inx
	inx
	inx
	inx
	cpx #512
	bcc -
	lda #0                      ; x bit 8 clear, small size
-	sta.l core_oam,x
	inx
	inx
	cpx #544
	bcc -
	plp
	rtl

; Publish separately so physics can use the CPU while a completed picture
; awaits NMI. Call core_frame_wait before touching any shared OAM/DMA data.
core_frame_submit:
	php
	sep #$20
	lda #1
	sta.l core_frame_ready
	plp
	rtl

core_frame_wait:
	php
	sep #$20
-	lda.l core_frame_ready
	bne -
	plp
core_frame_wait_end:
	rtl

; Original blocking API for menus, startup and terminal frames.
core_frame_done:
	jsl core_frame_submit
	jsl core_frame_wait
	rtl

; void core_wait_frames(u16 n): waits n NMIs (without a frame).
core_wait_frames:
	php
	rep #$30
	lda 5,s
	beq ++
	clc
	adc.l core_frame_count
	tax
-	txa
	cmp.l core_frame_count
	bne -
++	plp
	rtl

; u16 core_pad_take(void): the buttons pressed since the last call.
core_pad_take:
	php
	phb
	sep #$20
	lda #$80
	pha
	plb
	rep #$30
	lda core_pad_new
	sta.l tcc__r0
core_pad_take_read:
	; TRB atomically acknowledges only the edges just read. A different
	; edge latched by an intervening NMI remains pending for the next call.
	trb core_pad_new
	plb
	plp
core_pad_take_end:
	rtl

; void core_queue_vram(u16 vaddr, const void* src, u16 size)
; void core_queue_vram32(u16 vaddr, const void* src, u16 size)
; void core_queue_cgram(u16 color, const void* src, u16 size)
; Queues a DMA transfer for the next frame; src must stay valid until then.
; Returns 0 in tcc__r0 if the queue was full (nothing queued).
core_queue_vram:
	lda #DMAQ_VRAM
	bra _queue
core_queue_vram32:
	lda #DMAQ_VRAM32
	bra _queue
core_queue_cgram:
	lda #DMAQ_CGRAM
_queue:
	php
	rep #$30
	pha
	lda.l core_dmaq_n
	cmp #DMAQ_MAX*8
	bcc +
	pla
	lda #0
	sta.b tcc__r0
	plp
	rtl
+	tax
	pla
	sep #$20
	sta.l core_dmaq,x           ; type
	rep #$20
	lda 5,s                     ; vaddr (after php)
	sta.l core_dmaq+6,x
	lda 7,s                     ; src low
	sta.l core_dmaq+1,x
	lda 9,s                     ; src bank
	sep #$20
	sta.l core_dmaq+3,x
	rep #$20
	lda 11,s                    ; size
	sta.l core_dmaq+4,x
	clc
	adc.l core_dmaq_bytes
	sta.l core_dmaq_bytes
	txa
	clc
	adc #8
	sta.l core_dmaq_n
	lda #1
	sta.b tcc__r0
	plp
	rtl

; void core_queue_reg(u16 reg, u16 value): writes the 8-bit register reg
; ($21xx, $42xx...) with value at the next frame.
core_queue_reg:
	php
	rep #$30
	lda.l core_regq_n
	cmp #REGQ_MAX*4
	bcs +
	tax
	lda 5,s
	sta.l core_regq,x
	lda 7,s
	sta.l core_regq+2,x
	txa
	clc
	adc #4
	sta.l core_regq_n
+	plp
	rtl

; void core_vram_now(u16 vaddr, const void* src, u16 size): DMA to VRAM
; right away; only in forced blank (or in the vertical blank).
core_vram_now:
	php
	phb
	rep #$30
	sep #$20
	lda #$80
	pha
	plb
	lda #$80
	sta $2115
	rep #$20
	lda 6,s
	sta $2116
	lda 8,s
	sta $4302
	lda 12,s
	beq +
	sta $4305
	lda #$1801
	sta $4300
	sep #$20
	lda 10,s
	sta $4304
	lda #$01
	sta $420B
+	plb
	plp
	rtl

; void core_vram_fill_now(u16 vaddr, u16 value, u16 words): fills VRAM with
; a word, in forced blank.
core_vram_fill_now:
	php
	phb
	rep #$30
	sep #$20
	lda #$80
	pha
	plb
	lda #$80
	sta $2115
	rep #$20
	lda 6,s
	sta $2116
	lda 10,s
	tax
	beq +
	lda 8,s
-	sta $2118
	dex
	bne -
+	plb
	plp
	rtl

; void core_cgram_now(u16 color, const void* src, u16 size): DMA to CGRAM
; right away, in forced blank.
core_cgram_now:
	php
	phb
	rep #$30
	sep #$20
	lda #$80
	pha
	plb
	lda 6,s
	sta $2121
	rep #$20
	lda 8,s
	sta $4302
	lda 12,s
	beq +
	sta $4305
	lda #$2200
	sta $4300
	sep #$20
	lda 10,s
	sta $4304
	lda #$01
	sta $420B
+	plb
	plp
	rtl

; void core_screen_off(void): forced blank right away.
core_screen_off:
	php
	sep #$20
	lda #$80
	sta.l core_inidisp
	sta.l $002100
	plp
	rtl

; void core_screen_on(u16 brightness): full brightness is 15; from the next
; frame (the NMI writes INIDISP).
core_screen_on:
	php
	sep #$20
	lda 5,s
	and #$0F
	sta.l core_inidisp
	plp
	rtl

.ENDS
