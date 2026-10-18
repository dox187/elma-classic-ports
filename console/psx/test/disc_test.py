#!/usr/bin/env python3
"""Host tests of tools/mkdisc.py and src/cd/iso9660.c.

  python3 disc_test.py [--real] [--build DIR] [--keep]

For several disc variants (raw single .bin, raw split, plain 2048, no
second alignment, ISO made by genisoimage) the script builds an image with
mkdisc.py from synthetic files, then

  * parses the .cue itself and checks the track layout and every sector of
    the .bin (sync, header MSF and mode, EDC, ECC P/Q) with a checker that
    is written independently of mkdisc.py (bitwise EDC, Reed-Solomon
    syndromes over the geometry of ECMA-130);
  * runs the C reader (iso_host_test) on the .bin starting from the
    track-2 start that GetTD would report, also with deliberately
    misaligned bases: PVD found, LEV listing equal to the source directory,
    every file byte-identical, error cases and a fuzz run (selftest);
  * cross-checks the ISO with isoinfo, xorriso, 7z and bsdtar when present.

--real adds the real game data (read-only inputs, see below).
Outputs go to console/psx/build/test_disc/ and are deleted at the end
unless --keep is given.
"""

import argparse
import hashlib
import os
import random
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PSX = os.path.normpath(os.path.join(HERE, ".."))
MKDISC = os.path.join(PSX, "tools", "mkdisc.py")
REPO = os.path.normpath(os.path.join(PSX, "..", ".."))
# The real game data for --real; override with ELMA_RES, ELMA_LGR and ELMA_LEV.
REAL_RES = os.environ.get("ELMA_RES", os.path.join(REPO, "elma.res"))
REAL_LGR = os.environ.get("ELMA_LGR", os.path.join(REPO, "build", "Lgr", "Default_old.lgr"))
REAL_LEV = os.environ.get("ELMA_LEV", os.path.join(REPO, "build", "Lev"))

failures = []
checks = 0


def check(cond, what):
    global checks
    checks += 1
    if not cond:
        failures.append(what)
        print("  FAIL: " + what)


def run(cmd, **kw):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=kw.pop("text", True), **kw)


# ---------------------------------------------------------------------------
# Independent EDC / ECC checker
# ---------------------------------------------------------------------------

def _reflect(v, bits):
    r = 0
    for i in range(bits):
        if v & (1 << i):
            r |= 1 << (bits - 1 - i)
    return r


def ref_edc(data):
    """Bitwise CRC-32, normal polynomial 0x8001801B, MSB first, reflected
    input and output (ECMA-130 annex A written the textbook way)."""
    crc = 0
    for byte in data:
        crc ^= _reflect(byte, 8) << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x8001801B) if crc & 0x80000000 else (crc << 1)
            crc &= 0xFFFFFFFF
    return _reflect(crc, 32)


# GF(2^8), x^8 + x^4 + x^3 + x^2 + 1, generator 2
EXP = [0] * 512
LOG = [0] * 256
_x = 1
for _i in range(255):
    EXP[_i] = _x
    LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def gmul_alpha(v, e):
    return 0 if v == 0 else EXP[(LOG[v] + e) % 255]


def codeword_ok(symbols):
    """symbols: data bytes followed by the two parity bytes. Both
    syndromes (sum, sum of alpha^(n-1-i) * c_i) must be zero."""
    n = len(symbols)
    s0 = 0
    s1 = 0
    for i, c in enumerate(symbols):
        s0 ^= c
        s1 ^= gmul_alpha(c, n - 1 - i)
    return s0 == 0 and s1 == 0


def ecc_ok(body):
    """body: sector bytes 12..2351 as a bytes object (2340 bytes). Header
    bytes must already be zeroed for Mode 2 Form 1. The ECMA-130 layout:
    1032 words of 2 bytes (24 rows x 43 columns), P parity 2 rows x 43
    words, then Q parity 2 x 26 words."""
    # P: column j (0..42), byte lane l (LSB=0/MSB=1): rows 0..23, parity in
    # rows 24 and 25 of the same column
    for j in range(43):
        for lane in range(2):
            sym = [body[2 * (43 * row + j) + lane] for row in range(24)]
            sym.append(body[2064 + 2 * j + lane])
            sym.append(body[2064 + 86 + 2 * j + lane])
            if not codeword_ok(sym):
                return "P parity column %d lane %d" % (j, lane)
    # Q: diagonal i (0..25), lane l: 43 words (44*k + 43*i) mod 1118 of the
    # data + P parity area (1118 words), parity words 2236/2 + i and +26
    for i in range(26):
        for lane in range(2):
            sym = [body[2 * ((44 * k + 43 * i) % 1118) + lane] for k in range(43)]
            sym.append(body[2236 + 2 * i + lane])
            sym.append(body[2236 + 52 + 2 * i + lane])
            if not codeword_ok(sym):
                return "Q parity diagonal %d lane %d" % (i, lane)
    return None


SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


def msf_tuple(a):
    return bytes((a // 4500, a // 75 % 60, a % 75))


def bcd(b):
    return (b >> 4) * 10 + (b & 15)


def verify_raw_sector(sec, expect_abs, expect_mode):
    """Returns an error string or None."""
    if len(sec) != 2352:
        return "bad length"
    if sec[0:12] != b"\x00" + b"\xff" * 10 + b"\x00":
        return "sync"
    m, s, f = bcd(sec[12]), bcd(sec[13]), bcd(sec[14])
    if (sec[12] & 15) > 9 or (sec[13] & 15) > 9 or (sec[14] & 15) > 9:
        return "header not BCD"
    if (m * 60 + s) * 75 + f != expect_abs:
        return "header MSF %02d:%02d:%02d != abs %d" % (m, s, f, expect_abs)
    if sec[15] != expect_mode:
        return "mode byte %d" % sec[15]
    if expect_mode == 1:
        want = ref_edc(sec[0:2064])
        if int.from_bytes(sec[2064:2068], "little") != want:
            return "EDC"
        if sec[2068:2076] != bytes(8):
            return "intermediate bytes"
        return ecc_ok(sec[12:])
    # Mode 2 Form 1
    if int.from_bytes(sec[2072:2076], "little") != ref_edc(sec[16:2072]):
        return "EDC (mode 2)"
    if sec[16:20] != sec[20:24]:
        return "subheader copies differ"
    body = bytes(4) + sec[16:]
    return ecc_ok(body)


# ---------------------------------------------------------------------------
# Cue parsing (also independent)
# ---------------------------------------------------------------------------

def msf(text):
    m, s, f = (int(x) for x in text.split(":"))
    return (m * 60 + s) * 75 + f


def parse_cue(path):
    """Returns a list of dicts: file, mode, secsize, idx0, idx1, pregap
    (positions in sectors, relative to the start of that file)."""
    d = os.path.dirname(path)
    tracks = []
    cur_file = None
    for line in open(path, newline="").read().split("\r\n"):
        line = line.strip()
        if not line:
            continue
        mm = re.match(r'FILE "([^"]+)" BINARY$', line)
        if mm:
            cur_file = os.path.join(d, mm.group(1))
            continue
        mm = re.match(r"TRACK (\d\d) (MODE\d)/(\d+)$", line)
        if mm:
            tracks.append(dict(file=cur_file, num=int(mm.group(1)), mode=mm.group(2),
                               secsize=int(mm.group(3)), idx0=None, idx1=None,
                               pregap=0))
            continue
        mm = re.match(r"INDEX (\d\d) (\d\d:\d\d:\d\d)$", line)
        if mm:
            tracks[-1]["idx" + str(int(mm.group(1)))] = msf(mm.group(2))
            continue
        mm = re.match(r"PREGAP (\d\d:\d\d:\d\d)$", line)
        if mm:
            tracks[-1]["pregap"] = msf(mm.group(1))
            continue
        raise ValueError("unparsed cue line: %r" % line)
    return tracks


def layout(tracks):
    """Disc LBA of INDEX 01 of every track (like an emulator computes it)
    and the first LBA stored in each track's file."""
    lba = 0
    out = []
    prev_file = None
    for t in tracks:
        size = os.path.getsize(t["file"])
        nsec = size // t["secsize"]
        if t["file"] == prev_file:
            file_start = lba_of_file_start
        else:
            file_start = lba + t["pregap"]
            lba_of_file_start = file_start
            prev_file = t["file"]
        out.append(dict(t, lba1=file_start + t["idx1"],
                        lba0=None if t["idx0"] is None else file_start + t["idx0"],
                        file_start=file_start, nsec=nsec))
        lba = file_start + nsec
    return out


def getTD_base(lba1):
    """What a PS1 sees: absolute MSF of INDEX 01 rounded down to seconds,
    converted back to an LBA."""
    absolute = lba1 + 150
    return absolute - absolute % 75 - 150


# ---------------------------------------------------------------------------
# Synthetic content
# ---------------------------------------------------------------------------

def make_sources(root, seed=1):
    rnd = random.Random(seed)
    src = os.path.join(root, "src")
    shutil.rmtree(src, ignore_errors=True)
    os.makedirs(os.path.join(src, "Lev"))
    files = {}

    def blob(n):
        return bytes(rnd.getrandbits(8) for _ in range(n))

    res = os.path.join(src, "elma.res")
    open(res, "wb").write(blob(300000))
    lgr = os.path.join(src, "Default.lgr")
    open(lgr, "wb").write(blob(70001))
    files["ELMA.RES"] = open(res, "rb").read()
    files["DEFAULT.LGR"] = open(lgr, "rb").read()
    sizes = [0, 1, 2047, 2048, 2049, 4096, 4097, 65536 + 5]
    # names: many files so that the directory spans several sectors; mixed
    # case, to be upper-cased
    for i in range(130):
        name = "pa26%03d.lev" % i if i % 2 else "QWQUU%03d.LEV" % i
        n = sizes[i % len(sizes)] if i < 16 else rnd.randrange(1, 9000)
        data = blob(n)
        open(os.path.join(src, "Lev", name), "wb").write(data)
        files["LEV/" + name.upper()] = data
    # names that must be skipped
    for bad in ("toolongname.lev", "x y.lev", "ab.cd.lev", "ünï.lev"):
        open(os.path.join(src, "Lev", bad), "wb").write(b"bad")
    open(os.path.join(src, "Lev", "notalevel.txt"), "wb").write(b"not lev")
    # extra directory with a nested one
    extra = os.path.join(src, "extra")
    os.makedirs(os.path.join(extra, "sub"))
    open(os.path.join(extra, "readme.txt"), "wb").write(b"hello\n")
    open(os.path.join(extra, "sub", "deep.dat"), "wb").write(blob(5000))
    files["README.TXT"] = b"hello\n"
    files["SUB/DEEP.DAT"] = open(os.path.join(extra, "sub", "deep.dat"), "rb").read()
    return dict(res=res, lgr=lgr, lev=os.path.join(src, "Lev"), extra=extra,
                files=files)


def tree_of(directory):
    out = {}
    for base, _, names in os.walk(directory):
        for n in names:
            p = os.path.join(base, n)
            out[os.path.relpath(p, directory).replace(os.sep, "/")] = open(p, "rb").read()
    return out


# ---------------------------------------------------------------------------
# One disc variant
# ---------------------------------------------------------------------------

def c_reader(exe, f, secsize, dataoff, first_lba, base, *cmd):
    return run([exe, f, str(secsize), str(dataoff), str(first_lba), str(base)] + list(cmd))


def check_disc(name, outdir, expected, exe,
               selftest=False, check_all_sectors=True, aligned=True, t1_edc=True):
    print("== %s" % name)
    cue = os.path.join(outdir, "elma.cue")
    tracks = layout(parse_cue(cue))
    check(len(tracks) == 2, "two tracks in the cue")
    t1, t2 = tracks
    single = t2["file"] == t1["file"]
    check(t1["mode"] == "MODE2" and t1["secsize"] == 2352 and t1["lba1"] == 0,
          "track 1 is MODE2/2352 at LBA 0")
    check(t2["mode"] == "MODE1", "track 2 is MODE1")
    if single:
        t1_sectors = t2["lba0"]
        pregap = t2["lba1"] - t2["lba0"]
        stored_first = t2["lba0"]                 # LBA of the first stored sector
        stored_count = t2["nsec"] - t1_sectors    # pregap + ISO sectors
        iso_sectors = stored_count - pregap
    else:
        t1_sectors = t1["nsec"]
        pregap = t2["pregap"]
        stored_first = t2["lba1"]
        stored_count = t2["nsec"]
        iso_sectors = stored_count
    check(pregap >= 150, "pregap >= 150 sectors (%d)" % pregap)
    if aligned:
        check(pregap < 225, "aligned pregap stays below 225")
        check((t2["lba1"] + 150) % 75 == 0, "INDEX 01 of track 2 is on a second boundary")
    check(t2["lba1"] == t1_sectors + pregap, "track 2 starts after track 1 + pregap")
    print("   track 2 at LBA %d (abs %d), pregap %d, %d ISO sectors"
          % (t2["lba1"], t2["lba1"] + 150, pregap, iso_sectors))

    # ---- sector level check
    if check_all_sectors:
        with open(t1["file"], "rb") as f:
            bad = None
            for i in range(t1_sectors):
                sec = f.read(2352)
                if t1_edc:
                    err = verify_raw_sector(sec, i + 150, 2)
                else:  # mkpsxiso's own sectors: only sync, address and mode
                    err = None
                    if sec[0:12] != SYNC or sec[15] != 2:
                        err = "sync/mode"
                    elif bytes(bcd(x) for x in sec[12:15]) != msf_tuple(i + 150):
                        err = "address"
                if err:
                    bad = "track 1 sector %d: %s" % (i, err)
                    break
            check(bad is None, "track 1 sectors (%d): %s" % (t1_sectors, bad or "ok"))
        if t2["secsize"] == 2352:
            with open(t2["file"], "rb") as f:
                if single:
                    f.seek(t1_sectors * 2352)
                bad = None
                last = None
                for i in range(stored_count):
                    lba = stored_first + i
                    last = f.read(2352)
                    err = verify_raw_sector(last, lba + 150, 1)
                    if err:
                        bad = "sector LBA %d: %s" % (lba, err)
                        break
                check(bad is None, "all %d track 2 sectors incl. pregap (EDC, ECC, header): %s"
                      % (stored_count, bad or "ok"))
            # the checker must notice damage anywhere in a sector
            lba = stored_first + stored_count - 1
            for off in (3, 14, 15, 20, 2060, 2066, 2070, 2100, 2300, 2340):
                d = bytearray(last)
                d[off] ^= 0x10
                check(verify_raw_sector(bytes(d), lba + 150, 1) is not None,
                      "checker detects a flipped bit at offset %d" % off)

    # ---- C reader on the .bin
    if t2["secsize"] == 2352:
        f, secsize, dataoff = t2["file"], 2352, 16
        first_lba = 0 if t2["file"] == t1["file"] else t2["file_start"]
    else:
        f, secsize, dataoff = t2["file"], 2048, 0
        first_lba = t2["file_start"]
    start = t2["lba1"]
    td = getTD_base(start)
    r = c_reader(exe, f, secsize, dataoff, first_lba, td, "info")
    mo = re.match(r"mount 0 base (\d+) volume (\d+) root (\d+)", r.stdout)
    check(mo is not None and int(mo.group(1)) == start,
          "mount from the GetTD base finds track 2 start %d: %s" % (start, r.stdout.strip()))
    for k in (0, 1, 2, 37, 74):
        r = c_reader(exe, f, secsize, dataoff, first_lba, start - k, "info")
        mo = re.match(r"mount 0 base (\d+)", r.stdout)
        check(mo is not None and int(mo.group(1)) == start,
              "mount with the base %d sectors early" % k)
    r = c_reader(exe, f, secsize, dataoff, first_lba, start + 1, "info")
    check(not r.stdout.startswith("mount 0"), "mount fails when the base is after the start")

    # listing and extraction
    r = c_reader(exe, f, secsize, dataoff, first_lba, td, "list", "LEV")
    listing = {}
    for line in r.stdout.splitlines():
        n, size, flags, lba = line.split()
        listing[n] = int(size)
    want = {k[4:]: len(v) for k, v in expected.items() if k.startswith("LEV/")}
    check(listing == want, "LEV listing equals the source (%d entries, got %d)"
          % (len(want), len(listing)))
    r = c_reader(exe, f, secsize, dataoff, first_lba, td, "list", "/")
    root = {l.split()[0] for l in r.stdout.splitlines()}
    want_root = {k.split("/")[0] for k in expected}
    check(root == want_root, "root listing %s" % sorted(root))
    out = os.path.join(outdir, "extracted")
    shutil.rmtree(out, ignore_errors=True)
    r = c_reader(exe, f, secsize, dataoff, first_lba, td, "extract", out)
    check(r.returncode == 0, "extract ran: %s" % r.stdout.strip()[:200])
    got = tree_of(out)
    check(set(got) == set(expected), "extracted file set equals the source "
          "(missing %s, extra %s)" % (sorted(set(expected) - set(got))[:3],
                                      sorted(set(got) - set(expected))[:3]))
    diff = [k for k in expected if got.get(k) != expected[k]]
    check(not diff, "every file's bytes equal the source (%d files, diff %s)"
          % (len(expected), diff[:3]))
    shutil.rmtree(out, ignore_errors=True)
    if selftest:
        r = c_reader(exe, f, secsize, dataoff, first_lba, td, "selftest")
        check(r.returncode == 0 and "selftest OK" in r.stdout, "selftest: " + r.stdout.strip()[-300:])
    return dict(tracks=tracks, f=f, secsize=secsize, dataoff=dataoff, first_lba=first_lba)


def extract_iso_from_disc(info, out_iso):
    """Strip track 2 down to its 2048-byte user data."""
    t2 = info["tracks"][1]
    with open(info["f"], "rb") as src, open(out_iso, "wb") as dst:
        src.seek((t2["lba1"] - info["first_lba"]) * info["secsize"])
        n = (os.path.getsize(info["f"]) // info["secsize"]) - (t2["lba1"] - info["first_lba"])
        for _ in range(n):
            sec = src.read(info["secsize"])
            dst.write(sec[info["dataoff"]:info["dataoff"] + 2048])


def cross_check_tools(iso, expected, work):
    print("== cross-check of the ISO with standard tools")
    names_lev = sorted(k[4:] for k in expected if k.startswith("LEV/"))
    if shutil.which("isoinfo"):
        r = run(["isoinfo", "-l", "-i", iso])
        lev = sorted(re.findall(r"\s(\S+\.LEV);1", r.stdout))
        check(lev == names_lev, "isoinfo lists the same LEV files")
        check("ELMA.RES;1" in r.stdout and "DEFAULT.LGR;1" in r.stdout, "isoinfo root files")
        r = run(["isoinfo", "-d", "-i", iso])
        check("ISO 9660" in r.stdout and "Logical block size is: 2048" in r.stdout, "isoinfo -d")
        # extract one file with isoinfo and compare
        r = run(["isoinfo", "-x", "/LEV/%s;1" % names_lev[5], "-i", iso], text=False)
        check(r.stdout == expected["LEV/" + names_lev[5]], "isoinfo -x file bytes")
    else:
        print("   isoinfo not installed")
    if shutil.which("xorriso"):
        r = run(["xorriso", "-indev", iso, "-find", "/", "-type", "f"])
        found = [l for l in r.stdout.splitlines() if l.startswith("'/")]
        check(len(found) == len(expected), "xorriso finds %d files (got %d)"
              % (len(expected), len(found)))
        r = run(["xorriso", "-indev", iso, "-check_media", "--"])
        check("good" in r.stdout and "bad" not in r.stdout.replace("Media checks", ""),
              "xorriso check_media")
    else:
        print("   xorriso not installed")
    if shutil.which("bsdtar"):
        d = os.path.join(work, "bsdtar_out")
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        r = run(["bsdtar", "-xf", iso, "-C", d])
        got = tree_of(d)
        # libarchive may append ";1" nowhere (strips); accept both
        got = {re.sub(r";1$", "", k): v for k, v in got.items()}
        got = {k.upper(): v for k, v in got.items()}
        check(got == {k.upper(): v for k, v in expected.items()}, "bsdtar extracts identical files")
        shutil.rmtree(d, ignore_errors=True)
    if shutil.which("7z"):
        d = os.path.join(work, "7z_out")
        shutil.rmtree(d, ignore_errors=True)
        r = run(["7z", "x", "-y", "-o" + d, iso])
        got = {k.upper(): v for k, v in tree_of(d).items()}
        check(got == {k.upper(): v for k, v in expected.items()}, "7z extracts identical files")
        shutil.rmtree(d, ignore_errors=True)


def build_disc(outdir, src, extra_args, expect_ok=True, env_extra=None):
    shutil.rmtree(outdir, ignore_errors=True)
    env = dict(os.environ, SOURCE_DATE_EPOCH="1000000000")
    cmd = [sys.executable, MKDISC, "--out-dir", outdir] + extra_args
    r = run(cmd, env=env)
    if expect_ok and r.returncode != 0:
        print(r.stdout)
        check(False, "mkdisc failed: " + " ".join(cmd))
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true", help="also test the real game data")
    ap.add_argument("--build", default=os.path.join(PSX, "build", "test_disc"))
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--skip-sector-check", action="store_true",
                    help="do not verify every sector's EDC/ECC (slow)")
    args = ap.parse_args()
    work = os.path.abspath(args.build)
    os.makedirs(work, exist_ok=True)

    exe = os.path.join(work, "iso_host_test")
    cc = shutil.which("gcc") or shutil.which("cc")
    r = run([cc, "-std=c99", "-D_POSIX_C_SOURCE=200809L", "-O1", "-g", "-Wall", "-Wextra",
             "-Werror", "-pedantic", os.path.join(HERE, "iso_host_test.c"),
             os.path.join(PSX, "src", "cd", "iso9660.c"), "-o", exe])
    check(r.returncode == 0, "iso_host_test builds warning-free: " + r.stdout)
    if r.returncode:
        return 1

    S = make_sources(work)
    exp = S["files"]
    allsec = not args.skip_sector_check
    dummy = ["--dummy-track1", "333", "--res", S["res"], "--lgr", S["lgr"], "--lev-dir", S["lev"],
             "--extra-dir", S["extra"]]

    # 1. raw MODE1/2352, one .bin
    d = os.path.join(work, "raw")
    r = build_disc(d, S, dummy)
    check("skipped" in r.stdout and r.stdout.count("skipped") >= 4,
          "non-8.3 names reported as skipped")
    info = check_disc("raw MODE1/2352, single .bin", d, exp, exe, selftest=True,
                      check_all_sectors=allsec)
    iso = os.path.join(work, "t2.iso")
    extract_iso_from_disc(info, iso)
    cross_check_tools(iso, exp, work)
    # the writer's own --write-iso must equal the stripped track 2
    d2 = os.path.join(work, "raw_iso")
    build_disc(d2, S, dummy + ["--write-iso", os.path.join(work, "own.iso")])
    check(open(iso, "rb").read() == open(os.path.join(work, "own.iso"), "rb").read(),
          "track 2 user data equals the plain ISO")
    shutil.rmtree(d2)

    # 2. raw, split files
    d = os.path.join(work, "split")
    build_disc(d, S, dummy + ["--split"])
    check_disc("raw MODE1/2352, split files", d, exp, exe, check_all_sectors=allsec)
    shutil.rmtree(d)

    # 3. plain 2048
    d = os.path.join(work, "p2048")
    build_disc(d, S, dummy + ["--track2-format", "2048"])
    check_disc("plain MODE1/2048", d, exp, exe, check_all_sectors=False)
    shutil.rmtree(d)

    # 4. no alignment: track 2 starts mid-second, GetTD rounds down
    for n1 in (333, 150, 301):
        d = os.path.join(work, "noalign")
        build_disc(d, S, ["--dummy-track1", str(n1), "--res", S["res"], "--lgr", S["lgr"],
                          "--lev-dir", S["lev"], "--extra-dir", S["extra"], "--no-align"])
        t = layout(parse_cue(os.path.join(d, "elma.cue")))
        print("   (no-align, track 1 = %d sectors: start %d, GetTD base %d)"
              % (n1, t[1]["lba1"], getTD_base(t[1]["lba1"])))
        check_disc("no alignment, track 1 = %d sectors" % n1, d, exp, exe,
                   check_all_sectors=False, aligned=False)
        shutil.rmtree(d)

    # 5. ISO made by genisoimage / xorriso, fed as --track2-iso
    for tool in ("genisoimage", "xorriso"):
        if not shutil.which(tool):
            print("   %s not installed, skipped" % tool)
            continue
        stage = os.path.join(work, "stage")
        shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(os.path.join(stage, "LEV"))
        shutil.copy(S["res"], os.path.join(stage, "ELMA.RES"))
        shutil.copy(S["lgr"], os.path.join(stage, "DEFAULT.LGR"))
        for k, v in exp.items():
            if k.startswith("LEV/"):
                open(os.path.join(stage, k), "wb").write(v)
        std = os.path.join(work, "std.iso")
        if tool == "genisoimage":
            cmd = [tool, "-quiet", "-iso-level", "1", "-o", std, stage]
        else:
            cmd = [tool, "-as", "mkisofs", "-quiet", "-iso-level", "1", "-o", std, stage]
        r = run(cmd)
        check(r.returncode == 0, "%s built the ISO" % tool)
        d = os.path.join(work, "std")
        build_disc(d, S, ["--dummy-track1", "400", "--track2-iso", std])
        want = {k: v for k, v in exp.items() if k in ("ELMA.RES", "DEFAULT.LGR") or k.startswith("LEV/")}
        check_disc("--track2-iso from %s" % tool, d, want, exe, check_all_sectors=False)
        shutil.rmtree(d)
        shutil.rmtree(stage)
        os.remove(std)

    # 6. the reader on track 1 (Mode 2 Form 1, data at offset 24): track 1
    #    of a mkpsxiso image holds a real ISO; skip when mkpsxiso is missing
    mk = os.path.expanduser("~/.local/share/elma-psx/mkpsxiso/bin/mkpsxiso")
    hello = os.path.join(PSX, "build", "hello.exe")
    if os.path.exists(mk) and os.path.exists(hello):
        d = os.path.join(work, "mk")
        build_disc(d, S, ["--exe", hello, "--res", S["res"], "--lgr", S["lgr"],
                          "--lev-dir", S["lev"]])
        print("== mkpsxiso track 1 + own track 2")
        info = check_disc("track 1 by mkpsxiso", d, {k: v for k, v in exp.items()
                          if k in ("ELMA.RES", "DEFAULT.LGR") or k.startswith("LEV/")},
                          exe, check_all_sectors=allsec, t1_edc=False)
        t1_file = os.path.join(d, "elma.bin")
        # mkpsxiso is a third-party encoder: its Form 1 sectors (the
        # file area, from sector 16) must pass the EDC/ECC checker too
        with open(t1_file, "rb") as fh:
            n1 = info["tracks"][1]["lba0"]
            bad = None
            for i in range(n1):
                sec = fh.read(2352)
                if i >= 16 and verify_raw_sector(sec, i + 150, 2):
                    bad = "mkpsxiso sector %d: %s" % (i, verify_raw_sector(sec, i + 150, 2))
                    break
            check(bad is None, "mkpsxiso track 1 file sectors pass the independent checker: %s"
                  % (bad or "ok"))
        r = c_reader(exe, t1_file, 2352, 24, 0, 0, "list", "/")
        names = {l.split()[0] for l in r.stdout.splitlines()}
        check({"SYSTEM.CNF", "ELMA.EXE"} <= names,
              "reader mounts track 1 (MODE2/2352, offset 24): %s" % sorted(names))
        cnf = c_reader(exe, t1_file, 2352, 24, 0, 0, "extract", os.path.join(work, "t1x"))
        cnf_text = open(os.path.join(work, "t1x", "SYSTEM.CNF"), "rb").read()
        check(cnf_text == b"BOOT=cdrom:\\ELMA.EXE;1\r\nTCB=4\r\nEVENT=10\r\nSTACK=801FFFF0\r\n",
              "SYSTEM.CNF content")
        check(open(os.path.join(work, "t1x", "ELMA.EXE"), "rb").read() == open(hello, "rb").read(),
              "ELMA.EXE equals the PS-EXE")
        shutil.rmtree(os.path.join(work, "t1x"))
        shutil.rmtree(d)
    else:
        print("   mkpsxiso/hello.exe not found: skipped")

    # 7. error handling of the tool
    print("== mkdisc error cases")
    d = os.path.join(work, "err")
    r = build_disc(d, S, ["--dummy-track1", "10"], expect_ok=False)
    check(r.returncode != 0, "empty track 2 is refused")
    r = build_disc(d, S, ["--res", S["res"]], expect_ok=False)
    check(r.returncode != 0, "missing track 1 is refused")
    bad = os.path.join(work, "bad.bin")
    open(bad, "wb").write(b"x" * 1000)
    r = build_disc(d, S, ["--track1-bin", bad, "--res", S["res"]], expect_ok=False)
    check(r.returncode != 0, "track 1 of the wrong size is refused")
    r = build_disc(d, S, ["--dummy-track1", "10", "--res", S["res"], "--pregap", "100"], expect_ok=False)
    check(r.returncode != 0, "pregap below 150 is refused")
    open(bad, "wb").write(b"\x00" * 4096)
    r = build_disc(d, S, ["--dummy-track1", "10", "--track2-iso", bad], expect_ok=False)
    check(r.returncode != 0, "--track2-iso without CD001 is refused")
    r = run([sys.executable, MKDISC, "--help"])
    check(r.returncode == 0 and "pregap" in r.stdout.lower() and "genisoimage" in r.stdout,
          "--help documents the tool")
    shutil.rmtree(d, ignore_errors=True)
    os.remove(bad)

    # 8. real game data
    if args.real:
        for p in (REAL_RES, REAL_LGR, REAL_LEV):
            if not os.path.exists(p):
                print("   real data missing: %s" % p)
                break
        else:
            levs = sorted(n for n in os.listdir(REAL_LEV) if n.lower().endswith(".lev"))
            real = {"ELMA.RES": open(REAL_RES, "rb").read(),
                    "DEFAULT.LGR": open(REAL_LGR, "rb").read()}
            for n in levs:
                real["LEV/" + n.upper()] = open(os.path.join(REAL_LEV, n), "rb").read()
            d = os.path.join(work, "real")
            build_disc(d, S, ["--dummy-track1", "1000", "--res", REAL_RES, "--lgr", REAL_LGR,
                              "--lev-dir", REAL_LEV])
            info = check_disc("real game data (%d levels)" % len(levs), d, real, exe,
                              selftest=True, check_all_sectors=allsec)
            iso = os.path.join(work, "real.iso")
            extract_iso_from_disc(info, iso)
            cross_check_tools(iso, real, work)
            os.remove(iso)
            shutil.rmtree(d)
            real = None

    print("\n%d checks, %d failures" % (checks, len(failures)))
    for f in failures:
        print("  - " + f)
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
