GBDK_HOME ?= $(CURDIR)/.toolchain/gbdk
LCC := $(GBDK_HOME)/bin/lcc
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
ELMA_RES ?= ../../elma.res
ELMA_LGR ?= ../../lgr/default.lgr
PHYS_HZ ?= 30
DAMPER ?= exponential
GAME_ROM ?= build/elma-gbc.gbc
GEN := build/gen
FLAGS := -msm83:gb -Wf--opt-code-size -Wf--max-allocs-per-node -Wf100000 -Wm-yC -Wm-yt0x1A -Wm-ya16 -Wm-yoA -Wm-ynELMA-GBC -Wl-m -Wl-j -I$(GEN) -Isrc
PHYS_ASM := $(filter-out src/physics_mul16.s,$(wildcard src/physics_*.s))

.PHONY: all bootstrap assets check clean
all: $(GAME_ROM) build/elma-gbc-viewer.gbc build/physics-probe.gbc

bootstrap:
	bash tools/bootstrap.sh

# FORCE is intentional: changing the input paths must invalidate generated data.
.PHONY: FORCE
FORCE:

assets: FORCE
	$(PYTHON) tools/assets.py --res "$(ELMA_RES)" --lgr "$(ELMA_LGR)" --out $(GEN)
	$(PYTHON) tools/physics_constants.py $(GEN)
	$(PYTHON) tools/physics_level.py --res "$(ELMA_RES)" --out $(GEN) --hz $(PHYS_HZ) --damper $(DAMPER)
	$(PYTHON) tools/levels.py --res "$(ELMA_RES)" --lgr "$(ELMA_LGR)" --out $(GEN)
	$(PYTHON) tools/menu_assets.py --res "$(ELMA_RES)" --out $(GEN)
	$(PYTHON) tools/bike_frames.py --lgr "$(ELMA_LGR)" --out $(GEN)
	$(PYTHON) tools/bike_frames16.py --source $(GEN) --out $(GEN)
	$(PYTHON) tools/mul_table.py --out $(GEN)
	$(PYTHON) tools/scale_table.py --out $(GEN)
	$(PYTHON) tools/physics_sine.py --out $(GEN)
	$(PYTHON) tools/math32_coefficients.py --constants $(GEN)/riding_constants.h --out $(GEN)

$(GAME_ROM): assets src/video.s src/play.c src/runtime.h src/bike_render.c src/physics.c src/physics_core.c src/physics_contacts.c src/physics_collision.c src/physics_math.c src/physics_math32.c $(PHYS_ASM)
	$(PYTHON) tools/build.py --sdk "$(GBDK_HOME)" --gen $(GEN) --out $@

build/elma-gbc-viewer.gbc: assets src/main.c
	$(LCC) $(filter-out -Wm-yt0x1A -Wm-ya16,$(FLAGS)) -Wm-yt0x19 -o $@ src/main.c $(GEN)/world_*.c $(GEN)/patterns.c $(GEN)/assets.c

build/physics-probe.gbc: assets src/physics_probe.c src/suspension.c src/suspension.h src/mul16.s
	$(LCC) $(filter-out -Wm-yt0x1A -Wm-ya16,$(FLAGS)) -Wm-yt0x19 -o $@ src/physics_probe.c src/suspension.c src/mul16.s

check: all
	$(PYTHON) test/check.py --gen $(GEN)
	$(PYTHON) test/check_riding_math.py
	$(PYTHON) test/check_riding_mul9.py
	$(PYTHON) test/check_riding_division.py
	$(PYTHON) test/check_riding_sqrt.py
	$(PYTHON) test/check_riding_bounds.py
	$(PYTHON) test/check_riding_math32.py
	$(PYTHON) test/check_physics_export.py --gen $(GEN)
	$(PYTHON) test/check_physics_move.py
	$(PYTHON) test/check_physics_anchor.py
	$(PYTHON) test/check_physics_contact_sign.py
	$(PYTHON) test/check_physics_recip.py
	$(PYTHON) test/check_physics_shift.py
	$(PYTHON) test/check_physics_rider_reject.py --gen $(GEN)
	$(PYTHON) test/check_physics_sine.py
	$(PYTHON) test/check_physics_coefficients.py --constants $(GEN)/riding_constants.h
	$(PYTHON) test/check_physics_sweep.py --gen $(GEN)
	$(PYTHON) test/check_physics_levels.py --res "$(ELMA_RES)" --gen $(GEN)
	$(PYTHON) test/check_physics_levels.py --res "$(ELMA_RES)" --gen $(GEN) --out build/physics-high-bank-check --high-bank
	$(PYTHON) test/check_physics_trace.py --res "$(ELMA_RES)" --gen $(GEN)
	$(PYTHON) test/check_video.py
	$(PYTHON) test/check_video_screen.py
	$(PYTHON) test/check_video_pair.py
	$(PYTHON) test/check_objects_touch.py
	$(PYTHON) test/check_objects_draw.py
	$(PYTHON) test/check_objects_bounds.py
	$(PYTHON) test/check_physics_normal.py
	$(PYTHON) test/check_world_memory.py
	$(PYTHON) test/check_world_retire.py
	$(PYTHON) test/check_world_alloc.py
	$(PYTHON) test/check_world_acquire.py
	$(PYTHON) test/check_world_cache.py --gen $(GEN)
	$(PYTHON) test/all_levels.py --rom $(GAME_ROM) --gen $(GEN) --out build/playtest/all-levels --idle-updates 12
	$(PYTHON) test/freefall.py --rom $(GAME_ROM) --gen $(GEN) --out build/playtest/freefall
	$(PYTHON) test/play.py --rom $(GAME_ROM) --gen $(GEN) --out build/playtest/check

clean:
	$(PYTHON) -c 'import shutil; shutil.rmtree("build", ignore_errors=True)'
