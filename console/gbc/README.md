# Elasto Mania for Game Boy Color

Last completed version: **0.90 — intermediate playable prototype**.
Development version: **0.91**, recorded in [`VERSION`](VERSION), targets stable
30 FPS without changing the current physics results or adding input latency.
Active development now targets the **8 MiB ROM only**. Work on the 4 MiB
compressed variant stopped on 2026-11-17; its existing releases and experiments
are retained for reference.
See the [performance experiment log](PERFORMANCE.md) for measured candidates
and rejected approaches. Development builds do not overwrite the 0.90 ROMs.

Playable test: **[0.91 test1 — 8 MiB](build/elma-gbc-v0.91-test1-8m.gbc)**,
for MBC5 with 32 KiB cartridge RAM. Its SHA-256 is
`624e427940917c15d1d4960866f0368f61549b6f59292a41290c047b6c38a8b5`.

This build preserves all 27,447 native states in the 216-case controller
corpus. Deadline misses fall from 1,025 to 55, with 196 cases passing
throughout. Its separate functional run passes all 54 starts, complete
Freefall, menus, save profiles, volt controls and finish audio. Further graphics/physics
optimization and physical-cartridge timing checks remain; **0.91 is not yet a
stable 30-FPS release**.

In 0.90, the rider updates on every physics step and responds
to the body's rotation after a volt. Green scenery is slightly brighter.
This release uses the native fixed-point riding core; the much more precise
Q44/Q46 host experiments described below are separate research. Neither full
PC fidelity nor stable 30 FPS on every course is claimed.

The 0.84 audio balance is retained: CH1 idle volume 3 and throttle volume 8,
with the original-derived CH3 cycles, pitch curve, effect levels and master
gain. The two-channel engine has quieter idle, no streaming interrupt and
finite hardware watchdogs.

It includes the 0.74 splash: original logo above native CG Pixel 3x5 platform/
version text, `UNOFFICIAL FAN MADE PORT BY DOX187`, original copyright/author,
website and A/Start prompt. The 0.73 per-frame timer and frozen finish panel,
and 0.72 held volt controls are retained. Both playable filenames include the
version and live directly in `build/`; the previous versioned builds are retained.

The retained 0.90 release has two cartridge builds, both targeting **MBC5 +
32 KiB battery-backed RAM** with the same 54 courses, graphics and physics:

| Build | Scenery | Versioned test image |
|---|---|---|
| **4 MiB** (4,194,304 bytes) | Lossless ZX0 compression | `build/elma-gbc-v0.90-4m.gbc` |
| **8 MiB** (8,388,608 bytes) | Uncompressed, read directly from ROM | `build/elma-gbc-v0.90-8m.gbc` |

The 8 MiB build avoids decompression during scrolling. Both share the same
player/record save layout, compatible with 0.7. The 8 MiB build retains the
four physics-table banks at **477–480**, directly after the scenery, as in
`elma-gbc-v0.7-8m-bankfix.gbc` (previously 508–511). Its final 64 KiB
is unused. All graphics and table bytes are retained. **The same motorcycle
failure was subsequently reported with that 0.7 build on FlashMaster, so the
relocation has not resolved the issue.** Version 0.90 does not change this
bank layout; physical-cartridge verification remains outstanding.

The original 0.7 8 MiB image (`build/elma-gbc-v0.7-8m.gbc`) had an immediate
motorcycle physics failure on FlashMaster. Its full physical cartridge scan
passed banks 1–507 and first failed at **bank 508: expected CRC16 `65FD`, read
`FFF0`** (2026-11-16, source
ROM SHA-256 prefix `dbf763f7f55c`). `FFF0` is also the checksum of a full bank of
`FF` bytes; it suggests blank or incorrectly mapped data, but a CRC alone does
not prove every byte or identify the cause. The reported settings are MBC5,
8M ROM and 32K RAM. This confirms readable nonempty graphics banks above 255;
it does not establish why the final physics-table banks read incorrectly.
Erasing bank 508 to `FF` in the emulator also destabilizes the motorcycle.

Simulating an inaccessible upper ROM half (banks 256–511 reading the
corresponding lower banks) also reproduces a detached wheel on the first
physics step. However, that simulation reads CRC `6F29` at bank 508, different
from the physical `FFF0` result; simple upper-to-lower aliasing is not confirmed.

The 0.6 build required **128 KiB SRAM**. The
[FlashMaster guide](https://ae01.alicdn.com/kf/S2f62136b14a64022bb70b3d32150367f6.pdf)
lists RAM settings only through 32K. Running the same 0.6 ROM with emulated
32 KiB RAM reproduced corrupt Warm Up graphics; 128 KiB rendered correctly.
Version 0.7 replaces the large lookup and relocates the decoded caches and
saves to four RAM banks. Changing the ROM-size setting alone cannot fix the
old SRAM layout.

An early native Game Boy Color version built with
[GBDK-2020](https://gbdk.org/docs/api/index.html), C and SM83 assembly.
**All 54 registered internal levels are selectable:** ride, brake, volt, turn
around, collect apples and reach the flower. Original level geometry, LGR
artwork and an adaptation of the existing original-derived fixed-point
motorcycle physics form its basis.

## What works in 0.90

- Parallel **4 MiB compressed / 8 MiB raw ROMs** containing all 54 courses,
  with a compact graphics lookup and a shared 32 KiB cartridge RAM layout.

- An original-logo title screen with native platform/version, unofficial port
  credit, original copyright/author and website text. A fresh A/Start press
  continues to a separate main menu and Controls screen.
- A level selector with all **54 registered internal levels**, their original
  names and order, page navigation, pause/resume and explicit restart actions.
- Four persistent player profiles, editable ten-character names with a framed
  Game Boy keyboard, and best times for each player on all 54 courses.
- CH3 engine sound using separate original idle/load cycles, reinforced by a
  CH1 exhaust pulse for speaker audibility, with quieter,
  constant idle without throttle. Throttle raises the volume and uses the
  original wheel-speed/pitch curve. Apple, crash and finish sounds use
  original-derived native pulse/noise contours; menu clicks are included.
  Pausing silences the engine.
- Native **CG Pixel 3x5 Mono** text in the level selector and HUD, with a
  four-pixel character advance and no downscaling of the original PC font.
- Riding, acceleration, braking, volts and turning around, with suspension,
  rider movement, **32-bit linear velocities** and swept head collisions.
- Rider integration on every physics step, using the updated body rotation
  after a volt, with exact SM83 coordinate and movement helpers.
- Held left/right volt input with the original shared cooldown, rounded up to
  a physics step. Pause freezes the cooldown and restart clears it.
- Apple collection, gravity-changing apples, killers, crash detection, flower
  completion and advancing to the next course. The HUD shows remaining apples,
  a labelled elapsed time refreshed with every riding frame; A/Start retries
  after a crash. The frozen finish frame shows the measured time, previous
  best, record comparison and next/retry/menu controls.
- Original level geometry and LGR artwork, streamed terrain, independently
  positioned wheels and head, **red apples and white flower petals**.
- A modest brightness lift for green scenery while retaining its original
  artwork and the protected source sky colors.
- Head pattern buffering to prevent uploads from changing the head still on
  screen, and separate terrain/background reduction to avoid invented sky
  colors at terrain edges.
- A reproducible GBDK build and emulator checks for arithmetic, physics state,
  menu navigation, all 54 course starts, scrolling VRAM and protected colors.

## Remaining work and known limits

- **Finish stable 30 FPS.** Some complete-game updates still exceed the
  two-display-frame budget (about 29.86 updates per second). Continue assembly
  and scrolling optimization while preserving direct controls, the current
  physics model and no additional frame queue.
- **Verify complete rides on every course.** All 54 levels have been selected
  and started through actual menu input; this does not establish that every
  level can be completed. Extend contact, high-speed and long-route testing,
  and compare the riding behavior with the original game.
- **Measure frame timing on a real Game Boy Color.** Current timing figures
  come from emulation.
- **Add replay support and an editor.** These are unimplemented. Verify the
  new player and best-time saves on the physical cartridge.
- **Check the new audio on hardware and refine its timbre.** Two representative
  32-sample, 4-bit engine cycles and pulse/noise effects approximate the original
  recordings; they do not reproduce the full PCM, changing exhaust texture or
  start/rev transition. The added CH1 layer deliberately strengthens exhaust
  harmonics; its volume and character need another speaker listening test.
  Music is unimplemented.
- **Review further graphics and animation improvements.** Object animation
  currently uses its first frame; the sky has no parallax and foreground
  pictures do not occlude the rider. Crowded object sprites can flicker under
  the hardware scanline limit, as accepted for this version. Trees, flags and
  barrels are intentionally omitted from rendering.

The physics is adapted from the original-derived fixed-point core; it is not
trajectory-identical to the PC integrator. The detailed differences and
verification limits are described below.

## Planned after 0.90

- **0.91: target stable 30 FPS**, starting with the measured scenery-update
  spikes, while preserving the current physics results and direct controls.
  Check both ROM sizes, all 54 course starts, Freefall and moving views.
- Check the brighter bushes and green decorations on a real Game Boy Color.
- Bring the menu closer to the original game's layout, colors and functions,
  while retaining readable native pixel text on the 160x144 display.
- Verify the relocated **8 MiB** physics tables on FlashMaster, then verify
  scrolling and retained player saves with both ROM sizes, MBC5, 32K RAM and
  Save RAM enabled. Keep the confirmed original bank-508 failure as a regression.
- Continue measuring compressed graphics streaming, including first-use
  decoding and cache misses during fast scrolling. Keep all 54 levels and
  the current physics; discuss any necessary graphics or gameplay
  simplifications before choosing a compromise.

## Physics fidelity research

The intermediate 0.90 release includes the current native rider corrections.
The higher-precision solver remains research: its host results are not the
physics running in the playable ROMs. Version 0.91 targets the existing core's
complete-game timing; the PC-fidelity requirements below remain open.

Acceptance priorities, in the requested order:

1. At least **99.9%** of aligned samples must keep every measured part within
   **1 cm** position, **0.1 degree** angle and **0.01 m per real second** linear
   velocity of the PC reference, with matching collision, apple and finish
   events. Evaluate each case, including both wheel angles; easy cases must not
   hide a failing route.
2. Then evaluate **0.1% relative error**, with explicit absolute tolerances near
   zero. Preserve the direct controls and the 30 Hz gameplay budget.

Integrating the higher-precision solver requires both the fidelity target and
stable 30 FPS. Passing host comparisons alone does not establish a playable
console implementation. Preserve direct controls without an extra frame queue.

The comparison links the original PC physics equations with their actual
headers. Generated test-only copies observe resolved wheel-contact transitions;
their complete numeric state is checked bit for bit against uninstrumented
builds. It uses identical timed controls and the original **0.0055
maximum step plus remainder** schedule at each GBC sampling time. Its native
`double` reference is the project's PC SDL arithmetic profile, not a claim of
bit-identical Windows x87 behavior. Baselines are reconstructed from Git with
their own constants generator; reports include source/library hashes, full
trajectories, shared live windows and event mismatches.

From the repository root:

```sh
python3 console/gbc/test/compare_pc_physics.py \
  --res build-reg/elma.res --baseline-ref 17c1493
python3 console/gbc/test/score_pc_fidelity.py \
  console/gbc/build/pc-comparison-v090/report.json --run both --require-target
```

The current 40-case corpus covers six original courses and controlled
acceleration, braking, suspension, landing, air and volt fixtures, plus an
original-PC Warm Up run that collects the apple and reaches the flower. The rider
now updates each physics step and uses post-volt body rotation. Exact SM83
coordinate/movement helpers reduce the cost, and native/HOST state agreement
is checked. This intermediate correction leaves substantial whole-bike
errors; it does not meet the fidelity target. Further work must address
integration timing, brake/contact behavior and numerical precision.

The contact-enabled comparison observes both wheels' resolved contact counts,
transition order and enclosing frame intervals. All 40 cases have validated
contact coverage; both 0.84 and the current rider correction fail the primary
acceptance requirement in all 40 cases. This is an all-component threshold,
not a percentage estimate of how recognizable the game feels.

Separate arithmetic feasibility studies replay a longer 40-case corpus. Full
float32 arithmetic accepts 84.73% of its 10,203 live samples. The first checked
Q44 fixed variant accepted 92.17%: rounding a segment-length reciprocal tilted
the contact normal even on flat ground. Dividing each segment component directly
by its length fixes that particular bias. Together with the independently
verified rider-spring cancellation, the corrected Q44 variant passes all 40
cases and 10,203 live samples. All 817 ordered wheel-contact transitions also
match the original PC observation times, with instrumentation preserving the
complete underlying state bits.

An independent holdout adds four scripts on every internal course: neutral and
brake for 1,800 samples each, plus two seeded 900-sample control sequences.
Q44 passes 215 of these 216 cases. Q46 also passes 215, accepting 174,552 of
174,564 live samples overall (99.9931%). The remaining case, a minute at rest
on What the Heck, passes only 99.3333%: wheel velocity differs by up to
0.0121 m/s against the 0.01 m/s limit. Pooling easier cases cannot pass the
per-case requirement. Holdout object/terminal events match; its nonfatal contact
coverage has not yet been validated. Pure relative-error diagnostics also
remain separate from the primary absolute-tolerance result.

These studies use host trigonometry and do not establish a native GBC solver.
A separate byte-limb arithmetic ROM passes 2,050 integer-oracle checks, but a
dense 52-bit state product averages 6.80 ms and general wide division averages
34.70 ms in that C implementation. Those costs require substantial
specialization; they are not lower bounds for assembly or a full-game timing
result. The research corpus differs from the production-core comparison above,
and its scores cannot be substituted for that release gate. Versions 0.80
through 0.84 share the same production physics; their changes concern sound.

## Build and run

Requirements: Make, Bash, Python 3, a host C compiler for tests, curl and tar,
plus `elma.res` and `default.lgr` from your own copy of the game. The converters
use numpy and Pillow, and the emulator tests use PyBoy. From this directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
make bootstrap
make 8m ELMA_RES=/path/to/elma.res ELMA_LGR=/path/to/lgr/default.lgr
```

The defaults are `ROM_MIB=8 PHYS_HZ=30 DAMPER=exponential`.

The current checkout builds versioned **0.91 development ROMs**. They are not
accepted releases until their complete-game timing and regression checks pass.
The retained 0.90 images below are the last completed intermediate release.

Open **`build/elma-gbc-v0.90-4m.gbc`** (4 MiB) or
**`build/elma-gbc-v0.90-8m.gbc`** (8 MiB) in a Game Boy Color emulator.
These are CGB-only MBC5 cartridges, not Game Boy
Advance programs; monochrome Game Boy hardware is unsupported. Both use header
type `0x1B` (MBC5+RAM+BATTERY), RAM code `0x03` (32 KiB), and ROM code `0x07`
(4 MiB) or `0x08` (8 MiB).

`make 4m` and `make 8m` keep generated files separate in `build/gen` and
`build/gen-8m`. For an explicit output name, use e.g.
`make ROM_MIB=8 GAME_ROM=build/elma-gbc-v0.91-test-8m.gbc game` with your resource
paths. Both Make and the standalone builder read `VERSION` for their default
playable filenames. Original rendered tiles are reused when their fingerprints
match; codec and bank-layout mismatches are rejected before linking. Exact physics
tables live at ROM banks 252–255 or 477–480, respectively. The 8 MiB builder
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

Without gas, the selected idle cycle plays at approximately **103 Hz, 50% wave
level**, independently of wheel speed or braking. With gas, the separate loaded
cycle starts at **57.3 Hz, 100% wave level**, reaching about **111 Hz at the normal
driven-wheel limit** and approaching 114.6 Hz at extreme speed. These preserve
the selected cycles' original duration; the full recordings are nonstationary
and have richer spectra. Their perceived pitch is not just these base rates.
The generated 512-entry table converts native angular velocity to original
radians/model-second before applying `2 - exp(-min(abs(omega)*0.025, 30))`.
Braking changes audio through the physical wheel speed, without a separate
artificial pitch division. The former 96–344 Hz idle-wave transposition is gone.

CH1 uses a **12.5% pulse, volume 3 at idle / 8 under throttle**. Sharing CH3's
period value puts it exactly at the second harmonic: about 206 Hz at idle and
115–229 Hz under throttle. CH3 itself is not transposed. The narrow pulse adds
exhaust harmonics while keeping its second-harmonic amplitude below the original
loaded cycle's fundamental. Its sweep and automatic volume envelope are off;
speed changes update the period without retriggering. Mode changes retrigger
once to apply the new volume. CH1's duty phase survives retriggering, so the
combined peak level can vary with relative phase. Each update refreshes both
channels' 250 ms length watchdogs; both DACs are silenced when the engine stops.

The 0.82 CH3 output levels roughly double engine amplitude while keeping idle
quieter than gas. The physical CGB's analog high-pass filter attenuates the low
engine cycles more than the high menu beep; raw emulator PCM alone misses this
balance difference. The native fixture additionally reports a relative-level
proxy using the [Pan Docs CGB capacitor model](https://gbdev.io/pandocs/Audio_details.html#obscure-behavior).
It does not model the built-in speaker or replace a hardware listening test.

The converter derives the apple pulse contour from `eves.wav`, and crash/finish
noise contours from `torik.wav` / `siker.wav`. It uses the original mixer's
11025 Hz rate, even where the WAV header differs. Four-VBlank control points
describe pitch/noise colour, loudness and hardware envelope; the source-based
durations are 38, 59 and 46 VBlanks respectively. These are native APU
approximations, not full PCM playback. Generated `audio-manifest.json` records
source hashes, cycle selection and effect measurements. Finite hardware lengths
stop sounds if servicing ceases; there is no background music.

Crash/finish now peak at volume 15; the menu remains at 8 and apple at 10, with
master level 6/8 on both outputs. Each noise control point retriggers the 15-bit
LFSR, whose startup requires 15 clocks. Candidate noise rates must start within
one VBlank, leaving most of each four-VBlank control interval audible. The old
128/146 Hz settings took longer than the entire interval and produced silent
crash sections. This constraint adjusts noise colour offline, with no additional
cartridge CPU cost; engine waveform, pitch and effect durations are preserved.

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

`PHYS_HZ=60 DAMPER=explicit` remains available as a comparison profile. Selecting
it is not a claim that the complete game meets a 60 FPS budget. The standalone
`physics-probe.gbc` is an older suspension diagnostic, not the riding solver or
a measure of full-game performance.

## Verification

```sh
make check ELMA_RES=/path/to/elma.res ELMA_LGR=/path/to/lgr/default.lgr
```

`make check` builds the playable and diagnostic ROMs, checks conversion, ROM
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
The 0.73 result checks below use an explicit contact fixture and do not claim
a new controller-completed course.

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

For 0.90, both complete ROMs pass frontend, held-volt, finish-audio and
player/record checks, including save reload in both directions between sizes.
The clock check verifies 1,890 exact presentations, minute rollover and one
LCD update every two display frames. All 54 course starts and the complete
433-step no-input Freefall pass their functional checks: source scenery,
object colors, moving head buffers, 32-bit velocities and camera tracking.
The strict timing assertions still fail, as recorded below. These are the
baseline for 0.91, not a stable-30-FPS claim.

| 0.90 deadline misses | 4 MiB ZX0 | 8 MiB raw |
|---|---:|---:|
| 54 course starts, 12 idle updates each | 13 | 6 |
| No-input Freefall | 54 | 13 |
| 300-step Warm Up driving profile | 4 | 0 |

The 4 MiB native decoder independently checks all 4,800 unique scenery blocks
(6,034,992 decoded bytes), with zero byte, guard or bank-restoration failures.
The splash pixel check also passes. Reports are under
`build/v090-release-checks` and `build/splash-v090-release`; the two versioned
ROMs remain directly in `build`. Physical-cartridge testing is still needed.

For 0.84, the native fixture verifies CH1 volume 3 at idle and volume 8 under
load, including the emitted pulse PCM. Pitch, duty, original CH3 cycles,
watchdogs and effect checks pass; the maximum audio update remains 2,844 cycles.
Both complete ROMs pass frontend checks covering the new levels, throttle/coast,
pause/resume and version text. The new balance still needs a hardware audition.

For 0.83, the unchanged CH3 cycle shapes and pitch curve pass independently
with CH1 temporarily excluded from the fixture mixer. The isolated CH1 PCM
has **12.48% duty** and exactly twice the CH3 rate within measurement precision.
Both channels trigger only on starts/mode changes, survive 30 Hz servicing and
stop on pause/finish or after a 15-VBlank watchdog timeout. The CGB filter
proxy measures **8.98 dB more idle, 11.28 dB more low-gas and 10.00 dB more
fast-gas output** than 0.82; this is not a physical speaker measurement.
Engine-only updates take **816–1,132 cycles**, with a **2,844-cycle** maximum
including a mode switch and effect. Both complete ROMs pass frontend and
finish-audio checks; the 0.83 splash also passes its pixel check. The 300-step
controller profiles retain **four deadline misses for 4 MiB, zero for 8 MiB**.

For 0.82, unnormalized native PCM measured engine RMS increases of **5.85 dB
under throttle / 6.20 dB at idle**, crash **4.04 dB** and finish **3.38 dB**;
menu/apple levels are unchanged. The CGB HPF proxy estimates **7.40 dB** more
crash output after removing silent slow-LFSR intervals. Noise control-point
checks at both 30 and 60 Hz catch the previously silent sections.
The original engine cycles/pitches, finite effects and IRQ/bank checks still
pass. The largest audio update remains **2,552 cycles**. Both complete ROMs
passed frontend and finish-audio checks, and the 0.82 splash text passed its
pixel check. The 300-step controller profiles exactly match 0.81's measured
costs: **four deadline misses for 4 MiB, zero for 8 MiB**. Physical hardware
volume balance remains to be checked; the filter proxy omits speaker response.

For 0.81, all 65,536 speed arguments were checked against the original formula
with independently converted physics units; the maximum lookup plus hardware
rounding error was below **0.607 Hz**. Native PCM checks cover both cycle shapes,
source playback rates, speed boundaries, rapid throttle changes, effect/engine
overlap, muting, watchdog, IRQs and ROM-bank restoration. Every observed wave-RAM
write occurs with the DAC off. Steady engine updates take **596–924 cycles**;
the largest update including a throttle transition and an effect is **2,552
cycles**. Both complete ROMs passed frontend, finish-audio and splash checks.
The 300-step driving profile retains **four deadline misses for 4 MiB and zero
for 8 MiB**, as in 0.80. These results do not establish physical-cartridge sound
quality or stable 30 FPS on every course.

For 0.80, the same splash check passed with the new version label. The native
audio fixture captured 48 kHz PCM at both 30 and 60 Hz service rates. It verified
the engine waveform (0.9957 correlation to the quantized cycle), continuous
87.93 Hz idle, throttle/coast changes, only one trigger during continuous
running, no active wave-RAM writes, effect durations/priority, skipped updates,
timer wrap, the hardware watchdog and bank/IRQ preservation. The largest
measured `audio_update` was **1,240 cycles**, including simultaneous engine and
apple sound, versus 4,084 in the previous fixture; engine-only calls took
620–788 cycles. These are emulator measurements, not a listening comparison.

Both complete 0.80 ROMs passed frontend, player/record and cross-size save
reload checks. `test/check_finish_audio.py` also verifies audible onset, body
and tail after the frozen panel is visible, engine muting, and a finite stop.
It uses the explicit flower-contact fixture described below. A 300-step
controller-only driving profile retained the 0.74 deadline-miss counts:
**zero for 8 MiB, four for 4 MiB**. Real-cartridge audio quality and stable
30 FPS across all courses remain to be verified.

Both 0.72 ROMs passed the frontend check with continuous quiet idle PCM, throttle
volume and return to idle while coasting. The native audio fixture measured
87.93 Hz idle over 1.205 seconds and verified uninterrupted PCM between 30 Hz
updates, no-gas braking, throttle return, mute/resume, effects and bank restoration.
`test/check_volt_input.py` drives Freefall through actual controller input and
observes accepted physics commands without writing guest state. Both ROMs passed
held repeats in both directions, the shared 28-step cooldown, early held/released
input, pause and restart. These checks do not establish physical-cartridge behavior.

`test/check_save.py` compiles the production save module for the SM83 and
tests battery-file reboots, player/course isolation, faster-time replacement,
invalid requests, interrupted writes, CRC rejection and generation rollover.
It also checks that the graphics SRAM banks remain untouched. The 32 KiB run
passed 47 fresh boots, including 12 interrupted-write cases.

`test/check_players.py` drives the real name keyboard, selection, timer, pause,
crash and A retry through buttons, then reloads the battery file in a fresh
emulator. Its finish check supplies an unlocked-flower contact to exercise the
normal result/save path; it does not claim a controller-completed course.
For 0.73, both sizes passed all four finish comparisons, frozen scenery/sprite
preservation, result/detail toggling, next/retry/menu controls, and save reload
in both directions between ROM sizes. Each clock run checked 1,890 exact
presentations including minute rollover, with 90 actual LCD changes in 180
display frames and no idle deadline misses. A 300-step driving profile retained
the 0.72 deadline-miss counts: zero for 8 MiB and four for 4 MiB. The stable
30 FPS target across all courses and physical-cartridge save test remain outstanding.
The 32 KiB native cache fixtures each passed 3,031 verified views for raw and
compressed graphics. All 2,048 save bytes survived, requested RAM banks stayed
within 0–3, and bank3 cache eviction/reload was checked through address BFFF.

Both complete 0.7 ROMs passed all 54 course starts and the frontend/player
checks under a 32 KiB RAM configuration. Battery saves loaded in both
directions between the two ROM sizes. These are emulator results, not a
physical FlashMaster test or proof that every course can be completed.

| 0.7 diagnostic | 4 MiB ZX0 | 8 MiB raw |
|---|---:|---:|
| Longest course load, display frames | 75 | 21 |
| Deadline misses across 54 course starts | 13 | 4 |
| Deadline misses in no-input Freefall | 52 | 10 |

The relocated 8 MiB build passed 648 native coefficient vectors, all 54 course
starts and Freefall with the same 4/10 deadline-miss counts. Byte comparisons
confirm that banks 1–476 and all moved physics tables are unchanged; ROM0 only
changes the coefficient bank immediate and global checksum. The cartridge
diagnostic passed all 511 switchable banks and rejected a simulated alias.
The physical report for `elma-gbc-8m.gbc` still describes the same failure;
that file is byte-identical to `elma-gbc-v0.7-8m-bankfix.gbc`.

A separate rebuild of all 517 sources without cached objects produced the
same SHA-256 (`1eb65d4be66b785bdbb81147ddcb64f373268b2bcb57d8c195664d501f877049`).
Independent checks matched 453 generated byte arrays to their linked ROM
offsets and verified headers, checksums, coefficient descriptors and ROM-bank
bounds. These checks found no static packing/linking defect; they do not rule
out a runtime banking or SRAM problem on hardware. The standalone cartridge
reader replaces ROM0 and never exercises the game's SRAM-dependent runtime.

The 8 MiB build is faster in the emulator. Both still miss the strict stable-30-FPS
target; the diagnostic runs explicitly allow deadline misses while verifying
graphics and physics. All 4,800 unique compressed
graphics blocks decoded exactly with SRAM guards on the 32 KiB fixture, and
both coefficient placements passed 648 native vectors plus exhaustive host
checks without bank-restoration failures.

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
