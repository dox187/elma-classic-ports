# Elasto Mania for Game Boy Color

Current version: **0.4 — development prototype**. The port version is kept in
[`VERSION`](VERSION).

An early native Game Boy Color version built with
[GBDK-2020](https://gbdk.org/docs/api/index.html), C and SM83 assembly.
**All 54 registered internal levels are selectable:** ride, brake, volt, turn
around, collect apples and reach the flower. Original level geometry, LGR
artwork and an adaptation of the existing original-derived fixed-point
motorcycle physics form its basis.

## What works in 0.4

- An original-artwork title screen with the port version and a fresh A/Start
  press to continue, followed by a separate main menu and Controls screen.
- A level selector with all **54 registered internal levels**, their original
  names and order, page navigation, pause/resume and explicit restart actions.
- Native GBC engine sound reacting to throttle, braking and wheel speed, plus
  menu, apple, crash and finish effects. Pausing silences the engine.
- Native **CG Pixel 3x5 Mono** text in the level selector and HUD, with a
  four-pixel character advance and no downscaling of the original PC font.
- Riding, acceleration, braking, volts and turning around, with suspension,
  rider movement, **32-bit linear velocities** and swept head collisions.
- Apple collection, gravity-changing apples, killers, crash detection, flower
  completion and advancing to the next course. The HUD shows remaining apples,
  elapsed time and ride status.
- Original level geometry and LGR artwork, streamed terrain, independently
  positioned wheels and head, **red apples and white flower petals**.
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
- **Add persistent saves and replay support.** These are unimplemented, as is
  an editor. Cartridge RAM currently serves only as graphics scratch space.
- **Improve audio fidelity.** The current effects are synthesized GBC APU
  adaptations rather than the original PCM samples; music is unimplemented.
- **Review further graphics and animation improvements.** Object animation
  currently uses its first frame; the sky has no parallax and foreground
  pictures do not occlude the rider. Crowded object sprites can flicker under
  the hardware scanline limit, as accepted for this version. Trees, flags and
  barrels are intentionally omitted from rendering.

The physics is adapted from the original-derived fixed-point core; it is not
trajectory-identical to the PC integrator. The detailed differences and
verification limits are described below.

## Planned after 0.4

- Bring the menu closer to the original game's layout, colors and functions,
  while retaining readable native pixel text on the 160x144 display.
- Reduce the cartridge image size. The **8 MiB** ROM boots and plays on the
  tested cartridge, but its size frequently leaves graphics garbled or missing.
  Flash a **4 MiB** build to the same cartridge and check that graphics display
  correctly during play. If 4 MiB is still too large, target **2 MiB**.
- Measure graphics storage and compression options first, including shared
  patterns and tile-map encoding, together with their runtime CPU and RAM
  costs. Keep all 54 levels and the current physics; discuss any necessary
  graphics or gameplay simplifications before choosing a compromise.

## Build and run

Requirements: Make, Bash, Python 3, a host C compiler for tests, curl and tar,
plus `elma.res` and `default.lgr` from your own copy of the game. The converters
use numpy and Pillow, and the emulator tests use PyBoy. From this directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
make bootstrap
make ELMA_RES=/path/to/elma.res ELMA_LGR=/path/to/lgr/default.lgr
```

The defaults are `PHYS_HZ=30 DAMPER=exponential`.

Open **`build/elma-gbc.gbc`** in a Game Boy Color emulator. It is a CGB-only
MBC5 cartridge, not a Game Boy Advance program, and does not support monochrome
Game Boy hardware. The ROM occupies 8 MiB and requires an MBC5 cartridge with
128 KiB RAM. Cartridge RAM is scratch space for the graphics cache; it does
not contain persistent saves. Exact mathematical tables accelerate fixed-point
arithmetic without changing its results.

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
Choose Play, Level Select or Controls; the pause menu offers Resume, Restart,
Level Select and Controls. B returns from a sub-screen, then resumes a paused
ride from the main menu. After finishing, A starts the next course;
after a crash or finish, B or Select opens the main menu.

The HUD shows apples remaining and elapsed time, then crash, pause or finish
status. Volts are triggered by a new button press and have a cooldown.

Audio uses the GBC pulse and noise channels, serviced by the existing main
loop without a streaming interrupt. The engine responds to driven-wheel speed;
short effects have finite durations and hardware length limits. There is no
background music or playback of the original digitized sound samples.

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
Raw banked tile maps avoid decompression stalls. The remaining bank0 patterns
hold the killer sprites.

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

The final controller-only regression exercises controls, braking, pause,
head-collision death and restart, then collects the apple and reaches the
unlocked flower alive. It verifies actual tile, attribute and pattern VRAM across
map/chunk boundaries. It defaults to **zero allowed deadline misses** and does
not inject completion or object state into game RAM.

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
