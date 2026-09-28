#!/bin/sh
# Builds Elasto Mania for handheld Linux devices in a container and packs it
# for the device's launcher:
#
#   handheld/build.sh portmaster   64-bit ARM handhelds with PortMaster
#                                  (RGB30, RG353, RG35XX H/Plus/SP, ...)
#   handheld/build.sh miyoomini    Miyoo Mini and Mini Plus with Onion OS or MinUI
#
# Further arguments go to CMake, for example -DELMA_REGISTERED=ON.
# The package is written to dist/<target>/. Needs podman or docker.
set -eu

target=${1:-}
[ $# -gt 0 ] && shift
root=$(cd "$(dirname "$0")/.." && pwd)

case $target in
portmaster)
    image=elma-aarch64-toolchain
    toolchain=handheld/aarch64-linux-gnu.cmake
    platform=handheld
    strip=aarch64-linux-gnu-strip
    ;;
miyoomini)
    image=docker.io/aemiii91/miyoomini-toolchain:latest
    toolchain=handheld/miyoomini.cmake
    platform=miyoomini
    strip=/opt/miyoomini-toolchain/bin/arm-linux-gnueabihf-strip
    ;;
*)
    echo "usage: $0 portmaster|miyoomini [cmake options]" >&2
    exit 1
    ;;
esac

engine=${CONTAINER_ENGINE:-}
if [ -z "$engine" ]; then
    if command -v podman >/dev/null 2>&1; then engine=podman
    elif command -v docker >/dev/null 2>&1; then engine=docker
    else echo "podman or docker is needed" >&2; exit 1
    fi
fi

# Rootless podman runs the container as the current user; docker has to be
# told, otherwise the build files end up owned by root.
user=""
[ "$(basename "$engine")" = docker ] && user="--user $(id -u):$(id -g)"

if [ "$target" = portmaster ] && ! "$engine" image inspect "$image" >/dev/null 2>&1; then
    "$engine" build -t "$image" -f "$root/handheld/aarch64.Dockerfile" "$root/handheld"
fi

build=build-$target
# shellcheck disable=SC2086
"$engine" run --rm $user --security-opt label=disable -v "$root:/src" -w /src "$image" sh -c '
    build=$1 toolchain=$2 platform=$3 strip=$4
    shift 4
    cmake -S . -B "$build" -DCMAKE_TOOLCHAIN_FILE="$toolchain" \
        -DELMA_PLATFORM="$platform" -DCMAKE_BUILD_TYPE=Release -DELMA_REGISTERED=OFF "$@" &&
    cmake --build "$build" -j "$(nproc)" &&
    "$strip" -o "$build/elma.stripped" "$build/elma"
' sh "$build" "$toolchain" "$platform" "$strip" "$@"

# The license has to stay with anything built from the source. The notice
# credits the authors and tells which source and game data the build needs.
add_license() {
    cp "$root/LICENSE.md" "$root/handheld/NOTICE.txt" "$1/"
    cp "$root/third_party/hqx/COPYING" "$1/LICENSE-hqx.txt"
    commit=$(git -C "$root" rev-parse --short HEAD 2>/dev/null || true)
    if [ -n "$commit" ]; then
        git -C "$root" diff --quiet HEAD 2>/dev/null || commit="$commit, with uncommitted changes"
        printf '\nBuilt from commit %s.\n' "$commit" >> "$1/NOTICE.txt"
    fi
    edition=shareware
    grep -q '^ELMA_REGISTERED:BOOL=ON' "$root/$build/CMakeCache.txt" && edition=registered
    printf 'This build needs the game data of the %s version.\n' "$edition" >> "$1/NOTICE.txt"
}

dist=$root/dist/$target
rm -rf "$dist"
case $target in
portmaster)
    mkdir -p "$dist/elastomania"
    cp "$root/handheld/portmaster/elastomania.sh" "$dist/Elasto Mania.sh"
    cp "$root/$build/elma.stripped" "$dist/elastomania/elma"
    add_license "$dist/elastomania"
    chmod +x "$dist/Elasto Mania.sh" "$dist/elastomania/elma"
    echo "Copy the contents of $dist to the ports folder of the device,"
    echo "and the game data (elma.res, lgr, lev, ...) into its elastomania folder."
    ;;
miyoomini)
    mkdir -p "$dist/ElastoMania"
    cp "$root/handheld/miyoomini/launch.sh" "$root/handheld/miyoomini/config.json" "$dist/ElastoMania/"
    cp "$root/$build/elma.stripped" "$dist/ElastoMania/elma"
    add_license "$dist/ElastoMania"
    cp "$root/handheld/miyoomini/elastomania.port" "$dist/Elasto Mania.port"
    chmod +x "$dist/ElastoMania/launch.sh" "$dist/ElastoMania/elma" "$dist/Elasto Mania.port"
    echo "Onion OS: copy $dist/ElastoMania to Roms/PORTS/Games/ and"
    echo "'Elasto Mania.port' to Roms/PORTS/Shortcuts/, or the folder alone to App/."
    echo "MinUI: copy the folder to Tools/miyoomini/ as 'Elasto Mania.pak'."
    echo "Put the game data (elma.res, lgr, lev, ...) into the ElastoMania folder."
    ;;
esac
