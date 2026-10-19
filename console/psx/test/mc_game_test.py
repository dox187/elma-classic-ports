#!/usr/bin/env python3
"""Memory card test of the game in headless PCSX-Redux (two emulator runs on
one private card image, never the user's cards).

    python3 test/mc_game_test.py [--res elma.res] [--lgr default.lgr]
        [--build DIR] [--shots] [--timeout S]

Run 1: a new player (the first state.dat) must reach the card in the menu;
Warm Up is started with the game's clock held, the state is marked as saved
in the middle of the level (the card must not be written there), the level is
finished with test/phys_warmup_finish.txt, one step at a time, and the card
must be written after the level, in the menu.
Run 2: a new emulator with the same card: the best time must come back, without
a name entry. The game files are read from the host (PCdrv, symbolic links only).
Takes a few minutes: run it in the background. Exit 0 on PASS.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PSX = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PSX))
sys.path.insert(0, HERE)
import pcsx  # noqa: E402
import mc_test  # noqa: E402
from core_boot_test import make_pcdrv_dir  # noqa: E402


def read_script(path):
    """The time and the script of test/phys_warmup_finish.txt."""
    want, items = None, []
    for line in open(path):
        line = line.strip()
        if line.startswith("time "):
            m = re.fullmatch(r"time (\d\d):(\d\d):(\d\d)", line)
            want = (int(m.group(1)) * 60 + int(m.group(2))) * 100 + int(m.group(3))
        elif line and not line.startswith("#"):
            items.append(line)
    return want, " ".join(items)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--res", default=os.environ.get("ELMA_RES", os.path.join(REPO, "elma.res")))
    ap.add_argument("--lgr", default=os.environ.get(
        "ELMA_LGR", os.path.join(REPO, "build", "Lgr", "Default_old.lgr")))
    ap.add_argument("--build", default=os.path.join(PSX, "build"))
    ap.add_argument("--shots", action="store_true", help="screenshots in the work dirs")
    ap.add_argument("--timeout", type=float, default=1500)
    ap.add_argument("--finish", action="store_true",
                    help="also play test/phys_warmup_finish.txt step by step (experimental: the bike dies)")
    ap.add_argument("--redux")
    o = ap.parse_args()

    exe = os.path.join(o.build, "elma.exe")
    if not os.path.isfile(exe):
        print("FAIL: %s not built (make -C console/psx)" % exe)
        return 2
    want, script = (read_script(os.path.join(HERE, "phys_warmup_finish.txt")) if o.finish else (0, ""))
    base = os.path.join(o.build, "mc-game-test")
    os.makedirs(base, exist_ok=True)
    pcdrv = os.path.join(base, "pcdrv")
    make_pcdrv_dir(pcdrv, o.res, o.lgr)
    card = os.path.join(base, "card.mcd")
    with open(card, "wb") as f:
        f.write(mc_test.make_card("fresh"))

    status = 0
    for run in (1, 2):
        work = os.path.join(base, "run%d" % run)
        args = {"run": run, "want_time": want, "script": script}
        if os.environ.get("MC_NODIRTY"): args["nodirty"] = 1
        if os.environ.get("MC_SECOND"): args["second"] = 1
        if os.environ.get("MC_NOFREEZE"): args["nofreeze"] = 1
        if o.shots:
            args["shots"] = os.path.join(work, "shot_")
        os.makedirs(work, exist_ok=True)
        log = os.path.join(work, "test.log")
        if os.path.exists(log):
            os.remove(log)
        args["log"] = log
        r = pcsx.run(exe=exe, map_file=os.path.join(o.build, "elma.map"),
                     lua=os.path.join(HERE, "mc_game_test.lua"), pcdrv=pcdrv, ram8=True,
                     timeout=o.timeout, workdir=work, redux=o.redux, args=args,
                     extra_flags=["-memcard1", card])
        for line in r.output.splitlines():
            if line.startswith("elma: memory card"):
                print("run %d: %s" % (run, line))
        if os.path.exists(log):
            for line in open(log):
                print("run %d: %s" % (run, line.rstrip()))
        if r.returncode != 0:
            print("FAIL: run %d exit code %d; the end of its output:" % (run, r.returncode))
            print("\n".join(l[:160] for l in r.output.splitlines()[-12:]))
            status = 1
            break
    print("PASS" if status == 0 else "FAIL")
    return status


if __name__ == "__main__":
    sys.exit(main())
