"""Converts the background of the internal levels for the SNES (src/map.asm):
the ground, grass and pictures of BG1 and the sky of BG2, as the original
game draws them (mapmodel.py), scaled to 0.4.

  gen_map.py ELMA_RES ELMA_LGR OUT_DIR [-j JOBS] [--levels 0,1,...]

Writes OUT_DIR/map_data.asm (with the binary parts in OUT_DIR/map/),
OUT_DIR/map_data.h and OUT_DIR/map_report.txt.

Every level also gets the cells of Video Detail Low (only the ground of the
polygons: air, the foreground texture and its edges), stored as the
differences from High.

BG1 is made of 8x8 cells:
- air: the sky shows through (tile 0, transparent);
- texture: all pixels of the foreground texture, or of the texture of the
  masked pictures of the level (a second texture, e.g. stone3 through
  maskbig), with its tile given by the place of the cell in the texture's
  pattern (VRAM tiles 1..);
- edge: a texture and air: a 1 bit mask of the cell applied to the
  texture's tile when the cell comes onto the screen;
- complex: anything else (pictures, grass, two textures): a tile of its
  own, with the priority bit if most of it is in front of the bike.
A texture is resampled to a pattern of whole tiles that holds a whole
number of its periods (as big as the VRAM left by the level allows), a
little bigger or smaller than 0.4 times if it has to be, and placed so that
at the start of the level it lies exactly where the game puts it.

Palettes: 1-2 sky, 3 the foreground texture, 4 the second texture (if the
level has one), the rest the complex tiles.

ROM format (read by src/map.asm):

  map_level_info: 32 bytes a level:
    +0 wc, hc (cells), +4 cw, ch (chunks of 8x8 cells),
    +8 dir (24 bit: cw*ch words, row by row), +11 bank of the chunks,
    +12 texture tiles (24 bit: the foreground's then the second's),
    +15 ntx, nty (foreground pattern in tiles), +17 ntx2, nty2 (0: none),
    +19 palettes 3-7 (24 bit, 80 colors), +22 complex tile base (global
    number of the level's tile 0), +24 sky set, +25 skyk (BG2 scroll is
    (cam_x + skyk) / 2), +27 texture tiles in all, +29 address of the
    chunks, +31 unused.
  A word of the directory: 0 all air, 1 all foreground texture, else
  $8000 + the offset of a mixed chunk from the address of the chunks
  (in their bank): 8 bytes of special
  cells (a row a byte, bit 7 the left cell), 8 bytes of foreground cells
  (of the cells that are not special; of the special ones: mostly ground,
  shown with the foreground's tile while the cell's own is not ready), 8
  bytes of the special cells before each row, then a word for each special
  cell, row by row:
    bit 15 set: complex, bit 14 priority, bits 12-13 palette - 4, bits 0-11
      the level's tile number;
    bit 15 clear: bit 14 the texture (0 foreground, 1 second), bits 0-13
      the mask (0: the full mask, the texture's own tile).
  A word of the directory of 2..$7FFF is a chunk that Video Detail Low
  shows differently: 2 + the offset of a pair of words in the low part
  of the level, the word of the directory with High detail and the one
  with Low. A word of Low of 2..$7FFF is a mixed chunk of the low part (2
  + its offset), else as in the directory. With Low detail there are no
  complex cells and no second texture (the original draws no pictures
  and no grass then, ECSET.CPP).
  map_level_low: 4 bytes a level: the low part (24 bit, 0: none), 0.
  map_masks_N: 2048 masks of 16 bytes (every row of the 8x8 mask twice, bit
    7 the left pixel), map_mask_bank/map_mask_base: bank and address of
    each part.
  map_tiles_N: 1024 complex tiles of 32 bytes, map_tile_bank/map_tile_base.
  map_sky_info: 16 bytes a sky: tiles (24 bit), their size in bytes,
    columns (24 bit: ncol columns of 28 BG2 map words), palettes 1-2 (24
    bit), ncol, 1 if 256 is a multiple of the pattern's width.

The sky is the background texture, aligned to the bottom of the screen
(the game's sky does not move vertically), repeated horizontally at half
speed; BG2 holds 28 rows of tiles, its columns are those of the pattern.
"""

import argparse
import json
import os
import struct
import time
from multiprocessing import Pool

import numpy as np

import elmadata
import levgeom
import mapmodel
import tileq
from lgr import Lgr

BG1_TILES = 704
BG_ROWS = 28                    # tile rows of the screen
PAL_SKY = 1                     # BG palettes 1-2
PAL_TEX = 3                     # 3 foreground texture, 4 second texture
PAL_CPLX = 4                    # complex tiles: 4-7 (5-7 with a second texture)
MASKS_PER_BANK = 2048           # 16 bytes each
TILES_PER_BANK = 1024           # 32 bytes each
CHUNK = 8                       # cells
# The cells BG1 keeps ready around the screen (src/map.asm MAP_COLS,
# MAP_ROWS): the cache of edge and complex tiles must hold all of them.
FILL_W, FILL_H = 35, 31
CACHE_SLACK = 16
TEX2_MAX_TILES = 144
TEX_MAX_TILES = 240              # (ROM: 32 bytes each, in every level)
# A pixel of a texture differs from the texture this much at most (in a
# color channel 0-255) to count as the texture:
PURE_DIFF = 10
# Complex tiles of a level that differ less than this (average and most of
# a pixel, 0-255 in the channel that differs most) are stored once:
MERGE_MEAN = 6
MERGE_MAX = 48


def axis_candidates(n, scale=0.4, most=336):
    """Pattern sizes (pixels, multiple of 8, at most most) for a texture n
    pixels long: (size, periods, relative error), the best for each size."""
    best = {}
    for k in range(1, 24):
        p = int(round(n * scale * k / 8.0)) * 8
        if p < 8 or p > most:
            continue
        err = abs(p / (n * scale * k) - 1)
        if p not in best or err < best[p][2]:
            best[p] = (p, k, err)
    return sorted(best.values())


def choose_pattern(w, h, max_tiles):
    """The pattern of a w x h texture with the smallest error in at most
    max_tiles tiles: (px, kx, py, ky)."""
    best = None
    small = None
    for px, kx, ex in axis_candidates(w):
        for py, ky, ey in axis_candidates(h, most=256):
            t = (px // 8) * (py // 8)
            if small is None or (t, max(ex, ey)) < small[0]:
                small = ((t, max(ex, ey)), (px, kx, py, ky))
            if t > max_tiles:
                continue
            # Errors within half a percent are as good, then the smaller
            # error of the other direction, then fewer tiles:
            key = (int(round(max(ex, ey) * 200)), int(round((ex + ey) * 200)), t)
            if best is None or key < best[0]:
                best = (key, (px, kx, py, ky))
    if best is None:
        return small[1]
    return best[1]


def window_max(special, w, h):
    """The most special cells in any w x h window of cells."""
    s = special.astype(np.int64)
    hh, ww = s.shape
    if hh < h or ww < w:
        p = np.zeros((max(hh, h), max(ww, w)), dtype=np.int64)
        p[:hh, :ww] = s
        s = p
    i = np.pad(s.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    return int((i[h:, w:] - i[:-h, w:] - i[h:, :-w] + i[:-h, :-w]).max())


def cells_of(a, hc, wc):
    """(rows, cols, ...) of level pixels to (hc, wc, 64, ...) of cells."""
    rest = a.shape[2:]
    return a.reshape((hc, 8, wc, 8) + rest).swapaxes(1, 2).reshape((hc, wc, 64) + rest)


# ------------------------------------------------------------------ level
def convert_level(args):
    """Everything of one level that does not depend on the other levels."""
    res_path, lgr_path, li = args
    t0 = time.time()
    res = elmadata.Resource(res_path)
    lev = elmadata.internal_levels(res)[li]
    lgr = Lgr(lgr_path)
    tex = mapmodel.Textures(lgr)
    pl = mapmodel.PcLevel(lev, tex)
    w, h = pl.size
    wc, hc = w // 8, h // 8
    sky, fold, texs, other, orgb, front = mapmodel.level_classes(pl)
    opq = sky < 0.5
    opa = np.maximum(1 - sky, 1e-6)

    # The second texture: the masked one with the most pixels, if its
    # pieces are all behind the bike.
    t2 = None
    back = {}
    for p in lev.pictures:
        if not p.name and p.texture:
            back[p.texture] = back.get(p.texture, True) and p.distance >= mapmodel.FRONT
    order = sorted(range(len(texs)), key=lambda n: -float(texs[n].sum()))
    for n in order:
        if back.get(tex.texnames[n]) and texs[n].sum() > 64 * 16:
            t2 = n
            break
    sx, sy = lev.start()
    ax, ay = levgeom.to_px(lev, sx, sy)
    anchor = (int(ax), int(ay))

    # Patterns at the most precise first; refined below for the VRAM.
    def pattern(name, max_tiles):
        im = lgr[name].image
        pxn, kx, pyn, ky = choose_pattern(im.width, im.height, max_tiles)
        return (pxn, kx, pyn, ky), mapmodel.texture_pattern(pl, name, pxn, pyn, kx, ky, anchor)

    # Pixel classes: -1 air, 0 foreground, 1 second texture, 2 other. The
    # pattern only changes colors, not the classes, so a rough pattern is
    # enough for them (the classes compare with the texture's own colors).
    def classify(pat_fg, pat_t2):
        reps_fg = (-(-h // pat_fg.shape[0]), -(-w // pat_fg.shape[1]))
        tf = np.tile(pat_fg, (reps_fg[0], reps_fg[1], 1))[:h, :w]
        mix = fold[..., None] * tf + other[..., None] * orgb
        tt = None
        if t2 is not None:
            reps = (-(-h // pat_t2.shape[0]), -(-w // pat_t2.shape[1]))
            tt = np.tile(pat_t2, (reps[0], reps[1], 1))[:h, :w]
            mix = mix + texs[t2][..., None] * tt
        for n in range(len(texs)):
            if n != t2:
                # Other masked textures are colors like the pictures; their
                # average is their texture's (it is anchored like ground).
                pass
        cls = np.full((h, w), 2, dtype=np.int8)
        tot = fold + other + (texs[t2] if t2 is not None else 0)
        rest = 1 - sky - tot
        if rest.max() > 1e-4:
            # Masked textures that are not the second texture: their pixels
            # are averaged at their own texture's colors.
            for n in range(len(texs)):
                if n == t2:
                    continue
                m = texs[n] > 0
                if not m.any():
                    continue
                pn = mapmodel.texture_pattern(pl, tex.texnames[n], 64, 64, 1, 1, anchor) \
                    if False else None
                # (exact colors of such textures come from the game's
                # pixels: level_classes counts them under texs[n] only)
                tcol = exact_tex_colors(pl, tex.texnames[n])
                mix = mix + texs[n][..., None] * tcol
        mix = mix / opa[..., None]
        purefg = (fold / opa >= 0.5) & (np.abs(mix - tf).max(axis=2) <= PURE_DIFF)
        cls[purefg] = 0
        if tt is not None:
            pure2 = (texs[t2] / opa >= 0.5) & (np.abs(mix - tt).max(axis=2) <= PURE_DIFF)
            cls[pure2 & ~purefg] = 1
        cls[~opq] = -1
        return cls, mix

    pat2 = None
    pk2 = None
    if t2 is not None:
        pk2, pat2 = pattern(tex.texnames[t2], TEX2_MAX_TILES)
    pk1, pat1 = pattern(pl.fg, TEX_MAX_TILES)
    cls, _ = classify(pat1, pat2)
    cc = cells_of(cls, hc, wc)
    fr = cells_of(front, hc, wc)
    has_air = (cc < 0).any(axis=2)
    allair = (cc < 0).all(axis=2)
    has0 = (cc == 0).any(axis=2)
    has1 = (cc == 1).any(axis=2)
    has2 = (cc == 2).any(axis=2)
    frontc = (fr >= 0.5).any(axis=2)
    cplx = has2 | (has0 & has1) | frontc
    kind = np.zeros((hc, wc), dtype=np.int8)           # 0 air
    kind[~cplx & has0 & ~has_air] = 1                    # fg interior
    kind[~cplx & has0 & has_air] = 2                     # fg edge
    kind[~cplx & has1 & ~has_air] = 3                    # tex2 interior
    kind[~cplx & has1 & has_air] = 4                     # tex2 edge
    kind[cplx & ~allair] = 5                             # complex
    special = (kind == 2) | (kind == 4) | (kind == 5)
    worst = window_max(special, FILL_W, FILL_H)
    budget = BG1_TILES - 1 - worst - CACHE_SLACK
    n2 = (pk2[0] // 8) * (pk2[2] // 8) if pk2 else 0
    if budget - n2 < 16:
        raise RuntimeError('%s: %d special cells in a window, no room for textures' % (lev.name, worst))
    # Video Detail Low: the ground of the polygons only, air, the
    # foreground texture and its edges (the same texture tiles, without
    # the second texture's).
    sky_l = mapmodel.level_classes(mapmodel.PcLevel(lev, tex, detail=False))[0]
    cl = cells_of(sky_l < 0.5, hc, wc)
    kind_l = np.where(cl.all(axis=2), 1, np.where(cl.any(axis=2), 2, 0)).astype(np.int8)
    worst_l = window_max(kind_l == 2, FILL_W, FILL_H)
    budget_l = BG1_TILES - 1 - worst_l - CACHE_SLACK
    if budget_l < 16:
        raise RuntimeError('%s: %d edges in a window, no room for the texture' % (lev.name, worst_l))
    pk1, pat1 = pattern(pl.fg, min(TEX_MAX_TILES, budget - n2, budget_l))
    cls, mix = classify(pat1, pat2)

    # Palette 3 (and 4) and the texture tiles:
    def tex_tiles(pat, seed):
        ntx, nty = pat.shape[1] // 8, pat.shape[0] // 8
        tt = cells_of(pat, nty, ntx).reshape(-1, 64, 3)
        pal, _, idx = tileq.quantize_tiles(tt, None, 1, 15, seed=seed)
        return ntx, nty, pal[0], idx
    ntx, nty, tpal, tidx = tex_tiles(pat1, li + 1)
    tq1 = tpal[tidx - 1]                         # tiles x 64 x 3, as shown
    ntx2 = nty2 = 0
    tq2 = None
    tpal2 = np.zeros((15, 3))
    tidx2 = np.zeros((0, 64), dtype=np.int64)
    if pat2 is not None:
        ntx2, nty2, tpal2, tidx2 = tex_tiles(pat2, li + 101)
        tq2 = tpal2[tidx2 - 1]

    # Complex cells: their colors, over the textures as shown.
    cy_, cx_ = np.nonzero(kind == 5)
    cm = cells_of(mix, hc, wc)[cy_, cx_]                 # n x 64 x 3
    ccls = cc[cy_, cx_]
    t1idx = (cy_ % nty) * ntx + (cx_ % ntx)
    cm = np.where((ccls == 0)[..., None], tq1[t1idx], cm)
    if tq2 is not None:
        t2idx = (cy_ % nty2) * ntx2 + (cx_ % ntx2)
        cm = np.where((ccls == 1)[..., None], tq2[t2idx], cm)
    cop = ccls >= 0
    npal = 3 if t2 is not None else 4
    # The texture colors the complex tiles use most go into every palette,
    # so that ground in them matches the ground around them.
    fixed = None
    if len(cy_):
        pc = cm[(ccls == 0) | (ccls == 1)]
        if len(pc):
            cols, cnt = np.unique(np.round(pc).astype(np.int64), axis=0, return_counts=True)
            fixed = cols[np.argsort(-cnt)[:5]].astype(np.float64)
    cpal, ctp, cidx = tileq.quantize_tiles(cm, cop, npal, 15, seed=li + 7, fixed=fixed)
    cpal_base = PAL_CPLX + (1 if t2 is not None else 0)
    prio = (cells_of(front, hc, wc)[cy_, cx_] >= 0.5).sum(axis=1) * 2 >= np.maximum(cop.sum(axis=1), 1)
    # A complex cell that came out as its texture after all is one:
    for n in range(len(cy_)):
        if prio[n] or not ((ccls[n] == 0) | (ccls[n] < 0)).all():
            continue
        o = cop[n]
        got = cpal[ctp[n]][cidx[n][o] - 1]
        if np.abs(got - tq1[t1idx[n]][o]).max() < 1:
            kind[cy_[n], cx_[n]] = 1 if o.all() else 2
    keep = kind[cy_, cx_] == 5
    cy_, cx_, ctp, cidx, prio = cy_[keep], cx_[keep], ctp[keep], cidx[keep], prio[keep]

    # Edge masks (the full mask is mask 0 of the global table):
    masks = []
    epos = []
    for k_, t_ in ((2, 0), (4, 1), (3, 1)):
        ey, ex = np.nonzero(kind == k_)
        if k_ == 3:
            bits = np.full((len(ey), 8), 255, dtype=np.uint8)
        else:
            bits = np.packbits((cc[ey, ex] >= 0).reshape(-1, 8, 8), axis=2).reshape(-1, 8)
        for n in range(len(ey)):
            masks.append(bytes(np.repeat(bits[n], 2)))
            epos.append((int(ey[n]), int(ex[n]), t_))

    # Complex tiles, the same ones once, and the ones that look almost the
    # same (with the same transparent pixels) once too:
    rep = merge_tiles(cpal, ctp, cidx)
    enc = tileq.encode4_many(cidx)
    tiles = {}
    tlist = []
    centries = []
    for n in range(len(cy_)):
        r = rep[n]
        key = bytes(enc[r])
        if key not in tiles:
            tiles[key] = len(tlist)
            tlist.append(key)
        centries.append(0x8000 | (int(prio[n]) << 14) |
                        ((cpal_base + int(ctp[r]) - PAL_CPLX) << 12) | tiles[key])
    if len(tlist) > 4096:
        raise RuntimeError('%s: %d complex tiles' % (lev.name, len(tlist)))

    ly, lx = np.nonzero(kind_l == 2)
    lbits = np.packbits(cl[ly, lx].reshape(-1, 8, 8), axis=2).reshape(-1, 8)
    low = {'kind': kind_l, 'nop': cl.sum(axis=2), 'worst': worst_l,
           'edge_pos': [(int(ly[n]), int(lx[n]), 0) for n in range(len(ly))],
           'edge_masks': [bytes(np.repeat(b, 2)) for b in lbits]}

    pal = np.zeros((5, 16, 3))
    pal[0, 1:] = tpal
    pal[1, 1:] = tpal2
    pal[cpal_base - PAL_TEX:cpal_base - PAL_TEX + npal, 1:] = cpal
    nop = cells_of(opq, hc, wc).sum(axis=2)
    return {
        'index': li, 'name': lev.name, 'fg': pl.fg, 'bg': pl.bg,
        'tex2': tex.texnames[t2] if t2 is not None else '',
        'size': (w, h), 'cells': (wc, hc), 'cx': pl.cx, 'cy': pl.cy,
        'kind': kind, 'nop': nop,
        'edge_pos': epos, 'edge_masks': masks,
        'cplx_pos': (cy_, cx_), 'cplx_entries': centries,
        'tiles': b''.join(tlist),
        'tex': (ntx, nty), 'tex2_size': (ntx2, nty2),
        'tex_tiles': tileq.encode4_many(tidx).tobytes() + tileq.encode4_many(tidx2).tobytes(),
        'palette': pal.reshape(-1, 3), 'anchor': anchor,
        'pattern': pk1, 'pattern2': pk2, 'worst': worst,
        'pictures': len(lev.pictures), 'low': low,
        'time': time.time() - t0,
    }


def merge_tiles(pal, tp, idx, mean_diff=MERGE_MEAN, max_diff=MERGE_MAX):
    """For every tile the tile shown in its place: itself, or an earlier
    one with the same transparent pixels whose colors differ at most
    mean_diff on average and max_diff anywhere (largest of the channels,
    0-255)."""
    n = len(idx)
    rep = np.arange(n)
    if n == 0 or mean_diff <= 0:
        return rep
    shown = np.zeros((n, 64, 3))
    for p in range(len(pal)):
        m = tp == p
        shown[m] = pal[p][np.maximum(idx[m] - 1, 0)]
    opq = idx > 0
    shown[~opq] = 0
    groups = {}
    for i in range(n):
        groups.setdefault(np.packbits(opq[i]).tobytes(), []).append(i)
    for members in groups.values():
        if len(members) < 2:
            continue
        mem = np.array(members)
        flat = shown[mem].reshape(len(mem), -1)
        kept = []
        for j, i in enumerate(mem):
            if kept:
                k = np.array(kept)
                d = np.abs(flat[k] - flat[j]).reshape(len(k), 64, 3).max(axis=2)
                ok = (d.mean(axis=1) <= mean_diff) & (d.max(axis=1) <= max_diff)
                if ok.any():
                    best = k[np.argmin(np.where(ok, d.mean(axis=1), np.inf))]
                    rep[i] = mem[best]
                    continue
            kept.append(j)
    return rep


_exact_cache = {}


def exact_tex_colors(pl, name):
    """Average color of a texture (for masked textures that are not the
    second texture of a level: their pixels count as pictures)."""
    if name not in _exact_cache:
        _exact_cache[name] = pl.tex.pal[pl.tex.texture(name)].reshape(-1, 3).mean(axis=0)
    return _exact_cache[name]


# ------------------------------------------------------------------ sky
def convert_sky(lgr, name, seed=1, npal=2):
    """BG2 for a background texture: its pattern of columns (P/8 x 28
    tiles), the tiles (at most 512, similar ones merged), npal palettes."""
    tex = mapmodel.Textures(lgr)
    t = tex.pal[tex.texture(name)]                  # rows from the bottom
    th, tw = t.shape[:2]
    # BG2 is 256 pixels wide, so the pattern's width must divide 256 (and
    # 28 rows of its columns fit into the 512 tiles, or merge well):
    cands = []
    for p in (32, 64, 128, 256):
        k = max(1, int(round(p / (tw * 0.4))))
        cands.append((p, k, abs(p / (tw * 0.4 * k) - 1)))
    p, k, _ = min(cands, key=lambda c: (round(c[2], 3), c[0]))
    s = k * tw / float(p)
    # Columns: the pattern's pixel i covers texture columns [i s, (i+1) s).
    i = np.arange(p)
    a = mapmodel._avg_periodic(np.transpose(t, (1, 0, 2)), i * s, (i + 1) * s)  # p x th x 3
    a = np.transpose(a, (1, 0, 2))                 # th x p x 3
    # Rows: screen row y (from the top of 224) covers rows from the bottom
    # [2.5 (223 - y), 2.5 (224 - y)) of the picture; the texture repeats
    # (lower than 480) or continues mirrored above (egkepsor):
    hgt = BG_ROWS * 8
    rmap = mapmodel.sky_row_map(int(2.5 * hgt) + 2, th)
    rows = np.zeros((hgt, p, 3))
    for y in range(hgt):
        lo, hi = 2.5 * (hgt - 1 - y), 2.5 * (hgt - y)
        acc = np.zeros((p, 3))
        r = lo
        while r < hi - 1e-9:
            nxt = min(hi, np.floor(r) + 1)
            acc += a[rmap[int(np.floor(r))]] * (nxt - r)
            r = nxt
        rows[y] = acc / (hi - lo)
    ncol = p // 8
    tiles = cells_of(rows, BG_ROWS, ncol).reshape(-1, 64, 3)
    pals, tp, idx = tileq.quantize_tiles(tiles, None, npal, 15, seed=seed)
    enc = tileq.encode4_many(idx)
    # The same tile (also flipped vertically) once:
    flip = tileq.encode4_many(idx.reshape(-1, 8, 8)[:, ::-1].reshape(-1, 64))
    uniq = {}
    ref = np.zeros(len(tiles), dtype=np.int64)
    vfl = np.zeros(len(tiles), dtype=np.int64)
    order = []
    for n in range(len(tiles)):
        a1 = (bytes(enc[n]), int(tp[n]))
        a2 = (bytes(flip[n]), int(tp[n]))
        if a1 in uniq:
            ref[n] = uniq[a1]
        elif a2 in uniq:
            ref[n] = uniq[a2]
            vfl[n] = 1
        else:
            uniq[a1] = len(order)
            ref[n] = len(order)
            order.append(n)
    # Too many: merge the most similar tiles (of the colors they show).
    shown = np.array([pals[tp[n]][idx[n] - 1] for n in order])   # u x 64 x 3
    use = np.bincount(ref, minlength=len(order)).astype(np.float64)
    rep = list(range(len(order)))
    alive = list(range(len(order)))
    if len(order) > 512:
        flat = shown.reshape(len(order), -1)
        sq = (flat ** 2).sum(axis=1)
        dist = sq[:, None] + sq[None, :] - 2 * flat @ flat.T
        np.fill_diagonal(dist, np.inf)
        alive_m = np.ones(len(order), dtype=bool)
        cost = dist * np.minimum(use[:, None], use[None, :])
        while alive_m.sum() > 512:
            ij = int(np.argmin(cost))
            a_, b_ = divmod(ij, len(order))
            keep_, drop = (a_, b_) if use[a_] >= use[b_] else (b_, a_)
            alive_m[drop] = False
            rep[drop] = keep_
            use[keep_] += use[drop]
            cost[drop, :] = np.inf
            cost[:, drop] = np.inf
            row = dist[keep_] * np.minimum(use[keep_], use)
            row[~alive_m] = np.inf
            row[keep_] = np.inf
            cost[keep_, :] = row
            cost[:, keep_] = row
        alive = [n for n in range(len(order)) if alive_m[n]]

    def root(n):
        while rep[n] != n:
            n = rep[n]
        return n
    newid = {n: j for j, n in enumerate(alive)}
    tiles_out = b''.join(bytes(enc[order[n]]) for n in alive)
    cols = []
    for c in range(ncol):
        for r in range(BG_ROWS):
            n = r * ncol + c
            u = root(ref[n])
            e = newid[u] | ((PAL_SKY + int(tp[order[u]])) << 10) | (int(vfl[n]) << 15)
            cols.append(e)
    pal = np.zeros((npal, 16, 3))
    pal[:, 1:] = pals
    return {
        'name': name, 'period': p, 'ncol': ncol, 'k': k, 'texw': tw,
        'tiles': tiles_out, 'ntiles': len(alive),
        'cols': struct.pack('<%dH' % len(cols), *cols),
        'palette': pal.reshape(-1, 3), 'image': rows,
    }


def sky_k(lv, sk):
    """The BG2 scroll is (cam_x + skyk) >> 1: half the speed, at the place of
    the game's sky (exact for a pattern of 0.4 times the texture)."""
    k = int(round(lv['cx'] * sk['period'] / float(sk['k'] * sk['texw'])))
    return k % 512


# ------------------------------------------------------------------ output
def chunk_records(kind, nop, edge_pos, mask_ids, cplx_pos=None, cplx_entries=None):
    """The chunks of a level, row by row: 0 all air, 1 all foreground
    texture, else the bytes of a mixed chunk. Returns cw, ch, the list."""
    hc, wc = kind.shape
    cw, ch = -(-wc // CHUNK), -(-hc // CHUNK)
    k = np.ones((ch * CHUNK, cw * CHUNK), dtype=np.int64)    # outside: ground
    k[:hc, :wc] = kind
    val = np.zeros(k.shape, dtype=np.int64)
    nn_ = np.full(k.shape, 64, dtype=np.int64)
    nn_[:hc, :wc] = nop
    for n, (y, x, t) in enumerate(edge_pos):
        val[y, x] = (t << 14) | mask_ids[n]
    if cplx_pos is not None:
        cy_, cx_ = cplx_pos
        for n in range(len(cy_)):
            val[cy_[n], cx_[n]] = cplx_entries[n]
    recs = []
    for cy in range(ch):
        for cx in range(cw):
            kk = k[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8]
            vv = val[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8]
            nn = nn_[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8]
            if (kk == 0).all():
                recs.append(0)
                continue
            if (kk == 1).all():
                recs.append(1)
                continue
            spec = kk >= 2
            sb = np.packbits(spec, axis=1).reshape(8)
            gb = np.packbits((kk == 1) | (spec & (nn >= 32)), axis=1).reshape(8)
            pre = np.concatenate([[0], np.cumsum(spec.sum(axis=1))[:-1]]).astype(np.uint8)
            rec = bytes(sb) + bytes(gb) + bytes(pre)
            for v in vv[spec].tolist():
                rec += struct.pack('<H', v)
            recs.append(rec)
    return cw, ch, recs


def chunk_data(lv):
    """The chunk directory of a level, its mixed chunks, and the part of
    Video Detail Low: a directory word of 2..$7FFF is a pair of words in
    the low part (2 + its offset), the chunk with High and with Low
    detail. The low part holds the pairs, then the mixed chunks of Low
    that High does not have; a word of 2..$7FFF in a pair is one of these
    (2 + its offset)."""
    cw, ch, hrecs = chunk_records(lv['kind'], lv['nop'], lv['edge_pos'], lv['mask_ids'],
                                  lv['cplx_pos'], lv['cplx_entries'])
    lo = lv['low']
    _, _, lrecs = chunk_records(lo['kind'], lo['nop'], lo['edge_pos'], lo['mask_ids'])
    data = bytearray()
    seen = {}
    hval = []
    for r in hrecs:
        if isinstance(r, int):
            hval.append(r)
            continue
        if r not in seen:
            seen[r] = 0x8000 + len(data)
            data += r
        hval.append(seen[r])
    # The chunks of Low that High has not got, and the pairs:
    lnew = {}
    pairs = {}
    lkey = []
    for n, r in enumerate(lrecs):
        if r == hrecs[n]:
            lkey.append(None)
            continue
        if isinstance(r, int):
            k = ('v', r)
        elif r in seen:
            k = ('v', seen[r])
        else:
            lnew.setdefault(r, len(lnew))
            k = ('n', lnew[r])
        lkey.append(k)
        pairs.setdefault((hval[n], k), len(pairs))
    lrecs_off = {}
    off = 4 * len(pairs)
    for r in sorted(lnew, key=lnew.get):
        lrecs_off[lnew[r]] = off
        off += len(r)
    low = bytearray()

    def lowword(k):
        return k[1] if k[0] == 'v' else 2 + lrecs_off[k[1]]
    for (hv, k) in sorted(pairs, key=pairs.get):
        low += struct.pack('<HH', hv, lowword(k))
    for r in sorted(lnew, key=lnew.get):
        low += r
    dirv = []
    for n in range(len(hrecs)):
        if lkey[n] is None:
            dirv.append(hval[n])
        else:
            dirv.append(2 + 4 * pairs[(hval[n], lkey[n])])
    if len(data) > 0x8000:
        raise RuntimeError('%s: chunk data of %d bytes' % (lv['name'], len(data)))
    if len(low) > 0x7FFD:
        raise RuntimeError('%s: low chunk data of %d bytes' % (lv['name'], len(low)))
    # (map.asm: with Low detail $FFFF is the end of the words of High chunks)
    assert 0xFFFF not in hval and len(pairs) * 4 + sum(map(len, lnew)) == len(low)
    return cw, ch, struct.pack('<%dH' % len(dirv), *dirv), bytes(data), bytes(low), len(pairs)


def write_bin(out, name, data):
    path = os.path.join(out, 'map', name)
    with open(path, 'wb') as f:
        f.write(data)
    return os.path.join(out, 'map', name)


def section(lines, name, label, path, size):
    lines += ['.SECTION "%s" SUPERFREE' % name, '%s:' % label,
              '\t.INCBIN "%s"' % path, '.ENDS', '']
    assert size <= 0x8000, name


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('res')
    ap.add_argument('lgr')
    ap.add_argument('out')
    ap.add_argument('-j', '--jobs', type=int, default=4)
    ap.add_argument('--levels', help='only these levels (comma separated, for tests)')
    a = ap.parse_args()
    t0 = time.time()
    res = elmadata.Resource(a.res)
    n = len(elmadata.internal_levels(res))
    sel = list(range(n))
    if a.levels:
        sel = [int(x) for x in a.levels.split(',')]
    lgr = Lgr(a.lgr)
    os.makedirs(os.path.join(a.out, 'map'), exist_ok=True)
    jobs = [(a.res, a.lgr, i) for i in sel]
    if a.jobs > 1:
        with Pool(a.jobs) as pool:
            lvs = pool.map(convert_level, jobs, chunksize=1)
    else:
        lvs = [convert_level(j) for j in jobs]
    lvs.sort(key=lambda lv: lv['index'])

    # Skies:
    skynames = []
    for lv in lvs:
        if lv['bg'] not in skynames:
            skynames.append(lv['bg'])
    skies = [convert_sky(lgr, s, seed=3 + i) for i, s in enumerate(skynames)]

    # Masks of all levels, the full mask first:
    full = bytes([255] * 16)
    masks = {full: 0}
    mask_list = [full]
    for lv in lvs:
        ids = []
        for m in lv['edge_masks']:
            if m not in masks:
                masks[m] = len(mask_list)
                mask_list.append(m)
            ids.append(masks[m])
        lv['mask_ids'] = ids
    nmask_high = len(mask_list)
    for lv in lvs:
        ids = []
        for m in lv['low']['edge_masks']:
            if m not in masks:
                masks[m] = len(mask_list)
                mask_list.append(m)
            ids.append(masks[m])
        lv['low']['mask_ids'] = ids
    if len(mask_list) > 0x4000:
        raise RuntimeError('too many masks: %d' % len(mask_list))
    # Complex tiles of all levels:
    tbase = 0
    for lv in lvs:
        lv['tbase'] = tbase
        tbase += len(lv['tiles']) // 32

    asm = ['; Generated by tools/gen_map.py from %s and %s.' % (
        os.path.basename(a.res), os.path.basename(a.lgr)),
        '.include "hdr.asm"', '']
    sizes = {}

    def add(kind, nbytes):
        sizes[kind] = sizes.get(kind, 0) + nbytes

    # Masks, 2048 a bank:
    mblob = b''.join(mask_list)
    nmb = -(-len(mask_list) // MASKS_PER_BANK)
    for b in range(nmb):
        part = mblob[b * MASKS_PER_BANK * 16:(b + 1) * MASKS_PER_BANK * 16]
        section(asm, '.map_masks_%d' % b, 'map_masks_%d' % b,
                write_bin(a.out, 'masks_%d.bin' % b, part), len(part))
        add('masks', len(part))
    asm += ['.SECTION ".map_mask_tab" SUPERFREE', 'map_mask_bank:']
    asm += ['\t.db :map_masks_%d' % b for b in range(nmb)]
    asm += ['map_mask_base:'] + ['\t.dw map_masks_%d' % b for b in range(nmb)]
    asm += ['.ENDS', '']
    # Complex tiles, 1024 a bank:
    tblob = b''.join(lv['tiles'] for lv in lvs) or bytes(32)
    ntb = -(-len(tblob) // (TILES_PER_BANK * 32))
    for b in range(ntb):
        part = tblob[b * TILES_PER_BANK * 32:(b + 1) * TILES_PER_BANK * 32]
        section(asm, '.map_tiles_%d' % b, 'map_tiles_%d' % b,
                write_bin(a.out, 'tiles_%d.bin' % b, part), len(part))
        add('tiles', len(part))
    asm += ['.SECTION ".map_tile_tab" SUPERFREE', 'map_tile_bank:']
    asm += ['\t.db :map_tiles_%d' % b for b in range(ntb)]
    asm += ['map_tile_base:'] + ['\t.dw map_tiles_%d' % b for b in range(ntb)]
    asm += ['.ENDS', '']

    # Skies:
    for s, sk in enumerate(skies):
        section(asm, '.map_sky_tiles_%d' % s, 'map_sky_tiles_%d' % s,
                write_bin(a.out, 'sky_tiles_%d.bin' % s, sk['tiles']), len(sk['tiles']))
        other = sk['cols'] + tileq.bgr555(sk['palette'])
        section(asm, '.map_sky_%d' % s, 'map_sky_cols_%d' % s,
                write_bin(a.out, 'sky_%d.bin' % s, other), len(other))
        add('sky', len(sk['tiles']) + len(other))
    asm += ['.SECTION ".map_sky_info" SUPERFREE', 'map_sky_info:']
    for s, sk in enumerate(skies):
        asm += ['\t.dl map_sky_tiles_%d' % s,
                '\t.dw %d' % (sk['ntiles'] * 32),
                '\t.dl map_sky_cols_%d' % s,
                '\t.dl map_sky_cols_%d + %d' % (s, len(sk['cols'])),
                '\t.db %d, 1' % sk['ncol'],
                '\t.db 0, 0, 0']
    asm += ['.ENDS', '']

    # Levels:
    info = ['.SECTION ".map_level_info" SUPERFREE', 'map_level_info:']
    linfo = ['.SECTION ".map_level_low" SUPERFREE', 'map_level_low:']
    report = []
    man = {'masks': len(mask_list), 'mask_banks': nmb, 'tile_banks': ntb,
           'skies': [{'name': sk['name'], 'period': sk['period'], 'ncol': sk['ncol'],
                      'ntiles': sk['ntiles']} for sk in skies],
           'levels': {}}
    for lv in lvs:
        i = lv['index']
        cw, ch, dirb, data, low, npairs = chunk_data(lv)
        lv['chunk_bytes'] = len(dirb) + len(data)
        lv['low_bytes'] = len(low)
        section(asm, '.map_dir_%d' % i, 'map_dir_%d' % i,
                write_bin(a.out, 'dir_%d.bin' % i, dirb), len(dirb))
        section(asm, '.map_chunks_%d' % i, 'map_chunks_%d' % i,
                write_bin(a.out, 'chunks_%d.bin' % i, data or b'\0'), len(data) or 1)
        if low:
            section(asm, '.map_chunksl_%d' % i, 'map_chunksl_%d' % i,
                    write_bin(a.out, 'chunksl_%d.bin' % i, low), len(low))
            linfo.append('\t.dl map_chunksl_%d\n\t.db 0' % i)
        else:
            linfo.append('\t.dl 0\n\t.db 0')
        add('low', len(low))
        other = lv['tex_tiles'] + tileq.bgr555(lv['palette'])
        section(asm, '.map_tex_%d' % i, 'map_tex_%d' % i,
                write_bin(a.out, 'tex_%d.bin' % i, other), len(other))
        add('chunks', len(dirb) + len(data))
        add('textures', len(other))
        sk = skynames.index(lv['bg'])
        skyk = sky_k(lv, skies[sk])
        wc, hc = lv['cells']
        ntx, nty = lv['tex']
        ntx2, nty2 = lv['tex2_size']
        ntex = ntx * nty + ntx2 * nty2
        info += ['\t; %d %s' % (i + 1, lv['name']),
                 '\t.dw %d, %d, %d, %d' % (wc, hc, cw, ch),
                 '\t.dl map_dir_%d' % i,
                 '\t.db :map_chunks_%d' % i,
                 '\t.dl map_tex_%d' % i,
                 '\t.db %d, %d, %d, %d' % (ntx, nty, ntx2, nty2),
                 '\t.dl map_tex_%d + %d' % (i, len(lv['tex_tiles'])),
                 '\t.dw %d' % lv['tbase'],
                 '\t.db %d' % sk,
                 '\t.dw %d' % skyk,
                 '\t.dw %d' % ntex,
                 '\t.dw map_chunks_%d' % i,
                 '\t.db 0']
        man['levels'][str(i)] = {
            'name': lv['name'], 'cells': lv['cells'], 'tex': lv['tex'],
            'tex2': lv['tex2_size'], 'tbase': lv['tbase'], 'sky': sk, 'skyk': skyk,
            'anchor': lv['anchor'], 'fg': lv['fg'], 'bg': lv['bg'], 'tex2name': lv['tex2'],
            'low': len(low) > 0}
        ncpl = len(lv['cplx_entries'])
        report.append('%2d %-20s %-6s %-6s %-6s cells %4dx%-4d pics %3d edge %5d complex %5d '
                      'tiles %5d tex %3d+%-2d (%s) worst %3d data %6d B  %.1fs' % (
                          i + 1, lv['name'][:20], lv['fg'], lv['bg'], lv['tex2'] or '-', wc, hc,
                          lv['pictures'], len(lv['mask_ids']), ncpl, len(lv['tiles']) // 32,
                          ntx * nty, ntx2 * nty2, '%dx%d/%dx%d' % (lv['pattern'][0], lv['pattern'][2],
                                                                   lv['pattern'][1], lv['pattern'][3]),
                          lv['worst'], lv['chunk_bytes'] + len(lv['tiles']) + len(other), lv['time']))
        lo = lv['low']
        report.append('   Low: edge %5d worst %3d, pairs %4d, data %6d B' % (
            len(lo['mask_ids']), lo['worst'], npairs, len(low)))
    info += ['.ENDS', '']
    linfo += ['.ENDS', '']
    asm += info + linfo
    with open(os.path.join(a.out, 'map', 'manifest.json'), 'w') as f:
        json.dump(man, f, indent=1)
    total = sum(sizes.values())
    with open(os.path.join(a.out, 'map_data.asm'), 'w') as f:
        f.write('\n'.join(asm))
    hdr = ['// Generated by tools/gen_map.py.', '#ifndef MAP_DATA_H', '#define MAP_DATA_H',
           '#define MAP_MASKS %d' % len(mask_list),
           '#define MAP_TILES %d' % tbase,
           '#define MAP_SKIES %d' % len(skies),
           '#define MAP_ROM_BYTES %d' % total, '#endif', '']
    with open(os.path.join(a.out, 'map_data.h'), 'w') as f:
        f.write('\n'.join(hdr))
    with open(os.path.join(a.out, 'map_report.txt'), 'w') as f:
        f.write('\n'.join(report) + '\n')
        for k, v in sorted(sizes.items()):
            f.write('%-9s %8d\n' % (k, v))
        f.write('total     %8d (%d masks, %d of them only for Low; %d complex tiles; %s)\n' % (
            total, len(mask_list), len(mask_list) - nmask_high, tbase,
            ', '.join('%s %d tiles' % (s['name'], s['ntiles']) for s in skies)))
        f.write('time %.1fs\n' % (time.time() - t0))
    print('map: %d levels, %d bytes, %.1fs' % (len(lvs), total, time.time() - t0))


if __name__ == '__main__':
    main()
