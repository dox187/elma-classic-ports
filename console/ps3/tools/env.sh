# Source this file from bash to use the workspace-local SDK.
ELMA_PS3_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PS3DEV="${PS3DEV:-$ELMA_PS3_DIR/.toolchain/ps3dev}"
export PSL1GHT="$PS3DEV"
export PORTLIBS="$PS3DEV/portlibs/ppu"
export PATH="$PS3DEV/bin:$PS3DEV/ppu/bin:$PATH"
