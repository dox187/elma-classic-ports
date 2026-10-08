"""Reads an LGR file of Elasto Mania (LGR12 of the original game, LGR13 of
the Steam release, LGRFILE.CPP): its pictures as PIL images and the
pictures.lst information.

Every picture is a PCX of 8 bits with its own palette; the palette of the
game is that of q1bike.pcx.
"""

import io
import struct

from PIL import Image

# Types of pictures.lst (PICLIST.H):
PL_PICTURE, PL_TEXTURE, PL_MASK = 100, 101, 102


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
            self.pictures[name] = pic
            self.order.append(name)

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
