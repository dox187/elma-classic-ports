"""Writes random cases for test/physcheck: keys held for random times, on
every level.

  physrand.py SEED [RUNS_PER_LEVEL] [LEVELS] > cases.txt
"""

import random
import sys


def script(rnd):
    items = []
    steps = 0
    while steps < 800:
        n = rnd.randint(8, 120)
        keys = ''
        if rnd.random() < 0.7:
            keys += 'G'
        if rnd.random() < 0.2:
            keys += 'B'
        r = rnd.random()
        if r < 0.15:
            keys += 'R'
        elif r < 0.3:
            keys += 'L'
        if rnd.random() < 0.1:
            keys += 'T'
        items.append('%s%d' % (keys or 'N', n))
        steps += n
    return ' '.join(items)


def main():
    rnd = random.Random(int(sys.argv[1]))
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    levels = int(sys.argv[3]) if len(sys.argv) > 3 else 54
    for lev in range(levels):
        for _ in range(runs):
            print(lev, script(rnd))


if __name__ == '__main__':
    main()
