#!/usr/bin/env python3
"""External level menu from a disc image in headless PCSX-Redux.

    python3 test/ext_menu_test.py [--scenario list|lgr] [--lev-dir DIR]
        [--res elma.res] [--lgr default.lgr] [--build DIR] [--shots]

list: the game files and every level of --lev-dir (default: build/Lev at the
      top of the repository, 426 levels) are on track 2; the test goes
      Play, External Levels with the pad and measures how long the list takes
      to appear (printed as TIMING).
lgr:  track 2 holds only pa66le07.lev of that directory, a level that names an
      LGR that is not on the disc; the dialog "LGR file not found" must be
      answered with the pad and the level must start.
Needs build/elma-cd.exe (make -C console/psx). Takes minutes: run it in the
background. Exit 0 on PASS.
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PSX = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PSX))
sys.path.insert(0, HERE)
import pcsx  # noqa: E402
import mc_test  # noqa: E402


def make_disc(build, res, lgr, lev_dir, scenario):
    out = os.path.join(build, "ext-menu-disc-" + scenario)
    levels = lev_dir
    if scenario == "lgr":
        levels = os.path.join(out, "levels")
        os.makedirs(levels, exist_ok=True)
        shutil.copy(os.path.join(lev_dir, "pa66le07.lev"), levels)
    data = os.path.join(out, "data", "LGR")
    os.makedirs(data, exist_ok=True)
    link = os.path.join(data, "DEFAULT.LGR")
    if os.path.lexists(link):
        os.remove(link)
    os.symlink(os.path.abspath(lgr), link)
    command = [sys.executable, os.path.join(PSX, "tools", "mkdisc.py"),
               "--exe", os.path.join(build, "elma-cd.exe"), "--res", res,
               "--extra-dir", os.path.join(out, "data"), "--lev-dir", levels,
               "--out-dir", out, "--name", "elma"]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    return os.path.join(out, "elma.cue")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenario", choices=("list", "lgr"), default="list")
    ap.add_argument("--res", default=os.environ.get("ELMA_RES", os.path.join(REPO, "elma.res")))
    ap.add_argument("--lgr", default=os.environ.get(
        "ELMA_LGR", os.path.join(REPO, "build", "Lgr", "Default_old.lgr")))
    ap.add_argument("--lev-dir", default=os.environ.get(
        "ELMA_LEV_DIR", os.path.join(REPO, "build", "Lev")))
    ap.add_argument("--build", default=os.path.join(PSX, "build"))
    ap.add_argument("--shots", action="store_true")
    ap.add_argument("--8mb", dest="ram8", action="store_true", help="the 8 MB development RAM")
    ap.add_argument("--timeout", type=float, default=1500)
    ap.add_argument("--redux")
    o = ap.parse_args()

    exe = os.path.join(o.build, "elma-cd.exe")
    if not os.path.isfile(exe):
        print("FAIL: %s not built (make -C console/psx)" % exe)
        return 2
    cue = make_disc(o.build, o.res, o.lgr, o.lev_dir, o.scenario)
    work = os.path.join(o.build, "ext-menu-test-" + o.scenario)
    os.makedirs(work, exist_ok=True)
    card = os.path.join(work, "card.mcd")
    with open(card, "wb") as f:
        f.write(mc_test.make_card("fresh"))
    log = os.path.join(work, "test.log")
    if os.path.exists(log):
        os.remove(log)
    args = {"scenario": o.scenario, "log": log}
    if o.shots:
        args["shots"] = os.path.join(work, "shot_")
    r = pcsx.run(iso=cue, map_file=os.path.join(o.build, "elma-cd.map"),
                 lua=os.path.join(HERE, "ext_menu_test.lua"), timeout=o.timeout,
                 workdir=work, redux=o.redux, args=args, ram8=o.ram8, extra_flags=["-memcard1", card])
    for line in r.output.splitlines():
        if line.startswith(("elma: reading", "elma: no")):
            print(line)
    if os.path.exists(log):
        print(open(log).read().rstrip())
    if r.returncode != 0:
        print("FAIL: emulator exit code %d; the end of its output:" % r.returncode)
        print("\n".join(l[:160] for l in r.output.splitlines()[-12:]))
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
