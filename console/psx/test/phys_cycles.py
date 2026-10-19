#!/usr/bin/env python3
"""Counts the emulated CPU cycles of the physics on the PS1 in headless
PCSX-Redux (test/phys_cycles.lua): one leptet, one vizsgalat and one whole
step of the game loop, average, minimum and maximum, while an internal level
is played with a fixed input.

    python3 test/phys_cycles.py [--level N] [--seconds S] [--input gas|mixed]
        [--build DIR] [--res elma.res] [--lgr default.lgr] [--timeout S]
        [--probes SYM,SYM]

The level is an internal level from 0 (0 Warm Up, 15 New Wave); the
script unlocks all levels in the player's state of the run. The game data
comes from PCdrv as in test/core_boot_test.py (only links to the user's
files). The cycles are those PCSX-Redux counts, which approximates the
timing of the real CPU. Run it with the Bash tool's run_in_background
option: it takes a few minutes.
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
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--level", type=int, default=0)
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--input", default="mixed", choices=("gas", "mixed"))
    parser.add_argument("--build", default=os.environ.get("BUILD", os.path.join(PSX, "build")))
    parser.add_argument("--res", default=os.environ.get("ELMA_RES", os.path.join(REPO, "elma.res")))
    parser.add_argument("--lgr", default=os.environ.get(
        "ELMA_LGR", os.path.join(REPO, "build", "Lgr", "Default_old.lgr")))
    parser.add_argument("--timeout", type=float, default=1500)
    parser.add_argument("--shots", action="store_true")
    parser.add_argument("--probes", default="",
                        help="comma separated symbols of the map whose cycles to count")
    args = parser.parse_args()

    exe = os.path.join(args.build, "elma.exe")
    if not os.path.isfile(exe):
        print("FAIL: %s not built (make -C console/psx)" % exe)
        return 2
    workdir = os.path.join(args.build, "phys-cycles-%d" % args.level)
    os.makedirs(workdir, exist_ok=True)
    pcdrv = os.path.join(args.build, "pcdrv")
    make_pcdrv_dir(pcdrv, args.res, args.lgr)
    lua_args = {"level": args.level, "seconds": args.seconds, "input": args.input}
    if args.shots:
        lua_args["shots"] = "cycles_"
    if args.probes:
        lua_args["probes"] = args.probes
    result = pcsx.run(exe=exe, pcdrv=pcdrv, map_file=os.path.join(args.build, "elma.map"),
                      lua=os.path.join(HERE, "phys_cycles.lua"), ram8=True,
                      timeout=args.timeout, workdir=workdir, args=lua_args,
                      # Lua breakpoints only fire with the debugger, which
                      # needs the interpreter:
                      extra_flags=("-interpreter", "-debugger"))
    for line in result.output.splitlines():
        if line.startswith(("elma:", "frame ", "PASS", "FAIL", "LUA", "CYCLES")) or \
                "error" in line.lower():
            print(line)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
