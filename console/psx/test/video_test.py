#!/usr/bin/env python3
"""Check PAL/NTSC video and the game clock in menus and Warm Up, in 2 MB.

Runs headless and silent with private memory cards and read-only game data.
Use --disc to exercise the same checks from a two-track disc image.
"""
import argparse
import os
import sys

import pcsx
from core_boot_test import PSX, REPO, make_disc, make_pcdrv_dir
from mc_test import make_card


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", default=os.path.join(PSX, "build"))
    ap.add_argument("--res", default=os.environ.get("ELMA_RES", os.path.join(REPO, "elma.res")))
    ap.add_argument("--lgr", default=os.environ.get(
        "ELMA_LGR", os.path.join(REPO, "build", "Lgr", "Default_old.lgr")))
    ap.add_argument("--scene", choices=("menu", "level", "all"), default="all")
    ap.add_argument("--mode", choices=("ntsc", "pal", "all"), default="all")
    ap.add_argument("--disc", action="store_true")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--redux")
    args = ap.parse_args()
    base = os.path.abspath(os.path.join(args.build, "video-test-disc" if args.disc else "video-test"))
    os.makedirs(base, exist_ok=True)
    if args.disc:
        source = {"iso": make_disc(args.build, args.res, args.lgr, None)}
        stem = "elma-cd"
    else:
        pcdrv = os.path.join(base, "pcdrv")
        make_pcdrv_dir(pcdrv, args.res, args.lgr)
        source = {"exe": os.path.join(args.build, "elma.exe"), "pcdrv": pcdrv}
        stem = "elma"
    scenes = ("menu", "level") if args.scene == "all" else (args.scene,)
    modes = ("ntsc", "pal") if args.mode == "all" else (args.mode,)
    for scene in scenes:
        for mode in modes:
            work = os.path.join(base, scene + "-" + mode)
            os.makedirs(work, exist_ok=True)
            card = os.path.join(work, "card.mcd")
            with open(card, "wb") as f:
                f.write(make_card("fresh"))
            script = "video_level_test.lua" if scene == "level" else "video_test.lua"
            result = pcsx.run(**source, map_file=os.path.join(args.build, stem + ".map"),
                              lua=os.path.join(os.path.dirname(__file__), script),
                              ram8=False, workdir=work, timeout=args.timeout, redux=args.redux,
                              args={"force": 2 if mode == "pal" else 1,
                                    "frames": 900 if scene == "menu" else 480,
                                    "log": os.path.join(work, "test.log")},
                              extra_flags=["-memcard1", card])
            for line in result.output.splitlines():
                if line.startswith(("MEASURE", "PASS", "FAIL", "LUA ERROR")):
                    print("%s/%s: %s" % (scene, mode, line), flush=True)
            if result.returncode or "\nPASS" not in result.output:
                print("FAIL: %s/%s emulator exit %d" % (scene, mode, result.returncode))
                print("\n".join(result.output.splitlines()[-12:]))
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
