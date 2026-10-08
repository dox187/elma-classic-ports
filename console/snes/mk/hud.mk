# The time digits and the view box (tools/gen_hud.py, src/hud.asm).
GEN_ASM += $(GEN)/hud.asm
GEN_H += $(GEN)/hud.inc
TEST_ROMS += $(BUILD)/test_hud.sfc

$(GEN)/hud.asm $(GEN)/hud.inc $(GEN)/hud_test.asm &: tools/gen_hud.py \
		tools/elmadata.py tools/levgeom.py tools/config.py tools/lgr.py \
		$(GEN)/data_names
	$(PYTHON) tools/gen_hud.py $(ELMA_RES) $(ELMA_LGR) $(GEN) --test

# The test ROM brings its data (the levels and the path of its fake bike)
# and, until the physics (src/phys.h) is there, a stand-in of the variables
# of the physics that the HUD reads.
HUD_PHYS_STUB = $(if $(wildcard src/phys.h),,$(OBJDIR)/hud_physstub.obj)
$(BUILD)/test_hud.sfc: $(OBJDIR)/gen_hud_test.obj $(HUD_PHYS_STUB)
$(OBJDIR)/test_hud.obj: CFLAGS += $(if $(wildcard src/phys.h),-DHAVE_PHYS)

$(OBJDIR)/hud_physstub.obj: test/hud_physstub.asm $(HEADERS) | check-tools
	@mkdir -p $(OBJDIR)
	$(AS) $(ASFLAGS) -o $@ $<
