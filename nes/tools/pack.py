"""Places the converted levels in the banks of the PRG-ROM.

The data of the levels is one linear space of 8 KB banks, read through the
$8000 window of the MMC3. No record crosses the end of a bank.
"""

BANK = 8192


class Space:
    def __init__(self, banks):
        self.data = bytearray()
        self.limit = banks * BANK

    def pad_to(self, n):
        self.data += bytes(n - len(self.data))

    def place(self, blob, align=1):
        """Places a blob that may not cross the end of a bank."""
        if len(blob) > BANK:
            raise ValueError("record of %d bytes is larger than a bank" % len(blob))
        pos = -(-len(self.data) // align) * align
        if pos // BANK != (pos + max(len(blob), 1) - 1) // BANK:
            pos = -(-pos // BANK) * BANK
        self.pad_to(pos)
        self.data += blob
        if len(self.data) > self.limit:
            raise ValueError("the levels do not fit in %d KB of PRG-ROM"
                             % (self.limit // 1024))
        return pos

    def place_records(self, blob, size):
        """Places records of a size dividing the bank, aligned to it."""
        pos = -(-len(self.data) // size) * size
        self.pad_to(pos)
        self.data += blob
        if len(self.data) > self.limit:
            raise ValueError("the levels do not fit in %d KB of PRG-ROM"
                             % (self.limit // 1024))
        return pos


def le(v, n):
    return int(v).to_bytes(n, 'little')


class Placed:
    """Where the parts of a level are."""


def place_level(space, conv):
    p = Placed()
    # The columns of the map, then the table of their starts:
    starts = []
    first = None
    for col in conv.columns:
        pos = space.place(col)
        if first is None:
            first = pos
        starts.append(pos - first)
    if starts[-1] > 0xffff:
        raise ValueError("the map of %s is too large" % conv.name)
    p.map = first
    p.columns = space.place(b''.join(le(s, 2) for s in starts))
    p.segments = space.place_records(conv.segments, 16)
    # The rows of the grid, then the table of their starts:
    rows = []
    gfirst = None
    for row in conv.grid_rows:
        pos = space.place(row)
        if gfirst is None:
            gfirst = pos
        rows.append(pos - gfirst)
    p.grid = gfirst
    p.grid_rows = space.place(b''.join(le(r, 2) for r in rows))
    p.objects = space.place(conv.objects)
    return p
