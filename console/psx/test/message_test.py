#!/usr/bin/env python3
"""Repeated message/card notices and menu/game recovery in retail 2 MB RAM.

Uses a private copy of a valid POT14 level with its version changed to 15.
The core shows two warnings, then continues loading the compatible data.
No game data is changed in place. Run after building elma-cd:

    python3 test/message_test.py --build build --level /path/to/small.lev

The emulator is headless and silent, with the limits of test/pcsx.py.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

import pcsx
import mc_test

PSX = Path(__file__).resolve().parent.parent
REPO = PSX.parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", type=Path, default=PSX / "build")
    ap.add_argument("--level", type=Path, default=REPO / "build/Lev/pa60le10.lev")
    ap.add_argument("--res", default=os.environ.get("ELMA_RES", str(REPO / "elma.res")))
    ap.add_argument("--lgr", default=os.environ.get("ELMA_LGR", str(REPO / "build/Lgr/Default_old.lgr")))
    ap.add_argument("--pal", action="store_true")
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--redux")
    ap.add_argument("--shots", action="store_true")
    args = ap.parse_args()
    build = args.build.resolve()
    work = build / ("message-test-pal" if args.pal else "message-test-ntsc")
    levels = work / "levels"
    levels.mkdir(parents=True, exist_ok=True)
    data = args.level.read_bytes()
    if data[:5] != b"POT14":
        ap.error("--level must be a version 14 external level")
    (levels / "WARN.LEV").unlink(missing_ok=True)
    for name in ("WARN1.LEV", "WARN2.LEV"):
        (levels / name).write_bytes(b"POT15" + data[5:])
    disc = work / "disc"
    subprocess.run([sys.executable, str(PSX / "tools/mkdisc.py"),
                    "--exe", str(build / "elma-cd.exe"), "--res", args.res,
                    "--lgr", args.lgr, "--lev-dir", str(levels),
                    "--out-dir", str(disc), "--name", "elma"],
                   check=True, stdout=subprocess.DEVNULL)
    card = work / "card.mcd"
    card.write_bytes(mc_test.make_card("fresh"))
    lua_args = {"force": 2 if args.pal else 1, "log": str(work / "test.log")}
    if args.shots:
        lua_args["shots"] = str(work / "shot_")
    result = pcsx.run(iso=str(disc / "elma.cue"),
                      map_file=str(build / "elma-cd.map"),
                      lua=str(PSX / "test/message_test.lua"),
                      workdir=str(work), timeout=args.timeout, redux=args.redux,
                      args=lua_args, extra_flags=["-memcard1", str(card), "-interpreter", "-debugger"])
    for line in result.output.splitlines():
        if line.startswith(("MESSAGE", "PASS", "FAIL", "LUA ERROR")):
            print(line)
    if result.returncode or "PASS:" not in result.output:
        print("FAIL: emulator exit code %d" % result.returncode)
        print("\n".join(line[:160] for line in result.output.splitlines()[-10:]))
        return result.returncode or 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
