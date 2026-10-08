# The physics (src/phys.asm): its constants for PHYS_HZ steps a second, its
# tables, and the lines, grid and objects of the levels (tools/gen_phys.py).
#
#   make PHYS_HZ=80           steps a second (80, or 60 for a test: the
#                             original's physics is not stable at 60)
#   make phys-check           the C description of the physics against the
#                             original's on the host (test/physcheck), and
#                             the assembly against the C to the bit in Mesen

PHYS_HZ ?= 80
PHYS_GEN = $(GEN)/phys_const.h $(GEN)/phys_const.inc $(GEN)/phys_hz.h \
	$(GEN)/phys_tables.h $(GEN)/phys_tables.asm $(GEN)/phys_levels.asm
GEN_ASM += $(GEN)/phys_tables.asm $(GEN)/phys_levels.asm
GEN_H += $(GEN)/phys_const.h $(GEN)/phys_const.inc $(GEN)/phys_hz.h $(GEN)/phys_testcases.h
TEST_ROMS += $(BUILD)/test_phys.sfc

# Rewritten only when PHYS_HZ changes:
$(GEN)/phys_hz_value: FORCE
	@mkdir -p $(GEN)
	@echo '$(PHYS_HZ)' | cmp -s - $@ || echo '$(PHYS_HZ)' > $@

$(PHYS_GEN) &: tools/gen_phys.py tools/elmadata.py $(GEN)/data_names $(GEN)/phys_hz_value
	$(PYTHON) tools/gen_phys.py $(ELMA_RES) $(GEN) --hz $(PHYS_HZ)

# The cases of the test ROM (test/snes_phys.c):
$(GEN)/phys_testcases.h: test/physcases.txt test/physrom.py
	@mkdir -p $(GEN)
	$(PYTHON) test/physrom.py gen $< $@

# The tests on the host: the original's physics (src/*.CPP of the repository)
# and the C description, compared with the same keys.
HOSTCC ?= cc
HOSTCXX ?= c++
PHYS_TEST = $(BUILD)/host
PC_SRC = $(addprefix ../../src/,LEPTET.CPP BEALLIT.CPP UTKOZES.CPP UTKOZES2.CPP SZAKASZ.CPP VEKT2.CPP)

$(PHYS_TEST)/phys_spec.o: test/phys_spec.c test/phys_spec.h $(GEN)/phys_const.h $(GEN)/phys_tables.h
	@mkdir -p $(PHYS_TEST)
	$(HOSTCC) -O2 -Wall -c -Itest -I$(GEN) -o $@ $<

$(PHYS_TEST)/physcheck: test/physcheck.cpp test/pcphys/pcphys.cpp test/pcphys/*.h $(PC_SRC) \
		$(PHYS_TEST)/phys_spec.o
	@mkdir -p $(PHYS_TEST)
	$(HOSTCXX) -O2 -w -fpermissive -Itest -Itest/pcphys -I$(GEN) -o $@ test/physcheck.cpp \
		test/pcphys/pcphys.cpp $(PC_SRC) $(PHYS_TEST)/phys_spec.o

$(PHYS_TEST)/levdump: test/levdump.py tools/elmadata.py $(GEN)/data_names
	$(PYTHON) test/levdump.py $(ELMA_RES) $@
	@touch $@

# The asm against the C: test/snes_phys.c steps the physics in the ROM with
# scripted keys and dumps the state; test/physrom.py compares the dumps with
# the C description (test/physdump on the host).
$(PHYS_TEST)/physdump: test/physdump.c $(PHYS_TEST)/phys_spec.o test/phys_spec.h
	$(HOSTCC) -O2 -Wall -Itest -I$(GEN) -o $@ test/physdump.c $(PHYS_TEST)/phys_spec.o

phys-check: $(PHYS_TEST)/physcheck $(PHYS_TEST)/levdump $(PHYS_TEST)/physdump $(BUILD)/test_phys.sfc
	$(PHYS_TEST)/physcheck $(GEN) $(PHYS_TEST)/levdump -f test/physcases.txt > $(PHYS_TEST)/physcheck.txt
	$(PYTHON) test/physsum.py $(PHYS_TEST)/physcheck.txt
	$(PYTHON) test/physrom.py run $(BUILD)/test_phys.sfc $(PHYS_TEST)/physdump $(GEN) \
		test/physcases.txt --out $(PHYS_TEST)/rom

.PHONY: phys-check
