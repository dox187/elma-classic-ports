"""Draws the map of a level from the data of the ROM (levels.bin, levels.c,
chr.bin of a build), to check the converter and its encoding.

  mapview.py BUILD_DIR LEVEL OUT.png
"""

import re
import sys

import numpy as np
from PIL import Image

RUNLEN = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 20, 24, 32, 48, 64]
COLORS = [(66, 158, 236), (60, 30, 10), (140, 70, 30), (60, 180, 60)]


def main():
    build, level, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    data = open(build + '/levels.bin', 'rb').read()
    chr_rom = open(build + '/chr.bin', 'rb').read()
    rows = re.findall(r'\{ Name\d+, ([-\d, ]+) \}', open(build + '/levels.c').read())
    f = [int(v) for v in rows[level].split(',')]
    w, h, columns, mp, chrbank = f[0], f[1], f[2], f[3], f[12]
    tiles = np.zeros((256, 8, 8), np.uint8)
    for t in range(256):
        base = (t * 16) if t < 128 else (chrbank * 1024 + (t - 128) * 16)
        lo, hi = chr_rom[base:base + 8], chr_rom[base + 8:base + 16]
        for y in range(8):
            for x in range(8):
                tiles[t, y, x] = ((lo[y] >> (7 - x)) & 1) | (((hi[y] >> (7 - x)) & 1) << 1)
    img = np.zeros((h * 8, w * 8, 3), np.uint8)
    for x in range(w):
        off = int.from_bytes(data[columns + 2 * x:columns + 2 * x + 2], 'little')
        p = mp + off
        y = 0
        while y < h:
            b = data[p]
            p += 1
            n, t = (RUNLEN[b & 15], 1 if b >= 240 else 0) if b >= 224 else (1, b)
            for k in range(n):
                if y < h:
                    img[y * 8:y * 8 + 8, x * 8:x * 8 + 8] = np.array(COLORS)[tiles[t]]
                y += 1
    Image.fromarray(img).save(out)


if __name__ == '__main__':
    main()
