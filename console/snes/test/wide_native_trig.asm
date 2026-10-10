.include "hdr.asm"
.include "phys.inc"
.include "wide_native_trig.inc"
.RAMSECTION ".wnt_ram" BANK 0 SLOT 1 ALIGN 256
wnt_ram dsb 256
.ENDS
.SECTION ".wnt_text" SUPERFREE
.MACRO WNT_ENTRY
 php
 phb
 phd
 rep #$30
 sep #$20
 lda.b #$80
 pha
 plb
 rep #$20
 lda #wnt_ram
 tcd
.ENDM
.MACRO WNT_EXIT
 pld
 plb
 plp
.ENDM
wnt_mul40:
 WNT_ENTRY
 WNT_MUL24 0,8,16,32,40,48,52,5,0
 WNT_EXIT
wnt_mul40_end:
 rtl
wnt_mul29:
 WNT_ENTRY
 WNT_MUL24 0,8,16,32,40,48,52,4,0
 WNT_EXIT
wnt_mul29_end:
 rtl
wnt_mul17:
 WNT_ENTRY
 WNT_MUL24 0,8,16,32,40,48,52,3,0
 WNT_EXIT
wnt_mul17_end:
 rtl
.ENDS
