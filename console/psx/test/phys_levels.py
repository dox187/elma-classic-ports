#!/usr/bin/env python3
"""Writes levels as text for the host physics test (test/phys_host.cpp):
the internal levels of an elma.res and any .lev files, with the exact
numbers of the files.

    phys_levels.py ELMA_RES OUT_DIR [FILE.lev ...]

OUT_DIR/levNN.txt for internal level NN (from 0), OUT_DIR/<name>.txt for a
.lev file. Each file: the number of polygons and objects; each polygon
(grass flag, point count, then the points with y pointing down as in the
level file); each object (type, x, y pointing up, gravity, animation), in
the order of the file. The first line of the polygons is preceded by a
comment line with the name of the level.

elma.res is only read. The output is generated from the user's game data
and must not be committed.
"""

import os
import struct
import sys

T_FLOWER, T_APPLE, T_KILLER, T_START = 1, 2, 3, 4

# The order of the internal levels in the game (TOPOL.CPP, Levelnevek):
INTERNAL_LEVELS = [
    "a01.leb", "a02.leb", "a03.leb", "a04.leb", "a05.leb",
    "a06.leb", "a07.leb", "ujtag.leb", "a08.leb", "a09.leb", "ujgrav.leb",
    "a10.leb", "a11.leb", "a12.leb", "a13.leb", "a14.leb", "a15.leb",
    "a16.leb", "a17.leb", "ujupdown.leb", "a18.leb", "a19.leb", "a20.leb",
    "a21.leb", "a22.leb", "a23.leb", "a24.leb", "a25.leb",
    "a26.leb", "ujkomb.leb", "a27.leb", "ujtolcs.leb", "a28.leb",
    "ujzuhan.leb", "a29.leb", "a30.leb",
    "a31.leb", "a32.leb", "ujvissza.leb", "a33.leb", "a34.leb", "a35.leb",
    "a36.leb", "a37.leb", "ujcsab.leb", "Mate.leb", "a38.leb",
    "ujdownhi.leb", "ujcsomo.leb", "a39.leb", "a40.leb",
    "a41.leb", "ujhook.leb", "a42.leb",
]
# The shareware version ends with this level instead of a17.leb:
SHAREWARE_LAST = "ujvege.leb"


def _s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def _decrypt(data, a, b, c):
    """The XOR stream of QOPEN.CPP, computed with 16-bit shorts."""
    out = bytearray(data)
    for i in range(len(out)):
        out[i] ^= a & 0xFF
        a = _s16(int(a - c * int(a / c)))  # C remainder, truncating
        b = _s16(b + a * c)
        a = _s16(31 * b + c)
    return bytes(out)


class Resource:
    """The files packed into elma.res (QOPEN.CPP)."""

    MAGIC = 1347839
    # The keys of the file table and whether an entry gives the start of the
    # file before its size: registered, then shareware.
    LAYOUTS = ((9982, False), (9882, True))

    def __init__(self, path):
        with open(path, "rb") as f:
            self.data = f.read()
        count = struct.unpack_from("<i", self.data, 0)[0]
        for slots in (150, 3000):
            end = 4 + slots * 24
            if len(self.data) >= end + 4 and \
                    struct.unpack_from("<i", self.data, end)[0] == self.MAGIC:
                break
        else:
            raise ValueError("%s is not an elma.res file" % path)
        for key, start_first in self.LAYOUTS:
            table = _decrypt(self.data[4:4 + slots * 24], 23, key, 3391)
            files = self._files(table, count, start_first)
            if files:
                break
        else:
            raise ValueError("%s is not an elma.res file" % path)
        self.files = files

    def _files(self, table, count, start_first):
        files = {}
        for i in range(count):
            entry = table[i * 24:(i + 1) * 24]
            name = entry[:16].split(b"\0")[0]
            a, b = struct.unpack_from("<ii", entry, 16)
            start, size = (a, b) if start_first else (b, a)
            if not name or any(c < 32 or c > 126 for c in name) or \
                    start < 0 or size < 0 or start + size > len(self.data):
                return None
            files[name.decode("latin-1").lower()] = (start, size)
        return files

    def read(self, name):
        start, size = self.files[name.lower()]
        return self.data[start:start + size]

    def __contains__(self, name):
        return name.lower() in self.files


class _Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, fmt):
        vals = struct.unpack_from("<" + fmt, self.data, self.pos)
        self.pos += struct.calcsize("<" + fmt)
        return vals if len(vals) > 1 else vals[0]

    def skip(self, n):
        self.pos += n


def parse_level(data, internal=False):
    """(name, polygons [(grass, [(x, y_down)])], objects [(t, x, y_up, g, a)])
    of a .lev file or an internal .leb level."""
    r = _Reader(data)
    head = r.take("5s")
    if internal:
        if head[:3] != b"@@^":
            raise ValueError("not an internal level")
        version = 14
    else:
        if head[:3] != b"POT":
            raise ValueError("not a level file")
        version = int(head[3:5])
    if version >= 13:
        r.skip(2)
    r.skip(4 + 8 * 4)
    namelen = 50 if version >= 14 else 14
    name = r.take("%ds" % (namelen + 1)).split(b"\0")[0].decode("latin-1")
    if version > 6:
        r.skip(16)
    if version >= 8:
        r.skip(20)
    if version < 14:
        r.pos = 100

    def polygon():
        grass = 0
        if version >= 8:
            grass = r.take("i")
            if version < 12 and grass:
                r.skip(38)
        count = r.take("i")
        return grass, [r.take("dd") for _ in range(count)]

    def obj():
        x, y, t = r.take("ddi")
        gravity = animation = 0
        if version >= 9:
            gravity = r.take("i")
        if version >= 11:
            animation = r.take("i")
        return t, x, -y, gravity, animation

    npoly = int(r.take("d"))
    if internal:
        nobj = int(r.take("d"))
        polygons = [polygon() for _ in range(npoly)]
    else:
        polygons = [polygon() for _ in range(npoly)]
        nobj = int(r.take("d"))
    objects = [obj() for _ in range(nobj)]
    return name, polygons, objects


def internal_levels(res):
    names = list(INTERNAL_LEVELS)
    if "a17.leb" not in res and SHAREWARE_LAST in res:
        names[names.index("a17.leb")] = SHAREWARE_LAST
    titles = []
    if "desclist.txt" in res:
        titles = res.read("desclist.txt").decode("latin-1").splitlines()
    out = []
    for i, name in enumerate(names):
        if name not in res:
            break
        lev = parse_level(res.read(name), internal=True)
        title = titles[i].strip() if i < len(titles) else lev[0]
        out.append((title, lev[1], lev[2]))
    return out


def write_level(path, level):
    name, polygons, objects = level
    lines = ["# %s" % name, "%d %d" % (len(polygons), len(objects))]
    for grass, poly in polygons:
        lines.append("%d %d" % (1 if grass else 0, len(poly)))
        lines += ["%r %r" % (x, y) for x, y in poly]
    for t, x, y, grav, anim in objects:
        lines.append("%d %r %r %d %d" % (t, x, y, grav, anim))
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for n, lev in enumerate(internal_levels(Resource(sys.argv[1]))):
        write_level(os.path.join(out, "lev%02d.txt" % n), lev)
    for path in sys.argv[3:]:
        with open(path, "rb") as f:
            lev = parse_level(f.read())
        base = os.path.splitext(os.path.basename(path))[0].lower()
        write_level(os.path.join(out, base + ".txt"), lev)
    return 0


if __name__ == "__main__":
    sys.exit(main())
