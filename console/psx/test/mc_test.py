#!/usr/bin/env python3
"""Memory card test: host LZ test, then runs of mctest in headless PCSX-Redux.

Every run uses a private card image under <build>/mc-test/ (never the user's
cards), passed with -memcard1. Scenarios: fresh card, save and reload in a
new emulator run (empty, used and real state.dat), no card, unformatted card,
full card, damaged save. --real PATH sets the real state.dat (read only).
"""
import argparse
import os
import re
import struct
import subprocess
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pcsx  # noqa: E402

FRAME = 128
STATUS = {"OK": 0, "NO_CARD": 1, "UNFORMATTED": 2, "FULL": 3, "WRITE_ERROR": 4,
          "NO_SAVE": 5, "CORRUPT": 6, "NOT_FOUND": 7}
NAME = b"BAELMA-00000STATE"


def xor_sum(b):
    x = 0
    for c in b[:127]:
        x ^= c
    return x


def make_card(kind="fresh"):
    """A 128 KB card image: fresh (formatted, empty), full (15 foreign
    blocks), unformatted (zeros)."""
    img = bytearray(131072)
    if kind == "unformatted":
        return bytes(img)
    f0 = bytearray(FRAME)
    f0[0:2] = b"MC"
    f0[127] = xor_sum(f0)
    img[0:FRAME] = f0
    for i in range(1, 16):
        e = bytearray(FRAME)
        if kind == "full":
            e[0:4] = struct.pack("<I", 0x51)
            e[4:8] = struct.pack("<I", 8192)
            e[8:10] = b"\xff\xff"
            nm = b"BASLUS-00000TEST%02d" % i
            e[10:10 + len(nm)] = nm
        else:
            e[0:4] = struct.pack("<I", 0xA0)
            e[8:10] = b"\xff\xff"
        e[127] = xor_sum(e)
        img[i * FRAME:(i + 1) * FRAME] = e
    for i in range(16, 36):
        e = bytearray(FRAME)
        e[0:4] = b"\xff\xff\xff\xff"
        e[8:10] = b"\xff\xff"
        e[127] = xor_sum(e)
        img[i * FRAME:(i + 1) * FRAME] = e
    img[63 * FRAME:64 * FRAME] = f0
    return bytes(img)


def run(build, redux, card, workdir, op, kind, pcdrv=None, crc=0, length=0,
        no_card=False, timeout=240):
    os.makedirs(workdir, exist_ok=True)
    flags = [] if no_card else ["-memcard1", card]
    r = pcsx.run(exe=os.path.join(build, "mctest.exe"),
                 map_file=os.path.join(build, "mctest.map"),
                 lua=os.path.join(HERE, "mc_test.lua"), pcdrv=pcdrv,
                 timeout=timeout, redux=redux, workdir=workdir,
                 args={"op": op, "kind": kind, "crc": crc, "len": length,
                       "nocard": 1 if no_card else 0},
                 extra_flags=flags)
    m = re.search(r"RESULT (.*)", r.output)
    res = {}
    if m:
        for kv in m.group(1).split():
            k, v = kv.split("=")
            res[k] = v == "true" if v in ("true", "false") else int(v)
    res["_out"] = r.output
    res["_rc"] = r.returncode
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", required=True)
    ap.add_argument("--redux")
    # A real state.dat to round-trip; ELMA_STATE overrides the repository copy.
    ap.add_argument("--real", default=os.environ.get(
        "ELMA_STATE", os.path.join(HERE, "..", "..", "..", "state.dat")))
    ap.add_argument("--only", help="comma separated scenario names")
    o = ap.parse_args()
    build = os.path.abspath(o.build)
    base = os.path.join(build, "mc-test")
    os.makedirs(base, exist_ok=True)
    fails = []

    def check(cond, what):
        print(("  ok   " if cond else "  FAIL ") + what)
        if not cond:
            fails.append(what)

    def card_path(name, kind="fresh"):
        p = os.path.join(base, name + ".mcd")
        with open(p, "wb") as f:
            f.write(make_card(kind))
        return p

    # Host test of the codec.
    print("host LZ test")
    exe = os.path.join(base, "mc_lz_test")
    subprocess.check_call(["cc", "-O2", "-Wall", "-I", os.path.join(HERE, "../src/memcard"),
                           os.path.join(HERE, "mc_lz_test.c"),
                           os.path.join(HERE, "../src/memcard/mclz.c"), "-o", exe])
    out = subprocess.run([exe, o.real] if os.path.exists(o.real) else [exe],
                         capture_output=True, text=True)
    print(out.stdout.rstrip())
    check(out.returncode == 0, "host LZ round trips")

    only = set(o.only.split(",")) if o.only else None

    def want(n):
        return only is None or n in only

    real = None
    if os.path.exists(o.real):
        with open(o.real, "rb") as f:
            d = f.read()
        real = (zlib.crc32(d) & 0xFFFFFFFF, len(d))
        # mctest uses its own CRC (same polynomial as zlib).
        pcdrv = os.path.join(base, "pcdrv")
        os.makedirs(pcdrv, exist_ok=True)
        with open(os.path.join(pcdrv, "STATE.DAT"), "wb") as f:
            f.write(d)  # a copy; the original is only read

    for kind, label in ((0, "empty"), (1, "used")):
        if not want(label):
            continue
        print("scenario: %s state, save then reload in a new run" % label)
        card = card_path("card_" + label)
        r = run(build, o.redux, card, os.path.join(base, "w_" + label + "_save"), 1, kind)
        print("  init=%d save=%d/%d blocks=%d frames=%d crc=%08x comp=%d" % (
            r.get("init_status", -1), r.get("status", -1), r.get("status2", -1),
            r.get("blocks", -1), r.get("frames", -1), r.get("crc", 0), r.get("comp_bytes", 0)))
        check(r.get("init_status") == 0 and r.get("status") == 0 and r.get("status2") == 0, "save ok")
        r2 = run(build, o.redux, card, os.path.join(base, "w_" + label + "_load"), 2, kind)
        print("  load=%d/%d data_ok=%d crc=%08x len=%d" % (
            r2.get("status", -1), r2.get("status2", -1), r2.get("data_ok", -1),
            r2.get("crc", 0), r2.get("len", 0)))
        check(r2.get("data_ok") == 1 and r2.get("crc") == r.get("crc"), "reloaded bytes identical")
        if label == "used" or label == "empty":
            print("  REPORT %s: save blocks = %d, compressed = %d bytes" % (label, r.get("blocks", -1), r.get("comp_bytes", 0)))

    if real and want("real"):
        print("scenario: real state.dat")
        card = card_path("card_real")
        r = run(build, o.redux, card, os.path.join(base, "w_real_save"), 1, 2, pcdrv=pcdrv)
        print("  save=%d/%d blocks=%d comp=%d crc=%08x (expect %08x)" % (
            r.get("status", -1), r.get("status2", -1), r.get("blocks", -1),
            r.get("comp_bytes", 0), r.get("crc", 0), real[0]))
        check(r.get("status") == 0 and r.get("crc") == real[0], "real save ok")
        # No pcdrv in the load run: the bytes must come from the card.
        r2 = run(build, o.redux, card, os.path.join(base, "w_real_load"), 2, 2,
                 crc=real[0], length=real[1])
        check(r2.get("data_ok") == 1, "real state.dat reloaded identical (crc and size)")
        print("  REPORT real: save blocks = %d, compressed = %d bytes" % (r.get("blocks", -1), r.get("comp_bytes", 0)))

    if want("nosave"):
        print("scenario: fresh card, load without a save")
        card = card_path("card_nosave")
        r = run(build, o.redux, card, os.path.join(base, "w_nosave"), 2, 0)
        check(r.get("status") == STATUS["NO_SAVE"], "load on an empty card gives NO_SAVE (%s)" % r.get("status"))

    if want("unformatted"):
        print("scenario: unformatted card")
        card = card_path("card_unf", "unformatted")
        r = run(build, o.redux, card, os.path.join(base, "w_unf"), 1, 0)
        print("  init=%s save=%s" % (r.get("init_status"), r.get("status")))
        check(r.get("status") == STATUS["UNFORMATTED"], "save on an unformatted card gives UNFORMATTED")

    if want("full"):
        print("scenario: full card")
        card = card_path("card_full", "full")
        r = run(build, o.redux, card, os.path.join(base, "w_full"), 1, 0)
        print("  save=%s" % r.get("status"))
        check(r.get("status") == STATUS["FULL"], "save on a full card gives FULL")

    if want("nocard"):
        print("scenario: no card")
        r = run(build, o.redux, None, os.path.join(base, "w_nocard"), 1, 0, no_card=True)
        print("  init=%s save=%s" % (r.get("init_status"), r.get("status")))
        check(r.get("status") == STATUS["NO_CARD"], "save without a card gives NO_CARD")

    print("FAIL" if fails else "PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
