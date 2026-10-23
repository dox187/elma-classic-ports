# Physics comparison boundary

## Selected release reference

The user selected **this project's PC SDL version** as the final physics
reference on 2026-10-23. The released PS3 build explicitly sets
`ELMA_CLASSIC_X87=OFF` and retains the SDL arithmetic order and deterministic
Linux-compatible sine/cosine implementation. The installed Steam edition is
used for resource and LGR compatibility, not as a replacement physics target.

The native regression matches every recorded state bit and event in **1,135
cases across all 54 levels**: 487 single-player, 432 multiplayer/Tag at 30/60 Hz,
and 216 multiplayer/Tag at 50 Hz. This is exact agreement for the tested
inputs/time steps, not a mathematical proof covering every possible history.
Native RPCS3 execution does not replace a physical PS3 hardware run.

## Historical Windows investigation

The following Windows comparisons explain why choosing the reference matters;
they are retained as diagnostic evidence, not release acceptance requirements.
A public original 1.11a shareware executable supplies actual 440-byte motor-step
entry/exit captures: 4,551 of 4,559 steps match both Linux and native PPU exactly.
All native PPU outputs match the current Linux engine. The eight differences
from that Windows executable are isolated to math/operation order below.
Wine on a modern host does not recreate an historical Pentium floating point unit.

The separate software-x87/product-order experiment reproduces all 4,559 captured
original steps on host and PPU. It is not enabled in the selected release and
is not required for SDL parity. Broad endpoint testing finds differences from
this AMD host. See [X87_EXPERIMENTS.md](X87_EXPERIMENTS.md).

The 487-case single-player corpus uses the shared `LEPTET.CPP`, `BEALLIT.CPP`,
`UTKOZES.CPP`, `UTKOZES2.CPP`, `SZAKASZ.CPP` and `VEKT2.CPP` on both architectures.
The harness supplies level loading, initialization, object activation and game-loop
orchestration. It records numerical engine state and discrete events at each step;
it does not run the complete SDL input, audio, renderer or editor loop. Native
results and source/binary hashes are in `build/verification/physics-parity.json`.
The separate sine/cosine corpus checks 999,531 finite IEEE inputs from one
million generated bit patterns against the
desktop glibc reference. Matching that reference is necessary for the measured
Linux comparison; it is not evidence about the Windows math library.

The additional 432-case multiplayer corpus covers both ordinary two-player and
Tag, all 54 levels, 30/60 Hz scheduling, independent rider controls, shared apples,
respawns and Tag transfers. Each unpaused case has a counterpart with suspended
wall-clock periods. The host counterparts match exactly. Native execution status
must be taken from its verification artifact rather than inferred from the
single-player result. These fixtures exercise the production pause-clock helper,
but do not inject USB/pad or XMB events into the running game.

A separate 216-case corpus covers the same 54 levels, both Tag modes and
suspended-clock counterparts at 50 Hz. It also matches every recorded host
state bit and event; see `build/verification/pal-multiplayer-parity.json`.
RPCS3's 576-line video API reports 59.94 Hz independently of its configured
vblank cadence, so this fixture tests simulation scheduling rather than physical
PAL output detection.

## Optional further evidence for the original Windows game

1. The public 1.11a shareware executable/resources are now hash-identified and
   their live x87 control word is captured. Registered 1.11a identity, historical
   CPU behavior and original build/compiler flags remain unverified. Rebuilding the
   source with a modern Windows compiler would create another reference, not
   establish the behavior of that executable.
2. Actual original shareware motor-step capture is now working. Broaden it
   beyond the measured levels and controls, using the authorized debugger. Feed the same controls and exact simulation-step boundaries,
   and record the same internal positions, velocities, rotations, contact/history
   fields, object states and events. Record the floating point control state and
   math-function behavior too, so a discrepancy can be attributed rather than
   hidden with numerical tolerances.
3. Compare those traces with both the Linux reference and PPU traces. Include the
   finishing Warm Up script, wall/ceiling contacts, rotations, braking, gravity
   apples, death/finish boundaries, both riders and Tag respawns. The existing
   harness is reusable, but its reimplemented initialization/orchestration must
   also be checked against the executable.
4. Separately compare actual platform scheduling: input changes, pause/resume,
   XMB interruption and frame pacing must produce the intended simulation-step
   sequence. Replay playback is a stored trajectory, so watching a matching replay
   alone cannot prove that live physics computes identical trajectories.

The selected release target is tested exact parity with the Linux SDL source
baseline. The optional Windows investigation above is outside that target. Do not describe it as proven 100% Windows-original physics
parity. Native RPCS3 results also do not replace a real PS3 hardware run.

## Available Windows reference on this machine

Read-only inspection found Steam's `base/elma.exe` at
`/home/dox187/.local/share/Steam/steamapps/common/elma/base/elma.exe`:

- SHA-256: `3999b9c2a1e666fca3f47a187d7066cae22106a0f80ee47bf396e48718dc4be2`.
- PE32+ x86-64, linker version 14.29, PE timestamp 2023-10-07. This identifies
  the installed reference; it does not establish provenance as the historical
  Windows release. A subsequent private Wine launch is described below.
- Its `elma.res` exactly matches the repository's test resource, SHA-256
  `06e54ed79730befeab96605ef8b17700738e8e181fe51dfd09fb2e855c0478ff`.
- The inspected exports expose SDL APIs, with no identified physics trace or
  replay-resimulation interface. No such verification interface is present in
  this repository's recorder API. `recorder::recall` interpolates stored body,
  wheel and rider coordinates rather than calling `leptet` to recompute them.

The PS3 game defaults to `ELMA_REGISTERED=ON`; the desktop build defaults OFF,
which defines `SARVARI`. A desktop interoperability or behavioral reference must
therefore explicitly enable the registered build when using this resource. The
physics fixtures load extracted level geometry directly; their tested physics
sources do not branch on `SARVARI`. They bypass the registered/shareware resource
and menu checks, which are separate compatibility evidence.

A feasible additional acceptance test, without claiming internal equivalence,
would record a **fresh live run** in that Windows game using controlled inputs,
then compare its newly written replay's poses, event order and completion time
with fresh Linux/PPU runs. Constant controls reduce input-delivery ambiguity.
This is stronger than playing an existing replay, but recorder poses are sampled
and quantized, and uncontrolled frame timing can change the simulation steps.
Such a comparison must therefore be reported as observable live-run evidence,
not an IEEE64 per-tick proof. Exact proof still requires access to the original
simulation state and actual step/input sequence; SDL exports alone do not supply
those. The initial read-only audit did not instrument the executable; subsequent
private runtime and startup experiments are described below.

## Measured Microsoft runtime difference

A private Wine 11.17/Winelib probe loaded a **native Microsoft x64 UCRT
10.0.17134.12** copied from another installed Steam title's Rockstar launcher.
This is a candidate runtime, not evidence of which UCRT the Elma executable uses
on a particular Windows installation. Its SHA-256 is
`8a91052ef261b5fbf3223ae9ce789af73dfe1e9b0ba5bdbc4d564870a24f2bae`.
The installed Elma launcher's x86 UCRT has the same version, but cannot be loaded
by the x64 base executable. Wine's ordinary built-in UCRT was deliberately not
used for the native math calls; the loader log confirms the copied DLL as native.
The host comparison resolves directly to `/lib64/libm.so.6`.

| Corpus | Sine differences | Cosine differences | Maximum difference |
|---|---:|---:|---|
| 999,531 finite arbitrary IEEE64 inputs from one million attempts | 15,821 | 15,580 | 1 ULP; absolute 1.1102230246251565e-16 |
| Same count mapped to angles in [-32,32] | 30,943 | 30,974 | 1 ULP; absolute 1.1102230246251565e-16 |

The arbitrary-input Linux hash is the existing PPU golden
`d606934ef31fc787`; the Microsoft candidate hash is `55a43fc3d4c4920a`.
The square-root comparisons on nonnegative inputs had no differences. The
candidate reports FMA enabled, floating point control `0008001f`, and MXCSR
`00001f80`. No PS3 math implementation was changed from this experiment.

This establishes that selecting the math runtime can affect exact equality,
even for ordinary angles. It does **not** establish the released game's complete
physics behavior or identify its historical runtime. The isolated probe did not
launch the original game, write Steam data, or use RPCS3. Detailed counts, logs,
source and DLL hashes are in `build/verification/windows-ucrt-math.json` and
`build/windows-reference/`. The proprietary DLL/prefix are diagnostic build
artifacts and must not be included in release/source packages.

The probe source is `test/windows_ucrt_math.c`. With Wine's compiler/runtime
installed, build using `winegcc -m64 -mconsole -O2 -fno-builtin
-ffp-contract=off test/windows_ucrt_math.c -o wine-math.exe -lm -ldl`. It expects a
private copy of a native x64 Microsoft runtime named `ucrt-native.dll` beside the
probe and a separate WINEPREFIX. Preserve native-load logs and the DLL hash for
every comparison; testing an arbitrary Wine built-in would answer a different
question.

The executable imports `sin`, `cos`, `sqrt`, `exp` and `atan2` through
`api-ms-win-crt-math-l1-1-0.dll`. Read-only disassembly additionally identifies the function at VA
`0x1400e8fb0` as a strong match for `LEPTET.CPP::leptet`: it reads motor angles
at offsets `0x20`, `0x88`, `0xf0`, updates the brake-state field at `0x17c`, and
uses the same throttle thresholds (-110,110), torques (-600,600), and braking
coefficients (1000,100). Its calls at `0x1400e900c` and `0x1400e9019` reach the
imported `sin` and `cos` through thunks `0x1403d49c6` and `0x1403d49c0`.
This establishes that the installed executable's physics path uses the imported
math functions; it does not prove which Microsoft runtime version a real Windows
installation selects. The vector rotation at `0x14014f140` also matches the
source's separate double multiply/subtract/add operations. PE linker metadata
and these examples do not establish compiler floating point flags for the whole
engine. Filtered disassembly is retained in the ignored Windows reference build
folder.

A fresh live Windows replay could compare observable trajectories, but its
quantized states and frame timing cannot prove exact per-step motor states.
Exact comparison would require identifying a complete simulation-step entry,
its motor/topology/global-state dependencies and initialization, then capturing
or controlling each dt/input and all double-valued state after every call. An
instrumented original source build would provide the cleanest trace. Calling or
patching an isolated machine-code function without establishing those dependencies
would not be a trustworthy reference.

A subsequent isolated launch of a copied installed executable under Wine reached
the name prompt, main menu, Tutorial 1 and collection selector (visible build
1559). The private offline runtime exposed only Tutorial (0/4), so no fresh
Warm Up replay was captured. No entitlement or executable patches were applied.
Screenshots and private save data remain only under the ignored
`build/windows-reference/game` experiment; installed Steam assets were read only.
This startup does not establish the Windows math DLL selected on a user's real
Windows machine, nor exact historical Windows physics. The private Wine server
and Xvfb display were stopped afterward.


## Actual PE step capture and first-divergence attribution

A bounded debugger capture subsequently identified the live `leptet` call
boundary at `0x1400e8fb0` (caller return `0x1400e6b90`) in that exact executable.
Its 440-byte motor layout agrees with the shared source, including brake offset
380. Tutorial 1 geometry was extracted from the matching resource. Each captured
entry motor, exact `most`/`dt` bits and four controls was independently injected
into the shared source step with that geometry and normal default coefficients.
This compares the actual PE's unquantized motor state, rather than replay poses.

| Captured corpus | Linux GCC exact steps | Linux Clang exact steps |
|---|---:|---:|
| 256 idle Tutorial 1 steps | 256/256 | 256/256 |
| 256 throttle Tutorial 1 steps | 253/256 | 253/256 |

The throttle corpus contains two live attempts, with a timer reset at sample
195; it is a collection of independently matched steps, not one uninterrupted
trajectory. All 440 motor bytes are compared. The three differing steps (94,
112,189) differ by one ULP in seven double fields in total. GCC and Clang give
the same differences with floating point contraction disabled.

The actual process resolved its imports to **Wine's built-in x64 UCRT**, SHA-256
`ae1fd2b00f8cb22b642fb0c6ec9e33cc405ad7195ef46e26c26ed6aee7778166`,
not the separate Microsoft candidate discussed above. Captured MXCSR was
`0x1f80`/`0x1fa0` (precision sticky flag), x87 control `0x027f`: nearest rounding,
without FTZ/DAZ. A second bounded debugger session restored only the three
captured entry motors and arguments into the private process, then recorded its
math calls and output motors. All three output motors reproduced their original
PE captures exactly.

Five sine/cosine calls at four unique input bit patterns returned one ULP
away from Linux glibc. Substituting **only those four captured input/output
pairs** into the Linux one-step comparison made the entire throttle corpus
**256/256 exact**. This establishes the cause of the three observed differences
for this corpus. No shared physics or PS3 math was changed. It does not establish
complete equivalence on all levels, or historical Microsoft Windows behavior:
the reference remains the installed Steam PE executing under Wine's runtime.

Portable source tools are `test/windows_trace.py` (hash-gated bounded GDB
capture generator/runner) and `test/windows_step_compare.cpp` (source one-step
comparison). Start the authorized private Wine copy separately, then run the
capture tool with `--exe PRIVATE_EXE --out IGNORED_DIRECTORY --pid PID`.
`--generate-only` permits inspecting its commands before attaching. The GDB
addresses are deliberately restricted to the exact PE hash above; other builds
must first be remapped. The comparison accepts `LEVEL_TXT CAPTURE_DIRECTORY
OUTPUT_REPORT`, using the geometry text format of `test/physics_trace.cpp`.
Compile it with the same six shared physics sources and strict floating point
flags as the existing trace fixture. Private snapshots, extracted geometry,
GDB logs and math overrides are retained under ignored `build/windows-reference/`;
summary hashes are in `build/verification/windows-live-step.json`. These artifacts
contain proprietary runtime data and must not enter a source or release package.

A bounded four-angle console probe also called the separately identified
Microsoft 10.0.17134.12 candidate. For these four differing call pairs its results
matched Wine in three and glibc in one (`sin`, input `bfe4bb30038cad19`). Thus the
Wine override is a causal diagnostic, not a Microsoft compatibility correction.
The native candidate remains unverified as the game's actual Windows runtime.
The private probe log is `build/windows-reference/captured-angles.log`.
The comparison helper exits nonzero on any mismatch or empty corpus; a successful
report with differing states must not be interpreted as an equivalence pass.


## Local audit before the public shareware acquisition

A final read-only search limited to this repository, its private reference
folder and the known Steam Elma installation found `player/eol.exe` and an
identical `merged/eol.exe`. Their SHA-256 is
`40424cad1ff0ae5757c348d2b61d2d60599542c7799c05ab4a49c63bcc64cd87`.
This is a 430,080-byte PE32/i386 image with linker version 6 and a PE timestamp
of 2000-10-19 17:50:19 UTC. Its embedded strings identify an
“ElastoMania 1.11a to EOL 1.3 Patch” and “Registered version 1.3”; these are
identity clues, not authentication of an unmodified original 1.11a.

Static disassembly contains x87 `FSIN`, `FCOS` and `FSQRT` instructions
(for example VAs `0x41815e`, `0x41816f`, `0x403a34`). Imports include Win32,
DirectX, `wsock32.dll` and `bs.dll`, without an external CRT math DLL. The
known Steam tree does not contain `bs.dll`. No launch or patch was attempted,
and those instruction locations have not been mapped to a verified complete
physics step. Current x64 Steam/Wine UCRT comparisons cannot establish the
behavior of this x87-based, patched classic-derived binary.

At that pre-download audit, no authenticated unmodified 1.11a executable or
original build project with verified compiler/FP flags was found in the scoped
local locations. The subsequent public shareware acquisition below changes the
executable-availability finding, but not the missing original compiler metadata. The smallest
useful additional reference is an authorized, hash-identified 1.11a executable
with matching resource/level bytes, executed with its actual CPU/FP control and
runtime recorded. The bounded motor-entry/exit method can then be remapped to
its x86 physics function. A replay or a modern source rebuild alone does not
close this proof gap. Static findings are recorded in
`build/verification/windows-classic-static.json`; production PS3 math is unchanged.

## Hardware x87 endpoint diagnostic

`test/x87_math.c` directly executes host `FSIN`, `FCOS` and `FSQRT`, stores each
result to binary64, and compares it to the host glibc functions. It is a Linux
x86 diagnostic, not a PS3 math implementation or a complete instruction-stream
emulator. The deterministic corpus contains one million inputs in each range.

On the available AMD Ryzen 7 5700X3D, with glibc 2.43, nearest rounding, MXCSR
`0x1f80` and x87 control word `0x027f`, the measured results are:

| Input range | Sine differences | Cosine differences | Maximum sine/cosine ULP difference | Square-root differences |
|---|---:|---:|---|---:|
| [-pi, pi] | 1,325 | 1,321 | 5 / 19 | 0 |
| [-32, 32] | 1,974 | 1,795 | 344 / 29 | 0 |

The maximum absolute trigonometric difference is 1.1102230246251565e-16 in
both ranges. The large ULP counts occur near zeros of the functions (the maximum
sine case in the wider range is input 28.274333278076), not at large absolute
errors. Control word `0x037f` gives the same trigonometric results
in this corpus, but its extended-precision square root followed by a binary64
store introduces 283 and 239 one-ULP differences respectively. Thus even the
precision-control setting matters when reconstructing an original execution.

These values identify this host, not all historical x87 processors. Intel also
documents that x87 trigonometric instructions use a finite approximation of pi
and need not return the same values as software math functions:
[Intel's instruction-versus-math explanation](https://www.intel.com/content/www/us/en/developer/articles/technical/the-difference-between-x87-instructions-and-mathematical-functions.html).
The probe restores its caller's FP control state before returning. Source,
compiler flags, logs and hashes are indexed by `build/verification/x87-math.json`.
No production math was changed from this measurement.


## Public original 1.11a shareware: actual motor-step reference

The public [Moposite 1.11a information page](https://old.moposite.com/info_elasto_mania.php)
explicitly links the freely distributable 1122 KiB shareware
[installer](https://old.moposite.com/programs/elma111a_share.exe). The current
[publisher front page](https://elastomania.com/) links Moposite as community
history; it did not expose a classic 1.11a download. This is therefore a public
community-mirror source chain, **not a publisher signature or independently
verified archival master**. The installer license and actual runtime splash
identify 1.11a; the bundled readme retains the shorter 1.11 label.

| File | SHA-256 |
|---|---|
| Public installer, 1,148,755 bytes | `b52e556edb828a2edb1e28a0b6526c15013c970804fd0b00f1d6ced899b43a78` |
| Installed original PE32/i386 `Elma.exe` | `6781a4e1af27760086ae3e5b1e8e689824694483c715b51b3e5335c905d44737` |
| Its own shareware `Elma.res` | `f25c0f8ff5f51e8b7b3ad0284eed275a9213d35cedee1787f1c60906dfb22e2b` |

The private install uses only its 18 playable shareware levels and its own
Please Register sentinel. No registered assets, entitlement modifications or
on-disk executable patches were used. Other levels were reached through the
original permitted Skip Level UI. Bare fullscreen DirectDraw failed its 8-bit
mode on Xvfb; an isolated 640×480 Wine virtual desktop ran the unchanged game.
The PE timestamp is 2000-10-19 17:11:08 UTC and linker metadata is 6.0, neither
of which alone establishes the exact original compiler flags.

The actual `leptet` function is VA `0x420c20`, called at `0x41f9d2`, returning
to `0x41f9d7`. At entry the 32-bit cdecl stack contains motor pointer at ESP+4,
`most` double at +8, `dt` double at +16, and integer gas/brake/rotation1/rotation2
at +24/+28/+32/+36. The complete motor representation is 440 bytes. Hardware
breakpoints capture exact entry/exit motor bytes and argument bits. Captured
original FP state is x87 control `0x027f`, MXCSR `0x1f80`; original sine/cosine
instructions spill their initial endpoints to binary64 before vector creation.

The frozen corpus is **4,559 independently compared actual original motor
steps**. Every entry is injected into the shared source with geometry extracted
from the same shareware resource; no expected exit is substituted. The current
Linux implementation and actual native PPU each match **4,551**, with the same
**eight differing steps**. Every native PPU output matches Linux byte for byte
across all 4,559 steps (`build/verification/windows-classic-ppu-extended.json`):

| Original level and actual inputs | Steps | Current Linux exact |
|---|---:|---:|
| Warm Up idle | 256 | 256 |
| Warm Up gas | 256 | 256 |
| Warm Up brake and clockwise impulses | 922 | 919 |
| Twin Peaks gas and counterclockwise impulses | 1,004 | 1,004 |
| Flat Track gas, direction flip, simultaneous rotation inputs | 597 | 596 |
| Warm Up gas and direction flip, attempted apple approach | 1,524 | 1,520 |

Gas/brake raw values are 128 when pressed; rotation arguments are discrete
impulses. Both simultaneous rotation impulses and flipped motor orientation
are present in the Flat Track capture. Death/result menus were observed, and
captures bounded after gameplay stops retain only complete entry/exit pairs.
The apple attempt ended in death before collection: all its apple counts stay
zero. These captures do **not** establish apple activation, death detection or
finish transitions: those run outside `leptet`, and injecting each entry motor
also injects its existing object/history fields. They are not uninterrupted
cross-platform trajectory replays or an input/frame-pacing equivalence test.

The differences have two isolated causes. Replacing Linux sine/cosine endpoints
with actual host x87 FSIN/FCOS followed by FSTPL (control `0x027f`) removes six
of the eight differing steps. The remaining two use the driver's ellipse clamp:
original PE instructions at `0x403a8d` multiply **rxszorzo × x × x**, while the
shared source expression evaluates **x × x × rxszorzo**. The captured clamp
inputs/constants and arithmetic are retained in `frozen-seat/capture.log`.
A frozen motor injection reproduces the head/seat result there but does not
restore every original collision/global dependency; its full motor is not
claimed to reproduce. The independently captured real steps remain the primary
comparison evidence. The separate diagnostic x87-endpoint plus original-product-order build has
now independently matched all **4,559/4,559** captured steps, with no newly
introduced differences. A portable Bochs endpoint plus order candidate also
matches that same finite corpus; its scalar residuals against the measured AMD
CPU remain a separate limitation. See `build/verification/x87-candidate-game-steps.json`.
These diagnostic math/order experiments do not change
production PS3 physics. A portable original-x87 candidate remains separate
research and must not be accepted as a universal solution from this finite set.

The capture source is `test/windows_trace.py`, now hash-gated for both known
PEs. It selects `i386:x64-32` **before** attaching to the original's Wine process;
using the wrong architecture caused reproducible debugger resume faults. Full
GDB 17.2 and required libraries were extracted privately, not installed over the
system. `--skip-fp-registers` avoids a separate mixed-mode GDB XSAVE assertion;
the later capture manifests explicitly say FP registers were not recaptured.
Original FP control was measured in the earlier valid corpora, not inferred
from those later manifests. Timeout interrupts GDB first for graceful detach.

For example, after manually starting the private game and verifying its level:

```sh
CLASSIC_REF=/absolute/ignored/windows-classic-reference
LD_LIBRARY_PATH="$CLASSIC_REF/tools/usr/lib64" python3 test/windows_trace.py \
  --exe "$CLASSIC_REF/game/Elma.exe" --out "$CLASSIC_REF/new-capture" \
  --pid PRIVATE_GAME_PID --samples 1024 --timeout 10 \
  --gdb "$CLASSIC_REF/tools/usr/libexec/gdb" \
  --gdb-data-directory "$CLASSIC_REF/tools/usr/share/gdb" --skip-fp-registers
```

The output directory must use plain path characters without spaces/quotes
because of GDB's binary-dump filename parser. `test/windows_step_compare.cpp`
compares Linux one-step results; the separate `test/windows_ppu_compare.cpp`
decodes the canonical little-endian motor fields for actual PPU comparison.
Detailed hashes, per-job controls, geometry and snapshots are indexed by
`build/verification/windows-classic-live.json` and the native verification
artifacts. Public helper sources contain no proprietary executable/assets.
All downloaded files, Wine prefix, extracted geometry, snapshots and temporary
diagnostic overrides stay under ignored `build/windows-classic-reference/` and
are excluded from release packages. The final private game exited normally
with code 0, peak guarded RSS 288,768,000 bytes, and its Wine/Xvfb were stopped.
