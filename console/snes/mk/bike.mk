# The sprites of the bike, the rider and the objects, and the tables of
# their drawing (tools/gen_bike.py). The animation of the objects follows
# PHYS_HZ of src/phys.h (60 without it).
GEN_ASM += $(GEN)/bike_data.asm
GEN_H += $(GEN)/bike_data.h $(GEN)/bike_data.inc
TEST_ROMS += $(BUILD)/test_bike.sfc

$(GEN)/bike_data.asm $(GEN)/bike_data.h $(GEN)/bike_data.inc &: tools/gen_bike.py \
		tools/bikemodel.py tools/lgr.py tools/config.py $(GEN)/data_names \
		$(wildcard src/phys.h)
	$(PYTHON) tools/gen_bike.py $(ELMA_LGR) $(GEN) src/phys.h

# The test ROM: poses of the bike and objects around it (test/bike_poses.py).
$(OBJDIR)/test_bike.obj: $(GEN)/bike_poses.h

$(GEN)/bike_poses.h: test/bike_poses.py tools/bikemodel.py tools/levgeom.py \
		tools/elmadata.py $(GEN)/data_names
	$(PYTHON) test/bike_poses.py $(ELMA_RES) $@
