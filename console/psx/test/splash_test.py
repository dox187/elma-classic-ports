#!/usr/bin/env python3
"""Verify early Loading and the complete splash on a 2 MB NTSC/PAL disc.

The logo and copyright are checked against the read-only resource. Only the
PC version band is replaced; the PSX version and credits stay in the safe area.
"""
import argparse
import os
from pathlib import Path
import resource
import struct
import subprocess
import sys

import mc_test
import pcsx
from phys_levels import Resource
from res_layout import resource_layout

PSX = Path(__file__).resolve().parent.parent
REPO = PSX.parent.parent


def pcx(data):
    if data[0:4] != b"\x0a\x05\x01\x08" or data[65] != 1 or data[-769] != 12:
        raise ValueError("unsupported splash PCX")
    x0, y0, x1, y1 = struct.unpack_from("<4H", data, 4)
    width, height = x1 - x0 + 1, y1 - y0 + 1
    stride = struct.unpack_from("<H", data, 66)[0]
    pixels, at = bytearray(), 128
    while len(pixels) < stride * height:
        color, at = data[at], at + 1
        count = 1
        if color & 0xc0 == 0xc0:
            count, color, at = color & 63, data[at], at + 1
        if count == 0:
            raise ValueError("invalid splash run")
        pixels.extend(bytes([color]) * count)
    if len(pixels) != stride * height:
        raise ValueError("invalid splash dimensions")
    palette = [tuple(data[-768 + i * 3:-768 + i * 3 + 3]) for i in range(255)]
    palette.append(tuple(data[-3:]))
    palette[0] = (0, 0, 0)
    return width, height, stride, pixels, palette


def ppm(path):
    with path.open("rb") as f:
        if f.readline().strip() != b"P6" or f.readline().strip() != b"640 480" or f.readline().strip() != b"255":
            raise ValueError("splash display is not 640x480")
        data = f.read()
    if len(data) != 640 * 480 * 3:
        raise ValueError("truncated screen capture")
    return data


def font_ink(data):
    if data[:4] != b"RA1\0":
        raise ValueError("invalid splash credit font")
    glyphs, at = {}, 6
    for _ in range(struct.unpack_from("<H", data, 4)[0]):
        if data[at:at + 7] != b"EGYMIX\0":
            raise ValueError("invalid credit glyph")
        char, y0 = data[at + 7], struct.unpack_from("<h", data, at + 8)[0]
        at += 10
        if data[at] != 0x2d:
            raise ValueError("invalid credit sprite")
        width, height = struct.unpack_from("<HH", data, at + 1)
        at += 5 + width * height
        if data[at:at + 7] != b"SPRITE\0":
            raise ValueError("missing credit mask")
        size = struct.unpack_from("<H", data, at + 7)[0]
        at += 9
        mask, at = data[at:at + size], at + size
        ink, cursor = [], 0
        for y in range(height):
            x = 0
            while x < width:
                command, count = mask[cursor:cursor + 2]
                cursor += 2
                if not count or x + count > width or command not in (ord("K"), ord("N")):
                    raise ValueError("invalid credit mask run")
                if command == ord("K"):
                    ink.extend((xx, y + y0) for xx in range(x, x + count))
                x += count
        glyphs[chr(char)] = width, ink
    return glyphs


def check_art(path, original, glyphs, version):
    width, height, stride, source, palette = original
    if (width, height) != (640, 480):
        raise ValueError("expected the original 640x480 splash")
    screen = ppm(path)
    for y in range(384):
        if 333 <= y < 359:
            continue  # Original PC version text only; checked below.
        sy = ((2 * y + 1) * 5) // 8
        for x in range(512):
            sx = ((2 * x + 1) * 5) // 8
            want = palette[source[sy * stride + sx]]
            at = (y * 640 + x + 64) * 3
            if any(abs(screen[at + c] - want[c]) > 8 for c in range(3)):
                raise ValueError("original art differs at %d,%d" % (x, y))
    ink = [(x, y) for y in range(480) for x in range(640)
           if max(screen[(y * 640 + x) * 3:(y * 640 + x) * 3 + 3]) > 8]
    if not ink or any(x < 32 or x >= 608 or y < 24 or y >= 456 for x, y in ink):
        raise ValueError("splash content leaves the television safe area")
    credit = palette[max(source[450 * stride:480 * stride], key=lambda index: palette[index][0] >> 2)]
    ink = set()
    for text, baseline in (("PSX port v" + version, 350),
                           ("Unofficial PlayStation port", 416), ("Port by dox187", 440)):
        width = sum(5 if c == " " else glyphs[c][0] + 1 for c in text)
        x = 256 - width // 2
        for c in text:
            if c == " ":
                x += 5
            else:
                ink.update((x + xx, baseline + yy) for xx, yy in glyphs[c][1])
                x += glyphs[c][0] + 1
    for y in list(range(333, 359)) + list(range(384, 480)):
        for x in range(512):
            at = (y * 640 + x + 64) * 3
            want = credit if (x, y) in ink else (0, 0, 0)
            if any(abs(screen[at + c] - want[c]) > 8 for c in range(3)):
                raise ValueError("versioned port credit glyphs differ at %d,%d" % (x, y))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", type=Path, default=PSX / "build")
    p.add_argument("--res", type=Path, default=Path(os.environ.get("ELMA_RES", REPO / "elma.res")))
    p.add_argument("--lgr", type=Path, default=Path(os.environ.get("ELMA_LGR", REPO / "build/Lgr/Default_old.lgr")))
    p.add_argument("--video", choices=("both", "ntsc", "pal"), default="both")
    p.add_argument("--timeout", type=float, default=600)
    args = p.parse_args()
    build = args.build.resolve()
    base = build / ("splash-test-%d" % resource_layout(args.res)["descriptor_slots"])
    disc = base / "disc"
    disc.mkdir(parents=True, exist_ok=True)
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 << 20, 64 << 20))
    subprocess.run([sys.executable, str(PSX / "tools/mkdisc.py"), "--exe", str(build / "elma-cd.exe"),
                    "--res", str(args.res.resolve()), "--lgr", str(args.lgr.resolve()),
                    "--out-dir", str(disc), "--name", "elma"],
                   check=True, stdout=subprocess.DEVNULL)
    source = Resource(args.res)
    original = pcx(source.read("intro.pcx"))
    glyphs = font_ink(source.read("kisbetu1.abc"))
    version = (PSX / "VERSION").read_text().strip()
    for video in (("ntsc", "pal") if args.video == "both" else (args.video,)):
        work = base / video
        work.mkdir(exist_ok=True)
        card = work / "card.mcd"
        card.write_bytes(mc_test.make_card("fresh"))
        result = pcsx.run(iso=str(disc / "elma.cue"), map_file=str(build / "elma-cd.map"),
                          lua=str(PSX / "test/splash_test.lua"), ram8=False,
                          workdir=str(work), timeout=args.timeout,
                          args={"force": 1 if video == "ntsc" else 2},
                          extra_flags=["-memcard1", str(card), "-interpreter", "-debugger"])
        for line in result.output.splitlines():
            if line.startswith(("BOOT", "PASS:", "FAIL:", "LUA ERROR:")):
                print(video + ": " + line, flush=True)
        if result.returncode or "PASS: splash" not in result.output:
            print("FAIL: splash emulator exit %d; see %s" % (result.returncode, work / "output.log"))
            return 1
        try:
            loading = ppm(work / "loading.ppm")
            if not any(loading):
                raise ValueError("early Loading screen is black")
            check_art(work / "splash.ppm", original, glyphs, version)
        except (OSError, ValueError) as e:
            print("FAIL:", e)
            return 1
        print(video + ": PASS: full original art, copyright, credits and safe margins", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
