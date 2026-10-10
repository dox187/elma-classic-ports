# Elasto Mania SNES demake

Current version: **0.1 alpha** (kept in [`VERSION`](VERSION)).

An unofficial, fan-made version of Elasto Mania for the Super Nintendo,
made to look and play like the PC original. It is a separate program, not a
port of the game's code: the levels, pictures, fonts and sounds of the game
are converted from your own copy, and the physics of the game (`LEPTET.CPP`,
`BEALLIT.CPP`, `UTKOZES.CPP`) is rewritten in fixed point and 65816
assembly.

- The internal levels of the game, unlocked one by one as in the original,
  with their ground, grass, sky and pictures, the apples, flowers and
  killers, the time and a corner counter showing the apples still needed.
- The bike and the rider are drawn from the pictures of the LGR file, as
  the original draws them, at 0.4 of their size: the SNES shows the same
  part of the level on its 256 pixels as the original on 640.
- The camera keeps the bike's body at the center. Drawing interpolates
  between the 80 Hz physics steps; turns and gravity changes stay discrete.
- The menus of the original with its fonts and background: players, the
  levels finished, the best ten times of each level, Options (Sound,
  Animated Menus, Video Detail, Animated Objects, Customize Controls) and
  Help. They are saved in the battery-backed RAM of the cartridge.
- The engine, friction and effect sounds of the original, mixed on the
  sound processor as the original's mixer does.
- Not included: the level editor, external levels, replays, the demo and
  two players.

<p>
  <img src="docs/title.gif" width="256" alt="The intro, choosing the player and the main menu">
  <img src="docs/levels.gif" width="256" alt="The list of the levels">
  <img src="docs/gameplay.gif" width="256" alt="Native 256 by 224 Warm Up gameplay: apple pickup, jumps and finish">
</p>

The title, menu and level-list images above are from an earlier NTSC build.
The gameplay GIF is a fresh 256 by 224 capture of the current NTSC gameplay
in MesenCE 2.2.1. It shows the Warm Up route, collecting the apple, jumps
and reaching the finish.

The ROM is a LoROM cartridge with FastROM, 4 MB of ROM and 8 KB of
battery-backed RAM. It has been tested in emulators only (Mesen 2 and
snes9x). No enhancement chip is required; the changes described below were
validated in MesenCE 2.2.1.

## Known issues

This version does not give the experience of playing the original game, and
it may have bugs.

- Under extreme scrolling workloads, the edges of the level that come onto the
  screen (the ground against the air, the grass and the pictures) are drawn
  late: for a moment they show the plain texture of the ground or the air,
  until the console catches up. The console makes these parts of the
  picture while the level scrolls, in the time that the physics leaves of a
  frame.

## Physics

The physics runs 80 steps a second, as close to the original's 0.0055 game
time units a step as the console allows (the original's physics becomes
unstable with steps of 60 a second). `test/phys_spec.c` describes it in C;
the assembly follows it to the bit. Collision checks use the level's vector
geometry. Decoding map chunks prepares graphical tiles and does not change
those collision vectors.

The rendering changes preserve the existing SNES solver and its quirks.
Intermediate steps skip only drawing and sound-output calculations. No due
simulation steps are discarded when a frame is late. Interpolation uses a
temporary drawing view, restored before simulation resumes.

The full PC comparison now covers 134 cases: the original short tests,
the complete Warm Up script, and two seeded 30-second input scripts on all
54 levels. The current solver accepts 73.00% of samples within all of the
position, velocity, angle and angular-velocity tolerances together; 18
cases differ in important object or terminal events. The strict score
takes the worst case and rejects a case with a changed event chronology,
so it is currently zero. The 99% target has not been achieved. Rendering
regressions compare full SNES traces; their bit-exact agreement does not
establish PC fidelity.

`test/fidelity_check.py` retains the corpus, reference-source hashes,
tolerances and compressed full traces. `test/contact_check.py` probes the
same contact from each accumulated trajectory and a common prior state.
For example, Warm Up step 256 loses a wheel contact because accumulated
position error puts it outside the unchanged vector endpoint radius. The
collision radius and force-sign rules are preserved while higher-precision
equation variants are evaluated. `test/fidelity_compare.py` reports both
fixed cases and newly failing cases, including when an aggregate improves.

An isolated integer reference now passes all tolerances and exact critical
events on the 134 cases and a separate 242-case holdout (four new seeded
scripts per level plus the original fixtures). Its maximum holdout position
error is 0.086 mm. `test/wide_probe.py` transforms copies of the original
equations to checked Q36 integer arithmetic, integer square roots and table
trigonometry; floating conversion is used only for trace output. This is a
host reference, not the solver in the ROM. Its expensive general arithmetic
still needs a specialized SNES implementation and the same frame tests.

Subsequent references fold time, mass and inertia into the force equations,
store velocity and angular velocity in per-step units, and integrate compact
Q32 positions/unwrapped angles with Q40 per-step rates. These combined host
variants retain the full acceptance and holdout passes. Narrowing every
per-step intermediate to Q36 fails a holdout event and is rejected; Q38
passes both corpora. This is separate from the original unscaled Q36 model.

An additional 109-case endurance corpus holds neutral input or the brake
for 60 seconds on every level, plus the Warm Up fixture; 83 cases survive
the full minute. This exposes resting-contact jitter that the shorter
corpora missed: the compact Q32/Q40 candidate falls to 96.46% in its worst
case. The current Q44 per-step reference reaches 99.3125% in the worst
endurance case, with zero critical-event differences, and 100% on the
134-case acceptance and 242-case holdout corpora. Narrower position and
normal-vector storage has not met this longer check.

The same Q44 results now hold for a complete plain C step, arithmetic and
binary level loader (`build/wide-loaded-q44-v3`). The host executable links
no original C++ physics or level construction; C++ provides test I/O and
state marshalling.
This remains a host result. Its control and loader compile with 816-TCC,
but the complete native solver has not yet established either fidelity or
60 FPS. The general native multiply/divide/root routines are currently too
slow; their component tests must not be reported as a frame-rate pass.
The native Warm Up GAS16 check now agrees in all 17 complete raw states
with the host word reference: body, wheels, rider, head, brake/jump history,
object activity, game time and events. All 32 stack/flag canary cases pass.
Exact assembly scalar operations and original-table trigonometry reduce
the median measured command/step/snapshot cycle from 81,300,766 to
24,300,888 and then 13,937,274 master clocks (82.86% below the baseline).
The selected experiment is `build/wide-native-step-q44-fast-trig-v2`.
These measurements include test-driver and frame-sampling overhead. Even
this faster version is far outside the game budget; GAS16 is not a full
native fidelity corpus pass. A later combined cache/filter/literal variant
fails native state comparison and is excluded from the selected build.

The long reference tests also exposed a harness scheduling error: comparing
an accumulated floating clock with a multiplied sample target inserted an
extra matched PC step at sample 3187. Matched mode now calls the PC solver
exactly once per sample. `test/trace_schedule_check.py` checks 8,000 samples
in both matched and capped modes. The frozen `fidelity-endurance-v2` corpus
uses the corrected schedule; the original acceptance and holdout cases
all terminate before that clock error.

`test/wide_level_export.py` preserves all raw segment caches, initial state
and grid-list order. Its optional lossless geometry packing reduces the
54-level snapshots from 1,065,065 to 683,063 bytes, with exact decoding of
all 477,357 grid cells. The C loader retains only the current cell's linked
nodes, rather than allocating the original full linked grid.
`wide_level_banks.py` places each payload in a separate LoROM section;
`wide_level_banks_check.py` verifies every ROM byte and all 432 sections
through compiled native far-pointer reads. The split-section C loader and
the C coarse object filter each preserve all 545,029 full trace rows across
458 distinct cases. Integration into the production ROM remains pending.

Exact broad-phase checks reject 58% of candidate segment tests and 99.8% of
object squared-distance tests on the acceptance corpus, preserving every
full state/event trace. The segment bounds additionally pass 2,073,150
original-function comparisons across all 8,130 segments in the 54 levels.
Together with per-step units and paired trigonometry, these filters reduce
scalar products from about 286 to 116 per physical step; helper products,
root algorithms and filter comparisons are counted separately. These are
host operation counts, not measured SNES frame rates.

Native component ROMs independently check wide integration and arithmetic
against integer references, including overflow/rounding boundaries and
injected NMI latch interruptions. The compact integrator is exact in 3,416
cases (median 1,354 master clocks per scalar update, including entry and
register restoration). A complete native high-precision solver and its
60 FPS validation remain work in progress.

## Speed

A typical physics step takes about 98,000 master clocks. Exact coefficient
tables remove repeated arithmetic without changing solver outputs. The
game publishes each prepared picture, computes upcoming physics while it
awaits NMI, then waits before reusing its OAM/DMA buffers. Initial physics
also overlaps the initial picture's pending presentation. Simulation debt
is retained at the same fixed timestep.

NMI scroll writes share a hardware latch with the Mode 7 multiplier used
by physics. Each coefficient setup preserves its first write; NMI restores
that latch through an unused Mode 7 register without changing the product.
`test/m7_latch_check.py` injects scroll writes between coefficient writes
and includes a failing negative control. Controller edges are acknowledged
atomically with TRB, retaining a different edge arriving during the read.
Sampling input earlier in the pipeline can add up to one video frame of
controller latency relative to the blocking loop.

The map prepares a 39 by 32 tile window around the viewport, batches plain
texture work and shares the frame deadline and DMA budget with the sprites.
If physics has already missed a display deadline, map work uses the time
available before the following deadline. The former minimap is replaced by
an outlined apple counter, removing its per-frame work and about 330 KB of
generated ROM data. The camera uses integer assembly math, and unchanged
relative bike poses reuse their exact drawing geometry.

`test/perf_check.py` records presented FPS, physics frequency, DMA timing,
backlog and complete per-step state/event traces. `test/map_check.py
--moving-every N` also checks visible tiles during motion, without waiting
for pending graphics work to finish. Settled screenshots alone do not
establish that scrolling is correct.

Measured with MesenCE 2.2.1, registered 1.11a data and the same
`test/warmup_finish.txt` step script on each listed level (other levels may
end before Warm Up does). The integrated pipeline delivers a new picture on
all 2,375 measured steady NTSC NMIs across Warm Up, Hi Flyer, Gravity Ride,
Bowling and Downhill: the console's native 60.098 Hz. Full state/event
traces remain identical, with no discarded physics steps or DMA overruns.
The broader `test/benchmark_corpus.py` run covers all 54 levels with two
seeded input scripts per level: 27,274 fresh steady NTSC pictures and zero
missed presentations in 459 seconds of gameplay. Of its 108 runs, 105 meet
the minimum measurement duration; three end too early on death. Every
level has at least one sufficient-duration pass. The scripts allow 30
seconds but stop on death; the longest run lasts about 14.6 seconds. These
results establish the measured workloads, not every possible input.

`test/benchmark_check.py` requires every steady NMI to consume a distinct
new picture within one video interval of submission, with no overwritten
pending picture or DMA overrun. It retains elapsed work, explicit wait and
active-work p95/max separately. A pipelined physics/render job may span
NMIs while meeting every presentation deadline, so its elapsed job time
alone is not a dropped-frame criterion. `test/iteration_ledger.py` records
separate ROM versions and both physics and presentation results.

| Iteration | Weighted fresh NTSC pictures/s | Missed presentations | PC all-component samples |
|-----------|--------------------------------|----------------------|--------------------------|
| Baseline | 52.52 | 12.616% | 73.00% |
| 1: exact view copies | 53.07 | 11.691% | 73.00% |
| 2: interpolation arithmetic | 53.78 | 10.513% | 73.00% |
| 3: camera multiplication | 53.96 | 10.219% | 73.00% |
| 4: exact solver tables | 54.66 | 9.045% | 73.00% |
| 5: presentation pipeline | 60.10 | 0% | 73.00% |

Each result retains scripts, ROM hashes, full state/event traces and raw
timings under `build/iterations.json` and the referenced artifact folders.
Physics precision experiments stay separate until their full comparison
and assembly implementation are validated.

## Build

Requirements:

- [PVSnesLib](https://github.com/alekmaul/pvsneslib) 4.6, found through
  `PVSNESLIB_HOME` or in `~/pvsneslib`, `~/.local/share/pvsneslib`;
- GNU Make 4.3 or newer;
- Python 3 with numpy and Pillow;
- `elma.res` and an LGR file from a legally obtained copy of the game, both
  of them: `elma.res` has the levels, the fonts and pictures of the menus
  and the sounds, the LGR file the bike, the rider, the objects, the
  textures, the grass and the pictures of the levels.

The game's files are copyrighted: they are not part of this repository and
neither is anything made from them. Everyone builds the ROM from their own
copy of the game, and the ROMs must not be shared. These copies work:

| Game | `ELMA_RES` | `ELMA_LGR` |
|------|------------|------------|
| Steam release | `base/elma.res` | `base/lgr/default.lgr` (the remastered pictures) or `base/lgr/orig.lgr` (those of the original) |
| Registered 1.11a | `Elma.res` | `Lgr/Default.lgr` |
| Shareware 1.1 or 1.11a | `elma.res` | `lgr/default.lgr` |

```sh
cd console/snes
make ELMA_RES=/path/to/elma.res ELMA_LGR=/path/to/default.lgr
```

Without `ELMA_RES` the build uses `../../elma.res`, the `elma.res` in the
root of the repository; without `ELMA_LGR` it looks for `lgr/default.lgr`
next to `elma.res`, in any case of letters. `make clean` removes `build/`
with the ROMs and everything generated from the game.

A ROM is written for each TV system, `build/elma_ntsc.sfc` and
`build/elma_pal.sfc`, or `build/elma_sw_ntsc.sfc` and `build/elma_sw_pal.sfc`
from the shareware game (its 18 levels and Please Register, the level after
them). The program is the same, only
the region in the header differs; on a PAL console the game keeps its speed.
Options:

- `TV=ntsc` or `TV=pal`: only the ROM for one TV system.
- `PHYS_HZ=80`: steps of the physics a second (see above).

## Controls

The buttons of a level can be changed in Options, Customize Controls, as in
the original; these are the buttons at the start:

| Button            | In a level                         |
|-------------------|------------------------------------|
| B                 | Gas (Throttle)                     |
| A                 | Brake                              |
| Left, Right       | Volt (Rotate left, right)          |
| X                 | Turn around (Change direction)     |
| Select            | Apple counter on and off           |
| L                 | Time on and off                    |
| Start             | Leave the level (the original's Esc, cannot be changed) |

As in the original, there is no pause: leaving a level shows the menu
after it, as a crash does.

In the menus Up and Down move, L and R turn a page, A or Start chooses and
B goes back. A name is entered with Up and Down changing the last letter,
Right adding a letter and Left removing one.

## Tests

The tests run the ROMs in the test runner of
[Mesen 2](https://github.com/SourMesen/Mesen2) (`test/mesen.py`, without a
window); the physics checks also need a C and a C++ compiler for the host.

| Command | What it checks |
|---------|----------------|
| `make phys-check` | the physics in C against the original's, and the assembly against the C to the bit, with its time a step (its cases need the levels of the registered game) |
| `make tests` | builds the test ROMs of the parts below |
| `test/play.py` | plays a level with the keys of the original from its first frame, or with the keys of each step of the physics (`--steps`) |
| `test/finish_test.py` | finishes Warm Up with the keys of the steps found by `test/finish_search.py` (on the host, with the physics in C; `make build/host/physplay.so`), to the hundredth of the time it predicts |
| `test/map_check.py` | the background of the levels in the video memory against the converted data |
| `test/bike_test.py` | the sprites of the bike against a model of the original's drawing |
| `test/hud_check.py` | the outlined time and apple counter across backgrounds and visibility settings |
| `make render-check` | drawing interpolation, angle wrapping, discrete changes and restoration of the physics view |
| `test/camera_check.py --res PATH` | centered camera arithmetic for every level and fixed-point boundaries |
| `make coreframe-check` | shared deadlines across missed frames and DMA budgeting with a nonzero direct page |
| `test/perf_check.py` | presentation speed, DMA deadlines and complete physical traces against reference ROMs |
| `test/keys_persist.py` | custom bindings, including Apple Counter, through an options save and reboot |
| `test/ui_test.py` | the menus, the players and the best times in the SRAM |
| `test/snd_compare.py` | the sounds against a model of the original's mixer |

## Sources

| File                  | Content                                              |
|-----------------------|------------------------------------------------------|
| `src/core.asm`        | The frame loop: the NMI, the queue of transfers, the joypad |
| `src/main.c`, `src/game.c` | The menus and the levels after each other; playing a level |
| `src/phys.asm`        | The physics and the objects in 65816 assembly        |
| `src/game_render.asm`, `src/game_math.asm` | Drawing interpolation and centered camera arithmetic |
| `src/map.asm`         | The ground, grass, pictures and sky, loaded as the camera moves |
| `src/bike.asm`, `src/objects.asm` | The bike, the rider and the objects as sprites |
| `src/hud.asm`         | The time and the apple counter                       |
| `src/ui*.c`, `src/save.c` | The intro, the menus and the saved state        |
| `src/snd.asm`, `spc/driver.asm` | The sound on the 65816 and on the sound processor |
| `tools/gen_*.py`      | The converters of the game's data                    |
| `test/phys_spec.c`    | The physics in C: the description of the assembly    |

The original game is © 2000 Balázs Rózsa. This version is not affiliated
with or endorsed by its authors.
