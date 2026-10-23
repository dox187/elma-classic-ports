This directory contains the IBM Accurate Mathematical Library sin/cos routines
from glibc (`sysdeps/ieee754/dbl-64`, upstream master, retrieved 2026-10-23):
https://github.com/bminor/glibc/tree/master/sysdeps/ieee754/dbl-64

The PSL1GHT SDK's newlib libm uses an older approximation that changes even
`cos(0)`, which changes the rider's collision position before the first physics
step. These routines restore the desktop reference's binary64 results.

The upstream files retain their copyright and LGPL-2.1-or-later notices; see
COPYING.LIB. Adaptations are limited to symbol prefixes, byte-order macros,
standalone include paths and removal of glibc's private floating-point exception
bookkeeping. The engine always uses round-to-nearest and does not inspect those
exception flags. ps3_math.c exports the standard sin, cos and sincos names.

Compile s_sin.c with floating-point contraction enabled to reproduce the
FMA variant selected by the desktop glibc reference. Compile branred.c with
contraction disabled: its double-splitting range reduction depends on separate
rounding of operations. Keep contraction disabled
for the game physics itself. The PPU provides the same correctly rounded
binary64 fused multiply-add operation. The full original-engine trajectory
corpus in console/ps3/test/physics_test.py verifies the resulting bit patterns.

Other platforms continue using their existing libm. No fixed-point physics or
approximated lookup-table engine is introduced.
