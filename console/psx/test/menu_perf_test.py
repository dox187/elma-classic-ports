#!/usr/bin/env python3
"""Measure real-disc menu startup and cadence in retail 2 MB, headless/silent.

--compare requires a build configured with ELMA_PSX_MENU_COMPARE=ON. It
compares every menu pixel with an uncached full repaint of the same frame
and times cached/uncached partial drawing on identical circle geometry.
"""
import argparse
import os
import sys

import pcsx
from core_boot_test import PSX, REPO, make_disc
from mc_test import make_card


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", default=os.path.join(PSX, "build"))
    ap.add_argument("--res", default=os.environ.get("ELMA_RES", os.path.join(REPO, "elma.res")))
    ap.add_argument("--lgr", default=os.environ.get(
        "ELMA_LGR", os.path.join(REPO, "build", "Lgr", "Default_old.lgr")))
    ap.add_argument("--mode", choices=("ntsc", "pal"), default="ntsc")
    ap.add_argument("--frames", type=int, default=900, help="VBlanks after the main menu settles")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--compare-frames", type=int, default=200)
    ap.add_argument("--timeout", type=float, default=1200)
    ap.add_argument("--redux")
    args = ap.parse_args()
    if args.frames < 300 or args.compare_frames < 100:
        ap.error("use at least 300 VBlanks and 100 comparison frames")
    map_file = os.path.join(args.build, "elma-cd.map")
    symbols = pcsx.read_symbols(map_file)
    if args.compare and "gpu_menu_compare_enable" not in symbols:
        ap.error("--compare needs a build configured with ELMA_PSX_MENU_COMPARE=ON")
    work = os.path.abspath(os.path.join(args.build, "menu-perf-test-" + args.mode +
                                       ("-compare" if args.compare else "")))
    os.makedirs(work, exist_ok=True)
    card = os.path.join(work, "card.mcd")
    with open(card, "wb") as f:
        f.write(make_card("fresh"))
    result = pcsx.run(iso=make_disc(args.build, args.res, args.lgr, None),
                      map_file=map_file, ram8=False, workdir=work, timeout=args.timeout,
                      redux=args.redux, lua=os.path.join(os.path.dirname(__file__), "menu_perf_test.lua"),
                      args={"force": 2 if args.mode == "pal" else 1,
                            "frames": args.frames, "compare": int(args.compare),
                            "compare_frames": args.compare_frames,
                            "log": os.path.join(work, "test.log")},
                      extra_flags=["-memcard1", card])
    for line in result.output.splitlines():
        if line.startswith(("MENU ", "CADENCE ", "PARITY ", "PASS:", "FAIL:", "LUA ERROR")):
            print(line)
    passed = any(line.startswith("PASS:") for line in result.output.splitlines())
    if result.returncode or not passed:
        print("FAIL: emulator exit %d" % result.returncode)
        print("\n".join(result.output.splitlines()[-15:]))
        return result.returncode or 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
