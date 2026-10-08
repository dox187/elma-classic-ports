"""The picture of a level as the original game draws it (ECSET.CPP,
KOVETO.CPP, LGRFILE.CPP), at its own 48 pixels a meter, and its area
average at the 0.4 scale of the SNES (level pixels, levgeom.py).

The game builds the "ecset" of a level at load: rows of pieces that are
ground, sky, or pixels of pictures and textures, each piece with a distance.
For an internal level:

- ground and sky come from the edges of the polygons that are not grass:
  every edge puts a marker into the rows it crosses, ground to the right of
  an edge going down, sky to the right of one going up (ecset::addszakasz);
- the pictures of the level (pictures of the LGR, or a texture through a
  mask) and the grass go in in three phases (ecset::ecset):
  1. pictures clipped to the ground, then the grass: along the line of
     every grass polygon the qup_/qdown_ pictures that follow its slope
     best, and the qgrass texture above them (makevonal, kikovetokepek,
     kiegykovetokep, kovetotextura); these cover only ground;
  2. pictures clipped to the sky: these cover only sky;
  3. the other pictures, over ground and sky;
  where a piece is already there, the nearer one stays (the earlier of two
  as near). Then qgrass right under a piece nearer than 500 gets near too
  (ecset::foltoz). Pieces nearer than 500 are drawn in front of the bike
  (betoltecseteket moves them into the top ecset).

When drawing, ground is the foreground texture anchored to the ecset, the
textures of pieces too; sky is the background texture anchored to the
screen (ecset::kitesz).

With Video Detail Low (State->highquality 0) the game puts no pieces into
the ecset at all: no pictures, no grass, only ground and sky.

Coordinates: the ecset has its origin at the bottom left, column u and row
v (v grows upward). Pixel (u, v) covers [u, u+1) x [v, v+1). A level pixel
px covers u in [2.5 px + cx, 2.5 px + cx + 2.5); a level pixel row py covers
v in (cy - 2.5 py - 2.5, cy - 2.5 py]. cx and cy are halves (the origin of
the ecset sits in the middle of a pixel).
"""

import math

import numpy as np

import elmadata
import levgeom

ARANY = 48.0                   # pixels a meter of the original game
SCALE = 2.5                    # its pixels in a level pixel of the SNES
ECSETSZEL = 20
KELTOLAS = 20                  # a grass picture below the line (LGRFILE.CPP)
FUGGTOLDAS = 20                # qgrass above a grass picture
KOVVONALHOSSZ = 10000          # longest grass line
KEPSZELBAL, KEPSZELJOBB = 120, 50  # pictures this near the edge are left out
FRONT = 500                    # nearer pieces are in front of the bike
GRASS_DIST = 600

# Distances of the state of a pixel (D) that are not pieces:
D_FOLD, D_EG = -1, -2
# Sources of the color of a piece (S):
S_PIC, S_QGRASS, S_TEX = 0, 1, 2   # S_TEX + n: texture n of Textures.texnames

PH_FOLD, PH_EG, PH_NEM = 0, 1, 2


def _meghelyez(d):
    """ECSET.CPP meghelyez: to the middle of a pixel (truncating to int)."""
    return (int(d * ARANY) + 0.5) / ARANY


class Textures:
    """The pictures of an LGR file the level background uses, as arrays of
    the colors of the game's palette."""

    def __init__(self, lgr):
        self.lgr = lgr
        self.pal = np.array(lgr.palette(), dtype=np.float64)   # 256 x 3
        # Grass pictures in the order of the file (koveto::addkep):
        self.grass = []
        for name in lgr.order:
            if name.startswith('qup_') or name.startswith('qdown_'):
                a = np.array(lgr[name].image, dtype=np.uint8)
                up = name.startswith('qup_')
                lejtes = int(round(a.shape[0] - (2 * 20 + 1)))
                self.grass.append((name, a, up, int(a[0, 0]), lejtes))
        self.texnames = []
        self._pics = {}
        self._tex = {}

    def texture(self, name):
        """A texture as the game keeps it: flipped, row 0 is the bottom."""
        if name not in self._tex:
            self._tex[name] = np.array(self.lgr[name].image, dtype=np.uint8)[::-1].copy()
        return self._tex[name]

    def texture_id(self, name):
        if name not in self.texnames:
            self.texnames.append(name)
        return S_TEX + self.texnames.index(name)

    def picture(self, name):
        """A picture or mask, top down: (opaque, palette indices), with the
        transparent color of pictures.lst (LGRFILE.CPP getatlatszosag)."""
        if name in self._pics:
            return self._pics[name]
        a = np.array(self.lgr[name].image, dtype=np.uint8)
        kind = self.lgr.list.get(name, (100, 0, 0, 12))[3]
        h, w = a.shape
        corner = {11: 0, 12: a[0, 0], 13: a[0, w - 1], 14: a[h - 1, 0],
                  15: a[h - 1, w - 1]}
        if kind in corner:
            op = a != corner[kind]
        else:
            op = np.ones_like(a, dtype=bool)
        self._pics[name] = (op, a)
        return self._pics[name]


class Piece:
    """Something put into the ecset: opaque pixels (top down) at column u0,
    top row vtop, with a distance, phase and the source of its colors."""

    def __init__(self, u0, vtop, opaque, src, colors, dist, phase):
        self.u0 = u0
        self.vtop = vtop
        self.opaque = opaque
        self.src = src            # array of S_* (same shape) or one value
        self.colors = colors      # palette indices of S_PIC pixels, or None
        self.dist = dist
        self.phase = phase
        h, w = opaque.shape
        self.u1 = u0 + w
        self.vbot = vtop - h + 1


class PcLevel:
    """The ecset of a level."""

    def __init__(self, lev, tex, fg=None, bg=None, detail=True):
        self.lev = lev
        self.tex = tex
        self.detail = detail          # False: Video Detail Low, no pieces
        self.fg = fg or getattr(lev, 'foreground', 'ground')
        self.bg = bg or getattr(lev, 'background', 'sky')
        if self.fg not in tex.lgr:
            self.fg = 'ground'
        if self.bg not in tex.lgr:
            self.bg = 'sky'
        polys = [p for g, p in lev.polygons if not g]
        xs = [x for p in polys for x, _ in p]
        ys = [y for p in polys for _, y in p]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        ox = _meghelyez(minx - 10000 / ARANY)
        oy = _meghelyez(miny - 1000 / ARANY)
        self.origo = (ox, oy)
        self.maxx = int(((maxx + 10000 / ARANY) - ox) * ARANY)
        self.sorszam = int(((maxy + 1000 / ARANY) - oy) * ARANY)
        # Level pixels of the SNES (whole meters):
        gx, gy = levgeom.origin(lev)
        self.org = (gx / 65536.0, gy / 65536.0)
        self.cx = round((self.org[0] - ox) * ARANY * 2) / 2.0
        self.cy = round((self.org[1] - oy) * ARANY * 2) / 2.0
        self.size = levgeom.size_px(lev)
        self._edges = self._make_edges(polys)
        self._pieces = None
        self.qgrass = tex.texture('qgrass') if 'qgrass' in tex.lgr else None

    # ----------------------------------------------------------- ground
    def _make_edges(self, polys):
        """The markers of the edges: for every edge its rows and the
        parameters of ecset::addszakasz."""
        ox, oy = self.origo
        out = []
        for poly in polys:
            n = len(poly)
            for j in range(n):
                x1, y1 = poly[j]
                x2, y2 = poly[(j + 1) % n]
                rx = (x1 - ox) * ARANY - 0.5
                ry = (y1 - oy) * ARANY - 0.5
                vx = (x2 - x1) * ARANY
                vy = (y2 - y1) * ARANY
                fold = vy < 0
                if vy < 0:
                    rx, ry = rx + vx, ry + vy
                    vx, vy = -vx, -vy
                if vy < 0.001:
                    continue
                ya = int(ry + 1)
                yb = int(ry + vy)
                if yb < ya:
                    continue
                m = vx / vy
                dy1, dy2 = ry, ry + vy
                dx1, dx2 = rx, rx + vx
                a = (dx2 * dy1 - dx1 * dy2) / (dy1 - dy2)
                out.append((ya, yb, m, a, fold))
        return out

    def ground_rows(self, v0, v1):
        """For the ecset rows v0..v1-1: the x of the markers that remain of
        each row (ecset rendez), the kind changing at each, ground first."""
        rows = {}
        for ya, yb, m, a, fold in self._edges:
            lo, hi = max(ya, v0), min(yb, v1 - 1)
            if hi < lo:
                continue
            ys = np.arange(lo, hi + 1)
            xs = (m * ys + a + 1.0).astype(np.int64)
            for y, x in zip(ys.tolist(), xs.tolist()):
                rows.setdefault(y, []).append((x, fold))
        out = {}
        for y, marks in rows.items():
            # Stable sort by x, then pairs on one x: equal ones once,
            # different ones both left out (from the start again):
            marks.sort(key=lambda t: t[0])
            changed = True
            while changed:
                changed = False
                for i in range(len(marks) - 1):
                    if marks[i][0] == marks[i + 1][0]:
                        if marks[i][1] == marks[i + 1][1]:
                            del marks[i + 1]
                        else:
                            del marks[i:i + 2]
                        changed = True
                        break
            # The row starts with ground; then the same kind twice in a row
            # is one:
            res = []
            cur = True
            for x, f in marks:
                if f != cur:
                    res.append(x)
                    cur = f
            out[y] = res
        return out

    def ground_mask(self, u0, u1, v0, v1):
        """Ground (True) of the ecset pixels u0..u1-1, v0..v1-1, rows from
        v1-1 down to v0 (top down). Outside the ecset it is ground too."""
        rows = self.ground_rows(v0, v1)
        w = u1 - u0
        h = v1 - v0
        mask = np.ones((h, w), dtype=bool)
        for v, xs in rows.items():
            if not xs:
                continue
            d = np.zeros(w + 1, dtype=np.int32)
            for x in xs:
                d[min(max(x - u0, 0), w)] += 1
            mask[v1 - 1 - v] = (np.cumsum(d[:w]) % 2) == 0
        uu = np.arange(u0, u1)
        vv = np.arange(v1 - 1, v0 - 1, -1)
        mask[:, (uu < ECSETSZEL) | (uu > self.maxx - ECSETSZEL)] = True
        mask[(vv < ECSETSZEL) | (vv > self.sorszam - ECSETSZEL), :] = True
        return mask

    # ----------------------------------------------------------- pieces
    def _sprites(self):
        """The pictures of the level as pieces, by phase, in the order the
        game puts them in (ecset::addspriteok, addegymaszk)."""
        ox, oy = self.origo
        out = {PH_FOLD: [], PH_EG: [], PH_NEM: []}
        clip2phase = {elmadata.CLIP_GROUND: PH_FOLD, elmadata.CLIP_SKY: PH_EG,
                      elmadata.CLIP_NONE: PH_NEM}
        lgr = self.tex.lgr
        for phase in (PH_FOLD, PH_EG, PH_NEM):
            for p in getattr(self.lev, 'pictures', []):
                if clip2phase.get(p.clipping) != phase:
                    continue
                x1 = int((p.x - ox) * ARANY)
                y1 = int((p.y - oy) * ARANY)
                if p.name:
                    if p.name not in lgr:
                        continue
                    op, idx = self.tex.picture(p.name)
                    if x1 < KEPSZELBAL or x1 + op.shape[1] >= self.maxx - KEPSZELJOBB:
                        break     # this and every later picture is left out
                    out[phase].append(Piece(x1, y1, op, S_PIC, idx, p.distance, phase))
                else:
                    if not p.texture or not p.mask or p.texture not in lgr or p.mask not in lgr:
                        continue
                    op, _ = self.tex.picture(p.mask)
                    if x1 < KEPSZELBAL or x1 + op.shape[1] >= self.maxx - KEPSZELJOBB:
                        continue
                    out[phase].append(Piece(x1, y1, op, self.tex.texture_id(p.texture),
                                            None, p.distance, phase))
        return out

    def _makevonal(self, poly):
        """KOVETO.CPP makevonal: the y of the line of a grass polygon for
        every column from x0, or None."""
        ox, oy = self.origo
        n = len(poly)
        maxx = 0.0
        p1 = 0
        for i in range(n):
            j = (i + 1) % n
            d = abs(poly[i][0] - poly[j][0])
            if d > maxx:
                p1 = i
                maxx = d
        if maxx < 0.0001:
            return None
        elore = 1
        p2 = (p1 + 1) % n
        if poly[p1][0] < poly[p2][0]:
            elore = 0
        x0 = -1
        cur = -1
        ytomb = {}
        for _ in range(n - 1):
            if elore:
                p1 = (p1 + 1) % n
                p2 = (p2 + 1) % n
            else:
                p1 = (p1 - 1) % n
                p2 = (p2 - 1) % n
            pk, pn = (p1, p2) if elore else (p2, p1)
            r1, r2 = poly[pk], poly[pn]
            if r1[0] > r2[0]:
                continue
            # (elmadata's y is the game's -y of the polygon points)
            x1 = int((r1[0] - ox) * ARANY)
            y1 = (r1[1] - oy) * ARANY
            x2 = int((r2[0] - ox) * ARANY)
            y2 = (r2[1] - oy) * ARANY
            if x1 < 0 or x2 < 0:
                return None
            if cur < 0:
                cur = x1
                x0 = x1
                ytomb[0] = int(y1)
            if x1 >= x2:
                continue
            if x1 - x0 >= KOVVONALHOSSZ:
                continue
            if cur < x1 - 1:
                continue
            for x in range(x1, x2 + 1):
                if x < cur:
                    continue
                if x - x0 >= KOVVONALHOSSZ:
                    break
                y = y1 + (y2 - y1) * (float(x) - x1) / (x2 - x1)
                ytomb[x - x0] = int(y)
                cur = x
        if x0 < 0:
            return None
        hossz = cur - x0 + 1
        return x0, [ytomb[i] for i in range(hossz)]

    def grass_pieces(self):
        """Every grass picture of the level: (index, xo, yo) with yo the
        bottom row of the picture (after keltolas), in the order the game
        puts them into the ecset."""
        pics = self.tex.grass
        if self.qgrass is None or len(pics) < 2:
            return []
        out = []
        for g, poly in self.lev.polygons:
            if not g:
                continue
            line = self._makevonal(poly)
            if not line:
                continue
            x0, yt = line
            hossz = len(yt)
            curx, cury = x0, yt[0]
            while curx < x0 + hossz:
                best, bi, bdy = 10000, -1, 0
                for i, (_, a, up, _, lejtes) in enumerate(pics):
                    dy = lejtes if up else -lejtes
                    ujx = curx + a.shape[1]
                    vy = yt[hossz - 1] if ujx >= x0 + hossz else yt[ujx - x0]
                    e = abs(cury + dy - vy)
                    if e < best:
                        best, bi, bdy = e, i, dy
                _, a, up, _, lejtes = pics[bi]
                yo = cury - KELTOLAS - (0 if up else lejtes)
                out.append((bi, curx, yo))
                curx += a.shape[1]
                cury += bdy
        return out

    def pieces(self):
        """All pieces in the order the game puts them in."""
        if self._pieces is not None:
            return self._pieces
        if not self.detail:
            self._pieces = []
            return self._pieces
        sp = self._sprites()
        out = list(sp[PH_FOLD])
        for bi, xo, yo in self.grass_pieces():
            _, a, up, atl, _ = self.tex.grass[bi]
            ph, pw = a.shape
            opaque = a != atl
            above = np.cumsum(opaque, axis=0) == 0
            # Rows top down: FUGGTOLDAS rows of qgrass, then the picture,
            # qgrass in its transparent pixels above the first opaque one.
            src = np.full((ph + FUGGTOLDAS, pw), -1, dtype=np.int16)
            src[:FUGGTOLDAS] = S_QGRASS
            src[FUGGTOLDAS:][above] = S_QGRASS
            src[FUGGTOLDAS:][opaque] = S_PIC
            col = np.zeros(src.shape, dtype=np.uint8)
            col[FUGGTOLDAS:] = a
            # Only grass pictures that fit (kovetomaxx/y) get qgrass; all do.
            top = yo + ph + FUGGTOLDAS - 1
            out.append(Piece(xo, top, src >= 0, src, col, GRASS_DIST, PH_FOLD))
        out += sp[PH_EG] + sp[PH_NEM]
        self._pieces = out
        return out

    # ----------------------------------------------------------- render
    def render(self, u0, u1, v0, v1):
        """The ecset on the pixels u0..u1-1, v0..v1-1, top down: the ground
        mask of the polygons, the distance of every pixel (D_FOLD, D_EG or
        a piece), the source of its color (S_*) and its palette index (sky
        pixels: 0)."""
        # One more row on top for foltoz:
        vt = v1 + 1
        h, w = vt - v0, u1 - u0
        mask = self.ground_mask(u0, u1, v0, vt)
        D = np.where(mask, D_FOLD, D_EG).astype(np.int32)
        S = np.full((h, w), -1, dtype=np.int16)
        C = np.zeros((h, w), dtype=np.uint8)
        vrow = np.arange(vt - 1, v0 - 1, -1)
        inside = (vrow >= 0) & (vrow < self.sorszam)
        levon = False
        for pc in self.pieces():
            if pc.phase == PH_NEM and not levon:
                D[D >= 10000] -= 10000
                levon = True
            if pc.u1 <= u0 or pc.u0 >= u1 or pc.vbot >= vt or pc.vtop < v0:
                continue
            r0 = (vt - 1) - pc.vtop           # window row of the piece's row 0
            c0 = pc.u0 - u0
            ph, pw = pc.opaque.shape
            a0, a1 = max(0, -r0), min(ph, h - r0)
            b0, b1 = max(0, -c0), min(pw, w - c0)
            if a1 <= a0 or b1 <= b0:
                continue
            sl = (slice(r0 + a0, r0 + a1), slice(c0 + b0, c0 + b1))
            o = pc.opaque[a0:a1, b0:b1] & inside[r0 + a0:r0 + a1, None]
            cur = D[sl]
            d = pc.dist
            if pc.phase == PH_FOLD:
                ok = (cur == D_FOLD) | ((cur >= 0) & (d < cur))
            elif pc.phase == PH_EG:
                d += 10000
                ok = (cur == D_EG) | ((cur >= 0) & (d < cur))
            else:
                ok = (cur < 0) | (d < cur)
            ok &= o
            D[sl] = np.where(ok, d, cur)
            src = pc.src if np.isscalar(pc.src) else pc.src[a0:a1, b0:b1]
            S[sl] = np.where(ok, src, S[sl])
            if pc.colors is not None:
                C[sl] = np.where(ok, pc.colors[a0:a1, b0:b1], C[sl])
        if not levon:
            D[D >= 10000] -= 10000
        # foltoz: qgrass under a near piece of something else gets near:
        q = (S[1:] == S_QGRASS) & (D[1:] > FRONT)
        up = (D[:-1] >= 0) & (S[:-1] != S_QGRASS) & (D[:-1] <= FRONT)
        rows_ok = ((vrow[1:] >= 10) & (vrow[1:] < self.sorszam - 10))[:, None]
        f = q & up & rows_ok
        D[1:][f] = 223
        D, S, C, mask = D[1:], S[1:], C[1:], mask[1:]
        # Colors of the textures:
        vs = np.arange(v1 - 1, v0 - 1, -1)
        us = np.arange(u0, u1)
        fold = self.tex.texture(self.fg)
        C = np.where(D == D_FOLD, fold[np.mod(vs, fold.shape[0])][:, np.mod(us, fold.shape[1])], C)
        if self.qgrass is not None:
            qg = self.qgrass
            C = np.where(S == S_QGRASS, qg[np.mod(vs, qg.shape[0])][:, np.mod(us, qg.shape[1])], C)
        for n, name in enumerate(self.tex.texnames):
            m = S == S_TEX + n
            if m.any():
                t = self.tex.texture(name)
                C = np.where(m, t[np.mod(vs, t.shape[0])][:, np.mod(us, t.shape[1])], C)
        C[D == D_EG] = 0
        return mask, D, S, C

    # ----------------------------------------------------------- windows
    def window(self, px0, py0, w, h):
        """Ecset pixels covering the level pixels px0..px0+w-1,
        py0..py0+h-1: (u0, u1, v0, v1) and the offsets of the level pixel
        grid in the doubled pixels of the window (see box)."""
        ua = 2.5 * px0 + self.cx
        u0 = int(math.floor(ua))
        u1 = int(math.ceil(2.5 * (px0 + w) + self.cx)) + 1
        vtop = self.cy - 2.5 * py0
        vbot = self.cy - 2.5 * (py0 + h)
        v1 = int(math.floor(vtop)) + 1
        v0 = int(math.floor(vbot)) - 1
        offx = int(round(2 * (ua - u0)))
        offy = int(round(2 * (v1 - vtop)))
        return u0, u1, v0, v1, offx, offy


def box(a, offx, offy, w, h):
    """Area average of 2.5 x 2.5 pixels: a is (rows, cols[, ch]) of a
    window, the level pixel grid starts offx/offy doubled pixels in."""
    a = np.repeat(np.repeat(a, 2, axis=0), 2, axis=1)
    a = a[offy:offy + 5 * h, offx:offx + 5 * w]
    if a.ndim == 2:
        return a.reshape(h, 5, w, 5).mean(axis=(1, 3))
    return a.reshape(h, 5, w, 5, a.shape[2]).mean(axis=(1, 3))


def sky_row_map(height_pc, texh):
    """ecset.cpp egkepsor: the row of the (flipped) background texture for
    each row of the picture from its bottom."""
    r = np.arange(height_pc)
    if texh < 480:
        return r % texh
    r = r % (2 * texh)
    return np.where(r >= texh, 2 * texh - 1 - r, r)


def pc_frame(pl, cam_x, cam_y, w=256, h=224, sky_dx=None):
    """The picture of the original game at the camera (level pixels of the
    top left corner), averaged to the SNES scale: an RGB float array, the
    ground coverage and the coverage of the pieces in front of the bike.
    The sky is aligned to the bottom of the picture and moves at half speed
    (ecset::kitesz)."""
    u0, u1, v0, v1, offx, offy = pl.window(cam_x, cam_y, w, h)
    mask, D, S, C = pl.render(u0, u1, v0, v1)
    sky = pl.tex.texture(pl.bg)
    sh, sw = sky.shape
    if sky_dx is None:
        sky_dx = (2.5 * cam_x + pl.cx) / 2.0
    vbot = pl.cy - 2.5 * (cam_y + h)
    rows_from_bottom = np.floor(np.arange(v1 - 1, v0 - 1, -1) - vbot).astype(np.int64)
    rmap = sky_row_map(int(rows_from_bottom.max()) + 2, sh)
    sr = rmap[np.clip(rows_from_bottom, 0, None)]
    ua = 2.5 * cam_x + pl.cx
    scol = np.floor(sky_dx + (np.arange(u0, u1) - ua)).astype(np.int64) % sw
    skyidx = sky[sr][:, scol]
    idx = np.where(D == D_EG, skyidx, C)
    rgb = pl.tex.pal[idx]
    front = (D >= 0) & (D < FRONT)
    return (box(rgb, offx, offy, w, h), box((D != D_EG).astype(np.float64), offx, offy, w, h),
            box(front.astype(np.float64), offx, offy, w, h))


def pc_camera(pl, body_x, body_y, baljobb=1.0, w=640, h=480):
    """The bottom left pixel of the ecset in the game's picture (kepxe1,
    ye1) for the center of the bike (KIRAJ320.CPP kirakegyjatekost, zoom 1;
    baljobb 1 puts the bike on the right as at the start)."""
    mo_bal = (w / ARANY) * 0.15
    mo_dx = w / ARANY - 2 * mo_bal
    mo_y = h / ARANY / 2.0
    sx = body_x - (mo_bal + baljobb * mo_dx)
    sy = body_y - mo_y
    return int((sx - pl.origo[0]) * ARANY), int((sy - pl.origo[1]) * ARANY)


def pc_picture(pl, kepxe1, ye1, w=640, h=480):
    """The game's picture (palette indices, top down) of the background
    with its bottom left pixel at ecset pixel (kepxe1, ye1), and the pixels
    in front of the bike (ecset::kitesz of both ecsets)."""
    u0, u1, v0, v1 = kepxe1, kepxe1 + w, ye1, ye1 + h
    mask, D, S, C = pl.render(u0, u1, v0, v1)
    sky = pl.tex.texture(pl.bg)
    sh, sw = sky.shape
    sr = sky_row_map(h, sh)[::-1]
    egdx = (kepxe1 // 2) % sw
    scol = (egdx + np.arange(w)) % sw
    idx = np.where(D == D_EG, sky[sr][:, scol], C)
    return idx, (D >= 0) & (D < FRONT)


def _avg_periodic(f, a, b):
    """Average of the periodic piecewise constant f (n x ..., pixel k covers
    [k, k+1)) over [a, b) for the arrays a, b (same shape)."""
    n = f.shape[0]
    cum = np.concatenate([np.zeros((1,) + f.shape[1:]), np.cumsum(f, axis=0)])
    total = cum[-1]
    ex = (None,) * (f.ndim - 1)

    def integral(x):
        q = np.floor(x / n)
        r = x - q * n
        k = np.clip(np.floor(r).astype(np.int64), 0, n - 1)
        return q[(...,) + ex] * total + cum[k] + (r - k)[(...,) + ex] * f[k]
    return (integral(b) - integral(a)) / (b - a)[(...,) + ex]


def texture_pattern(pl, name, px_n, py_n, kx, ky, anchor):
    """The texture name as the SNES draws it over the level: a pattern of
    px_n x py_n level pixels holding kx x ky periods of the texture (so its
    scale may differ a little from 2.5), placed so that at the level pixel
    anchor (px, py) it covers the same part of the texture as the game;
    level pixel (px, py) shows pattern[py % py_n][px % px_n]. RGB 0-255,
    area averages of the texture's pixels."""
    t = pl.tex.pal[pl.tex.texture(name)]          # rows from the bottom
    th, tw = t.shape[:2]
    sx = kx * tw / float(px_n)
    sy = ky * th / float(py_n)
    ax, ay = anchor
    i = np.arange(px_n)
    j = np.arange(py_n)
    ua = 2.5 * ax + pl.cx + sx * (i - ax)
    a = _avg_periodic(np.transpose(t, (1, 0, 2)), ua, ua + sx)   # px_n x th x 3
    va = pl.cy - 2.5 * ay - sy * (j - ay)
    b = _avg_periodic(np.transpose(a, (1, 0, 2)), va - sy, va)    # py_n x px_n x 3
    return b


def level_classes(pl, strip=96):
    """The whole level at the SNES scale, by what its pixels show: for
    every level pixel the share (of the 2.5 x 2.5 pixels of the game) of
    sky, of the ground texture, of the texture of each kind of masked
    picture (pl.tex.texnames), and of everything else (pictures, grass);
    the average color of the latter (RGB 0-255) and the share of pieces in
    front of the bike. Returns (sky, fold, tex, other, orgb, front) with
    tex a list by texture."""
    w, h = pl.size
    pl.pieces()
    ntex = len(pl.tex.texnames)
    sky = np.zeros((h, w), dtype=np.float32)
    fold = np.zeros((h, w), dtype=np.float32)
    tex = [np.zeros((h, w), dtype=np.float32) for _ in range(ntex)]
    other = np.zeros((h, w), dtype=np.float32)
    orgb = np.zeros((h, w, 3), dtype=np.float32)
    front = np.zeros((h, w), dtype=np.float32)
    for y0 in range(0, h, strip):
        sh = min(strip, h - y0)
        u0, u1, v0, v1, offx, offy = pl.window(0, y0, w, sh)
        mask, D, S, C = pl.render(u0, u1, v0, v1)
        sl = slice(y0, y0 + sh)
        sky[sl] = box((D == D_EG).astype(np.float32), offx, offy, w, sh)
        fold[sl] = box((D == D_FOLD).astype(np.float32), offx, offy, w, sh)
        for n in range(ntex):
            m = (D >= 0) & (S == S_TEX + n)
            if m.any():
                tex[n][sl] = box(m.astype(np.float32), offx, offy, w, sh)
        oth = (D >= 0) & (S < S_TEX)
        if oth.any():
            g = box(oth.astype(np.float32), offx, offy, w, sh)
            other[sl] = g
            s = box(pl.tex.pal[C].astype(np.float32) * oth[..., None], offx, offy, w, sh)
            with np.errstate(invalid='ignore', divide='ignore'):
                orgb[sl] = np.where(g[..., None] > 0, s / np.maximum(g, 1e-9)[..., None], 0)
        fr = (D >= 0) & (D < FRONT)
        if fr.any():
            front[sl] = box(fr.astype(np.float32), offx, offy, w, sh)
    return sky, fold, tex, other, orgb, front


def level_layers(pl, strip=96):
    """The whole level at the SNES scale: ground coverage (0..1, not sky),
    the share of the opaque part that is pieces (pictures, grass, textures
    of pictures; 0..1), the average color of those pieces (RGB 0-255), and
    the share of the opaque part in front of the bike."""
    w, h = pl.size
    cov = np.zeros((h, w), dtype=np.float32)
    palpha = np.zeros((h, w), dtype=np.float32)
    prgb = np.zeros((h, w, 3), dtype=np.float32)
    front = np.zeros((h, w), dtype=np.float32)
    have = bool(pl.pieces())
    for y0 in range(0, h, strip):
        sh = min(strip, h - y0)
        u0, u1, v0, v1, offx, offy = pl.window(0, y0, w, sh)
        mask, D, S, C = pl.render(u0, u1, v0, v1)
        c = box((D != D_EG).astype(np.float32), offx, offy, w, sh)
        cov[y0:y0 + sh] = c
        if not have:
            continue
        isp = D >= 0
        if not isp.any():
            continue
        g = box(isp.astype(np.float32), offx, offy, w, sh)
        rgb = pl.tex.pal[C].astype(np.float32) * isp[..., None]
        s = box(rgb, offx, offy, w, sh)
        f = box(((D >= 0) & (D < FRONT)).astype(np.float32), offx, offy, w, sh)
        with np.errstate(invalid='ignore', divide='ignore'):
            palpha[y0:y0 + sh] = np.where(c > 0, g / np.maximum(c, 1e-9), 0)
            prgb[y0:y0 + sh] = np.where(g[..., None] > 0,
                                        s / np.maximum(g, 1e-9)[..., None], 0)
            front[y0:y0 + sh] = np.where(c > 0, f / np.maximum(c, 1e-9), 0)
    return cov, palpha, prgb, front
