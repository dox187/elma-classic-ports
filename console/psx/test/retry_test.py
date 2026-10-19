#!/usr/bin/env python3
"""Measure a real Warm Up death, compact selector and retained-level retry.

Runs silently with a fresh private memory card and retail 2 MB. Latency is
measured in guest vertical blanks, rather than host time or average FPS.
"""
import argparse
import os
import re
import resource
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PSX = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PSX))
sys.path.insert(0, HERE)
import pcsx  # noqa: E402
from core_boot_test import make_pcdrv_dir  # noqa: E402
from mc_test import make_card  # noqa: E402
from res_layout import resource_layout  # noqa: E402


def check_panel(path):
    with open(path, "rb") as f:
        if [f.readline().strip() for _ in range(3)] != [b"P6", b"320 240", b"255"]:
            raise ValueError("invalid compact-selector image")
        pixels = f.read()
    if len(pixels) != 320 * 240 * 3:
        raise ValueError("truncated compact-selector image")
    background = pixels[:3]
    if not (background[0] < 8 and 24 <= background[1] <= 40 and background[2] < 20):
        raise ValueError("selector background is not dark green")
    ink = [x for y in range(8, 16) for x in range(320)
           if pixels[(y * 320 + x) * 3:(y * 320 + x) * 3 + 3] != background]
    if not ink or not 8 <= min(ink) < 16:
        raise ValueError("selector title is not at its left margin")
    if pixels[16 * 320 * 3:24 * 320 * 3] != background * (8 * 320):
        raise ValueError("selector blank row contains stray glyphs")
    title = pixels[8 * 320 * 3:16 * 320 * 3]
    if not any(title[i] > 180 and title[i + 1] > 180 and title[i + 2] < 80
               for i in range(0, len(title), 3)):
        raise ValueError("selector text is not yellow")
    footer = pixels[216 * 320 * 3:224 * 320 * 3]
    if sum(footer[i:i + 3] != background for i in range(0, len(footer), 3)) < 80:
        raise ValueError("fast restart explanation is missing at the bottom")


def check_recording_removed(path):
    with open(path, encoding="utf-8") as f:
        symbols = f.read()
    for name in ("recorder_darab", "_ZN8recorder5store", "_ZN8recorder7addhang",
                 "_ZN8recorder4load", "_ZN8recorder4save", "_Z6replayv",
                 "_ZL4demov", "_Z8saveplayl", "_Z10replayprecv", "lejatszo_r"):
        if name in symbols:
            raise ValueError("obsolete replay/recording code remains linked: " + name)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", default=os.path.join(PSX, "build"))
    p.add_argument("--res", default=os.path.join(REPO, "elma.res"))
    p.add_argument("--lgr", default=os.path.join(REPO, "build/Lgr/Default_old.lgr"))
    p.add_argument("--disc", action="store_true")
    p.add_argument("--card-save", action="store_true", help="also save while the compact selector is visible")
    p.add_argument("--timeout", type=float, default=600)
    args = p.parse_args()
    work = os.path.abspath(os.path.join(args.build, "retry-test" +
                                      ("-disc" if args.disc else "") +
                                      ("-card" if args.card_save else "")))
    os.makedirs(work, exist_ok=True)
    card = os.path.join(work, "card.mcd")
    with open(card, "wb") as f:
        f.write(make_card("fresh"))
    image = "elma-cd" if args.disc else "elma"
    check_recording_removed(os.path.join(args.build, image + ".map"))
    print("RETRY no replay/demo/recording code linked")
    if args.disc:
        disc = os.path.join(work, "disc")
        subprocess.run([sys.executable, os.path.join(PSX, "tools/mkdisc.py"),
                        "--exe", os.path.join(args.build, image + ".exe"),
                        "--res", args.res, "--lgr", args.lgr,
                        "--out-dir", disc, "--name", "elma"],
                       check=True, stdout=subprocess.DEVNULL)
        source = {"iso": os.path.join(disc, "elma.cue")}
    else:
        data = os.path.join(work, "pcdrv")
        make_pcdrv_dir(data, args.res, args.lgr)
        source = {"exe": os.path.join(args.build, image + ".exe"), "pcdrv": data}
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    result = pcsx.run(map_file=os.path.join(args.build, image + ".map"),
                      lua=os.path.join(HERE, "retry_test.lua"), ram8=False,
                      timeout=args.timeout, workdir=work,
                      extra_flags=["-memcard1", card],
                      args={"memory_lua": os.path.join(HERE, "mem_test.lua"),
                            "level": 0, "play": 30000, "sites": 0,
                            "quick_card_save": int(args.card_save),
                            "path": ",".join(resource_layout(args.res)["internal_steps"])},
                      **source)
    for line in result.output.splitlines():
        if line.startswith(("RETRY", "PASS", "FAIL", "LUA")):
            print(line)
    ok = result.returncode == 0 and re.search(r"^PASS: retry transitions", result.output, re.M)
    if ok:
        try:
            check_panel(os.path.join(work, "retry-ready.ppm"))
        except (OSError, ValueError) as e:
            print("FAIL: retry panel pixels:", e)
            ok = False
    if not ok:
        print("FAIL: retry regression (emulator exit %d); see %s" % (
            result.returncode, os.path.join(work, "output.log")))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
