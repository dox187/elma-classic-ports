#!/usr/bin/env python3
"""Memory test of the game on the PS1 in headless PCSX-Redux.

Plays test/mem_test.lua for each given level: boot, menus, loading the level
and some seconds of gas (with --again then also the same level once more and
the next level, from the menu after a game). Prints, for every phase, the high-water of the heap
(its extent, gaps included, and the bytes in blocks), the biggest live
allocations of operator new by calling place at that moment (resolved to
functions with addr2line), the deepest stack use, and the RAM the whole game
needed:

    total = 64 KB (BIOS) + program (code, data, BSS: up to _end of the map)
            + heap extent + stack reserve (16 KB)

The test fails if a level does not load and play, or if the total of any
phase is above --limit KB. --without FILE,... also prints for each phase
the RAM the blocks would need without those allocated in the given source
files (for example the pictures of PIC8.CPP, if they were kept in VRAM
instead): BIOS, program and stack as above, plus the bytes in blocks at the
frame of the phase with the most of them, less those files' blocks; gaps in
the heap are not counted there.

    python3 test/mem_test.py [--levels 0,15,25|all] [--external FILE.lev[,FILE.lev...]]
        [--limit KB] [--jobs N] [--play FRAMES] [--again] [--sites N] [--build DIR]
        [--without FILE,...] [--res elma.res] [--lgr default.lgr] [--quiet]

The levels are the internal ones, from 0 (Warm Up); --external plays the
given .lev file from a two-track disc as the only external level. The loaded
level's stamp must match the requested file. The game files default to
$ELMA_RES / $ELMA_LGR as in test/core_boot_test.py (only linked, never
written). Run it with the Bash tool's run_in_background option: a level
takes one to two minutes; --jobs runs several emulators at once.
"""
import argparse
import concurrent.futures
import os
import re
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PSX = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PSX))
sys.path.insert(0, HERE)
import pcsx  # noqa: E402
from mc_test import make_card  # noqa: E402
from res_layout import resource_layout  # noqa: E402
from core_boot_test import link, make_pcdrv_dir  # noqa: E402

KB = 1024
BIOS = 64 * KB
STACK = 16 * KB  # STACK_SIZE of src/psx_platform.cpp
PHASES = ("boot", "menu", "load", "play", "again", "next")


def program_size(map_file):
    """Bytes from the load address (0x80010000) to _end."""
    syms = pcsx.read_symbols(map_file)
    return syms["_end"] - 0x80010000


def addr2line(elf, addresses):
    tool = shutil.which("mipsel-none-elf-addr2line") or os.path.join(
        os.path.expanduser("~/.local/share/elma-psx/gcc/bin"), "mipsel-none-elf-addr2line")
    if not addresses or not os.path.exists(tool):
        return {}
    out = subprocess.run([tool, "-f", "-C", "-s", "-e", elf] + ["%x" % (a - 8) for a in addresses],
                         capture_output=True, text=True).stdout.splitlines()
    names = {}
    for i, a in enumerate(addresses):
        func, where = out[2 * i], out[2 * i + 1]
        func = re.sub(r"\(.*", "", func)
        where = where.split(" ")[0]
        names[a] = ("%s (%s)" % (func, where), where.split(":")[0])
    return names


def run_level(args, label, lua_args, source, disc=False):
    workdir = os.path.join(args.out, label)
    os.makedirs(workdir, exist_ok=True)
    image = "elma-cd" if disc else "elma"
    card = os.path.join(workdir, "card.mcd")
    with open(card, "wb") as f:
        f.write(make_card("fresh"))
    run_args = {"iso": source} if disc else {
        "exe": os.path.join(args.build, image + ".exe"), "pcdrv": source}
    result = pcsx.run(map_file=os.path.join(args.build, image + ".map"),
                      lua=os.path.join(HERE, "mem_test.lua"), ram8=not args.ram2, timeout=args.timeout,
                      workdir=workdir, args=lua_args,
                      extra_flags=["-memcard1", os.path.abspath(card)], **run_args)
    with open(os.path.join(workdir, "output.txt"), "w") as f:
        f.write(result.output)
    return label, result, image


def external_header(path):
    """Read the stamp and required LGR without modifying the game file."""
    with open(path, "rb") as f:
        header = f.read(110)
    if header[:5] not in (b"POT06", b"POT14"):
        raise ValueError("unsupported external level: " + path)
    modern = header[:5] == b"POT14"
    stamp = struct.unpack_from("<I", header, 7 if modern else 5)[0]
    lgr = header[94:110].split(b"\0", 1)[0].upper() if modern else b"DEFAULT"
    return stamp, lgr


def external_disc(args, level, work):
    """Build a private disc so parallel external runs cannot replace it."""
    levels = os.path.join(work, "levels")
    os.makedirs(levels, exist_ok=True)
    for name in os.listdir(levels):
        os.remove(os.path.join(levels, name))
    link(level, os.path.join(levels, os.path.basename(level).upper()))
    disc = os.path.join(work, "disc")
    command = [sys.executable, os.path.join(PSX, "tools", "mkdisc.py"),
               "--exe", os.path.join(args.build, "elma-cd.exe"),
               "--res", args.res, "--lgr", args.lgr, "--lev-dir", levels,
               "--out-dir", disc, "--name", "elma"]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    return os.path.join(disc, "elma.cue")


def parse(output):
    phases, sites, stack, status, errors, ram_files = {}, {}, None, None, [], None
    live = {}
    for line in output.splitlines():
        if line.startswith("MEM "):
            f = line.split()
            values = dict(kv.split("=", 1) for kv in f[2:])
            phases[f[1]] = values
        elif line.startswith("SITE "):
            f = line.split()
            sites.setdefault(f[1], []).append((int(f[2], 16), int(f[3]), int(f[4])))
        elif line.startswith("LIVE "):
            f = line.split()
            live[f[1]] = {"live_" + k: v for k, v in (kv.split("=", 1) for kv in f[2:])}
        elif line.startswith("STACK used"):
            stack = int(line.split()[2])
        elif line.startswith("RAMFILES "):
            ram_files = int(line.split()[1])
        elif line.startswith(("PASS", "FAIL")):
            status = line
        elif "out of memory" in line or "internal error" in line:
            errors.append(line)
    for name, values in live.items():
        phases.setdefault(name, {}).update(values)
    return phases, sites, stack, status, errors, ram_files


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--levels", default="0", help="internal levels, e.g. 0,15,33 or all")
    parser.add_argument("--external", help="comma-separated .lev files, each on its own disc")
    parser.add_argument("--limit", type=int, default=8192, help="KB of RAM a phase may need")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--play", type=int, default=600, help="frames of gas")
    parser.add_argument("--idle", action="store_true",
                        help="hold the brake; require game frames to keep advancing throughout")
    parser.add_argument("--enable-sound-after", action="store_true",
                        help="start with sound off, enable it before --again, verify lazy initialization")
    parser.add_argument("--force-reload", action="store_true",
                        help="force and verify a full level reload before --again")
    parser.add_argument("--again", action="store_true",
                        help="then leave the game, play the level again and then the next one")
    parser.add_argument("--sites", type=int, default=12, help="calling places shown per phase")
    parser.add_argument("--without", default="",
                        help="source files (e.g. PIC8.CPP,KISKEP.CPP) whose live operator new blocks "
                        "are also subtracted from each total, as if they were not in RAM")
    parser.add_argument("--build", default=os.environ.get("BUILD", os.path.join(PSX, "build")))
    parser.add_argument("--res", default=os.environ.get("ELMA_RES", os.path.join(REPO, "elma.res")))
    parser.add_argument("--lgr", default=os.environ.get(
        "ELMA_LGR", os.path.join(REPO, "build", "Lgr", "Default_old.lgr")))
    parser.add_argument("--timeout", type=float, default=1200)
    parser.add_argument("--quiet", action="store_true", help="one line per level")
    parser.add_argument("--ram2", action="store_true", help="2 MB of RAM (the default is the 8 MB mode)")
    args = parser.parse_args()
    if args.enable_sound_after and not args.again:
        parser.error("--enable-sound-after requires --again")
    if args.force_reload and not args.again:
        parser.error("--force-reload requires --again")
    args.out = os.path.join(args.build, "mem-test")

    for path in (args.res, args.lgr):
        if not os.path.isfile(path):
            print("FAIL: game file not found: %s" % path)
            return 2
    layout = resource_layout(args.res)
    runs = []
    if args.levels:
        levels = range(layout["internal_count"]) if args.levels == "all" else [
            int(x) for x in args.levels.split(",")]
        if any(n < 0 or n >= layout["internal_count"] for n in levels):
            parser.error("internal level index is outside this resource's playable levels")
        pcdrv = os.path.join(args.out, "pcdrv")
        make_pcdrv_dir(pcdrv, args.res, args.lgr)
        for n in levels:
            lua_args = {"level": n, "play": args.play, "idle": int(args.idle),
                        "sound_after": int(args.enable_sound_after),
                        "force_reload": int(args.force_reload),
                        "path": ",".join(layout["internal_steps"])}
            if args.again:
                lua_args["after"] = "again,next" if n + 1 < layout["internal_count"] else "again"
            runs.append(("level%02d" % n, lua_args, pcdrv, False))
    if args.external:
        # PCdrv has no directory enumeration. A real disc both exercises the
        # retail file backend and makes the menu select this external file.
        for level in args.external.split(","):
            stamp, lgr = external_header(level)
            label = "external-" + os.path.splitext(os.path.basename(level))[0].lower()
            lua_args = {"external": 1, "play": args.play, "stamp": stamp,
                        "dialogs": int(lgr not in (b"", b"DEFAULT")), "idle": int(args.idle)}
            lua_args["sound_after"] = int(args.enable_sound_after)
            lua_args["force_reload"] = int(args.force_reload)
            lua_args["path"] = ",".join(layout["external_steps"])
            if args.again:
                lua_args["after"] = "again"
            cue = external_disc(args, level, os.path.join(args.out, label))
            runs.append((label, lua_args, cue, True))

    if not runs:
        parser.error("select at least one internal or external level")
    programs = {}
    for image in sorted({"elma-cd" if r[3] else "elma" for r in runs}):
        map_file = os.path.join(args.build, image + ".map")
        if not os.path.isfile(map_file):
            print("FAIL: %s not built (make -C console/psx)" % map_file)
            return 2
        programs[image] = program_size(map_file)
    without = {f.strip().upper() for f in args.without.split(",") if f.strip()}
    print("program (code, data, BSS): %s; BIOS %d KB, stack reserve %d KB, limit %d KB" % (
        ", ".join("%s %d KB" % (image, size // KB) for image, size in programs.items()),
        BIOS // KB, STACK // KB, args.limit))
    if without:
        print("'without': the totals less the live blocks of %s" % ", ".join(sorted(without)))
    failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(4, args.jobs))) as pool:
        futures = [pool.submit(run_level, args, label, lua_args, source, disc)
                   for label, lua_args, source, disc in runs]
        for future in futures:
            label, result, image = future.result()
            program = programs[image]
            elf = os.path.join(args.build, image + ".elf")
            phases, sites, stack, status, errors, ram_files = parse(result.output)
            names = addr2line(elf, sorted({s[0] for l in sites.values() for s in l}))
            peak = 0
            parts, parts_without = [], []
            for p in PHASES:
                if p not in phases or "extent_max" not in phases[p]:
                    continue
                extent = int(phases[p]["extent_max"])
                total = BIOS + program + extent + STACK
                peak = max(peak, total)
                parts.append("%s %d" % (p, total // KB))
                if without:
                    # The bytes in blocks at the frame of the calling places
                    # (gaps not counted), less those of the given files; each
                    # block also has 16 bytes of headers:
                    less = sum(size + 16 * blocks for caller, size, blocks in sites.get(p, [])
                               if names.get(caller, ("", ""))[1].upper() in without)
                    rest = BIOS + program + STACK + int(phases[p]["sites_alloc"]) - less
                    parts_without.append("%s %d" % (p, rest // KB))
            ok = (result.returncode == 0 and status is not None and status.startswith("PASS")
                  and peak <= args.limit * KB)
            failed += not ok
            print("%s %s: total KB by phase: %s; stack %s B; RAM files %s B" % (
                "ok  " if ok else "FAIL", label, ", ".join(parts) or "-", stack, ram_files))
            if without:
                print("     %s without: %s" % (label, ", ".join(parts_without) or "-"))
            if not ok or not args.quiet:
                for line in errors:
                    print("    " + line)
                if status:
                    print("    " + status)
                if status is None:
                    print("    emulator exit code %d" % result.returncode)
            if args.quiet:
                continue
            for p in PHASES:
                if p not in phases or "extent_max" not in phases[p]:
                    continue
                v = phases[p]
                print("  %-5s heap extent %6d KB, in blocks %6d KB (max %6d KB), free in the extent %s" % (
                    p, int(v["extent_max"]) // KB, int(v["alloc_at_peak"]) // KB,
                    int(v["alloc_max"]) // KB,
                    "-" if v["free_at_peak"] == "-" else "%d KB (largest %d KB)" % (
                        int(v["free_at_peak"]) // KB, int(v["largest_free"]) // KB)))
                if "live_allocated" in v:
                    print("        end of play: used %s B, free %s B, largest malloc %s B" % (
                        v["live_allocated"], v["live_free"], v["live_largest"]))
                for caller, size, blocks in sites.get(p, [])[:args.sites]:
                    name = names.get(caller, ("%08x" % caller, ""))[0]
                    print("        %7d B %5d blocks  %s" % (size, blocks, name))
    print("PASS" if not failed else "FAIL: %d of %d runs" % (failed, len(runs)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
