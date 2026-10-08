# The background of the levels: ground, grass and pictures of BG1, the sky
# of BG2 (tools/gen_map.py, about a minute with 4 processes).
GEN_ASM += $(GEN)/map_data.asm
GEN_H += $(GEN)/map_data.h
MAP_JOBS ?= 4

$(GEN)/map_data.asm $(GEN)/map_data.h &: tools/gen_map.py tools/mapmodel.py \
		tools/tileq.py tools/elmadata.py tools/levgeom.py tools/lgr.py \
		$(GEN)/data_names
	$(PYTHON) tools/gen_map.py $(ELMA_RES) $(ELMA_LGR) $(GEN) -j $(MAP_JOBS)
