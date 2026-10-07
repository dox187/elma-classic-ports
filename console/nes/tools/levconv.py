"""Turns Elasto Mania levels into the data of the NES version.

For each level it makes
  - the picture of the level as background tiles, 16 pixels a meter: the
    edges of the ground are drawn with a fixed set of tiles that cut a tile
    along a line between two points of its border (2 pixels apart), and the
    tiles that such a line cannot draw (corners of thin parts) with tiles of
    the level's own;
  - the columns of the map, run length encoded;
  - the lines of the ground for the physics, sorted into a grid of 4 m cells;
  - its objects.

Coordinates: u is 1/1024 m, x from the left edge of the map, y up from its
bottom edge. A pixel of the map is 64 u.

The data of a level (little endian):
  columns  one uint16 per column of the map: where the column starts in
           the map data
  map      the columns from the top: a byte below 224 is a tile; 224+k is
           RUN_LENGTHS[k] tiles of sky, 240+k as many of ground
  lines    16 bytes each: x, y (3 bytes each), dx, dy, ex, ey, len (int16):
           start, vector to the end (u), direction (16384 is 1), length (u)
  grid     a uint16 for each row of cells: where the row starts in the grid
           data; there a byte for each cell of the row, the length of its
           list (0 if empty), then the lists: the number of runs, then
           start (uint16) and count (byte) of each run of lines
  objects  their number, then type, gravity, x, y (3 bytes each)
"""

import math

import numpy as np

import elmadata

PPM = 16                 # pixels per meter
U = 1024                 # u per meter
UPX = U // PPM           # u per pixel
SS = 2                   # supersampling of the picture for the edges
MARGIN = 1.0             # meters of ground around the level

N_PARAM = 160            # tiles cut along a line
FIRST_PARAM = 2          # 0 is the sky, 1 the ground
FIRST_EXTRA = FIRST_PARAM + N_PARAM
LAST_TILE = 223          # bytes from 224 up are runs in the map
RUN_SKY = 224
RUN_GROUND = 240
RUN_LENGTHS = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 20, 24, 32, 48, 64]

SEG_MAX = 8.0 * U        # longer lines are cut into pieces
CELL = 4096              # grid cell in u (4 m)
CELL_PAD = 512           # a line is in the cells within 0.5 m of it

# Colors of the tiles: 0 sky, 1 ground, 2 rim and texture, 3 grass.
TEXTURE = np.array([
    [1, 1, 1, 1, 1, 1, 1, 1],
    [1, 1, 1, 2, 1, 1, 1, 1],
    [1, 1, 1, 1, 1, 1, 2, 1],
    [1, 1, 1, 1, 1, 1, 1, 1],
    [1, 2, 1, 1, 1, 1, 1, 1],
    [1, 1, 1, 1, 1, 2, 1, 1],
    [1, 1, 1, 1, 1, 1, 1, 1],
    [1, 1, 2, 1, 1, 1, 1, 1],
], dtype=np.uint8)


# --- The tiles cut along a line --------------------------------------------

def border_point(q):
    """Point q (0..15) of the tile's border, clockwise from the top left
    corner, 2 pixels apart, in pixels."""
    side, k = divmod(q, 4)
    d = 2 * k
    return [(d, 0), (8, d), (8 - d, 8), (0, 8 - d)][side]


def on_one_side(q1, q2):
    """True if the two points lie on the same side line of the tile."""
    (x1, y1), (x2, y2) = border_point(q1), border_point(q2)
    return (x1 == x2 and x1 in (0, 8)) or (y1 == y2 and y1 in (0, 8))


def param_pairs():
    """The (q1, q2) pairs of the cut tiles: ground on the border clockwise
    from q1 to q2, the sky on the rest."""
    return [(a, b) for a in range(16) for b in range(16)
            if a != b and not on_one_side(a, b)]


PAIRS = param_pairs()
assert len(PAIRS) == N_PARAM
PAIR_ID = {p: FIRST_PARAM + i for i, p in enumerate(PAIRS)}


def param_mask(q1, q2):
    """Ground mask (8x8, True is ground) of a cut tile."""
    (x1, y1), (x2, y2) = border_point(q1), border_point(q2)
    # A point of the ground's arc of the border, to find its side:
    q = q1
    steps = (q2 - q1) % 16
    mid = (q1 + steps / 2.0) % 16
    side, k = divmod(mid, 4)
    d = 2 * k
    tx, ty = [(d, 0), (8, d), (8 - d, 8), (0, 8 - d)][int(side)]
    def cross(px, py):
        return (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
    s = cross(tx, ty)
    ys, xs = np.mgrid[0:8, 0:8] + 0.5
    c = (x2 - x1) * (ys - y1) - (y2 - y1) * (xs - x1)
    return (c * s) > 0


def param_tile(q1, q2):
    """Colors of a cut tile."""
    g = param_mask(q1, q2)
    (x1, y1), (x2, y2) = border_point(q1), border_point(q2)
    lx, ly = x2 - x1, y2 - y1
    ln = math.hypot(lx, ly)
    ys, xs = np.mgrid[0:8, 0:8] + 0.5
    dist = np.abs(lx * (ys - y1) - ly * (xs - x1)) / ln
    # Normal of the line towards the sky (y down):
    nx, ny = -ly / ln, lx / ln
    gx, gy = np.where(g)
    if len(gx):
        # Points from the line into the ground give the side:
        cy, cx = gx.mean() + 0.5, gy.mean() + 0.5
        if (cx - x1) * nx + (cy - y1) * ny > 0:
            nx, ny = -nx, -ny
    tile = np.where(g, TEXTURE, 0).astype(np.uint8)
    if ny < -0.5:
        tile[g & (dist < 1.7)] = 3
    else:
        tile[g & (dist < 1.0)] = 2
    return tile


def solid_tiles():
    return [np.zeros((8, 8), np.uint8), TEXTURE.copy()]


# --- Rasterizing ----------------------------------------------------------

class Geometry:
    """A level placed on the map."""

    def __init__(self, lev):
        self.lev = lev
        polys = [p for g, p in lev.polygons if not g]
        pts = np.array([q for p in polys for q in p])
        x0, y0 = pts.min(0) - MARGIN
        x1, y1 = pts.max(0) + MARGIN
        # The map starts on whole tiles of the level's coordinates:
        tm = 8.0 / PPM
        self.x0 = math.floor(x0 / tm) * tm
        self.ytop = math.ceil(y1 / tm) * tm
        self.w = int(math.ceil((x1 - self.x0) / tm))
        self.h = int(math.ceil((self.ytop - y0) / tm))
        self.ybot = self.ytop - self.h * tm
        self.polys = polys

    def to_u(self, x, y):
        return (int(round((x - self.x0) * U)), int(round((y - self.ybot) * U)))

    def air(self, ss):
        """The sky (True) and the ground, ss times the pixels of the map."""
        W, H = self.w * 8 * ss, self.h * 8 * ss
        scale = PPM * ss
        e = []
        for p in self.polys:
            a = np.array(p)
            b = np.roll(a, -1, 0)
            e.append(np.hstack([a, b]))
        E = np.vstack(e)
        ex0 = (E[:, 0] - self.x0) * scale
        ey0 = (self.ytop - E[:, 1]) * scale
        ex1 = (E[:, 2] - self.x0) * scale
        ey1 = (self.ytop - E[:, 3]) * scale
        air = np.zeros((H, W), bool)
        xs = np.arange(W) + 0.5
        lo = np.minimum(ey0, ey1)
        hi = np.maximum(ey0, ey1)
        order = np.argsort(lo)
        for row in range(H):
            yc = row + 0.5
            m = (lo <= yc) & (hi > yc)
            if not m.any():
                continue
            t = (yc - ey0[m]) / (ey1[m] - ey0[m])
            xi = np.sort(ex0[m] + t * (ex1[m] - ex0[m]))
            air[row] = np.searchsorted(xi, xs) % 2 == 1
        return air


# --- Tiles of a level -----------------------------------------------------

def perimeter_index(n):
    """Pixels of the border of an n x n block clockwise from the top left,
    with the boundary before each, in 1/n of the side."""
    pts = []
    for i in range(n):
        pts.append((0, i))
    for j in range(n):
        pts.append((j, n - 1))
    for i in range(n - 1, -1, -1):
        pts.append((n - 1, i))
    for j in range(n - 1, -1, -1):
        pts.append((j, 0))
    return pts


PERIM = perimeter_index(8 * SS)
PR = np.array([p[0] for p in PERIM])
PC = np.array([p[1] for p in PERIM])


def classify(block):
    """Classifies a tile from its supersampled sky mask: 'sky', 'ground',
    (q1, q2) for a cut tile or None for one that no cut tile draws."""
    if block.all():
        return 'sky'
    if not block.any():
        return 'ground'
    ring = ~block[PR, PC]          # ground along the border
    n = len(ring)
    trans = [k for k in range(n) if ring[k] != ring[k - 1]]
    if len(trans) == 0:
        return None
    if len(trans) != 2:
        return None
    # Boundaries in 1/(8*SS) of a side; 4*SS of them make 2 pixels.
    side = 8 * SS
    step = 2 * SS
    def q(k):
        return int(round(k / step)) % 16
    if ring[trans[0]]:
        start, end = trans[0], trans[1]
    else:
        start, end = trans[1], trans[0]
    q1, q2 = q(start), q(end)
    ground = (~block).mean() > 0.5
    if q1 == q2 or on_one_side(q1, q2):
        return 'ground' if ground else 'sky'
    return (q1, q2)


def tile_from_mask(air1, ty, tx):
    """Colors of a tile drawn from the sky mask of the whole map (1 pixel
    per pixel), with the rim where the ground meets the sky."""
    H, W = air1.shape
    y0, x0 = ty * 8, tx * 8
    tile = np.zeros((8, 8), np.uint8)
    for y in range(8):
        for x in range(8):
            py, px = y0 + y, x0 + x
            if air1[py, px]:
                continue
            c = TEXTURE[y, x]
            above = py > 0 and air1[py - 1, px]
            above2 = py > 1 and air1[py - 2, px]
            other = ((py + 1 < H and air1[py + 1, px]) or
                     (px > 0 and air1[py, px - 1]) or
                     (px + 1 < W and air1[py, px + 1]))
            if above or above2:
                c = 3
            elif other:
                c = 2
            tile[y, x] = c
    return tile


class LevelTiles:
    def __init__(self, geo):
        air = geo.air(SS)
        h, w = geo.h, geo.w
        s = 8 * SS
        blocks = air.reshape(h, s, w, s).transpose(0, 2, 1, 3)
        # The map at one pixel per pixel, for the tiles of the level:
        air1 = air.reshape(h * 8, SS, w * 8, SS).mean(axis=(1, 3)) > 0.5
        self.map = np.zeros((h, w), np.uint8)
        complex_tiles = {}
        where = {}
        for ty in range(h):
            for tx in range(w):
                c = classify(blocks[ty, tx])
                if c == 'sky':
                    self.map[ty, tx] = 0
                elif c == 'ground':
                    self.map[ty, tx] = 1
                elif c is not None:
                    self.map[ty, tx] = PAIR_ID[c]
                else:
                    t = tile_from_mask(air1, ty, tx)
                    key = t.tobytes()
                    complex_tiles.setdefault(key, []).append((ty, tx))
        # The level's own tiles: the most frequent ones; the others are drawn
        # with the nearest tile.
        room = LAST_TILE + 1 - FIRST_EXTRA
        ranked = sorted(complex_tiles.items(), key=lambda kv: -len(kv[1]))
        self.extras = []
        for key, places in ranked[:room]:
            tid = FIRST_EXTRA + len(self.extras)
            self.extras.append(np.frombuffer(key, np.uint8).reshape(8, 8))
            for ty, tx in places:
                self.map[ty, tx] = tid
        self.approximated = 0
        if len(ranked) > room:
            cands = [(tid, t != 0) for tid, t in self.all_tiles()]
            ids = np.array([c[0] for c in cands])
            masks = np.array([c[1].reshape(64) for c in cands])
            for key, places in ranked[room:]:
                m = (np.frombuffer(key, np.uint8) != 0)
                d = (masks != m).sum(1)
                tid = ids[int(np.argmin(d))]
                for ty, tx in places:
                    self.map[ty, tx] = tid
                self.approximated += len(places)
        self.n_complex = len(ranked)

    def all_tiles(self):
        out = [(0, solid_tiles()[0]), (1, solid_tiles()[1])]
        for (q1, q2), tid in PAIR_ID.items():
            out.append((tid, param_tile(q1, q2)))
        for i, t in enumerate(self.extras):
            out.append((FIRST_EXTRA + i, t))
        return out


def common_tiles():
    """The tiles 0..FIRST_EXTRA-1, the same in every level."""
    tiles = [None] * FIRST_EXTRA
    tiles[0], tiles[1] = solid_tiles()
    for (q1, q2), tid in PAIR_ID.items():
        tiles[tid] = param_tile(q1, q2)
    return tiles


def encode_column(col):
    """Run length encoding of a column of the map (see the module doc)."""
    out = bytearray()
    i, n = 0, len(col)
    while i < n:
        t = int(col[i])
        if t in (0, 1):
            j = i
            while j < n and col[j] == t:
                j += 1
            run = j - i
            base = RUN_SKY if t == 0 else RUN_GROUND
            while run > 0:
                k = max(k for k, l in enumerate(RUN_LENGTHS) if l <= run)
                out.append(base + k)
                run -= RUN_LENGTHS[k]
            i = j
        else:
            out.append(t)
            i += 1
    return bytes(out)


# --- The lines and the objects ----------------------------------------------

def segments(geo):
    out = []
    for p in geo.polys:
        n = len(p)
        for i in range(n):
            ax, ay = geo.to_u(*p[i])
            bx, by = geo.to_u(*p[(i + 1) % n])
            l = math.hypot(bx - ax, by - ay)
            if l < 1:
                continue
            parts = int(l // SEG_MAX) + 1
            for k in range(parts):
                x0 = ax + (bx - ax) * k // parts
                y0 = ay + (by - ay) * k // parts
                x1 = ax + (bx - ax) * (k + 1) // parts
                y1 = ay + (by - ay) * (k + 1) // parts
                dx, dy = x1 - x0, y1 - y0
                ll = math.hypot(dx, dy)
                if ll < 1:
                    continue
                out.append((x0, y0, dx, dy,
                            int(round(dx / ll * 16384)),
                            int(round(dy / ll * 16384)),
                            int(round(ll))))
    return out


def grid_cells(segs, geo):
    gw = (geo.w * 8 * UPX + CELL - 1) // CELL
    gh = (geo.h * 8 * UPX + CELL - 1) // CELL
    cells = [[] for _ in range(gw * gh)]
    for i, (x0, y0, dx, dy, _, _, _) in enumerate(segs):
        xa, xb = sorted((x0, x0 + dx))
        ya, yb = sorted((y0, y0 + dy))
        cx0 = max(0, (xa - CELL_PAD) // CELL)
        cx1 = min(gw - 1, (xb + CELL_PAD) // CELL)
        cy0 = max(0, (ya - CELL_PAD) // CELL)
        cy1 = min(gh - 1, (yb + CELL_PAD) // CELL)
        for cy in range(cy0, cy1 + 1):
            for cx in range(cx0, cx1 + 1):
                cells[cy * gw + cx].append(i)
    return gw, gh, cells


def objects(geo):
    out = []
    for t, x, y, g in geo.lev.objects:
        ux, uy = geo.to_u(x, y)
        out.append((t, ux, uy, g))
    # Killers first, as in the game, then the rest:
    out.sort(key=lambda o: 0 if o[0] == elmadata.T_KILLER else 1)
    return out


def le(v, n):
    return int(v).to_bytes(n, 'little', signed=v < 0)


def encode_segments(segs):
    out = bytearray()
    for x, y, dx, dy, ex, ey, ln in segs:
        out += le(x, 3) + le(y, 3) + le(dx, 2) + le(dy, 2)
        out += le(ex, 2) + le(ey, 2) + le(ln, 2)
    return bytes(out)


def encode_cell(lst):
    if not lst:
        return b''
    runs = []
    for i in lst:
        if runs and runs[-1][0] + runs[-1][1] == i and runs[-1][1] < 255:
            runs[-1][1] += 1
        else:
            runs.append([i, 1])
    out = bytearray([len(runs)])
    for start, count in runs:
        out += le(start, 2) + bytes([count])
    return bytes(out)


def encode_grid_rows(gw, gh, cells):
    """The rows of the grid: lengths of the lists, then the lists."""
    rows = []
    for cy in range(gh):
        lists = [encode_cell(cells[cy * gw + cx]) for cx in range(gw)]
        if max(len(l) for l in lists) > 255:
            raise ValueError("a cell has too many lines")
        rows.append(bytes(len(l) for l in lists) + b''.join(lists))
    return rows


def encode_objects(objs):
    out = bytearray([len(objs)])
    for t, x, y, g in objs:
        out += bytes([t, g]) + le(x, 3) + le(y, 3)
    return bytes(out)


class Converted:
    """A level converted, its parts still to be placed in the ROM."""

    def __init__(self, lev):
        self.name = lev.name
        geo = Geometry(lev)
        self.w, self.h = geo.w, geo.h
        tiles = LevelTiles(geo)
        self.extras = tiles.extras
        self.n_complex = tiles.n_complex
        self.approximated = tiles.approximated
        self.columns = [encode_column(tiles.map[:, x]) for x in range(geo.w)]
        segs = segments(geo)
        self.segments = encode_segments(segs)
        self.n_segments = len(segs)
        self.gw, self.gh, cells = grid_cells(segs, geo)
        self.grid_rows = encode_grid_rows(self.gw, self.gh, cells)
        objs = objects(geo)
        self.objects = encode_objects(objs)
        self.n_apples = sum(1 for o in objs if o[0] == elmadata.T_APPLE)
        sx, sy = geo.to_u(*lev.start())
        self.start = (sx, sy)
