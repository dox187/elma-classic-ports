# Original x87 compatibility experiments

**Historical research, outside release acceptance.** On 2026-10-23 the user
selected this project’s PC SDL version as the final physics reference. Release
packages therefore use `ELMA_CLASSIC_X87=OFF`; this opt-in experiment remains
available for reproducibility and does not replace the SDL reference.

The default PS3 build still uses the deterministic Linux-compatible math
implementation. The source also provides an explicit `ELMA_CLASSIC_X87=ON`
build profile, backed by the pinned library in `third_party/elma_x87`. The
preceding isolated experiment reproduces all 4,559 captured original 1.11a
motor steps on both the host and native PPU. This is a useful
compatibility result, but not a universal original-physics guarantee: the
software x87 model has known differences from the actual AMD host, and finite measurements do not establish universal equivalence.

See [PHYSICS_PROVENANCE.md](PHYSICS_PROVENANCE.md) for the original executable,
resource hashes, capture boundaries and controls. No proprietary executable or
runtime snapshot is included in corresponding-source archives.

## What fixes the eight observed differences

Two changes are needed together:

1. Compute separate x87 `FSIN` and `FCOS` results, each stored to binary64 before
   the engine uses it. The original executable uses these instructions; a modern
   C library's sine/cosine results need not have identical bits. The host-only
   diagnostic wrapper [test/x87_step_wrap.c](test/x87_step_wrap.c) executes the
   actual host instructions with the captured `0x027f` control word and restores
   the caller's control word afterward.
2. Evaluate the rider normalization product as `rxszorzo*r.x*r.x`, matching the
   original instruction order. The shared source currently writes
   `r.x*r.x*rxszorzo`. With rounded double products, these are not necessarily
   identical. The source applies this order only when `ELMA_CLASSIC_X87` is
   enabled; ordinary SDL builds retain their existing evaluation order.

The instruction wrapper alone fixes six of the eight observed steps. The
product-order change fixes the remaining two. Enabling x87 arithmetic globally
at 53-bit precision did not fix the product-order counterexample.

| Actual original capture | Steps | Current Linux/PPU exact | Experimental host/PPU exact |
|---|---:|---:|---:|
| Warm Up idle | 256 | 256 | 256 |
| Warm Up throttle | 256 | 256 | 256 |
| Warm Up brake/rotation | 922 | 919 | 922 |
| Twin Peaks throttle/rotation | 1,004 | 1,004 | 1,004 |
| Flat Track direction/alovolt | 597 | 596 | 597 |
| Warm Up longer attempt | 1,524 | 1,520 | 1,524 |
| **Total** | **4,559** | **4,551** | **4,559** |

Each comparison covers all 440 motor bytes after one actual captured call, with
that call's input state, time, step length and controls. These are independently
injected steps, not a claim that a fresh continuous trajectory matches. The
longer Warm Up attempt did not collect an apple. Event orchestration, every
possible contact state and all histories remain outside this original corpus.

## Portable model and independent check

The portable experiment uses the official Bochs source at commit
`d9c3a9a87cb319da9053d385aac2b7814344b0bd`, compiling its minimal SoftFloat/FPU
dependencies and separate `fsin`/`fcos` entry points. Binary64 inputs are extended
exactly; results are rounded back to binary64. PPU configuration explicitly uses
big-endian storage and its verified 64-bit `long`/pointer and 128-bit integer
support. No x86 assembly is used in the PPU candidate.

This model is based on a reconstructed Intel instruction implementation. The
separate [x87-transcendental reference](https://github.com/xsleonard/x87-transcendental/blob/fdfeab8b804bd71e70f04183263ca1517b33c711/docs/validation.md)
identifies its target as Skylake and describes the hardware witnesses used for
validation. Its finite witnesses do not establish identity with every x86 CPU.
The independent reference at that pinned commit built successfully and passed
its API, saved-witness and captured-outcome tests locally.

Both libraries were compared with actual separate `FSIN`/`FCOS` instructions on
the AMD Ryzen 7 5700X3D host. Each range contains one million binary64 inputs from
the same fixed-seed generator. The table counts **binary64 result differences**:

| Input range | Bochs sine | Bochs cosine | Independent reference sine | Independent reference cosine |
|---|---:|---:|---:|---:|
| [-pi, pi] | 10 | 17 | 10 | 17 |
| [-32, 32] | 13 | 17 | 13 | 17 |

Thus 57 of four million scalar comparisons differ for each candidate. The
libraries also have the same aggregate counts of raw extended-precision
differences: about 3% differ by one bit at the 64-bit significand's last place.
Those raw 80-bit differences usually disappear when rounded to binary64.
Aggregate agreement is not a point-by-point comparison between the two models.
Varying the model's internal multiplication width did not remove the residuals
and was rejected; no lookup-table corrections were introduced.

The original executable running on this modern host is an actual executable
reference, but does not recreate a historical Pentium. Intel also documents why
[x87 instructions and mathematical library functions can differ](https://www.intel.com/content/www/us/en/developer/articles/technical/the-difference-between-x87-instructions-and-mathematical-functions.html).
The measured residuals alone do not establish which CPU implementation is the
intended canonical target. No such target has been silently selected.

A further diagnostic used MPFR at 256-bit precision, cross-checked at 384 bits
with no changed rounding results. It evaluated all 57 binary64 disagreement
cases and 1,000 deliberately balanced agreeing/differing raw-80 samples. Among
the 57 disagreements, the software reference matches correctly rounded
binary64 sine/cosine directly in 29 cases and the AMD instruction in 28. Neither
is uniformly correctly rounded even for small angles needing no reduction.
After substituting the exact stored 66-bit pi/2 for argument reduction, the
ideal extended80-then-binary64 result matches the reference in 6 cases and AMD
in 51. This explains why replacing either implementation with a more accurate
transcendental function is not automatically original-instruction emulation.
The selected 1,000 samples are diagnostic, not a population error-rate estimate.

## Native cost and evidence

The native PPU one-step candidate reproduces every byte of all 4,559 original
exit snapshots. Those canonical output streams were independently concatenated
and compared against the original files, in addition to the fixture's own
results. Production sources, SDL library, main executable and runtime packages
had unchanged hashes before and after the experiment.

In RPCS3's static interpreter, 10,000 sine/cosine pairs took 5,183 microseconds
with the current implementation and 468,254 microseconds with the software x87
candidate, about 90 times longer. This isolated measurement is **not** a
whole-game frame-rate ratio or a physical PS3 benchmark. Candidate text grew by
15,808 bytes and compressed SELF by 6,064 bytes in this small comparison fixture.

A separate full-game comparison of the isolated candidates used identical 720p
Original/Sharp output, a 640x360 host window and two-player Flag Tag controls.
Both sustained median 60.0 fps across seven steady 300-frame samples. Median
engine/event time was 1.29 ms for SDL and 1.33 ms for the candidate; both had
16.67 ms frames, 193,151 KiB free guest RAM and 23,839,008 bytes in nine RSX
allocations. Both exited normally and released all tracked RSX allocations.
This is one roughly 43-second active workload per build, not a long endurance
test or physical-hardware measurement. Its exact binaries precede the supported
build-profile integration and are recorded in `bochs-game-candidate.json`.

The opt-in build scopes the API calls to `LEPTET.CPP` and `VEKT2.CPP`, together
with the normalization product order in `BEALLIT.CPP`. It does not wrap global
libm symbols or change ordinary desktop builds. The allocation-free library
preserves its pinned upstream sources and notices; its portable adapter passes
the same two-million-angle endpoint hashes as the isolated reference. See the
build commands in [README.md](README.md) and the library's own provenance at
`third_party/elma_x87/README.md`. Native acceptance of this integrated build is
recorded separately from the earlier private experiment.

## Reproducing the host experiment

On an x86 Linux host with Git, Make, C/C++ compilers, Python 3 and standard shell
utilities, run from the repository root:

```sh
console/ps3/tools/probe_x87_candidate.sh --out console/ps3/build/x87-probe
```

This fetches the pinned official source into the diagnostic output directory,
builds only the required SoftFloat/FPU components and runs two million angles
(four million scalar comparisons). To reuse an existing clean checkout, add
`--source-cache /path/to/Bochs`. A wrong commit or modified tracked source is
rejected. The output retains upstream licenses, compiler identity, CPU/control
state, source hashes and endpoint hashes. Residual counts are measurements; the
script does not turn a nonzero count into a universal compatibility claim.

If private original captures and extracted geometry are available, add:

```sh
--one-step /path/to/warmup.txt /path/to/capture --original-product-order
```

The order change applies only to a generated source copy in that output
directory. The tested cached-source run reproduced the 57 endpoint differences
and all 922 Warm Up brake/rotation steps exactly. The standalone
[test/x87_endpoint_probe.cpp](test/x87_endpoint_probe.cpp) and script contain no
third-party instruction implementation or proprietary game data.

The ignored `build/verification` directory retains exact source/binary hashes,
commands and raw results:

- `x87-candidate.json`: model, host endpoint counts and diagnostic variants.
- `x87-candidate-game-steps.json`: both host candidates over the six captures.
- `x87-transcendental-endpoints.json`: independent reference build and counts.
- `x87-mpfr-diagnostic.json`: high-precision comparison and finite-pi analysis.
- `x87-repro-script.json`: public reproduction script and negative pin/hash checks.
- `bochs-ppu-candidate.json`: native outputs, baseline comparison, size and timing.
- `bochs-game-candidate.json`: matched bounded full-game performance experiment.
- `bochs-ppu/`: original-comparison canonical output streams and RPCS3 logs.

These results justify continued compatibility work. They do not justify calling
the released build 100% identical to the original or replacing its math without
resolving the remaining correctness and runtime questions.
