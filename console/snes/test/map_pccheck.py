"""Checks the model of the original game's level picture (tools/mapmodel.py)
against the game itself: the PC reference tool (pcref) shows the start of
each level; the model draws the same picture from the bike's place, and
the two must be the same except where the bike, the objects, the time and
the map view are (pixels that the background does not draw).

  map_pccheck.py --pcref DIR [--levels 0,1,...] [--out DIR] [--low STATE]

Prints the pixels that differ for each level and saves the differences as
pictures (model | game | differences in magenta). --low: Video Detail Low,
with a state.dat of the game that has it (made in its Options menu).
"""

import argparse
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import elmadata  # noqa: E402
import mapmodel  # noqa: E402
from lgr import Lgr  # noqa: E402


def main():
    names = ['', '']
    try:
        with open(os.path.join(ROOT, 'build', 'gen', 'data_names')) as f:
            names = f.read().split()
    except OSError:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--pcref', required=True, help='directory of pcref.py')
    ap.add_argument('--res', default=os.environ.get('ELMA_RES', names[0]))
    ap.add_argument('--lgr', default=os.environ.get('ELMA_LGR', names[1]))
    ap.add_argument('--levels', default=','.join(str(i) for i in range(54)))
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'map_pccheck'))
    ap.add_argument('--low', metavar='STATE', help='Video Detail Low: the state.dat for pcref')
    a = ap.parse_args()
    from PIL import Image
    os.makedirs(a.out, exist_ok=True)
    levs = elmadata.internal_levels(elmadata.Resource(a.res))
    tex = mapmodel.Textures(Lgr(a.lgr))
    worst = 0
    for li in [int(x) for x in a.levels.split(',')]:
        shot = os.path.join(a.out, 'pc_%d.png' % li)
        dump = os.path.join(a.out, 'pc_%d.txt' % li)
        state = ['--state', os.path.abspath(a.low)] if a.low else []
        subprocess.run([sys.executable, os.path.join(a.pcref, 'pcref.py'), '-q', '-o', a.out] + state +
                       ['-l', str(li), 'DUMP:pc_%d.txt SHOT:pc_%d.png W1 DUMP:off' % (li, li)],
                       check=True, cwd=a.pcref)
        row = [ln for ln in open(dump) if not ln.startswith('#')][0].split()
        bx, by, bj = float(row[4]), float(row[5]), float(row[23])
        pl = mapmodel.PcLevel(levs[li], tex, detail=not a.low)
        ke, ye = mapmodel.pc_camera(pl, bx, by, bj)
        idx, _ = mapmodel.pc_picture(pl, ke, ye)
        got = np.array(Image.open(shot))
        diff = idx != got
        # The bike, the objects, the time and the map view are drawn over
        # the background: count the differences outside them only roughly,
        # by the size of the area that differs.
        n = int(diff.sum())
        worst = max(worst, n)
        pal = tex.pal.astype(np.uint8)
        d = np.zeros(idx.shape + (3,), dtype=np.uint8)
        d[diff] = (255, 0, 255)
        Image.fromarray(np.concatenate([pal[idx], pal[got], d], axis=1)).save(
            os.path.join(a.out, 'diff_%d.png' % li))
        print('%2d %-24s %6d pixels differ' % (li + 1, levs[li].name[:24], n))
    print('most: %d (the bike, objects, time and map view are about 10000-17000)' % worst)


if __name__ == '__main__':
    main()
