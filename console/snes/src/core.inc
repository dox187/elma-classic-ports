; Constants shared by the sources in assembly (core.h has the same for C).

; Entries of the DMA queue of a frame and of the queue of register writes:
.DEFINE DMAQ_MAX 48
.DEFINE REGQ_MAX 32
; Queue cost in byte-times, excluding the fixed 544-byte OAM transfer.
; Includes 96 byte-times for each transfer's setup, leaving room for the
; remaining NMI register writes within a 224-line NTSC vertical blank.
.DEFINE DMAQ_ENTRY_COST 96
.DEFINE DMAQ_COST_MAX 5000
; Types of the entries of the DMA queue:
.DEFINE DMAQ_VRAM   0           ; VRAM, the address grows by a word
.DEFINE DMAQ_VRAM32 1           ; VRAM, the address grows by 32 words (a column)
.DEFINE DMAQ_CGRAM  2

; VRAM during a level (word addresses):
.DEFINE VRAM_BG1_CHR  $0000     ; ground: 704 tiles of 4 bits
.DEFINE VRAM_BG2_MAP  $2C00     ; sky: 32x32
.DEFINE VRAM_BG2_CHR  $3000     ; sky: 512 tiles of 4 bits
.DEFINE VRAM_BG3_CHR  $5000     ; map view: 128 tiles of 2 bits
.DEFINE VRAM_BG3_MAP  $5400     ; 32x32
.DEFINE VRAM_BG1_MAP  $5800     ; 64x32
.DEFINE VRAM_OBJ      $6000     ; sprites: 512 tiles of 4 bits (two tables)

; Joypad buttons (core_pad, the bits of JOY1):
.DEFINE JOY_R      $0010
.DEFINE JOY_L      $0020
.DEFINE JOY_X      $0040
.DEFINE JOY_A      $0080
.DEFINE JOY_RIGHT  $0100
.DEFINE JOY_LEFT   $0200
.DEFINE JOY_DOWN   $0400
.DEFINE JOY_UP     $0800
.DEFINE JOY_START  $1000
.DEFINE JOY_SELECT $2000
.DEFINE JOY_Y      $4000
.DEFINE JOY_B      $8000
