"""Colors and tiles of the SNES for the converters: palettes of 15 colors
(color 0 is transparent) chosen with k-means, tiles assigned to the palette
that fits them best, 4 bit planar tiles, BGR555 colors.

Everything is deterministic (fixed seeds), so a build gives the same ROM.
"""

import numpy as np


def to555(rgb):
    """RGB 0-255 (float array ..., 3) to the nearest SNES colors, as RGB
    0-255 again (the value the SNES shows: c5 * 255 / 31)."""
    c5 = np.clip(np.round(np.asarray(rgb, dtype=np.float64) * 31.0 / 255.0), 0, 31)
    return c5 * 255.0 / 31.0


def bgr555(rgb):
    """Little endian words of the colors (RGB 0-255, n x 3)."""
    c5 = np.clip(np.round(np.asarray(rgb, dtype=np.float64) * 31.0 / 255.0), 0, 31).astype(np.int64)
    w = c5[:, 0] | (c5[:, 1] << 5) | (c5[:, 2] << 10)
    out = bytearray()
    for v in w.tolist():
        out += bytes((v & 255, v >> 8))
    return bytes(out)


def _nearest(px, centers):
    d = ((px[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    return d.argmin(axis=1), d.min(axis=1)


def kmeans(px, k, weights=None, iters=20, seed=1, fixed=None):
    """k colors for the pixels px (n x 3); fixed: colors that are always
    among the centers (the first ones). Returns the centers (k x 3)."""
    px = np.asarray(px, dtype=np.float64)
    if weights is None:
        weights = np.ones(len(px))
    fixed = np.zeros((0, 3)) if fixed is None else np.asarray(fixed, dtype=np.float64)
    nf = len(fixed)
    # The distinct colors are enough, weighted by their count:
    key = np.round(px * 4).astype(np.int64)
    uniq, inv = np.unique(key[:, 0] * 1000003 + key[:, 1] * 1009 + key[:, 2], return_inverse=True)
    w = np.bincount(inv, weights=weights)
    pts = np.zeros((len(uniq), 3))
    np.add.at(pts, inv, px * weights[:, None])
    pts /= np.maximum(w, 1e-12)[:, None]
    nfree = k - nf
    if len(pts) <= nfree:
        c = np.vstack([fixed, pts])
        if len(c) < k:
            c = np.vstack([c, np.repeat(c[-1:], k - len(c), axis=0)]) if len(c) else np.zeros((k, 3))
        return c
    rng = np.random.RandomState(seed)
    # k-means++ start for the free centers:
    cen = list(fixed)
    if not cen:
        cen.append(pts[np.argmax(w)])
    while len(cen) < k:
        _, d = _nearest(pts, np.array(cen))
        p = d * w
        if p.sum() <= 0:
            cen.append(pts[rng.randint(len(pts))])
        else:
            cen.append(pts[rng.choice(len(pts), p=p / p.sum())])
    cen = np.array(cen, dtype=np.float64)
    if not len(fixed):
        nf = 0
    for _ in range(iters):
        lab, _ = _nearest(pts, cen)
        new = cen.copy()
        for j in range(nf, k):
            m = lab == j
            if m.any():
                new[j] = (pts[m] * w[m, None]).sum(axis=0) / w[m].sum()
        if np.allclose(new, cen):
            break
        cen = new
    return cen


def quantize_tiles(tiles, opaque, npal, ncol=15, iters=6, seed=1, fixed=None):
    """Palettes for the tiles (n x 64 x 3 RGB) whose opaque pixels (n x 64)
    must be drawn: npal palettes of ncol colors (SNES colors, RGB 0-255), the
    palette of every tile and its pixels (0 transparent, 1..ncol).
    fixed: colors every palette must have (put first)."""
    n = len(tiles)
    tiles = np.asarray(tiles, dtype=np.float64)
    if opaque is None:
        opaque = np.ones(tiles.shape[:2], dtype=bool)
    if n == 0:
        return np.zeros((npal, ncol, 3)), np.zeros(0, dtype=np.int64), np.zeros((0, 64), dtype=np.int64)
    # Start: groups of tiles by their average color (k-means on them):
    cnt = np.maximum(opaque.sum(axis=1), 1)
    mean = (tiles * opaque[..., None]).sum(axis=1) / cnt[:, None]
    if npal > 1 and n > npal:
        gc = kmeans(mean, npal, weights=cnt.astype(np.float64), seed=seed)
        tp, _ = _nearest(mean, gc)
    else:
        tp = np.zeros(n, dtype=np.int64)
    pals = np.zeros((npal, ncol, 3))
    for it in range(iters):
        for p in range(npal):
            m = tp == p
            if not m.any():
                # An empty palette takes the tiles that fit worst:
                m = np.zeros(n, dtype=bool)
            px = tiles[m][opaque[m]]
            if len(px) == 0:
                pals[p] = pals[0] if p else 0
                continue
            pals[p] = to555(kmeans(px, ncol, seed=seed + p, fixed=fixed))
        # Reassign every tile to the palette with the least error:
        err = np.zeros((n, npal))
        for p in range(npal):
            d = ((tiles[:, :, None, :] - pals[p][None, None, :, :]) ** 2).sum(axis=3).min(axis=2)
            err[:, p] = (d * opaque).sum(axis=1)
        ntp = err.argmin(axis=1)
        # Palettes nobody uses take the worst tiles:
        for p in range(npal):
            if not (ntp == p).any() and n > npal:
                worst = np.argsort(-err[np.arange(n), ntp])
                for t in worst:
                    if (ntp == ntp[t]).sum() > 1:
                        ntp[t] = p
                        break
        if np.array_equal(ntp, tp) and it > 0:
            break
        tp = ntp
    idx = np.zeros((n, 64), dtype=np.int64)
    for p in range(npal):
        m = tp == p
        if m.any():
            d = ((tiles[m][:, :, None, :] - pals[p][None, None, :, :]) ** 2).sum(axis=3)
            idx[m] = d.argmin(axis=2) + 1
    idx[~opaque] = 0
    return pals, tp, idx


def encode4(idx):
    """A tile of 4 bit pixels (64 values, rows top down) in the planar
    format of the SNES (32 bytes)."""
    idx = np.asarray(idx, dtype=np.int64).reshape(8, 8)
    out = bytearray(32)
    for r in range(8):
        for plane in range(4):
            bits = (idx[r] >> plane) & 1
            b = 0
            for x in range(8):
                b |= int(bits[x]) << (7 - x)
            off = (2 * r + (plane & 1)) + (16 if plane >= 2 else 0)
            out[off] = b
    return bytes(out)


def encode4_many(idx):
    """encode4 of many tiles (n x 64) at once."""
    idx = np.asarray(idx, dtype=np.int64).reshape(-1, 8, 8)
    n = len(idx)
    out = np.zeros((n, 32), dtype=np.uint8)
    weights = (1 << (7 - np.arange(8)))
    for plane in range(4):
        bits = ((idx >> plane) & 1) * weights[None, None, :]
        b = bits.sum(axis=2).astype(np.uint8)            # n x 8 rows
        base = 16 if plane >= 2 else 0
        out[:, base + (plane & 1):base + 16:2] = b
    return out


def decode4(data):
    """Pixels (8 x 8) of a 4 bit tile."""
    d = np.frombuffer(bytes(data), dtype=np.uint8)
    out = np.zeros((8, 8), dtype=np.int64)
    for r in range(8):
        for plane in range(4):
            off = (2 * r + (plane & 1)) + (16 if plane >= 2 else 0)
            b = int(d[off])
            for x in range(8):
                out[r, x] |= ((b >> (7 - x)) & 1) << plane
    return out
