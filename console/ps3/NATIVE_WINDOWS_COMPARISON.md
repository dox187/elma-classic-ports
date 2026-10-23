# Original Windows captures versus native PPU

This is historical diagnostic evidence. The user selected the project’s PC SDL
version as the final physics reference on 2026-10-23, with
`ELMA_CLASSIC_X87=OFF`. Windows equality is not the selected release criterion.

Recorded default-SDL comparison: **4551/4559** captured original 1.11a motor
outputs match exactly across three levels; eight calls differ. **All 4559**
native PPU outputs match the current Linux host engine byte for byte. See
`build/verification/windows-classic-ppu-extended.json` for all six capture cases,
per-level geometry hashes and exact differing fields. No production math was
changed.

`test/windows_ppu_compare.cpp` feeds captured original Windows physics-step
entries to the native PPU `leptet` implementation and compares all 440 output
bytes in canonical little-endian form. It includes the same geometry loader and
physics stubs as `physics_trace.cpp`, links the original engine sources and
production `elma-math`, and inherits the `physics-trace` compiler/link settings.
It links no Windows code and changes no production arithmetic.

The capture format is `inputs.txt`, one line per call:

```
index most_double_bits_hex dt_double_bits_hex gas brake rotate1 rotate2
```

Each index has `entry-N.bin` and `exit-N.bin`, exactly 440 bytes each. These
private capture files and level geometry stay under ignored `build/` directories.
The helper asserts the native sizes and every captured scalar offset. It
decodes 39 doubles and 7 integers explicitly; circle names, their padding and
the motor's padding remain opaque bytes. A decode/encode roundtrip must preserve
every entry byte before the engine runs. The result is encoded back to LE,
including untouched fields, names and padding, then compared against the
original exit. Each call starts from its captured entry; this is a one-step
comparison rather than an independently evolving trajectory comparison.

Build with the workspace SDK:

```
source console/ps3/tools/env.sh
cmake --build console/ps3/build --target windows-ppu-compare --parallel 4
sprxlinker console/ps3/build/windows-ppu-compare.elf
make_self console/ps3/build/windows-ppu-compare.elf console/ps3/build/windows-ppu-compare.self
```

Apply `sprxlinker` after a fresh link and before signing. The helper reads
`/dev_hdd0/game/ELMAC0001/USRDIR/windows-compare/jobs.txt`. Each whitespace-separated
line contains a case name, absolute native geometry-file path, and absolute
native capture-directory path. Copy captures into the isolated profile's
corresponding `dev_hdd0` directory; use path components without spaces. For
example:

```
idle256 /dev_hdd0/game/ELMAC0001/USRDIR/windows-compare/warmup.txt /dev_hdd0/game/ELMAC0001/USRDIR/windows-compare/idle256
```

Run the SELF with the existing bounded `test/rpcs3.py` harness and Null
renderer/audio. Require the complete `WINDOWS PPU RESULT` marker and
`windows-compare/ppu-result.txt`; RPCS3 exit status alone is insufficient.
Each capture directory receives `ppu-canonical.bin`, 440 bytes per input line
in input order. Compare that stream byte-for-byte and by SHA256 against the
concatenation of original `exit-N.bin` files in that same order.

Initial direct native evidence is `build/verification/windows-classic-ppu.json`:
256 idle and 256 throttle calls captured from the original 1.11a shareware PE
match exactly (512/512 complete motor states, zero differences). Its original
executable identity, geometry/capture/source/compiler/library/native-binary
hashes and canonical output hashes are recorded. The PE executed under Wine on
this host; this neither identifies historical PC hardware behavior nor proves
every possible input or a physical PS3 result. Broader capture coverage should
be added as separate measured cases, without weakening the full-byte criterion.

A broader measurement supersedes an all-exact headline:
`build/verification/windows-classic-ppu-broader.json` adds a 922-step Warm Up
brake/rotation capture. In total, **1431 of 1434** original output states match;
three calls (capture indices 346, 588 and 911 in `warmup-brake`) differ in seven
double fields by one or two adjacent bit-pattern units. Every one of the 1434
native PPU canonical output states is byte-identical to the current Linux host
engine comparator. The measured discrepancy is therefore also present on the
host, rather than newly introduced by PPU endian conversion. Production math
has not been changed to conceal the counterexample. The report preserves both
original and native/host hashes and every differing field.

The helper can also be built on the host with the same engine sources and
strict arithmetic flags. Without `ELMA_PS3`, its sole command-line argument is
the jobs-directory path and it writes `host-canonical.bin` in each case
directory. This permits a direct full-byte host/PPU comparison even when an
original PE output differs. The native path and original full-byte acceptance
criterion remain unchanged.
