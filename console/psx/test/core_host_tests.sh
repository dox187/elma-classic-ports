#!/bin/sh
# Host-side tests of the pieces the PS1 build adds to the game core: the
# vendored musl math subset and the small FILE layer. They need only the
# host C and C++ compilers. Output goes to console/psx/build/host-tests/.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
out=${1:-$here/build/host-tests}
mkdir -p "$out"
cc=${CC:-cc}
libm=$here/third_party/musl-libm/src

# The musl functions get an m_ prefix so that the test can call both them and
# the host library.
prefix=""
for f in sin cos atan2 atan exp sqrt floor ceil fabs scalbn __sin __cos __rem_pio2 \
         __rem_pio2_large __math_oflow __math_uflow __math_xflow __math_invalid \
         __exp_data __rsqrt_tab; do
    prefix="$prefix -D$f=m_$f"
done
objs=""
for src in "$libm"/*.c; do
    obj=$out/musl_$(basename "$src" .c).o
    # shellcheck disable=SC2086
    $cc -std=c99 -O2 -ffp-contract=off -fno-builtin -w $prefix -I"$here/src/include" -I"$libm" -c "$src" -o "$obj"
    objs="$objs $obj"
done
# shellcheck disable=SC2086
$cc -std=gnu99 -O2 -ffp-contract=off -fno-builtin "$here/test/core_libm_test.c" $objs -lm \
    -o "$out/core_libm_test"
"$out/core_libm_test"

$cc -std=c99 -O2 -Wall -Wextra -DPSX_FILE_HOST_TEST -I"$here/src" \
    "$here/test/core_file_test.c" "$here/src/psx_file.c" "$here/src/memcard/mclz.c" \
    -o "$out/core_file_test"
"$out/core_file_test" "$out/file-test"

$cc -std=c99 -O2 -Wall -Wextra -DPSX_FILE_HOST_TEST -I"$here/src" \
    "$here/test/core_file_alloc_test.c" "$here/src/memcard/mclz.c" \
    -o "$out/core_file_alloc_test"
"$out/core_file_alloc_test"

${CXX:-c++} -std=c++11 -O2 -Wall -Wextra -Werror -I"$here/src" \
    "$here/test/pcx_host_test.cpp" -o "$out/pcx_host_test"
"$out/pcx_host_test"

$cc -std=c99 -O2 -Wall -Wextra -Wno-pointer-to-int-cast \
    "$here/test/heap_host_test.c" -o "$out/heap_host_test"
"$out/heap_host_test"
