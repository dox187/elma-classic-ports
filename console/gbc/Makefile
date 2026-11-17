GBDK_HOME ?= $(CURDIR)/.toolchain/gbdk
LCC := $(GBDK_HOME)/bin/lcc
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
ELMA_RES ?= ../../elma.res
ELMA_LGR ?= ../../lgr/default.lgr
PHYS_HZ ?= 30
DAMPER ?= exponential
ROM_MIB ?= 8
ifeq ($(filter $(ROM_MIB),4 8),)
$(error ROM_MIB must be 4 or 8)
endif
VERSION := $(shell cat VERSION)
GAME_ROM ?= build/elma-gbc-v$(VERSION)-$(ROM_MIB)m.gbc
GEN ?= $(if $(filter 4,$(ROM_MIB)),build/gen,build/gen-8m)
LEVEL_CACHE ?= build/gen
# Keep the 8 MiB physics tables directly after scenery, away from the ROM tail.
COEFFICIENT_BANK := $(if $(filter 4,$(ROM_MIB)),252,477)
FLAGS := -msm83:gb -Wf--opt-code-size -Wf--max-allocs-per-node -Wf100000 -Wm-yC -Wm-yt0x1B -Wm-ya4 -Wm-yoA -Wm-ynELMA-GBC -Wl-m -Wl-j -I$(GEN) -Isrc
PHYS_ASM := $(filter-out src/physics_mul16.s,$(wildcard src/physics_*.s))

.PHONY: all game 4m 8m bootstrap assets check clean
all: $(GAME_ROM) build/elma-gbc-viewer.gbc build/physics-probe.gbc
game: $(GAME_ROM)

4m:
	$(MAKE) ROM_MIB=4 game

8m:
	$(MAKE) ROM_MIB=8 game

bootstrap:
	bash tools/bootstrap.sh

# FORCE is intentional: changing the input paths must invalidate generated data.
.PHONY: FORCE
FORCE:

assets: FORCE
	$(PYTHON) tools/assets.py --res "$(ELMA_RES)" --lgr "$(ELMA_LGR)" --out $(GEN)
	$(PYTHON) tools/physics_constants.py $(GEN)
	$(PYTHON) tools/physics_level.py --res "$(ELMA_RES)" --out $(GEN) --hz $(PHYS_HZ) --damper $(DAMPER)
	$(PYTHON) tools/levels.py --res "$(ELMA_RES)" --lgr "$(ELMA_LGR)" --out $(GEN) --rom-mib $(ROM_MIB) --cache-gen "$(LEVEL_CACHE)"
ifeq ($(ROM_MIB),4)
	$(PYTHON) tools/pack_graphics.py --gen $(GEN) --sdk "$(GBDK_HOME)"
endif
	$(PYTHON) tools/menu_assets.py --res "$(ELMA_RES)" --out $(GEN)
	$(PYTHON) tools/splash_assets.py --res "$(ELMA_RES)" --out $(GEN)
	$(PYTHON) tools/audio_assets.py --res "$(ELMA_RES)" --out $(GEN)
	$(PYTHON) tools/bike_frames.py --lgr "$(ELMA_LGR)" --out $(GEN)
	$(PYTHON) tools/bike_frames16.py --source $(GEN) --out $(GEN)
	$(PYTHON) tools/mul_table.py --out $(GEN)
	$(PYTHON) tools/scale_table.py --out $(GEN)
	$(PYTHON) tools/physics_sine.py --out $(GEN)
	$(PYTHON) tools/math32_coefficients.py --constants $(GEN)/riding_constants.h --out $(GEN) --first-bank $(COEFFICIENT_BANK)

$(GAME_ROM): assets src/video.s src/play.c src/runtime.h src/bike_render.c src/physics.c src/physics_core.c src/physics_contacts.c src/physics_collision.c src/physics_math.c src/physics_math32.c $(PHYS_ASM)
	$(PYTHON) tools/build.py --sdk "$(GBDK_HOME)" --gen $(GEN) --out $@ --rom-mib $(ROM_MIB)

build/elma-gbc-viewer.gbc: assets src/main.c
	$(LCC) $(filter-out -Wm-yt0x1B -Wm-ya4,$(FLAGS)) -Wm-yt0x19 -o $@ src/main.c $(GEN)/world_*.c $(GEN)/patterns.c $(GEN)/assets.c

build/physics-probe.gbc: assets src/physics_probe.c src/suspension.c src/suspension.h src/mul16.s
	$(LCC) $(filter-out -Wm-yt0x1B -Wm-ya4,$(FLAGS)) -Wm-yt0x19 -o $@ src/physics_probe.c src/suspension.c src/mul16.s

check: all
	$(PYTHON) test/check.py --gen $(GEN)
	$(PYTHON) test/check_splash.py --res "$(ELMA_RES)"
	$(PYTHON) test/check_audio.py --gen $(GEN)
	$(PYTHON) test/check_riding_math.py
	$(PYTHON) test/check_riding_mul9.py
	$(PYTHON) test/check_riding_division.py
	$(PYTHON) test/check_riding_sqrt.py
	$(PYTHON) test/check_riding_bounds.py
	$(PYTHON) test/check_riding_math32.py
	$(PYTHON) test/check_physics_export.py --gen $(GEN)
	$(PYTHON) test/check_physics_move.py
	$(PYTHON) test/check_physics_rider.py
	$(PYTHON) test/check_physics_anchor.py
	$(PYTHON) test/check_physics_brake.py --gen $(GEN)
	$(PYTHON) test/check_physics_contact_loop.py --gen $(GEN)
	$(PYTHON) test/check_physics_contact_sign.py
	$(PYTHON) test/check_physics_recip.py
	$(PYTHON) test/check_physics_shift.py
	$(PYTHON) test/check_physics_rider_reject.py --gen $(GEN)
	$(PYTHON) test/check_physics_sine.py
	$(PYTHON) test/check_physics_coefficients.py --constants $(GEN)/riding_constants.h --first-bank $(COEFFICIENT_BANK)
	$(PYTHON) test/check_physics_sweep.py --gen $(GEN)
	$(PYTHON) test/check_physics_levels.py --res "$(ELMA_RES)" --gen $(GEN)
	$(PYTHON) test/check_physics_levels.py --res "$(ELMA_RES)" --gen $(GEN) --out build/physics-high-bank-check --high-bank
	$(PYTHON) test/check_physics_trace.py --res "$(ELMA_RES)" --gen $(GEN) --first-bank $(COEFFICIENT_BANK)
	$(PYTHON) test/check_frame_wait.py
	$(PYTHON) test/check_video.py
	$(PYTHON) test/check_video_screen.py
	$(PYTHON) test/check_video_pair.py
	$(PYTHON) test/check_objects_touch.py
	$(PYTHON) test/check_objects_draw.py
	$(PYTHON) test/check_objects_bounds.py
	$(PYTHON) test/check_objects_empty.py --gen $(GEN)
	$(PYTHON) test/check_physics_normal.py
	$(PYTHON) test/check_world_memory.py
	$(PYTHON) test/check_world_fetch_raw.py --gen $(GEN)
	$(PYTHON) test/check_world_lookup_raw.py
	$(PYTHON) test/check_world_retire.py
	$(PYTHON) test/check_world_alloc.py
	$(PYTHON) test/check_world_acquire.py
	$(PYTHON) test/check_world_cache.py --gen $(GEN) --launch-observer
ifeq ($(ROM_MIB),4)
	$(PYTHON) test/check_world_cache.py --gen $(GEN) --compressed --out build/playtest/world-cache-compressed
	$(PYTHON) test/check_graphics.py --rom $(GAME_ROM) --gen $(GEN)
endif
	$(PYTHON) test/check_frontend.py --rom $(GAME_ROM) --gen $(GEN)
	$(PYTHON) test/check_finish_audio.py --rom $(GAME_ROM) --gen $(GEN)
	$(PYTHON) test/check_volt_input.py --rom $(GAME_ROM) --gen $(GEN)
	$(PYTHON) test/check_save.py
	$(PYTHON) test/check_players.py --rom $(GAME_ROM) --gen $(GEN)
	$(PYTHON) test/all_levels.py --rom $(GAME_ROM) --gen $(GEN) --out build/playtest/all-levels --idle-updates 12
	$(PYTHON) test/freefall.py --rom $(GAME_ROM) --gen $(GEN) --out build/playtest/freefall
	$(PYTHON) test/play.py --rom $(GAME_ROM) --gen $(GEN) --out build/playtest/check

clean:
	$(PYTHON) -c 'import shutil; shutil.rmtree("build", ignore_errors=True)'
