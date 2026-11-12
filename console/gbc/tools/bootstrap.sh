#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
case "$(uname -sm)" in
  'Darwin arm64') archive=gbdk-macos-arm64.tar.gz; sha=289ee60e46c5a2785a21e35533f84a5131ed4a063b21b0dbdedc9a10af15bf78 ;;
  'Darwin x86_64') archive=gbdk-macos.tar.gz; sha=1aa549d12032d8f6509d11923bb28b1a453098f42597feb378e9a42541f8fd89 ;;
  'Linux x86_64') archive=gbdk-linux64.tar.gz; sha=d7857a5f6d135ee4c249043ca26aad9f2ec8ab5d4106d97720d404114f42605c ;;
  'Linux aarch64') archive=gbdk-linux-arm64.tar.gz; sha=31eb2235f0fdb60163d0b1e9574a022098d6069cd56606a1daca4478a46e0439 ;;
  *) echo 'Supported hosts: macOS arm64/x86_64, Linux aarch64/x86_64' >&2; exit 1 ;;
esac
mkdir -p "$root/.toolchain"
if [[ ! -f "$root/.toolchain/$archive" ]]; then
  curl -fL --retry 3 "https://github.com/gbdk-2020/gbdk-2020/releases/download/4.5.0/$archive" -o "$root/.toolchain/$archive.part"
  mv "$root/.toolchain/$archive.part" "$root/.toolchain/$archive"
fi
python3 - "$root/.toolchain/$archive" "$sha" <<'PY'
import hashlib, pathlib, sys
p=pathlib.Path(sys.argv[1])
if hashlib.sha256(p.read_bytes()).hexdigest()!=sys.argv[2]:
    raise SystemExit('GBDK archive checksum mismatch: '+str(p))
print('PASS: pinned GBDK 4.5.0 archive checksum')
PY
tar -xzf "$root/.toolchain/$archive" -C "$root/.toolchain"
echo "GBDK installed in $root/.toolchain/gbdk"
