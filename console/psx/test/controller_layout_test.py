#!/usr/bin/env python3
"""Verify PSX physical-button customization, card persistence and gameplay."""
import argparse
from pathlib import Path
import shutil

import pcsx
from core_boot_test import make_pcdrv_dir
from res_layout import resource_layout

PSX = Path(__file__).resolve().parent.parent
REPO = PSX.parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--card", type=Path, required=True, help="read-only source card with a saved player")
    ap.add_argument("--res", type=Path, default=REPO / "elma.res")
    ap.add_argument("--lgr", type=Path, default=REPO / "build/Lgr/Default_old.lgr")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--replay", action="store_true", help="focused Circle replay toggle and Select exit regression")
    args = ap.parse_args()
    build = args.build.resolve()
    for path in (build / "elma.exe", build / "elma.map", args.card, args.res, args.lgr):
        if not path.is_file():
            ap.error("file not found: " + str(path))
    base = build / ("controller-replay-test" if args.replay else "controller-layout-test")
    base.mkdir(parents=True, exist_ok=True)
    card = base / "private-card.mcd"
    if card.resolve() == args.card.resolve():
        ap.error("source card must be separate from the private test card")
    shutil.copyfile(args.card, card)
    pcdrv = base / "pcdrv"
    make_pcdrv_dir(str(pcdrv), str(args.res.resolve()), str(args.lgr.resolve()))
    layout = resource_layout(str(args.res.resolve()))
    for run in ((3,) if args.replay else (1, 2)):
        work = base / ("run%d" % run)
        work.mkdir(exist_ok=True)
        result = pcsx.run(exe=str(build / "elma.exe"), map_file=str(build / "elma.map"),
                          pcdrv=str(pcdrv), lua=str(PSX / "test/controller_layout_test.lua"),
                          timeout=args.timeout, workdir=str(work),
                          args={"run": str(run), "log": str(work / "test.log"),
                                "capture": str(work / "layout.ppm"),
                                "collections": str(int(layout["collections"])),
                                "internal_steps": ",".join(layout["internal_steps"])},
                          extra_flags=["-memcard1", str(card)])
        for line in result.output.splitlines():
            if line.startswith(("CONTROLS ", "PASS:", "FAIL:", "LUA ERROR:")):
                print("run%d: %s" % (run, line), flush=True)
        if result.returncode or not any(line.startswith("PASS:") for line in result.output.splitlines()):
            print("FAIL: emulator exit %d" % result.returncode)
            print("\n".join(line[:160] for line in result.output.splitlines()[-8:]))
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
