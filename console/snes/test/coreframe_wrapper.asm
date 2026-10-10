; Assembly-only ABI adapters for the core component regression driver.
.include "hdr.asm"
.SECTION ".coreframe_test_text" SUPERFREE
render_test_work_over:
 php
 rep #$30
 lda 5,s
 jsl core_work_over
 lda #0
 rol a
 sta.l tcc__r0
 plp
 rtl

; Deliberately run with a caller's nonzero direct page. Both return channels
; must agree; restore the normal C direct page before the harness resumes.
render_test_dma_left:
 php
 phd
 rep #$30
 lda 7,s
 tcd
 jsl core_dma_left
 sta.l render_test_value
 tdc
 sta.l render_test_d
 pld
 plp
 rtl
.ENDS
