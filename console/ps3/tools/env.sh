# Source this file from bash to use the workspace-local SDK.
ELMA_PS3_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PS3DEV="${PS3DEV:-$ELMA_PS3_DIR/.toolchain/ps3dev}"
export PSL1GHT="$PS3DEV"
export PORTLIBS="$PS3DEV/portlibs/ppu"
export PATH="$PS3DEV/bin:$PS3DEV/ppu/bin:$PATH"

# macOS provides shasum rather than sha256sum; keep the same output/check format.
elma_ps3_sha256() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"
    else shasum -a 256 "$@"; fi
}

elma_ps3_build_jobs() {
    local jobs="${JOBS:-$(getconf _NPROCESSORS_ONLN)}"
    if [[ -z "${JOBS:-}" && "$jobs" -gt 4 ]]; then jobs=4; fi
    printf '%s\n' "$jobs"
}
