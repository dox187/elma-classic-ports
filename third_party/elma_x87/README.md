# Standalone Classic x87 trigonometry

This directory builds the `elma-classic-x87` static CMake target. It does not
select a game physics profile. The parent build must explicitly opt in; the
existing SDL math remains the default.

## Origin and source boundary

The files under `upstream/` are unchanged extracts of official
[Bochs](https://github.com/bochs-emu/Bochs/tree/d9c3a9a87cb319da9053d385aac2b7814344b0bd),
commit `d9c3a9a87cb319da9053d385aac2b7814344b0bd`.
`UPSTREAM.json` records the original repository paths and SHA-256 of all 46
copied files, checked against that commit's Git blobs. No generated Bochs
configuration, emulator CPU/device code, or external reconstructed x87 project
is included.

The compilation closure is 26 SoftFloat translation units plus `fsincos.cc`
and `f128_67.cc`, listed explicitly in `CMakeLists.txt`. It includes the
conversion, binary128 polynomial arithmetic, rounding, and NaN helpers needed
by those unmodified translation units. Keeping the original combined
trigonometry unit also retains its tangent/division dependencies. Nine
SoftFloat headers and five FPU headers complete the code closure.

`shim/config.h`, `elma_x87.h`, `elma_x87.cpp`, the CMake file and tests are local
integration files, not upstream modifications. The shim supplies fixed-width
Bochs integer aliases, compiler byte-order detection, compiler integer128 and
CLZ capability detection, and inline/constant macros. It replaces the full
Bochs configure output. It does not assume 32-bit `long` or pointers: the
PSL1GHT PPU compiler uses big-endian 64-bit `long`/pointers and supports
`__int128`; the host uses little-endian 64-bit `long`/pointers.

## API and limits

`elma_x87.h` exposes allocation-free C ABI functions `elma_x87_sin`,
`elma_x87_cos` and `elma_x87_sincos`. Each lane converts binary64 to extended80,
runs the emulated standalone FSIN or FCOS, then rounds to binary64. Rounding
is nearest/even, extended precision is 80-bit, exceptions are masked, and all
status is local to the call. The combined API deliberately evaluates separate
FSIN/FCOS lanes, rather than the distinct FSINCOS instruction. Its two output
pointers must be valid. There is no host libm call, allocation, lookup repair,
or global floating-point environment change.

This is the pinned Bochs approximation, not a claim of correctly rounded
mathematical sine/cosine or universal Intel/AMD bit identity. For unsupported
large finite operands (magnitude at least 2^63), upstream FSIN/FCOS leaves the
operand unchanged; this adapter preserves that behavior, without a libm
fallback. The intended game inputs are small finite angles. NaN/infinity
behavior follows upstream masked-exception conversion and arithmetic.

## Build and verification

```sh
cmake -S third_party/elma_x87 -B /tmp/elma-x87-build \
  -DCMAKE_BUILD_TYPE=Release -DELMA_X87_BUILD_TESTS=ON
cmake --build /tmp/elma-x87-build
ctest --test-dir /tmp/elma-x87-build --output-on-failure
/tmp/elma-x87-build/elma-x87-endpoint-test --full
```

Use the existing PS3 toolchain file for a PPU static-library build; the parent
PS3 build supplies Cell CPU flags. C++11 is sufficient. The target enforces
no fast math or contraction, signed chars, wrap semantics and no strict
aliasing, alongside the upstream SoftFloat integer configuration. There are
no filesystem, threading, SDL or SDK runtime dependencies in this library.

The endpoint regression hashes exact binary64 results (normalized byte order)
for deterministic LCG samples, seed 12345678, multiplier 6364136223846793005,
increment 1. Each range resets the seed. The default checks 10,000 inputs per
range; `--full` checks 1,000,000 per range, in [-pi,pi] and [-32,32]. Goldens
were generated independently with the earlier separately built pinned Bochs
model. The combined API must match both separate lanes at every input. Hashes
are regression evidence for this model, not hardware conformance assertions.

## License notices

Keep the upstream notices and this provenance when redistributing. These
components have their own licensing boundary; the game's license does not
replace them:

- `upstream/bochs/LICENSE` describes the Bochs licensing arrangement.
- `upstream/bochs/COPYING` supplies the GNU LGPL 2.1 text. Bochs FPU headers
  carry LGPL 2-or-later notices; retain their individual notices.
- `upstream/bochs/cpu/softfloat3e/COPYING.txt` supplies the SoftFloat 3e
  three-clause redistribution conditions; `README.txt` supplies its upstream
  description. Preserve the copyright/disclaimer blocks in individual files.
- `fsincos.cc` also retains its earlier SoftFloat Release 2b derivative
  notice. Do not relabel all vendor files as BSD or as game code.

The local shim, API wrapper, build file and regression test are offered under
the GNU LGPL version 2.1 or later, without warranty; see the included LGPL
text. A distributed linked build must retain applicable notices and provide
corresponding library source/build and relinking materials as required by the
applicable licenses. The complete source archive includes this directory.
