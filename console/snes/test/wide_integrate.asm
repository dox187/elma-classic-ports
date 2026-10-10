.include "hdr.asm"
.include "wide_integrate.inc"
.RAMSECTION ".wide_integrate_ram" BANK 0 SLOT 1 ALIGN 256
wi_ram dsb 256
.ENDS
.SECTION ".wide_integrate_text" SUPERFREE
.MACRO WI_ENTRY
	php
	phb
	phd
	rep #$30
	sep #$20
	lda #$80
	pha
	plb
	rep #$20
	lda #wi_ram
	tcd
.ENDM
.MACRO WI_EXIT
	pld
	plb
	plp
.ENDM
wide_integrate_position:
	WI_ENTRY
	WIDE_INTEGRATE48 0,8,16,32,24,5,5
	WI_EXIT
wide_integrate_position_end:
	rtl
wide_integrate_angle:
	WI_ENTRY
	WIDE_INTEGRATE48 0,8,16,32,24,8,5
	WI_EXIT
wide_integrate_angle_end:
	rtl
; Higher precision layout: state48Q32 + rate48Q40, unwrapped throughout.
wide_integrate_position_wide:
	WI_ENTRY
	WIDE_INTEGRATE48 0,8,16,32,24,8,6
	WI_EXIT
wide_integrate_position_wide_end:
	rtl
wide_integrate_angle_wide:
	WI_ENTRY
	WIDE_INTEGRATE48 0,8,16,32,24,8,6
	WI_EXIT
wide_integrate_angle_wide_end:
	rtl
.ENDS
