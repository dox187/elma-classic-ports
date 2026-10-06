# The NES version: elma.nes from the levels of an elma.res of the game, or
# elma_sw.nes, the shareware version, from that of the shareware game.
#
#   make ELMA_RES=/path/to/elma.res
#
# Needs the llvm-mos SDK (https://github.com/llvm-mos/llvm-mos-sdk) and
# Python 3 with numpy and Pillow.

ELMA_RES ?= ../elma.res
LEVELS ?=
# Steps of the physics in 60 frames: 60 is a step a frame, which the NES
# keeps up with at about 80 %, 50 is longer steps that it mostly keeps up
# with.
PHYS_HZ ?= 50
PYTHON ?= python3
# The compiler of the SDK, from LLVM_MOS, the PATH or ~/.local/share/llvm-mos:
ifdef LLVM_MOS
CC = $(LLVM_MOS)/bin/mos-nes-mmc3-clang
else
CC := $(or $(shell command -v mos-nes-mmc3-clang 2>/dev/null),$(HOME)/.local/share/llvm-mos/bin/mos-nes-mmc3-clang)
endif
CFLAGS = -Os -Wall -Isrc -Ibuild -mlto-zp=32 -DPHYSICS_ASM
BUILD = build
# The simulator of the SDK, for make check, and a compiler for the host:
MOS_BIN = $(dir $(CC))
HOSTCC ?= cc

PHYSICS ?= src/physics.S
SOURCES = $(addprefix src/,main.c game.c map.c menu.c fixmath.c \
	far.c segs.c save.c sound.c video.c mul.s) $(PHYSICS)
GENERATED = $(addprefix $(BUILD)/,levels.c sprites.c levdata.s chr.s)
HEADERS = $(BUILD)/physconst.h $(BUILD)/chrmap.h
# The ROM, named by the version that the elma.res is of:
EDITION := $(if $(wildcard $(ELMA_RES)),$(shell $(PYTHON) tools/elmadata.py $(ELMA_RES)))
ROM = $(if $(filter shareware,$(EDITION)),elma_sw.nes,elma.nes)

all: $(BUILD)/$(ROM)

$(BUILD)/$(ROM): $(SOURCES) $(wildcard src/*.h src/*.inc) $(GENERATED) $(HEADERS)
	$(CC) $(CFLAGS) -o $@ $(SOURCES) $(GENERATED) -lneslib

# Remade when PHYS_HZ changes:
$(BUILD)/physconst.h: tools/physconst.py $(BUILD)/phys_hz_$(PHYS_HZ)
	$(PYTHON) tools/physconst.py $@ $(PHYS_HZ)

$(BUILD)/phys_hz_$(PHYS_HZ):
	mkdir -p $(BUILD)
	rm -f $(BUILD)/phys_hz_*
	touch $@

$(GENERATED) $(BUILD)/chrmap.h &: $(wildcard tools/*.py) $(wildcard $(ELMA_RES)) $(LEVELS) \
		$(BUILD)/data_names
	$(PYTHON) tools/build.py --res $(ELMA_RES) $(if $(LEVELS),--lev $(LEVELS)) --out $(BUILD)

# The physics on the first level: the fixed point physics against the
# game's on the host, then physics.S against physics.c to the bit and its
# cycles in the simulator.
# The names of the data, rewritten only when they change: another elma.res
# is converted again even if it is older.
$(BUILD)/data_names: FORCE
	@mkdir -p $(BUILD)
	@echo '$(abspath $(ELMA_RES)) $(LEVELS)' | cmp -s - $@ || \
		echo '$(abspath $(ELMA_RES)) $(LEVELS)' > $@

FORCE:

check: $(BUILD)/physconst.h
	$(PYTHON) test/levtext.py $(ELMA_RES) 1 > $(BUILD)/level1.txt
	$(PYTHON) test/simlines.py $(BUILD)/level1.txt > $(BUILD)/simlines.h
	$(HOSTCC) -O2 -Isrc -I$(BUILD) -o $(BUILD)/physcmp test/physcmp.c test/refphys.c src/physics.c src/fixmath.c -lm
	$(BUILD)/physcmp $(BUILD)/level1.txt "G300 N60 B60 G200" | tail -3
	$(MOS_BIN)mos-sim-clang -O2 -Isrc -I$(BUILD) -DBike=RBike -Dph_init=rph_init \
		-Dph_step=rph_step -Dph_turn=rph_turn -c -o $(BUILD)/physics_c.o src/physics.c
	$(MOS_BIN)mos-sim-clang -O2 -mlto-zp=24 -Isrc -I$(BUILD) -o $(BUILD)/asmcmp test/asmcmp.c \
		$(BUILD)/physics_c.o src/physics.S src/mul.s src/fixmath.c
	$(MOS_BIN)mos-sim $(BUILD)/asmcmp
	$(MOS_BIN)mos-sim-clang -O2 -Isrc -I$(BUILD) -o $(BUILD)/bench test/bench.c src/physics.S \
		src/mul.s src/fixmath.c
	$(MOS_BIN)mos-sim $(BUILD)/bench

clean:
	rm -rf $(BUILD)

.PHONY: all check clean FORCE
