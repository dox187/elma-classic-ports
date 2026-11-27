"""Certify rounded normal lengths for physical wheel vectors in reciprocal-root bins."""
from math import isqrt

from head_clearance import write_if_changed


def length_row(start, reciprocal):
    # For n=floor(x*r/16), the exact length numerator times sixteen is
    # r*d2 - x*(x*r mod 16) - y*(y*r mod 16). Bound both discarded
    # fractions for every signed vector using |x|+|y| <= sqrt(2*d2).
    margin = 15 * isqrt(2 * (start + 511))
    slots = [(((d2 * reciprocal - margin + 131072) >> 18),
              (((d2 + 31) * reciprocal + margin + 131072) >> 18))
             for d2 in range(start, start + 512, 32)]
    # Pick the base and cuts retaining the most slots. For each returned
    # slot both integer bounds must equal the reader's decoded result.
    best = None
    for base in range(slots[0][0] - 1, slots[0][1] + 2):
        for first in range(16):
            for second in range(first, 16):
                retained = 0
                for k, (lower, upper) in enumerate(slots):
                    if k in (0, 15, first, first + 1, second, second + 1):
                        continue
                    if lower != upper or lower != base + (k > first) + (k > second):
                        break
                    retained += 1
                else:
                    choice = retained, base, first, second
                    if best is None or choice > best:
                        best = choice
    assert best and best[0] and 250 < best[1] < 506
    _, base, first, second = best
    return base - 250, first | second << 4


def generate(gen, reader, roots_path):
    roots = tuple(map(int, roots_path.read_text().split('\n', 1)[1].strip().rstrip(',').split(',')))
    results = []
    for bank, name, lower, upper in ((5, 'lower', 65536, 131072), (93, 'upper', 131072, 168448)):
        out = [f'.module normal_length_{name}', reader.read_text(), f'.area _CODE_{bank}',
               f'normal_read_{name}::', f' normal_length_reader normal_length_{name}',
               f'normal_length_{name}::']
        data = []
        for start in range(lower, upper, 512):
            data.extend(length_row(start, roots[(start - 16384) >> 9]))
        for i in range(0, len(data), 16):
            out.append(' .db ' + ','.join(map(str, data[i:i+16])))
        path = gen/f'normal_length_{name}.s'
        write_if_changed(path, '\n'.join(out) + '\n')
        results.append(path)
    return results
