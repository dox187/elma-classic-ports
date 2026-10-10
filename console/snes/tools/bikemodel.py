"""The bike and the rider as the original game draws them (kibike of
KIRAJ320.CPP, dobozki of DOBOZ.CPP), for the converter and the tests.

A part is a picture of the LGR mapped onto a parallelogram of the world
(meters, y up): the picture's pixel (0, 0) at r, (xsize-1, 0) at r+u and
(0, ysize-1) at r+v. kibike() returns the parts of a bike state in the
order the game draws them (the later on top).
"""

import math

import numpy as np

# Constants of the game (ADATOK.CPP, KIRAJ320.CPP, LGRFILE.CPP):
WHEEL_R = 0.395          # Kerekrajzsugar
WHEEL_R_LATE = 0.4       # kor2.sugar: the wheel drawn over the turning bike
HEAD_R = 0.238           # Fejsugar
MX, MY = 390.0, 420.0
MALFA = 0.62
MMERET = 0.0045
THIGH_LEN = 0.51         # combhossz
LEG_LEN = 0.51           # labszarhossz
FOREARM_LEN = 0.308 * 1.05   # alkarhossz
UPARM_LEN = 0.328 * 1.05     # felkarhossz

# The four pieces of q1bike (KisboxA..D): x1, y1, x2, y2.
BOXES = [(3, 36, 147, 184), (32, 183, 147, 297), (146, 141, 273, 264),
         (272, 181, 353, 244)]


def v(x, y):
    return np.array([x, y], dtype=float)


def rot90(a):
    return v(-a[1], a[0])


def rotm90(a):
    return v(a[1], -a[0])


def unit(a):
    return a / math.hypot(a[0], a[1])


def rotate(a, alfa):
    s, c = math.sin(alfa), math.cos(alfa)
    return v(c * a[0] - s * a[1], s * a[0] + c * a[1])


def two_circles(r1, r2, l1, l2):
    """ketkormetszete (VEKT2.CPP): the meeting point of two limbs of length
    l1 from r1 and l2 from r2, on the left of r1 -> r2."""
    vv = r2 - r1
    l = math.hypot(vv[0], vv[1])
    if l >= l1 + l2:
        l = l1 + l2 - 0.000001
    if l1 >= l + l2:
        l1 = l + l2 - 0.00001
    if l2 >= l + l1:
        l2 = l + l1 - 0.00001
    e = vv * (1 / l)
    n = rot90(e)
    x = (l1 * l1 - l2 * l2 + l * l) / (2.0 * l)
    m = math.sqrt(max(l1 * l1 - x * x, 0.0))
    return r1 + x * e + m * n


class Part:
    """A picture on the parallelogram r, r+u, r+v (world meters). name:
    the LGR picture (q1bike pieces: 'q1bike:N'). kind: 'wheel', 'head',
    'rod' (kidoboz) or 'frame'. a, b: the ends of a rod, ta, tb, w its
    extensions and half width, mirror: its tukor."""

    def __init__(self, name, r, u, vv, kind, **kw):
        self.name, self.r, self.u, self.v, self.kind = name, r, u, vv, kind
        self.affine = None
        self.__dict__.update(kw)

    def corners(self):
        return [self.r, self.r + self.u, self.r + self.v, self.r + self.u + self.v]


def kidoboz(name, a, b, w, ta, tb, mirror=False, kind='rod'):
    e = unit(b - a)
    b2 = b + e * tb
    a2 = a - e * ta
    vv = b2 - a2
    half = (rot90(e) if mirror else rotm90(e)) * w
    r = a2 - half
    return Part(name, r, vv, half * 2.0, kind, a=a, b=b, w=w, ta=ta, tb=tb,
                mirror=mirror)


def kidobozkerek(name, r, radius, alfa, mirror=False, kind='wheel'):
    vf = v(math.cos(alfa), math.sin(alfa)) * radius
    if mirror:
        p = kidoboz(name, r + vf, r - vf, radius, 0.0, 0.0, True, kind)
    else:
        p = kidoboz(name, r - vf, r + vf, radius, 0.0, 0.0, False, kind)
    p.center, p.alfa, p.radius = r, alfa, radius
    return p


class State:
    """A bike: the physics (meters, y up, radians) and the animation."""

    def __init__(self, body=(2.75, 3.6), body_a=0.0, wheel0=(1.9, 3.0),
                 wheel0_a=0.0, wheel1=(3.6, 3.0), wheel1_a=0.0,
                 rider=(2.75, 4.04), head=None, turned=False, turn=1.0,
                 volt=0.0, volt1=False):
        self.body = v(*body)
        self.body_a = body_a
        self.wheel = [v(*wheel0), v(*wheel1)]
        self.wheel_a = [wheel0_a, wheel1_a]
        self.rider = v(*rider)
        self.turned = turned
        if head is None:
            # szamitfejr (LEPTET.CPP):
            i = v(math.cos(body_a), math.sin(body_a))
            j = rot90(i)
            head = self.rider + (i * 0.09 if turned else -i * 0.09) + j * 0.63
        self.head = v(*head)
        self.turn = turn          # forgas, 0..1
        self.volt = volt          # ugrasnagysag, 0..1
        self.volt1 = volt1        # ugras1volt

    def moved(self, d):
        """The same bike moved by the vector d (meters)."""
        s = State()
        s.__dict__.update(self.__dict__)
        s.body = self.body + d
        s.wheel = [w + d for w in self.wheel]
        s.rider = self.rider + d
        s.head = self.head + d
        return s


def body_frame(st):
    """Mi, Mj, Mr of kibike (meters per q1bike pixel)."""
    jobbra = v(math.cos(st.body_a), math.sin(st.body_a))
    fel = rot90(jobbra)
    if st.turned:
        jobbra = -jobbra
    mi = jobbra * (MMERET * math.cos(MALFA)) + fel * (MMERET * math.sin(MALFA))
    mj = rot90(mi)
    if st.turned:
        mj = -mj
    return mi, mj, st.body.copy()


def body_point(st, px, py):
    """A point given in the coordinates of q1bike (+260) as kibike does."""
    mi, mj, mr = body_frame(st)
    return mi * (px - MX) + mj * (MY - py) + mr


def arm_swing(volt, volt1, turned):
    """alfa and hosszit of the arm while volting (kibike), or None."""
    if volt <= 0.0001:
        return None
    u = 1.0 - volt
    up = not ((volt1 and not turned) or (not volt1 and turned))
    if up:
        hatar, maxalfa, maxh = 0.25, 2.7, -0.3
    else:
        hatar, maxalfa, maxh = 0.2, -1.6, 0.15
    if u < hatar:
        alfa = maxalfa * u / hatar
        h = maxh * u / hatar + 1.0
    else:
        mertek = 1.0 - (u - hatar) / (1.0 - hatar)
        alfa = maxalfa * mertek
        h = maxh * mertek + 1.0
    return alfa, h


def joints(st):
    """The points of the rider and the frame that kibike computes."""
    mi, mj, mr = body_frame(st)
    j = {}
    j['handle'] = mi * (365.0 - MX) + mj * (MY - 292.0) + mr
    j['rear'] = mi * (370.0 - MX) + mj * (MY - 520.0) + mr
    rv = st.rider
    j['hip'] = rv + mi * 75.0 + mj * (-47.0)
    j['shoulder'] = rv + mi * 47.0 + mj * 65.0
    j['torso'] = rv + mi * 41.0 + mj * 70.0
    j['foot'] = mi * (346.0 - MX) + mj * (MY - 514.0) + mr
    if st.turned:
        j['knee'] = two_circles(j['hip'], j['foot'], THIGH_LEN, LEG_LEN)
    else:
        j['knee'] = two_circles(j['foot'], j['hip'], LEG_LEN, THIGH_LEN)
    hand = j['handle']
    sw = arm_swing(st.volt, st.volt1, st.turned)
    if sw:
        alfa, h = sw
        kar = hand - j['shoulder']
        kar = rotate(kar, alfa if st.turned else -alfa) * h
        hand = j['shoulder'] + kar
    j['hand'] = hand
    if st.turned:
        j['elbow'] = two_circles(hand, j['shoulder'], FOREARM_LEN, UPARM_LEN)
    else:
        j['elbow'] = two_circles(j['shoulder'], hand, UPARM_LEN, FOREARM_LEN)
    return j


def turn_squash(st):
    """The squash of the turn: (center, axis, factor) or None."""
    if st.turn >= 0.999:
        return None
    f = -math.cos(st.turn * math.pi)
    return st.body.copy(), v(math.cos(st.body_a), math.sin(st.body_a)), f


def squash_point(p, sq):
    k, ax, f = sq
    return p - ax * (((p - k) @ ax) * (1.0 - f))


def squash_vec(d, sq):
    _, ax, f = sq
    return d - ax * ((d @ ax) * (1.0 - f))


def kibike(st):
    """The parts in the order of drawing."""
    sq = turn_squash(st)
    k1, k2 = st.wheel[0], st.wheel[1]
    front_now = rear_now = True
    if sq:
        f = sq[2]
        if (f > 0.0 and not st.turned) or (f <= 0.0 and st.turned):
            front_now = False
        else:
            rear_now = False
    parts = []
    if front_now:
        parts.append(kidobozkerek('q1wheel', k1, WHEEL_R, st.wheel_a[0]))
    if rear_now:
        parts.append(kidobozkerek('q1wheel', k2, WHEEL_R, st.wheel_a[1]))
    if st.turned:
        k1, k2 = k2, k1
    mi, mj, mr = body_frame(st)
    jt = joints(st)
    body = []
    body.append(kidoboz('q1susp1', k1, jt['handle'], 0.06, 0.05, 0.03))
    body.append(kidoboz('q1susp2', jt['rear'], k2, 0.06, 0.0, 0.1))
    for n, (x1, y1, x2, y2) in enumerate(BOXES):
        r = mi * (x1 + 260 - MX) + mj * (MY - (y1 + 260)) + mr
        p = Part('q1bike:%d' % n, r, mi * (x2 - x1), mj * (y1 - y2), 'frame')
        body.append(p)
    body.append(kidobozkerek('q1head', st.head, HEAD_R, st.body_a, st.turned,
                             kind='head'))
    t = st.turned
    body.append(kidoboz('q1thigh', jt['knee'], jt['hip'], 0.14, 0.03, 0.1, t))
    body.append(kidoboz('q1leg', jt['foot'], jt['knee'], 0.21, 0.03, 0.03, t))
    body.append(kidoboz('q1body', jt['hip'], jt['torso'], 0.2, 0.1, 0.05, t))
    body.append(kidoboz('q1up_arm', jt['elbow'], jt['shoulder'], 0.11, 0.08, 0.1,
                        not t))
    body.append(kidoboz('q1forarm', jt['hand'], jt['elbow'], 0.076, 0.08, 0.1, t))
    if sq:
        for p in body:
            p.affine = sq
            p.r = squash_point(p.r, sq)
            p.u = squash_vec(p.u, sq)
            p.v = squash_vec(p.v, sq)
    parts += body
    if not front_now or not rear_now:
        k1, k2 = st.wheel[0], st.wheel[1]
        if not front_now:
            parts.append(kidobozkerek('q1wheel', k1, WHEEL_R_LATE, st.wheel_a[0]))
        if not rear_now:
            parts.append(kidobozkerek('q1wheel', k2, WHEEL_R_LATE, st.wheel_a[1]))
    return parts


class Pictures:
    """The pictures of the bike from an LGR as index arrays with their
    transparent index (kiskep: the color of the pixel (0, 0); the pieces of
    q1bike all take the first piece's)."""

    def __init__(self, lgr):
        self.pal = np.array(lgr.palette(), dtype=np.uint8)
        self.pics = {}
        for name in ('q1wheel', 'q1head', 'q1body', 'q1thigh', 'q1leg',
                     'q1forarm', 'q1up_arm', 'q1susp1', 'q1susp2'):
            a = np.array(lgr[name].image, dtype=np.uint8)
            self.pics[name] = (a, int(a[0, 0]))
        bike = np.array(lgr['q1bike'].image, dtype=np.uint8)
        lyuk = None
        for n, (x1, y1, x2, y2) in enumerate(BOXES):
            piece = np.full((y2 - y1 + 1, x2 - x1 + 1), 0, dtype=np.uint8)
            # blt8 of the picture into the box (outside the picture: 0):
            h, w = bike.shape
            ys, xs = slice(y1, min(y2 + 1, h)), slice(x1, min(x2 + 1, w))
            sub = bike[ys, xs]
            piece[:sub.shape[0], :sub.shape[1]] = sub
            if lyuk is None:
                lyuk = int(piece[0, 0])
            self.pics['q1bike:%d' % n] = (piece, lyuk)

    def __getitem__(self, name):
        return self.pics[name]


def sample_part(pics, part, wx, wy):
    """The picture's color indices at world points (arrays), -1 where
    transparent, as dobozki samples: floor(0.5 + coordinates)."""
    a, lyuk = pics[part.name]
    h, w = a.shape
    uu = part.u / (w - 1)
    vv = part.v / (h - 1)
    det = uu[0] * vv[1] - vv[0] * uu[1]
    if abs(det) < 1e-12:
        return np.full(wx.shape, -1, dtype=int)
    dx = wx - part.r[0]
    dy = wy - part.r[1]
    kx = (vv[1] * dx - vv[0] * dy) / det
    ky = (-uu[1] * dx + uu[0] * dy) / det
    ix = np.floor(kx + 0.5).astype(int)
    iy = np.floor(ky + 0.5).astype(int)
    inside = (ix >= 0) & (ix < w) & (iy >= 0) & (iy < h) & \
        (kx >= -0.5) & (ky >= -0.5) & (kx <= w - 1 + 0.5) & (ky <= h - 1 + 0.5)
    out = np.full(wx.shape, -1, dtype=int)
    c = a[np.clip(iy, 0, h - 1), np.clip(ix, 0, w - 1)]
    ok = inside & (c != lyuk)
    out[ok] = c[ok]
    return out


def render_pc(pics, parts, x0, y1, width, height, ppm=48.0):
    """The parts as the game draws them: a picture of width x height pixels
    (y down), its top-left pixel at the world point (x0, y1), ppm pixels a
    meter, nearest sampling. Returns color indices, -1 transparent."""
    out = np.full((height, width), -1, dtype=int)
    for p in parts:
        cs = p.corners()
        xs = [(c[0] - x0) * ppm for c in cs]
        ys = [(y1 - c[1]) * ppm for c in cs]
        ax0, ax1 = max(int(math.floor(min(xs))) - 1, 0), min(int(math.ceil(max(xs))) + 1, width)
        ay0, ay1 = max(int(math.floor(min(ys))) - 1, 0), min(int(math.ceil(max(ys))) + 1, height)
        if ax0 >= ax1 or ay0 >= ay1:
            continue
        gx, gy = np.meshgrid(np.arange(ax0, ax1), np.arange(ay0, ay1))
        wx = x0 + gx / ppm
        wy = y1 - gy / ppm
        c = sample_part(pics, p, wx, wy)
        sub = out[ay0:ay1, ax0:ax1]
        sub[c >= 0] = c[c >= 0]
    return out


def render_reference(pics, parts, x0, y1, width, height, scale=0.4, bg=(0, 0, 0)):
    """The game's look scaled: drawn at 48 pixels a meter, then reduced by
    scale with a box filter. Returns an RGB array of width x height."""
    from PIL import Image
    big_w = int(round(width / scale))
    big_h = int(round(height / scale))
    idx = render_pc(pics, parts, x0, y1, big_w, big_h, 48.0)
    rgb = np.empty((big_h, big_w, 3), dtype=np.uint8)
    rgb[:] = bg
    m = idx >= 0
    rgb[m] = pics.pal[idx[m]]
    im = Image.fromarray(rgb).resize((width, height), Image.BOX)
    return np.array(im)
