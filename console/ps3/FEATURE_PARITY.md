# SDL feature parity on PS3

Source audit: 2026-10-23. **Implemented** means a reachable source path, not a
completed hardware test. **Native evidence** below means PowerPC code under
RPCS3; no physical PS3 acceptance is established. Evidence artifacts record the
exact binary/SDK tested, so a later renderer must be tested again.

The final physics reference, selected by the user on 2026-10-23, is this
project’s PC SDL version (`ELMA_CLASSIC_X87=OFF`). Steam data/LGR compatibility
is a separate requirement. Historical Windows comparisons are diagnostic only.

| Shared SDL feature | PS3 implementation | Evidence / remaining gap |
|---|---|---|
| Original double-precision single-player engine | Shared physics sources, signed-char/wrap assumptions, contraction disabled; compatible sine/cosine | Native 487 trajectories / 54 levels exactly match the selected PC SDL baseline; `physics-parity.json`. Together with multiplayer/Tag and 50 Hz below, 1,135 cases match every recorded bit/event. Historical Windows differences are documented separately in `PHYSICS_PROVENANCE.md` and are outside the selected reference |
| Two players and Flag Tag | Shared two-rider/Tag logic; independent pad bindings | Native 432 trajectories at 30/60 Hz and a separate 216 at 50 Hz, all 54 levels, respawns/apples/transfers and suspended clocks match Linux. Continuous 1,800-second two-pad Tag has constant sampled guest/RSX memory and guest exit 0 (`tag-endurance.json`); final held-button respawn fix passes separately (`tag-ui-latch.json`) |
| Bike rendering, detail, animated objects/menus, swap bikes, Center Bike | Shared renderer and state/options paths retained | Native sprite golden passes; Warm Up rendering observed. Every option combination not executed |
| Internal/external levels, collections, library selection | Shared selectors, case-insensitive resource layer, local Steam collection files | Native Steam collections and copied external level exercised; all 54 original levels loaded and their start views reviewed at 1080p output (`memory-cycles.json`). This is not completion of every level |
| Steam HD LGR13, LGR12, PCX/SPR and palettes | Endian-safe readers, actual shared LGR renderer and scaling | Native LGR13 metadata and real 1×/4× game loads pass. Malformed and oversized library replacement preserves the previous editor library (`controller-final.json`); arbitrary third-party assets are not exhaustively validated |
| Player create/select/delete | Shared state; PS3 Delete Player row replaces hidden keyboard-only gesture | Native 1080p create, cancel-delete, confirm-delete and cold restart pass; existing player/progress preserved. `display-1080.json` |
| State/preferences and desktop interchange | Original encrypted LE layout; atomic backup/rollback/recovery; immediate player/options/XMB saves | Native encrypted-file golden `3acb3bea399218d1`; PS3-created player imported by desktop (`desktop-state-roundtrip/review.json`). Selected display/player settings and all 28 pad bindings persist; exhaustive preference combinations were not run |
| Controller configuration | 14 actions per pad; five-second press capture with drawn button; only throttle, brake, turn and both rotations required. Timeout keeps required bindings and clears optional bindings; occupied buttons swap safely; Start/Select reserved; legacy keyboard controls retained | Version 0.9.0 native two-pad binding, timeout, conflict, wrong-pad, cold-restart and SD layout workflows pass with normal exit; remapped Circle throttle works in Warm Up (`controller-capture-native.json`). Host tests cover 238 assignments, legacy config repair and release gating. Physical-pad reconnect test pending |
| Riding/replay utility actions | Throttle, brake, rotations, alovolt, turn, navigator, time, show/hide, screenshot, screen size and zoom mapped | Native Demo/Randomizer, replay navigator/time, pause/resume, screenshot, screen size and zoom pass; riding turn/alovolt visually verified (`controller-utility.json`). Multiplayer show/hide and exhaustive action/context combinations remain outside that run. Pad zoom is independent of disabled/conflicting keyboard zoom keys; targeted default/custom/player2 native checks and a zero-throttle recording pass (`pad-zoom-native.json`) |
| Replay load, record, save, randomizer and playback | Shared pose/event recorder and interpolation, endian-safe payloads; save transaction and malformed-file checks | Steam `done.rec` plays natively. Actual single/multi recorder golden, poses, events, replacement and eight malformed cases pass natively (`replay-parity.json`, `replay-final-native.json`); Demo and Randomizer also exercised (`controller-utility.json`); physical-console roundtrip pending |
| Pause and system UI | Freeze game clock, preserve outer pause, release held UI inputs across contexts, XMB exit save | Native Start pause and separate PS system overlay freeze/resume the timer; host suspended-clock/nested/context tests pass. RPCS3 did not open an overlay over the native pause dialog, so actual nested XMB and physical disconnect remain untested |
| Keyboard and mouse | Shared SDL events/DirectInput scancode ABI; PS3 SDK USB keyboard/mouse drivers | RPCS3 Basic USB keyboard/mouse exercised: key rebinding, throttle, menu input, editor cursor, left/right click (`usb-input.json`). Physical USB hardware remains untested |
| Editor tools/properties | Same ten tools, toolbar, object/picture/LGR pickers and topology/properties dialogs; right-stick mouse and modifier buttons | Native pad-only create/food ordinal/save/reopen/playtest, picture/texture/mask selection and placement, label text with spaces, locked save metadata and topology dialog pass (`controller-final.json`). Locked-file reopen displays its protection warning and returns an UNNAMED editor (`controller-utility.json`). Every topology-error variant was not executed |
| Editor text and confirmations | D-pad cycling for names/numbers/modes; Start accept, Circle cancel, cursor selects multi-button dialogs | Host text/context tests and native filename/food-ordinal workflows. Pad text uses the shared filename constraints; USB retains broader text entry |
| Screenshots | Bounded streaming PCX writer with explicit little-endian fields, odd-row padding and atomic replacement; riding/editor pad action | Actual native PCX fixture passes independent decoding, palette, replacement and odd/even rows (`screenshot-file.json`); 1842x1038 in-game capture independently decoded by Pillow. Host open/write/close failure injection preserves old files |
| External-level best times and editor saves | Original format; checked atomic save/copy-and-patch, dirty flag retained on failure, orphan level recovery | Actual TOPOL/GYURU serializer host tests inject open/short-write/install/encrypted-payload failures and preserve geometry/times. Native open/install/record update passes (`level-file.json`, `level-final-native.json`); PS3-created AB level loads and plays in desktop SDL |
| Sound on/off, engines, effects, replay sound | Shared 11025 Hz mono mixer; native SDL conversion/queue to output device | Native queue/conversion fixture passes; game/replay captures are finite and nonzero. Finalized 2,220.93-second stereo capture has zero nonfinite samples and peak 0.93036 (`tag-endurance.json`). Listening quality and physical audio output remain unverified |
| Compatibility / Best Quality setting | Value persists, as on SDL desktop | `SDL_SOUND.CPP::initdsound(int)` ignores this argument on both desktop SDL and PS3: there are not two distinct SDL audio backends despite the labels |
| Sharp, Smooth, Nearest, Integer display scaling | Same options; aligned render targets, nearest/bilinear and viewport/clip handling | Final synchronous RSX backend passes 1,200 flips, target/color/filter/readback and physical output-corner checks (`sdl-production.json`, `sdl-resolution-*.json`). Guest720/1080 Original/Sharp reaches 59.9–60 fps with a small host window; physical PS3 speed remains unmeasured |
| Pixel Art display scaling | Shared menu requests SDL's Best mode | Actual RSX shader adapts SDL3 smoothstep sampling and passes an independent CPU pixel reference for enlargement and clipped reduction (maximum channel error 1). Assembly reproduces embedded shaders; licenses and complete sources included |
| Screen/4:3, Original/Auto/Native resolution, numeric config | Same logical view calculations; PS3 defaults Original and applies XMB display aspect/safe area | Native 480/576 4:3, 720p and 1080p UI/game reviewed; fresh final-renderer 576/720/1080 splash captures are indexed by `controller-utility.json`. Oversized numeric config falls back to Original with a native warning and persists the fallback. RPCS3 reports 60 Hz even at 576; physical PAL/interlaced S-video remains untested |
| Engine zoom 0.5x–4x; texture/grass zoom; HQx/Smooth/Nearest filters | Shared options/config and rebuilding; grass zoom is config-only on SDL desktop too | Actual 4× game load confirmed by effective-zoom diagnostics with 133,284 KiB free guest RAM; malformed/oversized LGR rejection dialogs preserve the previous library (`controller-final.json`). Combined 1080 Native + 4× + HQx on Bowling correctly warns and persists safe 1× before loading (`combined-memory-native.json`); this is a resource limit. All filter/asset combinations were not run |
| Auto/manual menu scaling, scrolling, glyphs | Shared menu sizing and scrolling; pad page/navigation; large face-button overlays | Host layout/ball resize tests, all three native SD guide pages, 54-level scrolling and 720/1080 symbols reviewed; arbitrary long custom lists remain outside the tested corpus |
| Limited RAM / resize admission | 24 MiB reserve; measured LGR/brush estimates, 4M logical pixels, old-plus-new vector growth; explicit rejection/fallback | Host/native admission fixtures pass; 50 game, 50 replay and 50 editor-play cycles have zero steady heap/RSX growth, all 54 levels at Original logical resolution leave at least 185 MiB free guest RAM. Combined Native1080/4×/HQx refusal then 1× Bowling play leaves at least 167,831 KiB sampled free guest RAM; normal exit returns tracked RSX to zero. Shutdown releases all tracked RSX allocations (`memory-cycles.json`). Physical hardware peaks and unexpected OOM exit remain untested |

The desktop and PS3 use the same editor feature set. Clipboard editing and
independent picture rotation/scale dialogs are not present in this shared SDL
editor, so they are not PS3-only omissions. Local Steam asset compatibility does
not imply Steam online services or cloud integration.

See [TESTING.md](TESTING.md) for workflow evidence and
[PHYSICS_PROVENANCE.md](PHYSICS_PROVENANCE.md) for the exact reference boundary.
The installed Steam Windows executable has matching resource bytes. A private
debugger capture under Wine compared its actual 440-byte motor state at 512
physics steps: 509 matched the shared source exactly, and three had one-ULP
differences traced to the loaded Wine sine/cosine implementation. Replaying only
those captured math results in the diagnostic recovered all 512 steps. Production
math remains unchanged; this small Wine corpus does not prove historical Windows
equivalence. See `windows-live-step.json` and PHYSICS_PROVENANCE.md.

A measured native Microsoft UCRT candidate differs from the Linux sine/cosine
golden by up to one ULP, including about 3.1% of sampled ordinary angles per
function. Its active use by the Steam executable is unverified. See
`windows-ucrt-math.json` and PHYSICS_PROVENANCE.md. The locally installed EOL
executable is a patched classic-derived version with x87 math instructions, not
an authenticated unmodified 1.11a reference (`windows-classic-static.json`).

## Host sanitizer audit

The actual desktop game and all 14 host fixtures were built in a separate ignored
`build-ps3-asan-clang` directory with `-fsanitize=address,undefined
-fno-omit-frame-pointer`, Debug optimization and the existing floating point
flags. GCC's sanitizer libraries were absent, so this run used the installed
Clang 20 compiler/headers and Clang 22 sanitizer runtime. All 14 fixtures passed
with `UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=1` and
`ASAN_OPTIONS=detect_leaks=0`. Bounds, use-after-free and allocation/deallocation
mismatch checks were enabled. Leak detection was excluded because the engine
keeps process-lifetime globals; this is not a leak-free claim.

Concrete cleanup fixes preserve the allocated object types and gameplay math:

| Source | Corrected ownership |
|---|---|
| `PIC8.CPP`, `KISKEP.CPP` | Picture row/segment/sprite buffers and fixed sprite pixel array use `delete[]`. |
| `SPRITE.CPP`, `MAIN.CPP`, `MENUKEP.CPP` | Temporary RLE array, startup memory-test arrays and menu text rows use `delete[]`. |
| `LGRFILE.CPP` | Picture byte arrays, mask-element arrays, palette and negative-color lookup arrays use `delete[]`. |
| `ABC8.CPP`, `SZAKASZ.CPP`, `VALASZT2.CPP`, `GOLYOK.CPP` | Font arrays, segment arrays, menu arrays and allocation-failure time-table cleanup use `delete[]`. |
| `H_WAV.CPP` | PS1 compression's sample-array cleanup uses `delete[]`; this PS1-only branch was checked from its allocation, not exercised by the desktop run. |
| `RECORDER.CPP` | Initialize all 16 level-name bytes before serialization, removing three uninitialized trailing bytes exposed by ASan. Existing native/desktop replay goldens remain unchanged. |
| `TOPOL.CPP` | Convert the bounded possibly negative stamp value through a signed integer before unsigned masking, avoiding undefined float-to-unsigned conversion while retaining the stored low 16 bits. |

A private X11/dummy-audio game profile additionally exercised fresh-player
creation, live Warm Up with Steam HD default LGR, throttle, actual recorded replay
playback, replay saving, cold startup with the memory self-test enabled, loading
PS3-written encrypted player state and `AB.lev`, editor save/play/restore,
50 screen-verified editor/play-test cycles, HD default → original → HD default
LGR replacement, actual zoom rebuilds (verified at 1.25x and 1.5x), and normal
menu exit. The final live diagnostic log was empty. This is desktop sanitizer
coverage of the shared code, not native RSX/PS3 allocator instrumentation or an
exhaustive malformed-asset proof. Logs, source hashes, screenshots and the
per-cycle screen checks are recorded under the ignored build directories;
`console/ps3/build/verification/host-sanitizer.json` indexes the result.

## Final asset admission checks

PS3 LGR replacement now inspects metadata and peak library memory before freeing
the current library, after resolving the shared missing-custom-LGR fallback to
`default.lgr`. A rejected editor selection restores both the level's library
name and the loaded-library name when the previous library matches the requested
scale/filter. Invalid parser states that cannot safely recover produce a
controlled error instead of continuing through null pointers or invalid indices.
This is not a promise to recover every malformed payload without leaving the game.

Fixed-width LGR list/image names must terminate inside their fields. SPR files
also validate their K/N command stream before becoming usable: every pair must
fit the byte buffer, make progress, and finish the current row exactly. Harmless
trailing bytes remain accepted. Host and sanitizer fixtures cover metadata
rejection, exact reserve/old-library accounting boundaries, unterminated names,
SPR truncation/zero runs/row overruns, and actual valid/malformed SPR loading
through `PIC8.CPP`; the PCX golden stays unchanged. PPU object compilation and final native SPR/level/PCX fixtures pass.
The final-package editor rejection workflow is recorded in `controller-final.json`: malformed BAD.lgr and valid-metadata, oversized HUGE.lgr both warn before replacement and restore DEFAULT. `combined-memory-native.json` additionally records actual Native1080/4×/HQx admission refusal and usable 1× fallback. These results cover the specific fixtures, not arbitrary corrupt asset recovery.
