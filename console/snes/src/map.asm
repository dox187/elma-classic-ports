; The background of a level: BG1 (ground, grass, pictures) and BG2 (sky).
;
; tools/gen_map.py describes the data. BG1 is a 64x32 map, a window of
; 512x256 pixels that moves with the camera in both directions (cell x is
; map column x & 63, cell y map row y & 31). The cells of MAP_COLS x
; MAP_ROWS around the screen are kept ready: when the camera moves, the
; lines of cells that leave free their tiles, the ones that come get a job.
; A job first decodes its line from the chunks of the level and writes the
; tiles every cell can show at once (air, the texture, or for the special
; cells the texture or air as a stand-in), then makes the tiles of the
; special cells: edges are a texture tile and a mask, complex tiles are
; copied from the ROM. These go to tiles of VRAM from the cache (a stack of
; free tile numbers) through a buffer in WRAM, in runs of consecutive tiles.
;
; Lines that are on the screen are decoded in the frame they appear; the
; rest of the work goes on while the frame has time (MAP_LINES scanlines
; from the start of map_set_camera, read from the PPU's counter) and the
; DMA of the frame room, and waits for the next frame otherwise. Masks of
; the cells that hold tiles of the cache (a column's 32 bits, a row's 64)
; make freeing a line cheap.
;
; BG2 holds the sky: a pattern of columns whose width divides 256, written
; once; it scrolls at half the speed horizontally and not vertically.
;
; Video Detail Low (map_detail 0) shows the level as the original does
; then, without pictures and grass: the chunks that differ come from the
; low part of the level (map_chunk), there are no complex cells and no
; second texture, and only the foreground texture and its palette are
; loaded.
;
; The routines called from C set D to map_dp and DB to $7F (all our RAM is
; there) and restore them.

.include "hdr.asm"
.include "core.inc"

.DEFINE MAP_COLS     35         ; cells kept ready: the 33 columns of the screen and one more on each side
.DEFINE MAP_ROWS     31         ; the 29 rows and one more above and below
.DEFINE MAP_MAXT     32         ; tiles made in a frame
.DEFINE MAP_MAXCOMP  20         ; edges (masked texture) made in a frame
.DEFINE MAP_MAXRUNS  12         ; DMA transfers of tiles in a frame
.DEFINE MAP_MAXJOBS  80         ; lines waiting (all of them in the region and more)
.DEFINE MAP_LINES    42         ; scanlines map_set_camera may start new work in (about 57000 master clocks)
.DEFINE MAP_DECLINES 22         ; and decoding a line (about 20 scanlines of work)
.DEFINE MAP_TOUCH    8          ; lines written to the VRAM map in a frame
.DEFINE MAP_JOBSIZE  224        ; a job: 10 bytes and 6 a special cell
.DEFINE BG1_TILES    704
.DEFINE PAL_TEX      3          ; palettes: 1-2 sky, 3 foreground texture, 4 second texture, complex 4-7
.DEFINE PAL_CPLX     4
.DEFINE MAP_MAGIC0   $4D41
.DEFINE MAP_MAGIC1   $5021

; A job (map_jobs):
.DEFINE J_TYPE   0              ; 0 column, 1 row
.DEFINE J_COORD  1              ; x of a column, y of a row
.DEFINE J_DONE1  3              ; decoded
.DEFINE J_NSPEC  4              ; special cells
.DEFINE J_CUR    5              ; the first one not made yet
.DEFINE J_DIRTY  6              ; to write this frame: 1 the line, 2 the part J_LO..J_HI of it
.DEFINE J_LO     7              ; (cells by their place in the map: row or column 0-63)
.DEFINE J_HI     8
.DEFINE J_LIST   10             ; 6 bytes a special cell: coordinate along the line, entry, foreground entry

; The record of a level (map_level_info, 32 bytes):
.DEFINE LI_WC    0
.DEFINE LI_HC    2
.DEFINE LI_CW    4
.DEFINE LI_CH    6
.DEFINE LI_DIR   8
.DEFINE LI_CBANK 11
.DEFINE LI_TEX   12
.DEFINE LI_NTX   15
.DEFINE LI_NTY   16
.DEFINE LI_NTX2  17
.DEFINE LI_NTY2  18
.DEFINE LI_PAL   19
.DEFINE LI_TBASE 22
.DEFINE LI_SKY   24
.DEFINE LI_SKYK  25
.DEFINE LI_NTEX  27
.DEFINE LI_CHUNKS 29
; The record of a sky (map_sky_info, 16 bytes):
.DEFINE SI_TILES 0
.DEFINE SI_TSIZE 3
.DEFINE SI_COLS  5
.DEFINE SI_PAL   8
.DEFINE SI_NCOL  11

; Direct page (map_dp):
.DEFINE DTP      $00            ; long: texture tile
.DEFINE DTP2     $03            ; long: texture tile + 16
.DEFINE DMP      $06            ; long: mask
.DEFINE DCP      $09            ; long: chunk
.DEFINE DDIR     $0C            ; long: chunk directory
.DEFINE DSRC     $0F            ; long: anything in the ROM
.DEFINE DT0      $12            ; words
.DEFINE DT1      $14
.DEFINE DT2      $16
.DEFINE DT3      $18
.DEFINE DT4      $1A
.DEFINE DT5      $1C
.DEFINE DT6      $1E
.DEFINE DT7      $20
.DEFINE DT8      $22
.DEFINE DT9      $24
.DEFINE DJ       $26            ; offset of the current job
.DEFINE DSB      $28            ; byte: special bits of the chunk row
.DEFINE DGB      $2A            ; byte: foreground bits
.DEFINE DQT      $2E            ; queue: type
.DEFINE DQS      $30            ; queue: source (long)
.DEFINE DQZ      $33            ; queue: size
.DEFINE DQV      $35            ; queue: VRAM address
.DEFINE DNOW     $38            ; 1: transfer at once (forced blank)
.DEFINE DSTAT    $3A            ; 1: the budget of the frame ran out
.DEFINE DBIT     $3C            ; bit of the cell in a chunk row
.DEFINE DLEFT    $3E            ; bits of the cells left of it
.DEFINE DCNT     $40            ; cells of a part of a line
.DEFINE DLT      $42            ; 4 bytes of temporaries
.DEFINE DLEFTN   $46            ; cells left of a part of a line (in the loops)
.DEFINE DLINE0   $48            ; scanline at the start of map_set_camera
.DEFINE DLP      $4A            ; where the next special cell of a decoded line goes
.DEFINE DNS      $4C            ; special cells of the decoded line
.DEFINE DCP8     $50            ; long: the chunk + 8 (its foreground bits)
.DEFINE DCPP     $53            ; long: the chunk + 16 (special cells before each row)
.DEFINE DNF      $56            ; 1: the line holds no tiles of the cache (no checks needed)
.DEFINE DMI      $58            ; map_cellbits: byte of the column mask
.DEFINE DMB      $5A            ; its bit
.DEFINE DRI      $5C            ; byte of the row mask
.DEFINE DRB      $5E            ; its bit
.DEFINE DLS      $60            ; long: a pair of the low part

.RAMSECTION ".map_dp" BANK 0 SLOT 1 ALIGN 256
map_dp              dsb 100
.ENDS

.RAMSECTION ".map_detail" BANK 0 SLOT 1
map_detail          db          ; Video Detail: 1 High, 0 Low (no pictures, no grass); set before map_load
.ENDS

.BASE $00
.RAMSECTION ".map_vars" BANK $7F SLOT 3
map_cam_x           dw
map_cam_y           dw
map_rx0             dw          ; first column of the cells kept ready
map_ry0             dw          ; first row
map_wc              dw          ; the level in cells
map_hc              dw
map_cw              dw          ; in chunks
map_ch              dw
map_dir             dsb 3       ; chunk directory
map_cbank           db
map_tex             dsb 3       ; texture tiles
map_ntx             dw          ; foreground pattern in tiles
map_nty             dw
map_ntx2            dw          ; second texture's pattern (0: none)
map_nty2            dw
map_ntex1           dw          ; foreground tiles
map_cache0          dw          ; first tile of the cache
map_tbase           dw          ; complex tiles of the level from this one
map_skyk            dw          ; BG2 scroll: (cam_x + skyk) / 2
map_cdelta          dw          ; address of the chunks - $8000
map_ldelta          dw          ; address of the low part - 2
map_lbank           db          ; and its bank
map_lowf            dw          ; $8000: Video Detail Low, else 0
map_dlim            dw          ; map_chunk: words below this are not chunks of the High part ($FFFF with Low)
map_fglim           dw          ; foreground entries are below this
map_crow            dw          ; map_chunk: the last row of chunks
map_crowo           dw          ; and its offset in the directory
map_popr            dsb 256     ; bits set in a byte (copied from map_pop)
map_bitw            dsw 8       ; bit of a cell in a chunk byte
map_bit1            dsb 8       ; 1 << n
map_nbit1           dsb 8       ; ~(1 << n)
map_high            dsb 256     ; the highest bit set in a byte
map_cmask           dsb 256     ; cells holding a tile of the cache: 32 bits a column of the map
map_rmask           dsb 256     ; and 64 bits a row
map_leftw           dsw 8       ; bits of the cells left of it
map_freesp          dw          ; free tiles on the stack, times 2
map_free            dsw BG1_TILES
map_nstage          dw          ; tiles made this frame
map_ncomp           dw          ; of which edges
map_nruns           dw          ; transfers of tiles, times 6
map_runs            dsb MAP_MAXRUNS*6   ; offset in map_stage, first tile, count
map_lastslot        dw
map_jn              dw          ; jobs waiting
map_jq              dsw MAP_MAXJOBS ; their offsets in map_jobs, in order
map_jfn             dw          ; free records, times 2
map_jfree           dsw MAP_MAXJOBS ; their offsets
map_jn2             dw          ; map_jn * 2
map_jundn           dw          ; jobs not decoded yet, times 2
map_jund            dsw MAP_MAXJOBS ; their offsets
map_ndone           dw          ; jobs done since the queue was last tidied
map_jline           dsw 64+32   ; the job of each column, row of the map (offset + 1; 0 none)
map_tln             dw          ; jobs written this frame, times 2
map_tl              dsw MAP_TOUCH ; their offsets
map_ndecoded        dw          ; jobs decoded this frame
map_ncolbuf         dw          ; column buffers used, times 64
map_wk_i            dw          ; place in map_jq of the job looked at, times 2
map_wk_n            dw
map_bytes0          dw
map_qfirst          dw          ; our entries of the DMA queue of the next NMI (core_dmaq_n
map_qend            dw          ; before and after map_flush)
map_vx0             dw          ; first cell column on the screen
map_vy0             dw          ; first cell row on the screen
map_magic           dsw 2       ; MAP_MAGIC when a level is loaded (RAM is not cleared at the start)
; Measurements for the tests:
map_stat_tiles      dw          ; tiles made in the last frame
map_stat_comp       dw          ; of which edges
map_stat_bytes      dw          ; bytes queued for the DMA in the last frame
map_stat_jobs       dw          ; jobs waiting after the last frame
map_stat_short      dw          ; frames that ran out of budget since the load
map_stat_minfree    dw          ; fewest free cache tiles since the load, times 2
map_stat_nofree     dw          ; cells shown with a stand-in because the cache was empty
map_stat_resets     dw          ; starts from scratch (jumps of the camera) since the load
.ENDS

.RAMSECTION ".map_big" BANK $7F SLOT 3
map_shadow          dsw 2048    ; the BG1 map (32 rows of 64)
map_stage           dsb MAP_MAXT*32
map_colbuf          dsb MAP_TOUCH*64
map_jobs            dsb MAP_MAXJOBS*MAP_JOBSIZE
map_zero            dsb 32      ; zeros (the air tile)
.ENDS
.BASE $80

.SECTION ".map_tables" SUPERFREE
; Bit of a cell in a byte of a chunk, and the bits of the cells left of it:
map_bit:
	.db $80, $40, $20, $10, $08, $04, $02, $01
map_left:
	.db $00, $80, $C0, $E0, $F0, $F8, $FC, $FE
; Bits set in a byte:
map_pop:
.REPT 256 INDEX i
	.db (i & 1) + ((i >> 1) & 1) + ((i >> 2) & 1) + ((i >> 3) & 1) + ((i >> 4) & 1) + ((i >> 5) & 1) + ((i >> 6) & 1) + ((i >> 7) & 1)
.ENDR
.ENDS

.SECTION ".map_text" SUPERFREE

;---------------------------------------------------------------------------
; void map_set_camera(s16 cam_x, s16 cam_y): the top left pixel of the
; screen in level pixels. Sets the scroll of BG1 and BG2 and, with a level
; loaded, moves the cells kept ready and queues the transfers.
map_set_camera:
	php
	phb
	phd
	rep #$30
	lda 8,s
	tax
	lda 10,s
	tay
	pea map_dp
	pld
	sep #$20
	lda #$7F
	pha
	plb
	rep #$20
	stx map_cam_x
	sty map_cam_y
	stz DNOW
	jsr map_vline
	sta DLINE0
	jsr map_scroll
	lda map_magic
	cmp #MAP_MAGIC0
	bne +
	lda map_magic+2
	cmp #MAP_MAGIC1
	bne +
	jsr map_region
map_p_region:
	jsr map_work
map_p_work:
	jsr map_flush
+
map_set_camera_end:
	rep #$30
	pld
	plb
	plp
	rtl

; The scroll registers: BG1 at the camera (the first line of the screen
; shows the line after VOFS), BG2 at half the speed, fixed vertically.
map_scroll:
	lda map_cam_x
	sta.l core_scroll+0
	lda map_cam_y
	dec a
	sta.l core_scroll+2
	lda map_cam_x
	clc
	adc map_skyk
	cmp #$8000
	ror a
	sta.l core_scroll+4
	lda #$FFFF
	sta.l core_scroll+6
	rts

; A = A >> 3 (arithmetic) - 1: the first column or row kept ready.
map_first:
	cmp #$8000
	ror a
	cmp #$8000
	ror a
	cmp #$8000
	ror a
	dec a
	rts

;---------------------------------------------------------------------------
; Moves the cells kept ready to the camera: the lines that leave give
; their tiles back, the ones that come get a job. A jump (or too many jobs)
; starts everything again.
map_region:
	lda map_cam_x
	jsr map_first
	sta DT0
	lda map_cam_y
	jsr map_first
	sta DT1
	; Too far: from the start.
	lda DT0
	sec
	sbc map_rx0
	bpl +
	eor #$FFFF
	inc a
+	cmp #MAP_COLS
	bcc +
	jmp map_reset
+
	lda DT1
	sec
	sbc map_ry0
	bpl +
	eor #$FFFF
	inc a
+	cmp #MAP_ROWS
	bcc +
	jmp map_reset
+
@h:	lda DT0
	sec
	sbc map_rx0
	beq @v
	bmi @left
	lda map_rx0
	jsr map_free_col
	lda map_rx0
	and #$003F
	asl a
	tax
	jsr map_line_left
	inc map_rx0
	lda map_rx0
	clc
	adc #MAP_COLS-1
	ldx #0
	jsr map_job_add
	bcc +
	jmp map_reset
+
	bra @h
@left:
	lda map_rx0
	clc
	adc #MAP_COLS-1
	pha
	jsr map_free_col
	pla
	and #$003F
	asl a
	tax
	jsr map_line_left
	dec map_rx0
	lda map_rx0
	ldx #0
	jsr map_job_add
	bcc +
	jmp map_reset
+
	bra @h
@v:	lda DT1
	sec
	sbc map_ry0
	beq @done
	bmi @up
	lda map_ry0
	jsr map_free_row
	lda map_ry0
	and #$001F
	clc
	adc #64
	asl a
	tax
	jsr map_line_left
	inc map_ry0
	lda map_ry0
	clc
	adc #MAP_ROWS-1
	ldx #1
	jsr map_job_add
	bcc +
	jmp map_reset
+
	bra @v
@up:
	lda map_ry0
	clc
	adc #MAP_ROWS-1
	pha
	jsr map_free_row
	pla
	and #$001F
	clc
	adc #64
	asl a
	tax
	jsr map_line_left
	dec map_ry0
	lda map_ry0
	ldx #1
	jsr map_job_add
	bcc +
	jmp map_reset
+
	bra @v
@done:
	rts
@reset:
	jmp map_reset

; Everything from the start at the camera: no tiles in use, every row a job.
map_reset:
	inc map_stat_resets
	jsr map_free_init
	jsr map_shadow_clear
	jsr map_jobs_init
	lda map_cam_x
	jsr map_first
	sta map_rx0
	lda map_cam_y
	jsr map_first
	sta map_ry0
	sta DT0
	ldy #MAP_ROWS
-	phy
	lda DT0
	ldx #1
	jsr map_job_add
	inc DT0
	ply
	dey
	bne -
	rts

; The stack of free tiles: all of the cache, the first on top.
map_free_init:
	lda #BG1_TILES-1
	ldx #0
-	cmp map_cache0
	bcc +
	sta map_free,x
	inx
	inx
	dec a
	bra -
+	stx map_freesp
	stx map_stat_minfree
	ldx #0
-	stz map_cmask,x
	stz map_rmask,x
	inx
	inx
	cpx #256
	bcc -
	rts

; The map of BG1 all air (its copy in WRAM).
map_shadow_clear:
	ldx #0
-	stz map_shadow,x
	inx
	inx
	cpx #4096
	bcc -
	rts

; Frees the tiles of the cache held by column A (cells x), from the bottom
; (so that the tiles come back in their order).
map_free_col:
	and #$003F
	sta DT2                     ; column
	asl a
	asl a
	clc
	adc #3
	sta DT3                     ; byte of its mask
	lda DT2
	lsr a
	lsr a
	lsr a
	sta DT4                     ; byte of the column in a row's mask
	lda DT2
	and #$0007
	tay
	lda map_nbit1,y
	ora #$FF00
	sta DT5                     ; ~its bit there
	lda #4
	sta DT9
@byte:
	ldy DT3
	lda map_cmask,y
	and #$00FF
	beq @next
	tay
	lda map_high,y
	and #$00FF
	tay
	; Off in the column's mask:
	sep #$20
	lda map_nbit1,y
	ldx DT3
	and map_cmask,x
	sta map_cmask,x
	rep #$20
	tya
	sta DLT
	lda DT9
	dec a
	asl a
	asl a
	asl a
	clc
	adc DLT                     ; row
	sta DLT
	; Off in the row's mask:
	asl a
	asl a
	asl a
	clc
	adc DT4
	tay
	sep #$20
	lda map_rmask,y
	and DT5
	sta map_rmask,y
	rep #$20
	; The tile goes back:
	lda DLT
	xba
	lsr a
	sta DLT
	lda DT2
	asl a
	ora DLT
	tax
	jsr map_free_at
	bra @byte
@next:
	dec DT3
	dec DT9
	bne @byte
	rts

; Frees the tiles of the cache held by row A (cells y), from the right.
map_free_row:
	and #$001F
	sta DT2                     ; row
	asl a
	asl a
	asl a
	clc
	adc #7
	sta DT3                     ; byte of its mask
	lda DT2
	lsr a
	lsr a
	lsr a
	sta DT4                     ; byte of the row in a column's mask
	lda DT2
	and #$0007
	tay
	lda map_nbit1,y
	ora #$FF00
	sta DT5
	lda #8
	sta DT9
@byte:
	ldy DT3
	lda map_rmask,y
	and #$00FF
	beq @next
	tay
	lda map_high,y
	and #$00FF
	tay
	sep #$20
	lda map_nbit1,y
	ldx DT3
	and map_rmask,x
	sta map_rmask,x
	rep #$20
	tya
	sta DLT
	lda DT9
	dec a
	asl a
	asl a
	asl a
	clc
	adc DLT                     ; column
	sta DLT
	asl a
	asl a
	clc
	adc DT4
	tay
	sep #$20
	lda map_cmask,y
	and DT5
	sta map_cmask,y
	rep #$20
	lda DLT
	asl a
	sta DLT
	lda DT2
	xba
	lsr a
	ora DLT
	tax
	jsr map_free_at
	bra @byte
@next:
	dec DT3
	dec DT9
	bne @byte
	rts

; Frees the tile of the cache at X of the shadow (its bits are off
; already) and clears the cell.
map_free_at:
	lda map_shadow,x
	and #$03FF
	cmp map_cache0
	bcc +
	ldy map_freesp
	sta map_free,y
	iny
	iny
	sty map_freesp
	stz map_shadow,x
+	rts

; No jobs; all records free.
map_jobs_init:
	stz map_jn
	stz map_jundn
	stz map_ndone
	ldx #0
	lda #0
-	sta map_jfree,x
	clc
	adc #MAP_JOBSIZE
	inx
	inx
	cpx #MAP_MAXJOBS*2
	bcc -
	stx map_jfn
	ldx #0
-	stz map_jline,x
	inx
	inx
	cpx #(64+32)*2
	bcc -
	rts

; The place in map_jline of the line of job Y -> X.
map_job_line:
	lda map_jobs+J_TYPE,y
	and #$00FF
	bne +
	lda map_jobs+J_COORD,y
	and #$003F
	asl a
	tax
	rts
+	lda map_jobs+J_COORD,y
	and #$001F
	clc
	adc #64
	asl a
	tax
	rts

; A job for line A (X: 0 column, 1 row) at the end of the queue; carry set
; if there is no room.
map_job_add:
	pha
	lda map_jfn
	bne +
	pla
	sec
	rts
+	dec a
	dec a
	sta map_jfn
	phx
	tax
	lda map_jfree,x
	tay
	lda map_jn
	asl a
	tax
	tya
	sta map_jq,x
	inc map_jn
	ldx map_jundn
	sta map_jund,x
	inx
	inx
	stx map_jundn
	plx
	txa
	sep #$20
	sta map_jobs+J_TYPE,y
	lda #0
	sta map_jobs+J_DONE1,y
	sta map_jobs+J_NSPEC,y
	sta map_jobs+J_CUR,y
	sta map_jobs+J_DIRTY,y
	rep #$20
	pla
	sta map_jobs+J_COORD,y
	; The job of the line (an earlier one of the same line is over):
	jsr map_job_line
	lda map_jline,x
	beq +
	phy
	phx
	dec a
	tay
	jsr map_job_end
	plx
	ply
+	tya
	inc a
	sta map_jline,x
	clc
	rts

; The line (map_jline place X) left the region: its job is over.
map_line_left:
	lda map_jline,x
	beq +
	dec a
	tay
	jsr map_job_end
+	rts

; Job Y is over (whatever it had left to do): done, not undecoded, not the
; job of its line.
map_job_end:
	sep #$20
	lda map_jobs+J_DONE1,y
	bne +
	rep #$20
	jsr map_und_remove
	sep #$20
+	lda #1
	sta map_jobs+J_DONE1,y
	lda #0
	sta map_jobs+J_NSPEC,y
	sta map_jobs+J_CUR,y
	rep #$20
	inc map_ndone
	jsr map_job_line
	tya
	inc a
	cmp map_jline,x
	bne +
	stz map_jline,x
+	rts

; Job Y finished its special cells: done, and not the job of its line.
map_job_finished:
	inc map_ndone
	jsr map_job_line
	tya
	inc a
	cmp map_jline,x
	bne +
	stz map_jline,x
+	rts

; Takes job Y off the list of jobs not decoded yet (keeps Y).
map_und_remove:
	ldx #0
-	cpx map_jundn
	bcs ++
	tya
	cmp map_jund,x
	beq +
	inx
	inx
	bra -
+	; The last one comes to its place:
	phy
	ldy map_jundn
	dey
	dey
	sty map_jundn
	lda map_jund,y
	sta map_jund,x
	ply
++	rts

; Job Y is written to the VRAM map this frame (DJ = Y); carry set if there
; is no room for one more line. Keeps Y.
map_touch:
	sep #$20
	lda map_jobs+J_DIRTY,y
	rep #$20
	and #$00FF
	bne +
	ldx map_tln
	cpx #MAP_TOUCH*2
	bcs ++
	tya
	sta map_tl,x
	inx
	inx
	stx map_tln
	sep #$20
	lda #2
	sta map_jobs+J_DIRTY,y
	lda #$FF
	sta map_jobs+J_LO,y
	lda #0
	sta map_jobs+J_HI,y
	rep #$20
+	clc
	rts
++	sec
	rts

;---------------------------------------------------------------------------
; The jobs of the frame. First the lines that are on the screen and not
; decoded yet (they must be shown now), then all jobs in order as far as
; the time of the frame (MAP_LINES scanlines from the start of
; map_set_camera), the tiles and the lines of the frame allow.
map_work:
	stz map_nstage
	stz map_ncomp
	stz map_nruns
	stz map_ndecoded
	stz map_tln
	stz DSTAT
	lda #$FFFF
	sta map_lastslot
	; The cells on the screen:
	lda map_cam_x
	jsr map_first
	inc a
	sta map_vx0
	lda map_cam_y
	jsr map_first
	inc a
	sta map_vy0
	; Lines on the screen first (map_jund changes when one is decoded):
	stz map_wk_i
@vis:
	ldx map_wk_i
	cpx map_jundn
	bcs @fifo
	lda map_jund,x
	sta DJ
	tay
	lda map_jobs+J_TYPE,y
	and #$00FF
	bne @vrow
	lda map_jobs+J_COORD,y
	sec
	sbc map_vx0
	cmp #33
	bcs @vnext
	bra @vdec
@vrow:
	lda map_jobs+J_COORD,y
	sec
	sbc map_vy0
	cmp #29
	bcs @vnext
@vdec:
	jsr map_decode_job
	bcs @fifo
	bra @vis                    ; (another job is at this place now)
@vnext:
	inc map_wk_i
	inc map_wk_i
	bra @vis
@fifo:
	stz map_wk_i                ; place of the job in the queue
	lda map_jn
	asl a
	sta map_jn2
@job:
	ldx map_wk_i
	cpx map_jn2
	bcc +
	jmp @end
+	lda map_jq,x
	sta DJ
	tay
	sep #$20
	lda map_jobs+J_DONE1,y
	rep #$20
	and #$00FF
	bne @made
	lda #MAP_DECLINES
	jsr map_over_at
	bcs @end
	jsr map_decode_job
	bcs @end
	ldy DJ
@made:
	; Special cells left?
	sep #$20
	lda map_jobs+J_CUR,y
	cmp map_jobs+J_NSPEC,y
	rep #$20
	bcs @next
	jsr map_touch
	bcs @end
@p_make0:
	jsr map_make
@p_make1:
	ldy DJ
	sep #$20
	lda map_jobs+J_CUR,y
	cmp map_jobs+J_NSPEC,y
	rep #$20
	bcc +
	jsr map_job_finished
+	lda DSTAT
	bne @end
@next:
	inc map_wk_i
	inc map_wk_i
	jmp @job
@end:
	lda DSTAT
	beq +
	inc map_stat_short
+	rts

; Decodes job DJ (Y) and marks it decoded and to be written; carry set (and
; nothing done) if no more lines can be written this frame.
map_decode_job:
	jsr map_touch
	bcc +
	rts
+	sep #$20
	lda #1
	sta map_jobs+J_DIRTY,y
	rep #$20
	jsr map_und_remove
	inc map_ndecoded
@p_dec0:
	jsr map_decode
@p_dec1:
	ldy DJ
	sep #$20
	lda #1
	sta map_jobs+J_DONE1,y
	lda map_jobs+J_NSPEC,y
	rep #$20
	bne +
	jsr map_job_finished
+	clc
	rts

; The scanline the PPU is drawing (0-261 NTSC, 0-311 PAL) -> A.
map_vline:
	sep #$20
	lda.l $002137               ; latches the counters
	lda.l $00213F               ; the next reads give the low bytes
	lda.l $00213D
	xba
	lda.l $00213D
	and #$01
	xba
	rep #$20
	rts

; Carry set (and DSTAT 1) if the time of the frame is over (never while
; loading); map_over_at: if A scanlines of it have passed.
map_over:
	lda #MAP_LINES
map_over_at:
	sta.b DLT+2
	lda DNOW
	bne @no
	jsr map_vline
	sec
	sbc DLINE0
	bpl +
	clc
	adc #262
+	cmp.b DLT+2
	bcc @no
	lda #1
	sta DSTAT
	sec
	rts
@no:
	clc
	rts

;---------------------------------------------------------------------------
; Decodes the line of job DJ: writes every cell into the shadow (special
; cells as a stand-in) and lists the special ones.
map_decode:
	lda DJ
	clc
	adc #J_LIST
	sta DLP
	stz DNS
	ldy DJ
	lda map_jobs+J_TYPE,y
	and #$00FF
	beq +
	jsr map_decode_row
	bra ++
+	jsr map_decode_col
++	ldy DJ
	sep #$20
	lda DNS
	sta map_jobs+J_NSPEC,y
	rep #$20
	rts

; X % map_ntx -> A (A, X up to 32767; hardware division by 8 bits).
map_mod:
	sta.l $004204
	sep #$20
	lda DT9
	sta.l $004206
	rep #$20
	nop
	nop
	nop
	nop
	nop
	nop
	nop
	nop
	lda.l $004216
	rts

; A mod n (n in DT9, 1..255) for any signed A.
map_smod:
	cmp #$8000
	bcc map_mod
	; Negative: n - 1 - ((-A - 1) mod n)
	eor #$FFFF
	jsr map_mod
	eor #$FFFF
	sec
	adc DT9
	dec a
	rts

; The foreground tile (0-based) of cell (DT0, DT1) -> A (uses DT9).
map_fgtile:
	lda map_ntx
	sta DT9
	lda DT0
	jsr map_smod
	pha
	lda map_nty
	sta DT9
	lda DT1
	jsr map_smod
	sep #$20
	sta.l $004202
	lda map_ntx
	sta.l $004203
	rep #$20
	pla
	clc
	adc.l $004216
	rts


; Gives back tile A of the cache, held by the cell at X of the shadow
; (keeps X and Y).
map_push:
	phy
	ldy map_freesp
	sta map_free,y
	iny
	iny
	sty map_freesp
	ply
	; (falls through)

; Clears the bits of the cell at X in the masks of the cache (keeps X, Y).
map_clearbits:
	phy
	jsr map_cellbits
	sep #$20
	ldy DMB
	lda map_nbit1,y
	ldy DMI
	and map_cmask,y
	sta map_cmask,y
	ldy DRB
	lda map_nbit1,y
	ldy DRI
	and map_rmask,y
	sta map_rmask,y
	rep #$20
	ply
	rts

; Sets the bits of cell (DT0, DT1) in the masks of the cache (keeps X).
map_setbits:
	lda DT0
	and #$003F
	asl a
	asl a
	sta DMI
	lda DT1
	and #$001F
	sta DMB
	lsr a
	lsr a
	lsr a
	clc
	adc DMI
	sta DMI
	lda DT1
	and #$001F
	asl a
	asl a
	asl a
	sta DRI
	lda DT0
	and #$003F
	sta DRB
	lsr a
	lsr a
	lsr a
	clc
	adc DRI
	sta DRI
	sep #$20
	lda DMB
	and #$07
	tay
	lda map_bit1,y
	ldy DMI
	ora map_cmask,y
	sta map_cmask,y
	lda DRB
	and #$07
	tay
	lda map_bit1,y
	ldy DRI
	ora map_rmask,y
	sta map_rmask,y
	rep #$20
	rts

; The places of the cell at X (offset in the shadow) in the masks: DMI,
; DMB byte and bit of its column's mask, DRI, DRB of its row's.
map_cellbits:
	txa
	lsr a
	and #$003F
	sta DRB                     ; column
	asl a
	asl a
	sta DMI
	txa
	asl a
	xba
	and #$001F
	sta DMB                     ; row
	asl a
	asl a
	asl a
	sta DRI
	lda DMB
	lsr a
	lsr a
	lsr a
	clc
	adc DMI
	sta DMI
	lda DRB
	lsr a
	lsr a
	lsr a
	clc
	adc DRI
	sta DRI
	lda DMB
	and #$0007
	sta DMB
	lda DRB
	and #$0007
	sta DRB
	rts

; Frees what the shadow holds at X if it is a tile of the cache.
.MACRO FREEX
	lda map_shadow,x
	beq +
	and #$03FF
	cmp map_cache0
	bcc +
	jsr map_push
+
.ENDM

; Writes entry A into the shadow at X, freeing what was there.
map_put:
	pha
	FREEX
	pla
	sta map_shadow,x
	rts

; Adds a special cell to the list of the job being decoded (DLP, DNS):
; coordinate along the line DT6, entry A, foreground entry DT5. Keeps X.
.MACRO LISTADD
	ldy DLP
	sta map_jobs+2,y
	lda DT6
	sta map_jobs,y
	lda DT5
	sta map_jobs+4,y
	tya
	clc
	adc #6
	sta DLP
	inc DNS
.ENDM

; Reads the chunk of cell (DT0, DT1) (both inside the level) into DCP
; (0 air, 1 foreground, else the address of a mixed chunk), the one of
; Video Detail Low if map_lowf says so. Keeps X.
map_chunk:
	lda DT1
	lsr a
	lsr a
	lsr a
	cmp map_crow
	beq +
	sta map_crow
	sep #$20
	sta.l $004202
	lda map_cw
	sta.l $004203
	rep #$20
	nop
	nop
	nop
	lda.l $004216
	asl a
	sta map_crowo
+	lda DT0
	lsr a
	lsr a
	lsr a
	asl a
	clc
	adc map_crowo
	tay
	lda [DDIR],y
	cmp map_dlim
	bcc @other
@rec:
	clc
	adc map_cdelta
	sta DCP
	adc #8
	sta DCP8
	adc #8
	sta DCPP
	rts
@other:
	cmp #2
	bcc @plain
	bit map_lowf
	bmi @low
	; A chunk that Low shows differently: the first word of its pair.
	clc
	adc map_ldelta
	sta DLS
	lda [DLS]
	cmp #2
	bcs @rec
@plain:
	sta DCP
	rts
	; Video Detail Low (everything comes here): a chunk of either part,
	; the bank of the pointers changes with it.
@low:
	cmp #$8000
	bcs @lhigh
	clc
	adc map_ldelta
	sta DLS
	ldy #2
	lda [DLS],y                 ; the second word of the pair
	cmp #2
	bcc @plain
	cmp #$8000
	bcc @lpart
@lhigh:
	clc
	adc map_cdelta
	sta DCP
	adc #8
	sta DCP8
	adc #8
	sta DCPP
	sep #$20
	lda map_cbank
	bra @bank
	.ACCU 16
@lpart:
	clc
	adc map_ldelta
	sta DCP
	adc #8
	sta DCP8
	adc #8
	sta DCPP
	sep #$20
	lda map_lbank
@bank:
	sta.b DCP+2
	sta.b DCP8+2
	sta.b DCPP+2
	rep #$20
	rts

; The entry of the special cell of row Y of chunk DCP whose row has the
; special bits DSB, DLEFT the bits of the cells left of it -> A.
.MACRO SPECENTRY
	lda [DCPP],y
	and #$00FF
	sta DLT
	lda DSB
	and DLEFT
	tay
	lda map_popr,y
	and #$00FF
	clc
	adc DLT
	asl a
	adc #24
	tay
	lda [DCP],y
.ENDM

;---------------------------------------------------------------------------
; A column: cells (x, ry0..ry0+MAP_ROWS-1). X is the offset in the shadow,
; DT5 the entry of the foreground texture, DT1 the y, DT7 the cells left.
map_decode_col:
	ldy DJ
	lda map_jobs+J_COORD,y
	sta DT0
	lda map_ry0
	sta DT1
	lda DT0
	and #$003F
	asl a
	sta DT2
	lda DT1
	and #$001F
	xba
	lsr a
	ora DT2
	sta DT4
	jsr map_fgtile
	inc a
	ora #PAL_TEX << 10
	sta DT5
	lda #MAP_ROWS
	sta DT7
	; Does the column hold tiles of the cache?
	lda DT0
	and #$003F
	asl a
	asl a
	tay
	lda map_cmask,y
	ora map_cmask+2,y
	beq +
	lda #0
	bra ++
+	lda #1
++	sta DNF
	ldx DT4
	; A column outside the level: all foreground.
	lda DT0
	cmp map_wc
	bcc +
	ldy DT7
	jmp map_colfg
+	and #$0007
	asl a
	tay
	lda map_bitw,y
	sta DBIT
	lda map_leftw,y
	sta DLEFT
@seg:
	lda DT7
	bne +
	rts
+	lda DT1
	bpl +
	; Above the level:
	eor #$FFFF
	inc a
	cmp DT7
	bcc ++
	lda DT7
++	sta DCNT
	tay
	jsr map_colfg
	bra @adv
+	cmp map_hc
	bcc +
	ldy DT7
	jmp map_colfg
+	; To the end of the chunk:
	and #$0007
	sta DT8
	lda #8
	sec
	sbc DT8
	cmp DT7
	bcc +
	lda DT7
+	sta DCNT
	jsr map_chunk
	lda DCP
	cmp #2
	bcs @mixed
	ldy DCNT
	cmp #1
	beq +
	jsr map_colair
	bra @adv
+	jsr map_colfg
	bra @adv
@mixed:
	lda DT1
	sta DT6
	jsr map_colmix
@adv:
	lda DT1
	clc
	adc DCNT
	sta DT1
	lda DT7
	sec
	sbc DCNT
	sta DT7
	jmp @seg

; Y cells of a column: foreground (DNF: without looking at what was there).
map_colfg:
	lda DNF
	bne @nf
-	FREEX
	lda DT5
	sta map_shadow,x
	clc
	adc map_ntx
	cmp map_fglim
	bcc +
	sbc map_ntex1
+	sta DT5
	txa
	clc
	adc #128
	and #$0FFF
	tax
	dey
	bne -
	rts
@nf:
	lda DT5
-	sta map_shadow,x
	clc
	adc map_ntx
	cmp map_fglim
	bcc +
	sbc map_ntex1
+	pha
	txa
	clc
	adc #128
	and #$0FFF
	tax
	pla
	dey
	bne -
	sta DT5
	rts

; Y cells of a column: air.
map_colair:
	lda DNF
	bne @nf
-	FREEX
	stz map_shadow,x
	lda DT5
	clc
	adc map_ntx
	cmp map_fglim
	bcc +
	sbc map_ntex1
+	sta DT5
	txa
	clc
	adc #128
	and #$0FFF
	tax
	dey
	bne -
	rts
@nf:
	lda DT5
-	stz map_shadow,x
	clc
	adc map_ntx
	cmp map_fglim
	bcc +
	sbc map_ntex1
+	pha
	txa
	clc
	adc #128
	and #$0FFF
	tax
	pla
	dey
	bne -
	sta DT5
	rts

; DCNT cells of a column in mixed chunk DCP from its row DT8.
map_colmix:
	lda DCNT
	sta DLEFTN
	ldy DT8
@cell:
	lda [DCP],y
	and #$00FF
	sta DSB
	and DBIT
	bne @spec
@ground:
	lda [DCP8],y
	and DBIT
	beq @air
	FREEX
	lda DT5
	sta map_shadow,x
	bra @next
@air:
	FREEX
	stz map_shadow,x
	bra @next
@spec:
	sty DT8
	SPECENTRY
	LISTADD
	ldy DT8
	bra @ground
@next:
	iny
	inc DT6
	lda DT5
	clc
	adc map_ntx
	cmp map_fglim
	bcc +
	sbc map_ntex1
+	sta DT5
	txa
	clc
	adc #128
	and #$0FFF
	tax
	dec DLEFTN
	beq +
	jmp @cell
+	rts

;---------------------------------------------------------------------------
; A row: cells (rx0..rx0+MAP_COLS-1, y). X is the offset in the shadow
; (DT2 its row part), DT5 the entry of the foreground texture, DT3 the x in
; its pattern, DT0 the x, DT7 the cells left.
map_decode_row:
	ldy DJ
	lda map_jobs+J_COORD,y
	sta DT1
	lda map_rx0
	sta DT0
	and #$003F
	asl a
	sta DT3
	lda DT1
	and #$001F
	xba
	lsr a
	sta DT2
	ora DT3
	sta DT4
	jsr map_fgtile
	inc a
	ora #PAL_TEX << 10
	sta DT5
	lda map_ntx
	sta DT9
	lda DT0
	jsr map_smod
	sta DT3
	lda #MAP_COLS
	sta DT7
	; Does the row hold tiles of the cache?
	lda DT1
	and #$001F
	asl a
	asl a
	asl a
	tay
	lda map_rmask,y
	ora map_rmask+2,y
	ora map_rmask+4,y
	ora map_rmask+6,y
	beq +
	lda #0
	bra ++
+	lda #1
++	sta DNF
	ldx DT4
	; A row outside the level: all foreground.
	lda DT1
	cmp map_hc
	bcc +
	ldy DT7
	jmp map_rowfg
+	and #$0007
	sta DT8                     ; row in the chunks
@seg:
	lda DT7
	bne +
	rts
+	lda DT0
	bpl +
	; Left of the level:
	eor #$FFFF
	inc a
	cmp DT7
	bcc ++
	lda DT7
++	sta DCNT
	tay
	jsr map_rowfg
	bra @adv
+	cmp map_wc
	bcc +
	ldy DT7
	jmp map_rowfg
+	and #$0007
	sta DT6
	asl a
	tay
	lda map_bitw,y
	sta DBIT
	lda map_leftw,y
	sta DLEFT
	lda #8
	sec
	sbc DT6
	cmp DT7
	bcc +
	lda DT7
+	sta DCNT
	jsr map_chunk
	lda DCP
	cmp #2
	bcs @mixed
	ldy DCNT
	cmp #1
	beq +
	jsr map_rowair
	bra @adv
+	jsr map_rowfg
	bra @adv
@mixed:
	ldy DT8
	lda [DCP],y
	and #$00FF
	sta DSB
	lda [DCP8],y
	and #$00FF
	sta DGB
	lda DT0
	sta DT6
	jsr map_rowmix
@adv:
	lda DT0
	clc
	adc DCNT
	sta DT0
	lda DT7
	sec
	sbc DCNT
	sta DT7
	jmp @seg

; The next cell of a row: X, DT5, DT3.
.MACRO ROWNEXT
	inc DT5
	lda DT3
	inc a
	cmp map_ntx
	bcc +
	lda DT5
	sec
	sbc map_ntx
	sta DT5
	lda #0
+	sta DT3
	txa
	inc a
	inc a
	and #$007E
	ora DT2
	tax
.ENDM

; Y cells of a row: foreground (DNF: without looking at what was there).
map_rowfg:
	lda DNF
	bne @nf
@cell:
	FREEX
	lda DT5
	sta map_shadow,x
	ROWNEXT
	dey
	bne @cell
	rts
@nf:
	lda DT5
	sta map_shadow,x
	ROWNEXT
	dey
	bne @nf
	rts

; Y cells of a row: air.
map_rowair:
	lda DNF
	bne @nf
@cell:
	FREEX
	stz map_shadow,x
	ROWNEXT
	dey
	bne @cell
	rts
@nf:
	stz map_shadow,x
	ROWNEXT
	dey
	bne @nf
	rts

; DCNT cells of a row in mixed chunk DCP (its row's bits DSB, DGB) from
; the cell of bit DBIT.
map_rowmix:
	lda DCNT
	sta DLEFTN
@cell:
	lda DSB
	and DBIT
	bne @spec
@ground:
	lda DGB
	and DBIT
	beq @air
	FREEX
	lda DT5
	sta map_shadow,x
	bra @next
@air:
	FREEX
	stz map_shadow,x
	bra @next
@spec:
	ldy DT8
	SPECENTRY
	LISTADD
	bra @ground
@next:
	lsr DBIT
	lda DLEFT
	lsr a
	ora #$0080
	sta DLEFT
	inc DT6
	ROWNEXT
	dec DLEFTN
	beq +
	jmp @cell
+	rts

;---------------------------------------------------------------------------
; Makes the tiles of the special cells of job DJ from its cursor, as far as
; the budget of the frame allows (DSTAT 1 when it ran out).
map_make:
	ldy DJ
	sep #$20
	lda map_jobs+J_CUR,y
	cmp map_jobs+J_NSPEC,y
	rep #$20
	bcc +
	rts
+	and #$00FF
	sta DT6                     ; index
@spec:
	ldy DJ
	lda map_jobs+J_NSPEC,y
	and #$00FF
	cmp DT6
	beq +
	bcs ++
+	jmp @done
++	lda DT6
	asl a
	adc DT6
	asl a
	clc
	adc DJ
	tax
	lda map_jobs+J_LIST+2,x
	sta DT3                     ; entry
	lda map_jobs+J_LIST+4,x
	and #$03FF
	dec a
	sta DT5                     ; foreground tile
	lda map_jobs+J_LIST,x
	sta DT2
	; The cell: (job's x, coordinate) or (coordinate, job's y).
	lda map_jobs+J_TYPE,y
	and #$00FF
	bne @row
	lda map_jobs+J_COORD,y
	sta DT0
	lda DT2
	sta DT1
	bra +
@row:
	lda map_jobs+J_COORD,y
	sta DT1
	lda DT2
	sta DT0
+	; Still kept ready?
	lda DT0
	sec
	sbc map_rx0
	bmi @skip
	cmp #MAP_COLS
	bcs @skip
	lda DT1
	sec
	sbc map_ry0
	bmi @skip
	cmp #MAP_ROWS
	bcs @skip
	lda DT0
	and #$003F
	asl a
	sta DT4
	lda DT1
	and #$001F
	xba
	lsr a
	ora DT4
	sta DT4                     ; shadow offset
	jsr map_make_cell
	lda DSTAT
	bne @stop
	; The part of the line to write again:
	ldy DJ
	lda map_jobs+J_TYPE,y
	and #$00FF
	bne +
	lda DT1
	and #$001F
	bra ++
+	lda DT0
	and #$003F
++	sep #$20
	cmp map_jobs+J_LO,y
	bcs +
	sta map_jobs+J_LO,y
+	cmp map_jobs+J_HI,y
	bcc +
	sta map_jobs+J_HI,y
+	rep #$20
@skip:
	inc DT6
	jmp @spec
@stop:
	; Out of budget: the cursor stays here.
	ldy DJ
	lda DT6
	sep #$20
	sta map_jobs+J_CUR,y
	lda map_jobs+J_DIRTY,y
	rep #$20
	rts
@done:
	ldy DJ
	sep #$20
	lda map_jobs+J_NSPEC,y
	sta map_jobs+J_CUR,y
	rep #$20
	rts

; Makes the cell (DT0, DT1) of entry DT3 at shadow offset DT4 (foreground
; tile DT5). DSTAT 1 if out of budget (nothing done).
map_make_cell:
	jsr map_over
	bcc +
	rts
+	lda DT3
	bmi @cplx
	; Texture: which one and its tile.
	and #$4000
	beq @fg
	lda map_ntx2
	sta DT9
	lda DT0
	jsr map_smod
	sta DT5
	lda map_nty2
	sta DT9
	lda DT1
	jsr map_smod
	sep #$20
	sta.l $004202
	lda map_ntx2
	sta.l $004203
	rep #$20
	lda DT5
	clc
	adc map_ntex1
	nop
	clc
	adc.l $004216
	sta DT5
	lda.w #(PAL_TEX + 1) << 10
	bra +
@fg:
	lda #PAL_TEX << 10
+	sta DT7                     ; palette bits
	lda DT3
	and #$3FFF
	bne @edge
	; The full mask: the texture's own tile.
	lda DT5
	inc a
	ora DT7
	ldx DT4
	jmp map_put
@edge:
	lda map_ncomp
	cmp #MAP_MAXCOMP
	bcs @short
	jsr map_alloc
	bcs @short
	bvs @none
	stx DT8                     ; offset in the stage
	sta DT2                     ; tile
	inc map_ncomp
	jsr map_compose
	lda DT2
	ora DT7
	ldx DT4
	jsr map_put
	jmp map_setbits
@cplx:
	jsr map_alloc
	bcs @short
	bvs @none
	stx DT8
	sta DT2
	jsr map_copy
	; Palette, priority:
	lda DT3
	and #$3000
	lsr a
	lsr a
	clc
	adc #PAL_CPLX << 10
	sta DT7
	lda DT3
	and #$4000
	lsr a
	ora DT7
	ora DT2
	ldx DT4
	jsr map_put
	jmp map_setbits
@short:
	lda #1
	sta DSTAT
	rts
@none:
	; No free tile: the stand-in stays.
	inc map_stat_nofree
	rts

; A tile of the cache for this frame: A = tile, X = offset in map_stage.
; Carry set: out of budget. Overflow set: no free tile.
map_alloc:
	lda map_nstage
	cmp #MAP_MAXT
	bcs @short
	ldx map_freesp
	bne +
	clc
	sep #$40
	rts
+	lda map_free-2,x            ; the tile on top
	sta DT9
	; The same transfer as the last tile, or a new one:
	dec a
	cmp map_lastslot
	beq @same
	lda map_nruns
	cmp #MAP_MAXRUNS*6
	bcs @short
	tay
	lda map_nstage
	asl a
	asl a
	asl a
	asl a
	asl a
	sta map_runs,y
	lda DT9
	sta map_runs+2,y
	lda #1
	sta map_runs+4,y
	tya
	clc
	adc #6
	sta map_nruns
	bra @take
@same:
	ldy map_nruns
	lda map_runs-2,y
	inc a
	sta map_runs-2,y
@take:
	ldx map_freesp
	dex
	dex
	stx map_freesp
	cpx map_stat_minfree
	bcs +
	stx map_stat_minfree
+	lda DT9
	sta map_lastslot
	lda map_nstage
	inc map_nstage
	asl a
	asl a
	asl a
	asl a
	asl a
	tax
	lda DT9
	clc
	clv
	rts
@short:
	sec
	clv
	rts

; Edge: texture tile DT5 (0-based) through mask DT3 & $3FFF into the stage
; at DT8.
map_compose:
	lda DT5
	asl a
	asl a
	asl a
	asl a
	asl a
	clc
	adc map_tex
	sta DTP
	clc
	adc #16
	sta DTP2
	sep #$20
	lda map_tex+2
	sta.b DTP+2
	sta.b DTP2+2
	rep #$20
	; The mask: 2048 a bank.
	lda DT3
	and #$3FFF
	sta DT9
	xba
	lsr a
	lsr a
	lsr a
	and #$001F
	tax
	sep #$20
	lda.l map_mask_bank,x
	sta.b DMP+2
	rep #$20
	txa
	asl a
	tax
	lda DT9
	and #$07FF
	asl a
	asl a
	asl a
	asl a
	clc
	adc.l map_mask_base,x
	sta DMP
	ldx DT8
.REPT 8 INDEX r
	ldy #2*r
	lda [DTP],y
	and [DMP],y
	sta map_stage+2*r,x
	lda [DTP2],y
	and [DMP],y
	sta map_stage+16+2*r,x
.ENDR
	rts

; Complex tile DT3 & $0FFF of the level into the stage at DT8: DMA from
; the ROM to the WRAM (channel 7, the NMI uses channel 0 only).
map_copy:
	lda DT3
	and #$0FFF
	clc
	adc map_tbase
	sta DT9
	xba
	lsr a
	lsr a
	and #$003F
	tax                         ; bank part (1024 tiles each)
	sep #$20
	lda.l map_tile_bank,x
	sta.l $004374
	rep #$20
	txa
	asl a
	tax
	lda DT9
	and #$03FF
	asl a
	asl a
	asl a
	asl a
	asl a
	clc
	adc.l map_tile_base,x
	sta.l $004372
	lda DT8
	clc
	adc #map_stage
	sta.l $002181
	sep #$20
	lda #$01                    ; bank $7F
	sta.l $002183
	rep #$20
	lda #$8000                  ; to $2180, one register
	sta.l $004370
	lda #32
	sta.l $004375
	sep #$20
	lda #$80
	sta.l $00420B
	rep #$20
	rts

;---------------------------------------------------------------------------
; Queues (or, in forced blank, does) the transfers of the frame: the tiles
; made, then the lines written; drops the jobs that are done.
map_flush:
	lda.l core_dmaq_bytes
	sta map_bytes0
	lda.l core_dmaq_n
	sta map_qfirst
	; Tiles:
	ldy #0
-	cpy map_nruns
	bcs +
	lda #DMAQ_VRAM
	sta DQT
	lda map_runs,y
	clc
	adc #map_stage
	sta DQS
	sep #$20
	lda #$7F
	sta.b DQS+2
	rep #$20
	lda map_runs+4,y
	asl a
	asl a
	asl a
	asl a
	asl a
	sta DQZ
	lda map_runs+2,y
	asl a
	asl a
	asl a
	asl a
	sta DQV
	phy
	jsr map_queue
	ply
	tya
	clc
	adc #6
	tay
	bra -
+	lda map_nstage
	sta map_stat_tiles
	lda map_ncomp
	sta map_stat_comp
	; The lines written:
	stz map_ncolbuf
	ldx #0
@tl:
	cpx map_tln
	bcs @tld
	phx
	lda map_tl,x
	sta DJ
	tay
	jsr map_line_dma
	ldy DJ
	sep #$20
	lda #0
	sta map_jobs+J_DIRTY,y
	rep #$20
	plx
	inx
	inx
	bra @tl
@tld:
	; The jobs done go (when there are a few of them):
	lda map_ndone
	cmp #8
	bcs +
	lda map_jfn
	cmp #16*2
	bcs @dropped
+	jsr map_tidy
@dropped:
	lda.l core_dmaq_n
	sta map_qend
	lda map_jn
	sec
	sbc map_ndone
	sta map_stat_jobs
	lda.l core_dmaq_bytes
	sec
	sbc map_bytes0
	sta map_stat_bytes
	rts

; Takes the jobs that are done off the queue and frees their records.
map_tidy:
	stz map_ndone
	ldx #0
	stz DT8                     ; jobs kept, times 2
	lda map_jn
	asl a
	sta DT9
@job:
	cpx DT9
	bcs @end
	lda map_jq,x
	tay
	sep #$20
	lda map_jobs+J_DONE1,y
	beq @keep
	lda map_jobs+J_CUR,y
	cmp map_jobs+J_NSPEC,y
	bcc @keep
	rep #$20
	phx
	ldx map_jfn
	tya
	sta map_jfree,x
	inx
	inx
	stx map_jfn
	plx
	bra @next
@keep:
	rep #$20
	phx
	ldx DT8
	tya
	sta map_jq,x
	inx
	inx
	stx DT8
	plx
@next:
	inx
	inx
	bra @job
@end:
	lda DT8
	lsr a
	sta map_jn
	rts

; The VRAM map of job DJ's line, or of the part J_LO..J_HI of it (from
; the shadow).
map_line_dma:
	ldy DJ
	lda map_jobs+J_DIRTY,y
	and #$00FF
	cmp #2
	bne @all
	lda map_jobs+J_LO,y
	and #$00FF
	sta DT1
	lda map_jobs+J_HI,y
	and #$00FF
	cmp DT1
	bcs +
	rts                         ; nothing made
+	sta DT2
	bra +
@all:
	stz DT1
	lda #63
	sta DT2
+	sep #$20
	lda #$7F
	sta.b DQS+2
	rep #$20
	lda map_jobs+J_TYPE,y
	and #$00FF
	bne +
	jmp @col
+	; A row: the cells DT1..DT2 of the 64, the halves apart.
	lda map_jobs+J_COORD,y
	and #$001F
	sta DT0
	lda #DMAQ_VRAM
	sta DQT
	lda DT1
	cmp #32
	bcs @right
	lda DT2
	cmp #32
	bcc +
	lda #31
+	jsr @part
	lda DT2
	cmp #32
	bcc @x
	lda #32
	sta DT1
@right:
	lda DT2
@part:
	; Cells DT1..A of row DT0:
	sec
	sbc DT1
	inc a
	asl a
	sta DQZ
	lda DT0
	xba
	lsr a
	clc
	adc DT1
	adc DT1
	adc #map_shadow
	sta DQS
	lda DT0
	asl a
	asl a
	asl a
	asl a
	asl a
	sta DQV
	lda DT1
	cmp #32
	bcc +
	clc
	adc #$0400-32
+	clc
	adc DQV
	adc #VRAM_BG1_MAP
	sta DQV
	jmp map_queue
@x:	rts
@col:
	; A column: rows DT1..DT2 (of 32) copied out of the shadow, then a
	; transfer down the column.
	lda map_ncolbuf
	cmp #MAP_TOUCH*64
	bcc +
	rts
+	lda DT2
	cmp #32
	bcc +
	lda #31
	sta DT2
+	lda map_jobs+J_COORD,y
	and #$003F
	sta DT0
	asl a
	sta DT3
	; A few rows one by one, else all of them at once:
	lda DT2
	sec
	sbc DT1
	cmp #8
	bcs @all32
	inc a
	sta DT9
	lda DT1
	xba
	lsr a
	ora DT3
	tax
	lda DT1
	asl a
	clc
	adc map_ncolbuf
	tay
-	lda map_shadow,x
	sta map_colbuf,y
	iny
	iny
	txa
	clc
	adc #128
	tax
	dec DT9
	bne -
	jmp @copied
@all32:
	ldx DT3
	ldy map_ncolbuf
.REPT 32 INDEX r
	lda map_shadow+128*r,x
	sta map_colbuf+2*r,y
.ENDR
@copied:
	lda DT2
	sec
	sbc DT1
	inc a
	asl a
	sta DQZ
	lda map_ncolbuf
	clc
	adc DT1
	adc DT1
	adc #map_colbuf
	sta DQS
	lda map_ncolbuf
	clc
	adc #64
	sta map_ncolbuf
	lda #DMAQ_VRAM32
	sta DQT
	lda DT0
	cmp #32
	bcc +
	clc
	adc #$0400-32
+	sta DQV
	lda DT1
	asl a
	asl a
	asl a
	asl a
	asl a
	clc
	adc DQV
	adc #VRAM_BG1_MAP
	sta DQV
	jmp map_queue

; Queues DQT, DQS, DQZ, DQV for the next NMI (or does it now with DNOW).
map_queue:
	lda DNOW
	bne map_dma_now
	lda.l core_dmaq_n
	cmp #DMAQ_MAX*8
	bcs +
	tax
	sep #$20
	lda DQT
	sta.l core_dmaq,x
	lda.b DQS+2
	sta.l core_dmaq+3,x
	rep #$20
	lda DQS
	sta.l core_dmaq+1,x
	lda DQZ
	sta.l core_dmaq+4,x
	clc
	adc.l core_dmaq_bytes
	sta.l core_dmaq_bytes
	lda DQV
	sta.l core_dmaq+6,x
	txa
	clc
	adc #8
	sta.l core_dmaq_n
+	rts

; The same, right away (forced blank), with DMA channel 0.
map_dma_now:
	sep #$20
	lda DQT
	cmp #DMAQ_CGRAM
	beq @cg
	cmp #DMAQ_VRAM32
	beq +
	lda #$80
	bra ++
+	lda #$81
++	sta.l $002115
	rep #$20
	lda DQV
	sta.l $002116
	lda #$1801
	sta.l $004300
	bra @go
@cg:
	lda DQV
	sta.l $002121
	rep #$20
	lda #$2200
	sta.l $004300
@go:
	lda DQS
	sta.l $004302
	lda DQZ
	sta.l $004305
	sep #$20
	lda.b DQS+2
	sta.l $004304
	lda #$01
	sta.l $00420B
	rep #$20
	rts

;---------------------------------------------------------------------------
; Takes our transfers off the DMA queue if the NMI has not done them yet
; (map_set_camera of the level before; the next level's are written now).
map_unqueue:
	lda map_magic
	cmp #MAP_MAGIC0
	bne @x
	lda map_qend
	cmp map_qfirst
	beq @x
	bcc @x
	cmp.l core_dmaq_n
	beq +
	bcs @x                      ; done by the NMI already
+	; The bytes of ours:
	ldx map_qfirst
	lda.l core_dmaq_bytes
	sta DT0
-	cpx map_qend
	bcs +
	lda DT0
	sec
	sbc.l core_dmaq+4,x
	sta DT0
	txa
	clc
	adc #8
	tax
	bra -
+	lda DT0
	sta.l core_dmaq_bytes
	; The entries after ours come down:
	ldx map_qend
	ldy map_qfirst
-	txa
	cmp.l core_dmaq_n
	bcs +
	lda.l core_dmaq,x
	phx
	tyx
	sta.l core_dmaq,x
	plx
	inx
	inx
	iny
	iny
	bra -
+	tya
	sta.l core_dmaq_n
@x:	stz map_qfirst
	stz map_qend
	rts

; void map_load(u16 level): in forced blank. The palettes, tiles and maps
; of the level's background for the camera set last, and the registers of
; BG1 and BG2.
map_load:
	php
	phb
	phd
	rep #$30
	lda 8,s
	tay
	pea map_dp
	pld
	sep #$20
	lda #$7F
	pha
	plb
	rep #$20
	phy
	jsr map_unqueue
	ply
	stz map_magic
	lda #1
	sta DNOW
	; The low part of the level and the Video Detail:
	tya
	asl a
	asl a
	tax
	lda.l map_level_low,x
	sec
	sbc #2
	sta map_ldelta
	sep #$20
	lda.l map_level_low+2,x
	sta map_lbank
	sta.b DLS+2
	rep #$20
	stz map_lowf
	lda #$8000
	sta map_dlim
	lda.l map_detail
	and #$00FF
	bne +
	lda #$8000
	sta map_lowf
	lda #$FFFF
	sta map_dlim
+
	; The record of the level:
	tya
	asl a
	asl a
	asl a
	asl a
	asl a
	clc
	adc #map_level_info
	sta DSRC
	sep #$20
	lda.b #:map_level_info
	sta.b DSRC+2
	rep #$20
	ldy #LI_WC
	lda [DSRC],y
	sta map_wc
	ldy #LI_HC
	lda [DSRC],y
	sta map_hc
	ldy #LI_CW
	lda [DSRC],y
	sta map_cw
	ldy #LI_CH
	lda [DSRC],y
	sta map_ch
	ldy #LI_DIR
	lda [DSRC],y
	sta map_dir
	sta DDIR
	sep #$20
	ldy #LI_DIR+2
	lda [DSRC],y
	sta map_dir+2
	sta.b DDIR+2
	ldy #LI_CBANK
	lda [DSRC],y
	sta map_cbank
	sta.b DCP+2
	sta.b DCP8+2
	sta.b DCPP+2
	ldy #LI_TEX+2
	lda [DSRC],y
	sta map_tex+2
	rep #$20
	ldy #LI_TEX
	lda [DSRC],y
	sta map_tex
	ldy #LI_NTX
	lda [DSRC],y
	and #$00FF
	sta map_ntx
	ldy #LI_NTY
	lda [DSRC],y
	and #$00FF
	sta map_nty
	ldy #LI_NTX2
	lda [DSRC],y
	and #$00FF
	sta map_ntx2
	ldy #LI_NTY2
	lda [DSRC],y
	and #$00FF
	sta map_nty2
	bit map_lowf                ; no second texture with Low detail
	bpl +
	stz map_ntx2
	stz map_nty2
+
	sep #$20
	lda map_ntx
	sta.l $004202
	lda map_nty
	sta.l $004203
	rep #$20
	nop
	nop
	nop
	nop
	lda.l $004216
	sta map_ntex1
	clc
	adc #1 + (PAL_TEX << 10)
	sta map_fglim
	; Tables in our RAM (for indexing with Y):
	ldx #0
-	lda.l map_pop,x
	sta map_popr,x
	inx
	inx
	cpx #256
	bcc -
	; 1 << n and its complement, the highest bit of every byte:
	sep #$20
	ldx #0
	lda #1
-	sta map_bit1,x
	eor #$FF
	sta map_nbit1,x
	eor #$FF
	asl a
	inx
	cpx #8
	bcc -
	rep #$20
	ldx #0
@hb:
	txa
	beq @hz
	ldy #0
-	lsr a
	beq +
	iny
	bra -
+	tya
	bra @hs
@hz:
	lda #$00FF
@hs:
	sep #$20
	sta map_high,x
	rep #$20
	inx
	cpx #256
	bcc @hb
	ldx #0
	ldy #0
-	lda.l map_bit,x
	and #$00FF
	sta map_bitw,y
	lda.l map_left,x
	and #$00FF
	sta map_leftw,y
	iny
	iny
	inx
	cpx #8
	bcc -
	ldy #LI_TBASE
	lda [DSRC],y
	sta map_tbase
	ldy #LI_SKYK
	lda [DSRC],y
	sta map_skyk
	lda #$FFFF
	sta map_crow
	ldy #LI_CHUNKS
	lda [DSRC],y
	sec
	sbc #$8000
	sta map_cdelta
	ldy #LI_NTEX
	lda [DSRC],y
	bit map_lowf                ; Low detail: the foreground's only
	bpl +
	lda map_ntex1
+	sta DT6                     ; texture tiles
	inc a
	sta map_cache0
	; The air tile and the texture tiles:
	stz map_zero
	ldx #30
-	stz map_zero,x
	dex
	dex
	bpl -
	lda #DMAQ_VRAM
	sta DQT
	lda #map_zero
	sta DQS
	sep #$20
	lda #$7F
	sta.b DQS+2
	rep #$20
	lda #32
	sta DQZ
	lda #VRAM_BG1_CHR
	sta DQV
	jsr map_queue
	lda map_tex
	sta DQS
	sep #$20
	lda map_tex+2
	sta.b DQS+2
	rep #$20
	lda DT6
	asl a
	asl a
	asl a
	asl a
	asl a
	sta DQZ
	lda #VRAM_BG1_CHR+16
	sta DQV
	jsr map_queue
	; Palettes 3-7 (the color 0 of each is transparent anyway), with Low
	; detail palette 3 only:
	ldy #LI_PAL
	lda [DSRC],y
	sta DQS
	sep #$20
	ldy #LI_PAL+2
	lda [DSRC],y
	sta.b DQS+2
	rep #$20
	lda #DMAQ_CGRAM
	sta DQT
	lda #160
	bit map_lowf
	bpl +
	lda #32
+	sta DQZ
	lda #PAL_TEX*16
	sta DQV
	jsr map_queue
	; The sky:
	ldy #LI_SKY
	lda [DSRC],y
	and #$00FF
	asl a
	asl a
	asl a
	asl a
	clc
	adc #map_sky_info
	sta DSRC
	sep #$20
	lda.b #:map_sky_info
	sta.b DSRC+2
	ldy #SI_TILES+2
	lda [DSRC],y
	sta.b DQS+2
	rep #$20
	ldy #SI_TILES
	lda [DSRC],y
	sta DQS
	ldy #SI_TSIZE
	lda [DSRC],y
	sta DQZ
	lda #DMAQ_VRAM
	sta DQT
	lda #VRAM_BG2_CHR
	sta DQV
	jsr map_queue
	ldy #SI_PAL
	lda [DSRC],y
	sta DQS
	sep #$20
	ldy #SI_PAL+2
	lda [DSRC],y
	sta.b DQS+2
	rep #$20
	lda #DMAQ_CGRAM
	sta DQT
	lda #64
	sta DQZ
	lda #16
	sta DQV
	jsr map_queue
	; BG2's 32 columns: column c is the pattern's c % ncol.
	ldy #SI_NCOL
	lda [DSRC],y
	and #$00FF
	sta DT7
	ldy #SI_COLS
	lda [DSRC],y
	sta DT8
	sep #$20
	ldy #SI_COLS+2
	lda [DSRC],y
	sta.b DQS+2
	rep #$20
	lda #DMAQ_VRAM32
	sta DQT
	lda #56
	sta DQZ
	stz DT0                     ; map column
	stz DT1                     ; pattern column
-	lda DT1
	asl a
	asl a
	asl a
	sta DT9
	asl a
	asl a
	asl a
	sec
	sbc DT9                     ; * 56
	clc
	adc DT8
	sta DQS
	lda DT0
	clc
	adc #VRAM_BG2_MAP
	sta DQV
	jsr map_queue
	inc DT1
	lda DT1
	cmp DT7
	bcc +
	stz DT1
+	inc DT0
	lda DT0
	cmp #32
	bcc -
	; The registers of BG1 and BG2:
	sep #$20
	lda #$09                    ; mode 1, BG3 in front
	sta.l $002105
	lda #$30                    ; BG1 tiles at $0000, BG2 at $3000
	sta.l $00210B
	lda.b #(VRAM_BG1_MAP >> 8) | 1  ; 64x32
	sta.l $002107
	lda.b #(VRAM_BG2_MAP >> 8)      ; 32x32
	sta.l $002108
	lda #$03
	sta.l $00212C
	rep #$20
	; The cells around the camera, all of them:
	jsr map_free_init
	lda #0
	sta map_stat_short
	sta map_stat_nofree
	sta map_stat_resets
	lda #MAP_MAGIC0
	sta map_magic
	lda #MAP_MAGIC1
	sta map_magic+2
	jsr map_scroll
	jsr map_reset
-	jsr map_work
	jsr map_flush
	lda map_jn
	sec
	sbc map_ndone
	bne -
	jsr map_tidy
	stz DNOW
	stz map_stat_short
	stz map_stat_nofree
	stz map_stat_resets
	; (the minimum of free tiles counts from here)
	lda map_freesp
	sta map_stat_minfree
map_load_end:
	rep #$30
	pld
	plb
	plp
	rtl

.ENDS
