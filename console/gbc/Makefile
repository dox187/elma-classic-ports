GBDK_HOME ?= $(CURDIR)/.toolchain/gbdk
LCC := $(GBDK_HOME)/bin/lcc
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
ELMA_RES ?= ../../elma.res
ELMA_LGR ?= ../../lgr/default.lgr
PHYS_HZ ?= 30
DAMPER ?= scheduled
ROM_MIB ?= 8
ifneq ($(ROM_MIB),8)
$(error The scheduled source requires ROM_MIB=8; earlier 4 MiB sources remain in Git history)
endif
ifneq ($(DAMPER),scheduled)
$(error The current riding kernel requires DAMPER=scheduled)
endif
ifneq ($(PHYS_HZ),30)
$(error The current scheduled riding kernel requires PHYS_HZ=30)
endif
VERSION := $(shell cat VERSION)
GAME_ROM ?= build/elma-gbc-v$(VERSION)-$(ROM_MIB)m.gbc
GEN ?= $(if $(filter 4,$(ROM_MIB)),build/gen,build/gen-8m)
LEVEL_CACHE ?= build/gen
# Keep the 8 MiB physics tables directly after scenery, away from the ROM tail.
COEFFICIENT_BANK := $(if $(filter scheduled,$(DAMPER)),481,$(if $(filter 4,$(ROM_MIB)),252,477))
COEFFICIENT_TOOL := $(if $(filter scheduled,$(DAMPER)),math_q24_coefficients.py,math32_coefficients.py)
FLAGS := -msm83:gb -Wf--opt-code-size -Wf--max-allocs-per-node -Wf100000 -Wm-yC -Wm-yt0x1B -Wm-ya4 -Wm-yoA -Wm-ynELMA-GBC -Wl-m -Wl-j -I$(GEN) -Isrc
PHYS_ASM := $(filter-out src/physics_mul16.s,$(wildcard src/physics_*.s))

.PHONY: all game 4m 8m bootstrap assets check check-scheduled check-speed-limits clean
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
	$(PYTHON) tools/$(COEFFICIENT_TOOL) --constants $(GEN)/riding_constants.h --out $(GEN) --first-bank $(COEFFICIENT_BANK)

$(GAME_ROM): assets src/video.s src/play.c src/runtime.h src/bike_render.c src/physics.c src/physics_core.c src/physics_contacts.c src/physics_collision.c src/physics_math.c src/physics_math32.c $(PHYS_ASM)
	$(PYTHON) tools/build.py --sdk "$(GBDK_HOME)" --gen $(GEN) --out $@ --rom-mib $(ROM_MIB)

build/elma-gbc-viewer.gbc: assets src/main.c
	$(LCC) $(filter-out -Wm-yt0x1B -Wm-ya4,$(FLAGS)) -Wm-yt0x19 -o $@ src/main.c $(GEN)/world_*.c $(GEN)/patterns.c $(GEN)/assets.c

build/physics-probe.gbc: assets src/physics_probe.c src/suspension.c src/suspension.h src/mul16.s
	$(LCC) $(filter-out -Wm-yt0x1B -Wm-ya4,$(FLAGS)) -Wm-yt0x19 -o $@ src/physics_probe.c src/suspension.c src/mul16.s

# A caller can name an output directory to retain an investigation.
# Otherwise run the same recipe with a private directory for this invocation.
define check_in_temp
@set -e; scratch=$$(mktemp -d "$${TMPDIR:-/tmp}/elma-$@.XXXXXX"); \
 trap 'rm -rf "$$scratch"' 0; trap 'exit 1' HUP INT TERM; \
 $(MAKE) -o "$(GAME_ROM)" "$@" "$(1)=$$scratch"
endef

check-scheduled: $(GAME_ROM)
ifndef SCHEDULE_CHECK_DIR
	$(call check_in_temp,SCHEDULE_CHECK_DIR)
else
	$(PYTHON) test/check_wheel_pair.py --rom $(GAME_ROM)
	$(PYTHON) test/check_reaction_coefficient.py --gen $(GEN) --rom $(GAME_ROM)
	$(PYTHON) test/check_shallow_push.py --rom $(GAME_ROM)
	$(PYTHON) test/check_wheel_terrain.py --gen $(GEN) --rom $(GAME_ROM)
	$(PYTHON) test/check_normal_atlas.py --rom $(GAME_ROM)
	$(PYTHON) test/check_physics_rider.py --rom $(GAME_ROM)
	$(PYTHON) test/check_projection_tables.py --rom $(GAME_ROM)
	$(PYTHON) test/check_roll_table.py --rom $(GAME_ROM)
	$(PYTHON) test/check_level_exits.py --gen $(GEN) --res "$(ELMA_RES)" --out "$(SCHEDULE_CHECK_DIR)/level-exits"
	$(PYTHON) test/check_wide_brake.py --gen $(GEN) --out "$(SCHEDULE_CHECK_DIR)/wide-brake"
	$(PYTHON) test/check_wide_wheels.py --gen $(GEN) --out "$(SCHEDULE_CHECK_DIR)/wide-wheels"
	$(PYTHON) test/check_close_reaction.py --out "$(SCHEDULE_CHECK_DIR)/close-reaction"
	$(PYTHON) test/check_partial_motion.py --gen $(GEN) --out "$(SCHEDULE_CHECK_DIR)/partial-motion"
	$(PYTHON) test/check_physics_move.py --out "$(SCHEDULE_CHECK_DIR)/move"
	$(PYTHON) test/check_force_accumulator.py --out "$(SCHEDULE_CHECK_DIR)/force"
	$(PYTHON) test/check_force_registers.py --out "$(SCHEDULE_CHECK_DIR)/force-registers"
	$(PYTHON) test/check_physics_dot32.py --gen $(GEN) --out "$(SCHEDULE_CHECK_DIR)/dot32"
	$(PYTHON) test/check_q24.py --gen $(GEN) --out "$(SCHEDULE_CHECK_DIR)/q24"
	$(PYTHON) test/check_q24.py --gen $(GEN) --out "$(SCHEDULE_CHECK_DIR)/q24-signed" --signed-edges
	$(PYTHON) test/check_scheduled_native.py --gen $(GEN) --out "$(SCHEDULE_CHECK_DIR)/native"
	$(PYTHON) test/check_suspension_products.py --native "$(SCHEDULE_CHECK_DIR)/native" --out "$(SCHEDULE_CHECK_DIR)/suspension-products"
	$(PYTHON) test/check_suspension_forces.py --native "$(SCHEDULE_CHECK_DIR)/native" --out "$(SCHEDULE_CHECK_DIR)/suspension-forces"
	$(PYTHON) test/check_damping_moment.py --native "$(SCHEDULE_CHECK_DIR)/native" --out "$(SCHEDULE_CHECK_DIR)/damping-moment"
	$(PYTHON) test/check_rider_coefficients.py --native "$(SCHEDULE_CHECK_DIR)/native" --out "$(SCHEDULE_CHECK_DIR)/rider-coefficients"
	$(PYTHON) test/check_rebound_schedule.py --gen $(GEN) --out "$(SCHEDULE_CHECK_DIR)/pc" --max-rebound-error-percent 0.1 --max-airtime-error-percent 0.1
	$(PYTHON) test/check_audio.py --gen $(GEN) --out "$(SCHEDULE_CHECK_DIR)/audio"
	$(PYTHON) test/check_riding_audio.py --gen $(GEN) --out "$(SCHEDULE_CHECK_DIR)/riding-audio"
	$(PYTHON) test/check_volt_input.py --rom $(GAME_ROM) --gen $(GEN) --out "$(SCHEDULE_CHECK_DIR)/volt"
	$(PYTHON) test/check_frontend.py --rom $(GAME_ROM) --gen $(GEN) --out "$(SCHEDULE_CHECK_DIR)/frontend"
	$(PYTHON) test/check_players.py --rom $(GAME_ROM) --gen $(GEN) --out "$(SCHEDULE_CHECK_DIR)/players"
	$(PYTHON) test/all_levels.py --rom $(GAME_ROM) --gen $(GEN) --out "$(SCHEDULE_CHECK_DIR)/all-levels" --idle-updates 12
	$(PYTHON) test/freefall.py --rom $(GAME_ROM) --gen $(GEN) --out "$(SCHEDULE_CHECK_DIR)/freefall"
endif

# Numeric-limit findings are reported, not treated as passing PC fidelity.
# Drive cutoff, extreme-spin survival and raw native/HOST equivalence are strict gates.
check-speed-limits: $(GAME_ROM)
ifndef SPEED_CHECK_DIR
	$(call check_in_temp,SPEED_CHECK_DIR)
else
	$(PYTHON) test/check_freefall_volts.py --rom $(GAME_ROM) --gen $(GEN) --res "$(ELMA_RES)" --out "$(SPEED_CHECK_DIR)/controller"
	@for step in 240 250 260 270 280; do \
		$(PYTHON) test/check_airborne_spin.py --rom $(GAME_ROM) --gen $(GEN) --res "$(ELMA_RES)" --seed-step $$step --out "$(SPEED_CHECK_DIR)/spin-$$step" || exit 1; \
	done
	$(PYTHON) test/check_speed_limits.py --gen $(GEN) --out "$(SPEED_CHECK_DIR)/pc" --require-gas-cutoff --require-spin-survival
	$(PYTHON) test/check_scheduled_native.py --gen $(GEN) --case-file "$(SPEED_CHECK_DIR)/pc/cases.json" --out "$(SPEED_CHECK_DIR)/native"
endif

check: all
	$(PYTHON) test/check_build_layout.py
	$(PYTHON) test/check.py --gen $(GEN)
	$(PYTHON) test/check_splash.py --res "$(ELMA_RES)"
	$(PYTHON) test/check_audio.py --gen $(GEN)
	$(PYTHON) test/check_audio_idle.py --gen $(GEN)
	$(PYTHON) test/check_riding_audio.py --gen $(GEN)
	$(PYTHON) test/check_impact_audio.py --gen $(GEN)
	$(PYTHON) test/check_riding_math.py
	$(PYTHON) test/check_riding_mul9.py
	$(PYTHON) test/check_riding_division.py
	$(PYTHON) test/check_riding_sqrt.py
	$(PYTHON) test/check_riding_bounds.py
	$(PYTHON) test/check_riding_math32.py
	$(PYTHON) test/check_physics_mulq_wide.py --gen $(GEN)
	$(PYTHON) test/check_physics_export.py --gen $(GEN)
	$(PYTHON) test/check_physics_move.py
	$(PYTHON) test/check_physics_rider.py
	$(PYTHON) test/check_physics_rider_response.py --gen $(GEN)
	$(PYTHON) test/check_physics_head_pose.py --gen $(GEN)
	$(PYTHON) test/check_physics_anchor.py
	$(PYTHON) test/check_physics_brake.py --gen $(GEN)
	$(PYTHON) test/check_physics_torque_reaction.py --gen $(GEN)
	$(PYTHON) test/check_physics_contact_loop.py --gen $(GEN)
	$(PYTHON) test/check_physics_wheel.py --gen $(GEN)
	$(PYTHON) test/check_physics_pushout.py --gen $(GEN)
	$(PYTHON) test/check_physics_contact_sign.py
	$(PYTHON) test/check_physics_recip.py
	$(PYTHON) test/check_physics_shift.py
	$(PYTHON) test/check_physics_rider_reject.py --gen $(GEN)
	$(PYTHON) test/check_physics_sine.py
	$(PYTHON) test/check_physics_coefficients.py --constants $(GEN)/riding_constants.h --first-bank $(COEFFICIENT_BANK)
	$(PYTHON) test/check_physics_sweep.py --gen $(GEN)
	$(PYTHON) test/check_head_clearance.py --gen $(GEN) --rom $(GAME_ROM)
	$(PYTHON) test/check_head_quarters.py --rom $(GAME_ROM) --res "$(ELMA_RES)"
	$(PYTHON) test/check_physics_levels.py --res "$(ELMA_RES)" --gen $(GEN)
	$(PYTHON) test/check_physics_levels.py --res "$(ELMA_RES)" --gen $(GEN) --out build/physics-high-bank-check --high-bank
	$(PYTHON) test/check_physics_trace.py --res "$(ELMA_RES)" --gen $(GEN) --first-bank $(COEFFICIENT_BANK)
	$(PYTHON) test/check_frame_wait.py
	$(PYTHON) test/check_video.py
	$(PYTHON) test/check_video_screen.py
	$(PYTHON) test/check_video_pair.py
	$(PYTHON) test/check_objects_touch.py
	$(PYTHON) test/check_objects_draw.py
	$(PYTHON) test/check_objects_visible.py
	$(PYTHON) test/check_objects_bounds.py
	$(PYTHON) test/check_objects_empty.py --gen $(GEN)
	$(PYTHON) test/check_world_retain_column.py --gen $(GEN) --out build/world-retain-column-check --launch-observer
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
