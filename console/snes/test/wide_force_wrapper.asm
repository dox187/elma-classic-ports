; Experimental C entry for WIDE_FORCE_COMPONENT; not linked into the game.
; Include wide_native_force.inc before this file in the test translation unit.
;
; void wide_force_component(const u8 *gumiQ32, const u8 *rateQ40,
;                           u16 active, u8 *outQ40, u8 *fallback);
; Pointers address WRAM bank $7E. Inputs/output hold six little-endian bytes.
; PVSnesLib C pointers occupy two stack words (address followed by bank).
; Preserves D,DB,X,Y and caller flags. Output is untouched on fallback.
; This test owns a separate page; the production math-page layout is undecided.

.RAMSECTION ".wide_force_wrapper_ram" BANK 0 SLOT 1 ALIGN 256
wide_force_call_dp dsb 256
.ENDS

.SECTION ".wide_force_wrapper_text" SUPERFREE
wide_force_component:
	php
	phb
	phd
	rep #$30
	phx
	phy
	pea wide_force_call_dp
	pld
	sep #$20
	lda #$7E
	pha
	plb
	rep #$20
	lda 12,s
	tax
	lda.w 0,x
	sta.b 128
	lda.w 2,x
	sta.b 130
	lda.w 4,x
	sta.b 132
	lda 16,s
	tax
	lda.w 0,x
	sta.b 134
	lda.w 2,x
	sta.b 136
	lda.w 4,x
	sta.b 138
	lda 20,s
	beq _wide_call_inactive
	lda #1
_wide_call_inactive:
	sep #$20
	sta.b 140
	rep #$20
	WIDE_FORCE_COMPONENT 128,134,140,154,141,144
	sep #$20
	lda.b 141
	bne _wide_call_status
	rep #$20
	lda 22,s
	tax
	lda.b 154
	sta.w 0,x
	lda.b 156
	sta.w 2,x
	lda.b 158
	sta.w 4,x
_wide_call_status:
	rep #$20
	lda 26,s
	tax
	sep #$20
	lda.b 141
	sta.w 0,x
	rep #$20
	ply
	plx
	pld
	plb
	plp
	rtl
.ENDS
