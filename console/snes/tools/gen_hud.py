"""Generate compact outlined OBJ time digits and an LGR apple counter.

  gen_hud.py ELMA_RES ELMA_LGR OUT_DIR [--test]

No level raster maps are generated. --test adds existing fake-bike routes.
"""
import os
import sys
from pathlib import Path
import numpy as np
from PIL import Image
import elmadata
import levgeom
from lgr import Lgr

TIME_Y = 8
TIME_X = (8, 200)
DIGIT_X = (0, 7, 17, 24, 34, 41)
COLON_DX = 7
COLON_ROWS = (4, 9)
SEG_H, SEG_V = 3, 5
SLOT_COLON = 10
SLOT_TILES = [(i // 8) * 32 + (i % 8) * 2 for i in range(24)]
APPLE_X, APPLE_Y, COUNT_X = 8, 28, 28
C_DIGIT, C_OUTLINE = 1, 2
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


def ido2string(hs):
    """The time as the original shows it (BESTTIME.CPP), 59:59:99 at most."""
    if hs >= 360000:
        return '59:59:99'
    return '%02d:%02d:%02d' % (hs // 6000, hs // 100 % 60, hs % 100)



def bgr15(c):
    r, g, b = (int(v) >> 3 for v in c)
    return r | g << 5 | b << 10


def apple_image(lgr):
    """First frame of the original food1 animation, fitted to a 14px icon."""
    pic = lgr['qfood1'].image
    side = pic.height
    pic = pic.crop((0, 0, side, side))
    rgb = np.asarray(pic.convert('RGB'))
    mask = np.asarray(pic) != pic.getpixel((0, 0))
    rgba = np.dstack((rgb, mask.astype(np.uint8) * 255))
    im = Image.fromarray(rgba, 'RGBA').resize((14, 14), Image.Resampling.BOX)
    rgb = np.asarray(im.convert('RGB'))
    mask = np.asarray(im)[:, :, 3] >= 128
    # 13 apple colors plus transparent, white digits and dark outlines.
    # Quantize opaque pixels alone so transparency cannot consume a color.
    samples = Image.fromarray(rgb[mask].reshape(1, -1, 3), 'RGB')
    q = samples.quantize(colors=13, method=Image.Quantize.MEDIANCUT)
    pal = np.asarray(q.getpalette()[:39], np.uint8).reshape(-1, 3)
    pix = np.zeros((16, 16), np.uint8)
    body = np.zeros((14, 14), np.uint8)
    body[mask] = np.asarray(q).reshape(-1) + 3
    pix[1:15, 1:15] = body
    # Dark silhouette provides contrast over sky and textured ground.
    covered = pix != 0
    for y, x in zip(*np.nonzero(covered)):
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            if not covered[y + dy, x + dx]:
                pix[y + dy, x + dx] = C_OUTLINE
    return pix, [(0, 0, 0), (255, 255, 255), (8, 12, 20)] + list(map(tuple, pal))


def glyph_image(d, colon=False):
    pix = np.zeros((16, 16), np.uint8)
    points = [(x + 1, y + 1) for x, y in glyph(str(d))]
    if colon:
        points += [(COLON_DX + 1, y + 1) for y in COLON_ROWS]
    for x, y in points:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                pix[y + dy, x + dx] = C_OUTLINE
    for x, y in points:
        pix[y, x] = C_DIGIT
    return pix


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


def sprite_sheet(lgr):
    sheet = np.zeros((48, 128), np.uint8)
    for i in range(20):
        t = SLOT_TILES[i]
        y, x = (t // 16) * 8, (t % 16) * 8
        sheet[y:y + 16, x:x + 16] = glyph_image(i % 10, i >= 10)
    apple, pal = apple_image(lgr)
    t = SLOT_TILES[20]
    y, x = (t // 16) * 8, (t % 16) * 8
    sheet[y:y + 16, x:x + 16] = apple
    data = b''.join(tile4(sheet[y:y + 8, x:x + 8])
                    for y in range(0, 48, 8) for x in range(0, 128, 8))
    return data, pal


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


def main():
    res, lgr_path, out = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    data, pal = sprite_sheet(Lgr(lgr_path))
    inc = ['; Generated compact sprite HUD.',
           '.DEFINE HUD_SPRITE_BYTES %d' % len(data),
           '.DEFINE HUD_SLOT_COLON %d' % SLOT_COLON,
           '.DEFINE HUD_TIME_Y %d' % TIME_Y,
           '.DEFINE HUD_TIME_X0 %d' % TIME_X[0],
           '.DEFINE HUD_TIME_X1 %d' % TIME_X[1],
           '.DEFINE HUD_APPLE_X %d' % APPLE_X,
           '.DEFINE HUD_APPLE_Y %d' % APPLE_Y,
           '.DEFINE HUD_COUNT_X %d' % COUNT_X,
           '.DEFINE HUD_TILE_APPLE %d' % SLOT_TILES[20]]
    a = ['; Generated by tools/gen_hud.py.', '.include "hdr.asm"',
         '.SECTION ".hud_sprites" SUPERFREE', 'hud_sprite_tiles:']
    for i in range(0, len(data), 32):
        a.append('\t.db ' + ', '.join(str(b) for b in data[i:i + 32]))
    a += ['hud_slot_tiles:', '\t.db ' + ', '.join(map(str, SLOT_TILES)),
          'hud_obj_colors:', '\t.dw ' + ', '.join(str(bgr15(c)) for c in pal),
          'hud_bcd:']
    for i in range(0, 100, 20):
        a.append('\t.db ' + ', '.join(str((n // 10) << 4 | n % 10) for n in range(i, i + 20)))
    a.append('.ENDS')
    Path(out, 'hud.asm').write_text('\n'.join(a) + '\n')
    Path(out, 'hud.inc').write_text('\n'.join(inc) + '\n')
    sys.stderr.write('gen_hud: compact OBJ HUD, %d tile bytes; no minimap assets\n' % len(data))
    if '--test' in sys.argv[4:]:
        write_test(elmadata.internal_levels(elmadata.Resource(res)), out)


if __name__ == '__main__':
    main()
