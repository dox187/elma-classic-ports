"""The picture the level background of the SNES should show, decoded from
the converted data (build/gen/map/, tools/gen_map.py) independently of the
program, and the check of a VRAM dump of the program against it.

  map_ref.py GEN_DIR LEVEL CAM_X CAM_Y OUT.png      the expected screen
"""

import json
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import tileq  # noqa: E402

PAL_TEX = 3
PAL_CPLX = 4


def _words(b):
    return np.frombuffer(b, dtype='<u2')


def colors(b):
    """RGB 0-255 of BGR555 words."""
    w = _words(b).astype(np.int64)
    r, g, bl = w & 31, (w >> 5) & 31, (w >> 10) & 31
    return np.stack([r, g, bl], axis=1) * 255.0 / 31.0


def popcount(b):
    return bin(b & 0xFF).count('1')


class MapData:
    def __init__(self, gen):
        self.dir = os.path.join(gen, 'map')
        with open(os.path.join(self.dir, 'manifest.json')) as f:
            self.man = json.load(f)
        self.masks = b''.join(self._read('masks_%d.bin' % b) for b in range(self.man['mask_banks']))
        self.tiles = b''.join(self._read('tiles_%d.bin' % b) for b in range(self.man['tile_banks']))
        self._lev = {}

    def _read(self, name):
        with open(os.path.join(self.dir, name), 'rb') as f:
            return f.read()

    def level(self, li):
        if li in self._lev:
            return self._lev[li]
        m = self.man['levels'][str(li)]
        wc, hc = m['cells']
        ntx, nty = m['tex']
        ntx2, nty2 = m['tex2']
        n1, n2 = ntx * nty, ntx2 * nty2
        tex = self._read('tex_%d.bin' % li)
        lv = dict(m)
        lv['dirv'] = _words(self._read('dir_%d.bin' % li))
        lv['chunks'] = self._read('chunks_%d.bin' % li)
        lv['cw'] = -(-wc // 8)
        lv['tex_raw'] = tex[:(n1 + n2) * 32]
        lv['tex_tiles'] = [tileq.decode4(tex[i * 32:i * 32 + 32]) for i in range(n1 + n2)]
        lv['pal_bg1'] = colors(tex[(n1 + n2) * 32:(n1 + n2) * 32 + 160])   # palettes 3-7
        sk = self.man['skies'][m['sky']]
        sky = self._read('sky_%d.bin' % m['sky'])
        ncol = sk['ncol']
        lv['sky_cols'] = _words(sky[:ncol * 28 * 2]).reshape(ncol, 28)
        lv['pal_sky'] = colors(sky[ncol * 28 * 2:ncol * 28 * 2 + 64])       # palettes 1-2
        st = self._read('sky_tiles_%d.bin' % m['sky'])
        lv['sky_raw'] = st
        lv['sky_tiles'] = [tileq.decode4(st[i * 32:i * 32 + 32]) for i in range(len(st) // 32)]
        lv['sky_period'] = sk['period']
        self._lev[li] = lv
        return lv

    def palettes(self, li):
        """The 8 BG palettes (RGB 0-255) of a level; palette 0 is not ours."""
        lv = self.level(li)
        pal = np.zeros((8, 16, 3))
        pal[1:3] = lv['pal_sky'].reshape(2, 16, 3)
        pal[3:8] = lv['pal_bg1'].reshape(5, 16, 3)
        return pal

    def cell(self, li, cx, cy):
        """(kind, entry) of a cell: 0 air, 1 foreground texture, 2 special
        (entry of the chunk); outside the level the foreground."""
        lv = self.level(li)
        wc, hc = lv['cells']
        if cx < 0 or cy < 0 or cx >= wc or cy >= hc:
            return 1, 0
        d = int(lv['dirv'][(cy >> 3) * lv['cw'] + (cx >> 3)])
        if d < 2:
            return d, 0
        c = lv['chunks'][d - 0x8000:]
        i, j = cx & 7, cy & 7
        bit = 0x80 >> i
        if not c[j] & bit:
            return (1 if c[8 + j] & bit else 0), 0
        n = sum(popcount(c[r]) for r in range(j)) + popcount(c[j] & ~((0x100 >> i) - 1))
        assert c[16 + j] == sum(popcount(c[r]) for r in range(j))
        return 2, struct.unpack_from('<H', c, 24 + 2 * n)[0]

    def cell_tile(self, li, cx, cy):
        """The 32 bytes of the tile BG1 shows in a cell, its palette (0..7)
        and priority."""
        lv = self.level(li)
        ntx, nty = lv['tex']
        k, e = self.cell(li, cx, cy)
        if k == 0:
            return bytes(32), 0, 0
        t1 = (cy % nty) * ntx + (cx % ntx)
        if k == 1:
            return lv['tex_raw'][t1 * 32:t1 * 32 + 32], PAL_TEX, 0
        if e & 0x8000:
            g = lv['tbase'] + (e & 0xFFF)
            return self.tiles[g * 32:g * 32 + 32], PAL_CPLX + ((e >> 12) & 3), (e >> 14) & 1
        if e & 0x4000:
            ntx2, nty2 = lv['tex2']
            t = ntx * nty + (cy % nty2) * ntx2 + (cx % ntx2)
            pal = PAL_TEX + 1
        else:
            t, pal = t1, PAL_TEX
        src = lv['tex_raw'][t * 32:t * 32 + 32]
        m = e & 0x3FFF
        mk = self.masks[m * 16:m * 16 + 16]
        out = bytes(src[i] & mk[i & 15] for i in range(32))
        return out, pal, 0

    def sky_image(self, li):
        lv = self.level(li)
        if 'sky_img' not in lv:
            pal = self.palettes(li)
            P = lv['sky_period']
            img = np.zeros((224, P, 3))
            for c in range(P // 8):
                for r in range(28):
                    e = int(lv['sky_cols'][c][r])
                    t = lv['sky_tiles'][e & 0x3FF]
                    if e & 0x8000:
                        t = t[::-1]
                    img[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = pal[(e >> 10) & 7][t]
            lv['sky_img'] = img
        return lv['sky_img']

    def screen(self, li, cam_x, cam_y, w=256, h=224):
        """The expected picture (RGB 0-255 of SNES colors), BG1's opacity
        and its priority."""
        lv = self.level(li)
        pal = self.palettes(li)
        s = (cam_x + lv['skyk']) >> 1
        cols = (s + np.arange(w)) % lv['sky_period']
        out = self.sky_image(li)[:h][:, cols].copy()
        op = np.zeros((h, w), dtype=bool)
        pr = np.zeros((h, w), dtype=bool)
        cx0, cy0 = cam_x >> 3, cam_y >> 3
        nx = ((cam_x + w - 1) >> 3) - cx0 + 1
        ny = ((cam_y + h - 1) >> 3) - cy0 + 1
        big = np.zeros((ny * 8, nx * 8, 3))
        bop = np.zeros((ny * 8, nx * 8), dtype=bool)
        bpr = np.zeros((ny * 8, nx * 8), dtype=bool)
        for j in range(ny):
            for i in range(nx):
                data, p, prio = self.cell_tile(li, cx0 + i, cy0 + j)
                t = tileq.decode4(data)
                big[j * 8:j * 8 + 8, i * 8:i * 8 + 8] = pal[p][t]
                bop[j * 8:j * 8 + 8, i * 8:i * 8 + 8] = t > 0
                bpr[j * 8:j * 8 + 8, i * 8:i * 8 + 8] = prio
        ox, oy = cam_x & 7, cam_y & 7
        big, bop, bpr = big[oy:oy + h, ox:ox + w], bop[oy:oy + h, ox:ox + w], bpr[oy:oy + h, ox:ox + w]
        out[bop] = big[bop]
        op[:] = bop
        pr[:] = bpr & bop
        return out, op, pr


def main():
    from PIL import Image
    md = MapData(sys.argv[1])
    li, cx, cy = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    img, _, _ = md.screen(li, cx, cy)
    Image.fromarray(np.round(img).astype(np.uint8)).save(sys.argv[5])


if __name__ == '__main__':
    main()
