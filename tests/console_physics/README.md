# Common console physics benchmark

The reference is the original C++ bike and collision code built on the host
with double precision, native math functions and floating-point contraction
disabled. All five implementations start at each course's own start marker
with the default bike direction. They receive the same controller timeline.
The original Windows 1.11a executable has a [separate capture comparison](../../console/ps3/NATIVE_WINDOWS_COMPARISON.md).

## What each ride tests

Each of the 54 registered courses gets a 12-second throttle run and a
12-second sequence of acceleration, braking, coasting and rotations in both
directions. Two longer rides test opposite rotations during a Freefall descent
and a Flat Track run that reaches the flower on PC at tick 683. The scripts
do not correct the bike midride or restart after a crash. The suite has 110
runs and 40,104 scheduled observation ticks per implementation. [Input sequences](corpus.py)

## Reading the numbers

- **Position** measures the distance between the PC and port bike centres as
  a percentage of the axle-to-axle distance of the original bike at rest.
  A bike one full wheelbase away scores 100% error.
- **Tilt** measures the shortest angular difference between the two frames.
  For both pose columns, we average the error over each ride up to and
  including the PC's crash or finish, then give each ride equal weight. If a
  port crashes early, its last pose stays in the comparison.
- **Same outcome** counts rides where both are still riding at the deadline,
  both crash, or both finish. **Within one tick** counts PC crashes or finishes
  that the port reproduces within ±1 observation tick. An early crash and a
  late crash can agree in the first column and differ in the second.

Buttons change on a 30 Hz simulation clock. Each solver takes input at the
start of its own update and runs its usual physics steps. For poses between
updates we interpolate position and the shortest body-angle arc at the common
sample time. A crash or finish is recorded at the first sample on or after it.
Rendering delays do not advance this clock. The suite measures body motion
and these two events. Independent wheel motion and pickup timing have no
separate score. [Scoring](run.py) · [Published results and input hashes](results.json)

## Reproduce

Run from the repository root with Python 3, NumPy, the GBC port's PyBoy test
dependencies, a host C/C++ compiler, CMake, the PS3 port's PSL1GHT SDK and RPCS3
with firmware installed. Supply your registered game resource and a matching
local GBC build with its generated directory, build manifest and linker symbols.

```sh
python3 tests/console_physics/run.py --res "$ELMA_RES" \
  --gbc-rom "$GBC_ROM" --gbc-gen "$GBC_GEN" --output scores.json
```

The GBC adapter drives the ROM through its menus and buttons in PyBoy. The
PS3 adapter runs the native PPU physics fixture in an isolated RPCS3 profile.
The NES and SNES adapters run the host C models of the shipping assembly
solvers, with each port's converted geometry and native update rate. The
PlayStation adapter runs the port's fixed-point code and the PC reference from
the same level data. Floating-point results may differ in the last digits
across host math libraries.
