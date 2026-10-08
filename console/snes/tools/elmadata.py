"""Reads the levels of Elasto Mania: the internal levels from elma.res and
external .lev files.

Coordinates are returned as the physics of the game uses them: y points up
(the files store it pointing down).
"""

import struct

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
    """The XOR stream of the game, computed with 16-bit shorts."""
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
    # The keys of the table of the files and whether an entry gives the
    # start of the file before its size: of the registered game, then of the
    # shareware (SARVARI in QOPEN.CPP).
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
        for key, shareware in self.LAYOUTS:
            table = _decrypt(self.data[4:4 + slots * 24], 23, key, 3391)
            files = self._files(table, count, shareware)
            if files:
                break
        else:
            raise ValueError("%s is not an elma.res file" % path)
        self.files = files
        self.shareware = shareware

    def _files(self, table, count, start_first):
        """The files of the table, or None if its names or places are not
        those of files: decrypted with the wrong key."""
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


class Level:
    def __init__(self):
        self.name = ""
        self.polygons = []   # list of (is_grass, [(x, y), ...])
        self.objects = []    # list of (type, x, y, gravity, animation)

    def start(self):
        for t, x, y, _, _ in self.objects:
            if t == T_START:
                return x, y
        raise ValueError("level %s has no start" % self.name)


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


def _read_polygon(r, version):
    grass = 0
    if version >= 8:
        grass = r.take("i")
        if version < 12 and grass:
            r.skip(38)
    count = r.take("i")
    pts = [r.take("dd") for _ in range(count)]
    return grass, [(x, -y) for x, y in pts]


def _read_object(r, version):
    x, y, t = r.take("ddi")
    # Apples may change the gravity: 0 none, 1 up, 2 down, 3 left, 4 right;
    # the animation is the number of the qfood picture, from 0:
    gravity = animation = 0
    if version >= 9:
        gravity = r.take("i")
    if version >= 11:
        animation = r.take("i")
    return t, x, -y, gravity, animation


def parse_level(data, internal=False):
    """Parses a .lev file, or an internal .leb level of elma.res."""
    r = _Reader(data)
    head = r.take("5s")
    lev = Level()
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
    lev.name = r.take("%ds" % (namelen + 1)).split(b"\0")[0].decode("latin-1")
    if version > 6:
        r.skip(16)
    if version >= 8:
        r.skip(20)
    if version < 14:
        r.pos = 100
    npoly = int(r.take("d"))
    if internal:
        nobj = int(r.take("d"))
        lev.polygons = [_read_polygon(r, version) for _ in range(npoly)]
    else:
        lev.polygons = [_read_polygon(r, version) for _ in range(npoly)]
        nobj = int(r.take("d"))
    lev.objects = [_read_object(r, version) for _ in range(nobj)]
    return lev


def internal_levels(res):
    """The internal levels found in elma.res, in the order of the game,
    named as in the game's menus."""
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
        if i < len(titles):
            lev.name = titles[i].strip()
        if i == 30:  # The game fixes the typo of desclist.txt the same way
            lev.name = "Animal Farm"
        out.append(lev)
    return out


def load_lev(path):
    with open(path, "rb") as f:
        return parse_level(f.read())


if __name__ == "__main__":
    # The version of the game an elma.res is of, for the Makefile:
    import sys
    print("shareware" if Resource(sys.argv[1]).shareware else "registered")
