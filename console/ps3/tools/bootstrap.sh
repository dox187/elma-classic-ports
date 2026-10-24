#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
source "$root/tools/env.sh"
release=nightly-2026-10-12
case "$(uname -sm)" in
    'Linux x86_64') platform=linux-X64; sha256=76b1b3bc9ac260a4ece86da520225da7f2f4e334174e37b850093ff925eeb900 ;;
    'Darwin arm64') platform=macos-ARM64; sha256=974a5ae84ce4800120bdf2331f2124034c90b846c9c152e05d15bd258ee3ffbb ;;
    'Darwin x86_64') platform=macos-X64; sha256=c1dbd7d03c5d1f993017c90f4789b0cd89dcc27ea7369ac9991f4f9535b30a5e ;;
    *) echo 'This pinned SDK supports Linux x86_64 and macOS arm64/x86_64.' >&2; exit 1 ;;
esac
archive="$root/.toolchain/ps3dev-$platform.tar.gz"
mkdir -p "$root/.toolchain"
if [[ ! -f "$archive" ]]; then
    curl -fL --retry 3 "https://github.com/ps3dev/ps3dev/releases/download/$release/ps3dev-$platform.tar.gz" -o "$archive.part"
    mv "$archive.part" "$archive"
fi
printf '%s  %s\n' "$sha256" "$archive" | elma_ps3_sha256 -c -
tar -xzf "$archive" -C "$root/.toolchain"
"$root/tools/build_sdl2.sh"
echo "SDK ready. Source $root/tools/env.sh"
