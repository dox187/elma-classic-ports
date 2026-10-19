#!/usr/bin/env python3
"""PS1 disc test: builds discs with tools/mkdisc.py from the cdtest PS-EXE and
runs them in headless PCSX-Redux (through test/pcsx.py, no window, no sound).

  python3 cd_test.py --build DIR [--redux PATH] [--layouts raw[,split,2048]]
                     [--real] [--keep] [--discs-only] [--timeout S]

For every layout (raw = MODE1/2352 single .bin, split = raw track 2 in its
own file, 2048 = plain MODE1/2048 track 2 file) it runs the synthetic data
set, and with --real also the real game data (same inputs as disc_test.py).
The discs go to DIR/cdtest-disc/<set>-<layout>/ and are deleted afterwards
unless --keep (or --discs-only).
"""

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PSX = os.path.normpath(os.path.join(HERE, ".."))
MKDISC = os.path.join(PSX, "tools", "mkdisc.py")

sys.path.insert(0, HERE)
import pcsx  # noqa: E402


def load_disc_test():
    spec = importlib.util.spec_from_file_location("disc_test", os.path.join(HERE, "disc_test.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Layouts PCSX-Redux (build 450) cannot play: its cue parser rejects the
# MODE1/2048 track type, and for a track in a second FILE it reports the right
# positions but delivers no sector data. They are not counted as failures.
KNOWN_BAD = {
    "split": "reads of a track in a second .bin return no data",
    "2048": "cue parser: TRACK type MODE1_2048 not supported",
}

LAYOUT_ARGS = {
    "raw": [],
    "split": ["--split"],
    "2048": ["--track2-format", "2048"],
}


def build_disc(outdir, exe, data_args, layout):
    shutil.rmtree(outdir, ignore_errors=True)
    cmd = [sys.executable, MKDISC, "--out-dir", outdir, "--exe", exe,
           "--manifest", "SUMS.TXT"] + data_args + LAYOUT_ARGS[layout]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        print(r.stdout)
        raise SystemExit("mkdisc failed: " + " ".join(cmd))
    return os.path.join(outdir, "elma.cue")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default=os.path.join(PSX, "build"))
    ap.add_argument("--redux")
    ap.add_argument("--layouts", default="raw", help="raw,split,2048 (split and 2048 are known not to work in PCSX-Redux)")
    ap.add_argument("--real", action="store_true", help="also test the real game data")
    ap.add_argument("--real-only", action="store_true")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--discs-only", action="store_true")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--frames", type=int, default=0, help="Lua frame limit")
    args = ap.parse_args()

    build = os.path.abspath(args.build)
    exe = os.path.join(build, "cdtest.exe")
    mapf = os.path.join(build, "cdtest.map")
    if not os.path.exists(exe):
        raise SystemExit("build cdtest first (make -C console/psx cdtest)")
    layouts = args.layouts.split(",")
    root = os.path.join(build, "cdtest-disc")
    os.makedirs(root, exist_ok=True)

    dt = load_disc_test()
    sets = []  # (name, data args, min levels)
    if not args.real_only:
        S = dt.make_sources(root)
        sets.append(("synthetic", ["--res", S["res"], "--lgr", S["lgr"], "--lev-dir", S["lev"],
                                   "--extra-dir", S["extra"]], 100))
    if args.real or args.real_only:
        ok = all(os.path.exists(p) for p in (dt.REAL_RES, dt.REAL_LGR, dt.REAL_LEV))
        if not ok:
            raise SystemExit("real game data not found (ELMA_RES / ELMA_LGR / ELMA_LEV)")
        sets.append(("real", ["--res", dt.REAL_RES, "--lgr", dt.REAL_LGR,
                              "--lev-dir", dt.REAL_LEV], 400))

    failed = []
    for name, data_args, min_levels in sets:
        for layout in layouts:
            tag = "%s-%s" % (name, layout)
            d = os.path.join(root, tag)
            cue = build_disc(d, exe, data_args, layout)
            print("== %s: %s" % (tag, cue))
            if args.discs_only:
                continue
            frames = args.frames or (60000 if name == "real" else 20000)
            if layout != "raw" and not args.frames:
                frames = 3000   # known to fail in PCSX-Redux, do not wait long
            r = pcsx.run(iso=cue, lua=os.path.join(HERE, "cd_test.lua"), map_file=mapf,
                         timeout=args.timeout, redux=args.redux,
                         workdir=os.path.join(d, "redux"),
                         args={"frames": str(frames), "min_levels": str(min_levels)})
            for line in r.output.splitlines():
                if re.search(r"CDTEST|probe|tracks|  track |LEV|mount data|RESULT|^PASS|^FAIL|LUA ERROR|frame \d+:", line):
                    print("   " + line)
            if r.returncode != 0 and layout in KNOWN_BAD:
                print("   -> not supported by PCSX-Redux (known limitation: %s)" % KNOWN_BAD[layout])
            elif r.returncode != 0:
                failed.append(tag)
                print("   -> FAILED (exit %d%s)" % (r.returncode, ", timeout" if r.timed_out else ""))
                if "CDTEST" not in r.output:
                    print(r.output[-3000:])
            else:
                print("   -> ok" + (" (layout now works in this emulator)" if layout in KNOWN_BAD else ""))
            if not args.keep:
                shutil.rmtree(d, ignore_errors=True)
    if not args.keep and not args.discs_only:
        shutil.rmtree(os.path.join(root, "src"), ignore_errors=True)
    print("\n%d of %d runs passed" % (len(sets) * len(layouts) - len(failed), len(sets) * len(layouts)))
    for t in failed:
        print("  FAILED: " + t)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
