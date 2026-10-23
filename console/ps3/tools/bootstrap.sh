#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
release=nightly-2026-10-12
archive="$root/.toolchain/ps3dev-linux-X64.tar.gz"
[[ "$(uname -sm)" == 'Linux x86_64' ]] || { echo 'This pinned SDK requires Linux x86_64.' >&2; exit 1; }
mkdir -p "$root/.toolchain"
if [[ ! -f "$archive" ]]; then
    curl -fL --retry 3 "https://github.com/ps3dev/ps3dev/releases/download/$release/ps3dev-linux-X64.tar.gz" -o "$archive.part"
    mv "$archive.part" "$archive"
fi
printf '%s  %s\n' 76b1b3bc9ac260a4ece86da520225da7f2f4e334174e37b850093ff925eeb900 "$archive" | sha256sum -c -
tar -xzf "$archive" -C "$root/.toolchain"
"$root/tools/build_sdl2.sh"
echo "SDK ready. Source $root/tools/env.sh"
