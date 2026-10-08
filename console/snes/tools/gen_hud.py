"""Writes build/gen/hud.asm and hud.inc: the pictures of the time digits
and of the view box (the map of the level at the bottom of the screen),
drawn by src/hud.asm.

  gen_hud.py ELMA_RES ELMA_LGR OUT_DIR [--test]

--test also writes hud_test.asm, the data of the test ROM (test/snes_hud.c):
the objects of a few levels and a path of the bike through each.

The view box of the original (KIRAJ320.CPP kiview) shows the level at
Aranyalap/Viewzoom = 4.8 pixels a meter in a 140x70 window; 0.4 of it is a
56x28 window at 1.92 pixels a meter. Here the view pixels are exactly a
tenth of the level pixels (levgeom.py): u = (x - org_x) * VPM,
v = (org_y - y) * VPM. A view pixel is sky when at least half of it is
inside the level (an odd number of polygons around it, grass polygons left
out, as ECSET.CPP fills the view), measured with 4x4 samples.

The map of a level is stored column by column: a column is 8 view pixels
wide, one word a row in the format of a row of a 2-bit tile (plane 0, plane
1): 1 ground, 2 sky, 3 an apple (the original's ring at 0.4 is a pixel).
Killers are pixels of ground: the original draws them black, the colors of
a BG3 palette are taken by ground, sky and apples, and the dark ground is
the closest. A row range of a column is copied by DMA. The apples are also
listed with the color under them, for the ones eaten (hud.asm).
"""

import math
import os
import sys

import numpy as np

import elmadata
import levgeom
from config import BANK_SIZE
from lgr import Lgr

VPM = levgeom.PX_PER_M_NUM / 2560.0     # view pixels a meter (1.9199...)
VIEW_W, VIEW_H = 56, 28                 # 0.4 of the original's 140x70
VIEW_X0 = 16                            # 0.4 of Viewxorig (40)
VIEW_XRANGE = 168                       # 0.4 of Viewxtolas (420)
VIEW_Y = 195                            # first row of the window on the screen
# The bike's place in the window: 20%..80% of its width (szeltoltav), the
# middle row (the original's ring is at row 34 of 70 from the top):
BIKE_ROW = 13
PAD_ROWS = 16                           # rows above and below the level
SUBSAMPLE = 4

# Time digits (DIGIT.CPP kidigit at 0.4): 1-pixel lines, digits 5x15.
TIME_Y = 10
TIME_X = (11, 197)                      # 0.4 of 28 and 640 - 148
DIGIT_X = (0, 6, 16, 22, 32, 38)
COLON_DX = 7                            # from the digit before the colon
COLON_ROWS = (4, 10)
SEG_H, SEG_V = 3, 6

# Sprite tiles (the second name table, VRAM $7000): a sheet of 16x8 tiles.
# The frame of the view box is a 64x32 block (two 32x32 sprites) in the
# columns 0-7 of rows 0-3; the other 24 places are 16x16 sprites whose
# right half is empty: the 10 digits, the 10 digits with a colon after them,
# and the dots of the view box.
FRAME_TILE = 0
SLOT_TILES = [8, 10, 12, 14, 40, 42, 44, 46] + \
    [64 + 2 * i for i in range(8)] + [96 + 2 * i for i in range(8)]
SLOT_COLON = 10
SLOT_DOT = 20                           # the bike's, the flower's
# OBJ palette 7: digits black (over the sky), palette 6: white (over the
# ground, the original's negative); the other colors are the view box's.
C_DIGIT, C_FRAME, C_BIKE, C_FLOWER = 1, 2, 3, 4
# Sprite attributes: priority 3, the second name table, palette 6 or 7.
ATTR_WHITE, ATTR_BLACK = 0x3D, 0x3F

SEGS = {'0': (4, 0, 1, 2, 3, 6), '1': (1, 3), '2': (4, 0, 5, 3, 6),
        '3': (4, 1, 5, 3, 6), '4': (1, 5, 2, 3), '5': (4, 1, 5, 2, 6),
        '6': (4, 0, 1, 5, 2, 6), '7': (1, 3, 6), '8': (4, 0, 1, 5, 2, 3, 6),
        '9': (4, 1, 5, 2, 3, 6)}

# Warm Up, Steep Corner (killers), Haircut and Apple Harvest (apples):
TEST_LEVELS = (0, 31, 38, 53)
TEST_FRAMES = 900
TEST_SPEED = 12.0                       # meters a second of the fake bike


def glyph(c):
    """Pixels (x, y from the top) of a digit; the segments are numbered as
    in DIGIT.CPP (0-3 vertical, 4 bottom, 5 middle, 6 top; its picture is
    upside down)."""
    H, V = SEG_H, SEG_V
    out = []
    for s in SEGS[c]:
        if s == 6:
            out += [(1 + i, 0) for i in range(H)]
        elif s == 5:
            out += [(1 + i, V + 1) for i in range(H)]
        elif s == 4:
            out += [(1 + i, 2 * V + 2) for i in range(H)]
        elif s == 2:
            out += [(0, 1 + i) for i in range(V)]
        elif s == 3:
            out += [(H + 1, 1 + i) for i in range(V)]
        elif s == 0:
            out += [(0, V + 2 + i) for i in range(V)]
        elif s == 1:
            out += [(H + 1, V + 2 + i) for i in range(V)]
    return out


def digit_u(r, t, k):
    """The view column under the middle of digit k of time t (0 best, 1
    now), less cam_x // 10, for r = cam_x % 10."""
    return (r + TIME_X[t] + DIGIT_X[k] + 2) // 10


def ido2string(hs):
    """The time as the original shows it (BESTTIME.CPP), 59:59:99 at most."""
    if hs >= 360000:
        return '59:59:99'
    return '%02d:%02d:%02d' % (hs // 6000, hs // 100 % 60, hs % 100)


# ---------------------------------------------------------------------------
# Colors

def colors(lgr):
    """The colors of the view box (qcolors.pcx, LGRFILE.CPP) and of the time
    (the brightest and darkest of the palette, makenegalttomb), 8-bit RGB."""
    pal = lgr.palette()
    q = lgr['qcolors'].image
    names = ['ground', 'sky', 'frame', 'time', 'bike', 'bike2', 'flower',
             'apple', 'killer']
    out = {n: pal[q.getpixel((6, 6 + i * 12))] for i, n in enumerate(names)}
    s = [sum(p) for p in pal]
    out['bright'] = pal[s.index(max(s))]
    out['dark'] = pal[s.index(min(s))]
    return out


def bgr15(c):
    r, g, b = (v >> 3 for v in c)
    return r | g << 5 | b << 10


# ---------------------------------------------------------------------------
# The map of a level

def level_polys(lev):
    return [np.array(p, float) for g, p in lev.polygons if not g]


def sky_rows(polys, ys, xs):
    """Inside (odd number of polygons) of the points xs x ys (meters):
    a len(ys) x len(xs) array of 0/1."""
    x1 = np.concatenate([p[:, 0] for p in polys])
    y1 = np.concatenate([p[:, 1] for p in polys])
    x2 = np.concatenate([np.roll(p[:, 0], -1) for p in polys])
    y2 = np.concatenate([np.roll(p[:, 1], -1) for p in polys])
    out = np.zeros((len(ys), len(xs)), np.uint8)
    for i, y in enumerate(ys):
        m = (y1 > y) != (y2 > y)
        xi = x1[m] + (y - y1[m]) * (x2[m] - x1[m]) / (y2[m] - y1[m])
        xi.sort()
        out[i] = np.searchsorted(xi, xs) & 1
    return out


class LevelMap:
    """The view pixels of a level that are stored: byte columns
    xmin..xmin+ncols-1, rows vmin..vmin+nrows-1. Everything outside is
    ground."""

    def __init__(self, lev):
        self.lev = lev
        ox, oy = levgeom.origin(lev)
        self.ox, self.oy = ox / 65536.0, oy / 65536.0
        polys = level_polys(lev)
        x0 = min(p[:, 0].min() for p in polys)
        x1 = max(p[:, 0].max() for p in polys)
        y0 = min(p[:, 1].min() for p in polys)
        y1 = max(p[:, 1].max() for p in polys)
        self.xmin = int(math.floor((x0 - self.ox) * VPM)) // 8
        self.ncols = int(math.floor((x1 - self.ox) * VPM)) // 8 - self.xmin + 1
        self.vmin = int(math.floor((self.oy - y1) * VPM)) - PAD_ROWS
        self.nrows = int(math.floor((self.oy - y0) * VPM)) + PAD_ROWS - self.vmin + 1
        w, h = self.ncols * 8, self.nrows
        ss = SUBSAMPLE
        us = self.xmin * 8 + (np.arange(w * ss) + 0.5) / ss
        vs = self.vmin + (np.arange(h * ss) + 0.5) / ss
        sky = sky_rows(polys, self.oy - vs / VPM, self.ox + us / VPM)
        sky = sky.reshape(h, ss, w, ss).mean(axis=(1, 3))
        # 1 ground, 2 sky; killers ground, 3 apples (with what is under):
        self.pix = np.where(sky >= 0.5, 2, 1).astype(np.uint8)
        self.apples = []
        for t, x, y, _, _ in lev.objects:
            if t in (elmadata.T_KILLER, elmadata.T_APPLE):
                u, v = view_px(self, x, y)
                c, r = u - self.xmin * 8, v - self.vmin
                under = 1
                if 0 <= c < w and 0 <= r < h:
                    under = int(self.pix[r, c])
                    if t == elmadata.T_KILLER:
                        self.pix[r, c] = 1
                if t == elmadata.T_APPLE:
                    self.apples.append((u, v, under))
        for u, v, under in self.apples:
            c, r = u - self.xmin * 8, v - self.vmin
            if 0 <= c < w and 0 <= r < h:
                self.pix[r, c] = 3

    def at(self, u, v):
        """Color index of a view pixel (1 ground, 2 sky, 3 apple)."""
        c, r = u - self.xmin * 8, v - self.vmin
        if 0 <= c < self.ncols * 8 and 0 <= r < self.nrows:
            return int(self.pix[r, c])
        return 1

    def column(self, x):
        """The words of a byte column, as bytes (plane 0, plane 1 a row)."""
        p = self.pix[:, (x - self.xmin) * 8:(x - self.xmin) * 8 + 8]
        bits = 1 << (7 - np.arange(8))
        p0 = ((p & 1) * bits).sum(axis=1)
        p1 = ((p >> 1) * bits).sum(axis=1)
        return np.stack([p0, p1], axis=1).astype(np.uint8).tobytes()


def view_px(m, x, y):
    """The view pixel of a point (meters), as hud.asm computes it."""
    return fx_view(int(round((x - m.ox) * 65536))), fx_view(int(round((m.oy - y) * 65536)))


def fx_view16(d):
    """A 16.16 distance from the origin in sixteenths of a view pixel, as
    hud.asm computes it: n = d >> 12 (sixteenths of a meter), 2n - 41n/512."""
    n = d >> 12
    return 2 * n - ((n * 41) >> 9)


def fx_view(d):
    return fx_view16(d) >> 4


def window(m, x, y, baljobb):
    """The window of the view box for the bike's body at (x, y) meters and
    baljobb 0..65535, as hud.asm computes it: the view pixel of its top
    left corner, the column of the window on the screen and the bike's dot
    in the window."""
    ub = fx_view16(int(round((x - m.ox) * 65536)))
    vb = fx_view16(int(round((m.oy - y) * 65536)))
    off = bike_offset16(baljobb)
    u0 = (ub - off) >> 4
    v0 = (vb >> 4) - BIKE_ROW
    vx = VIEW_X0 + (((baljobb >> 8) * VIEW_XRANGE) >> 8)
    return u0, v0, vx, off >> 4


def bike_offset16(baljobb):
    """11.2 + 33.6 * baljobb pixels in sixteenths (0.4 of the original's
    140 * (0.2 + 0.6 * baljobb)), from the high byte of baljobb."""
    b = baljobb >> 8
    return 179 + 2 * b + ((b * 26) >> 8)


# ---------------------------------------------------------------------------
# Sprite tiles

def tile4(pix):
    """An 8x8 tile of 4 bits from an 8x8 array of color indices."""
    out = bytearray(32)
    for y in range(8):
        for x in range(8):
            c = int(pix[y][x])
            for p in range(4):
                if c >> p & 1:
                    out[(p >> 1) * 16 + y * 2 + (p & 1)] |= 0x80 >> x
    return bytes(out)


def sprite_sheet():
    sheet = np.zeros((64, 128), np.uint8)       # 8 rows x 16 tiles
    # The frame: 58x30 around the 56x28 window.
    fw, fh = VIEW_W + 2, VIEW_H + 2
    fy, fx = (FRAME_TILE // 16) * 8, (FRAME_TILE % 16) * 8
    sheet[fy, fx:fx + fw] = C_FRAME
    sheet[fy + fh - 1, fx:fx + fw] = C_FRAME
    sheet[fy:fy + fh, fx] = C_FRAME
    sheet[fy:fy + fh, fx + fw - 1] = C_FRAME

    def slot(i):
        t = SLOT_TILES[i]
        return (t // 16) * 8, (t % 16) * 8

    for d in range(10):
        for colon in (0, 1):
            y, x = slot(d + colon * SLOT_COLON)
            for a, b in glyph(str(d)):
                sheet[y + b, x + a] = C_DIGIT
            if colon:
                for r in COLON_ROWS:
                    sheet[y + r, x + COLON_DX] = C_DIGIT
    for i, c in enumerate((C_BIKE, C_FLOWER)):
        y, x = slot(SLOT_DOT + i)
        sheet[y, x] = c
    data = b''
    for ty in range(8):
        for tx in range(16):
            data += tile4(sheet[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8])
    return data


# ---------------------------------------------------------------------------
# The fake bike of the test ROM

def test_path(lev):
    """Frames of a bike riding from the start through the apples (nearest
    first) to the flower: (x, y, baljobb, eaten object index or -1) a frame,
    and the objects. baljobb turns as the original's over 0.5 game time
    units (1.14 s) when the direction changes."""
    objs = list(lev.objects)
    sx, sy = lev.start()
    pos = np.array([sx + 0.85, sy + 0.6])
    todo = [i for i, o in enumerate(objs) if o[0] == elmadata.T_APPLE]
    flower = [i for i, o in enumerate(objs) if o[0] == elmadata.T_FLOWER][0]
    route = []
    p = pos.copy()
    while todo:
        j = min(todo, key=lambda i: np.hypot(objs[i][1] - p[0], objs[i][2] - p[1]))
        todo.remove(j)
        route.append(j)
        p = np.array(objs[j][1:3])
    route.append(flower)
    frames = []
    bj = 65535.0                # facing left at the start
    face_left = True
    step = TEST_SPEED / 60.0
    turn = 65536.0 / (0.5 / 0.4368 * 60)
    for j in route:
        target = np.array(objs[j][1:3])
        while len(frames) < TEST_FRAMES:
            d = target - pos
            dist = np.hypot(*d)
            if abs(d[0]) > 0.5:
                face_left = d[0] < 0
            bj = min(65535.0, bj + turn) if face_left else max(0.0, bj - turn)
            eaten = -1
            if dist <= step:
                pos = target.copy()
                eaten = j if objs[j][0] == elmadata.T_APPLE else -1
            else:
                pos = pos + d / dist * step
            frames.append((pos[0], pos[1], int(bj), eaten))
            if eaten >= 0 or dist <= step:
                break
    while len(frames) < TEST_FRAMES:
        frames.append((pos[0], pos[1], int(bj), -1))
    return frames


def test_camera(lev, x, y):
    """A camera with the bike in the middle of the screen (level pixels)."""
    ox, oy = levgeom.origin(lev)
    px = ((int(round(x * 65536)) - ox) * levgeom.PX_PER_M_NUM) >> 24
    py = ((oy - int(round(y * 65536))) * levgeom.PX_PER_M_NUM) >> 24
    w, h = levgeom.size_px(lev)
    return max(0, min(w - 256, px - 128)), max(0, min(h - 224, py - 112))


def test_levels(levels):
    """The levels of the test ROM that the elma.res has (the shareware has
    10): TEST_LEVELS, else the first ones."""
    tl = [i for i in TEST_LEVELS if i < len(levels)]
    return tl if len(tl) == len(TEST_LEVELS) else list(range(min(4, len(levels))))


def write_test(levels, out):
    """The data of the test ROM: hud_test_count levels (hud_test_levels),
    their objects (hud_test_nobjs, hud_test_objs: type, animation, 2 bytes
    of padding, x, y) and TEST_FRAMES frames of the fake bike
    (hud_test_path: x, y, baljobb, camera x, y, the apple eaten or 255, a
    byte of padding), laid out as 816-tcc lays out the structures of
    test/snes_hud.c (32-bit fields on 4 bytes)."""
    tl = test_levels(levels)
    n = len(tl)
    a = ['; Generated by tools/gen_hud.py: the data of the test ROM.',
         '.include "hdr.asm"', '',
         '.SECTION ".hud_test_levels" SUPERFREE',
         'hud_test_count:', '\t.dw %d' % n,
         'hud_test_frames:', '\t.dw %d' % TEST_FRAMES,
         'hud_test_levels:', '\t.dw %s' % ', '.join(str(i) for i in tl),
         'hud_test_nobjs:',
         '\t.dw %s' % ', '.join(str(len(levels[i].objects)) for i in tl),
         'hud_test_objs:']
    a += ['\t.dl hud_test_o%d\n\t.db 0' % k for k in range(n)]
    a.append('hud_test_path:')
    a += ['\t.dl hud_test_p%d\n\t.db 0' % k for k in range(n)]
    a.append('.ENDS')
    for k, li in enumerate(tl):
        lev = levels[li]
        a += ['', '.SECTION ".hud_test_o%d" SUPERFREE' % k, 'hud_test_o%d:' % k]
        for t, x, y, g, anim in lev.objects:
            a.append('\t.db %d, %d, 0, 0\n\t.dd %d, %d' % (
                t, anim, int(round(x * 65536)), int(round(y * 65536))))
        a.append('.ENDS')
        a += ['.SECTION ".hud_test_p%d" SUPERFREE' % k, 'hud_test_p%d:' % k]
        for x, y, bj, e in test_path(lev):
            cx, cy = test_camera(lev, x, y)
            a.append('\t.dd %d, %d\n\t.dw %d, %d, %d\n\t.db %d, 0' % (
                int(round(x * 65536)), int(round(y * 65536)), bj, cx, cy,
                e if e >= 0 else 255))
        a.append('.ENDS')
    with open(os.path.join(out, 'hud_test.asm'), 'w') as f:
        f.write('\n'.join(a) + '\n')


# ---------------------------------------------------------------------------

def main():
    res, lgr_path, out = sys.argv[1:4]
    levels = elmadata.internal_levels(elmadata.Resource(res))
    col = colors(Lgr(lgr_path))
    os.makedirs(out, exist_ok=True)

    inc = ['; Generated by tools/gen_hud.py.',
           '.DEFINE HUD_LEVELS %d' % len(levels),
           '.DEFINE HUD_VIEW_W %d' % VIEW_W, '.DEFINE HUD_VIEW_H %d' % VIEW_H,
           '.DEFINE HUD_VIEW_X0 %d' % VIEW_X0, '.DEFINE HUD_VIEW_XRANGE %d' % VIEW_XRANGE,
           '.DEFINE HUD_VIEW_Y %d' % VIEW_Y, '.DEFINE HUD_BIKE_ROW %d' % BIKE_ROW,
           '.DEFINE HUD_TIME_Y %d' % TIME_Y,
           '.DEFINE HUD_TIME_X0 %d' % TIME_X[0], '.DEFINE HUD_TIME_X1 %d' % TIME_X[1],
           '.DEFINE HUD_FRAME_TILE %d' % FRAME_TILE,
           '.DEFINE HUD_SLOT_COLON %d' % SLOT_COLON,
           '.DEFINE HUD_TILE_BIKE %d' % SLOT_TILES[SLOT_DOT],
           '.DEFINE HUD_TILE_FLOWER %d' % SLOT_TILES[SLOT_DOT + 1]]
    a = ['; Generated by tools/gen_hud.py from %s and %s.' % (
        os.path.basename(res), os.path.basename(lgr_path)),
        '.include "hdr.asm"', '']

    # Sprite tiles, the place of the 16x16 sprites in them, colors.
    sheet = sprite_sheet()
    a += ['.SECTION ".hud_sprites" SUPERFREE', 'hud_sprite_tiles:']
    for i in range(0, len(sheet), 32):
        a.append('\t.db ' + ', '.join(str(b) for b in sheet[i:i + 32]))
    a.append('hud_slot_tiles:')
    a.append('\t.db ' + ', '.join(str(t) for t in SLOT_TILES))
    # BG colors 0-3 (backdrop, ground, sky, apple), OBJ palettes 6 and 7:
    a.append('hud_bg_colors:')
    a.append('\t.dw %d, %d, %d, %d' % (0, bgr15(col['ground']), bgr15(col['sky']),
                                       bgr15(col['apple'])))
    for name, digit in (('hud_obj_colors_white', 'bright'), ('hud_obj_colors_black', 'dark')):
        pal = [0] * 16
        pal[C_DIGIT] = bgr15(col[digit])
        pal[C_FRAME] = bgr15(col['frame'])
        pal[C_BIKE] = bgr15(col['bike'])
        pal[C_FLOWER] = bgr15(col['flower'])
        a.append(name + ':')
        a.append('\t.dw ' + ', '.join(str(c) for c in pal))
    # Two decimal digits of 0..99 (tens in the high nibble), n / 10 of 0..255:
    a.append('hud_bcd:')
    for i in range(0, 100, 20):
        a.append('\t.db ' + ', '.join(str((n // 10) << 4 | n % 10) for n in range(i, i + 20)))
    a.append('hud_div10:')
    for i in range(0, 256, 32):
        a.append('\t.db ' + ', '.join(str(n // 10) for n in range(i, i + 32)))
    # The colors of the digits of a time (bit k: digit k is white) by the
    # remainder of cam_x / 10 and five pixels of the map from the one under
    # the first digit (bit 4: that one).
    a.append('hud_colmask:')
    for t in range(2):
        for r in range(10):
            row = []
            for m in range(32):
                mask = 0
                for k in range(6):
                    j = digit_u(r, t, k) - digit_u(r, t, 0)
                    if m >> (4 - j) & 1:
                        mask |= 1 << k
                row.append(mask)
            a.append('\t.db ' + ', '.join(str(v) for v in row))
    # The attributes of six digits by their colors (bit k: digit k white,
    # OBJ palette 6, else palette 7), in the high byte of a word:
    a.append('hud_attrtab:')
    for mask in range(64):
        a.append('\t.dw ' + ', '.join(
            str((ATTR_WHITE if mask >> k & 1 else ATTR_BLACK) << 8) for k in range(6)))
    # A column of ground for the parts of the window outside the level:
    a.append('hud_ground_column:')
    a.append('\t.db ' + ', '.join(['255, 0'] * VIEW_H))
    a.append('.ENDS')

    # The maps, packed into sections of at most a bank, a column never
    # crossing one:
    sec = []
    sec_size = 0
    nsec = 0
    level_cols = []
    total = 0

    def flush():
        nonlocal sec, sec_size, nsec
        if sec:
            a.extend(['', '.SECTION ".hud_map%d" SUPERFREE' % nsec, 'hud_map%d:' % nsec] + sec +
                     ['.ENDS'])
            nsec += 1
        sec, sec_size = [], 0

    for li, lev in enumerate(levels):
        m = LevelMap(lev)
        cols = []
        for x in range(m.xmin, m.xmin + m.ncols):
            data = m.column(x)
            if sec_size + len(data) > BANK_SIZE:
                flush()
            cols.append('hud_map%d+%d' % (nsec, sec_size))
            for i in range(0, len(data), 64):
                sec.append('\t.db ' + ', '.join(str(b) for b in data[i:i + 64]))
            sec_size += len(data)
            total += len(data)
        level_cols.append((m, cols))
    flush()

    # A level (16 bytes): first column, columns, first row, rows, the table
    # of its columns (24-bit addresses and a byte of padding), the table of
    # its apples (u, v, color under it; ended by $FFFF).
    a += ['', '.SECTION ".hud_levels" SUPERFREE', 'hud_levels:']
    for li, (m, cols) in enumerate(level_cols):
        a.append('\t.dw %d, %d, %d, %d\n\t.dl hud_cols%d\n\t.db 0\n'
                 '\t.dl hud_apples%d\n\t.db 0' % (
                     m.xmin, m.ncols, m.vmin & 0xFFFF, m.nrows, li, li))
    a.append('.ENDS')
    for li, (m, cols) in enumerate(level_cols):
        a += ['.SECTION ".hud_apples%d" SUPERFREE' % li, 'hud_apples%d:' % li]
        for u, v, under in m.apples:
            a.append('\t.dw %d, %d, %d' % (u, v, under))
        a += ['\t.dw $FFFF', '.ENDS']
    for li, (m, cols) in enumerate(level_cols):
        a += ['.SECTION ".hud_cols%d" SUPERFREE' % li, 'hud_cols%d:' % li]
        for c in cols:
            a.append('\t.dl %s\n\t.db 0' % c)
        a.append('.ENDS')

    with open(os.path.join(out, 'hud.asm'), 'w') as f:
        f.write('\n'.join(a) + '\n')
    with open(os.path.join(out, 'hud.inc'), 'w') as f:
        f.write('\n'.join(inc) + '\n')
    sys.stderr.write('gen_hud: maps of %d levels, %d bytes\n' % (len(levels), total))
    if '--test' in sys.argv[4:]:
        write_test(levels, out)


if __name__ == '__main__':
    main()
