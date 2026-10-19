# musl libm subset

The PSn00bSDK C library has no double precision math functions. The game
core needs `sin`, `cos`, `atan2`, `exp`, `sqrt`, `floor`, `ceil` and `fabs`;
they come from musl 1.2.5 (MIT license, see `COPYRIGHT`), unchanged except:

- `libm.h` is a trimmed copy of musl's `src/internal/libm.h` (double
  precision helpers only, no long double or float variants);
- `musl_features.h` replaces musl's `<features.h>` (only the `hidden`
  macro), and `exp_data.h` and `sqrt_data.h` include it instead.

The functions run on libgcc's soft-float doubles, which round like the
IEEE hardware of the desktop builds. `sqrt` is computed with integers and is
correctly rounded. `console/psx/test/core_libm_test.c` compares the subset
with the host C library on the inputs the physics uses.

Source: https://musl.libc.org/releases/musl-1.2.5.tar.gz
(sha256 a9a118bbe84d8764da0ea0d28b3ab3fae8477fc7e4085d90102b8596fc7c75e4)
