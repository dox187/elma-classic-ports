"""Original level/LGR -> a CGB tile-streaming experiment, never a tile collision map.

Reuse the existing PC raster reconstruction and LGR/level readers. Geometry is
exported independently, including ALL source edges, for the later physics port.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'console/snes/tools'))
import elmadata
import lgr as lgr_reader
import mapmodel
import bikemodel

PPM = 12
CHUNK_W, CHUNK_H = 32, 16
OMITTED_PICTURES = frozenset(('tree1', 'tree2', 'tree3', 'tree4', 'tree5', 'flag', 'barrel'))


def render_level_data(level):
    """Omit approved scenery only; keep the source data and terrain masks."""
    rendered = copy.copy(level)
    rendered.pictures = [pic for pic in level.pictures if pic.name not in OMITTED_PICTURES]
    return rendered


def rgb555(colors):
    a = np.asarray(colors, dtype=np.uint16) >> 3
    return (a[..., 0] | a[..., 1] << 5 | a[..., 2] << 10).ravel().tolist()


def tile2bpp(indices):
    """GBC row order: low plane then high plane, leftmost pixel in bit 7."""
    out = bytearray()
    for row in indices:
        out.extend(sum(((int(v) >> bit) & 1) << (7 - i) for i, v in enumerate(row))
                   for bit in (0, 1))
    return bytes(out)


def palettes_for(tiles, count=7, colors=4):
    # Cluster tile means, then quantize the source pixels of each cluster.
    means = tiles.mean(axis=1)
    centers = means[np.linspace(0, len(means) - 1, count, dtype=int)].copy()
    for _ in range(12):
        labels = ((means[:, None] - centers) ** 2).sum(axis=2).argmin(axis=1)
        for k in range(count):
            if np.any(labels == k):
                centers[k] = means[labels == k].mean(axis=0)
    palettes = []
    for k in range(count):
        pixels = tiles[labels == k].reshape(-1, 3)
        if not len(pixels):
            pixels = tiles[0]
        im = Image.fromarray(pixels.astype(np.uint8).reshape(-1, 1, 3))
        q = im.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
        pal = np.array(q.getpalette()[:colors * 3], dtype=np.uint8).reshape(colors, 3)
        # Evaluate in the actual hardware color space, not unrepresentable RGB.
        palettes.append((pal >> 3) * 8)
    return np.array(palettes)


def encode_scene(image):
    h, w, _ = image.shape
    tiles = image.reshape(h // 8, 8, w // 8, 8, 3).transpose(0, 2, 1, 3, 4)
    flat = tiles.reshape(-1, 64, 3).astype(np.int32)
    palettes = palettes_for(flat)
    choices, encoded, restored = [], [], []
    for tile in flat:
        d = ((tile[None, :, None] - palettes[:, None].astype(np.int32)) ** 2).sum(axis=3)
        pi = int(d.min(axis=2).sum(axis=1).argmin())
        indices = d[pi].argmin(axis=1).astype(np.uint8).reshape(8, 8)
        choices.append(pi)
        encoded.append(tile2bpp(indices))
        restored.append(palettes[pi][indices])
    preview = np.array(restored).reshape(h // 8, w // 8, 8, 8, 3)
    preview = preview.transpose(0, 2, 1, 3, 4).reshape(h, w, 3)
    return np.array(encoded, dtype='S16'), np.array(choices, dtype=np.uint8), palettes, preview


def array(name, data, ctype='uint8_t'):
    values = list(data)
    rows = [', '.join(str(v) for v in values[i:i + 24]) for i in range(0, len(values), 24)]
    return 'const %s %s[] = {\n%s\n};\n' % (ctype, name, ',\n'.join(rows))


def render_level(level, lgr):
    level = render_level_data(level)
    points = [p for _, poly in level.polygons for p in poly]
    ox = math.floor(min(x for x, y in points) - 4)
    oy = math.ceil(max(y for x, y in points) + 4)
    w = math.ceil((max(x for x, y in points) + 4 - ox) * PPM / 256) * 256
    h = math.ceil((oy - min(y for x, y in points) + 4) * PPM / 128) * 128
    pl = mapmodel.PcLevel(level, mapmodel.Textures(lgr))
    image = Image.new('RGB', (w * 4, h * 4))
    sky = pl.tex.texture(pl.bg)
    sky_rows = mapmodel.sky_row_map(h * 4, sky.shape[0])
    x = round((ox - pl.origo[0]) * 48)
    sky_columns = ((x // 2) + np.arange(w * 4)) % sky.shape[1]
    # Render in strips to bound temporary arrays. Sky is baked at this stage;
    # parallax and foreground occlusion are separate open rendering decisions.
    for top in range(0, h * 4, 128):
        rows = min(128, h * 4 - top)
        y = round((oy - pl.origo[1]) * 48) - top - rows
        _, distance, _, colors = pl.render(x, x+w*4, y, y+rows)
        sr = sky_rows[h*4-top-rows:h*4-top][::-1]
        idx = np.where(distance == mapmodel.D_EG, sky[sr][:,sky_columns], colors)
        image.paste(Image.fromarray(pl.tex.pal[idx].astype(np.uint8)), (0, top))
    # Objects use separate hardware sprites with protected semantic palettes.
    return np.array(image.resize((w, h), Image.Resampling.BOX)), ox, oy


def bike_data(lgr):
    st = bikemodel.State(body=(0, 0), wheel0=(-.85, -.6), wheel1=(.85, -.6), rider=(0, .44))
    pics = bikemodel.Pictures(lgr)
    idx = bikemodel.render_pc(pics, bikemodel.kibike(st), -16 / PPM, 16 / PPM, 128, 128)
    opaque = idx >= 0
    rgba = np.zeros((128, 128, 4), dtype=np.uint8)
    rgba[opaque, :3] = pics.pal[idx[opaque]]
    rgba[opaque, 3] = 255
    im = Image.fromarray(rgba).resize((32, 32), Image.Resampling.BOX)
    a = np.array(im)
    colors = a[a[:, :, 3] >= 128, :3]
    palette = palettes_for(colors.reshape(-1, 1, 3).astype(np.int32), 1, 3)[0]
    d = ((a[:, :, None, :3].astype(np.int32) - palette.astype(np.int32)) ** 2).sum(axis=3)
    q = (d.argmin(axis=2) + 1).astype(np.uint8)
    q[a[:, :, 3] < 128] = 0
    tiles = b''.join(tile2bpp(q[y:y + 8, x:x + 8]) for y in range(0, 32, 8) for x in range(0, 32, 8))
    im.save(OUT / 'bike-source.png')
    return tiles, rgb555(np.vstack(([0, 0, 0], palette)))


def object_data(lgr):
    """Keep the original outlines, with red apples and white flower petals.

    These palettes are a product requirement, never fitted to scenery pixels.
    Only the first frame is used in this viewer; animation is not implemented.
    """
    palettes = [[(0, 0, 0), (248, 0, 0), (0, 192, 0), (128, 0, 0)],
                [(0, 0, 0), (248, 248, 248), (248, 224, 0), (0, 160, 0)]]
    result = bytearray()
    for kind, name in enumerate(('qfood1', 'qexit')):
        pic = lgr[name].image
        frame = pic.crop((0, 0, pic.height, pic.height))
        alpha = (np.array(frame) != frame.getpixel((0, 0))).astype(np.uint8) * 255
        rgba = frame.convert('RGBA')
        rgba.putalpha(Image.fromarray(alpha))
        size = max(1, round(pic.height / 4))
        if size > 16:
            raise ValueError('Object frame exceeds the prototype sprite budget')
        im = Image.new('RGBA', (16, 16))
        im.paste(rgba.resize((size, size), Image.Resampling.BOX), ((16-size)//2, (16-size)//2))
        a = np.array(im)
        r, g, b = [a[:, :, i].astype(np.int32) for i in range(3)]
        if kind == 0:
            q = np.where((g > r) & (g > b), 2, np.where(r > 90, 1, 3))
        else:
            q = np.where((g > r * 1.2) & (g > b * 1.2), 3,
                         np.where((r > 80) & (g > 60) & (b < g * .7), 2, 1))
        q[a[:, :, 3] < 128] = 0
        result.extend(b''.join(tile2bpp(q[y:y+8, x:x+8]) for y in (0, 8) for x in (0, 8)))
        preview = np.array(palettes[kind], dtype=np.uint8)[q]
        Image.fromarray(preview).save(OUT / (name+'-gbc.png'))
    return result, rgb555(palettes)


def main():
    global OUT
    p = argparse.ArgumentParser()
    p.add_argument('--res', type=Path, required=True)
    p.add_argument('--lgr', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    OUT = a.out
    OUT.mkdir(parents=True, exist_ok=True)
    # Remove only generated bank sources when changing the selected data.
    for old in OUT.glob('world_*.c'):
        old.unlink()
    levels = elmadata.internal_levels(elmadata.Resource(a.res))
    lgr = lgr_reader.Lgr(a.lgr)
    image, ox, oy = render_level(levels[0], lgr)
    data, attrs, palettes, preview = encode_scene(image)
    Image.fromarray(image).save(OUT / 'scene-source.png')
    Image.fromarray(preview).save(OUT / 'scene-gbc.png')
    h, w, _ = image.shape
    tw, th = w // 8, h // 8
    raw = [bytes(x).ljust(16, b'\0') for x in data]
    # CGB tile flips allow lossless reuse of mirrored pixel patterns.
    reverse = bytes(int(f'{i:08b}'[::-1],2) for i in range(256))
    canonical, flips = [], []
    for tile in raw:
        vertical = b''.join(tile[i:i+2] for i in range(14,-1,-2))
        variants = (tile,tile.translate(reverse),vertical,vertical.translate(reverse))
        chosen = min(range(4),key=lambda i:variants[i])
        canonical.append(variants[chosen])
        flips.append((0,32,64,96)[chosen])
    raw = canonical
    unique = list(dict.fromkeys(raw))
    # 480 BG patterns leave bank 1 tiles 224..231 for status, 232.. for OBJ.
    # Do not silently degrade a level which needs a different streaming design.
    if len(unique) > 480:
        raise ValueError('Level exceeds the prototype 480-pattern VRAM budget: %d' % len(unique))
    pattern_ids = {pattern:i for i,pattern in enumerate(unique)}
    ids_all = [pattern_ids[tile] for tile in raw]
    (OUT/'patterns.c').write_text('#include <stdint.h>\n#pragma bank 1\n'
                                + array('world_patterns', b''.join(unique)))
    bank_meta, declarations = [], []
    for cy in range(th // CHUNK_H):
        for cx in range(tw // CHUNK_W):
            bank = len(bank_meta) + 2
            if bank > 255:
                raise ValueError('Prototype bank table exceeds the 8-bit bank range')
            ids = [(cy * CHUNK_H + y) * tw + cx * CHUNK_W + x
                   for y in range(CHUNK_H) for x in range(CHUNK_W)]
            name = 'world_%d' % bank
            blob = bytes(ids_all[i] & 255 for i in ids) + bytes(int(attrs[i]) | flips[i] | (8 if ids_all[i]>=256 else 0) for i in ids)
            assert len(blob) == 1024
            (OUT / (name + '.c')).write_text('#include <stdint.h>\n#pragma bank %d\n' % bank + array(name, blob))
            declarations.append('extern const uint8_t %s[];' % name)
            bank_meta.append('{ %d, %s }' % (bank, name))
    bike, bike_pal = bike_data(lgr)
    objects, object_pal = object_data(lgr)
    object_positions = [(round((x-ox)*PPM), round((oy-y)*PPM), kind,
                         round(x*65536), round(y*65536), gravity)
                        for kind, x, y, gravity, animation in levels[0].objects
                        if kind in (elmadata.T_APPLE, elmadata.T_FLOWER)]
    sx, sy = levels[0].start()
    bx, by = round((sx + .85 - ox) * PPM), round((oy - sy - .6) * PPM)
    header = ('#ifndef GBC_ASSETS_H\n#define GBC_ASSETS_H\n#include <stdint.h>\n'
              'typedef struct { uint8_t bank; const uint8_t *data; } world_chunk_t;\n'
              'extern const world_chunk_t world_chunks[];\n'
              'extern const uint16_t bg_palette[], bike_palette[];\n'
              'extern const uint8_t bike_tiles[];\n'
              'extern const uint8_t world_patterns[];\n'
              'typedef struct { uint16_t x, y; uint8_t kind; int32_t world_x, world_y; uint8_t gravity; } level_object_t;\n'
              'extern const level_object_t level_objects[];\n'
              'extern const uint16_t object_palette[];\n'
              'extern const uint8_t object_tiles[];\n'
              '#define WORLD_WIDTH %d\n#define WORLD_HEIGHT %d\n#define WORLD_CHUNKS_X %d\n'
              '#define BIKE_X %d\n#define BIKE_Y %d\n#define OBJECT_COUNT %d\n'
              '#define WORLD_PATTERN_COUNT %d\n'
              '#define WORLD_ORIGIN_X_FP (%dL)\n#define WORLD_ORIGIN_Y_FP (%dL)\n'
              '#define GAME_START_X_FP (%dL)\n#define GAME_START_Y_FP (%dL)\n'
              '#endif\n') % (w, h, tw // 32, bx, by, len(object_positions),len(unique),
                             ox*65536,oy*65536,round(sx*65536),round(sy*65536))
    (OUT / 'assets.h').write_text(header)
    (OUT / 'assets.c').write_text('#include "assets.h"\n' + '\n'.join(declarations) + '\n'
        + 'const world_chunk_t world_chunks[] = {\n' + ',\n'.join(bank_meta) + '\n};\n'
        + array('bg_palette', rgb555(palettes), 'uint16_t')
        + array('bike_palette', bike_pal, 'uint16_t') + array('bike_tiles', bike)
        + array('object_palette', object_pal, 'uint16_t') + array('object_tiles', objects)
        + 'const level_object_t level_objects[] = {\n'
        + ',\n'.join('{%d,%d,%d,%dL,%dL,%d}' % obj for obj in object_positions) + '\n};\n')
    geometry = [{'name': l.name, 'polygons': l.polygons, 'objects': l.objects,
                 'pictures': [vars(pic) for pic in l.pictures]} for l in levels]
    (OUT / 'levels.json').write_text(json.dumps(geometry, indent=2) + '\n')
    segments = [[int(round(v * 65536)) for v in (*poly[i], *poly[(i + 1) % len(poly)])]
                for grass, poly in levels[0].polygons if not grass for i in range(len(poly))]
    (OUT / 'collision.json').write_text(json.dumps({'units': 'Q16.16 meters, y up', 'segments': segments}, indent=2) + '\n')
    report = {'milestone': 'level viewer, not gameplay', 'level': levels[0].name,
              'source_levels_preserved': len(levels), 'ppm': PPM, 'origin_m': [ox, oy],
              'size_px': [w, h], 'banks': len(bank_meta), 'collision_segments': len(segments),
              'unique_patterns': len(unique), 'protected_object_colors': {'apple':'red','flower_petals':'white'},
              'objects': [{'x':x,'y':y,'kind':kind,'world_x_fp':wx,'world_y_fp':wy,'gravity':g}
                          for x,y,kind,wx,wy,g in object_positions],
              'omitted_render_pictures': sorted(OMITTED_PICTURES),
              'omitted_placements': sum(pic.name in OMITTED_PICTURES for pic in levels[0].pictures),
              'omitted_placements_all_levels': sum(pic.name in OMITTED_PICTURES for level in levels for pic in level.pictures),
              'source_sha256': {str(f.resolve()): hashlib.sha256(f.read_bytes()).hexdigest() for f in (a.res, a.lgr)}}
    (OUT / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Original data:', len(levels), 'levels;', levels[0].name, w, 'x', h, 'pixels;',len(bank_meta),'ROM data banks')


if __name__ == '__main__':
    main()
