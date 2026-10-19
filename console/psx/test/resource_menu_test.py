#!/usr/bin/env python3
"""Verify content-based Play menus and level loading from a retail 2 MB disc.

Run once with each resource file, for example:
  python3 test/resource_menu_test.py --res /path/to/classic/Elma.res
  python3 test/resource_menu_test.py --res /path/to/Steam/elma.res

Classic resources exercise their original and external level menus; resources
with collections verify every collection row and play the first collection.
Original game inputs are read-only. All generated files remain in --build.
"""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import sys

import mc_test
import pcsx
from phys_levels import INTERNAL_LEVELS, Resource
from res_layout import COLLECTIONS, resource_layout

PSX = Path(__file__).resolve().parent.parent
REPO = PSX.parent.parent


def level_stamp(data):
    version = 14 if data[:3] == b"@@^" else int(data[3:5])
    return struct.unpack_from("<I", data, 7 if version >= 13 else 5)[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", type=Path, default=PSX / "build")
    ap.add_argument("--res", type=Path, default=Path(os.environ.get("ELMA_RES", REPO / "elma.res")))
    ap.add_argument("--lgr", type=Path, default=Path(os.environ.get("ELMA_LGR", REPO / "build/Lgr/Default_old.lgr")))
    ap.add_argument("--external", type=Path, default=REPO / "build/Lev/pa60le10.lev")
    ap.add_argument("--scenario", choices=("auto", "original", "external", "collection"), default="auto")
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--redux")
    ap.add_argument("--shots", action="store_true")
    args = ap.parse_args()
    build, res, lgr = args.build.resolve(), args.res.resolve(), args.lgr.resolve()
    layout = resource_layout(res)
    resource = Resource(res)
    scenarios = (["collection", "external"] if layout["collections"] else ["original", "external"])
    if args.scenario != "auto":
        scenarios = [args.scenario]
    if "collection" in scenarios and not layout["collections"]:
        ap.error("the supplied resource has no level collections")
    base = build / ("resource-menu-%d" % layout["descriptor_slots"])
    levels = base / "levels"
    levels.mkdir(parents=True, exist_ok=True)
    link = levels / "TEST.LEV"
    link.unlink(missing_ok=True)
    link.symlink_to(args.external.resolve())
    disc = base / "disc"
    subprocess.run([sys.executable, str(PSX / "tools/mkdisc.py"),
                    "--exe", str(build / "elma-cd.exe"), "--res", str(res),
                    "--lgr", str(lgr), "--lev-dir", str(levels),
                    "--out-dir", str(disc), "--name", "elma"],
                   check=True, stdout=subprocess.DEVNULL)
    print("LAYOUT slots=%d internal=%d collections=%s" %
          (layout["descriptor_slots"], layout["internal_count"], layout["collection_counts"]), flush=True)
    for scenario in scenarios:
        work = base / scenario
        work.mkdir(parents=True, exist_ok=True)
        card = work / "card.mcd"
        card.write_bytes(mc_test.make_card("fresh"))
        if scenario == "external":
            stamp = level_stamp(args.external.read_bytes())
        elif scenario == "collection":
            title, prefix = next(item for item, count in zip(COLLECTIONS, layout["collection_counts"]) if count)
            stamp = level_stamp(resource.read(prefix + "01.lev"))
        else:
            stamp = level_stamp(resource.read(INTERNAL_LEVELS[0]))
        log = work / "test.log"
        log.unlink(missing_ok=True)
        lua_args = {"collections": int(layout["collections"]), "scenario": scenario,
                    "stamp": stamp, "slots": layout["descriptor_slots"],
                    "rows": "|".join(layout["collection_rows"]),
                    "internal_steps": ",".join(layout["internal_steps"]),
                    "external_steps": ",".join(layout["external_steps"]),
                    "counts": ",".join(str(n) for n in layout["collection_counts"]),
                    "log": str(log)}
        if scenario == "collection":
            lua_args["collection_steps"] = ",".join(["DOWN"] * layout["collection_rows"].index(title) + ["CROSS"])
        if args.shots:
            lua_args["shots"] = str(work / "shot_")
        result = pcsx.run(iso=str(disc / "elma.cue"), map_file=str(build / "elma-cd.map"),
                          lua=str(PSX / "test/resource_menu_test.lua"), ram8=False,
                          workdir=str(work), timeout=args.timeout, redux=args.redux,
                          args=lua_args, extra_flags=["-memcard1", str(card)])
        for line in result.output.splitlines():
            if line.startswith(("MENU", "LEVEL", "PASS:", "FAIL:", "LUA ERROR:")):
                print(scenario + ": " + line, flush=True)
        if result.returncode or not any(line.startswith("PASS:") for line in result.output.splitlines()):
            print("FAIL: %s emulator exit %d" % (scenario, result.returncode))
            print("\n".join(line[:160] for line in result.output.splitlines()[-12:]))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
