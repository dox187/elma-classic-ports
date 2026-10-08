# The SNES version: build/elma_ntsc.sfc and build/elma_pal.sfc from the
# levels of an elma.res and the pictures of an LGR file of the game, or
# elma_sw_ntsc.sfc and elma_sw_pal.sfc from the data of the shareware game.
#
#   make ELMA_RES=/path/to/elma.res ELMA_LGR=/path/to/default.lgr
#
# Needs PVSnesLib 4.6 (https://github.com/alekmaul/pvsneslib), its compiler,
# assembler and linker, and Python 3 with numpy and Pillow.

.DEFAULT_GOAL := all

ELMA_RES ?= ../../elma.res
# The LGR file of the original game, by default lgr/default.lgr next to
# elma.res (in any case of letters):
ELMA_LGR ?= $(firstword $(shell find $(or $(dir $(ELMA_RES)),.) -maxdepth 2 \
	-ipath '*/lgr/default.lgr' 2>/dev/null))
# The TV systems to build a ROM for: ntsc, pal or both. The program is the
# same, only the region of the header differs.
TV ?= ntsc pal
PYTHON ?= python3
# 32 KB banks of the ROM (LoROM, FastROM) and the size in its header:
ROMBANKS ?= 128
ROMSIZE = $(if $(filter 128,$(ROMBANKS)),$$0C,$(if $(filter 64,$(ROMBANKS)),$$0B,$$0A))

# PVSnesLib, from PVSNESLIB_HOME or a few usual places:
PVSNESLIB_HOME ?= $(firstword $(wildcard \
	$(HOME)/pvsneslib $(HOME)/.local/share/pvsneslib \
	$(HOME)/.local/share/elma-snes/pvsneslib-4.6.0/pvsneslib /opt/pvsneslib))
DEVKIT = $(PVSNESLIB_HOME)/devkitsnes
CC = $(DEVKIT)/bin/816-tcc
OPT = $(DEVKIT)/tools/816-opt
AS = $(DEVKIT)/bin/wla-65816
LD = $(DEVKIT)/bin/wlalink
LIBDIR = $(PVSNESLIB_HOME)/pvsneslib/lib/LoROM_FastROM

BUILD = build
OBJDIR = $(BUILD)/obj
GEN = $(BUILD)/gen
VERSION := $(strip $(file <VERSION))

CFLAGS = -Wall -F -Isrc -I$(GEN) -I$(PVSNESLIB_HOME)/pvsneslib/include \
	-I$(DEVKIT)/include
# The assembler, on the compiler's output (-d as PVSnesLib needs it) and on
# the sources written in assembly:
ASFLAGS_C = -d -s -x -I$(GEN) -Isrc
ASFLAGS = -h -s -x -I$(GEN) -Isrc

# Sources of the game: every src/*.c and src/*.asm. main.c only goes into
# the game, the test ROMs (test/snes_*.c) bring their own main().
CSRC = $(wildcard src/*.c)
SSRC = $(wildcard src/*.asm)
OBJS = $(patsubst src/%.c,$(OBJDIR)/%.obj,$(CSRC)) \
	$(patsubst src/%.asm,$(OBJDIR)/%.obj,$(SSRC))
LIBOBJS = $(wildcard $(LIBDIR)/*.obj)

# Generated data and headers; the parts (mk/*.mk) add to these:
GEN_ASM =
GEN_H = $(GEN)/hdr.asm $(GEN)/version.h $(GEN)/version.inc
TEST_ROMS =
include $(wildcard mk/*.mk)
GENOBJS = $(patsubst $(GEN)/%.asm,$(OBJDIR)/gen_%.obj,$(GEN_ASM))
HEADERS = $(wildcard src/*.h src/*.inc) $(GEN_H)

# The ROMs, named by the version that the elma.res is of and by the TV
# system:
EDITION := $(if $(wildcard $(ELMA_RES)),$(shell $(PYTHON) tools/elmadata.py $(ELMA_RES)))
NAME = $(if $(filter shareware,$(EDITION)),elma_sw,elma)

all: $(foreach tv,$(TV),$(BUILD)/$(NAME)_$(tv).sfc)

check-tools:
	@test -x $(CC) || { echo "PVSnesLib not found: set PVSNESLIB_HOME"; exit 1; }
	@test -f "$(ELMA_RES)" || { echo "elma.res not found: set ELMA_RES"; exit 1; }
	@test -f "$(ELMA_LGR)" || { echo "default.lgr not found: set ELMA_LGR"; exit 1; }

$(BUILD)/elma.sfc: $(OBJS) $(GENOBJS)
	$(call link,$^)

# The ROM of a TV system: the region of the header, and its checksum.
$(BUILD)/$(NAME)_%.sfc: $(BUILD)/elma.sfc tools/romfix.py
	$(PYTHON) tools/romfix.py $< $@ --tv $*

# A test ROM: test/snes_NAME.c with its main(), and the game without its own.
$(BUILD)/test_%.sfc: $(OBJDIR)/test_%.obj $(filter-out $(OBJDIR)/main.obj,$(OBJS)) $(GENOBJS)
	$(call link,$^)
	$(PYTHON) tools/romfix.py $@ $@ --tv ntsc

tests: $(TEST_ROMS)

define link
	@mkdir -p $(dir $@)
	@echo '[objects]' > $@.link
	@for o in $(1) $(LIBOBJS); do echo $$o >> $@.link; done
	$(LD) -d -s -v -A -c -L $(LIBDIR) $@.link $@ > $@.log || { cat $@.log; exit 1; }
	@grep -E "ROM:|RAM:" $@.log
endef

# C: 816-tcc, its optimizer, then the assembler.
$(OBJDIR)/%.obj: src/%.c $(HEADERS) | check-tools
	@mkdir -p $(OBJDIR)
	$(CC) $(CFLAGS) -c $< -o $(OBJDIR)/$*.ps
	$(OPT) -i $(OBJDIR)/$*.ps -o $(OBJDIR)/$*.s
	$(AS) $(ASFLAGS_C) -o $@ $(OBJDIR)/$*.s

$(OBJDIR)/test_%.obj: test/snes_%.c $(HEADERS) | check-tools
	@mkdir -p $(OBJDIR)
	$(CC) $(CFLAGS) -c $< -o $(OBJDIR)/test_$*.ps
	$(OPT) -i $(OBJDIR)/test_$*.ps -o $(OBJDIR)/test_$*.s
	$(AS) $(ASFLAGS_C) -o $@ $(OBJDIR)/test_$*.s

$(OBJDIR)/%.obj: src/%.asm $(HEADERS) | check-tools
	@mkdir -p $(OBJDIR)
	$(AS) $(ASFLAGS) -o $@ $<

$(OBJDIR)/gen_%.obj: $(GEN)/%.asm $(HEADERS) | check-tools
	@mkdir -p $(OBJDIR)
	$(AS) $(ASFLAGS) -o $@ $<

# The memory map and header, included by every source:
$(GEN)/hdr.asm: src/hdr.asm.in Makefile
	@mkdir -p $(GEN)
	sed -e 's/@ROMBANKS@/$(ROMBANKS)/' -e 's/@ROMSIZE@/$(ROMSIZE)/' $< > $@

$(GEN)/version.h $(GEN)/version.inc &: VERSION
	@mkdir -p $(GEN)
	echo '#define ELMA_VERSION "$(VERSION)"' > $(GEN)/version.h
	echo '.define ELMA_VERSION "$(VERSION)"' > $(GEN)/version.inc

# The names of the data, rewritten only when they change: another elma.res
# or LGR is converted again even if it is older. Generators depend on it.
$(GEN)/data_names: FORCE
	@mkdir -p $(GEN)
	@echo '$(abspath $(ELMA_RES)) $(abspath $(ELMA_LGR))' | cmp -s - $@ || \
		echo '$(abspath $(ELMA_RES)) $(abspath $(ELMA_LGR))' > $@

FORCE:

clean:
	rm -rf $(BUILD)

.PHONY: all tests check-tools clean FORCE
.SECONDARY:
