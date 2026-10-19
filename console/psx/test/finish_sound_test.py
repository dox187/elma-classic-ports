#!/usr/bin/env python3
"""Check complete death/success cues and prompt sound-off transitions in 2 MB.

Two small synthetic levels replace only private copies of the first two
internal levels. SDL disk audio captures real SPU output without host audio.
"""
import argparse
import array
import json
import io
import math
import os
from pathlib import Path
import re
import resource
import struct
import wave

import mc_test
import pcsx
from core_boot_test import make_pcdrv_dir
from phys_levels import Resource, parse_level
from res_layout import resource_layout

PSX = Path(__file__).resolve().parent.parent
REPO = PSX.parent.parent
RATE, FRAME_BYTES = 44100, 8


def fixture(success):
    # File coordinates point down. The ceiling intersects the rider's head;
    # the success fixture puts a flower just ahead, with no apples to collect.
    polygons = [[(-20., 0.), (20., 0.), (20., 10.), (-20., 10.)]]
    if not success:
        polygons.append([(-5., -2.), (5., -2.), (5., -1.5), (-5., -1.5)])
    objects = [(0., -0.6, 4), (-2. if success else 10., -0.6, 1)]
    checksum = (sum(x + y for poly in polygons for x, y in poly) +
                sum(x + y + kind for x, y, kind in objects)) * 3247.764325643
    stamp = 0x46530002 if success else 0x46530001
    data = bytearray(b"@@^!@\0\0" + struct.pack("<Idddd", stamp, checksum,
                     15000. - checksum, 15000. - checksum, 15000. - checksum))
    for value, size in ((b"Sound success" if success else b"Sound head hit", 51),
                        (b"default", 16), (b"ground", 10), (b"sky", 10)):
        data += value.ljust(size, b"\0")
    data += struct.pack("<dd", len(polygons), len(objects))
    for poly in polygons:
        data += struct.pack("<ii", 0, len(poly))
        for point in poly:
            data += struct.pack("<dd", *point)
    for x, y, kind in objects:
        data += struct.pack("<ddiii", x, y, kind, 0, 0)
    data += struct.pack("<d", 0.)
    parse_level(data, internal=True)
    return data


def check_audio(path, output, enabled):
    samples = array.array("f", path.read_bytes())
    for kind, size, first, ready, last in re.findall(
            r"FINISH_AUDIO (death|success) samples=(\d+) start=(\d+) ready=(\d+) end=(\d+)", output):
        size, first, ready, last = map(int, (size, first, ready, last))
        segment = samples[first // 4:last // 4]
        if not segment or any(not math.isfinite(x) for x in segment):
            raise ValueError("invalid captured " + kind)
        nonzero = [i for i, value in enumerate(segment) if abs(value) > 1e-5]
        if enabled:
            span = (nonzero[-1] - nonzero[0] + 1) / (2 * RATE) if nonzero else 0
            duration = size / 11025.
            if span < duration * .8:
                raise ValueError("truncated %s output: %.3fs of %.3fs" % (kind, span, duration))
            print("FINISH_PCM %s audible span %.3fs; sample %.3fs" % (kind, span, duration))
        elif nonzero:
            raise ValueError(kind + " is audible with sound disabled")
        tail = samples[max(first, last - int(.25 * RATE) * FRAME_BYTES) // 4:last // 4]
        if any(abs(value) > 1e-5 for value in tail):
            raise ValueError(kind + " menu is not silent")
    if len(re.findall(r"^FINISH_AUDIO ", output, re.M)) != 2:
        raise ValueError("both actual ending captures are required")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", type=Path, default=PSX / "build")
    ap.add_argument("--res", type=Path, default=REPO / "elma.res")
    ap.add_argument("--lgr", type=Path, default=REPO / "build/Lgr/Default_old.lgr")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--sound", choices=("on", "off", "both"), default="both")
    args = ap.parse_args()
    build = args.build.resolve()
    base = build / "finish-sound-test"
    base.mkdir(parents=True, exist_ok=True)
    archive = Resource(args.res)
    private = bytearray(archive.data)
    for name, success in (("a01.leb", False), ("a02.leb", True)):
        start, size = archive.files[name]
        data = fixture(success)
        if len(data) > size:
            ap.error(name + " has no room for the private fixture")
        private[start:start + size] = data + bytes(size - len(data))
    res = base / "fixture.res"
    res.write_bytes(private)
    layout = resource_layout(args.res)
    lengths = {}
    for label, name in (("death", "torik.wav"), ("success", "siker.wav")):
        with wave.open(io.BytesIO(archive.read(name))) as sample:
            lengths[label] = sample.getnframes()
    os.environ.update(SDL_AUDIO_DRIVER="disk", SDL_AUDIODRIVER="disk",
                      PULSE_SERVER="unix:/nonexistent/pulse", PIPEWIRE_REMOTE="/nonexistent/pipewire",
                      ALSA_CONFIG_PATH="/dev/null")
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 << 20, 128 << 20))
    for mode in (("on", "off") if args.sound == "both" else (args.sound,)):
        work = base / mode
        work.mkdir(exist_ok=True)
        raw = work / "sdlaudio.raw"
        raw.unlink(missing_ok=True)
        settings = work / "home/.config/pcsx-redux"
        settings.mkdir(parents=True, exist_ok=True)
        (settings / "pcsx.json").write_text(json.dumps({"spu": {"Backend": "disk"}}))
        card = work / "card.mcd"
        card.write_bytes(mc_test.make_card("fresh"))
        make_pcdrv_dir(str(work / "pcdrv"), str(res), str(args.lgr.resolve()))
        result = pcsx.run(exe=str(build / "elma.exe"), map_file=str(build / "elma.map"),
                          pcdrv=str(work / "pcdrv"), ram8=False, sound=True,
                          timeout=args.timeout, workdir=str(work),
                          lua=str(PSX / "test/finish_sound_test.lua"),
                          extra_flags=["-memcard1", str(card)],
                          args={"sound": int(mode == "on"), "capture": str(raw),
                                "death_samples": lengths["death"], "success_samples": lengths["success"],
                                "log": str(work / "test.log"), "shots": str(work / "shot-"),
                                "collections": int(layout["collections"]),
                                "path": ",".join(layout["internal_steps"])})
        for line in result.output.splitlines():
            if line.startswith(("FINISH", "PASS:", "FAIL:", "LUA ERROR:")):
                print(mode + ": " + line, flush=True)
        if result.returncode or not re.search(r"^PASS:", result.output, re.M):
            print("FAIL: finish sound mode %s exited %d; see %s" % (mode, result.returncode, work / "output.log"))
            return 1
        if "Audio: driver disk," not in result.output:
            print("FAIL: silent disk audio backend was not used")
            return 1
        try:
            check_audio(raw, result.output, mode == "on")
        except (OSError, ValueError) as error:
            print("FAIL:", error)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
