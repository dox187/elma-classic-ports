#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "$0")/env.sh"
[[ -x "$PS3DEV/ppu/bin/ppu-g++" ]] || { echo 'Run tools/bootstrap.sh first.' >&2; exit 1; }
build_dir="${ELMA_PS3_BUILD_DIR:-$ELMA_PS3_DIR/build}"
cmake -S "$ELMA_PS3_DIR" -B "$build_dir" -DCMAKE_TOOLCHAIN_FILE="$ELMA_PS3_DIR/toolchain.cmake" "$@"
build_jobs="${JOBS:-$(nproc)}"
if [[ -z "${JOBS:-}" && "$build_jobs" -gt 4 ]]; then build_jobs=4; fi
cmake --build "$build_dir" --parallel "$build_jobs"
