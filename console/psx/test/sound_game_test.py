#!/usr/bin/env python3
"""Plays the game core boot test (test/core_boot_test.lua) with the sound
stream counters printed along the way. Needs the game build with sound
(elma.exe in BUILD) and the user's game files, like core_boot_test.py.
Headless and silent. Run it in the background; it takes a few minutes.

    python3 test/sound_game_test.py [--build DIR] [--timeout S]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PSX = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PSX))
sys.path.insert(0, HERE)
import pcsx  # noqa: E402
from core_boot_test import make_pcdrv_dir  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--res", default=os.environ.get("ELMA_RES", os.path.join(REPO, "elma.res")))
    p.add_argument("--lgr", default=os.environ.get(
        "ELMA_LGR", os.path.join(REPO, "build", "Lgr", "Default_old.lgr")))
    p.add_argument("--build", default=os.path.join(PSX, "build"))
    p.add_argument("--timeout", type=float, default=900)
    args = p.parse_args()

    exe = os.path.join(args.build, "elma.exe")
    pcdrv = os.path.join(args.build, "pcdrv")
    make_pcdrv_dir(pcdrv, args.res, args.lgr)
    result = pcsx.run(
        exe=exe, pcdrv=pcdrv, ram8=True, timeout=args.timeout,
        map_file=os.path.splitext(exe)[0] + ".map",
        lua=os.path.join(HERE, "sound_game_test.lua"),
        workdir=os.path.join(args.build, "sound-game-test"),
        args={"core_lua": os.path.join(HERE, "core_boot_test.lua")})
    for line in result.output.splitlines():
        if line.startswith(("elma:", "sound:", "PASS", "FAIL", "LUA")) or "error" in line.lower():
            print(line)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
