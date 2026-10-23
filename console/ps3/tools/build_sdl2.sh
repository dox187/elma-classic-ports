#!/usr/bin/env bash
# Rebuild pinned SDL2 with RSX quad rendering, targets and true Pixel Art filtering.
set -euo pipefail
source "$(dirname -- "$0")/env.sh"
commit=b81fbad4489918f5ed9c9c052238d7a25da9bab9
archive="$ELMA_PS3_DIR/.toolchain/sdl2-b81fbad.tar.gz"
sdl_source="$ELMA_PS3_DIR/.toolchain/SDL2-patched"
patch_file="$ELMA_PS3_DIR/sdk/sdl2-render-targets.patch"
if [[ ! -f "$archive" ]]; then
    curl -fL --retry 3 "https://github.com/shagkur/SDL_PSL1GHT/archive/$commit.tar.gz" -o "$archive.part"
    mv "$archive.part" "$archive"
fi
printf '%s  %s\n' 4f5d3fc55aa048b9ffc0d2960e324f5cf73857a5a51ad3dd71fbbc788c4c4e97 "$archive" | sha256sum -c -
stamp="$(sha256sum "$patch_file" | cut -d ' ' -f1)"
if [[ ! -f "$sdl_source/.elma-patch" || "$(cat "$sdl_source/.elma-patch")" != "$stamp" ]]; then
    rm -rf "$sdl_source"
    mkdir -p "$sdl_source"
    tar -xzf "$archive" --strip-components=1 -C "$sdl_source"
    patch -d "$sdl_source" -p1 < "$patch_file"
    printf '%s\n' "$stamp" > "$sdl_source/.elma-patch"
fi
cp "$ELMA_PS3_DIR/sdk/SDL3_PIXELART_LICENSE.txt" "$sdl_source/SDL3_PIXELART_LICENSE.txt"
python3 "$ELMA_PS3_DIR/tools/verify_sdl_shaders.py" "$sdl_source"
cd "$sdl_source"
CC=ppu-gcc CXX=ppu-g++ AR=ppu-ar RANLIB=ppu-ranlib \
    CFLAGS="-O2 -I$PS3DEV/ppu/include" LDFLAGS="-L$PS3DEV/ppu/lib -lrt -llv2" \
    ./configure --prefix="$PS3DEV/portlibs/ppu" --host=powerpc64-ps3-elf \
    --disable-shared --enable-static --enable-atomic=yes --enable-video-psl1ght=yes \
    --enable-joystick=yes --enable-audio=yes
build_jobs="${JOBS:-$(nproc)}"
if [[ -z "${JOBS:-}" && "$build_jobs" -gt 4 ]]; then build_jobs=4; fi
make -j"$build_jobs"
make install
mkdir -p "$PS3DEV/portlibs/ppu/share/elma"
printf '%s\n' "SDL2_PSL1GHT $commit" "archive-sha256 4f5d3fc55aa048b9ffc0d2960e324f5cf73857a5a51ad3dd71fbbc788c4c4e97" "patch-sha256 $stamp" > "$PS3DEV/portlibs/ppu/share/elma/sdl2-build.txt"
for shader in "$ELMA_PS3_DIR"/sdk/elma_*.vp "$ELMA_PS3_DIR"/sdk/elma_*.fp "$ELMA_PS3_DIR/sdk/SDL3_PIXELART_LICENSE.txt"; do
    printf 'shader-sha256 %s %s\n' "$(sha256sum "$shader" | cut -d ' ' -f1)" "$(basename "$shader")" >> "$PS3DEV/portlibs/ppu/share/elma/sdl2-build.txt"
done
