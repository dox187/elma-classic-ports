# The NES version: elma.nes from the levels of an elma.res of the game.
#
#   make ELMA_RES=/path/to/elma.res
#
# Needs the llvm-mos SDK (https://github.com/llvm-mos/llvm-mos-sdk) and
# Python 3 with numpy and Pillow.

ELMA_RES ?= ../elma.res
LEVELS ?=
# Steps of the physics in 60 frames: 60 is a step a frame, 50 is longer
# steps that take less time a second.
PHYS_HZ ?= 60
PYTHON ?= python3
# The compiler of the SDK, from LLVM_MOS, the PATH or ~/.local/share/llvm-mos:
ifdef LLVM_MOS
CC = $(LLVM_MOS)/bin/mos-nes-mmc3-clang
else
CC := $(or $(shell command -v mos-nes-mmc3-clang 2>/dev/null),$(HOME)/.local/share/llvm-mos/bin/mos-nes-mmc3-clang)
endif
CFLAGS = -Os -Wall -Isrc -Ibuild -mlto-zp=32 -DPHYSICS_ASM
BUILD = build

PHYSICS ?= src/physics.S
SOURCES = $(addprefix src/,main.c game.c map.c menu.c fixmath.c \
	far.c segs.c save.c sound.c video.c mul.s) $(PHYSICS)
GENERATED = $(addprefix $(BUILD)/,levels.c sprites.c levdata.s chr.s)
HEADERS = $(BUILD)/physconst.h $(BUILD)/chrmap.h

all: $(BUILD)/elma.nes

$(BUILD)/elma.nes: $(SOURCES) $(wildcard src/*.h src/*.inc) $(GENERATED) $(HEADERS)
	$(CC) $(CFLAGS) -o $@ $(SOURCES) $(GENERATED) -lneslib

# Remade when PHYS_HZ changes:
$(BUILD)/physconst.h: tools/physconst.py $(BUILD)/phys_hz_$(PHYS_HZ)
	$(PYTHON) tools/physconst.py $@ $(PHYS_HZ)

$(BUILD)/phys_hz_$(PHYS_HZ):
	mkdir -p $(BUILD)
	rm -f $(BUILD)/phys_hz_*
	touch $@

$(GENERATED) $(BUILD)/chrmap.h &: $(wildcard tools/*.py) $(wildcard $(ELMA_RES)) $(LEVELS)
	$(PYTHON) tools/build.py --res $(ELMA_RES) $(if $(LEVELS),--lev $(LEVELS)) --out $(BUILD)

clean:
	rm -rf $(BUILD)

.PHONY: all clean
