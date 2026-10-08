# The menus: pictures and font from elma.res (tools/gen_ui.py).
GEN_ASM += $(GEN)/ui_data.asm
GEN_H += $(GEN)/ui_data.h

$(GEN)/ui_data.asm $(GEN)/ui_data.h &: tools/gen_ui.py tools/elmadata.py \
		$(GEN)/data_names
	$(PYTHON) tools/gen_ui.py $(ELMA_RES) $(GEN)
