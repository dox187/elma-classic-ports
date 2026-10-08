"""Writes the sprites of the bike, the rider and the objects (apples,
flower, killers) and the tables the program draws them with:
build/gen/bike_data.asm, bike_data.inc and bike_data.h.

  gen_bike.py ELMA_LGR OUT_DIR [PHYS_H]

Every part of the bike (bikemodel.py) is drawn beforehand at a number of
angles, 0.4 times the size of the original game, from the pictures of the
LGR file, each into 16x16 sprites around the part's center. Only half of
the circle is stored: the other half and the mirrored parts are the same
sprites flipped (sprites flipped horizontally and vertically are the part
turned by 180 degrees, flipped vertically the part mirrored).

An angle alpha (u16, 65536 a turn, counterclockwise) with a handedness h
(0: the picture as it is, 1: mirrored) of a part drawn at N angles is the
stored picture k with the flips:

  q = (alpha + 32768/N) >> (16 - log2 N) & (N - 1)
  h = 0:  q < N/2: k = q;  else k = q - N/2, flipped both ways
  h = 1:  q' = -q & (N - 1);  q' < N/2: k = q', flipped vertically;
          else k = q' - N/2, flipped horizontally

While the bike turns (the squash of kibike), the parts are drawn from
pictures squashed at four levels, of the rider sitting still, at the angle
of the bike (the same rule, alpha = the angle of the bike).

Units of the program: 1/16 pixel (16 * 19.2 a meter), y up.
"""

import math
import os
import re
import sys

import numpy as np

import bikemodel as bm
from lgr import Lgr
from config import BANK_SIZE

PPM = 19.2                   # pixels a meter
U = 16 * PPM                 # units a meter
N_WHEEL = 64                 # angles of the wheels
N_PART = 64                  # head, limbs and suspension pieces
N_FRAME = 128                # the body of the bike
N_TURN = 32                  # parts while turning
N_TURN_FRAME = 64
TURN_LEVELS = (0.06, 0.25, 0.5, 0.75)   # squash of the pictures while turning
ALPHA_MIN = 0.4              # coverage of a pixel to be drawn
ALPHA_WHEEL = 0.5            # the same for the wheels (no lone tips of the tire)
SS = 8                       # samples a pixel, both ways

# The parts with sprites loaded while drawing: index, picture, palette.
# Their order is the order of their places in the VRAM (two rows of 8
# sprites of 16x16): parts that change together are next to each other.
PARTS = ['thigh', 'leg', 'uparm', 'forearm', 's1a', 's1b', 's2a', 's2b',
         'head', 'torso']
PART_PIC = {'thigh': 'q1thigh', 'leg': 'q1leg', 'uparm': 'q1up_arm',
            'forearm': 'q1forarm', 's1a': 'q1susp1', 's1b': 'q1susp1',
            's2a': 'q1susp2', 's2b': 'q1susp2', 'head': 'q1head',
            'torso': 'q1body'}
PALETTE = {'frame': 0, 'wheel': 0, 's1a': 0, 's1b': 0, 's2a': 0, 's2b': 0,
           'head': 1, 'forearm': 1, 'leg': 1,
           'torso': 2, 'uparm': 2, 'thigh': 2}
FRAME_SPRITES = 6            # places for the sprites of the body
FRAME_DESC = 128             # bytes of the descriptor of a picture of the body
# Length of a piece of a suspension, of the whole:
PIECE = 0.58
# The table of the limbs (by the rider's place in the frame of the bike):
LIMBS = ('thigh', 'leg', 'uparm', 'forearm')
LIMB_X0, LIMB_NX = -160, 64
LIMB_Y0, LIMB_NY = 8, 40

# The rods of kibike: picture, the ends a, b (joints of bikemodel), ta,
# tb, half width, mirrored when the bike is not turned.
RODS = {
    'thigh': ('knee', 'hip', 0.03, 0.1, 0.14, False),
    'leg': ('foot', 'knee', 0.03, 0.03, 0.21, False),
    'torso': ('hip', 'torso', 0.1, 0.05, 0.2, False),
    'uparm': ('elbow', 'shoulder', 0.08, 0.1, 0.11, True),
    'forearm': ('hand', 'elbow', 0.08, 0.1, 0.076, False),
    's1': ('wheel0', 'handle', 0.05, 0.03, 0.06, False),
    's2': ('rear', 'wheel1', 0.0, 0.1, 0.06, False),
}


def nominal_joints(st):
    j = bm.joints(st)
    j['wheel0'], j['wheel1'] = st.wheel[0], st.wheel[1]
    return j


def rod_part(name, pic, a, b, ta, tb, w, mirror):
    return bm.kidoboz(pic, a, b, w, ta, tb, mirror)


class Geometry:
    """The constants of the bike at rest (initmotor), not turned, angle 0."""

    def __init__(self):
        st = bm.State()
        self.st = st
        j = nominal_joints(st)
        self.j = j
        body, rider = st.body, st.rider
        mi, mj, _ = bm.body_frame(st)

        def un(p):
            return [int(round(p[0] * U)), int(round(p[1] * U))]
        # Points fixed to the body (from its center) and to the rider:
        self.handle = un(j['handle'] - body)
        self.rear = un(j['rear'] - body)
        self.foot = un(j['foot'] - body)
        self.hip = un(j['hip'] - rider)
        self.shoulder = un(j['shoulder'] - rider)
        # The torso: its center from the rider and its angle in the body:
        a, b = j['hip'] - rider, j['torso'] - rider
        e = bm.unit(b - a)
        c = (a + b) / 2 + e * (0.05 - 0.1) / 2
        self.torso_c = un(c)
        # The same in units, not rounded (for the tables of the angles):
        self.points = {'handle': (j['handle'] - body) * U, 'rear': (j['rear'] - body) * U,
                       'foot': (j['foot'] - body) * U, 'hip': (j['hip'] - rider) * U,
                       'shoulder': (j['shoulder'] - rider) * U, 'torso_c': c * U,
                       'head': bm.v(-0.09, 0.63) * U}
        self.torso_beta = int(round(math.atan2(e[1], e[0]) / (2 * math.pi) * 65536)) & 0xFFFF
        # Lengths of the rods (with their ends) at rest:
        self.rod_len = {}
        for r, (ja, jb, ta, tb, w, m) in RODS.items():
            self.rod_len[r] = math.hypot(*(j[jb] - j[ja])) + ta + tb
        # Where the center of a rod is between its ends (a + c * (b - a)):
        self.center_c = {}
        for r, ln in (('thigh', bm.THIGH_LEN), ('leg', bm.LEG_LEN),
                      ('uparm', bm.UPARM_LEN), ('forearm', bm.FOREARM_LEN)):
            ta, tb = RODS[r][2], RODS[r][3]
            self.center_c[r] = 0.5 + (tb - ta) / (2 * ln)
        # Pieces of the suspensions: their length (meters):
        self.piece_len = {s: self.rod_len[s] * PIECE for s in ('s1', 's2')}


# --- Drawing the pictures --------------------------------------------------

class Renderer:
    def __init__(self, pics):
        self.pics = pics

    def render(self, parts, size, clip=None):
        """The parts (world, the pivot at 0, 0) on a size x size picture
        (pivot at its center), SS x SS samples a pixel: colors (RGB float)
        and coverage. clip: (part, kx0, kx1) draws only the columns of that
        part's picture between kx0 and kx1."""
        n = size * SS
        g = (np.arange(n) + 0.5) / SS - size / 2
        gx, gy = np.meshgrid(g, g)
        wx = gx / PPM
        wy = -gy / PPM
        idx = np.full(gx.shape, -1, dtype=int)
        for p in parts:
            c = self.sample(p, wx, wy, clip[1:] if clip and clip[0] is p else None)
            idx[c >= 0] = c[c >= 0]
        rgb = np.zeros(gx.shape + (3,))
        m = idx >= 0
        rgb[m] = self.pics.pal[idx[m]]
        rgb = rgb.reshape(size, SS, size, SS, 3).sum(axis=(1, 3))
        a = m.reshape(size, SS, size, SS).sum(axis=(1, 3)).astype(float)
        col = rgb / np.maximum(a, 1)[..., None]
        return col, a / (SS * SS)

    def sample(self, part, wx, wy, cols=None):
        a, lyuk = self.pics[part.name]
        h, w = a.shape
        uu = part.u / (w - 1)
        vv = part.v / (h - 1)
        det = uu[0] * vv[1] - vv[0] * uu[1]
        out = np.full(wx.shape, -1, dtype=int)
        if abs(det) < 1e-12:
            return out
        dx = wx - part.r[0]
        dy = wy - part.r[1]
        kx = (vv[1] * dx - vv[0] * dy) / det
        ky = (-uu[1] * dx + uu[0] * dy) / det
        ix = np.floor(kx + 0.5).astype(int)
        iy = np.floor(ky + 0.5).astype(int)
        inside = (ix >= 0) & (ix < w) & (iy >= 0) & (iy < h)
        if cols:
            inside &= (kx >= cols[0]) & (kx < cols[1])
        c = a[np.clip(iy, 0, h - 1), np.clip(ix, 0, w - 1)]
        ok = inside & (c != lyuk)
        out[ok] = c[ok]
        return out


def moved(part, d):
    p = bm.Part(part.name, part.r + d, part.u, part.v, part.kind)
    return p


def center_of(part):
    return part.r + part.u / 2 + part.v / 2


def piece_clip(part, piece, frac):
    """Columns of the picture of a rod's piece (a: from its start, b: to its
    end) and the piece's center (world)."""
    w = part.picw
    span = (w - 1) * frac
    if piece == 'a':
        k0, k1 = -0.5, span + 0.5
    else:
        k0, k1 = (w - 1) - span - 0.5, w - 0.5
    kc = (k0 + k1) / 2
    ky = (part.pich - 1) / 2
    c = part.r + part.u * (kc / (w - 1)) + part.v * (ky / (part.pich - 1))
    return k0, k1, c


class Images:
    """The pictures of a set: sprites (dx, dy, 16x16 RGB, coverage) each."""

    def __init__(self):
        self.images = []     # [ [(dx, dy, col, alpha), ...], ... ]


def cover(alpha, size):
    """16x16 windows covering every drawn pixel of the picture (greedy)."""
    opaque = alpha >= ALPHA_MIN
    rem = opaque.copy()
    wins = []
    while rem.any():
        integ = np.zeros((size + 1, size + 1), int)
        integ[1:, 1:] = rem.cumsum(0).cumsum(1)
        best = None
        for y in range(size - 15):
            s = integ[y + 16, 16:] - integ[y, 16:] - integ[y + 16, :-16] + integ[y, :-16]
            x = int(np.argmax(s))
            if best is None or s[x] > best[0]:
                best = (s[x], x, y)
        _, x, y = best
        wins.append((x, y))
        rem[y:y + 16, x:x + 16] = False
    return wins


def single_image(rend, parts, clip=None):
    """A part on one 16x16 sprite, its center at the sprite's center."""
    col, a = rend.render(parts, 24, clip)
    lost = (a >= ALPHA_MIN).sum() - (a[4:20, 4:20] >= ALPHA_MIN).sum()
    return [(-8, -8, col[4:20, 4:20], a[4:20, 4:20])], lost


def multi_image(rend, parts):
    col, a = rend.render(parts, 64)
    wins = cover(a, 64)
    if len(wins) > FRAME_SPRITES:
        raise SystemExit('the body of the bike needs %d sprites' % len(wins))
    out = []
    for x, y in wins:
        sa = a[y:y + 16, x:x + 16].copy()
        out.append((x - 32, y - 32, col[y:y + 16, x:x + 16], sa))
    return out


def rotated_state(st, theta, **kw):
    """The bike at rest turned around its center by theta."""
    def R(p):
        return st.body + bm.rotate(p - st.body, theta)
    return bm.State(body=st.body, body_a=st.body_a + theta, wheel0=R(st.wheel[0]),
                    wheel1=R(st.wheel[1]), rider=R(st.rider), **kw)


def draw_all(lgr, geo, log):
    pics = bm.Pictures(lgr)
    rend = Renderer(pics)
    sets = {}
    lost_max = 0
    # The wheel:
    imgs = []
    for k in range(N_WHEEL // 2):
        al = k * 2 * math.pi / N_WHEEL
        p = bm.kidobozkerek('q1wheel', bm.v(0, 0), bm.WHEEL_R, al)
        im, lost = single_image(rend, [p])
        lost_max = max(lost_max, lost)
        imgs.append(im)
    sets['wheel'] = imgs
    # Head and rods, not turned, at angle alpha (h = 0):
    for name in PARTS:
        imgs = []
        for k in range(N_PART // 2):
            al = k * 2 * math.pi / N_PART
            e = bm.v(math.cos(al), math.sin(al))
            clip = None
            if name == 'head':
                p = bm.kidobozkerek('q1head', bm.v(0, 0), bm.HEAD_R, al)
                parts = [p]
            else:
                rod = name[:2] if name[0] == 's' else name
                ta, tb, w = RODS[rod][2], RODS[rod][3], RODS[rod][4]
                ln = geo.rod_len[rod]
                p = bm.kidoboz(PART_PIC[name], -e * (ln / 2), e * (ln / 2), w, 0.0, 0.0)
                a, _ = pics[p.name]
                p.pich, p.picw = a.shape
                if rod in ('s1', 's2'):
                    k0, k1, c = piece_clip(p, name[2], geo.piece_len[rod] / ln)
                    p = moved(p, -c)
                    p.pich, p.picw = a.shape
                    clip = (p, k0, k1)
                parts = [p]
            im, lost = single_image(rend, parts, clip)
            lost_max = max(lost_max, lost)
            imgs.append(im)
        sets[name] = imgs
    # The body of the bike at the angle of the bike:
    imgs = []
    for k in range(N_FRAME // 2):
        th = k * 2 * math.pi / N_FRAME
        st = rotated_state(geo.st, th)
        parts = [moved(p, -st.body) for p in bm.kibike(st) if p.kind == 'frame']
        imgs.append(multi_image(rend, parts))
    sets['frame'] = imgs
    log.append('frame sprites: %s' % [len(i) for i in imgs])
    # Squashed while turning:
    for lv, s in enumerate(TURN_LEVELS):
        turn = math.acos(-s) / math.pi
        fr, singles = [], {n: [] for n in PARTS}
        for k in range(N_TURN_FRAME // 2):
            th = k * 2 * math.pi / N_TURN_FRAME
            st = rotated_state(geo.st, th, turn=turn)
            parts = bm.kibike(st)
            fparts = [moved(p, -st.body) for p in parts if p.kind == 'frame']
            fr.append(multi_image(rend, fparts))
            if k % (N_TURN_FRAME // N_TURN):
                continue
            byname = {}
            for p in parts:
                byname.setdefault(p.name, []).append(p)
            for name in PARTS:
                pic = PART_PIC[name]
                p = byname[pic][0]
                a, _ = pics[pic]
                p.pich, p.picw = a.shape
                clip = None
                if name[0] == 's':
                    rod = name[:2]
                    k0, k1, c = piece_clip(p, name[2], geo.piece_len[rod] / geo.rod_len[rod])
                    q = moved(p, -c)
                    q.pich, q.picw = a.shape
                    clip = (q, k0, k1)
                else:
                    q = moved(p, -center_of(p))
                im, lost = single_image(rend, [q], clip)
                lost_max = max(lost_max, lost)
                singles[name].append(im)
        sets['frame_t%d' % lv] = fr
        for name in PARTS:
            sets['%s_t%d' % (name, lv)] = singles[name]
        log.append('squash %.2f frame sprites: %s' % (s, [len(i) for i in fr]))
    log.append('pixels cut off at the edges of single sprites: %d at most' % lost_max)
    return sets, pics


# --- Colors ------------------------------------------------------------------

def snes_rgb(c):
    """A color of 8 bits a channel as the SNES shows it (5 bits)."""
    q = np.clip(np.round(np.asarray(c, float) / 255 * 31), 0, 31)
    return q * 255 / 31


WEIGHT = np.array([0.30, 0.59, 0.11]) ** 0.5 * 1.7


def kmeans(colors, weights, k, iters=40, seed=1):
    """k colors for the weighted colors (rows of RGB)."""
    x = colors * WEIGHT
    if len(x) <= k:
        c = list(x) + [x[0]] * (k - len(x))
        return np.array(c) / WEIGHT
    rng = np.random.default_rng(seed)
    c = [x[rng.choice(len(x), p=weights / weights.sum())]]
    for _ in range(k - 1):
        d = np.min(((x[:, None, :] - np.array(c)[None]) ** 2).sum(-1), axis=1)
        p = d * weights
        c.append(x[rng.choice(len(x), p=p / p.sum())] if p.sum() > 0 else x[0])
    c = np.array(c, float)
    for _ in range(iters):
        d = ((x[:, None, :] - c[None]) ** 2).sum(-1)
        lab = d.argmin(1)
        for j in range(k):
            m = lab == j
            if m.any():
                c[j] = (x[m] * weights[m, None]).sum(0) / weights[m].sum()
    return c / WEIGHT


def make_palette(cols, boost=3.0):
    """15 colors for the colors of the pictures; saturated colors weigh
    more (small colored details, like the hub of the wheel, keep a color)."""
    cols = np.concatenate(cols)
    q = np.round(cols / 4).astype(int)
    u, cnt = np.unique(q, axis=0, return_counts=True)
    c = u * 4.0
    mx, mn = c.max(1), c.min(1)
    sat = (mx - mn) / np.maximum(mx, 1)
    pal = kmeans(c, cnt * (1 + boost * sat), 15)
    return snes_rgb(pal)


def quantize(col, alpha, pal, thr=ALPHA_MIN):
    """Color indices 1..15 of the palette, 0 where not drawn."""
    d = (((col[..., None, :] - pal[None, None]) * WEIGHT) ** 2).sum(-1)
    idx = d.argmin(-1) + 1
    idx[alpha < thr] = 0
    return idx


def bgr555(c):
    r, g, b = [int(round(x * 31 / 255)) for x in c]
    return r | g << 5 | b << 10


def tiles16(idx):
    """A 16x16 picture of color indices as 4 tiles of 4 bits (top left,
    top right, bottom left, bottom right): 128 bytes."""
    out = bytearray()
    for ty in (0, 8):
        for tx in (0, 8):
            t = bytearray(32)
            for y in range(8):
                for x in range(8):
                    v = int(idx[ty + y, tx + x])
                    bit = 0x80 >> x
                    if v & 1: t[2 * y] |= bit
                    if v & 2: t[2 * y + 1] |= bit
                    if v & 4: t[16 + 2 * y] |= bit
                    if v & 8: t[16 + 2 * y + 1] |= bit
            out += t
    return bytes(out)


# --- Objects -------------------------------------------------------------------

def object_frames(lgr):
    """The animations of the objects (qexit, qkiller, qfood1..9): for each a
    list of 16x16 (colors, coverage)."""
    kinds = [('exit', 'qexit'), ('killer', 'qkiller')]
    for i in range(1, 10):
        if 'qfood%d' % i in lgr:
            kinds.append(('food%d' % i, 'qfood%d' % i))
    pal = np.array(lgr.palette(), dtype=float)
    out = []
    for kind, name in kinds:
        im = np.array(lgr[name].image, dtype=np.uint8)
        h, w = im.shape
        size = h if lgr.lgr13 else 40
        lyuk = im[0, 0]
        frames = []
        for f in range(w // size):
            fr = im[:, f * size:(f + 1) * size]
            # 16x16 of the frame: SS x SS samples a pixel.
            g = ((np.arange(16 * SS) + 0.5) / (16 * SS) * size).astype(int)
            s = fr[np.ix_(g, g)]
            m = s != lyuk
            rgb = np.zeros(s.shape + (3,))
            rgb[m] = pal[s[m]]
            rgb = rgb.reshape(16, SS, 16, SS, 3).sum(axis=(1, 3))
            a = m.reshape(16, SS, 16, SS).sum(axis=(1, 3)).astype(float)
            frames.append((rgb / np.maximum(a, 1)[..., None], a / (SS * SS)))
        out.append((kind, frames))
    return out


# --- Tables --------------------------------------------------------------------

def s8(v):
    return max(-128, min(127, int(round(v))))


def rod_k(geo, r):
    """The pieces of suspension r: their centers from the ends of the rod
    along it (units)."""
    ext_a, ext_b = RODS[r][2], RODS[r][3]
    lp = geo.piece_len[r]
    return int(round((lp / 2 - ext_a) * U)), int(round((ext_b - lp / 2) * U))


def mul8(a, b):
    """The PPU's multiplication of bike.asm: s16 * s8, bits 8-23."""
    v = ((a * b) >> 8) & 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def tables(geo):
    t = {}
    # sin of 1024 angles (and 256 more: cos), times 128:
    # (periodic, long enough for the angles of the limbs: bk_limbs)
    t['sin'] = [s8(128 * math.sin(i * 2 * math.pi / 1024)) for i in range(2816)]
    # atan of 0..256/256 in u16 angle units:
    t['atan'] = [int(round(math.atan(i / 256) / (2 * math.pi) * 65536)) for i in range(257)]
    # The knee and the elbow (ketkormetszete): by d4 >> 3, d4 the square of
    # the distance in 1/4 pixels.
    def ik(l1, l2, idx):
        d4 = idx * 8 + 4
        l = math.sqrt(d4) / 4 / PPM
        lc = l
        if lc >= l1 + l2:
            lc = l1 + l2 - 0.000001
        if l1 >= lc + l2:
            l1 = lc + l2 - 0.00001
        if l2 >= lc + l1:
            l2 = lc + l1 - 0.00001
        x = (l1 * l1 - l2 * l2 + lc * lc) / (2 * lc)
        m = math.sqrt(max(l1 * l1 - x * x, 0))
        return x / lc, m / lc
    t['knee_b'] = [s8(64 * ik(bm.LEG_LEN, bm.THIGH_LEN, i)[1]) for i in range(1024)]
    t['elbow_a'] = [s8(128 * ik(bm.UPARM_LEN, bm.FOREARM_LEN, i)[0]) for i in range(1024)]
    t['elbow_b'] = [s8(64 * ik(bm.UPARM_LEN, bm.FOREARM_LEN, i)[1]) for i in range(1024)]
    # The angles of the limbs from the angle of foot -> hip and shoulder ->
    # hand (256 steps): the leg +-atan(2b), the thigh -+atan(2b); the upper
    # arm 128 +- atan(b / a), the forearm 128 -+ atan(b / (1 - a)).
    def ang(y, x):
        return int(round(math.atan2(y, x) / (2 * math.pi) * 256)) & 255
    t['knee_beta'] = [ang(2 * ik(bm.LEG_LEN, bm.THIGH_LEN, i)[1], 1) for i in range(1024)]
    t['elbow_gu'] = []
    t['elbow_gf'] = []
    for i in range(1024):
        a, b = ik(bm.UPARM_LEN, bm.FOREARM_LEN, i)
        t['elbow_gu'].append(ang(b, a))
        t['elbow_gf'].append(ang(b, 1 - a))
    # Centers of the pieces of the suspensions, a + c * v (c times 128), by
    # d4 >> 4:
    for s in ('s1', 's2'):
        ta, tb = RODS[s][2], RODS[s][3]
        lp = geo.piece_len[s]
        ca, cb = [], []
        for i in range(1024):
            l = max(math.sqrt(i * 16 + 8) / 4 / PPM, 0.05)
            ca.append(s8(128 * (lp / 2 - ta) / l))
            cb.append(s8(128 * (tb - lp / 2) / l))
        t[s + 'a'] = ca
        t[s + 'b'] = cb
    # The arm while volting: h * cos(alfa), h * sin(alfa) times 64, by
    # ugrasnagysag >> 8, swung up (1) or down (0).
    for up in (0, 1):
        c, s = [], []
        for i in range(256):
            volt = (i + 0.5) / 256
            if i == 0:
                al, h = 0.0, 1.0
            else:
                u = 1.0 - volt
                if up:
                    hat, maxa, maxh = 0.25, 2.7, -0.3
                else:
                    hat, maxa, maxh = 0.2, -1.6, 0.15
                if u < hat:
                    al, h = maxa * u / hat, maxh * u / hat + 1.0
                else:
                    mert = 1.0 - (u - hat) / (1.0 - hat)
                    al, h = maxa * mert, maxh * mert + 1.0
            c.append(s8(64 * h * math.cos(al)))
            s.append(s8(64 * h * math.sin(al)))
        t['volt_c%d' % up] = c
        t['volt_s%d' % up] = s
    # The turn: f = -cos(forgas * pi) times 128 and the level of the
    # squashed pictures (4: not squashed), by forgas >> 8.
    f, lv = [], []
    for i in range(256):
        x = -math.cos((i + 0.5) / 256 * math.pi)
        f.append(s8(128 * x))
        a = abs(x)
        lv.append(4 if a >= 0.875 else min(range(4), key=lambda j: abs(TURN_LEVELS[j] - a)))
    t['turn_f'] = f
    t['turn_lv'] = lv
    # f - 1 times 64 (the squash matrix, bike.asm):
    t['turn_g'] = [s8(64 * (-math.cos((i + 0.5) / 256 * math.pi) - 1)) for i in range(256)]
    # Bobbing of the apples and the flower: -2 * sin (pixels, y down):
    t['bob'] = [s8(-2 * math.sin(i * 2 * math.pi / 256)) for i in range(256)]
    # The points fixed to the bike and the rider, rotated with the bike: by
    # the angle >> 6 (1024 steps), not turned then turned (mirrored along
    # the bike), x and y in units.
    for name, (pj, pf) in geo.points.items():
        tab = []
        for tr in (0, 1):
            for i in range(1024):
                th = (i + 0.5) * 2 * math.pi / 1024
                c, sn = math.cos(th), math.sin(th)
                x = -pj if tr else pj
                tab.append((int(round(x * c - pf * sn)), int(round(x * sn + pf * c))))
        t['rot_' + name] = tab
    # The legs and the arms (not volting) by the rider's place in the frame
    # of the bike (not turned, units): LIMB_NX x LIMB_NY cells of 4 units
    # from (LIMB_X0, LIMB_Y0): the centers of the thigh, the leg, the upper
    # arm and the forearm (units, from the center of the bike) and their
    # angles (256 steps).
    # Also as 2 * the distance and the angle (1024 steps) of the center.
    for name in LIMBS:
        t['limb_%s_x' % name], t['limb_%s_y' % name], t['limb_%s_a' % name] = [], [], []
        t['limb_%s_r2' % name], t['limb_%s_phi' % name] = [], []
    for iy in range(LIMB_NY):
        for ix in range(LIMB_NX):
            rx = (LIMB_X0 + 4 * ix + 2) / U
            ry = (LIMB_Y0 + 4 * iy + 2) / U
            st = bm.State(body=(0.0, 0.0), wheel0=(-0.85, -0.6), wheel1=(0.85, -0.6),
                          rider=(rx, ry))
            j = bm.joints(st)
            for name in LIMBS:
                ja, jb, ta, tb = RODS[name][:4]
                a, b = j[ja], j[jb]
                e = bm.unit(b - a)
                c = (a - e * ta + b + e * tb) / 2 * U
                t['limb_%s_x' % name].append(int(round(c[0])))
                t['limb_%s_y' % name].append(int(round(c[1])))
                t['limb_%s_r2' % name].append(int(round(2 * math.hypot(c[0], c[1]))))
                t['limb_%s_phi' % name].append(int(round(math.atan2(c[1], c[0]) / (2 * math.pi) * 1024)) & 1023)
                t['limb_%s_a' % name].append(int(round(math.atan2(e[1], e[0]) / (2 * math.pi) * 256)) & 255)
    # The angle (256 steps) of a vector by |y| >> 3 (rows) and |x| >> 3
    # (columns), 0..63 each:
    t['atan8'] = [int(round(math.atan2(y, x) / (2 * math.pi) * 256)) & 255
                  for y in range(64) for x in range(64)]
    # The stored picture and flips of an angle step q (N steps) for h = 0
    # then h = 1: k | flips << 8 (gen_bike.py's rule).
    for n in (32, 64, 128):
        tab = []
        for h in (0, 1):
            for q in range(n):
                half = n // 2
                if not h:
                    k, f = (q, 0) if q < half else (q - half, 0xC0)
                else:
                    q2 = -q & (n - 1)
                    k, f = (q2, 0x80) if q2 < half else (q2 - half, 0x40)
                tab.append(k | f << 8)
        t['lk%d' % n] = tab
    # The wheel at 64 steps: its tile | (priority 2 | flips) << 8.
    tab = []
    for q in range(64):
        k, f = (q, 0) if q < 32 else (q - 32, 0xC0)
        tab.append((k >> 3) * 32 + (k & 7) * 2 | (0x20 | f) << 8)
    t['wheel'] = tab
    return t


# --- Output --------------------------------------------------------------------

class Blob:
    """Tile data in sections of at most a bank, identical sprites once."""

    def __init__(self, prefix):
        self.prefix = prefix
        self.sections = [bytearray()]
        self.seen = {}

    def add(self, data):
        if data in self.seen:
            return self.seen[data]
        if len(self.sections[-1]) + len(data) > BANK_SIZE:
            self.sections.append(bytearray())
        ref = '%s%d+%d' % (self.prefix, len(self.sections) - 1, len(self.sections[-1]))
        self.sections[-1] += data
        self.seen[data] = ref
        return ref

    def size(self):
        return sum(len(s) for s in self.sections)


def db(data, per=16):
    out = []
    for i in range(0, len(data), per):
        out.append('\t.db ' + ','.join('$%02X' % (b & 0xFF) for b in data[i:i + per]))
    return out


def phys_hz(path):
    if path and os.path.exists(path):
        m = re.search(r'#define\s+PHYS_HZ\s+\(?\s*(\d+)', open(path).read())
        if m:
            return int(m.group(1))
    return 60


def main():
    lgr = Lgr(sys.argv[1])
    out = sys.argv[2]
    hz = phys_hz(sys.argv[3] if len(sys.argv) > 3 else None)
    geo = Geometry()
    log = []
    sets, pics = draw_all(lgr, geo, log)

    # Palettes 0-2 of the bike from all its pictures:
    group = {}
    for name, imgs in sets.items():
        base = name.split('_')[0]
        pl = PALETTE[base]
        for im in imgs:
            for dx, dy, col, a in im:
                group.setdefault(pl, []).append(col[a >= ALPHA_MIN])
    pals = [make_palette(group[i]) for i in range(3)]
    objs = object_frames(lgr)
    pals.append(make_palette([c[a >= ALPHA_MIN] for _, fr in objs for c, a in fr]))

    blob = Blob('bike_tiles_')
    # Wheels: their 32 pictures as tiles 0-127 of the VRAM.
    wheel_vram = bytearray(128 * 32)
    for k, im in enumerate(sets['wheel']):
        t = tiles16(quantize(im[0][2], im[0][3], pals[0], ALPHA_WHEEL))
        base = (k >> 3) * 32 + (k & 7) * 2
        for half in range(2):
            o = (base + half * 16) * 32
            wheel_vram[o:o + 64] = t[half * 64:half * 64 + 64]
    # Descriptors of the single parts: 4 bytes (pointer, 0) for each. The
    # squashed pictures of the parts 0-7 are only loaded in rows (below):
    # no pointer.
    single = []
    single_idx = []
    single_data = []
    for pn, name in enumerate(PARTS):
        pl = pals[PALETTE[name]]
        lst = [sets[name]] + [sets['%s_t%d' % (name, l)] for l in range(4)]
        for li, imgs in enumerate(lst):
            for im in imgs:
                dx, dy, col, a = im[0]
                q = quantize(col, a, pl)
                single_idx.append(q.astype(np.uint8))
                t = bytes(tiles16(q))
                single_data.append(t)
                single.append(blob.add(t) if li == 0 or pn >= 8 else '0')
    per_part = N_PART // 2 + 4 * (N_TURN // 2)
    assert len(single) == len(PARTS) * per_part
    # Whole rows of sprites for the loads with two transfers (bike.asm):
    # the top halves of the sprites, then their bottom halves.
    rows_blob = Blob('bike_rows_')

    def rows(datas):
        return rows_blob.add(b''.join(t[:64] for t in datas) + b''.join(t[64:] for t in datas))
    # The squashed pictures of the parts 0-7 while turning (they all have
    # the same angle and squash): by squash level * 16 + angle.
    turn_rows = [rows([single_data[p * per_part + N_PART // 2 + lv * (N_TURN // 2) + k]
                       for p in range(8)])
                 for lv in range(4) for k in range(N_TURN // 2)]
    # Descriptors of the body: count, then (dx, dy, pointer) for each sprite.
    frame = []
    frame_idx = []
    frame_rows = []
    for imgs in [sets['frame']] + [sets['frame_t%d' % l] for l in range(4)]:
        for im in imgs:
            spr = []
            datas = []
            for dx, dy, col, a in im:
                q = quantize(col, a, pals[0])
                frame_idx.append(q.astype(np.uint8))
                t = bytes(tiles16(q))
                datas.append(t)
                spr.append((dx, dy, '0'))   # loaded in rows (below)
            frame.append(spr)
            frame_rows.append(rows(datas))
    wheel_idx = [quantize(im[0][2], im[0][3], pals[0], ALPHA_WHEEL).astype(np.uint8)
                 for im in sets['wheel']]
    # Objects:
    obj_blob = Blob('obj_tiles_')
    obj_kinds = []
    obj_idx = []
    for kind, frames in objs:
        qs = [quantize(c, a, pals[3]) for c, a in frames]
        obj_idx.append([q.astype(np.uint8) for q in qs])
        refs = [obj_blob.add(tiles16(q)) for q in qs]
        obj_kinds.append((kind, refs))
    tb = tables(geo)

    # --- bike_data.asm ---
    a = ['; Generated by tools/gen_bike.py from %s.' % os.path.basename(sys.argv[1]),
         '.include "hdr.asm"', '.include "core.inc"', '']
    for n, sec in enumerate(blob.sections):
        a += ['.SECTION ".bike_tiles_%d" SUPERFREE' % n, 'bike_tiles_%d:' % n]
        a += db(sec, 32)
        a += ['.ENDS', '']
    for n, sec in enumerate(rows_blob.sections):
        a += ['.SECTION ".bike_rows_%d" SUPERFREE' % n, 'bike_rows_%d:' % n]
        a += db(sec, 32)
        a += ['.ENDS', '']
    for n, sec in enumerate(obj_blob.sections):
        a += ['.SECTION ".obj_tiles_%d" SUPERFREE' % n, 'obj_tiles_%d:' % n]
        a += db(sec, 32)
        a += ['.ENDS', '']
    a += ['.SECTION ".bike_wheels" SUPERFREE', 'bike_wheel_tiles:']
    a += db(wheel_vram, 32)
    a += ['.ENDS', '']
    # Palettes (OBJ 0-3, color 0 unused):
    pal_words = []
    for p in pals:
        pal_words += [0] + [bgr555(c) for c in p]
    a += ['.SECTION ".bike_pal" SUPERFREE', 'bike_palettes:']
    a += ['\t.dw ' + ','.join('$%04X' % w for w in pal_words[i:i + 16])
          for i in range(0, 64, 16)]
    a += ['.ENDS', '']
    # Descriptors, in one bank:
    a += ['.SECTION ".bike_desc" SUPERFREE', 'bike_desc_single:']
    for ref in single:
        a.append('\t.dl %s\n\t.db 0' % ref)
    # The body: the number of sprites, 18 bytes not used, then for each
    # flip (none, H, V, both) the corners of the 6 sprites from the pivot
    # (x, y words), then the pointer of its rows.
    a.append('bike_desc_frame:')
    for spr, rref in zip(frame, frame_rows):
        a.append('\t.db %d' % len(spr))
        for dx, dy, ref in spr:
            a.append('\t.dl %s' % ref)
        a.append('\t.dsb %d, 0' % (3 * (FRAME_SPRITES - len(spr))))
        for fl in range(4):
            offs = []
            for dx, dy, ref in spr:
                fx = -dx - 16 if fl & 1 else dx
                fy = -dy - 16 if fl & 2 else dy
                offs += [fx, fy]
            offs += [0] * (2 * (FRAME_SPRITES - len(spr)))
            a.append('\t.dw ' + ','.join('%d & $FFFF' % x for x in offs))
        a.append('\t.dl %s' % rref)
        a.append('\t.dsb %d, 0' % (FRAME_DESC - 1 - 3 * FRAME_SPRITES - 16 * FRAME_SPRITES - 3))
    # The rows of the parts 0-7 while turning (4 bytes each):
    a.append('bike_turn_rows:')
    for ref in turn_rows:
        a.append('\t.dl %s\n\t.db 0' % ref)
    a += ['.ENDS', '']
    # Objects: per kind the number of frames and the pointers of the frames.
    a += ['.SECTION ".obj_anims" SUPERFREE', 'obj_kind_frames:']
    a.append('\t.db ' + ','.join(str(len(r)) for _, r in obj_kinds))
    a.append('obj_kind_nfr:')
    a.append('\t.dw ' + ','.join(str(len(r)) for _, r in obj_kinds))
    a.append('obj_kind_table:')
    for n in range(len(obj_kinds)):
        a.append('\t.dw obj_frames_%d' % n)
    for n, (kind, refs) in enumerate(obj_kinds):
        a.append('obj_frames_%d:' % n)
        for ref in refs:
            a.append('\t.dl %s' % ref)
    # The same as the two transfers of the queue of the NMI that load a
    # frame (its top tiles at 192 + 2k, the bottom ones 16 tiles further).
    a.append('obj_q:')
    for n, (kind, refs) in enumerate(obj_kinds):
        a.append('obj_q_%d:' % n)
        vaddr = 'VRAM_OBJ+%d*16' % (192 + 2 * n)
        for ref in refs:
            bank = ':' + ref.split('+')[0]
            a.append('\t.db DMAQ_VRAM\n\t.dw %s\n\t.db %s\n\t.dw 64, %s' % (ref, bank, vaddr))
            a.append('\t.db DMAQ_VRAM\n\t.dw %s+64\n\t.db %s\n\t.dw 64, %s+256' % (ref, bank, vaddr))
    a.append('obj_q_offs:')
    a.append('\t.dw ' + ','.join('obj_q_%d-obj_q' % n for n in range(len(obj_kinds))))
    a += ['.ENDS', '']
    # Tables:
    a += ['.SECTION ".bike_tables" SUPERFREE']
    for name in ('sin', 'elbow_a', 'elbow_b',
                 'volt_c0', 'volt_s0', 'volt_c1', 'volt_s1', 'turn_f', 'turn_lv', 'turn_g',
                 'bob', 'elbow_gu', 'elbow_gf'):
        a.append('bike_t_%s:' % name)
        a += db(tb[name], 32)
    a.append('bike_t_bob16:')
    a += ['\t.dw ' + ','.join('%d & $FFFF' % x for x in tb['bob'][i:i + 16])
          for i in range(0, 256, 16)]
    # El * 19 + (El * 51 >> 8): the low byte of a distance in level pixels
    # (bk_lpx16).
    a.append('bike_t_lpx:')
    a += ['\t.dw ' + ','.join(str(e * 19 + (e * 51 >> 8)) for e in range(i, i + 16))
          for i in range(0, 256, 16)]
    a.append('bike_t_atan:')
    a += ['\t.dw ' + ','.join(str(x) for x in tb['atan'][i:i + 16])
          for i in range(0, 257, 16)]
    # 2 * the lowest set bit of a byte (bk_load).
    a.append('bike_t_low2:')
    lows = [2 * ((v & -v).bit_length() - 1) if v else 0 for v in range(256)]
    a += ['\t.dw ' + ','.join(str(x) for x in lows[i:i + 16]) for i in range(0, 256, 16)]
    a.append('bike_t_wheel:')
    a += ['\t.dw ' + ','.join(str(x) for x in tb['wheel'][i:i + 16]) for i in range(0, 64, 16)]
    # The same by the high byte of the angle (bk_oam).
    w256 = [tb['wheel'][((h + 2) & 255) >> 2] for h in range(256)]
    a.append('bike_t_wheel256:')
    a += ['\t.dw ' + ','.join(str(x) for x in w256[i:i + 16]) for i in range(0, 256, 16)]
    for n in (32, 64, 128):
        a.append('bike_t_lk%d:' % n)
        a += ['\t.dw ' + ','.join(str(x) for x in tb['lk%d' % n][i:i + 16])
              for i in range(0, 2 * n, 16)]
    # The descriptor of each single part by its key (bike_t_lk64's index).
    a.append('bike_t_d64:')
    ppart = N_PART // 2 + 4 * (N_TURN // 2)
    for p in range(len(PARTS)):
        ds = ['bike_desc_single+%d' % (4 * (ppart * p + (x & 255))) for x in tb['lk64']]
        a += ['\t.dw ' + ','.join(ds[i:i + 8]) for i in range(0, len(ds), 8)]
    a += ['.ENDS', '']
    a += ['.SECTION ".bike_atan8" SUPERFREE', 'bike_t_atan8:']
    a += db(tb['atan8'], 32)
    a += ['.ENDS', '']
    # The limbs by the rider's place (not turned): 2 x, 2 y, the angle << 8,
    # 2 * the distance and the angle (1024 steps) of the center.
    for name in LIMBS:
        lx, ly, la = (tb['limb_%s_%s' % (name, f)] for f in 'xya')
        lr, lp = tb['limb_%s_r2' % name], tb['limb_%s_phi' % name]
        for f, tab in (('x2', [2 * x for x in lx]), ('y2', [2 * y for y in ly]),
                       ('a16', [x << 8 for x in la]), ('r2', lr), ('phi', lp)):
            a += ['.SECTION ".bike_limb_%s_%s" SUPERFREE' % (name, f),
                  'bike_limb_%s_%s:' % (name, f)]
            a += ['\t.dw ' + ','.join('%d & $FFFF' % x for x in tab[i:i + 16])
                  for i in range(0, len(tab), 16)]
            a += ['.ENDS', '']
    # The centers of the pieces of the suspensions from the ends of the rod
    # by its angle (256 steps): (2 k cos, 2 k sin) as bike.asm multiplies.
    a += ['.SECTION ".bike_rods" SUPERFREE']
    for r in ('s1', 's2'):
        for kn, k in zip(('ka', 'kb'), rod_k(geo, r)):
            a.append('bike_t_%s_%s:' % (r, kn))
            vals = []
            for ang in range(256):
                vals += [mul8(2 * k, tb['sin'][4 * ang + 256]), mul8(2 * k, tb['sin'][4 * ang])]
            a += ['\t.dw ' + ','.join('%d & $FFFF' % x for x in vals[i:i + 16])
                  for i in range(0, len(vals), 16)]
    a += ['.ENDS', '']
    for name in geo.points:
        a += ['.SECTION ".bike_rot_%s" SUPERFREE' % name, 'bike_rot_%s:' % name]
        tab = tb['rot_' + name]
        for i in range(0, len(tab), 8):
            a.append('\t.dw ' + ','.join('%d & $FFFF,%d & $FFFF' % xy for xy in tab[i:i + 8]))
        a += ['.ENDS', '']

    # --- bike_data.inc ---
    inc = ['; Generated by tools/gen_bike.py.']

    def d(n, v):
        inc.append('.DEFINE %s %d' % (n, v))
    for n, p in (('HANDLE', geo.handle), ('REAR', geo.rear), ('FOOT', geo.foot),
                 ('HIP', geo.hip), ('SHOULDER', geo.shoulder), ('TORSO_C', geo.torso_c)):
        d('BK_%s_J' % n, p[0])
        d('BK_%s_F' % n, p[1])
    d('BK_TORSO_BETA', geo.torso_beta)
    for r in ('thigh', 'leg', 'uparm', 'forearm'):
        d('BK_C_%s' % r.upper(), s8(128 * geo.center_c[r]))
    for n in PARTS + ['frame', 'wheel']:
        d('BK_PAL_%s' % n.upper(), PALETTE[n])
    d('BK_PER_PART', per_part)
    d('BK_N_PART_HALF', N_PART // 2)
    d('BK_N_TURN_HALF', N_TURN // 2)
    d('BK_N_FRAME_HALF', N_FRAME // 2)
    d('BK_N_TURN_FRAME_HALF', N_TURN_FRAME // 2)
    d('BK_FRAME_SPRITES', FRAME_SPRITES)
    d('BK_FRAME_DESC', FRAME_DESC)
    d('BK_FRAME_ROWS', 1 + 3 * FRAME_SPRITES + 16 * FRAME_SPRITES)
    for r in ('s1', 's2'):
        ka, kb = rod_k(geo, r)
        d('BK_%s_KA' % r.upper(), ka)
        d('BK_%s_KB' % r.upper(), kb)
    d('BK_LIMB_X0', LIMB_X0)
    d('BK_LIMB_Y0', LIMB_Y0)
    d('BK_LIMB_NY', LIMB_NY)
    d('OBJ_KINDS', len(obj_kinds))
    d('OBJ_FOODS', len(obj_kinds) - 2)
    # Animation of the objects: frames a step (0.4368 / PHYS_HZ / 0.014)
    # and the angle of the bobbing a step (t * 15.5), times 65536:
    d('OBJ_ANIM_K', int(round(65536 * 0.4368 / hz / 0.014)))
    d('OBJ_BOB_K', int(round(65536 * 0.4368 * 15.5 / hz / (2 * math.pi))))
    d('BIKE_PHYS_HZ', hz)

    # --- bike_data.h ---
    h = ['// Generated by tools/gen_bike.py.', '#ifndef BIKE_DATA_H', '#define BIKE_DATA_H', '',
         '#define OBJ_KINDS %d' % len(obj_kinds),
         '#define OBJ_FOODS %d' % (len(obj_kinds) - 2),
         'extern const u8 bike_wheel_tiles[];   // VRAM tiles 0-127',
         'extern const u16 bike_palettes[];     // OBJ palettes 0-3',
         'extern const u8 obj_kind_frames[];    // frames of each kind of object',
         '', '#endif']
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'bike_data.asm'), 'w') as f:
        f.write('\n'.join(a) + '\n')
    with open(os.path.join(out, 'bike_data.inc'), 'w') as f:
        f.write('\n'.join(inc) + '\n')
    with open(os.path.join(out, 'bike_data.h'), 'w') as f:
        f.write('\n'.join(h) + '\n')
    log.append('tiles: bike %d bytes, objects %d bytes, wheels %d bytes' % (
        blob.size(), obj_blob.size(), len(wheel_vram)))
    log.append('PHYS_HZ %d' % hz)
    with open(os.path.join(out, 'bike_data.log'), 'w') as f:
        f.write('\n'.join(log) + '\n')
    # For the tests (test/bikefix.py): the numbers of the program.
    import pickle
    with open(os.path.join(out, 'bike_data.pkl'), 'wb') as f:
        pickle.dump({'geo': {k: v for k, v in geo.__dict__.items() if k not in ('st', 'j')},
                     'tables': tb, 'pals': [p.tolist() for p in pals],
                     'frame': [[(dx, dy) for dx, dy, _ in spr] for spr in frame],
                     'obj_frames': [len(r) for _, r in obj_kinds], 'hz': hz}, f)
    with open(os.path.join(out, 'bike_images.pkl'), 'wb') as f:
        pickle.dump({'single': single_idx, 'frame': frame_idx, 'wheel': wheel_idx,
                     'obj': obj_idx}, f)


if __name__ == '__main__':
    main()
