# The list of the internal levels and their geometry (tools/gen_levels.py).
GEN_ASM += $(GEN)/levels.asm
GEN_H += $(GEN)/levels.h

$(GEN)/levels.asm $(GEN)/levels.h &: tools/gen_levels.py tools/elmadata.py \
		tools/levgeom.py tools/config.py $(GEN)/data_names
	$(PYTHON) tools/gen_levels.py $(ELMA_RES) $(GEN)
