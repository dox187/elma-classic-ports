"""Reads an LGR file of Elasto Mania (LGR12 of the original game, LGR13 of
the Steam release, LGRFILE.CPP): its pictures as PIL images and the
pictures.lst information.

Every picture is a PCX of 8 bits with its own palette; the palette of the
game is that of q1bike.pcx. The bigger pictures of an LGR13 file are
resized to their size in the game, as the game does when it loads them, so
that the converters see the same sizes as from an LGR12 file.
"""

import io
import struct

import numpy as np
from PIL import Image

# Types of pictures.lst (PICLIST.H):
PL_PICTURE, PL_TEXTURE, PL_MASK = 100, 101, 102
# Transparency of pictures.lst: none, color 0, the color of a corner:
TR_NONE, TR_0, TR_TOPLEFT, TR_TOPRIGHT, TR_BOTTOMLEFT, TR_BOTTOMRIGHT = range(10, 16)
# Animations: square frames side by side (ANIM.CPP):
ANIMS = ('qexit', 'qkiller') + tuple('qfood%d' % i for i in range(1, 10))
# Textures not in pictures.lst:
TEXTURES = ('qgrass',)


def _transparent(image, code):
    """The transparent color index of a picture, None if it has none."""
    w, h = image.size
    if code == TR_NONE:
        return None
    if code == TR_0:
        return 0
    corner = {TR_TOPRIGHT: (w - 1, 0), TR_BOTTOMLEFT: (0, h - 1),
              TR_BOTTOMRIGHT: (w - 1, h - 1)}.get(code, (0, 0))
    return image.getpixel(corner)


def _resize(image, size, transparent):
    """A picture of mode P resized to size: the colors averaged over the
    pixels that are not transparent, mapped back to the picture's own
    palette; a pixel stays transparent where most of its area was."""
    pal = image.getpalette()[:768]
    pal += [0] * (768 - len(pal))
    idx = np.asarray(image)
    rgb = np.asarray(image.convert('RGB')).astype(np.float32)
    if transparent is None:
        opaque = np.ones(idx.shape, np.float32)
    else:
        opaque = (idx != transparent).astype(np.float32)
    channels = []
    for c in range(3):
        ch = Image.fromarray(rgb[:, :, c] * opaque, 'F').resize(size, Image.BOX)
        channels.append(np.asarray(ch))
    cover = np.asarray(Image.fromarray(opaque, 'F').resize(size, Image.BOX))
    avg = np.stack(channels, axis=2) / np.maximum(cover, 1e-6)[:, :, None]
    # Nearest color of the palette (without the transparent one):
    choices = [i for i in range(256) if i != transparent]
    palimg = Image.new('P', (1, 1))
    entries = [pal[3 * i:3 * i + 3] for i in choices]
    flat = sum(entries, []) + entries[0] * (256 - len(entries))
    palimg.putpalette(flat)
    q = Image.fromarray(np.clip(avg + 0.5, 0, 255).astype(np.uint8), 'RGB')
    q = np.asarray(q.quantize(palette=palimg, dither=Image.Dither.NONE))
    out = np.array(choices, np.uint8)[np.minimum(q, len(choices) - 1)]
    if transparent is not None:
        out[cover < 0.5] = transparent
    res = Image.fromarray(out, 'P')
    res.putpalette(pal)
    return res


class Picture:
    def __init__(self, name, image, target=None):
        self.name = name            # lower case, without .pcx
        self.image = image          # PIL image of mode P
        # The size in the game without zoom: its own in LGR12, the one
        # stored in LGR13 (whose pictures are bigger):
        self.target = target or image.size

    def palette(self):
        """The 256 colors (r, g, b) of the picture's own palette."""
        p = self.image.getpalette() or []
        p += [0] * (768 - len(p))
        return [tuple(p[i:i + 3]) for i in range(0, 768, 3)]


class Lgr:
    def __init__(self, path):
        with open(path, 'rb') as f:
            d = f.read()
        if d[:3] != b'LGR' or d[3:5] not in (b'12', b'13'):
            raise ValueError('%s is not an LGR12/LGR13 file' % path)
        self.lgr13 = d[3:5] == b'13'
        count = struct.unpack_from('<i', d, 5)[0]
        p = 9
        version, n = struct.unpack_from('<ii', d, p)
        if version != 1002:
            raise ValueError('pictures.lst of unknown version in %s' % path)
        p += 8
        self.list = {}  # name -> (type, distance, clipping, transparency)
        names = [d[p + i * 10:p + i * 10 + 10].split(b'\0')[0].decode('latin-1').lower()
                 for i in range(n)]
        p += 10 * n
        cols = []
        for _ in range(4):
            cols.append(struct.unpack_from('<%di' % n, d, p))
            p += 4 * n
        for i, name in enumerate(names):
            self.list[name] = tuple(c[i] for c in cols)
        self.pictures = {}
        self.order = []
        for _ in range(count):
            name = d[p:p + 20].split(b'\0')[0].decode('latin-1').lower()
            p += 20
            target = None
            if self.lgr13:
                target = struct.unpack_from('<hh', d, p)
                p += 4
            size = struct.unpack_from('<i', d, p)[0]
            p += 4
            image = Image.open(io.BytesIO(d[p:p + size]))
            image.load()
            p += size
            if name.endswith('.pcx'):
                name = name[:-4]
            pic = Picture(name, image, target if target and target[0] > 0 else None)
            if pic.target != image.size:
                pic.image = self._to_target(name, image, pic.target)
            self.pictures[name] = pic
            self.order.append(name)

    def _to_target(self, name, image, target):
        info = self.list.get(name)
        texture = name in TEXTURES or (info and info[0] == PL_TEXTURE)
        code = TR_NONE if texture else (info[3] if info else TR_TOPLEFT)
        transparent = _transparent(image, code)
        if name in ANIMS:
            # Frame by frame, so that no frame bleeds into the next:
            h = image.height
            n = image.width // h
            th = target[1]
            out = Image.new('P', (n * th, th))
            for f in range(n):
                frame = image.crop((f * h, 0, f * h + h, h))
                out.paste(_resize(frame, (th, th), transparent), (f * th, 0))
            out.putpalette(image.getpalette())
            return out
        return _resize(image, target, transparent)

    def __getitem__(self, name):
        return self.pictures[name.lower()]

    def __contains__(self, name):
        return name.lower() in self.pictures

    def palette(self):
        """The palette of the game: q1bike's."""
        return self['q1bike'].palette()


if __name__ == '__main__':
    import sys
    lgr = Lgr(sys.argv[1])
    for name in lgr.order:
        pic = lgr.pictures[name]
        info = lgr.list.get(name, '')
        print('%-10s %4dx%-4d %s' % (name, pic.image.width, pic.image.height, info))
