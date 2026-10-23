# PS3 acceptance checklist

The final release physics reference is this project’s PC SDL version, selected
by the user on 2026-10-23. Build explicitly with `ELMA_CLASSIC_X87=OFF`. The
1,135-case native SDL comparison below is the physics acceptance corpus;
historical Windows/x87 experiments are separate diagnostics.

Status is evidence, not a claim of console compatibility. Host checks below were
run on 2026-10-23. Every hardware item remains pending until run on a PS3; RPCS3
results should be recorded separately with emulator version, firmware, game data
version, display mode, controller model, and available memory.

The 576-line RPCS3 run reports a 60 Hz guest refresh. Upstream
[cellVideoOutGetState](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellVideoOut.cpp)
currently reports 59.94 Hz regardless of the selected resolution. Thus its
576-line/4:3 layout result is not proof of PAL 50 Hz or interlaced S-video output
on physical hardware; those require separate evidence.

## RPCS3 workflow evidence (2026-10-23)

### Version 0.9.0 controller and artwork refresh

`build/verification/controller-capture-native.json` records two reviewed runs of
the packaged 0.9.0 executable, both with normal menu exit (code 0) and zero
tracked RSX allocations at shutdown. The first used 1280×720/16:9; the cold
restart used 720×576/4:3. Two keyboard-mapped pads exercised the actual native
configuration UI; the game USB keyboard handler was disabled.

Passed: five-second capture, release of the opening Cross before capture,
Circle binding without cancelling the menu, mandatory-action swaps, retaining
an existing custom mandatory binding on timeout, and clearing optional time,
alovolt and screen-size bindings on timeout. Start/Select are reserved. The
wrong player's pad is ignored, and an unassigned optional action cannot steal
a mandatory button. Both players' bindings survived a cold restart. The SD
countdown, instructions and drawn Circle fit inside the safe area; Circle
throttle then moved the bike in Warm Up without leaving gameplay.

Only throttle, brake, change direction and the two rotations require bindings.
This replaces the older duplicate-removal behavior described in the historical
run below. The timeout is five seconds of wall time, including time spent
disconnected or in system UI. Host regressions cover 238 assignment cases,
config repair and reconnect-held release gating (`controller-capture-host.json`);
physical controller disconnect/reconnect is still untested.

The cold-restart run left 194,215 KiB free guest RAM during reviewed gameplay,
with a tracked RSX peak of 15,618,848 bytes. These are sampled RPCS3 results,
not physical-console peaks or a repeat of the endurance corpus. The 18 recorded
physics/math source files still match the previously passed 1,135-case PC SDL
comparison; no physics change was made in this UI update.

The 0.9.0 package icon uses an actual game crop and the original yellow splash
lettering. `assets/icon-sources.json` records both source crops and the exact
composition; `tools/render_icon.sh` reproduces it. Rejected artwork and packages
containing it were removed. No normal commit contained the rejected icon; its
12 Codex snapshot references were cleaned and its old Git blobs removed. The
cleanup audit is `build/verification/icon-artifact-cleanup.json`.

### Earlier port workflows

The first reviewed graphical run used RPCS3 0.0.43-20320, firmware 4.93,
Vulkan, 1280×720/16:9, four host CPU cores and a keyboard mapped as a pad.
It used the installed Steam `elma.res` and LGR13 `default.lgr`. Its screenshots,
input log, executable hash and measured results are preserved under
`build/verification/game-720p-initial/`, with verdicts in `review.json`.

Passed in that run: splash credits/version, controller naming and navigation,
Steam collection selection, Warm Up loading, bike rotation rendering and
throttle input, death/restart, native Start pause/resume, Select back,
controller assignment previews, and normal exit (code 0). The stopwatch read
14.16 before an extended pause and 15.26 about one second after resuming.
The level left 193,718 KiB free CPU memory, then 193,363 KiB during play;
the emulator peaked at 1,544.5 MiB host RSS.

That run exposed a configuration replacement failure and a presentation wait
of about 32 ms per frame. The next reviewed run, archived under
`build/verification/game-720p-controls-audio/`, verified the configuration fix
through the actual controller menu: all 28 bindings were saved, duplicate
assignment removed the old binding, and defaults were restored afterward.
The two controller ports drove separate bikes in split-screen Warm Up. A copy
of the installed Steam game's `done.rec`, named `STEAM.rec` in the private
profile, opened and played the original Bounce Back level (`QWQUU009`).
Large controller symbols and the revised Sound Quality row were also reviewed.

That second run was stopped by its 600-second test limit; it is not evidence
of normal exit. It left at least 191,627 KiB free CPU memory in the reviewed
replay. That earlier 2D backend reached roughly 29.4–29.9 fps with Smooth,
compared with 28.1 fps for Sharp. The final RSX renderer and host-window
presentation checks below supersede those performance measurements. The first
Null-audio dump was empty; Cubeb output is analyzed separately. All physical
console items below remain pending independently of emulator results.

The private Cubeb capture contains 579.30 seconds of finite stereo audio,
21,577,980 nonzero samples, peak amplitude 0.81347 and RMS 0.03451. Its test
timeout left an unfinished WAV header, so the analyzer explicitly recovered
the known RPCS3 float32/48 kHz payload; this is signal evidence, not a listening
quality verdict. `audio-cubeb.json` records the original file hash and an
eight-second PCM listening excerpt.

A separate desktop SDL run loaded the PS3-created player A from the actual
state file, selected a Steam collection and played a copied external level.
Screenshots and file hashes are in `build/verification/desktop-state-roundtrip/`.
That bounded run does not establish a normal desktop exit or every field of
a native replay roundtrip; the file fixtures address those separately.

The follow-up `desktop-level-roundtrip/` run opened and played the 1,006-byte
`AB.lev` created entirely with the PS3 controller editor, displaying its saved
geometry, apple and flower. The copied level SHA256 is
`c814165abab8512e18c446507c45ca3d73b170470866da96257eae4854d575be`.
This desktop run completed through the quit confirmation and end screen with
process exit 0.

## Native regression evidence

The files in `build/verification/` record executable/source hashes and process
results. These fixtures execute the actual PowerPC code under RPCS3:

| Check | Result |
|---|---|
| Single-player physics | 487 trajectories across all 54 internal levels: every recorded IEEE64 state bit and integer event matches the Linux x86_64 SDL reference |
| Two-player and Tag physics | 432 cases across all 54 levels, 30/60 fps and suspended-clock cases match every recorded state bit and event; includes 1,744 respawns, 34 apples and 666 Tag transfers |
| PAL simulation cadence | Separate 216 cases at 50 fps cover all 54 levels, both Tag modes and suspended clocks; every recorded state bit and event matches the host. This does not assert that RPCS3 reports PAL correctly to the game |
| Sine/cosine | 999,531 finite IEEE64 inputs from one million generated bit patterns match desktop glibc's FMA implementation; hash `d606934ef31fc787` |
| Sprite rotation | 3,360 area/clipping checks and 120 patterned frames pass; raster hash `18552202131d5665` matches the host |
| State files | Actual encrypted state writer/reader matches host golden `3acb3bea399218d1`; normal fixture exit |
| Replay files | Single/two-player files match host hashes `98a0ba57ae05a2ce` / `35582120fa62b5b2`; both riders' sampled poses, sound events, replacement and eight malformed-file cases pass; exit 0 |
| Editor/external-level writes | Actual level writer passes open/install failure preservation and geometry-preserving record update; exit 0 |
| Screenshots | Actual PCX writer passes independent pixel/palette decoding, odd/even rows, replacement and host file hash `3a7788caa6e655f2`; exit 0 |
| Endian and filesystem | Legacy structure/scalar roundtrips and 14 native filesystem checks pass |
| Atomic save replacement | Existing-file replacement, failed writes, install rollback, failed rollback recovery and stale-backup handling pass |
| Steam LGR13 memory estimates | Native metadata parsing passes at 1× and 4×; the 4× estimate is 90,049,704 bytes plus 26,703,872 bytes temporary storage, before brushes |
| SDL backend | Final synchronous RSX renderer passes 1,200 flips, 2562×2148 targets, ARGB/bilinear colors, independent Pixel Art reference (maximum channel error 1), guarded multi-chunk readback, offset/clipped primitives, target chaining, renderer recreation, audio conversion and timers |
| SPR stream safety | Native command-boundary/row/progress fixtures and the actual PIC8 loader accept valid runs and reject zero-progress bytecode |

Final-source physics refreshes are recorded in
`build/verification/final-physics-test-parity.json`,
`final-multiplayer-test-parity.json` and `final-pal-multiplayer-test-parity.json`.
Fresh desktop traces remained byte-identical to the earlier reference corpora.

The installed renderer evidence is `build/verification/sdl-production.json`.
Separate `sdl-resolution-{1080,480,576}.json` runs validate actual window output
corners before presentation at 1920×1080, 720×480 and 720×576, including the
fixed physical-size query. These correctness runs used separate CPU cores
alongside other QA and make no performance claim. Shader assembly reproduces
all embedded binaries without proprietary Cg libraries; the complete patch,
shader and tested library hashes are preserved.

`build/verification/host-window-synchronous-ab.json` isolates a host presentation
constraint: the synchronous renderer reaches 59.9–60 fps with Original/Sharp
at both guest 720p and 1080p when the Xvfb host window is 640×360. Larger host
windows reduced measured rates despite unchanged guest settings. This does
not establish physical-console speed. The production renderer retains the
simpler completed-flip wait before reusing its command ring and resources.

Physics results establish parity for the tested cases with this repository's
desktop engine. They do not establish bit-for-bit parity with the original
Windows executable, and do not replace a physical-console endurance run.

## Automated host evidence

Harness-only regression: `test/test_game_smoke.py` checks atomic progress/final
records, sampled peak preservation, actual SIGTERM handling, unknown guest-exit
semantics and cleanup of owned child sessions while an unrelated process stays
alive. Both cases passed; this repairs future evidence collection and does not
reconstruct missing metrics from previous interrupted runs.

Run `cmake -S . -B build-ps3-host`, build the host `*-test` targets, then
`ctest --test-dir build-ps3-host --output-on-failure`.

| Check | Evidence |
|---|---|
| Sprite rotation and software rendering | Host and native checks passed: 3360 area/clipping checks plus 120 patterned integer-transform frames; golden FNV64 `18552202131d5665`. Old PPC low-word extraction negative control fails (first wheel area 66 vs expected 1028.9) |
| PS3 diagonal UI strokes using the real engine image/pixel implementation, both slopes, clipping and point case | Host controller CTest passed |
| Menu layout and SDL settings | Host CTest passed |
| Little-endian scalar and legacy structure fixture roundtrip | Host and actual big-endian native checks passed |
| Filter memory estimates and reserve rejection | Host/native fixtures pass; measured native guest admission/fallback and tracked RSX peaks are recorded in `controller-final.json` and `combined-memory-native.json`. Physical-console peaks remain unmeasured |
| Controller defaults, player isolation, persistence, invalid config, reserved buttons, duplicate reassignment, unassigned bindings, text cycling/bounds, missing keyboard-action recovery | Host CTest passed |
| Input transitions | Host regression passes held-button release gating across menu, editor, playtest and nested text dialogs for both pads |
| Replay file format | Host and native fixtures pass deterministic single/two-player files, complete sampled poses and sounds, replacement, missing files and eight malformed-file cases |
| Screenshot files | Actual PCX writer passes independent pixel/palette decoding, deterministic headers, odd/even scanline sizes and injected full-disk, delayed-close and open failures; previous captures survive |
| Level files | Actual level writer passes failed-open, failed-install rollback, short writes including inside encrypted times, and geometry-preserving record updates |
| Failed level loading | Host regression runs the real editor-play recovery path and verifies restoration after a refused load |
| Nested pauses | Host regression verifies nested system/game pause preserves the previous pause state |
| Cross compilation and package | Record current build/package results separately; not established by host tests |

## Physical-console acceptance checklist

The unchecked boxes in the following four sections are **physical PS3 acceptance**
items. Native RPCS3 evidence is recorded separately above and below; a later
emulator pass does not mark these hardware boxes complete.

### Game and data compatibility

- [ ] Cold boot with registered assets; splash retains original copyright and shows PS3 version and unofficial port credit.
- [ ] First player creation, returning player selection and deletion; names entered using D-pad alone.
- [ ] All internal levels and external `.lev` files load; library selection and custom graphics work.
- [ ] Finish, restart, death, fruit collection, flower, single-player and two-player flag tag behave correctly.
- [ ] Existing desktop `state.dat`, levels and replay files load; newly written files reopen on desktop.
- [ ] Replay comparison reproduces desktop completion time, bike positions, collisions and sound event timing.
- [ ] Save and reload player state, best times, external records and replay filenames after a cold restart.
- [ ] Save errors, missing/corrupt files, full storage and overwrite dialogs remain usable; D-pad chooses highlighted buttons, Start accepts and Circle cancels.

### Controllers and editor

- [ ] Controller 1 navigates every menu with repeat, accepts with Cross/Start and backs out with Circle/Select.
- [ ] D-pad Up/Down cycles letters, Right adds and Left deletes in player, replay and editor name dialogs.
- [ ] Both pads control only their configured player; disconnect/reconnect and system menu release held inputs.
- [ ] Customize every riding/utility action; confirm graphical Cross, Circle, Triangle and Square previews are clear.
- [ ] Same-pad duplicate assignment removes the prior action; unassigned actions do nothing; Start/Select remain reserved.
- [ ] Mappings persist in `elma.cfg`; original keyboard mappings remain usable.
- [ ] Throttle, brake, both rotations, alovolt, turn, navigator, time, view, screenshot, screen size and zoom work during play/replay.
- [ ] Start pauses/resumes play and replay without advancing physics or leaving a stuck key; Select leaves.
- [ ] Editor: right stick moves cursor, R1 slows it, Cross/Square click, L1 Ctrl, R1 Shift, Triangle closes polygon, Circle cancels.
- [ ] Editor: L2 zooms out, R2 captures screenshot, Start tests, Select exits; toolbars reach every tool and file action.
- [ ] Editor text: arrow cycling enters filenames, level/designer names (including spaces), distance, clipping mode and food ordinal; Start accepts, Circle cancels without changing the original.
- [ ] Create, modify, save, reopen and test a complete custom level using only the controller.
- [ ] USB keyboard/mouse support all original commands and work alongside controllers.

Reconnect/held-input source audit: disconnected ports and failed status/data
reads clear both button masks and all four axes; a successful zero-length
packet retains unchanged input. The SDL adapter clears generated action keys
on every poll, resets menu repeats after release, and requires held UI/pause
buttons to be released across context changes. System-menu input now gates
both sticks as well as buttons, including editor cursor movement. Automatic
disconnect pause was not added. Physical unplug/reconnect remains **untested**;
these source checks are not a native hardware PASS. Virtual PS-menu clock
freeze/resume evidence is in `build/verification/display-576.json`.

System-UI event audit (2026-10-23): the pinned
[PSL1GHT header](https://github.com/ps3dev/PSL1GHT/blob/f649a08fd536a9e27c08c7db2d93a2d7ee4c3bbe/ppu/include/sysutil/sysutil.h)
distinguishes drawing and menu events. RPCS3's
[home-menu dispatch](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellSysutil.cpp)
uses DRAW_BEGIN → MENU_OPEN → MENU_CLOSE → DRAW_END; its
[message dialogs](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellMsgDialog.cpp)
also use drawing-only lifetimes. The former single bool became false at
MENU_CLOSE while drawing was still active. The PS3 helper now tracks the two
states independently and exposes their OR, with SDK event-value static assertions.
Host event-sequence tests cover this actual overlap, drawing-only dialogs,
unrelated notifications, duplicate state updates and independent closure. This
establishes a state-model correction, not an observed one-frame clock jump:
queued callbacks may all drain in one poll. Earlier native pause evidence predates
this helper; no new physical-console event sequence is claimed. A subsequent
new-profile smoke with the rebuilt staged EBOOT passed XMB open/hold/close
(clock 1.63s unchanged during a four-second explicit hold, then 2.81s after
resume), direction/throttle recovery, and a separate Start pause (17.45s
unchanged across a three-second hold, then 18.63s after Cross resume). Normal
exit 0 returned tracked RSX to zero. `build/verification/system-ui-native.json`
records exact binary/settings and fresh screenshots; this checks regression,
not physical event timing or an instrumented callback overlap.


A later Tag source audit found respawn cleared the held navigator/time/view UI
latches. The PS3 path now preserves only those three latches across respawn;
riding/physics reset fields remain unchanged. The actual `valtozok` host
control-flow regression counts five false/repeated edges with the old reset,
versus two intentional presses with preservation. A separate zero-filled QA-state
test verifies all nineteen engine action keys are distinct, valid and separate
from both zoom keys; alovolt intentionally combines the two rotation bindings.
This targeted host result does not retroactively validate the patched binary
in the earlier native endurance run. A separate short patched native run
(`build/verification/tag-ui-latch.json`) verifies split → full B → split with
separate two-second R3 holds, including another eight-second gas/rotation hold.
It exited normally with code 0 and released all tracked RSX allocations. Native
respawn counts were not instrumented; the forced-reset host case supplies that
specific regression evidence.

Pad zoom independence was checked after the final audit found its legacy-key
coupling. The PS3 route now combines direct pad bindings with allowed keyboard
zoom, without injecting a keyboard code for pad zoom. Host tests cover disabled
keyboard zoom, Page Up throttle collisions, custom/unassigned buttons, both pads,
release and system-menu gating while retaining valid keyboard zoom. Two fresh
native runs (`build/verification/pad-zoom-native.json`) verify default R2 with
keyboard zoom disabled, custom Triangle with Page Up reused for throttle, and
player 2 R2: graphics logs record 1.25× and 1.50× rebuilds. The saved zoom-only
`pad-zoom-A.rec` has 1068 sampled frames and zero throttle bits, independently
confirming zoom did not drive the bike. Both runs exited normally with code 0;
tracked RSX allocations returned to zero. Non-PS3 routing and physics are unchanged.

### SDL feature parity and display

- [ ] Sound enabled/disabled, compatibility/best-quality sound setting, engine/audio loops and replay sounds.
- [ ] Animated menus, video detail, animated objects, swap bikes, single/multiplayer and tag settings persist.
- [ ] Center Bike setting; all scaling modes (Sharp, Smooth, Nearest, Integer, Pixel Art).
- [ ] Screen/4:3 aspect; all offered resolutions; zoom, zoom textures, zoom grass and texture filters.
- [ ] Auto/manual menu scaling; tall lists scroll; menu text and controller symbols share display scaling.
- [ ] 480p, 576p if available, 720p and 1080p: glyph previews, menus, game and editor remain visible and readable.
- [ ] TV Safe Area values compensate overscan; screenshots capture the intended logical game/editor image.
- [ ] Fullscreen console output, display refresh pacing, system menu, quit and relaunch work without hangs.

### Limited-RAM acceptance

PS3 has separate CPU and RSX memory pools. A host pass cannot validate either
pool's real availability or fragmentation. Record free CPU memory and peak CPU /
RSX use at cold boot, first level load, largest custom library load, editor,
replay playback, highest offered resolution, and each texture filter.

- [ ] Memory reserve prevents high-cost filters from exhausting CPU memory; fallback produces a visible usable result.
- [ ] Resize/setting transitions fit both old and new buffers at peak; RSX texture allocation failures recover.
- [ ] Repeated level loads, replay opens and editor tests (at least 50 each) do not accumulate memory.
- [ ] Exercise large custom textures and malformed dimensions; reject unsafe allocations without corruption.
- [ ] Run a 30-minute two-player session with sound and animated objects, then enter editor and replay browser.
- [ ] No unbounded screenshot, replay or state buffering; storage failure paths preserve existing files.

Record results with measured numbers and logs before replacing any pending box.

With diagnostics enabled, `ELMA PS3 checkpoint` marks actual game, replay and
editor-play entry/return. It reports free guest CPU memory, live heap bytes and
tracked application RSX allocations. The fixed 128-entry RSX observer preserves
the allocator result even if its table fills; `complete=0` then marks its counters
as lower bounds. RSX bytes exclude alignment, allocator headers and firmware
reservations; they must not be described as total free VRAM. Normal shutdown also
records a checkpoint after SDL destroys its video resources.

`test/memory_cycle.py` repeats a prepared browser/editor workflow and requires
matching guest entry/return markers for every cycle. It records the binary hash,
each cycle's memory samples and a screenshot every ten cycles. Review those
screenshots and the steady-state heap/RSX trend before concluding that a workflow
is stable. Successful input injection alone is not a completed load.

## Native sprite regression fixture

Build only `sprite-rotation-test` in the PS3 build directory, process the ELF
with `sprxlinker`, then sign it with `make_self`. Signing a freshly linked ELF
without the required PSL1GHT fixups can prevent it from booting. Run the resulting SELF in a disposable fixture profile after
stopping other verification sessions. The test uses real `DOBOZ`, `KISKEP` and
`VEKT2` with memory-only image storage; no game assets, display or controller are
required. It writes `/dev_hdd0/game/ELMAC0001/USRDIR/sprite-result.txt`.

Success requires `PASS checks=3360 hash=18552202131d5665`. The hash additionally
covers 120 patterned renders in eight directions, three sizes and five clip
positions. Area checks use a viewport sized to each disk, retaining four guard pixels
and all four edge positions. Whole zero words are skipped during exact area
counting; eight zero-byte FNV steps are combined as multiplication by
`prime^8`, preserving the hash. These optimizations reduce scan work without dropping cases. Native execution completed successfully with process exit 0 and
454.7 MiB peak emulator RSS; `build/verification/sprite-parity.json` records the
actual source/binary hashes. Emulator RSS is not PS3 guest memory usage.

Their transforms use integer-valued vectors, avoiding host/PPC libm
rounding differences. The original defect read the low 16-bit coordinate word
on PPC. A host negative control replacing the fixed high-word extraction with
`uint32_t(coordinate) & 0xffff` fails the first area check, demonstrating that
the fixture rejects that defect. This negative control is distinct from a
native big-endian execution result; record the latter separately.

## Editor source coverage audit

The following mapping was checked against `EDITUJ.CPP`, `EDITTOOL.CPP`,
`EDITTOLT.CPP`, `DIALOG.CPP`, and `DIALOG32.CPP`. This is source coverage;
runtime evidence is recorded separately below; unexecuted actions remain pending.

| Shared editor action | PS3 access |
|---|---|
| Move cursor, left/right mouse button | Right stick, Cross/Square; R1 slows cursor |
| Esc, Space, Enter | Circle, Triangle, R3 |
| Play `p`, exit `x`, zoom out `z`, screenshot `i` | Start, Select, L2, R2 |
| Open `o`, save `s` | Click toolbar Open/Save with Cross |
| New, Save As/Locked, topology check, properties, zoom fill, view toggles, help | Click the corresponding left toolbar button; Square gives contextual help |
| Move, zoom in, create/delete vertex/polygon, create food/killer, delete object, create/delete picture | Select one of the ten left toolbar tools with Cross, then use cursor and Cross/Square |
| Change insertion direction / join neighboring vertices | R3 / Triangle while using vertex tool |
| Picture, texture, mask and LGR selectors | Square opens picker; cursor clicks fields, list rows and buttons; D-pad scrolls lists |
| Sprite distance, U/G/S clipping mode, food ordinal | Select field with cursor; D-pad adjusts/cycles; Start accepts; Circle cancels |
| Level/designer text, save filename | D-pad character cycling/add/delete; Start accepts; Circle cancels |
| Polygon grass property, gravity food type, animation/food index, view flags | Cursor selects the corresponding property/list/checkbox |
| Multi-button confirmation | D-pad changes outlined choice; Start accepts, Circle cancels; cursor buttons remain available |

The shared SDL editor does not implement clipboard cut/copy or independent
picture rotation/scale dialogs. Its complete toolbar/tool set is covered above.
The right-stick cursor uses the same 640x480 coordinate range as these dialogs.

A host preview using the actual `PIC8.CPP` pixel implementation confirms that
PS3 face symbols render on dark circular caps. The supplied intro palette has
blue, red and green hues; its missing pink hue uses a bright square fallback.
No palette entries are modified. Native 720x480 / 4:3 testing with keyboard
Null confirms all three guide pages, filename hints, and Cross/Square/Triangle
previews fit the safe area. Later native 720p/1080p glyph and menu checks passed (`display-1080.json`, `controller-final.json`), and final-renderer 576p/720p/1080p splash captures are recorded in `controller-utility.json`. Physical-TV legibility/overscan checks remain pending.

The private `rpcs3-editor-sd` profile imported a copy of Steam player state
(SHA256 `96743dd638bf53d820e55c4b4f36519827d190c835dd216455df0aac97c65745`),
selected unlocked player dox187 and opened copied external `DESKTOP.lev`.
Controller-only input then created `AB.lev`, placed food, opened its properties
with Square, changed ordinal 1 to 2 using D-pad/Start, saved, reopened and
started a playtest. Captures `editor-*.png`, `guide-sd-*.png`,
`glyph-sd-*.png` and `inputs.jsonl` in that private build profile preserve the
steps. Source Steam state/assets were not modified. Later native workflows
covered picture/texture/mask selection and placement, label text with spaces,
locked save/reopen protection and the successful topology dialog
(`controller-final.json`, `controller-utility.json`). Fifty editor-play restore
cycles passed (`memory-cycles.json`). Individual topology-error variants and
arbitrary third-party graphics remain outside that coverage.

This run exposed Select carrying from playtest into editor exit. A shared
input-context release gate now suppresses held UI/pause/exit buttons until
release across gameplay/editor/dialog transitions; its focused host regression
covers both pads and nested dialogs. Native retest passed: holding Start for two seconds entered play without
pausing, and holding Select for two seconds returned to the unchanged editor
without exiting. `build/verification/editor-sd.json` records the reviewed
captures, remaining gaps and original Steam-state hash. Gameplay movement
continues to use held action bindings.

Virtual USB acceptance (`build/verification/usb-input.json`) uses a separate
private profile with `--keyboard Basic --usb-only`; Null pads prevent RPCS3
from routing keys into its controller handler. The harness enables Basic
mouse events and disables emulator keyboard shortcuts so Escape reaches
the game. Native testing confirmed W throttle remapping and driving, USB
menu navigation, relative editor cursor movement, left toolbar clicks and
right contextual help. This does not certify physical USB devices.

## Repeated native loads and memory

`build/verification/memory-cycles.json` records a private 1080p RPCS3 run with
Original 852×480 logical rendering, Sharp, 1× engine zoom and Steam HD default
LGR. All 54 original levels loaded in order; their start views were reviewed.
The QA player has synthetic progress solely to enable selection. The minimum
free guest RAM at level return was 189,674 KiB (about 185 MiB).

| Repeated workflow | Cycles | Steady heap bytes | Steady tracked RSX bytes | Growth |
|---|---:|---:|---:|---:|
| Warm Up enter/leave | 50 | 16,437,136 | 49,398,048 | 0 |
| Steam replay enter/leave | 50 | 18,084,688 | 49,398,048 | 0 |
| Editor Save and Play/restore | 50 | 15,924,016 | 45,281,568 | 0 |

Steady measurements exclude the first five cycles. Tracked RSX allocation failures
were zero throughout; normal game shutdown returned every tracked RSX allocation
(0 bytes / 0 allocations, tracking complete) and RPCS3 exited with code 0. RSX
counters cover requested allocation sizes, excluding allocator overhead and
firmware reservations. The host emulator peaked at about 1,732 MiB; this is
separate from the PS3 guest RAM budget.

The loaded binary predates the later defensive LGR/SPR guards and SDL physical
output-size query correction; its exact hash is preserved. Those changes have
separate final native fixtures/smokes. This run establishes the measured valid-asset
lifecycles, not exhaustive leak absence or physical-console acceptance.

### Final controller/editor and LGR admission smoke

`build/verification/controller-final.json` and `controller-final-TTY.log` record
latest-package native checks with a private synthetic QA state, USB keyboard Null,
720p guest output and a 640×360 host window. Controller-only keyboard capture
cancel (Circle and Select), picture/texture/mask selectors and placement, a level
label containing a space, locked-save metadata and topology dialog were exercised.
The initial locked-file reopen capture was inconclusive; a later isolated single-accept test captured the protection warning and return to an UNNAMED editor (`controller-utility.json`).
The preceding editor run and final admission run both exited normally with code 0.

A valid level rendered at configured and effective 4.00× zoom; native diagnostics
reported 133,284 KiB available guest RAM, 31,995 KiB LGR storage, 2,743 KiB brushes and
4,279 KiB brush construction peak. A corrupt private BAD.lgr produced its invalid
metadata warning. A private HUGE.lgr retained valid LGR13 metadata/pixel data but
changed the first bike target dimensions to 32767²; it produced the explicit memory
refusal before allocation. Reopening Properties after both refusals showed DEFAULT,
and the previous editor graphics remained available. Captures are in
`build/rpcs3-controller-final/` (`zoom4-loaded.png`, `bad-rejected.png`,
`bad-rollback-properties.png`, `huge-memory-refused.png`,
`huge-rollback-default.png`). Final shutdown reported 0 tracked RSX bytes and
0 allocations, complete tracking and 0 allocation failures. Concurrent emulator QA
means these screenshots/logs do not establish performance. Physical unplug and
reconnect remain untested.


The final combined-pressure run requested **1080p output, Native logical
resolution, 4× engine zoom and HQx** on original level 46 Bowling. Admission
refused the projected 395,234,839-byte LGR plus 98,984,960-byte temporary and
153,662,360-byte brush peak against 207,054,832 bytes available. The visible
warning explicitly announced safe 1× fallback. After confirmation the actual
level rendered and responded to controls at 1842×1038, engine zoom 1× and asset
scale 2.16×. The persisted config retains Native/HQx and records zoom 1. This is
an expected resource limit, not a missing zoom/filter feature. Sampled guest free
RAM stayed at least 167,831 KiB; maximum checkpoint heap was 42,741,856 bytes;
tracked RSX peaked at 40,699,680 bytes with zero failures, then returned to zero
bytes/allocations on normal exit 0. Host RSS peaked at 1,840,001,024 bytes.
`build/verification/combined-memory-native.json` records binary/artifact hashes;
`build/rpcs3-combined-1080/` preserves the warning, level screen, config and logs.
Concurrent native tests and the reduced host window make this a memory/error-path
check, not a speed measurement. No further production source change was needed.

The remaining utility gaps were checked in a separate private profile:
`build/verification/controller-utility.json` records the exact native runs. A single
Start press on selected locked C.lev displayed “The file C.lev is locked, you cannot
edit it!”; dismissing it returned an UNNAMED editor, resolving the earlier uncertain
capture. Demo and Randomizer (a copied Steam replay) played correctly. Controller
navigator/time toggles changed the replay display, Start opened its pause dialog,
viewport decrease/increase visibly added/removed the stone border, and zoom
changed 3.75×/4×. D-pad Up screenshots independently decoded as indexed 640×480
PCX files (103 and 130 colors). Circle visibly reversed the riding bike and D-pad
Down alovolt rotated it. Multiplayer show/hide remains outside this singleplayer
visual check. The utility run and a cold 1080p persistence run both exited 0; cold
native diagnostics confirmed saved effective 4.00× zoom. Fresh production splash
captures (`boot-ready.png` at 720p, `production-splash1080.png` at 1080p) are in
`build/rpcs3-utility-final/`; historical mirrored images are not final evidence.

Final production 576p splash and Main menu captures are `production-splash576.png`
and `production-main576.png` in the same profile; that run also exited normally
with code 0. This verifies SD display layout, not physical PAL50Hz timing.

## Thirty-minute native Tag endurance

`build/verification/tag-endurance.json` records 1,800.3 uninterrupted seconds of
two independent pad inputs on level 8 Tag, with 1080p output, Original 852×480
logical view, Pixel Art sampling, 1× engine zoom and Cubeb audio. All 60 sampled
cycles report exactly 193,191 KiB available guest RAM and 19,906,848 tracked RSX
bytes in seven allocations, with complete tracking and zero failures. Reviewed
start, middle and final captures show both riders and advancing Tag clocks.
The game returned through its results/menu screens and logged guest process
exit status 0. SDL shutdown returned tracked RSX usage to zero bytes/allocations.

The finalized 48 kHz stereo float WAV contains 2,220.93 seconds including menus
and replay checks: 106,604,800 frames, zero nonfinite samples, 178,095,154 nonzero
samples, peak 0.930357 and RMS 0.070145. This is a numerical audio check, not a
listening-quality or physical-output acceptance. The private audio sink was
removed after exit. The saved two-rider `A.rec` also reopened and played natively;
both records contain the shared desktop/PS3 limit of 8,981 poses at 30 Hz, about
five minutes. It does not retain the entire thirty-minute session.

This uninterrupted run began before the final PS3-only Tag UI-latch correction;
the corrected build has the separate held-R3 acceptance recorded above. The
outer graphical test harness received SIGTERM before it could write `run.json`.
Its cause is unknown. The independent endurance input/log capture completed,
and the guest later shut down normally through the menus. `recovered-run.json`
records this distinction: host exit status and peak RSS are unavailable for this
run, and continuous host RSS guarding after the last harness capture is not
claimed. The remaining private Xvfb and audio module were explicitly cleaned up.
No physical PS3 or S-video result is inferred from this test.

## Television mode initialization and physical SD acceptance

The final mode initialization fix zeroes the entire SDL driver mode allocation
and explicitly copies the documented 4:3 or 16:9 aspect from `videoGetState`
into `videoConfiguration.aspect`, with AUTO for an unknown aspect. The stock
pinned SDL source used `SDL_malloc` and left aspect/reserved bytes uninitialized.
`build/verification/sdl-aspect-initialization.json` records the rebuilt SDK and
four targeted native 30-flip runs: 720×480/4:3, 720×576/4:3, 1280×720/16:9 and
1920×1080/16:9. All retain the before/after firmware aspect, resolution, scan
mode and refresh mask; output-boundary, texture/filter/readback and renderer
recreation checks pass. This changes video setup, not the physics engine or
renderer command implementation.

The application selects no cable, PAL region, interlace mode or refresh mode.
XMB/firmware owns those settings. `ps3_prepare` queries `videoGetState` before
SDL starts and preserves the television aspect and the 50 Hz refresh flag.
The PSL1GHT `sysutil/video.h` API exposes `videoDisplayMode.scanMode` and
`refreshRates`; `videoConfiguration` has resolution/format/aspect/pitch but no
scan-mode or refresh member. SDL configures the current resolution, XRGB format,
pitch and captured aspect. The display-mode table's “progressive” comments do
not select progressive scanout. The renderer uses the actual scanout extent,
not a requested window extent, and GCM VSYNC remains enabled.

For SD output, `ps3_display_size` compensates non-square pixels using the XMB
aspect: a 4:3 720×480 buffer has a logical 640×480 extent, and 720×576 has a
logical 768×576 extent. Widescreen SD uses height×16/9. Layout fits the picture
in that logical extent, then maps its rectangle back to the physical buffer.
The configurable safe area removes 5% at each SD edge by default (2% for HD),
with a 0–10% setting. It cannot measure a television's overscan automatically.
PAL's queried 50 Hz flag selects the 50 Hz frame-cap threshold; present still
waits for the firmware flip, and elapsed-time physics uses the existing clock.

**Physical acceptance remains pending:** configure a real PS3 for S-video
480i/4:3 and PAL 576i/4:3 separately; record the queried resolution, scanMode=0,
aspect=1 and refresh mask (50 Hz bit=2 for PAL, 59.94 Hz bit=1 for NTSC). Verify
full splash/footer/menu and editor bounds, round geometry, safe-area adjustment,
interlace text stability, tear-free flips, sound and controls. Check a timed
PAL gameplay/replay sample against a wall clock. RPCS3 reports scanMode=1 and
59.94 Hz in these SD runs, so neither its resolution setting nor a separate
50 Hz vblank override proves real interlaced output, analog picture geometry,
field cadence, cable compatibility or PAL50 timing. No physical PS3/S-video
test has been performed.

The corresponding rebuilt main was also reviewed at those four resolutions:
`build/verification/main-aspect-safe-area.json` links the per-mode captures and
logs. The stable full splash, continue prompt, port version and copyright footer
fit in all four modes. The 480-line capture was repeated with a warm cache
because the first cold LLVM compile finished after its last screenshot; that
initial compilation image is not counted as a visual pass. Captures use a
640×360 RPCS3 host window and establish layout fit only, not analog television
pixel geometry or physical overscan. The final package is separately installed
and hash-checked in a new private RPCS3 profile after both the mode setup and
system-overlay state fixes; see `build/verification/pkg-install.json`.
