"""Sums up the output of physcheck -f: how long the bikes stay within 1 cm
and 10 cm of the original's, and whether the ends (dead, finish) and the
apples come at the same times.

  physsum.py OUTPUT [-v]
"""

import re
import sys

# physcheck reports the original engine clock, which advances 0.4368
# units per wall second. Keep its canonical dt and convert only the report.
GAME_UNITS_PER_SECOND = 0.4368


def events(s):
    out = []
    for name, t in re.findall(r'(dead|finish|eat)[a-z ]* ?([0-9.]+)', s):
        out.append((name, float(t) / GAME_UNITS_PER_SECOND))
    return out


def main():
    lines = open(sys.argv[1]).read().splitlines()
    verbose = '-v' in sys.argv
    cases = []
    for i, line in enumerate(lines):
        m = re.match(r'level\s+(\d+)\s+(.*?)\s+1cm\s+(-?[0-9.]+) 10cm\s+(-?[0-9.]+)\s+max ([0-9.]+)/([0-9.]+)/([0-9.]+) m', line)
        if not m:
            continue
        snes = lines[i + 1].split(':', 1)[1]
        orig = lines[i + 2].split(':', 1)[1]
        cases.append((int(m.group(1)), m.group(2), float(m.group(3)) / GAME_UNITS_PER_SECOND,
                      float(m.group(4)) / GAME_UNITS_PER_SECOND,
                      [float(m.group(k)) for k in (5, 6, 7)], events(snes), events(orig)))
    n = len(cases)

    def frac(cond):
        return sum(1 for c in cases if cond(c)) / max(n, 1)
    print('%d runs' % n)
    for lim in (0.5, 1.0, 2.0, 5.0):
        print('within 1 cm for at least %.1f s (or to the end): %.0f%%' % (
            lim, 100 * frac(lambda c: c[2] < 0 or c[2] >= lim)))
    for lim in (1.0, 2.0, 5.0):
        print('within 10 cm for at least %.1f s (or to the end): %.0f%%' % (
            lim, 100 * frac(lambda c: c[3] < 0 or c[3] >= lim)))
    # The end of the run (dead or finish) and the apples:
    same_end = 0
    ends = 0
    dts = []
    for c in cases:
        se = [e for e in c[5] if e[0] != 'eat']
        oe = [e for e in c[6] if e[0] != 'eat']
        if se or oe:
            ends += 1
            if se and oe and se[0][0] == oe[0][0]:
                dt = abs(se[0][1] - oe[0][1])
                dts.append(dt)
                if dt < 0.0001:
                    same_end += 1
    if ends:
        print('runs that ended: %d, the same way: %d, at the same step: %d' % (ends, len(dts), same_end))
        if dts:
            dts.sort()
            print('end time difference: median %.3f s, 90%% %.3f s' % (dts[len(dts) // 2], dts[int(len(dts) * 0.9)]))
    eats = sum(len([e for e in c[6] if e[0] == 'eat']) for c in cases)
    same = sum(len(set(e for e in c[5] if e[0] == 'eat') & set(e for e in c[6] if e[0] == 'eat')) for c in cases)
    print('apples eaten by the original: %d, by the SNES at the same step: %d' % (eats, same))
    if verbose:
        for c in sorted(cases, key=lambda c: (c[2] < 0, c[2]))[:20]:
            print(c[0], c[2], c[3], c[1][:60])


if __name__ == '__main__':
    main()
