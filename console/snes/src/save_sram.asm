; The battery-backed RAM of the cartridge (LoROM: bank $70, 8 KB) and the
; checksum of the saved state (save.c).

.include "hdr.asm"
.include "core.inc"

.DEFINE SRAM_BANK $70

.SECTION ".save_sram_text" SUPERFREE

; void save_sram_write(u16 ofs, const void* src, u16 n)
save_sram_write:
	php
	rep #$30
	lda 5,s
	sta.b tcc__r2
	lda #SRAM_BANK
	sta.b tcc__r2+2
	lda 7,s
	sta.b tcc__r1
	lda 9,s
	sta.b tcc__r1+2
	lda 11,s
	beq +
	tax
	ldy #0
	sep #$20
-	lda [tcc__r1],y
	sta [tcc__r2],y
	iny
	dex
	bne -
+	plp
	rtl

; void save_sram_read(u16 ofs, void* dst, u16 n)
save_sram_read:
	php
	rep #$30
	lda 5,s
	sta.b tcc__r2
	lda #SRAM_BANK
	sta.b tcc__r2+2
	lda 7,s
	sta.b tcc__r1
	lda 9,s
	sta.b tcc__r1+2
	lda 11,s
	beq +
	tax
	ldy #0
	sep #$20
-	lda [tcc__r2],y
	sta [tcc__r1],y
	iny
	dex
	bne -
+	plp
	rtl

; u16 save_sum(const void* p, u16 n, u16 seed): the checksum of n bytes:
; for each, the sum is rotated left by a bit and the byte added.
save_sum:
	php
	rep #$30
	lda 5,s
	sta.b tcc__r1
	lda 7,s
	sta.b tcc__r1+2
	lda 11,s
	sta.b tcc__r3               ; the sum
	lda 9,s
	beq +
	tax
	ldy #0
-	lda [tcc__r1],y
	and #$00FF
	sta.b tcc__r2
	lda.b tcc__r3
	asl a
	adc #0                      ; the bit shifted out comes in
	clc
	adc.b tcc__r2
	sta.b tcc__r3
	iny
	dex
	bne -
+	lda.b tcc__r3
	sta.b tcc__r0
	plp
	rtl

; u16 save_sram_sum(u16 ofs, u16 n, u16 seed): the same over the SRAM.
save_sram_sum:
	php
	rep #$30
	lda 5,s
	sta.b tcc__r1
	lda #SRAM_BANK
	sta.b tcc__r1+2
	lda 9,s
	sta.b tcc__r3
	lda 7,s
	beq +
	tax
	ldy #0
-	lda [tcc__r1],y
	and #$00FF
	sta.b tcc__r2
	lda.b tcc__r3
	asl a
	adc #0
	clc
	adc.b tcc__r2
	sta.b tcc__r3
	iny
	dex
	bne -
+	lda.b tcc__r3
	sta.b tcc__r0
	plp
	rtl

.ENDS
