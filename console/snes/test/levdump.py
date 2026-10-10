"""Writes the internal levels of an elma.res as text for the reference
physics (test/pcref): the exact numbers of the level file.

  levdump.py ELMA_RES OUT_DIR

OUT_DIR/levNN.txt for level NN (from 0): the number of polygons and
objects, then each polygon (grass flag, point count, points with y pointing
down as in the file), then each object (type, x, y pointing up, gravity,
animation), in the order of the file.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import elmadata  # noqa: E402


def main():
    levels = elmadata.internal_levels(elmadata.Resource(sys.argv[1]))
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for n, lev in enumerate(levels):
        lines = ['%d %d' % (len(lev.polygons), len(lev.objects))]
        for grass, poly in lev.polygons:
            lines.append('%d %d' % (1 if grass else 0, len(poly)))
            lines += ['%r %r' % (x, -y) for x, y in poly]
        for t, x, y, grav, anim in lev.objects:
            lines.append('%d %r %r %d %d' % (t, x, y, grav, anim))
        with open(os.path.join(out, 'lev%02d.txt' % n), 'w') as f:
            f.write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
