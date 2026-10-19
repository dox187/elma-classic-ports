#!/usr/bin/env python3
"""Fidelity test of the fixed point physics of the PlayStation (src/phys/)
on the host: builds test/phys_host.cpp with the original double physics of
src/ and the fixed point one, writes the internal levels of elma.res as text
(test/phys_levels.py) and

1. plays test/phys_warmup_finish.txt on Warm Up: both physics must eat the
   apple and finish in the time written there (exit code 1 if not);
2. plays a corpus on the internal levels: gas only, and seeded random key
   scripts, in whole steps and with the frames of a 30 fps game loop, and
   reports, for each case, whether the events (apples, flower, death) are
   the same and how far apart the bikes get over time;
3. runs test/phys_check.c, a fixed point run with a checksum of every
   state, on the host and with --ps1 BUILD also its PS-EXE (BUILD/
   physcheck.exe, make -C console/psx) in headless PCSX-Redux: the sums
   must be equal (exit code 1 if not).

    python3 test/phys_test.py [--res elma.res] [--build DIR] [--levels 0,1,..]
        [--seeds N] [--seconds S] [--quiet] [--ps1 BUILD]

The outputs go to DIR (default console/psx/build/phys-test, git-ignored):
the level texts are made from the user's game data and must stay there.
"""
import argparse
import os
import random
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PSX = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PSX))

CORE = ["LEPTET.CPP", "BEALLIT.CPP", "UTKOZES.CPP", "UTKOZES2.CPP", "SZAKASZ.CPP", "VEKT2.CPP"]
FLAGS = ["-O2", "-fsigned-char", "-fwrapv", "-fno-strict-aliasing", "-ffp-contract=off", "-w"]


def build(out):
    """Builds phys_host in out; the core includes its headers by lower case
    names, which are forwarded as in the CMake builds."""
    lc = os.path.join(out, "lowercase_headers")
    os.makedirs(lc, exist_ok=True)
    src = os.path.join(REPO, "src")
    for name in os.listdir(src):
        if name.endswith(".H"):
            text = '#include "%s"\n' % os.path.join(src, name)
            path = os.path.join(lc, name.lower())
            if not os.path.exists(path) or open(path).read() != text:
                with open(path, "w") as f:
                    f.write(text)
    inc = ["-I" + src, "-I" + os.path.join(REPO, "desktop"), "-I" + lc,
           "-I" + os.path.join(PSX, "src"), "-I" + os.path.join(PSX, "src", "phys")]
    obj = os.path.join(out, "fixphys.o")
    subprocess.run(["gcc", "-std=gnu11"] + FLAGS + inc +
                   ["-c", os.path.join(PSX, "src", "phys", "fixphys.c"), "-o", obj], check=True)
    exe = os.path.join(out, "phys_host")
    subprocess.run(["g++", "-std=gnu++11", "-fpermissive"] + FLAGS + inc +
                   ["-o", exe, os.path.join(HERE, "phys_host.cpp"),
                    os.path.join(PSX, "src", "phys", "phys_glue.cpp"), obj] +
                   [os.path.join(src, f) for f in CORE], check=True)
    return exe


def read_script(path):
    """The time (mm:ss:hh) and the keys of a script file."""
    time, keys = None, []
    for line in open(path):
        line = line.split("#")[0].strip()
        if line.startswith("time "):
            time = line.split()[1]
        elif line:
            keys.append(line)
    return time, " ".join(keys)


def random_script(rng, steps):
    """Keys a player might press: mostly gas, with brakes, volts and turns."""
    keys = ["G"] * 6 + ["N", "B", "GR", "GL", "R", "L", "GB"]
    items, total = [], 0
    while total < steps:
        k = rng.choice(keys)
        if rng.random() < 0.08:
            k += "T"
        n = rng.randint(8, 80)
        items.append("%s%d" % (k, n))
        total += n
    return " ".join(items)


SUMMARY = re.compile(r"events (SAME|DIFFERENT) \(largest time difference ([\d.]+) s\); "
                     r"apart 1 mm (-?[\d.]+) s, 1 cm (-?[\d.]+) s, 10 cm (-?[\d.]+) s; "
                     r"largest ([\d.]+)/([\d.]+)/([\d.]+) m .*; ([\d.]+)% within 1 cm")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--res", default=os.environ.get("ELMA_RES", os.path.join(REPO, "elma.res")))
    ap.add_argument("--build", default=os.path.join(PSX, "build", "phys-test"))
    ap.add_argument("--levels", default="all", help="internal levels from 0, or all")
    ap.add_argument("--seeds", type=int, default=2, help="random scripts a level")
    ap.add_argument("--seconds", type=float, default=30, help="length of the scripts")
    ap.add_argument("--quiet", action="store_true", help="only the totals of the corpus")
    ap.add_argument("--ps1", metavar="BUILD", help="also run BUILD/physcheck.exe in the emulator")
    a = ap.parse_args()

    os.makedirs(a.build, exist_ok=True)
    exe = build(a.build)
    levels = os.path.join(a.build, "levels")
    subprocess.run([sys.executable, os.path.join(HERE, "phys_levels.py"), a.res, levels], check=True)

    # 1. Warm Up finish:
    want, script = read_script(os.path.join(HERE, "phys_warmup_finish.txt"))
    out = subprocess.run([exe, os.path.join(levels, "lev00.txt"), script, "--every", "100"],
                         capture_output=True, text=True, check=True).stdout
    ok = True
    for name in ("orig", "fixed"):
        m = re.search(r"%s: +(.*)" % name, out)
        got = m.group(1) if m else ""
        fin = re.search(r"finish@(\S+)", got)
        good = fin is not None and fin.group(1) == want and "apple" in got
        ok &= good
        print("Warm Up finish, %-5s physics: %s %s" % (name, got.strip(), "OK" if good else "FAIL"))

    # 2. The corpus:
    names = sorted(f for f in os.listdir(levels) if re.fullmatch(r"lev\d\d\.txt", f))
    if a.levels != "all":
        names = ["lev%02d.txt" % int(n) for n in a.levels.split(",")]
    steps = int(a.seconds * 0.4368 / 0.0055)
    cases = []
    for name in names:
        n = int(name[3:5])
        cases.append((name, "G%d" % steps))
        for seed in range(a.seeds):
            cases.append((name, random_script(random.Random(n * 1000 + seed), steps)))
    path = os.path.join(a.build, "cases.txt")
    with open(path, "w") as f:
        for name, s in cases:
            f.write("%s %s\n" % (os.path.join(levels, name), s))
    for fps in (0, 30):
        out = subprocess.run([exe, "-f", path, "--fps", str(fps)], capture_output=True,
                             text=True, check=True).stdout
        rows = SUMMARY.findall(out)
        same = sum(1 for r in rows if r[0] == "SAME")
        never_1mm = sum(1 for r in rows if float(r[2]) < 0)
        never_1cm = sum(1 for r in rows if float(r[3]) < 0)
        first5 = sorted(float(r[6]) for r in rows)
        within = sorted(float(r[8]) for r in rows)
        apart = sorted(float(r[3]) for r in rows if float(r[3]) >= 0)
        if not a.quiet:
            print(out.rstrip())
        print("corpus %s: %d cases, events the same in %d; never 1 mm apart in %d, never 1 cm "
              "in %d; median first 1 cm apart %.1f s; largest distance in the first 5 s: "
              "median %.6f m, worst %.4f m; samples within 1 cm: median %.1f%%, worst %.1f%%" % (
                  "in whole steps" if fps == 0 else "at %d fps" % fps, len(rows), same,
                  never_1mm, never_1cm, apart[len(apart) // 2] if apart else -1,
                  first5[len(first5) // 2], first5[-1], within[len(within) // 2], within[0]))
    if not ok:
        print("FAIL: Warm Up is not finished in %s" % want)

    # 3. The same bits on the PlayStation:
    check = os.path.join(a.build, "phys_check")
    subprocess.run(["gcc", "-std=gnu11"] + FLAGS + ["-I" + os.path.join(PSX, "src", "phys"),
                    "-o", check, os.path.join(HERE, "phys_check.c"),
                    os.path.join(PSX, "src", "phys", "fixphys.c"), "-lm"], check=True)
    out = subprocess.run([check], capture_output=True, text=True, check=True).stdout
    print(out.rstrip())
    host = re.search(r"physcheck: .*", out).group(0).strip()
    if a.ps1:
        sys.path.insert(0, HERE)
        import pcsx
        r = pcsx.run(exe=os.path.join(a.ps1, "physcheck.exe"),
                     map_file=os.path.join(a.ps1, "physcheck.map"),
                     lua=os.path.join(HERE, "phys_check.lua"), timeout=240,
                     workdir=os.path.join(a.build, "physcheck-ps1"))
        m = re.search(r"physcheck: .*", r.output)
        ps1 = m.group(0).strip() if m else "(no result: exit code %d)" % r.returncode
        same = ps1 == host
        print("PlayStation: %s %s" % (ps1, "SAME" if same else "DIFFERENT"))
        ok &= same
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
