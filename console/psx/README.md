# Elasto Mania for PlayStation

An experimental PlayStation port of the original C++ game, with a GPU
renderer, fixed-point physics, SPU sound, two controllers and memory card
saves. The target is a retail PlayStation with 2 MB of RAM. The registered
game's 54 internal levels have been tested in PCSX-Redux at that memory
size. Real hardware has not been tested.

This is an alpha version. The level editor is omitted, and the physics and
rendering can differ from the PC game. It needs the files from your own
copy of Elasto Mania; no game data is included here.

## Requirements

The build uses:

- [PSn00bSDK](https://github.com/Lameguy64/PSn00bSDK), including its CMake
  toolchain and `elf2x`;
- a `mipsel-none-elf` GCC toolchain;
- [mkpsxiso](https://github.com/Lameguy64/mkpsxiso);
- CMake 3.21 or later, Ninja, GNU Make and Python 3.

The Makefile expects this layout by default:

```text
~/.local/share/elma-psx/
  psn00bsdk/        SDK installation (bin/ and lib/libpsn00b/cmake/)
  gcc/             cross-compiler installation (bin/mipsel-none-elf-*)
  mkpsxiso/bin/mkpsxiso
  pcsx-redux/PCSX-Redux-HEAD-x86_64.AppImage   optional, for tests
```

Override `ELMA_PSX`, or the individual `SDK`, `GCC_DIR`, `MKPSXISO` and
`PCSX_REDUX` Make variables, for other installations. Automated emulator
tests also need PCSX-Redux, `xvfb-run`, Mesa software rendering and a user
systemd session. Host tests need a native C/C++ compiler. The test harness
uses the emulator's OpenBIOS, so those tests do not require a Sony BIOS.

## Build and game data

Run these commands from the repository root:

```sh
make -C console/psx
make -C console/psx disc \
  ELMA_RES=/path/to/elma.res \
  ELMA_LGR=/path/to/Default_old.lgr \
  ELMA_LEV=/path/to/Lev
```

`ELMA_LEV` is optional. Use the original-look LGR (about 760 KB), often
named `Default_old.lgr` in the Steam installation. The large Steam LGR13
graphics set is not supported. The supplied LGR is stored as
`LGR/DEFAULT.LGR`, regardless of its original filename.

The registered build reads both the original and Steam `elma.res` formats
automatically. As on desktop, the archive's contents determine the Play
menu: original data opens the internal-level list directly, including its
External File entry; Steam data first offers Tutorial, Original Levels,
Stolen Internals, Quick & Easy, Quick & Hard and External Levels. Only
collections actually present in the archive are listed. Steam resource
data works with the original-look LGR described above.

The default build uses registered game data. For shareware data, configure
the same build directory with `ELMA_PSX_REGISTERED=OFF` first:

```sh
make -C console/psx configure
cmake -S console/psx -B console/psx/build -DELMA_PSX_REGISTERED=OFF
make -C console/psx
```

The setting remains in the CMake cache; set it back to `ON` for registered
data. `BUILD=/absolute/path` selects another build directory (use the same
directory with CMake). The root repository's desktop `build/` directory is
separate from the default PSX output directory.

The main outputs in `console/psx/build/` are:

| File | Use |
|------|-----|
| `elma-cd.exe` | Game executable that reads from the disc |
| `elma.exe` | Development executable that reads host files through PCdrv |
| `disc/elma.cue`, `disc/elma.bin` | Complete two-track disc image with your game data |
| `*.elf`, `*.map` | Debugging and automated tests |

Open `disc/elma.cue` in the emulator so both tracks are available. The
default image keeps both tracks in one `.bin`; this layout is tested in
PCSX-Redux. The builder's split-file and MODE1/2048 options are available
for other tools, but are not supported by the current Redux test path.

In DuckStation, open the `.cue` at normal emulation speed with standard
2 MB RAM. Boot, gameplay with sound, returning to the menu and starting a
level again have passed with its software renderer and OpenBIOS.
No proprietary BIOS image is distributed.

## Disc layout and packaging

Track 1 is bootable MODE2/2352 and contains `SYSTEM.CNF` and the game
executable. Track 2 is ISO9660 and contains your game data:

```text
ELMA.RES
LGR/DEFAULT.LGR
LEV/NAME.LEV         optional external levels
```

Names on the data track use uppercase DOS 8.3 names. The builder reports
and skips level names that do not fit. External levels are selected through
Play → External Levels with collection data, or Play → External File with
original data. A level referring to an absent LGR offers the
game's fallback to the default graphics.

[`tools/mkdisc.py`](tools/mkdisc.py) can also combine an existing code-only
track with a data ISO made by a standard ISO9660 tool:

```sh
python3 console/psx/tools/mkdisc.py \
  --track1-cue /path/to/code.cue \
  --track2-iso /path/to/game-data.iso \
  --out-dir console/psx/build/disc
```

Run it with `--help` for image formats and other options. The game locates
the second track through the disc TOC; it can also read the same data
layout from track 1 for development.

Keep distributable code separate from game data. A complete image made
with `make disc` contains your original assets and is for your own use;
do not redistribute it with the source release. Code-only packaging must
also retain the applicable source and third-party license notices. An
optional user-supplied `LICENSE_FILE=/path/to/license.dat` is passed to
mkpsxiso for hardware-oriented images. No Sony license data is included,
and hardware boot compatibility has not been verified.

## Controls

Controller 1 controls player A and the menus. Controller 2 controls player
B in two-player games. The controls use digital buttons.

| Button | In a level | In menus (controller 1) |
|--------|------------|-------------------------|
| Up / Cross | Gas | Up / Confirm |
| Down / Circle | Brake | Down / Back |
| Left / Right | Rotate left / right | Left / right |
| Square / R1 | Turn the bike | — / Page down |
| Triangle | Toggle navigator | — |
| L1 | Toggle time | Page up |
| L2 | Both rotation keys (alovolt) | — |
| R2 | Show/hide the player's view | — |
| Select | Leave the level | Back |
| Start | — | Confirm |

Holding Up or Down repeats menu movement. Use Left/Right and Up/Down to
edit letters in name-entry fields. Message screens are dismissed with
Cross or Start on controller 1.

The game has no Quit action. Back stays on the initial name/player screen
and the main menu; it returns from submenus and can cancel a new player
opened from Options.

PAL and NTSC are detected from the console's video mode. Gameplay uses
320×240 output and menus use 640×480 interlaced output, at 50 Hz on PAL
and about 60 Hz on NTSC. The game clock is independent of the video rate.
Menu animation is drawn in software and its update rate varies with the
drawing workload.

Level loading shows the current stage: reading the level, loading graphics
and sounds, preparing the level and starting play. The first load also
prepares sound data, so it can take longer than subsequent loads.

## Saves and compatibility

A formatted memory card in slot 1 stores players, options, best times and
external collection times. The port compresses `state.dat` and
`state-elma-ports.dat` into one card save, named `BAELMA-00000STATE`. This
is a homebrew identifier. The number of card blocks depends on the saved
data.

Saves are restored at boot and written automatically in menus, after the
game changes its state. Player creation and selection are saved immediately;
option changes are saved when returning from Options. Wait for the `Saving...`
message to disappear before resetting or removing the card; a write can take
several seconds. Card
errors are reported and play can continue, but those changes may not be
kept. The port does not format cards. Replays and other files written by
the game stay in RAM for the current session; they are not included in
the memory card save. The disc is read-only.

The physics uses 64-bit fixed-point state rather than the PC version's
floating-point calculations. Regression tests compare events and positions
against the original physics, but numerical differences can grow on some
levels. The replay file format is retained; identical gameplay, times and
PC compatibility are not guaranteed. Large or unusual external levels and
custom graphics may exceed the console's memory or renderer limits.

## Tests

These commands use the default build directory. Build the game first and
set `ELMA_RES`, `ELMA_LGR` and, for external levels, `ELMA_LEV_DIR` in the
environment to point to your own files.

```sh
# Host tests: file layer, math, ISO reader and disc builder
sh console/psx/test/core_host_tests.sh
make -C console/psx disc-test

# Host comparison of fixed-point and original physics
python3 console/psx/test/phys_test.py --quiet

# Emulator smoke tests, then game boot from the disc in retail 2 MB RAM
make -C console/psx test
python3 console/psx/test/core_boot_test.py --disc --ram2
python3 console/psx/test/video_test.py --disc
python3 console/psx/test/resource_menu_test.py --res /path/to/elma.res
python3 console/psx/test/console_ui_test.py
python3 console/psx/test/menu_perf_test.py --mode ntsc

# Internal levels in 2 MB; can take a long time
make -C console/psx mem-test \
  MEM_TEST_ARGS='--ram2 --limit 2048 --levels all --quiet'

# External levels from the disc, including return to the menu and replay
python3 console/psx/test/mem_test.py --levels '' \
  --external /path/to/Lev/NAME.LEV --ram2 --limit 2048 --again

# Repeated warning screens, shared card notices and heap integrity in 2 MB
python3 console/psx/test/message_test.py --level /path/to/Lev/NAME.LEV

# Disc reading, memory card module, in-game saves and sound
make -C console/psx cd-test
make -C console/psx mc-test
python3 console/psx/test/mc_game_test.py
python3 console/psx/test/sound_output_test.py --card-save
python3 console/psx/test/sound_game_test.py --ram2
make -C console/psx sound-test

# Options save and cold-boot restore; only a copy of this saved card is used
python3 console/psx/test/options_save_test.py --build console/psx/build \
  --card /path/to/card-with-a-saved-player.mcd
```

`make -C console/psx gpu-test` compares the GPU view with the software renderer.
`test/ext_menu_test.py` checks the external-level list and missing-LGR
dialog. `mem_test.py --external` checks that the requested level actually
loaded; comma-separated paths run several levels on separate discs.
Add `--again --force-reload` to check a full reload with sound already
initialized, or `--again --enable-sound-after` to check enabling sound
on a retained level.
`menu_perf_test.py` reports startup time and menu update intervals in retail
2 MB RAM. Use `--mode pal` for PAL and `--frames 900` to select the measurement
length in VBlanks. Its update count measures submitted pictures; interlaced
fields and uneven intervals can make motion less smooth than the average suggests.
For exact menu pixel comparisons, configure a separate build with
`-DELMA_PSX_MENU_COMPARE=ON`, build `elma-cd`, and run the test with
`python3 console/psx/test/menu_perf_test.py --build /path/to/that/build --compare`.
`--compare-frames 200` selects the minimum number of checked pictures. The
reference repaint adds substantial work; keep this option off for release timing.
`message_test.py` needs a small POT14 level and changes only a private copy
to exercise two recoverable version warnings per load. Consult each test's
`--help` for data paths and narrower runs.
Some development tests default to 8 MB of emulator RAM; passing a test in
that mode does not establish that the same case fits in 2 MB.

Emulator tests run headlessly and silently through
[`test/pcsx.py`](test/pcsx.py), with private emulator settings and card
images, bounded output and a memory-limited systemd scope. Test logs and
generated files go into the build directory.

## Source and licenses

The original game code is shared from [`../../src`](../../src), with
PSX-specific changes guarded by `ELMA_PSX`. The platform, file and CD
layers are in `src/`; `src/phys`, `src/gpu`, `src/sound`, `src/mem` and
`src/memcard` implement the console subsystems. The editor is replaced
by stubs.

The repository's [license](../../LICENSE.md) applies to the game source;
read its additional conditions as well as the CC BY-NC-SA terms. The
vendored [musl math subset](third_party/musl-libm/README.md) has its own
[copyright and license notices](third_party/musl-libm/COPYRIGHT).
PSn00bSDK is a separate dependency under MPL-2.0. The original graphics,
sounds, levels and other game assets are not part of this source release
and remain subject to their own terms.
