# Elasto Mania for Game Boy Color

Current development version: **0.96 — joint physics fidelity and stable-30-FPS work**,
recorded in [`VERSION`](VERSION). Development is in progress; no accepted 0.96
ROM exists yet. Latest playable diagnostic:
**[0.96 test69 — 8 MiB](build/elma-gbc-v0.96-test69-8m.gbc)**.
The primary controller replays averaged 29.830 updates/s, with 58 late
intervals out of 25,310. The independent replays had 22 late intervals out
of 5,302. Forced Steep Corner peaked at 58.68 ms for physics alone against
the 33.49 ms whole-game budget. [Measurements and verification](PERFORMANCE.md#096-test69--wheel-projections-and-terrain-records)

Active development targets the 8 MiB cartridge. All 54 original internal courses are selectable, with player profiles and per-course records.

## Build and run

Finished tests keep their versioned playable ROM and the results recorded in
[PERFORMANCE.md](PERFORMANCE.md). Remove their private trial directories,
duplicate ROMs and native compiler outputs after integration. Keep raw
reference traces only while the next comparison uses them. The builder
removes its intermediate Intel HEX file after it verifies the cartridge.
The gameplay benchmark writes its report and reference trace to the output
directory. It deletes each route's emulator screenshots and driver logs when
the route ends, including on interruption.
`make check-scheduled` and `make check-speed-limits` use a temporary
directory per run. To keep the native binaries and reports for debugging,
pass `SCHEDULE_CHECK_DIR=path` or `SPEED_CHECK_DIR=path` to the respective
target.

Requirements: Make, Bash, Python 3, a host C compiler for tests, curl and tar,
plus `elma.res` and `default.lgr` from your own copy of the game. The converters
use numpy and Pillow, and the emulator tests use PyBoy. From this directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
make bootstrap
make 8m ELMA_RES=/path/to/elma.res ELMA_LGR=/path/to/lgr/default.lgr
```

The current kernel requires `ROM_MIB=8 PHYS_HZ=30 DAMPER=scheduled`.

The current checkout builds versioned **0.96 development ROMs**. They are not
accepted releases until their complete-game timing and regression checks pass.

The current default output is **`build/elma-gbc-v0.96-8m.gbc`**. The corrected
scheduled kernel is still too slow; use this development output for diagnostics.
These are CGB-only MBC5 cartridges, not Game Boy
Advance programs; monochrome Game Boy hardware is unsupported. Both use header
type `0x1B` (MBC5+RAM+BATTERY), RAM code `0x03` (32 KiB), and ROM code `0x07`
(4 MiB) or `0x08` (8 MiB).

`make 8m` generates assets in `build/gen-8m`. The earlier 4 MiB and alternative
integration kernels remain in Git history; the current source rejects those
profiles. For an explicit output name, use e.g.
`make ROM_MIB=8 GAME_ROM=build/elma-gbc-v0.96-dev-8m.gbc game` with your resource
paths. Both Make and the standalone builder read `VERSION` for their default
playable filenames. Original rendered tiles are reused when their fingerprints
match; codec and bank-layout mismatches are rejected before linking. The current scheduled Q24
physics tables occupy banks **481–501**. The 8 MiB builder
rejects data in banks 508–511 and verifies that this tail remains unused.

On FlashMaster, select **MBC5**, **32K RAM**, the file's matching **4M or 8M ROM
size**, and enable **Save RAM**. The emulator's battery file or the cartridge's
save mechanism must preserve RAM across sessions. SRAM bank0 B800–BFFF holds
two checksummed save slots; the previous valid slot survives an interrupted
write. Versions 0.7 through 0.90 share saves across both ROM sizes; 0.6's 128 KiB
save files used a different location and are not loaded automatically.

For the reported 8 MiB hardware failure, build a separate cartridge diagnostic:

```sh
.venv/bin/python tools/cartridge_check.py --source build/elma-gbc-v0.84-8m.gbc --out build/elma-gbc-v0.84-8m-check.gbc --first-bank 477 --verify
```

Load the resulting `build/elma-gbc-v0.84-8m-check.gbc` with the same MBC5 / 8M / 32K settings.
It retains every byte of the game's switchable ROM banks and replaces only
ROM0 with a reader. It runs at double speed, first checking all bytes of banks
477–480 (about three seconds including boot in the emulator). **A** scans banks
1–511 (about 5–6 minutes of emulated hardware time); **B** repeats the quick check.
`FAIL` reports the bank and expected/read CRC16 values; `Matches bank 221`,
for example, suggests that bank 477 is reading its lower-half counterpart.
Record the displayed result before drawing a hardware conclusion. CRC16 is an
error detector, not a collision-proof comparison. The diagnostic itself never
enables or writes cartridge SRAM and is not a playable game build. The original
diagnostic is retained as `build/elma-gbc-v0.7-8m-check.gbc`; use `--first-bank
508` when rebuilding it from the original image.

| Button | Riding action |
|---|---|
| A | Gas |
| B | Brake |
| Left / Right | Volt left / right |
| Up | Turn around |
| Select | Open the pause menu; press again to resume |
| Start | Restart the current level, including after a crash or finish |

In Level Select, Up/Down select a course, Left/Right change page, and A/Start
launch it. On the title screen, a fresh A/Start press enters the main menu.
Choose Play, Level Select, Players or Controls; the pause menu offers Resume,
Restart, Level Select and Controls. B returns from a sub-screen, then resumes a paused
ride from the main menu. After finishing, A starts the next course;
after a crash, A or Start retries. After a crash or finish, B or Select opens
the main menu. These actions are shown on the result panel. After finishing,
Up toggles between the frozen gameplay frame and the detailed result screen.

The riding HUD shows apples remaining at the left and a labelled `TIME`
clock at the right. The display refreshes on every riding presentation
(nominally 29.86 Hz), using prebuilt digit-pair tiles so a normal update uploads
just one changed tile. The clock advances with simulated riding time, freezes
while paused or after a result, and resets on retry. Left/right can be held
to repeat volts. Both directions share the original `Ugroturelem = 0.4`
model-second cooldown, approximately **0.916 seconds** on the displayed clock.
The 30 Hz GBC profile waits **28 physics steps, approximately 0.938 seconds**:
the first step strictly beyond that threshold. An early held press fires when
eligible; releasing it before expiry does not queue a volt. Pause freezes the
cooldown and restart clears it. Missed frame deadlines can extend real elapsed
time, as they do for the rest of the simulation.

In Players, Up/Down chooses one of four profiles, A/Start selects it, Select
opens the name editor, and B returns. The editor accepts up to ten uppercase
letters, digits or spaces: arrows move around the large keyboard, A enters
the highlighted key, B deletes, Start saves, and Select cancels. Blank names
are rejected. Renaming keeps the profile’s records. Players can be changed
from the main menu outside a paused ride. Finishing a course saves a new best
time automatically; crashes and slower finishes leave existing records intact.

The finish panel and detailed screen show `TIME`, the previous best, and one
of `FIRST RECORD`, `NEW RECORD`, `BEST MATCHED` or `NO IMPROVEMENT`. Comparison
uses the current player's saved time for that course before replacing a record.
Matching or slower times leave that record intact. The bottom panel occupies
the final 24 screen pixels; scenery and sprites above it remain frozen. Its
extra text tiles reuse only world patterns absent from the visible area.
Returning from the detail screen, retrying or starting the next course rebuilds
the world cache before rendering gameplay again.

Audio uses the GBC wave, pulse and noise channels, serviced by the existing
main loop without a streaming interrupt. `tools/audio_assets.py` selects one
real cycle from each original `harl.wav` idle and `harl2.wav` load loop, limits
them to representable harmonics and quantizes each into CH3's 32 samples / 16
bytes. The cycle changes only at throttle edges, with the DAC off during the
bounded transfer. Steady pitch changes never rewrite wave RAM or retrigger it.

`make bootstrap` installs pinned GBDK **4.5.0**, with SHA-256 verification,
under ignored `.toolchain/`. It supports macOS arm64/x86_64 and Linux
aarch64/x86_64 and does not modify the shell profile. `GBDK_HOME=/path/to/gbdk`
selects an existing SDK. The Makefile supports macOS Make 3.81 and prefers
`.venv/bin/python`; override it with `PYTHON=/path/to/python` if needed.

Without explicit data paths, it looks for `../../elma.res` and
`../../lgr/default.lgr`. Keep the SDK, virtual environment, generated assets,
original game data and ROMs out of source commits; their working directories
are ignored by Git.

## Original data and graphics

The host converters reuse the existing readers and PC rendering models under
[`../snes/tools`](../snes/tools). All internal levels present in the resource
file are preserved in `build/gen/levels.json`, including original polygon,
object and picture records. Registered data supplies all 54 playable runtime
levels, in their original order and with their original names.

Collisions use the original non-grass polygon edges, subdivided for local
fixed-point contact queries and indexed by spatial cells. Dense cells receive
an additional subdivision without dropping edges. Collision queries use the
original geometry independently of the visual tile map. Source exports use
Q16.16 meters with y pointing upward.

The scenery reconstructs the PC graphics at 48 pixels per meter and reduces
them to a provisional **12 pixels per meter**, using seven four-color background
palettes. Foreground and background are reduced separately so terrain edges do
not invent a third sky color. Lossless horizontal/vertical flip deduplication
reduces storage; a **444-pattern cache** streams entering strips while retaining
all patterns still visible. Idle CPU time prepares the next offscreen row or
column, retaining the same 399 current cells until the camera enters the new
tile. Temporary references cover at most 438 cells; reversal discards the
prediction safely. This preparation adds no simulation or presentation frame.
The discontinued 0.91 development 4 MiB layout stores ZX0 blocks of 32 patterns
(512 bytes) and three independent 512-byte planes per 32x16 map chunk. Five
decoded map chunks use SRAM bank1; 32 decoded pattern blocks use banks2–3.
Preparation can stop between cold planes; a complete cached map gathers all
three planes together. Small courses that fit are preloaded with the LCD off.
Each compressed stream carries its exact native decode cost, rounded up to
double-speed scanlines. Idle preparation uses that cost plus a separate margin
for bank switching, cache work and interrupts. The build verifies the decoder
source hash before accepting these costs.
The retained 0.90 release uses 1,024-byte pattern and 1,536-byte map blocks.
The 8 MiB ROM
reads uncompressed patterns and maps directly, without these decoded caches.
It uses SRAM banks1–3 as a direct table for up to 12,288 pattern IDs. All but
one course fit; the larger Bowling course uses the linked bank0
lookup. Every lookup restores SRAM bank0, and the player save region is shared
with the retained earlier builds.

Both builds use this bank0 layout:

| Address | Purpose |
|---|---|
| A000–A7FF | 1,024 fallback lookup bucket heads |
| A800–AEEF | 444 fallback entries storing full pattern IDs and chain links |
| AEF0–AFFF | Reserved |
| B000–B7FF | 32x32 viewport slot mirror |
| B800–BFFF | Two persistent player/record save slots |

The lookup retains full IDs and resolves hash collisions without discarding
artwork. Background preparation stops between bounded work units. Cold block
decoding can extend level loading and scrolling updates, so the compressed
build still needs timing optimization. The remaining bank0 VRAM patterns hold
the killer sprites. Cartridge SRAM banks and VRAM banks are separate memories.

The build uses GBDK's `gbcompress --alg=zx0` and an optimized SM83 decoder.
ZX0 was created by Einar Saukas. Its decompressor license accompanies the port
in [`licenses/ZX0.txt`](licenses/ZX0.txt).
Every generated block is decoded on the host and compared byte-for-byte with
its source before packing. `test/check_graphics.py` also checks every block
through the native decoder, including SRAM guards and bank restoration.

Trees (`tree1`–`tree5`), flags and barrels are omitted from rendering. The original
picture records remain in the exported source data, as do the original polygons
and game objects. Grass, bushes and terrain texture/mask records are retained.
The sky is currently baked, without parallax or foreground-picture occlusion.

The menu retains the original background texture and helmet cursor. Text uses
[CG Pixel 3x5 Mono](fonts/README.md) at its native pixel size, with two characters
per tile. The HUD uploads only character pairs that changed. The
motorcycle and rider are rendered from the original LGR parts at **32
angles, three rider-compression poses and two facing directions**. The wheels
and head follow their independent physical positions; changed patterns are
uploaded through CGB DMA. The head updates every physics step with half-pixel
animation phases and separate front/back patterns so an upload cannot alter
the head still displayed at the previous position. This discrete animation is
an approximation of the original articulation. Global 8×16 sprite mode leaves
13 OAM entries for the bike and 26 for course objects. The riding VRAM layout is:

| VRAM allocation | Pattern indices |
|---|---|
| Background, bank 0 | 0–251 |
| Killers, bank 0 | 252–255 |
| Background, bank 1 | 0–191 |
| Bike body, wheels and head buffers, bank 1 | 192–219 |
| HUD text cells, bank 1 | 220–239 |
| Reserved, bank 1 | 240–247 |
| Apple and flower, bank 1 | 248–255 |

**Apples must be red and flower petals must be white.** They retain their
original outlines with dedicated object palettes, protected from scenery palette
fitting. Their first animation frames are used for now. Objects remain separate
sprites. Crowded areas cycle their sprite priority and can flicker at the
hardware's ten-sprites-per-scanline limit.

## Physics and the 30 FPS profile

The riding engine adapts the complete fixed-point C core of the existing NES
version, itself derived from `LEPTET.CPP`, `BEALLIT.CPP` and the original contact
code. It includes the body and both wheels, suspension, motor/brake reactions,
rolling contacts, rider movement and swept head-collision death. Linear
velocities retain 32-bit precision for fast courses such as Freefall. The GBC adaptation
uses banked code, cell-indexed collision data, SM83 arithmetic and exact lookup
tables; the tables accelerate products without approximating their results.

The **exponential damper** profile integrates the isolated suspension damper's
velocity impulse over the longer update interval. It retains the suspension
spring coefficient, physical damping coefficient and masses, applying the
corresponding reaction to the body. It is not an exact solution of the complete
coupled motorcycle and is numerically different from the PC integrator. Fixed
point, coarser stepping and the inherited discrete brake/contact solver also
mean PC trajectory equivalence is not claimed.

The original clock is **182 ticks per second scaled by `0.0024`** to obtain
target simulation time. Its solver uses a **`0.0055` step cap with a shorter
final step**, not a fixed 182 Hz physics rate. The GBC profile advances the same
game-time scale at nominal 30 updates per second, synchronized to every other
display frame (about 29.86 Hz on the GBC clock).

Historical `PHYS_HZ=60 DAMPER=explicit` comparisons do not establish a complete
60 FPS game and require the corresponding historical sources. The standalone
`physics-probe.gbc` is an older suspension diagnostic, not the riding solver or
a measure of full-game performance.

## Verification

```sh
make check-scheduled ELMA_RES=/path/to/elma.res ELMA_LGR=/path/to/lgr/default.lgr
```

`make check-scheduled` runs exact native/HOST state comparison, original-PC
rebound and braking trajectories, audio/control tests and complete-game checks.
It retains zero allowed deadline misses; current timing/cadence failures block
release. Each native run keeps an immutable source snapshot. The older
`make check` sequence below targets the historical one-step kernel and has not
been fully migrated to scheduled units.

The historical `make check` builds the playable and diagnostic ROMs, checks conversion, ROM
metadata, actual scrolling VRAM, protected object colors and the diagnostic
arithmetic. Native SM83 tests check the production multiplication, coefficient,
division, square-root, coordinate-bound and video helpers against independent
references, including lookup-table bytes and ROM-bank restoration.

The controller-only regression exercises controls, braking, pause,
head-collision death and restart, then attempts an apple/flower route.
It verifies actual tile, attribute and pattern VRAM across
map/chunk boundaries. It defaults to **zero allowed deadline misses** and does
not inject completion or object state into game RAM. Its default Warm Up
controller currently needs retuning: it also fails on the retained 0.72 ROM.

The native trajectory fixture compares all 109 internal and 52 public state
bytes after each call against the HOST implementation and a frozen reference.
It covers a Warm Up completion, fast Freefall and braking. This establishes
that arithmetic optimizations preserve the selected fixed-point model; it is
not a comparison against the PC integrator. Separate real-ROM checks select
all 54 courses through buttons and verify starts, object metadata, HUD, actual
VRAM, scenery palettes and moving head buffers. A diagnostic run with an
explicitly relaxed deadline budget is marked as failing the performance target.

Separate title and audio fixtures verify the complete splash framebuffer,
fresh button presses, audible PCM output, pitch changes, finite effects,
pause muting and ROM-bank restoration. The complete-ROM frontend check covers
title-to-menu navigation, Controls, course selection, pause/resume and restart.
The 0.74 splash fixture also checks all six native footer rows against the
source BDF glyphs, including the version, DOX187 credit and original copyright.

Results, ROM hashes, timing traces and screenshots are written under
`build/playtest/`; conversion and diagnostic results use
`build/verification.json`. Emulator results do not establish complete PC
trajectory parity.

`build/elma-gbc-viewer.gbc` remains as a graphics inspection ROM: D-pad pans,
A pans faster, B mirrors the illustration, Select hides/shows it and Start
returns to the start. Its static `VIEW` scene is separate from the playable ROM.

Toolchain references are the
[GBDK coding guidelines](https://gbdk.org/docs/api/docs_coding_guidelines.html)
and [Pan Docs](https://gbdev.io/pandocs/).

## Development history

Read the [detailed GBC release notes](RELEASE_NOTES.md) for build changes, measurements and test results.

| Version | Main change |
| --- | --- |
| First playable / 0.3 | Fixed-point bike physics, original artwork, all 54 courses |
| 0.4 | Title screen, menus, 3×5 font, native audio |
| 0.5 | Compressed scenery for a 4 MiB ROM |
| 0.6 | Player names, saved records, race feedback |
| 0.7 | 4 and 8 MiB builds, 32 KiB SRAM, bank diagnostics |
| 0.72 | Steady idle sound and held volt controls |
| 0.73 | Per-frame timer and finish results |
| 0.74 | Readable splash credits |
| 0.80 | Native sounds derived from original samples |
| 0.81 | Original engine pitch and load-dependent tone |
| 0.82 | Louder engine and effects |
| 0.83 | Second engine sound channel |
| 0.84 | Half-volume CH1 exhaust |
| 0.90 | PC physics comparisons, rider fixes, brighter scenery |
| 0.91 / test1 | Faster suspension, contact checks and scenery streaming |
| 0.92 | Variable idle, wheel-impact creaks, volt sound |
| 0.93 | PC-timed physics substeps, corrected rebound and braking |
| 0.94 | High-speed physics audit and drive cutoff correction |
| 0.95 | Speed work folded into 0.96 |

### 0.96 test builds

| Build | Main change |
| --- | --- |
| test1 | Faster suspension forces and wide dot products |
| test2 | 32-bit angular velocity and brake torque |
| test3 | Greater airborne wheel travel |
| test4 | More precise airborne damping and course exits |
| test5 | Full-precision wheel damping and fractional body rotation |
| test6 | Faster rider-limit checks and scheduled physics |
| test7 | Cached terrain clearance and faster damping torque |
| test8 | Faster grounded contacts and head sweeps |
| test9 | Skipped redundant single-contact velocity projections |
| test10 | Reused both contacts at unchanged wheel positions |
| test11 | Precomputed wheel clearance across all courses |
| test12 | Combined spring and damping products |
| test13 | Paired wheel updates and narrower terrain searches |
| test14 | Prepared suspension during spare display time |
| test15 | Looked up contact normals at terrain vertices |
| test16 | Shorter damping products and cheaper scenery uploads |
| test17 | Fused fractional movement and synchronized HUD time |
| test18 | Looked up stationary two-contact wheel responses |
| test19 | Shared angular updates for free and rolling wheels |
| test20 | Combined opposing spring moments |
| test21 | Prepared suspension one wheel at a time |
| test22 | Kept wheel animation tiles in VRAM |
| test23 | Batched changed bike tiles into DMA transfers |
| test24 | Reused terrain classifications and signed products |
| test25 | Looked up partial movement and shallow slopes |
| test26 | Skipped irrelevant edges and exterior endpoints |
| test27 | Tabulated slope and compressed-suspension products |
| test28 | Reused terrain spans and partially prepared columns |
| test29 | Batched suspension forces and shortened signed projections |
| test30 | Narrowed dense-terrain searches and reused rolling projections |
| test31 | Packed scenery indices to fit suspension tables |
| test32 | Reused rider displacement in spring and spin calculations |
| test33 | Shared projected points between equal wheel contacts |
| test34 | Reused terrain spans across both wheels |
| test35 | Extended rolling tables and skipped unnecessary pushouts |
| test36 | Tabulated 172 rolling directions and shared vertex normals |
| test37 | Shared rolling lookups and batched background transfers |
| test38 | Combined torque products before rounding |
| test39 | Paired body and wheel position updates with residuals |
| test40 | Faster rolling impulses and head clearance checks |
| test41 | Reduced wheel-contact and scenery update costs |
| test42 | Faster course bounds and swept-head checks |
| test43 | Ran force calculations from work RAM |
| test44 | Shortened rolling calculations on flats and slopes |
| test45 | Tabulated wheel reactions for 16-bit inputs |
| test46 | Reused wheel coordinates and background strip bounds |
| test47 | Shared vertex contacts at multi-edge corners |
| test48 | Faster deep wheel contacts and repeated head sweeps |
| test49 | Reused wheel projections, suspension coordinates and camera crossing ranks |
| test50 | Reused contact points and skipped unreachable terrain edges |
| test51 | Reused wheel normals and shortened rolling and suspension calculations |
| test52 | Shared wide rolling products and packed ordered two-edge contacts |
| test53 | Shortened wheel edge lists, shared vertex projections and head checks |
| test54 | Shortened Curvaceous contact searches and Gravity Ride braking updates |
| test55 | Reused wheel projections and terrain results on corners and braking routes |
| test56 | Shortened suspension, rolling and planar contacts on braking routes |
| test57 | Shortened wheel responses and prepared suspension during short waits |
| test58 | Streamed ordered edges and shortened braking, scenery and camera work |
| test59 | Tabulated wheel endpoint lengths and skipped distant object checks |
| test60 | Shortened wheel pivots, head sweeps and object checks |
| test61 | Reused Bowling vertex contacts and shortened throttle, body and head updates |
| test62 | Shortened Bumpy Journey braking, moving contacts, suspension and sprite transfers |
| test63 | Cached wheel projections and eleven motorcycle poses |
| test64 | Bounded wheel pivots, shared braking products and resident rider heads |
| test65 | Skipped unused locked-wheel velocity, paired motion and deep-contact divisions |
| test66 | Expanded wheel normals, shared spring products and batched scenery strips |
| test67 | Shared scenery slots, faster signed products and eight complete contact tiles |
| test68 | Tabulated contact lengths, shorter wheel corrections and scenery preloads |
| test69 | Reused terrain records and shortened flat and two-contact wheel projections |
