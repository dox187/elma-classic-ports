# Elasto Mania PlayStation port: build wrapper around CMake + PSn00bSDK.
#
#   make -C console/psx            build everything into build/
#   make -C console/psx hello      PS-EXE smoke test
#   make -C console/psx hello-disc track-1-only hello .bin/.cue
#   make -C console/psx test       run the headless PCSX-Redux hello tests
#   make -C console/psx disc-test  host tests of the disc builder and ISO reader
#                                  (DISC_TEST_ARGS=--real adds the game data)
#   make -C console/psx disc       the game disc (elma-cd, two tracks) into
#                                  $(BUILD)/disc/elma.cue; needs your own game files:
#                                  ELMA_RES=elma.res ELMA_LGR=Default_old.lgr
#                                  [ELMA_LEV=dir with the .lev files]
#   make -C console/psx clean
#
# Override any variable on the command line, for example BUILD=/path or
# LICENSE_FILE=/path/to/license.dat (real hardware only, never committed).

ROOT        := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
ELMA_PSX    ?= $(HOME)/.local/share/elma-psx
SDK         ?= $(ELMA_PSX)/psn00bsdk
GCC_DIR     ?= $(ELMA_PSX)/gcc
MKPSXISO    ?= $(ELMA_PSX)/mkpsxiso/bin/mkpsxiso
PCSX_REDUX  ?= $(ELMA_PSX)/pcsx-redux/PCSX-Redux-HEAD-x86_64.AppImage
PYTHON      ?= python3
BUILD       ?= $(ROOT)/build
LICENSE_FILE ?=
# The game data of the disc (your own copy of the game, never committed). The
# defaults are the Steam layout at the top of the repository.
REPO_ROOT   := $(abspath $(ROOT)/../..)
ELMA_RES    ?= $(wildcard $(REPO_ROOT)/elma.res)
ELMA_LGR    ?= $(wildcard $(REPO_ROOT)/build/Lgr/Default_old.lgr)
ELMA_LEV    ?=
BUILD_TYPE  ?= Release

CMAKE_ARGS := -G Ninja \
	-DCMAKE_TOOLCHAIN_FILE=$(SDK)/lib/libpsn00b/cmake/sdk.cmake \
	-DCMAKE_BUILD_TYPE=$(BUILD_TYPE) \
	-DPSN00BSDK_TC=$(GCC_DIR) \
	-DMKPSXISO=$(MKPSXISO) \
	-DPSX_LICENSE_FILE=$(LICENSE_FILE)

# The tools of the SDK (ninja, elf2x, ...) are found through PATH too.
export PATH := $(SDK)/bin:$(GCC_DIR)/bin:$(PATH)

.PHONY: all hello hello-disc test disc disc-test configure clean

all: configure
	cmake --build $(BUILD)

hello: configure
	cmake --build $(BUILD) --target hello

hello-disc: configure
	cmake --build $(BUILD) --target hello-disc

# The game disc: elma-cd.exe on track 1 (mkpsxiso; the Sony license data of
# LICENSE_FILE is only needed for real hardware), your ELMA.RES, the LGR as
# LGR/DEFAULT.LGR and the levels of ELMA_LEV as LEV/*.LEV on track 2; see
# tools/mkdisc.py. The result is $(BUILD)/disc/elma.cue and elma.bin.
disc: configure
	@test -n "$(ELMA_RES)" -a -f "$(ELMA_RES)" || { echo "disc: ELMA_RES is not set or not a file (your elma.res): make disc ELMA_RES=... ELMA_LGR=..."; exit 1; }
	@test -n "$(ELMA_LGR)" -a -f "$(ELMA_LGR)" || { echo "disc: ELMA_LGR is not set or not a file (the original-look LGR, e.g. Default_old.lgr): make disc ELMA_RES=... ELMA_LGR=..."; exit 1; }
	@test -z "$(ELMA_LEV)" -o -d "$(ELMA_LEV)" || { echo "disc: ELMA_LEV is not a directory: $(ELMA_LEV)"; exit 1; }
	cmake --build $(BUILD) --target elma-cd
	$(PYTHON) $(ROOT)/tools/mkdisc.py --exe $(BUILD)/elma-cd.exe --res "$(ELMA_RES)" \
		--lgr "$(ELMA_LGR)" $(if $(ELMA_LEV),--lev-dir "$(ELMA_LEV)") \
		$(if $(LICENSE_FILE),--license "$(LICENSE_FILE)") --mkpsxiso $(MKPSXISO) \
		--out-dir $(BUILD)/disc --name elma

cdtest: configure
	cmake --build $(BUILD) --target cdtest

# Builds the disc images (default layout and the variants) from the cdtest
# PS-EXE with tools/mkdisc.py, into $(BUILD)/cdtest-disc/.
cdtest-disc: cdtest
	$(PYTHON) $(ROOT)/test/cd_test.py --build $(BUILD) --discs-only

mctest: configure
	cmake --build $(BUILD) --target mctest

# Memory card test: LZ host test, then save/load/no-card/full-card runs in
# headless PCSX-Redux with private card images. MC_TEST_ARGS: --real ...
mc-test: mctest
	$(PYTHON) $(ROOT)/test/mc_test.py --build $(BUILD) --redux $(PCSX_REDUX) $(MC_TEST_ARGS)

soundtest: configure
	cmake --build $(BUILD) --target soundtest

# Sound output: encoder round trip on the host (real samples from elma.res,
# read only), then soundtest in headless PCSX-Redux. SOUND_TEST_ARGS: host|ps1.
sound-test: soundtest
	BUILD=$(BUILD) PCSX_REDUX=$(PCSX_REDUX) $(PYTHON) $(ROOT)/test/sound_test.py $(SOUND_TEST_ARGS)

# The GPU renderer of the game view against the original software renderer
# in headless PCSX-Redux (several minutes). GPU_TEST_ARGS: --levels
# warmup,internal,external, --external A.lev,B.lev, --gpu-only --fps (frame
# rate and the time of each part of a frame), --no-build ...
gpu-test: all
	PCSX_REDUX=$(PCSX_REDUX) $(PYTHON) $(ROOT)/test/gpu_compare_test.py --build $(BUILD) $(GPU_TEST_ARGS)

# Heap, stack and RAM high-water per phase (boot, menu, load, play) in
# headless PCSX-Redux, 8 MB mode. MEM_TEST_ARGS: --levels 0,15|all,
# --external FILE.lev, --limit KB, --jobs N, --quiet ...
mem-test: all
	PCSX_REDUX=$(PCSX_REDUX) $(PYTHON) $(ROOT)/test/mem_test.py --build $(BUILD) $(MEM_TEST_ARGS)

# Re-run configure every time; it is cheap and picks up elma.cmake appearing
# or variables changing.
configure:
	cmake -S $(ROOT) -B $(BUILD) $(CMAKE_ARGS)

test: hello hello-disc
	$(PYTHON) $(ROOT)/test/pcsx.py --redux $(PCSX_REDUX) --exe $(BUILD)/hello.exe \
		--map $(BUILD)/hello.map --lua $(ROOT)/test/hello_test.lua \
		--workdir $(BUILD)/test-exe --timeout 90 --grep 'magic=|PASS|FAIL|LUA ERROR'
	$(PYTHON) $(ROOT)/test/pcsx.py --redux $(PCSX_REDUX) --iso $(BUILD)/hello.cue \
		--map $(BUILD)/hello.map --lua $(ROOT)/test/hello_test.lua \
		--workdir $(BUILD)/test-iso --timeout 180 --arg frames=1500 --grep 'magic=|PASS|FAIL|LUA ERROR'
	@echo "hello tests passed"

# PS1 disc test in headless PCSX-Redux: track 2 mount, LEV/ listing, CRC of
# every file. CD_TEST_ARGS: --real, --layouts raw,split,2048, --keep ...
cd-test: cdtest
	$(PYTHON) $(ROOT)/test/cd_test.py --build $(BUILD) --redux $(PCSX_REDUX) $(CD_TEST_ARGS)

# Runs on the host only; ELMA_RES, ELMA_LGR and ELMA_LEV choose the game data
# for --real.
disc-test:
	$(PYTHON) $(ROOT)/test/disc_test.py --build $(BUILD)/test_disc $(DISC_TEST_ARGS)

clean:
	rm -rf $(BUILD)
