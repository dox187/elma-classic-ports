"""The drawing of the bike and the objects as src/bike.asm does it, in the
same integer steps, for the tests: what the program writes into the OAM and
the VRAM for a state of the bike, and a picture of it.

  bikefix.State: phys_view, bike_anim and the camera in the program's
  numbers (16.16 meters, u16 angles).
"""

import math
import os
import pickle
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))

PRIO = 0x20                  # sprites behind the front pictures (priority 2)
FLIP_H, FLIP_V = 0x40, 0x80
TURN_DONE = 65470            # forgas >= 0.999: not turning
BUDGET = 1600                # bytes of tiles a frame

# Parts with sprites loaded while drawing (gen_bike.PARTS), then the body:
PARTS = ['thigh', 'leg', 'uparm', 'forearm', 's1a', 's1b', 's2a', 's2b',
         'head', 'torso']
FRAME = 10
# Their places: pair of tile rows (0: tiles 128.., 1: tiles 160..), slot.
SLOT = {0: (0, 0), 1: (0, 1), 2: (0, 2), 3: (0, 3), 4: (0, 4), 5: (0, 5),
        6: (0, 6), 7: (0, 7), 8: (1, 0), 9: (1, 1), 10: (1, 2)}
PAIR_TILE = (128, 160)


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def mul8(a, b):
    """The PPU's multiplication: s16 * s8, bits 8..23 of the product."""
    return s16((s16(a) * b) >> 8)


def asr(v, n):
    return s16(v) >> n


class Data:
    def __init__(self, gen_dir):
        with open(os.path.join(gen_dir, 'bike_data.pkl'), 'rb') as f:
            d = pickle.load(f)
        self.geo = d['geo']
        self.t = d['tables']
        self.pals = d['pals']
        self.frame = d['frame']
        self.obj_frames = d['obj_frames']
        self.hz = d['hz']
        self.inc = {}
        for line in open(os.path.join(gen_dir, 'bike_data.inc')):
            p = line.split()
            if len(p) == 3 and p[0] == '.DEFINE':
                self.inc[p[1]] = int(p[2])
        path = os.path.join(gen_dir, 'bike_images.pkl')
        self.images = pickle.load(open(path, 'rb')) if os.path.exists(path) else None


class State:
    def __init__(self, body=(0, 0), body_a=0, wheel=((0, 0), (0, 0)), wheel_a=(0, 0),
                 rider=(0, 0), head=(0, 0), turned=0, turn=65535, volt=0, volt1=0,
                 org=(0, 0), cam=(0, 0)):
        self.body, self.body_a = body, body_a & 0xFFFF
        self.wheel, self.wheel_a = wheel, wheel_a
        self.rider, self.head = rider, head
        self.turned, self.turn, self.volt, self.volt1 = turned, turn, volt, volt1
        self.org, self.cam = org, cam

    @staticmethod
    def from_model(st, org, cam):
        """From a bikemodel.State (floats) and the level's origin (16.16)
        and the camera (pixels)."""
        def fx(v):
            return int(round(v * 65536))

        def ang(a):
            return int(round(a / (2 * math.pi) * 65536)) & 0xFFFF
        return State(body=(fx(st.body[0]), fx(st.body[1])), body_a=ang(st.body_a),
                     wheel=((fx(st.wheel[0][0]), fx(st.wheel[0][1])),
                            (fx(st.wheel[1][0]), fx(st.wheel[1][1]))),
                     wheel_a=(ang(st.wheel_a[0]), ang(st.wheel_a[1])),
                     rider=(fx(st.rider[0]), fx(st.rider[1])),
                     head=(fx(st.head[0]), fx(st.head[1])), turned=int(st.turned),
                     turn=min(int(st.turn * 65536), 65535),
                     volt=min(int(st.volt * 65536), 65535), volt1=int(st.volt1),
                     org=org, cam=cam)


def lookup(alpha, h, n):
    """The stored picture and the flips of an angle (gen_bike.py)."""
    sh = {32: 11, 64: 10, 128: 9}[n]
    q = ((alpha + (32768 // n)) & 0xFFFF) >> sh
    half = n // 2
    if not h:
        return (q, 0) if q < half else (q - half, FLIP_H | FLIP_V)
    q = -q & (n - 1)
    return (q, FLIP_V) if q < half else (q - half, FLIP_H)


def atan2(vx, vy, t):
    """The angle in 256 steps, times 256: the table by |y| >> 3, |x| >> 3."""
    ax, ay = abs(vx), abs(vy)
    while (ax | ay) >= 512:
        ax >>= 1
        ay >>= 1
    a = t['atan8'][((ay << 3) & 0xFC0) | (ax >> 3)]
    if vx >= 0:
        a = a if vy >= 0 else -a
    else:
        a = 128 - a if vy >= 0 else 128 + a
    return (a & 255) << 8


def conv(p, body):
    """A point of the physics (16.16) from the body's, in units: the bytes
    1-2 of both (1/256 m) subtracted, times 77/64."""
    d8 = s16(((p >> 8) & 0xFFFF) - ((body >> 8) & 0xFFFF))
    return mul8(s16(4 * d8), 77)


def lpx16(d):
    """16.16 meters from the origin to 1/16 level pixels (mod 65536)."""
    if d < 0:
        return 0
    return (((d >> 8) * 4915) >> 12) & 0xFFFF


class Bike:
    """The state the program keeps between frames."""

    def __init__(self, data):
        self.d = data
        self.cur = [None] * 11          # descriptor in the VRAM
        self.cur_flip = [0] * 11
        self.toggle = 0

    def frame(self, s):
        """One frame: returns (oam entries [(x, y, tile, attr, part, sprite
        image)], uploads [(part, desc)], dma bytes)."""
        d, t, g = self.d, self.d.t, self.d.inc
        bx, by = s.body
        bsx = s16(lpx16(bx - s.org[0]) - s.cam[0] * 16)
        bsy = s16(lpx16(s.org[1] - by) - s.cam[1] * 16)

        def rel(p):
            return (conv(p[0], bx), conv(p[1], by))
        w0, w1 = rel(s.wheel[0]), rel(s.wheel[1])
        rider, head = rel(s.rider), rel(s.head)
        th = s.body_a
        ti = th >> 6
        c, sn = t['sin'][ti + 256], t['sin'][ti]
        tr = s.turned

        def add(a, b):
            return (s16(a[0] + b[0]), s16(a[1] + b[1]))

        def sub(a, b):
            return (s16(a[0] - b[0]), s16(a[1] - b[1]))
        # Points fixed to the bike and the rider: tables by the angle.
        ri = (th >> 6) + (1024 if tr else 0)

        def rot(name):
            return tuple(t['rot_' + name][ri])
        handle = rot('handle')
        rear = rot('rear')
        foot = rot('foot')
        hip = add(rider, rot('hip'))
        sh = add(rider, rot('shoulder'))
        torso = add(rider, rot('torso_c'))
        head = add(rider, rot('head'))      # szamitfejr
        # The hand:
        vi = s.volt >> 8
        hand = handle
        if vi:
            up = int(bool(s.volt1) == bool(tr))
            hc, hs = t['volt_c%d' % up][vi], t['volt_s%d' % up][vi]
            kx, ky = sub(handle, sh)
            if tr:
                kar = (mul8(4 * kx, hc) - mul8(4 * ky, hs), mul8(4 * kx, hs) + mul8(4 * ky, hc))
            else:
                kar = (mul8(4 * kx, hc) + mul8(4 * ky, hs), mul8(4 * ky, hc) - mul8(4 * kx, hs))
            hand = add(sh, (s16(kar[0]), s16(kar[1])))

        def d4(v):
            a = max(-127, min(127, asr(v[0], 2)))
            b = max(-127, min(127, asr(v[1], 2)))
            return a * a + b * b
        sg = -1 if tr else 1
        P = {}
        # The legs and the arms from the table by the rider's place in the
        # frame of the bike (mirrored when turned).
        rbx = s16(mul8(2 * rider[0], c) + mul8(2 * rider[1], sn))
        rby = s16(mul8(2 * rider[1], c) - mul8(2 * rider[0], sn))
        if tr:
            rbx = s16(-rbx)
        ix = min(max((rbx - g['BK_LIMB_X0']) >> 2, 0), 63)
        iy = min(max((rby - g['BK_LIMB_Y0']) >> 2, 0), g['BK_LIMB_NY'] - 1)
        idx = iy * 64 + ix
        for name, h in (('thigh', tr), ('leg', tr), ('uparm', 1 - tr), ('forearm', tr)):
            bx, by = t['limb_%s_x' % name][idx], t['limb_%s_y' % name][idx]
            a8 = t['limb_%s_a' % name][idx]
            if tr:
                bx, a8 = -bx, (128 - a8) & 255
            P[name] = [(s16(mul8(2 * bx, c) - mul8(2 * by, sn)),
                        s16(mul8(2 * bx, sn) + mul8(2 * by, c))), (th + (a8 << 8)) & 0xFFFF, h]
        if vi:
            # Volting: the arm swung, computed (ketkormetszete).
            v = sub(hand, sh)
            i = min(d4(v) >> 3, 1023)
            a, b = t['elbow_a'][i], t['elbow_b'][i]
            elbow = (s16(sh[0] + mul8(2 * v[0], a) + mul8(4 * (-v[1] * sg), b)),
                     s16(sh[1] + mul8(2 * v[1], a) + mul8(4 * (v[0] * sg), b)))
            a8 = atan2(v[0], v[1], t) >> 8
            uparm_a = ((a8 + 128 + sg * t['elbow_gu'][i]) & 255) << 8
            forearm_a = ((a8 + 128 - sg * t['elbow_gf'][i]) & 255) << 8

            def rod(name, a, b, cc, al, h):
                v = sub(b, a)
                P[name] = [(s16(a[0] + mul8(2 * v[0], cc)), s16(a[1] + mul8(2 * v[1], cc))), al, h]
            rod('uparm', elbow, sh, g['BK_C_UPARM'], uparm_a, 1 - tr)
            rod('forearm', hand, elbow, g['BK_C_FOREARM'], forearm_a, tr)
        k1, k2 = (w1, w0) if tr else (w0, w1)
        for name, a, b in (('s1', k1, handle), ('s2', rear, k2)):
            # The pieces: from the ends along the rod (its angle's cos, sin).
            v = sub(b, a)
            al = atan2(v[0], v[1], t)
            ec, es = t['sin'][(al >> 6) + 256], t['sin'][al >> 6]
            ka, kb = g['BK_%s_KA' % name.upper()], g['BK_%s_KB' % name.upper()]
            P[name + 'a'] = [(s16(a[0] + mul8(2 * ka, ec)), s16(a[1] + mul8(2 * ka, es))), al, 0]
            P[name + 'b'] = [(s16(b[0] + mul8(2 * kb, ec)), s16(b[1] + mul8(2 * kb, es))), al, 0]
        half = 0x8000 if tr else 0
        P['torso'] = [torso, (th + (0x8000 - g['BK_TORSO_BETA'] if tr else g['BK_TORSO_BETA'])) & 0xFFFF, tr]
        P['head'] = [head, (th + half) & 0xFFFF, tr]
        P['frame'] = [(0, 0), (th + half) & 0xFFFF, tr]
        # The turn:
        late = None
        lv = 4
        if s.turn < TURN_DONE:
            ti2 = s.turn >> 8
            f = t['turn_f'][ti2]
            lv = t['turn_lv'][ti2]
            neg = f < 0
            teff = tr ^ int(neg)
            late = 0 if ((f > 0 and not tr) or (f <= 0 and tr)) else 1
            # The squash as a matrix: (f - 1) * j j^T, times 64.
            gg = t['turn_g'][ti2]
            ma = mul8(c * c, gg) >> 6
            mb = mul8(c * sn, gg) >> 6
            md = mul8(sn * sn, gg) >> 6
            for name, p in P.items():
                if name == 'frame':
                    continue
                px, py = p[0]
                p[0] = (s16(px + mul8(4 * px, ma) + mul8(4 * py, mb)),
                        s16(py + mul8(4 * px, mb) + mul8(4 * py, md)))
            for name, p in P.items():
                if lv == 4:
                    if neg:
                        p[1] = (2 * th + 0x8000 - p[1]) & 0xFFFF
                        p[2] ^= 1
                else:
                    p[1] = (th + (0x8000 if teff else 0)) & 0xFFFF
                    p[2] = teff
        # Pictures:
        want, flip = [None] * 11, [0] * 11
        for i, name in enumerate(PARTS + ['frame']):
            ctr, al, h = P[name]
            if i == FRAME:
                if lv == 4:
                    k, fl = lookup(al, h, 128)
                    want[i] = k
                else:
                    k, fl = lookup(al, h, 64)
                    want[i] = 64 + lv * 32 + k
            else:
                if lv == 4:
                    k, fl = lookup(al, h, 64)
                    want[i] = i * 96 + k
                else:
                    k, fl = lookup(al, h, 32)
                    want[i] = i * 96 + 32 + lv * 16 + k
            flip[i] = fl
        # Loading: which parts this frame.
        def nspr(i, desc):
            return len(self.d.frame[desc]) if i == FRAME else 1
        pend = [i for i in range(11) if want[i] != self.cur[i]]
        for i in range(11):
            if want[i] == self.cur[i]:
                self.cur_flip[i] = flip[i]
        ranges = {}
        accepted = []
        pairs = [0, 1] if self.toggle == 0 else [1, 0]
        if pend:
            self.toggle ^= 1
        left = BUDGET
        for n, pair in enumerate(pairs):
            lo = hi = None
            for i in pend:
                if SLOT[i][0] != pair:
                    continue
                s0 = SLOT[i][1]
                s1 = s0 + nspr(i, want[i]) - 1
                nlo = s0 if lo is None else lo
                if (s1 - nlo + 1) * 128 > left:
                    break
                lo, hi = nlo, s1
                accepted.append(i)
            if lo is not None:
                ranges[pair] = (lo, hi)
                left -= (hi - lo + 1) * 128
        for i in accepted:
            self.cur[i] = want[i]
            self.cur_flip[i] = flip[i]
        dma = sum((hi - lo + 1) * 128 for lo, hi in ranges.values())
        # OAM:
        oam = []

        def put(i, ctr, desc_sprites, tiles, fl, pal, imgs):
            px = s16(bsx + ctr[0] + 8) >> 4
            py = s16(bsy - ctr[1] + 8) >> 4
            for (dx, dy), tile, im in zip(desc_sprites, tiles, imgs):
                if fl & FLIP_H:
                    dx = -dx - 16
                if fl & FLIP_V:
                    dy = -dy - 16
                x, y = px + dx, py + dy
                if -15 <= x <= 255 and -15 <= y <= 223:
                    oam.append((x, y, tile, fl | pal << 1 | PRIO, i, im))

        def wheel(n):
            ctr = (w0, w1)[n]
            k, fl = lookup(s.wheel_a[n], 0, 64)
            tile = (k >> 3) * 32 + (k & 7) * 2
            put(11 + n, ctr, [(-8, -8)], [tile], fl, 0, [('wheel', k)])

        def part(i):
            name = (PARTS + ['frame'])[i]
            if self.cur[i] is None:
                # Not loaded yet: a single part shows its empty tiles.
                if i != FRAME:
                    pair, slot = SLOT[i]
                    pal = g['BK_PAL_%s' % name.upper()]
                    put(i, P[name][0], [(-8, -8)], [PAIR_TILE[pair] + 2 * slot], 0, pal,
                        [('empty', 0)])
                return
            pal = g['BK_PAL_%s' % name.upper()]
            pair, slot = SLOT[i]
            if i == FRAME:
                spr = self.d.frame[self.cur[i]]
                tiles = [PAIR_TILE[pair] + 2 * (slot + n) for n in range(len(spr))]
                base = sum(len(x) for x in self.d.frame[:self.cur[i]])
                imgs = [('frame', base + n) for n in range(len(spr))]
            else:
                spr = [(-8, -8)]
                tiles = [PAIR_TILE[pair] + 2 * slot]
                imgs = [('single', self.cur[i])]
            put(i, P[name][0], spr, tiles, self.cur_flip[i], pal, imgs)
        if late is not None:
            wheel(late)
        for i in (3, 2, 9, 1, 0, 8, FRAME, 7, 6, 5, 4):
            part(i)
        if late is None:
            wheel(1)
            wheel(0)
        else:
            wheel(1 - late)
        return oam, accepted, dma


def preview(data, oam, size=(256, 224)):
    """The sprites (OAM order: the first on top) as an RGB picture with a
    transparent background (alpha channel)."""
    img = np.zeros((size[1], size[0], 4), np.uint8)
    pals = [np.array(p) for p in data.pals]
    for x, y, tile, attr, part, (kind, idx) in reversed(oam):
        if kind == 'empty':
            continue
        q = data.images[kind][idx]
        if attr & FLIP_H:
            q = q[:, ::-1]
        if attr & FLIP_V:
            q = q[::-1]
        pal = pals[(attr >> 1) & 7]
        for j in range(16):
            for i in range(16):
                v = q[j, i]
                X, Y = x + i, y + j
                if v and 0 <= X < size[0] and 0 <= Y < size[1]:
                    img[Y, X, :3] = pal[v - 1]
                    img[Y, X, 3] = 255
    return img


def lpx_round(d):
    """bike_load.c lpx(): level pixels of a distance (16.16), rounded."""
    if d < 0:
        d = 0
    return s16(((d >> 8) * 4915 + 32768) >> 16)


class Objects:
    """objects_load and objects_draw."""

    def __init__(self, data, objs, org):
        self.d = data
        foods = len(data.obj_frames) - 2
        self.tab = []
        self.used = 0
        for i, (t, anim, grav, active, x, y) in enumerate(objs):
            if t == 4:
                continue
            k = 0 if t == 1 else 1 if t == 3 else 2 + anim % foods
            self.tab.append([lpx_round(x - org[0]), lpx_round(org[1] - y), k, i,
                             (i * 151 + 71) & 255])
            self.used |= 1 << k
        self.curf = [None] * 8

    def frame(self, cam, time, active):
        """active: the active flags of phys_objs. Returns (oam, kinds
        loaded)."""
        g = self.d.inc
        ac = ((time * g['OBJ_ANIM_K']) >> 16) & 0xFFFF
        ba = (time * g['OBJ_BOB_K']) & 0xFFFF
        oam = []
        vis = set()
        for x, y, k, i, ph in reversed(self.tab):
            if k >= 2 and not active[i]:
                continue
            sx = x - cam[0] - 8
            if not -15 <= sx <= 255:
                continue
            dy = 0 if k == 1 else self.d.t['bob'][((ba >> 8) + ph) & 255]
            sy = y + dy - cam[1] - 8
            if not -15 <= sy <= 223:
                continue
            if len(oam) < 64:
                oam.append([sx, sy, 192 + 2 * k, PRIO | 3 << 1, k, ['obj', [k, None]]])
                vis.add(k)
        # The frames of the kinds on the screen that changed are loaded.
        loaded = []
        for k, n in enumerate(self.d.obj_frames):
            if self.used >> k & 1 and k in vis:
                f = ac % n
                if f != self.curf[k]:
                    self.curf[k] = f
                    loaded.append(k)
        for o in oam:
            o[5][1][1] = self.curf[o[4]]
        oam = [(o[0], o[1], o[2], o[3], o[4], (o[5][0], tuple(o[5][1]))) for o in oam]
        return oam, loaded
