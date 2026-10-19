#!/usr/bin/env python3
"""Tests of the PlayStation sound output (M5).

  sound_test.py host   encoder round trip on synthetic signals and on the WAV
                       files of elma.res (read only), SNR must be reasonable
  sound_test.py ps1    soundtest.exe in headless, silent PCSX-Redux: streams a
                       known signal through the SPU ring, reads SPU RAM back,
                       checks playback progress, underruns and the CRC of the
                       encoder output against the host build
  sound_test.py        both (the ps1 part needs `make sound-test` built first)

Environment: ELMA_RES (default: elma.res in the repository root), BUILD
(default: console/psx/build), PCSX_REDUX. Scratch files go to BUILD/sound-test.
"""

import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ROOT))
BUILD = os.environ.get("BUILD", os.path.join(ROOT, "build"))
WORK = os.path.join(BUILD, "sound-test")
ELMA_RES = os.environ.get("ELMA_RES", os.path.join(REPO, "elma.res"))

sys.path.insert(0, HERE)


def res_files(path):
    """Yields (name, data) for every file of elma.res (the format of
    src/QOPEN.CPP: count, descriptors of 24 bytes xor-scrambled, magic)."""
    with open(path, "rb") as f:
        blob = f.read()
    count = struct.unpack_from("<i", blob, 0)[0]
    magic = 1347839
    for slots in (150, 3000):
        if struct.unpack_from("<i", blob, 4 + slots * 24)[0] == magic:
            break
    else:
        raise RuntimeError("elma.res: magic number not found")
    desc = bytearray(blob[4:4 + slots * 24])

    def s16(v):
        return ((v + 0x8000) & 0xFFFF) - 0x8000

    a, b, c = 23, 9982, 3391
    for i in range(len(desc)):
        desc[i] ^= a & 0xFF
        a = int(a - c * int(a / c))  # C remainder, a is never negative here
        b = s16(b + a * c)
        a = s16(31 * b + c)
    for i in range(min(count, slots)):
        name, length, start = struct.unpack_from("<16sii", desc, i * 24)
        name = name.split(b"\0")[0].decode("latin1")
        yield name, blob[start:start + length]


def extract_wavs():
    out = os.path.join(WORK, "wav")
    os.makedirs(out, exist_ok=True)
    files = []
    if not os.path.exists(ELMA_RES):
        print("note: %s not found, real samples skipped" % ELMA_RES)
        return files
    for name, data in res_files(ELMA_RES):
        if name.lower().endswith(".wav") and len(data) > 44:
            # Only what the game loads as 16 bit mono at 11025 Hz.
            ch, rate = struct.unpack_from("<HI", data, 22)
            if data[:4] == b"RIFF" and ch == 1:
                p = os.path.join(out, name.lower())
                with open(p, "wb") as f:
                    f.write(data)
                files.append(p)
    return files


def build_host():
    os.makedirs(WORK, exist_ok=True)
    exe = os.path.join(WORK, "sound_host_test")
    subprocess.check_call([
        os.environ.get("CC", "cc"), "-O2", "-Wall", "-Wextra",
        "-I" + os.path.join(ROOT, "src", "sound"),
        "-I" + os.path.join(ROOT, "soundtest"),
        os.path.join(HERE, "sound_host_test.c"),
        os.path.join(ROOT, "src", "sound", "spu_adpcm.c"),
        "-lm", "-o", exe])
    return exe


def host_test():
    exe = build_host()
    wavs = extract_wavs()
    r = subprocess.run([exe] + wavs, capture_output=True, text=True)
    print(r.stdout, end="")
    print(r.stderr, end="")
    return r.returncode == 0


def host_crc():
    exe = build_host()
    out = subprocess.run([exe, "--crc-only"], capture_output=True, text=True,
                         check=True).stdout
    return re.search(r"crc=([0-9a-f]{8})", out).group(1)


def ps1_test():
    from pcsx import run
    exe = os.path.join(BUILD, "soundtest.exe")
    if not os.path.exists(exe):
        print("soundtest.exe missing, run `make -C console/psx sound-test`")
        return False
    crc = host_crc()
    print("host crc of the test signal:", crc)
    redux = os.environ.get("PCSX_REDUX")
    r = run(exe=exe, map_file=os.path.join(BUILD, "soundtest.map"),
            lua=os.path.join(HERE, "sound_test.lua"), timeout=240,
            workdir=os.path.join(WORK, "pcsx"), redux=redux,
            args={"crc": crc})
    for line in r.output.splitlines():
        if re.search(r"sound|PASS|FAIL|LUA ERROR|timeout", line):
            print(line)
    return r.returncode == 0


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    ok = True
    if what in ("host", "all"):
        ok = host_test() and ok
    if what in ("ps1", "all"):
        ok = ps1_test() and ok
    print("sound tests", "passed" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
