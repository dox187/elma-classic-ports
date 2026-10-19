# Elasto Mania PlayStation port: build wrapper around CMake + PSn00bSDK.
#
#   make -C console/psx            build everything into build/
#   make -C console/psx hello      PS-EXE smoke test
#   make -C console/psx hello-disc track-1-only hello .bin/.cue
#   make -C console/psx test       run the headless PCSX-Redux hello tests
#   make -C console/psx disc-test  host tests of the disc builder and ISO reader
#                                  (DISC_TEST_ARGS=--real adds the game data)
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
BUILD_TYPE  ?= Release

CMAKE_ARGS := -G Ninja \
	-DCMAKE_TOOLCHAIN_FILE=$(SDK)/lib/libpsn00b/cmake/sdk.cmake \
	-DCMAKE_BUILD_TYPE=$(BUILD_TYPE) \
	-DPSN00BSDK_TC=$(GCC_DIR) \
	-DMKPSXISO=$(MKPSXISO) \
	-DPSX_LICENSE_FILE=$(LICENSE_FILE)

# The tools of the SDK (ninja, elf2x, ...) are found through PATH too.
export PATH := $(SDK)/bin:$(GCC_DIR)/bin:$(PATH)

.PHONY: all hello hello-disc test disc-test configure clean

all: configure
	cmake --build $(BUILD)

hello: configure
	cmake --build $(BUILD) --target hello

hello-disc: configure
	cmake --build $(BUILD) --target hello-disc

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
