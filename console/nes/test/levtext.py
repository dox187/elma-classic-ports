"""Writes a level as text for physcmp: the number of its lines and the
start, then x y dx dy of each line (m, y up).

  levtext.py elma.res N      the Nth internal level of the game (from 1)
  levtext.py FILE.lev
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))
import elmadata  # noqa: E402


def main():
    if len(sys.argv) > 2:
        levs = elmadata.internal_levels(elmadata.Resource(sys.argv[1]))
        lev = levs[int(sys.argv[2]) - 1]
    else:
        lev = elmadata.load_lev(sys.argv[1])
    lines = []
    for grass, poly in lev.polygons:
        if grass:
            continue
        for i, a in enumerate(poly):
            b = poly[(i + 1) % len(poly)]
            lines.append((a[0], a[1], b[0] - a[0], b[1] - a[1]))
    sx, sy = lev.start()
    print(len(lines), sx, sy)
    for line in lines:
        print(*line)


if __name__ == '__main__':
    main()
