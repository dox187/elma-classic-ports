#!/usr/bin/env bash
# Isolated diagnostic; never edits production physics or bundles game data.
set -euo pipefail
PIN=d9c3a9a87cb319da9053d385aac2b7814344b0bd
URL=https://github.com/bochs-emu/Bochs.git
ROOT=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
OUT= CACHE= REUSE= REUSE_HASH= LEVEL= CAPTURE= ORDER=0
JOBS=2
usage() {
    cat <<'USAGE'
Usage: probe_x87_candidate.sh --out DIRECTORY [options]
  --source-cache GIT_CLONE       Existing clean checkout at the exact pin.
                                If absent, fetch the official pinned source.
  --jobs N                      SoftFloat build parallelism (default 2).
  --reuse-softfloat ARCHIVE --reuse-softfloat-sha256 HASH
                                Explicit hash-checked cached archive; avoids
                                rebuilding SoftFloat. Origin is recorded.
  --one-step LEVEL_TXT CAPTURE   Optional private original motor snapshots.
  --original-product-order      Optional private ellipse-product reorder.

Requires bash, git, tar, make, C/C++ compilers, sha256sum and Python3. The scalar
probe requires x86. A scalar residual is a measurement, not an overall pass.
One-step differences return status1, and remain in the report/manifest.
Output must be separate from source. Nothing under --out belongs in releases.
USAGE
}
while (($#)); do
    case "$1" in
        --out) OUT=$2; shift 2;;
        --source-cache) CACHE=$2; shift 2;;
        --jobs) JOBS=$2; shift 2;;
        --reuse-softfloat) REUSE=$2; shift 2;;
        --reuse-softfloat-sha256) REUSE_HASH=$2; shift 2;;
        --one-step) LEVEL=$2; CAPTURE=$3; shift 3;;
        --original-product-order) ORDER=1; shift;;
        --help|-h) usage; exit 0;;
        *) usage >&2; exit 2;;
    esac
done
[[ -n "$OUT" && "$JOBS" =~ ^[1-9][0-9]?$ ]] || { usage >&2; exit 2; }
[[ -z "$REUSE$REUSE_HASH" || (-n "$REUSE" && "$REUSE_HASH" =~ ^[0-9a-f]{64}$) ]] || {
    echo 'Cached archive requires its exact SHA-256.' >&2; exit 2;
}
[[ "$ORDER" == 0 || -n "$LEVEL" ]] || { echo 'Product order requires --one-step.' >&2; exit 2; }
OUT=$(realpath -m -- "$OUT")
case "$OUT/" in
    "$ROOT/build"*|"$ROOT/console/ps3/build/"*) ;;
    "$ROOT/"*) echo 'Inside the source tree, use an ignored build directory.' >&2; exit 2;;
esac
if [[ -d "$OUT" && -n "$(ls -A -- "$OUT")" && ! -f "$OUT/.x87-probe-output" ]]; then
    echo 'Refusing an existing nonempty output directory without our marker.' >&2; exit 2
fi
mkdir -p -- "$OUT"
if [[ -f "$OUT/.x87-probe-output" ]]; then
    [[ $(cat "$OUT/.x87-probe-output") == "$PIN" ]] || { echo 'Output pin mismatch.' >&2; exit 2; }
else
    printf '%s\n' "$PIN" > "$OUT/.x87-probe-output"
fi
CACHE=${CACHE:-"$OUT/source-cache"}
CACHE=$(realpath -m -- "$CACHE")
[[ "$OUT" != "$CACHE" && "$CACHE" != "$OUT/upstream" ]] || { echo 'Source/output overlap.' >&2; exit 2; }
if [[ ! -e "$CACHE" ]]; then
    mkdir -p -- "$CACHE"
    git -C "$CACHE" init -q
    if ! git -C "$CACHE" fetch --depth 1 "$URL" "$PIN" > "$OUT/fetch.log" 2>&1; then
        echo "Fetch failed; supply --source-cache with a clean pinned clone. See $OUT/fetch.log" >&2
        exit 1
    fi
    git -C "$CACHE" checkout -q --detach FETCH_HEAD
fi
[[ $(git -C "$CACHE" rev-parse HEAD) == "$PIN" ]] || { echo 'Cached source pin mismatch.' >&2; exit 2; }
git -C "$CACHE" diff --quiet "$PIN" -- || { echo 'Cached tracked sources differ from pin.' >&2; exit 2; }
git -C "$CACHE" rev-parse HEAD^{tree} > "$OUT/pinned-tree.txt"
if [[ ! -d "$OUT/upstream" ]]; then
    mkdir "$OUT/upstream"
    git -C "$CACHE" archive "$PIN" LICENSE bochs | tar -x -C "$OUT/upstream"
fi
# Validate even a previously extracted output tree before configuring/building.
python3 - "$CACHE" "$OUT/upstream" "$PIN" <<'PY'
import os,pathlib,subprocess,sys,tarfile
cache,tree,pin=sys.argv[1:];tree=pathlib.Path(tree)
process=subprocess.Popen(['git','-C',cache,'archive',pin,'LICENSE','bochs'],stdout=subprocess.PIPE)
with tarfile.open(fileobj=process.stdout,mode='r|') as archive:
    for entry in archive:
        path=tree/entry.name
        if entry.isfile():
            if path.read_bytes()!=archive.extractfile(entry).read():raise SystemExit('Extracted pinned file mismatch: '+entry.name)
        elif entry.issym():
            if not path.is_symlink() or os.readlink(path)!=entry.linkname:raise SystemExit('Extracted pinned symlink mismatch: '+entry.name)
if process.wait()!=0:raise SystemExit('Cannot verify pinned source archive')
PY
UP="$OUT/upstream/bochs"
CXX=${CXX:-c++}
CC=${CC:-cc}
if [[ ! -f "$UP/config.h" ]]; then
    (cd "$UP"; CXX="$CXX" CC="$CC" ./configure --with-nogui --enable-x86-64 --disable-docbook) > "$OUT/configure.log" 2>&1
fi
if [[ -n "$REUSE" ]]; then
    REUSE=$(realpath -- "$REUSE")
    [[ $(sha256sum -- "$REUSE" | cut -d' ' -f1) == "$REUSE_HASH" ]] || { echo 'Cached archive hash mismatch.' >&2; exit 2; }
    if [[ "$REUSE" != "$OUT/libsoftfloat.a" ]]; then cp -- "$REUSE" "$OUT/libsoftfloat.a"; fi
    printf 'Explicit cached archive %s SHA256 %s\n' "$REUSE" "$REUSE_HASH" > "$OUT/softfloat-build.log"
else
    make -C "$UP/cpu/softfloat3e" -j"$JOBS" CXX="$CXX" > "$OUT/softfloat-build.log" 2>&1
    cp -- "$UP/cpu/softfloat3e/libsoftfloat.a" "$OUT/libsoftfloat.a"
fi
# The archive and extracted tree preserve all upstream license notices. Copy
# the applicable top-level and SoftFloat notices beside the diagnostic output.
mkdir -p "$OUT/licenses"
cp -- "$UP/COPYING" "$OUT/licenses/Bochs-COPYING"
cp -- "$UP/LICENSE" "$OUT/licenses/Bochs-LICENSE"
cp -- "$UP/cpu/softfloat3e/COPYING.txt" "$OUT/licenses/SoftFloat-COPYING.txt"
FLAGS=(-std=gnu++17 -O2 -fno-fast-math -ffp-contract=off)
INC=(-I"$OUT/upstream" -I"$UP" -I"$UP/cpu" -I"$UP/cpu/fpu")
(
    set -x
    "$CXX" "${FLAGS[@]}" "${INC[@]}" -c "$UP/cpu/fpu/fsincos.cc" -o "$OUT/fsincos.o"
    "$CXX" "${FLAGS[@]}" "${INC[@]}" -c "$UP/cpu/fpu/f128_67.cc" -o "$OUT/f128_67.o"
    "$CXX" "${FLAGS[@]}" "${INC[@]}" "$ROOT/console/ps3/test/x87_endpoint_probe.cpp" "$OUT/fsincos.o" "$OUT/f128_67.o" "$OUT/libsoftfloat.a" -lm -o "$OUT/endpoint-probe"
) > "$OUT/build.log" 2>&1
"$OUT/endpoint-probe" > "$OUT/endpoint-probe.log"
cat "$OUT/endpoint-probe.log"
STEP_STATUS=0
if [[ -n "$LEVEL" ]]; then
    LEVEL=$(realpath -- "$LEVEL"); CAPTURE=$(realpath -- "$CAPTURE")
    python3 - "$ROOT" "$OUT" "$ORDER" <<'PY'
import pathlib,sys
root,out=map(pathlib.Path,sys.argv[1:3]);order=sys.argv[3]=='1'
headers=out/'headers';headers.mkdir(exist_ok=True)
for p in (root/'src').iterdir():
    if p.is_file():
        link=headers/p.name.lower()
        if not link.exists():link.symlink_to(p)
source=(root/'src/BEALLIT.CPP').read_bytes()
if order:
    old=b'r.x*r.x*rxszorzo';assert source.count(old)==1
    source=source.replace(old,b'rxszorzo*r.x*r.x')
(out/'BEALLIT-diagnostic.CPP').write_bytes(source)
PY
    (
        set -x
        "$CXX" "${FLAGS[@]}" "${INC[@]}" -DNO_PROBE_MAIN -c "$ROOT/console/ps3/test/x87_endpoint_probe.cpp" -o "$OUT/endpoint-wrap.o"
        CORE=(LEPTET UTKOZES UTKOZES2 SZAKASZ VEKT2)
        SOURCES=(); for name in "${CORE[@]}"; do SOURCES+=("$ROOT/src/$name.CPP"); done
        "$CXX" "${FLAGS[@]}" -fpermissive -fsigned-char -fwrapv -fno-strict-aliasing -I"$ROOT/src" -I"$ROOT/desktop" -I"$OUT/headers" "$ROOT/console/ps3/test/windows_step_compare.cpp" "$OUT/BEALLIT-diagnostic.CPP" "${SOURCES[@]}" "$OUT/endpoint-wrap.o" "$OUT/fsincos.o" "$OUT/f128_67.o" "$OUT/libsoftfloat.a" -Wl,--wrap=sin,--wrap=cos,--wrap=sincos -lm -o "$OUT/one-step-candidate"
    ) > "$OUT/step-build.log" 2>&1
    "$OUT/one-step-candidate" "$LEVEL" "$CAPTURE" "$OUT/one-step-report.txt" || STEP_STATUS=$?
    cat "$OUT/one-step-report.txt"
fi
"$CXX" --version > "$OUT/compiler.txt"
(getconf GNU_LIBC_VERSION || true) > "$OUT/runtime.txt"
python3 - "$OUT" "$ROOT" "$PIN" "$URL" "$REUSE" "$LEVEL" "$CAPTURE" "$ORDER" "$STEP_STATUS" <<'PY'
import hashlib,json,pathlib,sys
out,root=map(pathlib.Path,sys.argv[1:3]);pin,url,reuse,level,capture,order,status=sys.argv[3:]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
files={str(p.relative_to(out)):sha(p) for p in out.iterdir() if p.is_file() and p.name!='manifest.json'}
sources={str(p.relative_to(root)):sha(p) for p in [root/'console/ps3/test/x87_endpoint_probe.cpp',root/'console/ps3/tools/probe_x87_candidate.sh',root/'console/ps3/test/windows_step_compare.cpp',root/'src/BEALLIT.CPP']}
record={'status':'Diagnostic measurements; no production changes or universal x87 parity claim','pin':pin,'upstream':url,'cached_softfloat':reuse or None,'one_step':{'level':level or None,'capture':capture or None,'original_product_order':order=='1','exit':int(status)},'files_sha256':files,'project_sources_sha256':sources}
if level:record['one_step']['geometry_sha256']=sha(pathlib.Path(level));record['one_step']['inputs_sha256']=sha(pathlib.Path(capture)/'inputs.txt')
(out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
PY
exit "$STEP_STATUS"
