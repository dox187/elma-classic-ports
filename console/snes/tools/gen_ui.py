"""Writes build/gen/ui_data.asm and ui_data.h: the pictures and the font of
the menus of the original game (MENUKEP.CPP, ABC8.CPP, ANIM.CPP,
TELJES.CPP) from elma.res, scaled by 0.4 for the SNES.

  gen_ui.py ELMA_RES OUT_DIR

The menus of the game are drawn on a 640x480 picture, or on a taller one
with the same things centered (Menueltolasy). The SNES screen is that
taller picture of 640x560 scaled by 0.4: 256x224.

- The background: szoveg1.pcx tiled as kirajzol does it, 4 bits.
- The font: the letters of menu.abc scaled by 0.4, 2 bits (3 colors).
- The helmet that marks the chosen row: the 50 frames of sisak.pcx with the
  red line korrigal draws above them, 16x17 pixels.
- The balls of the animated menus (GOLYOK.CPP): circles of the three sizes
  with the two small circles in them, at 16 angles of half a turn
  (clockwise on the screen, as the original turns them).
- The intro picture: intro.pcx with the version written over as teljes
  does it, 4 bits in a few palettes.
"""

import io
import math
import os
import struct
import sys

import numpy as np
from PIL import Image

import elmadata

SCALE = 0.4
# The taller picture of the menus that the SNES screen shows (MENUKEP.CPP:
# Menuysize; ui.c puts the things placed for 640x480 40 lines lower):
MENU_W, MENU_H = 640, 560
SCREEN_W, SCREEN_H = 256, 224

# The space between the letters of menu.abc (initmenukep1: settav( 2 )):
FONT_TAV = 2
# The places a letter can start at in a column of 8 pixels: x of the
# original menus mod 20 (0.4 x mod 8), and the columns a letter may cover.
FONT_POSITIONS = 20
GLYPH_COLUMNS = 3

# Angles of the balls in half a turn (they look the same after it):
BALL_ANGLES = 16
BALL_RADII = (24, 30, 50)          # kitoltgolyokat, PC pixels

# BG palettes of the background and of the intro picture (its tiles are in
# front of the sprites, the background behind them):
BG_PAL = 2
INTRO_PAL = 4


# -- colors and tiles -------------------------------------------------------

def to555(rgb):
    r, g, b = (min(31, int(round(c * 31 / 255.0))) for c in rgb)
    return r | (g << 5) | (b << 10)


def from555(c):
    return tuple(int(round(((c >> s) & 31) * 255 / 31.0)) for s in (0, 5, 10))


def kmeans(pixels, k, iters=30, seed=1):
    """Colors (k, 3) for the pixels (n, 3), Lloyd's algorithm from spread
    starting points."""
    pixels = np.asarray(pixels, float)
    uniq = np.unique(pixels, axis=0)
    if len(uniq) <= k:
        return uniq
    rng = np.random.default_rng(seed)
    # k-means++ start:
    cent = [pixels[rng.integers(len(pixels))]]
    for _ in range(1, k):
        d = np.min(((pixels[:, None, :] - np.array(cent)[None]) ** 2).sum(-1), axis=1)
        if d.sum() == 0:
            break
        cent.append(pixels[rng.choice(len(pixels), p=d / d.sum())])
    cent = np.array(cent)
    for _ in range(iters):
        lab = ((pixels[:, None, :] - cent[None]) ** 2).sum(-1).argmin(1)
        new = np.array([pixels[lab == i].mean(0) if (lab == i).any() else cent[i]
                        for i in range(len(cent))])
        if np.allclose(new, cent):
            break
        cent = new
    return cent


def nearest(pixels, colors):
    return ((np.asarray(pixels, float)[..., None, :] - colors) ** 2).sum(-1).argmin(-1)


def tile_4bpp(t):
    """32 bytes of an 8x8 tile of color numbers 0-15."""
    out = bytearray(32)
    for y in range(8):
        for x in range(8):
            v = int(t[y][x])
            bit = 0x80 >> x
            for p in range(4):
                if v & (1 << p):
                    out[(p >> 1) * 16 + y * 2 + (p & 1)] |= bit
    return bytes(out)


def area_scale(rgba, scale, phase=(0.0, 0.0), size=None):
    """Scales an RGBA float picture (h, w, 4) by averaging the area each
    target pixel covers; returns colors (premultiplied back) and coverage.
    phase moves the picture right/down in target pixels."""
    h, w = rgba.shape[:2]
    if size is None:
        size = (int(math.ceil(w * scale + phase[0])), int(math.ceil(h * scale + phase[1])))
    tw, th = size
    # Weights of the source columns/rows in each target column/row:
    def weights(n_src, n_dst, ph):
        m = np.zeros((n_dst, n_src))
        for t in range(n_dst):
            a = (t - ph) / scale
            b = (t + 1 - ph) / scale
            for s in range(max(0, int(math.floor(a))), min(n_src, int(math.ceil(b)))):
                m[t, s] = max(0.0, min(s + 1, b) - max(s, a)) * scale
        return m
    wx = weights(w, tw, phase[0])
    wy = weights(h, th, phase[1])
    alpha = rgba[..., 3]
    prem = rgba[..., :3] * alpha[..., None]
    cov = wy @ alpha @ wx.T
    col = np.stack([wy @ prem[..., c] @ wx.T for c in range(3)], -1)
    with np.errstate(invalid='ignore', divide='ignore'):
        col = np.where(cov[..., None] > 0, col / cov[..., None], 0)
    return col, cov


def pal_image(img, pal=None):
    """RGB float array of a mode P picture with its palette (or pal)."""
    p = np.array((pal or img.getpalette())[:768] + [0] * 768, float)[:768].reshape(-1, 3)
    return p[np.array(img)]


# -- the pictures of elma.res ----------------------------------------------

class Res:
    def __init__(self, path):
        self.res = elmadata.Resource(path)
        self.intro = Image.open(io.BytesIO(self.res.read('intro.pcx')))
        self.intro.load()
        # The palette of the menus is that of intro.pcx (initmenukep2):
        self.pal = self.intro.getpalette()[:768]

    def pcx(self, name):
        im = Image.open(io.BytesIO(self.res.read(name)))
        im.load()
        return im


def menu_background(res):
    """The background of the menus at 640x560 (szoveglista::kirajzol)."""
    tile = res.pcx('szoveg1.pcx')
    img = Image.new('P', (MENU_W, MENU_H), 0)
    img.putpalette(res.pal)
    y = -47
    kezdox = 0
    while y < MENU_H:
        x = kezdox
        kezdox += 110
        while x > 0:
            x -= tile.width
        while x < MENU_W:
            img.paste(tile, (x, y))
            x += tile.width
        y += tile.height
    return pal_image(img, res.pal)


def gen_background(res):
    rgb = menu_background(res)
    rgba = np.concatenate([rgb, np.ones(rgb.shape[:2] + (1,))], -1)
    col, _ = area_scale(rgba, SCALE, size=(SCREEN_W, SCREEN_H))
    pix = col.reshape(-1, 3)
    colors = kmeans(np.round(pix / 255 * 31) * 255 / 31, 15)
    colors = np.array([from555(to555(c)) for c in colors], float)
    idx = nearest(col, colors) + 1          # color 0 stays transparent
    tiles, tmap = [], []
    known = {tile_4bpp(np.zeros((8, 8))): 0}
    tiles.append(tile_4bpp(np.zeros((8, 8))))
    for ty in range(SCREEN_H // 8):
        for tx in range(32):
            t = tile_4bpp(idx[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8])
            if t not in known:
                known[t] = len(tiles)
                tiles.append(t)
            tmap.append(known[t] | BG_PAL << 10)
    tmap += [BG_PAL << 10] * (32 * 32 - len(tmap))
    pal = [0] + [to555(c) for c in colors]
    return b''.join(tiles), tmap, pal


# -- the font ---------------------------------------------------------------

def parse_abc(data):
    """The letters of an .abc file (ABC8.CPP): {code: (y, rows, mask)}."""
    if data[:3] != b'RA1':
        raise ValueError('not an abc file')
    n = struct.unpack_from('<h', data, 4)[0]
    p = 6
    letters = {}
    for _ in range(n):
        if data[p:p + 6] != b'EGYMIX':
            raise ValueError('broken abc file')
        p += 7
        code = data[p]
        y = struct.unpack_from('<h', data, p + 1)[0]
        p += 3
        if data[p] != 0x2d:
            raise ValueError('broken sprite in abc file')
        w, h = struct.unpack_from('<HH', data, p + 1)
        p += 5
        rows = np.frombuffer(data, np.uint8, w * h, p).reshape(h, w)
        p += w * h
        if data[p:p + 6] != b'SPRITE':
            raise ValueError('broken sprite in abc file')
        size = struct.unpack_from('<H', data, p + 7)[0]
        p += 9
        mask = np.zeros((h, w), bool)
        b = p
        for yy in range(h):
            x = 0
            while x < w:
                cmd, k = data[b], data[b + 1]
                b += 2
                if cmd == ord('K'):
                    mask[yy, x:x + k] = True
                x += k
        p += size
        letters[code] = (y, rows, mask)
    return letters


def gen_font(res):
    """Letters of menu.abc scaled by 0.4, each drawn from the top of its
    line (its y of the abc file included), at the FONT_POSITIONS places in
    a column of 8 pixels a letter can start at: a letter at x of the
    original menus starts at 0.4 x, in column x / 20 at 0.4 (x mod 20).
    Returns {code: (width in the original, [(top, columns, rows)] for each
    place)}, a row being a word of the two planes for each column; and the
    colors of the text."""
    letters = parse_abc(res.res.read('menu.abc'))
    pal = np.array(res.pal + [0] * 768, float)[:768].reshape(-1, 3)
    scaled = {}
    for code, (yo, rows, mask) in letters.items():
        h, w = rows.shape
        # The picture starts at the top of the line, or a whole number of
        # target pixels above it for the few letters reaching above it:
        base = 0 if yo >= 0 else -5
        rgba = np.zeros((yo - base + h, w, 4))
        rgba[yo - base:, :, :3] = pal[rows]
        rgba[yo - base:, :, 3] = mask
        for k in range(FONT_POSITIONS):
            col, cov = area_scale(rgba, SCALE, phase=(k * SCALE, 0.0))
            scaled[k, code] = (base, col, cov, w)
    # The three colors of the text: of the well covered pixels, the bright
    # face, the middle and the dark edge (by brightness; the averages of a
    # clustering came out darker than the original's text looks).
    allpix = np.concatenate([c[v > 0.5] for (k, _), (_, c, v, _) in scaled.items() if k == 0])
    order = allpix[np.argsort(allpix.sum(1))]
    colors = np.array([order[int(len(order) * q)] for q in (0.95, 0.6, 0.2)])
    colors = np.array([from555(to555(c)) for c in colors], float)
    # A pixel is drawn where the letter covers enough of it; partly covered
    # pixels are seen over the dark green of the background:
    behind = np.array([0, 40, 0], float)
    glyphs = {}
    for (k, code), (y0, col, cov, w) in sorted(scaled.items()):
        h, tw = cov.shape
        mixed = col * cov[..., None] + behind * (1 - cov[..., None])
        choice = nearest(mixed, np.vstack([behind[None], colors]))
        choice[cov < 0.25] = 0
        yo, lrows, lmask = letters[code]
        if lrows.shape[0] <= 3:
            # A thin letter (_): its rows become one row of the screen.
            line = np.zeros((1, lrows.shape[1], 4))
            for x in range(lrows.shape[1]):
                ys = np.nonzero(lmask[:, x])[0]
                if len(ys):
                    line[0, x, :3] = pal[lrows[ys[0], x]]
                    line[0, x, 3] = 1
            lcol, lcov = area_scale(line, SCALE, phase=(k * SCALE, 0.0))
            row = int(round((yo - y0) * SCALE))
            choice = np.zeros(cov.shape, int)
            lc = nearest(lcol[:1], colors)[0] + 1
            lc[lcov[0] < 0.5 * SCALE] = 0   # a row of the source is SCALE of a pixel
            choice[row, :len(lc)] = lc[:choice.shape[1]]
        used = np.nonzero(choice.any(0))[0]
        ncols = (used.max() // 8 + 1) if len(used) else 0
        if ncols > GLYPH_COLUMNS:
            raise ValueError('letter %r too wide' % chr(code))
        rows = []
        for yy in range(h):
            words_ = []
            for c in range(ncols):
                p0 = p1 = 0
                for xx in range(8):
                    v = int(choice[yy, c * 8 + xx]) if c * 8 + xx < tw else 0
                    if v & 1:
                        p0 |= 0x80 >> xx
                    if v & 2:
                        p1 |= 0x80 >> xx
                words_.append(p0 | p1 << 8)
            rows.append(words_)
        # Leave out empty rows at the top and bottom:
        first = 0
        while first < len(rows) and not any(rows[first]):
            first += 1
        last = len(rows)
        while last > first and not any(rows[last - 1]):
            last -= 1
        top = int(round(y0 * SCALE)) + first
        glyphs.setdefault(code, (w, []))[1].append((top, ncols, rows[first:last]))
    # Color numbers 1-3 are bright, middle, dark (the order of choice).
    return glyphs, [0] + [to555(c) for c in colors]


# -- the helmet --------------------------------------------------------------

def helmet_frames(res):
    """The 50 frames of sisak.pcx as anim and korrigal make them: 40x41,
    transparent where -1."""
    big = res.pcx('sisak.pcx')
    a = np.array(big).astype(int)
    see = a[0, 0]
    frames = []
    for i in range(big.width // 40):
        fr = a[:, i * 40:(i + 1) * 40]
        new = np.full((41, 40), see)
        new[1:, :] = fr
        for x in range(40):
            if new[1, x] != see:
                new[0, x + 4:] = new[1, x + 3]
                break
        for x in range(39, 0, -1):
            if new[1, x] != see:
                new[0, max(0, x - 3):] = see
                break
        frames.append(np.where(new == see, -1, new))
    return frames


def gen_helmet(res):
    pal = np.array(res.pal + [0] * 768, float)[:768].reshape(-1, 3)
    out = []
    for fr in helmet_frames(res):
        rgba = np.zeros(fr.shape + (4,))
        rgba[..., :3] = pal[np.maximum(fr, 0)]
        rgba[..., 3] = fr >= 0
        out.append(area_scale(rgba, SCALE, size=(16, 17)))
    allpix = np.concatenate([c[v >= 0.5] for c, v in out])
    colors = kmeans(allpix, 15)
    colors = colors[np.argsort(colors.sum(1))]
    colors = np.array([from555(to555(c)) for c in colors], float)
    chr_ = bytearray()
    for col, cov in out:
        idx = nearest(col, colors) + 1
        idx[cov < 0.5] = 0
        full = np.zeros((24, 16), int)
        full[:17] = idx
        # Two tiles in each of three rows of the 32x32 sprite:
        for ty in range(3):
            for tx in range(2):
                chr_ += tile_4bpp(full[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8])
    return bytes(chr_), [0] + [to555(c) for c in colors]


# -- the balls ---------------------------------------------------------------

def gen_balls():
    """For each size: (sprite tiles a side, chr of BALL_ANGLES frames). A
    ball is drawn in color 1 where it darkens the background; the two small
    circles at half its radius show the background as it is (kirajzolgolyo
    with Buffsima)."""
    out = []
    for r_pc in BALL_RADII:
        r = r_pc * SCALE
        side = int(math.ceil(2 * r / 8.0))
        size = side * 8
        c = size / 2.0
        frames = bytearray()
        for k in range(BALL_ANGLES):
            a = math.pi * k / BALL_ANGLES
            ex, ey = 0.5 * r * math.cos(a), 0.5 * r * math.sin(a)
            img = np.zeros((size, size), int)
            for y in range(size):
                for x in range(size):
                    px, py = x + 0.5 - c, y + 0.5 - c
                    if px * px + py * py <= r * r:
                        img[y, x] = 1
                        for s in (1, -1):
                            dx, dy = px - s * ex, py - s * ey
                            if dx * dx + dy * dy <= (0.25 * r) ** 2:
                                img[y, x] = 0
            for ty in range(side):
                for tx in range(side):
                    frames += tile_4bpp(img[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8])
        out.append((side, bytes(frames)))
    return out


# -- the intro picture -------------------------------------------------------

def intro_picture(res):
    """intro.pcx as teljes shows it: the number of the version written over
    with pieces of the picture itself ("1.0" to "1.11a" on the picture of
    the original game; on the remastered picture of the Steam release the
    same copies leave "11 a" after "Remastered version", as the original
    code shows it there too)."""
    im = res.intro.copy()

    def blt(x, y, x1, y1, x2, y2):
        im.paste(im.crop((x1, y1, x2 + 1, y2 + 1)), (x, y))
    if res.res.shareware:
        blt(321, 420, 296, 420, 314, 441)
        blt(321 + 15, 420, 296, 420, 314, 441)
        blt(321 + 15 + 17, 432, 88, 458, 98, 468)
    else:
        blt(321, 420, 297, 420, 315, 441)
        blt(321 + 15, 420, 297, 420, 315, 441)
        blt(321 + 15 + 16, 432, 88, 458, 98, 468)
    pal = list(res.pal)
    pal[0:3] = [0, 0, 0]                     # pcxtopal: color 0 is black
    return pal_image(im, pal)


def gen_intro(res, npal=4):
    """Tiles of the intro picture at 0.4 (256x192) in up to npal palettes
    of 15 colors; black is the transparent color 0. The map has the picture
    from its first row."""
    rgb = intro_picture(res)
    rgba = np.concatenate([rgb, np.ones(rgb.shape[:2] + (1,))], -1)
    col, _ = area_scale(rgba, SCALE, size=(256, 192))
    col = np.round(col / 255 * 31) * 255 / 31
    dark = col.max(-1) < 12
    tiles = [(ty, tx, col[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8],
              dark[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8])
             for ty in range(24) for tx in range(32)]
    used = [t for t in tiles if not t[3].all()]
    # Groups of tiles by their mean color, a palette for each:
    means = np.array([t[2][~t[3]].mean(0) for t in used])
    groups = nearest(means, kmeans(means, npal))
    pals = []
    for g in range(npal):
        pix = [t[2][~t[3]] for t, gg in zip(used, groups) if gg == g]
        if not pix:
            pals.append(np.zeros((1, 3)))
            continue
        pals.append(np.array([from555(to555(c)) for c in kmeans(np.concatenate(pix), 15)], float))
    chr_ = [tile_4bpp(np.zeros((8, 8)))]
    known = {chr_[0]: 0}
    tmap = [0x2000] * (32 * 32)
    for ty, tx, c, d in tiles:
        if d.all():
            continue
        best = None
        for g, p in enumerate(pals):
            idx = nearest(c, p)
            err = ((p[idx] - c) ** 2).sum(-1)[~d].sum()
            if best is None or err < best[0]:
                best = (err, g, idx)
        _, g, idx = best
        idx = idx + 1
        idx[d] = 0
        t = tile_4bpp(idx)
        if t not in known:
            known[t] = len(chr_)
            chr_.append(t)
        tmap[ty * 32 + tx] = known[t] | (INTRO_PAL + g) << 10 | 0x2000
    pal = []
    for p in pals:
        q = [0] + [to555(c) for c in p]
        pal += q + [0] * (16 - len(q))
    return b''.join(chr_), len(chr_), tmap, pal


# -- output ------------------------------------------------------------------

class Asm:
    def __init__(self):
        self.lines = ['; Generated by tools/gen_ui.py.', '.include "hdr.asm"', '']
        self.n = 0

    def section(self, label, data, comment=None):
        """A label with bytes, in sections of at most a bank."""
        if len(data) > 0x8000:
            raise ValueError('%s does not fit in a bank' % label)
        self.n += 1
        if comment:
            self.lines.append('; ' + comment)
        self.lines.append('.SECTION ".ui_data_%d" SUPERFREE' % self.n)
        self.lines.append('%s:' % label)
        for i in range(0, len(data), 32):
            self.lines.append('\t.db ' + ', '.join('$%02X' % b for b in data[i:i + 32]))
        self.lines.append('.ENDS')
        self.lines.append('')


def words(values):
    return b''.join(struct.pack('<H', v & 0xFFFF) for v in values)


def main():
    res = Res(sys.argv[1])
    out = sys.argv[2]
    asm = Asm()
    h = ['// Generated by tools/gen_ui.py from %s.' % os.path.basename(sys.argv[1]),
         '#ifndef UI_DATA_H', '#define UI_DATA_H', '']

    bg_chr, bg_map, bg_pal = gen_background(res)
    asm.section('ui_bg_chr', bg_chr, 'The background of the menus: 4-bit tiles.')
    asm.section('ui_bg_map', words(bg_map))
    asm.section('ui_bg_pal', words(bg_pal))
    h += ['// The background of the menus (4 bits, a 32x32 map, 16 colors):',
          '#define UI_BG_TILES %d' % (len(bg_chr) // 32),
          '#define UI_BG_PAL %d' % BG_PAL,
          'extern const u8 ui_bg_chr[], ui_bg_map[], ui_bg_pal[];', '']

    glyphs, text_pal = gen_font(res)
    pcw = [0] * 256
    asm.lines.append('; The letters of menu.abc: offsets of the 20 places (from the label),')
    asm.lines.append('; then at each: the first row under the top of the line (signed), the')
    asm.lines.append('; rows, the columns; a row: a word of the two planes for each column.')
    n = 0
    size = 0
    for code in sorted(glyphs):
        w, places = glyphs[code]
        pcw[code] = w
        data = bytearray()
        offsets = []
        for top, ncols, rows in places:
            offsets.append(2 * FONT_POSITIONS + len(data))
            data += struct.pack('<bBB', top, len(rows), ncols)
            for r in rows:
                data += words(r)
        block = words(offsets) + bytes(data)
        if size + len(block) > 0x7000 or n == 0:
            if n:
                asm.lines += ['.ENDS', '']
            n += 1
            size = 0
            asm.lines.append('.SECTION ".ui_font_%d" SUPERFREE' % n)
        size += len(block)
        asm.lines.append('ui_glyph_%d:' % code)
        for i in range(0, len(block), 32):
            asm.lines.append('\t.db ' + ', '.join('$%02X' % b for b in block[i:i + 32]))
    asm.lines += ['.ENDS', '']
    asm.lines.append('.SECTION ".ui_font_ptr" SUPERFREE')
    asm.lines.append('ui_font_ptr:')
    for code in range(256):
        asm.lines.append('\t.dl %s' % ('ui_glyph_%d' % code if code in glyphs else '0'))
    asm.lines += ['.ENDS', '']
    asm.section('ui_font_pcw', bytes(pcw), 'Widths of the letters in the original game.')
    asm.section('ui_text_pal', words(text_pal))
    # A letter at x of the original menus (640 wide) starts in the column of
    # tiles x / 20 (times 16: bytes in the canvas), at place x mod 20 (times 2):
    asm.section('ui_xcol', words([(x // 20) * 16 for x in range(1024)]))
    asm.section('ui_xplace', bytes([(x % 20) * 2 for x in range(1024)]))
    h += ['// The font (menu.abc): the width of each letter in the original game',
          '// (0: none), the space between letters and the width of a space there.',
          '#define UI_FONT_TAV %d' % FONT_TAV,
          '#define UI_FONT_SPACE 10',
          'extern const u8 ui_font_pcw[256];',
          'extern const u8 ui_text_pal[];', '']

    hchr, hpal = gen_helmet(res)
    asm.section('ui_helmet_chr', hchr, 'The helmet: 50 frames of 2x3 tiles.')
    asm.section('ui_helmet_pal', words(hpal))
    h += ['// The helmet (sisak.pcx): frames of 2x3 tiles of 4 bits.',
          '#define UI_HELMET_FRAMES %d' % (len(hchr) // 192),
          'extern const u8 ui_helmet_chr[], ui_helmet_pal[];', '']

    balls = gen_balls()
    for i, (side, frames) in enumerate(balls):
        asm.section('ui_ball%d_chr' % i, frames, 'Ball %d: %d angles of %dx%d tiles.'
                    % (i, BALL_ANGLES, side, side))
    h += ['// The balls of the menus: radius (original pixels) and tiles a side.',
          '#define UI_BALL_ANGLES %d' % BALL_ANGLES]
    for i, (side, _) in enumerate(balls):
        h.append('#define UI_BALL%d_R %d' % (i, BALL_RADII[i]))
        h.append('#define UI_BALL%d_SIDE %d' % (i, side))
    h += ['extern const u8 ui_ball0_chr[], ui_ball1_chr[], ui_ball2_chr[];', '']

    ichr, ntiles, imap, ipal = gen_intro(res)
    # The room of each in the VRAM of the menus (ui.c):
    if len(bg_chr) // 32 > 448 or ntiles > 448:
        raise ValueError('too many tiles: background %d, intro %d'
                         % (len(bg_chr) // 32, ntiles))
    asm.section('ui_intro_chr', ichr, 'The intro picture: 4-bit tiles.')
    asm.section('ui_intro_map', words(imap))
    asm.section('ui_intro_pal', words(ipal))
    h += ['// The intro picture (intro.pcx): tiles, a 32x32 map from its first row,',
          '// palettes from BG palette UI_INTRO_PAL.',
          '#define UI_INTRO_PAL %d' % INTRO_PAL,
          '#define UI_INTRO_TILES %d' % ntiles,
          '#define UI_INTRO_PALS %d' % (len(ipal) // 16),
          'extern const u8 ui_intro_chr[], ui_intro_map[], ui_intro_pal[];', '',
          '#endif']

    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'ui_data.asm'), 'w') as f:
        f.write('\n'.join(asm.lines) + '\n')
    with open(os.path.join(out, 'ui_data.h'), 'w') as f:
        f.write('\n'.join(h) + '\n')


if __name__ == '__main__':
    main()
