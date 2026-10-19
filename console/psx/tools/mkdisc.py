#!/usr/bin/env python3
"""mkdisc.py - assemble the two-track Elasto Mania PlayStation disc image.

Disc layout
-----------
Track 1  MODE2/2352, bootable, only our own code (SYSTEM.CNF + PS-EXE). It
         is made by mkpsxiso and contains no original game data.
Track 2  ISO9660 level 1 (8.3 upper-case names, ";1" versions) holding the
         user's own game files:  ELMA.RES, LGR/DEFAULT.LGR and LEV/*.LEV
         (plus anything from --extra-dir).

The game finds track 2 through the TOC (GetTN/GetTD), looks for the "CD001"
descriptor and reads the files with its own small ISO9660 reader.

Output: <out-dir>/<name>.cue plus the .bin file(s). The default output
directory is console/psx/build/disc/ (git-ignored).

Examples
--------
  # Normal use: build track 1 with mkpsxiso from a PS-EXE, track 2 from the
  # user's game files.
  mkdisc.py --exe elma.exe --res elma.res --lgr Default_old.lgr \\
            --lev-dir ~/game/Lev

  # Track 1 already made by mkpsxiso (MODE2/2352 .bin or its .cue).
  mkdisc.py --track1-cue track1.cue --res elma.res --lgr Default_old.lgr

  # Track 2 made with any standard tool, e.g.
  #   genisoimage -iso-level 1 -o levels.iso dir/
  #   xorriso -as mkisofs -iso-level 1 -o levels.iso dir/
  # Any plain ISO9660 image works; our own writer is only a convenience.
  mkdisc.py --track1-bin track1.bin --track2-iso levels.iso

  # Development without mkpsxiso: dummy 1000-sector track 1 (not bootable).
  mkdisc.py --dummy-track1 1000 --res elma.res --lgr Default_old.lgr

Track 2 sector format (--track2-format)
---------------------------------------
  2352  (default) raw MODE1/2352 sectors: sync, BCD header with the correct
        absolute MSF, user data, EDC and ECC P/Q. The most compatible choice
        (emulators, CHD conversion, burning). Everything goes in one .bin.
  2048  plain MODE1/2048 user data in a separate <name>_track02.iso file
        (a file cannot mix 2352 and 2048 byte sectors). Accepted by
        DuckStation and Mednafen; PCSX-Redux/ODEs/burners are not verified.
  --split puts the raw track 2 into a separate <name>_track02.bin too.

Pregap and track position
-------------------------
Between the two data tracks the cue sheet has a pregap of at least 150
sectors (2 seconds), exactly as the Yellow Book requires when the sector
mode changes and as redump/mkpsxiso/cdrdao cue sheets do for an audio track
after a data track:

    FILE "elma.bin" BINARY
      TRACK 01 MODE2/2352
        INDEX 01 00:00:00
      TRACK 02 MODE1/2352
        INDEX 00 mm:ss:ff        ; start of the pregap, stored in the file
        INDEX 01 mm:ss:ff        ; first ISO sector

With --split the raw track 2 gets its own file in the usual redump style,
the pregap stored at its start ("INDEX 00 00:00:00" / "INDEX 01 pregap").
For the plain 2048 file the pregap is not stored (that file stays a plain
ISO image) and the cue has a "PREGAP 00:0x:xx" line instead. The pregap sectors contain valid Mode 1 sectors
with zero data. The PS1 drive reports the INDEX 01 position of a track via
GetTD rounded DOWN to whole seconds, so by default the pregap is lengthened
(150..224 sectors) until INDEX 01 falls on a second boundary, which makes
GetTD exact. The reader copes with the rounding anyway (it scans forward
for "CD001"); use --no-align to disable the padding, --pregap N to force a
pregap length.

Only the Python 3 standard library is used.
"""

import argparse
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import zlib

SECTOR_RAW = 2352
SECTOR_USER = 2048
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
MIN_PREGAP = 150
MAX_SECTORS = 360000  # 80 minute disc


# ---------------------------------------------------------------------------
# EDC / ECC (ECMA-130 annex A and B)
# ---------------------------------------------------------------------------

def _make_edc_table():
    table = []
    for i in range(256):
        edc = i
        for _ in range(8):
            edc = (edc >> 1) ^ (0xD8018001 if edc & 1 else 0)
        table.append(edc)
    return table


_EDC_TABLE = _make_edc_table()
_ECC_F = [((i << 1) ^ (0x11D if i & 0x80 else 0)) & 0xFF for i in range(256)]
_ECC_B = [0] * 256
for _i in range(256):
    _ECC_B[_i ^ _ECC_F[_i]] = _i


def edc(data):
    """CD-ROM EDC (CRC-32, polynomial 0x8001801B reflected, no final xor)."""
    crc = 0
    table = _EDC_TABLE
    for b in data:
        crc = (crc >> 8) ^ table[(crc ^ b) & 0xFF]
    return crc


def _ecc_index_lists(major_count, minor_count, major_mult, minor_inc):
    size = major_count * minor_count
    lists = []
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        idx = []
        for _ in range(minor_count):
            idx.append(index)
            index += minor_inc
            if index >= size:
                index -= size
        lists.append(idx)
    return lists


_P_LISTS = _ecc_index_lists(86, 24, 2, 86)
_Q_LISTS = _ecc_index_lists(52, 43, 86, 88)


def _ecc_block(src, lists, dest):
    """Fill dest (bytearray of 2 * len(lists) bytes) with the parity bytes."""
    n = len(lists)
    f_lut = _ECC_F
    b_lut = _ECC_B
    for major, idx in enumerate(lists):
        a = 0
        b = 0
        for i in idx:
            t = src[i]
            a ^= t
            b ^= t
            a = f_lut[a]
        a = b_lut[f_lut[a] ^ b]
        dest[major] = a
        dest[major + n] = a ^ b


def _fill_ecc(sector):
    """Compute P and Q parity over sector[12:2076] (a bytearray, in place).

    The caller has already put the header (zeroed for Mode 2) in place."""
    src = bytes(sector[12:12 + 2064])
    par = bytearray(172)
    _ecc_block(src, _P_LISTS, par)
    sector[2076:2076 + 172] = par
    src = bytes(sector[12:12 + 2236])
    par = bytearray(104)
    _ecc_block(src, _Q_LISTS, par)
    sector[2248:2248 + 104] = par


def _bcd(n):
    return ((n // 10) << 4) | (n % 10)


def msf_bytes(abs_lba):
    """BCD min/sec/frame bytes for an absolute sector address (LBA + 150)."""
    m, rest = divmod(abs_lba, 60 * 75)
    s, f = divmod(rest, 75)
    return bytes((_bcd(m), _bcd(s), _bcd(f)))


def encode_mode1(abs_lba, user):
    """Raw 2352-byte MODE1 sector. abs_lba = LBA + 150 (header address)."""
    assert len(user) == SECTOR_USER
    s = bytearray(SECTOR_RAW)
    s[0:12] = SYNC
    s[12:15] = msf_bytes(abs_lba)
    s[15] = 1
    s[16:2064] = user
    struct.pack_into("<I", s, 2064, edc(s[0:2064]))
    # bytes 2068..2075 stay zero
    _fill_ecc(s)
    return bytes(s)


def encode_mode2_form1(abs_lba, user, submode=0x08):
    """Raw 2352-byte MODE2 Form 1 sector (used for the dummy track 1)."""
    assert len(user) == SECTOR_USER
    s = bytearray(SECTOR_RAW)
    s[0:12] = SYNC
    s[12:15] = msf_bytes(abs_lba)
    s[15] = 2
    s[16:24] = bytes((0, 0, submode, 0)) * 2
    s[24:2072] = user
    struct.pack_into("<I", s, 2072, edc(s[16:2072]))
    hdr = bytes(s[12:16])
    s[12:16] = b"\x00\x00\x00\x00"  # ECC is computed with a zeroed header
    _fill_ecc(s)
    s[12:16] = hdr
    return bytes(s)


# ---------------------------------------------------------------------------
# ISO9660 level 1 writer
# ---------------------------------------------------------------------------

FILE_RE = re.compile(r"^([A-Z0-9_]{1,8})(?:\.([A-Z0-9_]{0,3}))?$")
DIR_RE = re.compile(r"^[A-Z0-9_]{1,8}$")


def iso_file_ident(name):
    """Return the level-1 identifier "NAME.EXT" for a file name, or None."""
    m = FILE_RE.match(name.upper())
    if not m:
        return None
    return "%s.%s" % (m.group(1), m.group(2) or "")


class _Dir:
    def __init__(self, name, parent):
        self.name = name        # identifier ("" for the root)
        self.parent = parent
        self.dirs = {}
        self.files = {}         # ident -> (source path or bytes, size)
        self.extent = 0
        self.size = 0
        self.number = 0         # path table number (1-based)


class IsoImage:
    """Collects files, then lays out and serialises an ISO9660 image."""

    def __init__(self, volume_id="ELMA", timestamp=None):
        self.root = _Dir("", None)
        self.volume_id = volume_id
        self.timestamp = int(time.time()) if timestamp is None else timestamp
        self.skipped = []

    def _dir_for(self, parts, create=True):
        d = self.root
        for p in parts:
            ident = p.upper()
            if not DIR_RE.match(ident):
                return None
            if ident not in d.dirs:
                if not create:
                    return None
                d.dirs[ident] = _Dir(ident, d)
            d = d.dirs[ident]
        return d

    def add(self, iso_path, source):
        """Add a file. source is a path (str) or bytes. Returns True/False."""
        parts = [p for p in iso_path.split("/") if p]
        ident = iso_file_ident(parts[-1])
        d = self._dir_for(parts[:-1])
        if ident is None or d is None:
            self.skipped.append((iso_path, "name does not fit ISO9660 level 1 (8.3)"))
            return False
        if ident in d.files:
            self.skipped.append((iso_path, "duplicate name after upper-casing"))
            return False
        size = len(source) if isinstance(source, bytes) else os.path.getsize(source)
        d.files[ident] = (source, size)
        return True

    def add_tree(self, directory, iso_prefix=""):
        """Add every file below a host directory (recursively)."""
        for name in sorted(os.listdir(directory)):
            full = os.path.join(directory, name)
            iso = iso_prefix + "/" + name
            if os.path.isdir(full):
                if self._dir_for([p for p in iso.split("/") if p]) is None:
                    self.skipped.append((iso, "directory name does not fit level 1"))
                    continue
                self.add_tree(full, iso)
            else:
                self.add(iso, full)

    def manifest(self):
        """Text listing "CRC32 SIZE PATH" of every file (paths as stored,
        without the ';1' version and a trailing '.'), CRC-32 as in zlib."""
        lines = []

        def walk(d, prefix):
            for ident in sorted(d.files, key=self._sort_key):
                src, size = d.files[ident]
                data = src if isinstance(src, bytes) else open(src, "rb").read()
                name = ident[:-1] if ident.endswith(".") else ident
                lines.append("%08X %d %s%s" % (zlib.crc32(data) & 0xFFFFFFFF, size,
                                                prefix, name))
            for ident in sorted(d.dirs, key=self._sort_key):
                walk(d.dirs[ident], prefix + ident + "/")

        walk(self.root, "")
        return ("\n".join(lines) + "\n").encode()

    # -- layout ----------------------------------------------------------

    @staticmethod
    def _sort_key(ident):
        name, _, rest = ident.split(";")[0].partition(".")
        return (name.ljust(8), rest.ljust(3))

    @staticmethod
    def _rec_len(ident_len):
        n = 33 + ident_len
        return n + (n & 1)

    def _dir_children(self, d):
        """Directory entries in sorted order: (ident, kind, obj)."""
        items = [(i, "d", x) for i, x in d.dirs.items()]
        items += [(i + ";1", "f", x) for i, x in d.files.items()]
        items.sort(key=lambda t: (self._sort_key(t[0]), t[0]))
        return items

    def _dir_size(self, d):
        sectors = 1
        used = 2 * 34  # '.' and '..' records have a 1-byte identifier
        for ident, _, _ in self._dir_children(d):
            n = self._rec_len(len(ident))
            if used + n > SECTOR_USER:
                sectors += 1
                used = 0
            used += n
        return sectors * SECTOR_USER

    def _bfs_dirs(self):
        order = [self.root]
        i = 0
        while i < len(order):
            d = order[i]
            i += 1
            for ident in sorted(d.dirs, key=self._sort_key):
                order.append(d.dirs[ident])
        for n, d in enumerate(order):
            d.number = n + 1
        return order

    def _date7(self):
        t = time.gmtime(self.timestamp)
        return bytes((t.tm_year - 1900, t.tm_mon, t.tm_mday,
                      t.tm_hour, t.tm_min, t.tm_sec, 0))

    def _date17(self):
        t = time.gmtime(self.timestamp)
        return ("%04d%02d%02d%02d%02d%02d00" % (
            t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec
        )).encode() + b"\x00"

    def _record(self, extent, size, is_dir, ident):
        n = self._rec_len(len(ident))
        r = bytearray(n)
        r[0] = n
        struct.pack_into("<I", r, 2, extent)
        struct.pack_into(">I", r, 6, extent)
        struct.pack_into("<I", r, 10, size)
        struct.pack_into(">I", r, 14, size)
        r[18:25] = self._date7()
        r[25] = 2 if is_dir else 0
        struct.pack_into("<H", r, 28, 1)
        struct.pack_into(">H", r, 30, 1)
        r[32] = len(ident)
        r[33:33 + len(ident)] = ident
        return bytes(r)

    def _path_table(self, order, big):
        out = bytearray()
        e2 = ">" if big else "<"
        for d in order:
            ident = d.name.encode() if d.parent else b"\x00"
            parent = d.parent.number if d.parent else 1
            out += struct.pack("B", len(ident)) + b"\x00"
            out += struct.pack(e2 + "I", d.extent)
            out += struct.pack(e2 + "H", parent)
            out += ident
            if len(ident) & 1:
                out += b"\x00"
        return bytes(out)

    def build(self):
        """Return the image as a list of chunks: bytes objects and
        (path, size) tuples for file data; also the total sector count."""
        order = self._bfs_dirs()
        for d in order:
            d.size = self._dir_size(d)
        pt_size = len(self._path_table(order, False))
        pt_sectors = (pt_size + SECTOR_USER - 1) // SECTOR_USER
        lpath = 18
        mpath = lpath + pt_sectors
        lba = mpath + pt_sectors
        for d in order:
            d.extent = lba
            lba += d.size // SECTOR_USER
        file_extents = {}
        file_list = []
        for d in order:
            for ident in sorted(d.files, key=self._sort_key):
                src, size = d.files[ident]
                sectors = (size + SECTOR_USER - 1) // SECTOR_USER
                file_extents[(id(d), ident)] = lba
                file_list.append((src, size, lba))
                lba += sectors
        total = lba

        chunks = []  # (kind, payload) kind "b" bytes (sector aligned) / "f" file
        chunks.append(("b", bytes(16 * SECTOR_USER)))
        # primary volume descriptor
        pvd = bytearray(SECTOR_USER)
        pvd[0] = 1
        pvd[1:6] = b"CD001"
        pvd[6] = 1
        pvd[8:40] = b"PLAYSTATION".ljust(32)
        pvd[40:72] = self.volume_id.encode().ljust(32)
        struct.pack_into("<I", pvd, 80, total)
        struct.pack_into(">I", pvd, 84, total)
        struct.pack_into("<H", pvd, 120, 1)
        struct.pack_into(">H", pvd, 122, 1)
        struct.pack_into("<H", pvd, 124, 1)
        struct.pack_into(">H", pvd, 126, 1)
        struct.pack_into("<H", pvd, 128, SECTOR_USER)
        struct.pack_into(">H", pvd, 130, SECTOR_USER)
        struct.pack_into("<I", pvd, 132, pt_size)
        struct.pack_into(">I", pvd, 136, pt_size)
        struct.pack_into("<I", pvd, 140, lpath)
        struct.pack_into("<I", pvd, 144, 0)
        struct.pack_into(">I", pvd, 148, mpath)
        struct.pack_into(">I", pvd, 152, 0)
        pvd[156:190] = self._record(self.root.extent, self.root.size, True, b"\x00")
        pvd[190:318] = b"".ljust(128)       # volume set id
        pvd[318:446] = b"".ljust(128)       # publisher
        pvd[446:574] = b"".ljust(128)       # data preparer
        pvd[574:702] = b"MKDISC.PY".ljust(128)
        pvd[702:739] = b"".ljust(37)
        pvd[739:776] = b"".ljust(37)
        pvd[776:813] = b"".ljust(37)
        pvd[813:830] = self._date17()
        pvd[830:847] = self._date17()
        pvd[847:864] = b"0000000000000000\x00"
        pvd[864:881] = b"0000000000000000\x00"
        pvd[881] = 1
        chunks.append(("b", bytes(pvd)))
        term = bytearray(SECTOR_USER)
        term[0] = 255
        term[1:6] = b"CD001"
        term[6] = 1
        chunks.append(("b", bytes(term)))
        for big in (False, True):
            pt = self._path_table(order, big)
            chunks.append(("b", pt.ljust(pt_sectors * SECTOR_USER, b"\x00")))
        # directories
        for d in order:
            parent = d.parent or d
            buf = bytearray()
            sec_used = 0

            def put(rec):
                nonlocal sec_used
                if sec_used + len(rec) > SECTOR_USER:
                    buf.extend(bytes(SECTOR_USER - sec_used))
                    sec_used = 0
                buf.extend(rec)
                sec_used += len(rec)

            put(self._record(d.extent, d.size, True, b"\x00"))
            put(self._record(parent.extent, parent.size, True, b"\x01"))
            for ident, kind, obj in self._dir_children(d):
                if kind == "d":
                    put(self._record(obj.extent, obj.size, True, ident.encode()))
                else:
                    size = d.files[ident[:-2]][1]
                    ext = file_extents[(id(d), ident[:-2])] if size else 0
                    put(self._record(ext, size, False, ident.encode()))
            buf.extend(bytes(d.size - len(buf)))
            assert len(buf) == d.size
            chunks.append(("b", bytes(buf)))
        for src, size, ext in file_list:
            if size:
                chunks.append(("f", (src, size)))
        return chunks, total

    def write_sectors(self):
        """Generator yielding the image as 2048-byte sectors."""
        chunks, total = self.build()
        count = 0
        for kind, payload in chunks:
            if kind == "b":
                for off in range(0, len(payload), SECTOR_USER):
                    yield payload[off:off + SECTOR_USER]
                    count += 1
            else:
                src, size = payload
                if isinstance(src, bytes):
                    data = src
                else:
                    with open(src, "rb") as f:
                        data = f.read()
                if len(data) != size:
                    raise IOError("file changed while building: %r" % (src,))
                for off in range(0, size, SECTOR_USER):
                    yield data[off:off + SECTOR_USER].ljust(SECTOR_USER, b"\x00")
                    count += 1
        assert count == total, (count, total)


# ---------------------------------------------------------------------------
# Track 1
# ---------------------------------------------------------------------------

def default_mkpsxiso():
    home = os.path.expanduser("~/.local/share/elma-psx")
    for cand in (os.path.join(home, "bin", "mkpsxiso"),
                 os.path.join(home, "mkpsxiso"),
                 os.path.join(home, "mkpsxiso", "bin", "mkpsxiso")):
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return shutil.which("mkpsxiso")


SYSTEM_CNF = ("BOOT=cdrom:\\ELMA.EXE;1\r\nTCB=4\r\nEVENT=10\r\n"
              "STACK=801FFFF0\r\n")


def xml_attr(s):
    return (s.replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def build_track1_with_mkpsxiso(args, workdir):
    """Run mkpsxiso on a generated project. Returns the path of the .bin."""
    exe = args.mkpsxiso or os.environ.get("MKPSXISO") or default_mkpsxiso()
    if not exe or not os.path.exists(exe):
        sys.exit("mkdisc: mkpsxiso not found (use --mkpsxiso or install it "
                 "under ~/.local/share/elma-psx/)")
    os.makedirs(workdir, exist_ok=True)
    cnf = os.path.join(workdir, "SYSTEM.CNF")
    with open(cnf, "wb") as f:
        f.write(SYSTEM_CNF.encode())
    xml = os.path.join(workdir, "track1.xml")
    binp = os.path.join(workdir, "track1.bin")
    cue = os.path.join(workdir, "track1.cue")
    lic = ""
    if args.license:
        lic = '        <license file="%s"/>\n' % xml_attr(os.path.abspath(args.license))
    with open(xml, "w") as f:
        f.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<iso_project image_name="%s" cue_sheet="%s">\n'
            '  <track type="data">\n'
            '    <identifiers system="PLAYSTATION" application="PLAYSTATION" '
            'volume="ELMA" volume_set="ELMA" publisher="" data_preparer="" '
            'copyright=""/>\n'
            '%s'
            '    <directory_tree>\n'
            '      <file name="SYSTEM.CNF" type="data" source="%s"/>\n'
            '      <file name="ELMA.EXE" type="data" source="%s"/>\n'
            '    </directory_tree>\n'
            '  </track>\n'
            '</iso_project>\n' % (
                xml_attr(binp), xml_attr(cue), lic, xml_attr(cnf),
                xml_attr(os.path.abspath(args.exe))))
    cmd = [exe, "-y", "-q", xml]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True)
    if r.returncode != 0 or not os.path.exists(binp):
        sys.exit("mkdisc: mkpsxiso failed (%s):\n%s" % (" ".join(cmd), r.stdout))
    return binp


def track1_bin_from_cue(cue_path):
    """Find the .bin of a single-track MODE2/2352 cue made by mkpsxiso."""
    with open(cue_path) as f:
        text = f.read()
    m = re.search(r'FILE\s+"([^"]+)"|FILE\s+(\S+)', text)
    if not m:
        sys.exit("mkdisc: no FILE line in %s" % cue_path)
    name = m.group(1) or m.group(2)
    tracks = re.findall(r"TRACK\s+(\d+)\s+(\S+)", text)
    if len(tracks) != 1 or tracks[0][1] != "MODE2/2352":
        sys.exit("mkdisc: %s must contain exactly one MODE2/2352 track "
                 "(found %r)" % (cue_path, tracks))
    return os.path.join(os.path.dirname(os.path.abspath(cue_path)), name)


def make_dummy_track1(path, sectors):
    """Not bootable. For tests: PVD-less MODE2 Form 1 sectors with a marker."""
    with open(path, "wb") as f:
        for i in range(sectors):
            user = (b"DUMMY TRACK 1 %d" % i).ljust(SECTOR_USER, b"\x00")
            f.write(encode_mode2_form1(i + 150, user))


# ---------------------------------------------------------------------------
# Disc assembly
# ---------------------------------------------------------------------------

def msf_str(lba):
    m, rest = divmod(lba, 60 * 75)
    s, f = divmod(rest, 75)
    return "%02d:%02d:%02d" % (m, s, f)


def copy_file(src, dst_f):
    with open(src, "rb") as f:
        shutil.copyfileobj(f, dst_f, 1 << 20)


def track2_sectors(args, iso):
    """Yield the 2048-byte sectors of track 2."""
    if args.track2_iso:
        size = os.path.getsize(args.track2_iso)
        if size % SECTOR_USER or size < 18 * SECTOR_USER:
            sys.exit("mkdisc: %s is not a plain ISO image (size %d)"
                     % (args.track2_iso, size))
        with open(args.track2_iso, "rb") as f:
            f.seek(16 * SECTOR_USER)
            if f.read(6)[1:6] != b"CD001":
                sys.exit("mkdisc: %s has no CD001 descriptor at sector 16"
                         % args.track2_iso)
            f.seek(0)
            while True:
                b = f.read(SECTOR_USER)
                if not b:
                    return
                yield b
    else:
        yield from iso.write_sectors()


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    default_out = os.path.normpath(os.path.join(here, "..", "build", "disc"))
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_argument_group("track 2 contents (own ISO9660 writer)")
    g.add_argument("--res", help="stored as ELMA.RES")
    g.add_argument("--lgr", help="stored as LGR/DEFAULT.LGR, where the game looks for it")
    g.add_argument("--lev-dir", help="every *.lev is stored as LEV/NAME.LEV; "
                   "names that do not fit 8.3 are skipped and reported")
    g.add_argument("--extra-dir", help="further files/directories, stored "
                   "with their names upper-cased")
    g.add_argument("--manifest", metavar="NAME",
                   help="also store a text file NAME (e.g. SUMS.TXT) with a "
                   "'CRC32 SIZE PATH' line for every file (test aid: the "
                   "PS1 test program verifies the disc against it)")
    g.add_argument("--volume-id", default="ELMA", help="ISO volume id")
    g.add_argument("--write-iso", metavar="FILE",
                   help="also write the generated track 2 as a plain ISO")
    g.add_argument("--track2-iso", metavar="FILE",
                   help="use a ready-made ISO9660 image as track 2 instead")
    g = ap.add_argument_group("track 1")
    g.add_argument("--track1-bin", help="MODE2/2352 image made by mkpsxiso")
    g.add_argument("--track1-cue", help="its cue sheet (names the .bin)")
    g.add_argument("--exe", help="PS-EXE: run mkpsxiso on a generated XML "
                   "(SYSTEM.CNF: BOOT=cdrom:\\ELMA.EXE;1, TCB=4, EVENT=10, "
                   "STACK=801FFFF0)")
    g.add_argument("--license", help="Sony license data file for mkpsxiso "
                   "(real hardware only; never committed)")
    g.add_argument("--mkpsxiso", help="mkpsxiso binary (default: $MKPSXISO, "
                   "~/.local/share/elma-psx/, PATH)")
    g.add_argument("--dummy-track1", type=int, metavar="SECTORS",
                   help="generate a non-bootable dummy track 1 (tests)")
    g = ap.add_argument_group("output")
    g.add_argument("--out-dir", default=default_out,
                   help="default: console/psx/build/disc")
    g.add_argument("--name", default="elma", help="output base name")
    g.add_argument("--track2-format", choices=("2352", "2048"), default="2352")
    g.add_argument("--split", action="store_true",
                   help="write the raw track 2 into its own .bin file")
    g.add_argument("--pregap", type=int, metavar="SECTORS",
                   help="force the pregap length (>= 150)")
    g.add_argument("--no-align", action="store_true",
                   help="do not lengthen the pregap to a whole second")
    args = ap.parse_args(argv)

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    # ---- track 1
    work = os.path.join(out_dir, "work")
    made_work = bool(args.exe or args.dummy_track1) and not (
        args.track1_bin or args.track1_cue)
    if args.track1_bin:
        t1 = args.track1_bin
    elif args.track1_cue:
        t1 = track1_bin_from_cue(args.track1_cue)
    elif args.exe:
        t1 = build_track1_with_mkpsxiso(args, work)
    elif args.dummy_track1:
        os.makedirs(work, exist_ok=True)
        t1 = os.path.join(work, "dummy_track1.bin")
        make_dummy_track1(t1, args.dummy_track1)
    else:
        ap.error("need one of --track1-bin, --track1-cue, --exe, --dummy-track1")
    t1_size = os.path.getsize(t1)
    if t1_size % SECTOR_RAW or t1_size == 0:
        sys.exit("mkdisc: %s is not a MODE2/2352 image (size %d)" % (t1, t1_size))
    n1 = t1_size // SECTOR_RAW

    # ---- track 2 content
    iso = None
    if not args.track2_iso:
        ts = os.environ.get("SOURCE_DATE_EPOCH")
        iso = IsoImage(args.volume_id, int(ts) if ts else None)
        if args.res:
            iso.add("ELMA.RES", args.res)
        if args.lgr:
            iso.add("LGR/DEFAULT.LGR", args.lgr)
        if args.lev_dir:
            for name in sorted(os.listdir(args.lev_dir)):
                if name.lower().endswith(".lev"):
                    iso.add("LEV/" + name, os.path.join(args.lev_dir, name))
        if args.extra_dir:
            iso.add_tree(args.extra_dir)
        if args.manifest:
            iso.add(args.manifest, iso.manifest())
        for path, why in iso.skipped:
            print("mkdisc: skipped %s: %s" % (path, why), file=sys.stderr)
        if not iso.root.files and not iso.root.dirs:
            ap.error("track 2 would be empty: give --res/--lgr/--lev-dir/"
                     "--extra-dir or --track2-iso")

    # ---- positions
    if args.pregap is not None:
        if args.pregap < MIN_PREGAP:
            ap.error("--pregap must be at least %d" % MIN_PREGAP)
        pregap = args.pregap
    elif args.no_align:
        pregap = MIN_PREGAP
    else:
        pregap = MIN_PREGAP + ((-n1) % 75)
    t2_start = n1 + pregap       # LBA of the first ISO sector (INDEX 01)
    raw = args.track2_format == "2352"
    split = args.split or not raw
    t2_ext = "bin" if raw else "iso"
    t2_name = "%s_track02.%s" % (args.name, t2_ext)
    bin_name = "%s.bin" % args.name
    cue_name = "%s.cue" % args.name

    # ---- write the files
    t2_sectors = 0
    iso_out = open(args.write_iso, "wb") if args.write_iso else None
    t2_path = os.path.join(out_dir, t2_name)
    main_path = os.path.join(out_dir, bin_name)
    with open(main_path, "wb") as fb:
        copy_file(t1, fb)
        ft2 = open(t2_path, "wb") if split else fb
        if raw:
            # the pregap is stored: Mode 1 sectors with zero data
            zero = bytes(SECTOR_USER)
            for i in range(pregap):
                ft2.write(encode_mode1(n1 + i + 150, zero))
        for i, sec in enumerate(track2_sectors(args, iso)):
            if iso_out:
                iso_out.write(sec)
            if raw:
                ft2.write(encode_mode1(t2_start + i + 150, sec))
            else:
                ft2.write(sec)
            t2_sectors += 1
        if split:
            ft2.close()
    if iso_out:
        iso_out.close()
    if made_work:
        shutil.rmtree(work, ignore_errors=True)
    if n1 + pregap + t2_sectors > MAX_SECTORS:
        print("mkdisc: warning: image exceeds an 80 minute disc", file=sys.stderr)

    # ---- cue sheet
    lines = ['FILE "%s" BINARY' % bin_name,
             "  TRACK 01 MODE2/2352",
             "    INDEX 01 00:00:00"]
    if not split:
        lines += ["  TRACK 02 MODE1/2352",
                  "    INDEX 00 %s" % msf_str(n1),
                  "    INDEX 01 %s" % msf_str(t2_start)]
    elif raw:
        # redump style multi-file layout: the pregap is stored in the file
        lines += ['FILE "%s" BINARY' % t2_name,
                  "  TRACK 02 MODE1/2352",
                  "    INDEX 00 00:00:00",
                  "    INDEX 01 %s" % msf_str(pregap)]
    else:
        lines += ['FILE "%s" BINARY' % t2_name,
                  "  TRACK 02 MODE1/%s" % args.track2_format,
                  "    PREGAP %s" % msf_str(pregap),
                  "    INDEX 01 00:00:00"]
    with open(os.path.join(out_dir, cue_name), "w", newline="") as f:
        f.write("\r\n".join(lines) + "\r\n")

    absolute = t2_start + 150
    print("mkdisc: wrote %s" % os.path.join(out_dir, cue_name))
    print("  track 1: MODE2/2352, %d sectors, LBA 0..%d" % (n1, n1 - 1))
    print("  pregap : %d sectors" % pregap)
    print("  track 2: MODE1/%s, %d sectors, starts at LBA %d (absolute "
          "%s, GetTD %s)" % (args.track2_format, t2_sectors, t2_start,
                             msf_str(absolute), msf_str(absolute - absolute % 75)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
