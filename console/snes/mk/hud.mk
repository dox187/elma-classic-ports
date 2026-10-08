# The time digits and the view box (tools/gen_hud.py, src/hud.asm).
GEN_ASM += $(GEN)/hud.asm
GEN_H += $(GEN)/hud.inc

$(GEN)/hud.asm $(GEN)/hud.inc $(GEN)/hud_test.asm &: tools/gen_hud.py \
		tools/elmadata.py tools/levgeom.py tools/config.py tools/lgr.py \
		$(GEN)/data_names
	$(PYTHON) tools/gen_hud.py $(ELMA_RES) $(ELMA_LGR) $(GEN) --test

