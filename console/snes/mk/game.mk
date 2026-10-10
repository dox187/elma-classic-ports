# The test ROM of a whole level played with scripted keys (test/play.py).
TEST_ROMS += $(BUILD)/test_play.sfc

# Independent arithmetic checks of presentation interpolation.
TEST_ROMS += $(BUILD)/test_render.sfc
render-check: $(BUILD)/test_render.sfc
	$(PYTHON) test/render_check.py --rom $< --out $(BUILD)/render
.PHONY: render-check

# Test adapters expose the assembly carry and direct-page contracts.
$(BUILD)/test_render.sfc: $(OBJDIR)/coreframe_wrapper.obj
$(OBJDIR)/coreframe_wrapper.obj: test/coreframe_wrapper.asm $(HEADERS) | check-tools
	@mkdir -p $(OBJDIR)
	$(AS) $(ASFLAGS) -o $@ $<

coreframe-check: $(BUILD)/test_render.sfc
	$(PYTHON) test/coreframe_check.py --rom $< --out $(BUILD)/coreframe
.PHONY: coreframe-check
