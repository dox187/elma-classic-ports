#!/usr/bin/env python3
"""Verify console Back behavior with fresh and saved players in 2 MB RAM.

Uses a private memory card and read-only PCdrv links to the game data.
The second boot reuses the player saved by the first run. Both runs use
the bounded, headless and silent test/pcsx.py harness.

    python3 test/console_ui_test.py --build build
"""
import argparse
import os
from pathlib import Path

import mc_test
import pcsx
from core_boot_test import make_pcdrv_dir

PSX = Path(__file__).resolve().parent.parent
REPO = PSX.parent.parent


def check_main_menu_pixels(path):
    """Stock menu letters are yellow; verify both the heading and first row."""
    parts = path.read_bytes().split(b"\n", 3)
    if len(parts) != 4 or parts[0] != b"P6" or parts[2] != b"255":
        raise ValueError("invalid menu screenshot")
    width, height = map(int, parts[1].split())
    rgb = parts[3]
    if (width, height) != (640, 480) or len(rgb) != width * height * 3:
        raise ValueError("unexpected menu screenshot dimensions")
    counts = {}
    for name, box in (("heading", (230, 20, 420, 65)), ("Play", (190, 92, 340, 137))):
        count = 0
        for y in range(box[1], box[3]):
            for x in range(box[0], box[2]):
                r, g, b = rgb[(y * width + x) * 3:(y * width + x) * 3 + 3]
                count += r >= 128 and g >= 128 and b < 96
        counts[name] = count
    return all(count >= 100 for count in counts.values()), counts


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", type=Path, default=PSX / "build")
    ap.add_argument("--res", type=Path, default=Path(os.environ.get("ELMA_RES", REPO / "elma.res")))
    ap.add_argument("--lgr", type=Path, default=Path(os.environ.get("ELMA_LGR", REPO / "build/Lgr/Default_old.lgr")))
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--redux")
    ap.add_argument("--shots", action="store_true")
    args = ap.parse_args()
    build = args.build.resolve()
    exe = build / "elma.exe"
    for path in (exe, args.res, args.lgr):
        if not path.is_file():
            ap.error("file not found: %s" % path)
    base = build / "console-ui-test"
    base.mkdir(parents=True, exist_ok=True)
    pcdrv = base / "pcdrv"
    make_pcdrv_dir(str(pcdrv), str(args.res), str(args.lgr))
    card = base / "card.mcd"
    card.write_bytes(mc_test.make_card("fresh"))
    for scenario in ("fresh", "saved"):
        work = base / scenario
        work.mkdir(parents=True, exist_ok=True)
        capture = work / "main_menu.ppm"
        lua_args = {"scenario": scenario, "log": str(work / "test.log"), "capture": str(capture)}
        if args.shots:
            lua_args["shots"] = str(work / "shot_")
        result = pcsx.run(exe=str(exe), pcdrv=str(pcdrv),
                          map_file=str(build / "elma.map"),
                          lua=str(PSX / "test/console_ui_test.lua"),
                          ram8=False, workdir=str(work), timeout=args.timeout,
                          redux=args.redux, args=lua_args,
                          extra_flags=["-memcard1", str(card)])
        for line in result.output.splitlines():
            if line.startswith(("UI ", "PASS:", "FAIL:", "LUA ERROR:")):
                print(scenario + ": " + line, flush=True)
        if result.returncode or not any(line.startswith("PASS:") for line in result.output.splitlines()):
            print("FAIL: %s emulator exit %d" % (scenario, result.returncode))
            print("\n".join(line[:160] for line in result.output.splitlines()[-12:]))
            return 1
        visible, counts = check_main_menu_pixels(capture)
        print("%s: PIXELS Main Menu %s" % (scenario, counts), flush=True)
        if not visible:
            print("FAIL: %s Main Menu text is missing from the displayed image" % scenario)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
