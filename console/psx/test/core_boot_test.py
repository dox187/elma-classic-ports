#!/usr/bin/env python3
"""Boot test of the game core on the PS1 in headless PCSX-Redux.

Builds a PCdrv data directory from the user's own game files (only symbolic
links, nothing is copied or written there), runs build/elma.exe in the 8 MB
development mode (--ram2: in the retail 2 MB) and plays test/core_boot_test.lua: intro, name entry, main
menu, Original Levels, Warm Up, gas. Exits 0 on PASS.

    python3 test/core_boot_test.py [--res elma.res] [--lgr default.lgr]
        [--build DIR] [--shots] [--timeout S] [--disc [--lev-dir DIR]] [--ram2]

--disc runs build/elma-cd.exe from a two-track disc image instead
(tools/mkdisc.py: the program on track 1, the game files on track 2, in
build/core-boot-disc/).

The game files default to $ELMA_RES / $ELMA_LGR, else to elma.res and
build/Lgr/Default_old.lgr at the top of the repository (the Steam layout;
the original-look LGR, as the Steam LGR13 is too big for the PS1). Run it
with the Bash tool's run_in_background option: it takes a few minutes.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PSX = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PSX))
sys.path.insert(0, HERE)
import pcsx  # noqa: E402


def link(target, path):
    if os.path.islink(path) or os.path.exists(path):
        os.remove(path)
    os.symlink(os.path.abspath(target), path)


def make_pcdrv_dir(directory, res, lgr):
    """The disc layout: ELMA.RES, LGR/DEFAULT.LGR (upper case 8.3 names)."""
    os.makedirs(os.path.join(directory, "LGR"), exist_ok=True)
    os.makedirs(os.path.join(directory, "LEV"), exist_ok=True)
    link(res, os.path.join(directory, "ELMA.RES"))
    link(lgr, os.path.join(directory, "LGR", "DEFAULT.LGR"))


def make_disc(build, res, lgr, lev_dir):
    """The disc of build/elma-cd.exe with the game files on track 2."""
    data = os.path.join(build, "core-boot-disc", "data")
    os.makedirs(os.path.join(data, "LGR"), exist_ok=True)
    # The game opens LGR\\DEFAULT.LGR:
    link(lgr, os.path.join(data, "LGR", "DEFAULT.LGR"))
    out = os.path.join(build, "core-boot-disc")
    command = [sys.executable, os.path.join(PSX, "tools", "mkdisc.py"),
               "--exe", os.path.join(build, "elma-cd.exe"), "--res", res,
               "--extra-dir", data, "--out-dir", out, "--name", "elma"]
    if lev_dir:
        command += ["--lev-dir", lev_dir]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    return os.path.join(out, "elma.cue")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--res", default=os.environ.get("ELMA_RES", os.path.join(REPO, "elma.res")))
    parser.add_argument("--lgr", default=os.environ.get(
        "ELMA_LGR", os.path.join(REPO, "build", "Lgr", "Default_old.lgr")))
    parser.add_argument("--build", default=os.path.join(PSX, "build"))
    parser.add_argument("--shots", action="store_true", help="save screenshots in the work dir")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--disc", action="store_true", help="boot from a disc image")
    parser.add_argument("--ram2", action="store_true",
                        help="the retail 2 MB of RAM (the default is the 8 MB development mode)")
    parser.add_argument("--lev-dir", default=os.environ.get("ELMA_LEV_DIR"),
                        help="external levels for the disc")
    args = parser.parse_args()

    for path in (args.res, args.lgr):
        if not os.path.isfile(path):
            print("FAIL: game file not found: %s" % path)
            return 2
    exe = os.path.join(args.build, "elma-cd.exe" if args.disc else "elma.exe")
    if not os.path.isfile(exe):
        print("FAIL: %s not built (make -C console/psx)" % exe)
        return 2

    workdir = os.path.join(args.build, "core-boot-test-disc" if args.disc else "core-boot-test")
    os.makedirs(workdir, exist_ok=True)
    lua_args = {"shots": "boot_"} if args.shots else {}
    run_args = dict(map_file=os.path.splitext(exe)[0] + ".map",
                    lua=os.path.join(HERE, "core_boot_test.lua"), ram8=not args.ram2,
                    timeout=args.timeout, workdir=workdir, args=lua_args)
    if args.disc:
        result = pcsx.run(iso=make_disc(args.build, args.res, args.lgr, args.lev_dir), **run_args)
    else:
        pcdrv = os.path.join(args.build, "pcdrv")
        make_pcdrv_dir(pcdrv, args.res, args.lgr)
        result = pcsx.run(exe=exe, pcdrv=pcdrv, **run_args)
    for line in result.output.splitlines():
        if line.startswith(("elma:", "frame ", "PASS", "FAIL", "LUA")) or "error" in line.lower():
            print(line)
    if result.returncode != 0 and "PASS" not in result.output:
        print("FAIL: emulator exit code %d" % result.returncode)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
