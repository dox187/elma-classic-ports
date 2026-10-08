# The physics (src/phys.asm): its constants for PHYS_HZ steps a second, its
# tables, and the lines, grid and objects of the levels (tools/gen_phys.py).
#
#   make PHYS_HZ=80           steps a second (80, or 60 for a test: the
#                             original's physics is not stable at 60)
#   make phys-check           the C description of the physics against the
#                             original's on the host (test/physcheck)

PHYS_HZ ?= 80
PHYS_GEN = $(GEN)/phys_const.h $(GEN)/phys_const.inc $(GEN)/phys_hz.h \
	$(GEN)/phys_tables.h $(GEN)/phys_tables.asm $(GEN)/phys_levels.asm
GEN_ASM += $(GEN)/phys_tables.asm $(GEN)/phys_levels.asm
GEN_H += $(GEN)/phys_const.h $(GEN)/phys_const.inc $(GEN)/phys_hz.h

# Rewritten only when PHYS_HZ changes:
$(GEN)/phys_hz_value: FORCE
	@mkdir -p $(GEN)
	@echo '$(PHYS_HZ)' | cmp -s - $@ || echo '$(PHYS_HZ)' > $@

$(PHYS_GEN) &: tools/gen_phys.py tools/elmadata.py $(GEN)/data_names $(GEN)/phys_hz_value
	$(PYTHON) tools/gen_phys.py $(ELMA_RES) $(GEN) --hz $(PHYS_HZ)

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

phys-check: $(PHYS_TEST)/physcheck $(PHYS_TEST)/levdump
	$(PHYS_TEST)/physcheck $(GEN) $(PHYS_TEST)/levdump -f test/physcases.txt > $(PHYS_TEST)/physcheck.txt
	$(PYTHON) test/physsum.py $(PHYS_TEST)/physcheck.txt

.PHONY: phys-check
