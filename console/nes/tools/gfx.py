"""The sprites and the menu tiles of the NES version, drawn from shapes.

The bike and the rider are drawn at 64 angles, each turned as shapes at 8
times the size and then reduced to pixels, so that every angle is sharp.
"""

import math
import os

import numpy as np
from PIL import Image, ImageDraw

PPM = 16          # pixels per meter
SUPER = 8         # drawn this many times larger, then reduced
ANGLES = 64

# --- A 5x7 font -------------------------------------------------------------

FONT = {
    ' ': [],
    'A': ['.###.', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'],
    'B': ['####.', '#...#', '#...#', '####.', '#...#', '#...#', '####.'],
    'C': ['.###.', '#...#', '#....', '#....', '#....', '#...#', '.###.'],
    'D': ['####.', '#...#', '#...#', '#...#', '#...#', '#...#', '####.'],
    'E': ['#####', '#....', '#....', '####.', '#....', '#....', '#####'],
    'F': ['#####', '#....', '#....', '####.', '#....', '#....', '#....'],
    'G': ['.###.', '#...#', '#....', '#.###', '#...#', '#...#', '.####'],
    'H': ['#...#', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'],
    'I': ['.###.', '..#..', '..#..', '..#..', '..#..', '..#..', '.###.'],
    'J': ['..###', '...#.', '...#.', '...#.', '...#.', '#..#.', '.##..'],
    'K': ['#...#', '#..#.', '#.#..', '##...', '#.#..', '#..#.', '#...#'],
    'L': ['#....', '#....', '#....', '#....', '#....', '#....', '#####'],
    'M': ['#...#', '##.##', '#.#.#', '#.#.#', '#...#', '#...#', '#...#'],
    'N': ['#...#', '#...#', '##..#', '#.#.#', '#..##', '#...#', '#...#'],
    'O': ['.###.', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'],
    'P': ['####.', '#...#', '#...#', '####.', '#....', '#....', '#....'],
    'Q': ['.###.', '#...#', '#...#', '#...#', '#.#.#', '#..#.', '.##.#'],
    'R': ['####.', '#...#', '#...#', '####.', '#.#..', '#..#.', '#...#'],
    'S': ['.####', '#....', '#....', '.###.', '....#', '....#', '####.'],
    'T': ['#####', '..#..', '..#..', '..#..', '..#..', '..#..', '..#..'],
    'U': ['#...#', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'],
    'V': ['#...#', '#...#', '#...#', '#...#', '#...#', '.#.#.', '..#..'],
    'W': ['#...#', '#...#', '#...#', '#.#.#', '#.#.#', '#.#.#', '.#.#.'],
    'X': ['#...#', '#...#', '.#.#.', '..#..', '.#.#.', '#...#', '#...#'],
    'Y': ['#...#', '#...#', '.#.#.', '..#..', '..#..', '..#..', '..#..'],
    'Z': ['#####', '....#', '...#.', '..#..', '.#...', '#....', '#####'],
    '0': ['.###.', '#...#', '#..##', '#.#.#', '##..#', '#...#', '.###.'],
    '1': ['..#..', '.##..', '..#..', '..#..', '..#..', '..#..', '.###.'],
    '2': ['.###.', '#...#', '....#', '...#.', '..#..', '.#...', '#####'],
    '3': ['#####', '...#.', '..#..', '...#.', '....#', '#...#', '.###.'],
    '4': ['...#.', '..##.', '.#.#.', '#..#.', '#####', '...#.', '...#.'],
    '5': ['#####', '#....', '####.', '....#', '....#', '#...#', '.###.'],
    '6': ['..##.', '.#...', '#....', '####.', '#...#', '#...#', '.###.'],
    '7': ['#####', '....#', '...#.', '..#..', '.#...', '.#...', '.#...'],
    '8': ['.###.', '#...#', '#...#', '.###.', '#...#', '#...#', '.###.'],
    '9': ['.###.', '#...#', '#...#', '.####', '....#', '...#.', '.##..'],
    '.': ['.....', '.....', '.....', '.....', '.....', '.##..', '.##..'],
    ',': ['.....', '.....', '.....', '.....', '.##..', '..#..', '.#...'],
    ':': ['.....', '.##..', '.##..', '.....', '.##..', '.##..', '.....'],
    '-': ['.....', '.....', '.....', '#####', '.....', '.....', '.....'],
    '!': ['..#..', '..#..', '..#..', '..#..', '..#..', '.....', '..#..'],
    '?': ['.###.', '#...#', '....#', '...#.', '..#..', '.....', '..#..'],
    "'": ['..#..', '..#..', '.#...', '.....', '.....', '.....', '.....'],
    '&': ['.##..', '#..#.', '#.#..', '.#...', '#.#.#', '#..#.', '.##.#'],
    '/': ['....#', '...#.', '...#.', '..#..', '.#...', '.#...', '#....'],
    '(': ['...#.', '..#..', '.#...', '.#...', '.#...', '..#..', '...#.'],
    ')': ['.#...', '..#..', '...#.', '...#.', '...#.', '..#..', '.#...'],
    '>': ['.#...', '..#..', '...#.', '....#', '...#.', '..#..', '.#...'],
    '<': ['...#.', '..#..', '.#...', '#....', '.#...', '..#..', '...#.'],
    '+': ['.....', '..#..', '..#..', '#####', '..#..', '..#..', '.....'],
    '#': ['.#.#.', '.#.#.', '#####', '.#.#.', '#####', '.#.#.', '.#.#.'],
}

# Lower case letters are drawn as capitals.


def glyph(ch):
    rows = FONT.get(ch.upper(), FONT['?'])
    g = np.zeros((7, 5), bool)
    for y, r in enumerate(rows):
        for x, c in enumerate(r):
            g[y, x] = c == '#'
    return g


def font_tile(ch, color=3, shadow=1):
    """A character in a tile: the glyph at (1, 0) with a shadow below and
    to its right."""
    t = np.zeros((8, 8), np.uint8)
    g = glyph(ch)
    if shadow:
        t[1:8, 2:7][g] = shadow
    t[0:7, 1:6][g] = color
    return t


# --- Drawing shapes ----------------------------------------------------------

class Canvas:
    """Shapes in meters (y up) drawn around an origin, SUPER times larger."""

    def __init__(self, size_px, angle=0.0, mirror=False):
        self.n = size_px * SUPER
        self.img = Image.new('L', (self.n, self.n), 0)
        self.draw = ImageDraw.Draw(self.img)
        self.c = math.cos(angle)
        self.s = math.sin(angle)
        self.half = self.n / 2.0

    def pt(self, x, y):
        rx = x * self.c - y * self.s
        ry = x * self.s + y * self.c
        k = PPM * SUPER
        return (self.half + rx * k, self.half - ry * k)

    def line(self, pts, width, color):
        p = [self.pt(*q) for q in pts]
        w = max(1, int(round(width * PPM * SUPER)))
        self.draw.line(p, fill=color, width=w, joint='curve')
        r = w / 2.0
        for x, y in (p[0], p[-1]):
            self.draw.ellipse((x - r, y - r, x + r, y + r), fill=color)

    def poly(self, pts, color):
        self.draw.polygon([self.pt(*q) for q in pts], fill=color)

    def circle(self, x, y, r, color, ring=None):
        cx, cy = self.pt(x, y)
        k = PPM * SUPER
        self.draw.ellipse((cx - r * k, cy - r * k, cx + r * k, cy + r * k),
                          fill=color)
        if ring is not None:
            rr = (r - ring) * k
            self.draw.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=0)

    def pixels(self):
        """Reduced to pixels: a pixel gets the color most of it has, if a
        third of it is drawn at all."""
        a = np.array(self.img, np.uint8)
        n = self.n // SUPER
        blocks = a.reshape(n, SUPER, n, SUPER).transpose(0, 2, 1, 3).reshape(n, n, -1)
        out = np.zeros((n, n), np.uint8)
        for c in (1, 2, 3):
            pass
        counts = np.stack([(blocks == c).sum(-1) for c in range(4)], -1)
        drawn = counts[..., 1:].sum(-1)
        best = counts[..., 1:].argmax(-1) + 1
        out[drawn * 3 >= SUPER * SUPER] = best[drawn * 3 >= SUPER * SUPER]
        return out


# Colors of the bike: 1 black, 2 red, 3 light gray. Of the rider: 1 black,
# 2 blue, 3 white.
BLACK, MAIN, LIGHT = 1, 2, 3

# The rider's point is this far above the body when at rest (Kord5y):
RIDER_UP = 0.44


def draw_frame(cv):
    """The bike without its wheels, around the body's center, facing left."""
    # Swing arm and fork:
    cv.line([(0.85, -0.6), (0.12, -0.32)], 0.08, LIGHT)
    cv.line([(-0.85, -0.6), (-0.62, 0.06)], 0.08, LIGHT)
    # Engine and exhaust:
    cv.poly([(-0.36, -0.12), (0.14, -0.12), (0.12, -0.44), (-0.22, -0.46)], BLACK)
    cv.line([(0.05, -0.30), (0.42, -0.24), (0.76, -0.02)], 0.07, LIGHT)
    # Tank and frame:
    cv.poly([(-0.66, 0.06), (-0.2, 0.16), (0.12, 0.08), (0.14, -0.12),
             (-0.42, -0.14)], MAIN)
    # Seat and rear fender:
    cv.poly([(0.02, 0.14), (0.62, 0.11), (0.6, 0.03), (0.06, 0.04)], BLACK)
    cv.poly([(0.5, 0.1), (1.02, 0.02), (1.0, -0.04), (0.5, 0.02)], MAIN)
    # Front fender and handlebar:
    cv.poly([(-1.08, -0.12), (-0.86, -0.04), (-0.62, -0.1), (-0.86, -0.12)], MAIN)
    cv.line([(-0.64, 0.06), (-0.5, 0.2)], 0.07, BLACK)


def draw_rider(cv):
    """The rider around its point, facing left."""
    # Leg: hip, knee, foot on the peg:
    cv.line([(0.1, -0.02), (-0.28, -0.14), (-0.1, -0.56)], 0.13, MAIN)
    cv.line([(-0.1, -0.56), (-0.24, -0.58)], 0.09, BLACK)
    # Body:
    cv.line([(0.1, 0.0), (-0.06, 0.4)], 0.22, MAIN)
    # Arm to the handlebar:
    cv.line([(-0.06, 0.36), (-0.32, 0.12), (-0.5, -0.24)], 0.09, MAIN)
    cv.circle(-0.5, -0.24, 0.05, BLACK)
    # Helmet with its visor:
    cv.circle(-0.09, 0.63, 0.24, LIGHT)
    cv.poly([(-0.33, 0.66), (-0.12, 0.66), (-0.12, 0.56), (-0.33, 0.56)], BLACK)


def draw_wheel(cv, spin):
    cv.circle(0, 0, 0.4, BLACK, ring=0.09)
    cv.circle(0, 0, 0.31, LIGHT, ring=0.04)
    for k in range(4):
        a = spin + k * math.pi / 2
        cv.line([(0, 0), (0.29 * math.cos(a), 0.29 * math.sin(a))], 0.05, LIGHT)
    cv.circle(0, 0, 0.06, BLACK)


def draw_apple(cv):
    cv.circle(0, -0.04, 0.33, 1)
    cv.circle(-0.1, 0.06, 0.08, 3)
    cv.line([(0.0, 0.26), (0.04, 0.38)], 0.05, 2)
    cv.poly([(0.04, 0.3), (0.28, 0.42), (0.18, 0.26)], 2)


def draw_flower(cv):
    cv.line([(0.0, -0.4), (0.0, 0.05)], 0.07, 2)
    cv.poly([(0.0, -0.25), (0.22, -0.12), (0.02, -0.18)], 2)
    for k in range(5):
        a = math.pi / 2 + k * 2 * math.pi / 5
        cv.circle(0.18 * math.cos(a), 0.18 + 0.18 * math.sin(a), 0.12, 1)
    cv.circle(0.0, 0.18, 0.1, 3)


def draw_killer(cv, spin):
    for k in range(8):
        a = spin + k * math.pi / 4
        cv.poly([(0.38 * math.cos(a), 0.38 * math.sin(a)),
                 (0.2 * math.cos(a + 0.35), 0.2 * math.sin(a + 0.35)),
                 (0.2 * math.cos(a - 0.35), 0.2 * math.sin(a - 0.35))], 2)
    cv.circle(0, 0, 0.24, 1)
    cv.circle(-0.08, 0.08, 0.06, 3)


# --- Sprites -------------------------------------------------------------------

def cut(img, cx, cy):
    """Cuts an image into tiles with the grid placed so that the fewest
    tiles are used; returns [(dx, dy, tile)] relative to (cx, cy)."""
    h, w = img.shape
    best = None
    for oy in range(8):
        for ox in range(8):
            parts = []
            for ty in range(-1, h // 8 + 1):
                for tx in range(-1, w // 8 + 1):
                    x0, y0 = tx * 8 + ox, ty * 8 + oy
                    t = np.zeros((8, 8), np.uint8)
                    xa, xb = max(0, x0), min(w, x0 + 8)
                    ya, yb = max(0, y0), min(h, y0 + 8)
                    if xa >= xb or ya >= yb:
                        continue
                    t[ya - y0:yb - y0, xa - x0:xb - x0] = img[ya:yb, xa:xb]
                    if t.any():
                        parts.append((x0 - cx, y0 - cy, t))
            if best is None or len(parts) < len(best):
                best = parts
    return best


class Bank:
    """64 tiles of 1 KB of the CHR-ROM, without repeated tiles."""

    def __init__(self):
        self.tiles = []

    def add(self, t):
        key = t.tobytes()
        for i, u in enumerate(self.tiles):
            if u.tobytes() == key:
                return i
        if len(self.tiles) == 64:
            raise ValueError("a sprite bank is full")
        self.tiles.append(t.copy())
        return len(self.tiles) - 1


def tile_bytes(t):
    t = np.asarray(t, np.uint8)
    lo = np.packbits((t & 1).astype(np.uint8), axis=1)[:, 0]
    hi = np.packbits((t >> 1).astype(np.uint8), axis=1)[:, 0]
    return bytes(lo) + bytes(hi)


def put_bank(chr_rom, bank, tiles, size=64):
    data = b''.join(tile_bytes(t) for t in tiles)
    chr_rom[bank * 1024:bank * 1024 + len(data)] = data


def metasprite(bank, parts):
    return [(dx, dy, bank.add(t)) for dx, dy, t in parts]


def c_metasprite(name, parts):
    vals = [len(parts)] + [v for dx, dy, i in parts for v in (dx, dy, i)]
    return 'static const int8_t %s[] = { %s };\n' % (name, ', '.join(map(str, vals)))


def bike_angles():
    """The frame and the rider at each angle, as metasprites around the
    body's and the rider's point, with their banks."""
    out = []
    for a in range(ANGLES):
        th = 2 * math.pi * a / ANGLES
        bank = Bank()
        cv = Canvas(48, th)
        draw_frame(cv)
        frame = metasprite(bank, cut(cv.pixels(), 24, 24))
        cv = Canvas(40, th)
        draw_rider(cv)
        rider = metasprite(bank, cut(cv.pixels(), 20, 20))
        # metasprite of game.c draws them without checking the edges of the
        # screen when far enough from them for offsets of this range:
        if any(not -24 <= v <= 16 for dx, dy, _ in frame + rider for v in (dx, dy)):
            raise ValueError("a sprite of the bike is off the range of game.c")
        out.append((frame, rider, bank))
    return out


def objects_bank():
    """Wheels, apple, flower and killers in one bank, each 16x16 pixels."""
    bank = Bank()
    sprites = {}
    def add(name, cv):
        img = cv.pixels()
        parts = [(dx, dy, bank.add(img[dy + 8:dy + 16, dx + 8:dx + 16]))
                 for dy in (-8, 0) for dx in (-8, 0)]
        sprites[name] = [p[2] for p in parts]
    for k in range(8):
        cv = Canvas(16)
        draw_wheel(cv, k * math.pi / 16)
        add('wheel%d' % k, cv)
    cv = Canvas(16)
    draw_apple(cv)
    add('apple', cv)
    cv = Canvas(16)
    draw_flower(cv)
    add('flower', cv)
    for k in range(4):
        cv = Canvas(16)
        draw_killer(cv, k * math.pi / 16)
        add('killer%d' % k, cv)
    return bank, sprites


HUD_CHARS = '0123456789:.ABCDEFGHIJKLMNOPQRSTUVWXYZ!-?>'

# Lines of hints under the messages of the game, set closer than the font:
# a line of the screen shows at most 8 sprites.
HUD_LINES = {'Hint_again': 'A/B: AGAIN', 'Hint_menu': 'START: MENU'}


def text_tiles(s, color=3, shadow=1):
    """s in as few tiles as it fits: the glyphs trimmed of their empty
    columns, a pixel apart (their shadow), a space 2 pixels wide, the whole
    centered in the tiles."""
    gs = []
    for ch in s:
        if ch == ' ':
            gs.append(np.zeros((7, 2), bool))
            continue
        g = glyph(ch)
        cols = np.flatnonzero(g.any(axis=0))
        gs.append(g[:, cols[0]:cols[-1] + 1])
    width = sum(g.shape[1] + 1 for g in gs)
    n = -(-width // 8)
    img = np.zeros((8, n * 8), np.uint8)
    x = (n * 8 - width) // 2
    for g in gs:
        w = g.shape[1]
        if shadow:
            img[1:8, x + 1:x + 1 + w][g] = shadow
        img[0:7, x:x + w][g] = color
        x += w + 1
    return [img[:, k * 8:k * 8 + 8] for k in range(n)]


def hud_bank():
    """The bank of the font of the sprites, the tile of each character and
    the tiles of each of HUD_LINES."""
    bank = Bank()
    index = {}
    for ch in HUD_CHARS:
        index[ch] = bank.add(font_tile(ch, 3, 1))
    # An apple for the counter:
    cv = Canvas(8)
    cv2 = Canvas(16)
    draw_apple(cv2)
    small = cv2.pixels()[4:12, 4:12]
    index['@'] = bank.add(small)
    lines = {name: [bank.add(t) for t in text_tiles(s)] for name, s in HUD_LINES.items()}
    return bank, index, lines


MENU_CHARS = ''.join(chr(c) for c in range(32, 96))


def menu_tiles():
    """4 KB of background tiles for the menus: the font at its ASCII codes
    (from 32), a frame and the letters of the title twice as large."""
    tiles = [np.zeros((8, 8), np.uint8) for _ in range(256)]
    for ch in MENU_CHARS:
        tiles[ord(ch)] = font_tile(ch, 3, 1)
    # Dim letters (for locked levels) from 96:
    for ch in MENU_CHARS:
        if ord(ch) + 64 < 160:
            tiles[ord(ch) + 64] = font_tile(ch, 2, 0)
    # Title letters, 2x2 tiles each, from 160:
    title = {}
    nxt = 160
    for ch in 'ELASTOMNI':
        g = glyph(ch)
        big = np.zeros((16, 16), np.uint8)
        for y in range(7):
            for x in range(5):
                if g[y, x]:
                    big[1 + 2 * y:3 + 2 * y, 2 + 2 * x:4 + 2 * x] = 3
                    for yy in (2 + 2 * y, 3 + 2 * y):
                        for xx in (3 + 2 * x, 4 + 2 * x):
                            if yy < 16 and xx < 16 and big[yy, xx] == 0:
                                big[yy, xx] = 1
        for y in range(16):
            for x in range(16):
                if big[y, x] == 3 and (y + x) % 4 == 0:
                    big[y, x] = 2
        title[ch] = nxt
        for ty in range(2):
            for tx in range(2):
                tiles[nxt] = big[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
                nxt += 1
    # A frame: corners and sides, from 240:
    frame = np.zeros((8, 8), np.uint8)
    corner = frame.copy()
    corner[3:5, 3:8] = 2
    corner[3:8, 3:5] = 2
    side_h = frame.copy()
    side_h[3:5, :] = 2
    side_v = frame.copy()
    side_v[:, 3:5] = 2
    tiles[240] = corner
    tiles[241] = side_h
    tiles[242] = np.fliplr(corner)
    tiles[243] = side_v
    tiles[244] = np.flipud(corner)
    tiles[245] = np.flipud(np.fliplr(corner))
    # A cursor:
    cur = np.zeros((8, 8), np.uint8)
    for y in range(7):
        w = 3 - abs(3 - y)
        cur[y, 1:2 + w] = 3
    tiles[246] = cur
    return tiles, title


def preview(path, angles, obank, osprites, hbank):
    """A picture of the sprites with the wheels at rest, to look at them."""
    sky = (100, 176, 236)
    pal = {1: (0, 0, 0), 2: (200, 40, 40), 3: (210, 210, 210)}
    rider_pal = {1: (0, 0, 0), 2: (40, 60, 220), 3: (248, 248, 248)}
    obj_pal = {1: (216, 40, 16), 2: (60, 180, 60), 3: (248, 216, 60)}
    zoom, cell = 3, 52
    cols = 8
    img = Image.new('RGB', (cell * cols * zoom, (cell * 8 + 24) * zoom), sky)
    def put(ox, oy, t, p, flip=False):
        for y in range(8):
            for x in range(8):
                c = t[y, 7 - x if flip else x]
                if c:
                    img.paste(p[c], (ox + x * zoom, oy + y * zoom,
                                     ox + (x + 1) * zoom, oy + (y + 1) * zoom))
    wheel = [obank.tiles[i] for i in osprites['wheel0']]
    for a, (frame, rider, bank) in enumerate(angles):
        cx = (a % cols) * cell + cell // 2
        cy = (a // cols) * cell + cell // 2
        th = 2 * math.pi * a / ANGLES
        def at(x, y):
            return (int(round((x * math.cos(th) - y * math.sin(th)) * PPM)),
                    int(round(-(x * math.sin(th) + y * math.cos(th)) * PPM)))
        for wx, wy in (at(-0.85, -0.6), at(0.85, -0.6)):
            for k, (dx, dy) in enumerate(((-8, -8), (0, -8), (-8, 0), (0, 0))):
                put((cx + wx + dx) * zoom, (cy + wy + dy) * zoom, wheel[k], pal)
        rx, ry = at(0, RIDER_UP)
        for parts, p, bx, by in ((frame, pal, 0, 0), (rider, rider_pal, rx, ry)):
            for dx, dy, i in parts:
                put((cx + bx + dx) * zoom, (cy + by + dy) * zoom, bank.tiles[i], p)
    # The objects and the font below:
    y0 = cell * 8 + 4
    names = ['apple', 'flower', 'killer0', 'killer1', 'killer2', 'killer3'] + \
            ['wheel%d' % k for k in range(8)]
    for n, name in enumerate(names):
        ts = [obank.tiles[i] for i in osprites[name]]
        p = pal if name.startswith(('wheel', 'killer')) else obj_pal
        if name.startswith('killer'):
            p = {1: (0, 0, 0), 2: (216, 40, 16), 3: (248, 248, 248)}
        for k, (dx, dy) in enumerate(((0, 0), (8, 0), (0, 8), (8, 8))):
            put((4 + n * 20 + dx) * zoom, (y0 + dy) * zoom, ts[k], p)
    hud_pal = {1: (60, 60, 60), 2: (200, 40, 40), 3: (248, 248, 248)}
    for n, t in enumerate(hbank.tiles):
        put((4 + n * 9) * zoom, (y0 + 18) * zoom, t, hud_pal)
    img.save(path)


def build(chr_rom, bg_menu, spr_misc, spr_hud, spr_bike, outdir, space):
    angles = bike_angles()
    for a, (frame, rider, bank) in enumerate(angles):
        put_bank(chr_rom, spr_bike + a, bank.tiles)
    obank, osprites = objects_bank()
    put_bank(chr_rom, spr_misc, obank.tiles)
    hbank, hindex, hlines = hud_bank()
    put_bank(chr_rom, spr_hud, hbank.tiles)
    mtiles, title = menu_tiles()
    put_bank(chr_rom, bg_menu, mtiles)
    preview(os.path.join(outdir, 'sprites.png'), angles, obank, osprites, hbank)

    # The metasprites of the bike go into the data banks: a table of 64
    # pairs of offsets (frame, rider) from its start, then the metasprites.
    blobs = []
    for frame, rider, bank in angles:
        for parts in (frame, rider):
            vals = [len(parts)] + [v for dx, dy, i in parts for v in (dx, dy, i)]
            blobs.append(bytes(v & 0xff for v in vals))
    table = bytearray()
    off = 4 * ANGLES
    for b in blobs:
        table += off.to_bytes(2, 'little')
        off += len(b)
    bike_meta = space.place(bytes(table) + b''.join(blobs))
    with open(os.path.join(outdir, 'sprites.c'), 'w') as f:
        f.write('// Generated by gfx.py: the sprites.\n#include "sprites.h"\n\n')
        f.write('const uint32_t Bike_meta = %d;\n\n' % bike_meta)
        def arr(name, vals):
            f.write('const uint8_t %s[] = { %s };\n' % (name, ', '.join(map(str, vals))))
        # Tiles of the objects, top left, top right, bottom left, bottom
        # right, in the second sprite bank (from 64):
        arr('Wheel_tiles', [64 + t for k in range(8) for t in osprites['wheel%d' % k]])
        arr('Apple_tiles', [64 + t for t in osprites['apple']])
        arr('Flower_tiles', [64 + t for t in osprites['flower']])
        arr('Killer_tiles', [64 + t for k in range(4) for t in osprites['killer%d' % k]])
        # Characters of the sprite font, in the third bank (from 128):
        codes = [0] * 96
        for ch, i in hindex.items():
            codes[ord(ch) - 32] = 128 + i
        for ch in 'abcdefghijklmnopqrstuvwxyz':
            codes[ord(ch) - 32] = 128 + hindex[ch.upper()]
        arr('Hud_font', codes)
        # The lines of hints: their number of tiles, then the tiles:
        for name, ts in hlines.items():
            arr(name, [len(ts)] + [128 + t for t in ts])
    with open(os.path.join(outdir, 'chrmap.h'), 'w') as f:
        f.write('// Generated by build.py: the banks of the CHR-ROM.\n')
        f.write('#define CHR_BG_COMMON 0\n#define CHR_BG_MENU %d\n' % bg_menu)
        f.write('#define CHR_SPR_MISC %d\n#define CHR_SPR_HUD %d\n' % (spr_misc, spr_hud))
        f.write('#define CHR_SPR_BIKE %d\n' % spr_bike)
        f.write('#define MENU_FRAME 240\n#define MENU_CURSOR 246\n')
        f.write('#define MENU_DIM 64\n')
        for ch, i in title.items():
            f.write('#define TITLE_%s %d\n' % (ch, i))
