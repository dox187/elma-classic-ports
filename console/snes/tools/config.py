"""Constants shared by the converters (the same as in src/core.h)."""

# The original game draws 48 pixels a meter on its 640x480 picture; the
# SNES shows the same width of the level on its 256 pixels:
SCALE = 0.4
PX_PER_M = 48 * SCALE          # 19.2

SCREEN_W, SCREEN_H = 256, 224

# VRAM during a level (word addresses):
VRAM_BG1_CHR = 0x0000          # ground: 704 tiles of 4 bits
VRAM_BG2_MAP = 0x2C00          # sky: 32x32
VRAM_BG2_CHR = 0x3000          # sky: 512 tiles of 4 bits
VRAM_BG3_CHR = 0x5000          # map view: 128 tiles of 2 bits
VRAM_BG3_MAP = 0x5400          # 32x32
VRAM_BG1_MAP = 0x5800          # 64x32
VRAM_OBJ = 0x6000              # sprites: 512 tiles of 4 bits

BG1_TILES = 704
BG2_TILES = 512
BG3_TILES = 128
OBJ_TILES = 512

# The banks of the ROM (LoROM): a section of data fits in one.
BANK_SIZE = 0x8000
