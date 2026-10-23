#!/usr/bin/env bash
# Package only user-supplied game data; no proprietary data is downloaded.
set -euo pipefail
source "$(dirname -- "$0")/env.sh"
data="${1:-}"
if [[ -n "$data" && ( ! -d "$data" || ! -f "$data/elma.res" ) ]]; then
    echo "Usage: $0 [GAME_DATA_DIRECTORY containing elma.res]" >&2; exit 1
fi
build_dir="$(realpath "${ELMA_PS3_BUILD_DIR:-$ELMA_PS3_DIR/build}")"
profile_cache="$(sed -n 's/^ELMA_CLASSIC_X87:BOOL=//p' "$build_dir/CMakeCache.txt")"
case "$profile_cache" in
    OFF) physics_profile=sdl; profile_suffix= ;;
    ON) physics_profile=classic-x87; profile_suffix=-classic-x87 ;;
    *) echo "Missing or invalid ELMA_CLASSIC_X87:BOOL in $build_dir/CMakeCache.txt" >&2; exit 1 ;;
esac
echo "Packaging physics profile: $physics_profile ($build_dir)"
elf="$build_dir/elma.elf"
[[ -f "$elf" ]] || { echo 'Build the ELF first with tools/build.sh.' >&2; exit 1; }
# Reject packages that would silently mix new source with an old executable.
python3 - "$ELMA_PS3_DIR" "$elf" "$build_dir" "$physics_profile" <<'PYCHECK'
import os, pathlib, shlex, sys
root, elf, build = map(pathlib.Path, sys.argv[1:4])
classic = sys.argv[4] == 'classic-x87'
stale = set()
flags=(build/'CMakeFiles/elma.dir/flags.make').read_text()
if ('-DELMA_CLASSIC_X87' in flags) != classic:
    raise SystemExit('Build compile definitions differ from selected physics profile')
import subprocess
symbols=subprocess.check_output(['ppu-nm',str(elf)],text=True)
if bool(__import__('re').search(r'\b[TD] \.?elma_x87_sin$',symbols,__import__('re').M)) != classic:
    raise SystemExit('ELF physics symbols differ from selected profile; rebuild first')
marker=b'ELMA PS3 physics: classic_x87 (experimental)' if classic else b'ELMA PS3 physics: sdl'
if marker not in elf.read_bytes(): raise SystemExit('ELF startup profile marker differs; rebuild first')
for generated in [build/'CMakeFiles/elma.dir/flags.make', build/'CMakeFiles/elma.dir/link.txt']:
    if generated.stat().st_mtime_ns > elf.stat().st_mtime_ns: stale.add(str(generated))

for target in ('elma', 'hqx', 'elma-math') + (('elma-classic-x87',) if classic else ()):
    target_dir = build/('elma-x87/CMakeFiles' if target=='elma-classic-x87' else 'CMakeFiles')/f'{target}.dir'
    deps = list(target_dir.rglob('*.obj.d'))
    if not deps:
        raise SystemExit(f'No {target} dependency records; run tools/build.sh first')
    for record in deps:
        text = record.read_text().replace('\\\n', ' ')
        for name in shlex.split(text.split(':', 1)[1]):
            p = pathlib.Path(name)
            if p.is_file() and p.stat().st_mtime_ns > elf.stat().st_mtime_ns:
                stale.add(str(p))
for library in (pathlib.Path(os.environ['PS3DEV'])/'portlibs/ppu/lib/libSDL2.a', build/'libhqx.a', build/'libelma-math.a'):
    if not library.is_file(): raise SystemExit('Missing linked library: '+str(library))
    if library.stat().st_mtime_ns > elf.stat().st_mtime_ns:
        stale.add(str(library))
if classic:
    libraries = [build/'elma-x87/libelma-classic-x87.a']
    libraries = [p for p in libraries if p.is_file()]
    if len(libraries) != 1: raise SystemExit('Missing or ambiguous Classic x87 library')
    if libraries[0].stat().st_mtime_ns > elf.stat().st_mtime_ns: stale.add(str(libraries[0]))
metadata = pathlib.Path(os.environ['PS3DEV'])/'portlibs/ppu/share/elma/sdl2-build.txt'
import hashlib
patch_sha = hashlib.sha256((root/'sdk/sdl2-render-targets.patch').read_bytes()).hexdigest()
if not metadata.is_file() or 'patch-sha256 '+patch_sha not in metadata.read_text():
    raise SystemExit('Installed SDL2 patch provenance differs; run tools/build_sdl2.sh then rebuild the game')
for shader in list((root/'sdk').glob('elma_*.vp'))+list((root/'sdk').glob('elma_*.fp'))+[root/'sdk/SDL3_PIXELART_LICENSE.txt']:
    expected='shader-sha256 '+hashlib.sha256(shader.read_bytes()).hexdigest()+' '+shader.name
    if expected not in metadata.read_text():
        raise SystemExit('Installed shader provenance differs: '+str(shader))
if stale:
    raise SystemExit('ELF is older than compiled source/header dependencies; rebuild first:\n'+'\n'.join(sorted(stale)))
PYCHECK
out="$ELMA_PS3_DIR/dist"
version="$(cat "$ELMA_PS3_DIR/VERSION")"
kind=code
[[ -z "$data" ]] || kind=with-data
name="elma-classic-ps3-v$version$profile_suffix-$kind"
stage="$out/$name/ELMAC0001"
# Recreate staging so removed assets cannot leak in from an older data package.
python3 - "$stage" <<'PYCLEAN'
import pathlib, shutil, sys
stage = pathlib.Path(sys.argv[1])
if stage.exists(): shutil.rmtree(stage)
stage.mkdir(parents=True)
PYCLEAN
mkdir -p "$stage/USRDIR"
ppu-strip "$elf" -o "$out/elma-stripped.elf"
sprxlinker "$out/elma-stripped.elf"
make_self "$out/elma-stripped.elf" "$out/$name.self"
fself "$out/elma-stripped.elf" "$out/$name.fake.self"
content=UP0001-ELMAC0001_00-ELMACLASSIC000000
make_self_npdrm "$out/elma-stripped.elf" "$stage/USRDIR/EBOOT.BIN" "$content"
# Match the SDK NPDRM entry alignment before hashing staging files, so an
# actual package installation reproduces EBOOT.BIN byte for byte.
python3 - "$stage/USRDIR/EBOOT.BIN" <<'PYPAD'
import pathlib,sys
p=pathlib.Path(sys.argv[1]);data=p.read_bytes()
size=((len(data)-0x30+63)&~63)+0x30
p.write_bytes(data+bytes(size-len(data)))
PYPAD
python3 - "$ELMA_PS3_DIR/assets/PARAM.SFO.xml" "$out/$name.sfo.xml" "$version" <<'PYSFO'
import re, sys, xml.etree.ElementTree as ET
source, dest, version = sys.argv[1:]
parts = version.split('.')
if len(parts) != 3 or not all(p.isdigit() for p in parts) or int(parts[0]) > 99 or int(parts[1]) > 99:
    raise SystemExit('VERSION must be major.minor.patch; major/minor <= 99 for PS3 APP_VER')
app_ver = f'{int(parts[0]):02d}.{int(parts[1]):02d}'
tree = ET.parse(source)
for value in tree.getroot():
    if value.get('name') in ('APP_VER','VERSION'): value.text = app_ver
    if value.get('name') == 'TITLE': value.text = 'Elasto Mania Classic '+version
tree.write(dest, encoding='utf-8', xml_declaration=True)
PYSFO
sfo -f "$out/$name.sfo.xml" "$stage/PARAM.SFO"
cp "$ELMA_PS3_DIR/assets/ICON0.PNG" "$stage/ICON0.PNG"
mkdir -p "$stage/USRDIR/licenses/elma" "$stage/USRDIR/licenses/hqx" "$stage/USRDIR/licenses/elma_libm" "$stage/USRDIR/licenses/SDL2"
cp "$ELMA_PS3_DIR/../../LICENSE.md" "$stage/USRDIR/licenses/elma/"
cp "$ELMA_PS3_DIR/../../third_party/hqx/README.md" "$ELMA_PS3_DIR/../../third_party/hqx/COPYING" "$ELMA_PS3_DIR/../../third_party/hqx/AUTHORS" "$stage/USRDIR/licenses/hqx/"
cp "$ELMA_PS3_DIR/../../third_party/elma_libm/README.md" "$ELMA_PS3_DIR/../../third_party/elma_libm/COPYING.LIB" "$stage/USRDIR/licenses/elma_libm/"
cp "$ELMA_PS3_DIR/.toolchain/SDL2-patched/COPYING.txt" "$stage/USRDIR/licenses/SDL2/"
mkdir -p "$stage/USRDIR/licenses/SDL2/shaders"
cp "$ELMA_PS3_DIR"/sdk/elma_*.vp "$ELMA_PS3_DIR"/sdk/elma_*.fp "$stage/USRDIR/licenses/SDL2/shaders/"
cp "$ELMA_PS3_DIR/sdk/SDL3_PIXELART_LICENSE.txt" "$stage/USRDIR/licenses/SDL2/"
cp "$PS3DEV/portlibs/ppu/share/elma/sdl2-build.txt" "$stage/USRDIR/licenses/SDL2/"
cp "$ELMA_PS3_DIR/../../third_party/elma_libm/COPYING.LIB" "$stage/USRDIR/licenses/SDL2/"
cp "$ELMA_PS3_DIR/.toolchain/SDL2-patched/src/render/psl1ght/SDL_PSL1GHTrender.c" "$stage/USRDIR/licenses/SDL2/"
if [[ "$physics_profile" == classic-x87 ]]; then
    x87_source="$ELMA_PS3_DIR/../../third_party/elma_x87"
    x87_notices="$stage/USRDIR/licenses/elma_x87"
    mkdir -p "$x87_notices/softfloat3e"
    cp "$x87_source/README.md" "$x87_source/UPSTREAM.json" "$x87_notices/"
    cp "$x87_source/upstream/bochs/LICENSE" "$x87_source/upstream/bochs/COPYING" "$x87_notices/"
    cp "$x87_source/upstream/bochs/cpu/softfloat3e/COPYING.txt" "$x87_source/upstream/bochs/cpu/softfloat3e/README.txt" "$x87_notices/softfloat3e/"
fi
# Keep game installation hierarchy and optional editor/replay/assets intact.
for item in elma.res lgr lev rec snaps; do
    [[ -z "$data" || ! -e "$data/$item" ]] || cp -a "$data/$item" "$stage/USRDIR/"
done
# The SDK strips the exact input prefix; the slash prevents absolute entry names.
pkg --contentid "$content" "$stage/" "$out/$name.pkg"
cp "$out/$name.pkg" "$out/$name.gnpdrm.pkg"
package_finalize "$out/$name.gnpdrm.pkg"
cp "$elf" "$out/$name.elf"
# Include complete patched SDL sources as well as the game and LGPL libraries.
sdl_archive="$ELMA_PS3_DIR/.toolchain/sdl2-b81fbad.tar.gz"
[[ -f "$sdl_archive" ]] || { echo 'Missing pinned SDL source; run tools/build_sdl2.sh.' >&2; exit 1; }
source_stage="$build_dir/package-source/third_party/SDL2-PSL1GHT"
rm -rf "$source_stage"
mkdir -p "$source_stage"
tar -xzf "$sdl_archive" --strip-components=1 -C "$source_stage"
patch -d "$source_stage" -p1 < "$ELMA_PS3_DIR/sdk/sdl2-render-targets.patch"
cp "$ELMA_PS3_DIR/sdk/SDL3_PIXELART_LICENSE.txt" "$source_stage/SDL3_PIXELART_LICENSE.txt"
tar -cf "$out/$name.source.tar" -C "$ELMA_PS3_DIR/../.." \
    --exclude='console/ps3/.toolchain' --exclude='console/ps3/build' \
    --exclude='console/ps3/dist' --exclude='__pycache__' \
    CMakeLists.txt README.md LICENSE.md src desktop third_party console/ps3 tests
tar -rf "$out/$name.source.tar" -C "$build_dir/package-source" third_party/SDL2-PSL1GHT
gzip -f "$out/$name.source.tar"
python3 - "$out" "$name" "$version" "$physics_profile" "$build_dir" <<'PYMANIFEST'
import hashlib, json, pathlib, sys
out, name, version = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
profile, build = sys.argv[4], pathlib.Path(sys.argv[5])
provenance = {}
for artifact in [build/'CMakeCache.txt', build/'CMakeFiles/elma.dir/flags.make', build/'CMakeFiles/elma.dir/link.txt', build/'libelma-math.a', build/'libhqx.a'] + ([build/'elma-x87/libelma-classic-x87.a'] if profile=='classic-x87' else []):
    if artifact.is_file(): provenance[str(artifact.relative_to(build))] = hashlib.sha256(artifact.read_bytes()).hexdigest()
files = sorted(p for p in out.glob(name + '.*') if p.suffix != '.json')
stage = out/name/"ELMAC0001"
manifest = {"version": version, "physics_profile": profile, "build_provenance_sha256": provenance, "build_directory": str(build), "cmake_cache_sha256": hashlib.sha256((build/"CMakeCache.txt").read_bytes()).hexdigest(), "kind": "with-data" if name.endswith("with-data") else "code", "built_elf_sha256": hashlib.sha256((out/(name+".elf")).read_bytes()).hexdigest(), "sdk": "ps3dev nightly-2026-10-12", "stage_files": [{"name": str(p.relative_to(stage)), "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(stage.rglob("*")) if p.is_file()], "files": [
    {"name": p.name, "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]}
(out / (name + '.json')).write_text(json.dumps(manifest, indent=2) + '\n')
PYMANIFEST
echo "ELF, SELF, PKG, SHA256 manifest and RPCS3 game folder: $out/$name*"
