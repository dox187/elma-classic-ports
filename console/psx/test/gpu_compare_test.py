#!/usr/bin/env python3
"""The GPU renderer against the original software renderer, headless.

Builds the comparison program (ELMA_PSX_GPU_COMPARE: both renderers, the
software one switched on by gpu_render_soft) into BUILD/gpu-compare, and for
each level runs test/gpu_compare_test.lua in PCSX-Redux (8 MB mode): the
game's clock is stopped, the same state is drawn by both renderers and
screenshotted, at the start and after some gas. The software picture
(640x480) is sampled at the GPU view's pixels (320x240, every second pixel,
aligned to the GPU's camera) and compared.

    python3 test/gpu_compare_test.py [--build DIR] [--levels warmup,internal,external]
        [--external FILE.lev[,FILE.lev...]] [--no-build] [--timeout S] [--gpu-only] [--fps] [--ram2]

--ram2 runs in the retail 2 MB of RAM (with --gpu-only; the comparison
program does not fit). --gpu-only takes only the GPU renderer's pictures, with the normal program
of BUILD (elma.exe, elma-cd.exe; it is not built), e.g. for a level too big
for the software renderer's brushes in 8 MB; --fps also measures the view's
frame rate (10 seconds without input after the pictures, or until the
level ends): frames a second, the longest gap between two frames, and the
average time of each part of building a frame.

Levels: Warm Up; internal level 19 (95 pictures, the most of the early
levels); external levels from build/Lev (default pa27le01.lev: 183
polygons, 1774 vertices, 592 pictures; --external takes a comma separated
list, each played in turn as external-NAME), played from a disc image as
PCdrv cannot list directories. (pa67le07.lev, 2410 pictures, is too big for the
software renderer's brushes in 8 MB: --gpu-only.) The game files (elma.res, the LGR, the levels)
are the user's: only linked, never copied or changed.

Writes into BUILD/gpu-compare-test/: for each state NAME a side by side PNG
(software sampled | GPU | difference) and the PPM screenshots. A pixel
counts as matching if no color component differs by more than 24 (of 255).
Exit status 0 if every state matches in at least 90% of its pixels.
Takes several minutes; run it in the background.
"""
import argparse
import os
import struct
import subprocess
import sys
import threading
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
PSX = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PSX))
sys.path.insert(0, HERE)
import pcsx  # noqa: E402
import core_boot_test  # noqa: E402

SDK = os.path.expanduser("~/.local/share/elma-psx")

LEVELS = {
    # name: (menu path after "Play", internal levels to unlock, disc)
    "warmup": ("DOWN,CROSS,CROSS", 0, False),
    "internal": ("DOWN,CROSS" + ",DOWN" * 18 + ",CROSS", 19, False),
    "external": ("DOWN,DOWN,DOWN,DOWN,DOWN,CROSS,CROSS", 0, True),
}


def build(build_dir):
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([os.path.join(SDK, "psn00bsdk", "bin"), os.path.join(SDK, "gcc", "bin"),
                                   env.get("PATH", "")])
    subprocess.run(["cmake", "-S", PSX, "-B", build_dir, "-G", "Ninja",
                    "-DCMAKE_TOOLCHAIN_FILE=" + os.path.join(SDK, "psn00bsdk", "lib", "libpsn00b", "cmake",
                                                             "sdk.cmake"),
                    "-DCMAKE_BUILD_TYPE=Release", "-DPSN00BSDK_TC=" + os.path.join(SDK, "gcc"),
                    "-DMKPSXISO=" + os.path.join(SDK, "mkpsxiso", "bin", "mkpsxiso"),
                    "-DELMA_PSX_GPU_COMPARE=ON"], check=True, env=env, stdout=subprocess.DEVNULL)
    subprocess.run(["cmake", "--build", build_dir, "--target", "elma", "elma-cd"], check=True, env=env,
                   stdout=subprocess.DEVNULL)


def read_ppm(path):
    with open(path, "rb") as f:
        data = f.read()
    parts = data.split(b"\n", 3)
    w, h = map(int, parts[1].split())
    return w, h, parts[3]


def write_png(path, w, h, rgb):
    raw = b"".join(b"\0" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))

    def chunk(t, x):
        return struct.pack(">I", len(x)) + t + x + struct.pack(">I", zlib.crc32(t + x) & 0xffffffff)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
                chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def compare(workdir, name, cam, out_png):
    """Returns (matching fraction, mean difference) of a state."""
    gw, gh, gpu = read_ppm(os.path.join(workdir, name + "_gpu.ppm"))
    sw, sh, soft = read_ppm(os.path.join(workdir, name + "_soft.ppm"))
    if (gw, gh) != (320, 240) or (sw, sh) != (640, 480):
        return 0.0, 255.0
    cam_x, cam_y, view_x, view_y = cam
    # A GPU pixel (cx, r) samples brush column cam_x + 2cx and row
    # cam_y + 478 - 2r (gpu_draw.cpp); the software picture's column is the
    # brush column - view_x, its row from the top 479 - (row - view_y).
    dx = cam_x - view_x
    dy = cam_y - view_y
    side = bytearray(3 * 320 * 240 * 3)
    match = total = 0
    diff_sum = 0
    for r in range(240):
        sy = 479 - (478 - 2 * r + dy)
        for cx in range(320):
            sx = 2 * cx + dx
            gi = (r * 320 + cx) * 3
            g = gpu[gi:gi + 3]
            o = 3 * (r * 960 + 320 + cx)
            side[o:o + 3] = g
            if not (0 <= sx < 640 and 0 <= sy < 480):
                continue
            si = (sy * 640 + sx) * 3
            s = soft[si:si + 3]
            o = 3 * (r * 960 + cx)
            side[o:o + 3] = s
            d = max(abs(g[0] - s[0]), abs(g[1] - s[1]), abs(g[2] - s[2]))
            diff_sum += d
            total += 1
            if d <= 24:
                match += 1
            o = 3 * (r * 960 + 640 + cx)
            v = min(255, d * 2)
            side[o:o + 3] = bytes((v, v if d <= 24 else 0, v if d <= 24 else 0))
    write_png(out_png, 960, 240, bytes(side))
    return (match / total if total else 0.0), (diff_sum / total if total else 255.0)


def run_level(name, args, exe_dir, result):
    # "external" is one run for each file of --external, named by the file:
    key, external = name, None
    if name.startswith("external:"):
        external = name.split(":", 1)[1]
        name = "external-" + os.path.splitext(os.path.basename(external))[0].lower()
        path, levels, disc = LEVELS["external"]
    else:
        path, levels, disc = LEVELS[name]
    workdir = os.path.join(args.build, "gpu-compare-test", name + ("-gpu" if args.gpu_only else ""))
    os.makedirs(workdir, exist_ok=True)
    lua_args = {"path": path, "soft": "0" if args.gpu_only else "1", "shots": ""}
    if args.trace:
        lua_args["trace"] = "1"
    if args.fps:
        lua_args["fps"] = "1"
    if levels:
        lua_args["levels"] = str(levels)
    exe = os.path.join(exe_dir, "elma-cd.exe" if disc else "elma.exe")
    run_args = dict(map_file=os.path.splitext(exe)[0] + ".map", lua=os.path.join(HERE, "gpu_compare_test.lua"),
                    ram8=not args.ram2, timeout=args.timeout, workdir=workdir, args=lua_args)
    if disc:
        lev_dir = os.path.join(workdir, "lev")
        os.makedirs(lev_dir, exist_ok=True)
        for f in os.listdir(lev_dir):
            os.remove(os.path.join(lev_dir, f))
        core_boot_test.link(external, os.path.join(lev_dir, os.path.basename(external).upper()))
        iso = core_boot_test.make_disc(exe_dir, args.res, args.lgr, lev_dir)
        r = pcsx.run(iso=iso, **run_args)
    else:
        pcdrv = os.path.join(workdir, "pcdrv")
        core_boot_test.make_pcdrv_dir(pcdrv, args.res, args.lgr)
        r = pcsx.run(exe=exe, pcdrv=pcdrv, **run_args)
    result[key] = (r, workdir, name)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", default=os.path.join(PSX, "build"))
    ap.add_argument("--levels", default="warmup,internal,external")
    ap.add_argument("--external", default=os.path.join(REPO, "build", "Lev", "pa27le01.lev"))
    ap.add_argument("--res", default=os.environ.get("ELMA_RES", os.path.join(REPO, "elma.res")))
    ap.add_argument("--lgr", default=os.environ.get("ELMA_LGR", os.path.join(REPO, "build", "Lgr",
                                                                           "Default_old.lgr")))
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--timeout", type=float, default=1500)
    ap.add_argument("--gpu-only", action="store_true")
    ap.add_argument("--fps", action="store_true")
    ap.add_argument("--ram2", action="store_true",
                    help="the retail 2 MB of RAM (with --gpu-only; the default is the 8 MB mode)")
    ap.add_argument("--trace", action="store_true", help="print where the program is while a level loads")
    args = ap.parse_args()
    exe_dir = args.build if args.gpu_only else os.path.join(args.build, "gpu-compare")
    if not args.no_build and not args.gpu_only:
        build(exe_dir)
    names = []
    for n in args.levels.split(","):
        if n == "external":
            names += ["external:" + f for f in args.external.split(",") if f]
        elif n:
            names.append(n)
    result = {}
    # The external levels one after the other (their discs are made in the
    # same place), next to the others:
    def run_externals(ext):
        for n in ext:
            run_level(n, args, exe_dir, result)
    ext = [n for n in names if n.startswith("external:")]
    threads = [threading.Thread(target=run_level, args=(n, args, exe_dir, result)) for n in names if n not in ext]
    if ext:
        threads.append(threading.Thread(target=run_externals, args=(ext,)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok = True
    for key in names:
        r, workdir, name = result[key]
        cams = {}
        for line in r.output.splitlines():
            if line.startswith("elma: LGR") or line.startswith("elma: level for"):
                print("%s: %s" % (name, line))
            if line.startswith("state "):
                p = line.split()
                cams[p[1]] = tuple(int(v) for v in p[2:6])
            if line.startswith(("PASS", "FAIL", "LUA", "view ")):
                print("%s: %s" % (name, line))
        with open(os.path.join(workdir, "output.txt"), "w") as f:
            f.write(r.output)
        if r.returncode != 0 or not cams:
            ok = False
            print("FAIL %s: emulator exit %d (%s)" % (name, r.returncode, os.path.join(workdir, "output.txt")))
            for line in r.output.splitlines():
                if line.startswith("elma:   ") or "error" in line.lower():
                    print("  " + line)
            continue
        for state, cam in sorted(cams.items()):
            if args.gpu_only:
                gw, gh, gpu = read_ppm(os.path.join(workdir, state + "_gpu.ppm"))
                write_png(os.path.join(workdir, state + "_gpu.png"), gw, gh, gpu)
                print("     %s/%s: %s" % (name, state, os.path.join(workdir, state + "_gpu.png")))
                continue
            png = os.path.join(workdir, state + "_compare.png")
            frac, mean = compare(workdir, state, cam, png)
            good = frac >= 0.90
            ok = ok and good
            print("%s %s/%s: %.1f%% of the pixels match, mean difference %.1f (%s)" %
                  ("ok  " if good else "FAIL", name, state, 100 * frac, mean, png))
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
