"""Generate exact tables for the scheduled cartridge's seat and ellipse constraints."""
from bisect import bisect_left
import math
import re

from head_clearance import write_if_changed


def generate(gen):
    header = (gen / 'riding_constants.h').read_text()
    constants = {name: int(value) for name, value in
                 re.findall(r'^#define (\w+) (-?\d+)$', header, re.M)}

    def coefficient(name):
        full, partial = map(int, re.search(
            rf'q24_C_{name}\[2\]\s*=\s*\{{(\d+),(\d+)\}}', header).groups())
        return full if full == partial else None

    nx, ny, ellipse = (coefficient(name) for name in ('SEAT_NX', 'SEAT_NY', 'ELLIPSE'))
    left, right, top = (constants[name] for name in ('RIDER_LEFT', 'RIDER_RIGHT', 'RIDER_TOP'))
    unit = 1 << 24
    if (None in (nx, ny, ellipse) or not (0 < nx < unit and 0 < ny < unit)
            or not (-512 <= left < 0 < right < 512 and 0 < top < 512)):
        return False

    lines = []

    def array(type_name, name, data):
        lines.append(f'static const {type_name} {name}[] = {{')
        lines.extend(','.join(map(str, data[i:i+32])) + ',' for i in range(0, len(data), 32))
        lines.append('};')

    # Split each 16-bit coordinate into a signed high byte and an unsigned
    # low byte. The cross-byte carry depends only on the rank of the low
    # product's fractional part among its 256 possible values.
    for axis, scale in [('x', nx), ('y', ny)]:
        low = [n * scale for n in range(256)]
        fractions = sorted(v % unit for v in low)
        array('uint8_t', 'whole_' + axis, [v // unit for v in low])
        array('uint8_t', 'rank_' + axis, [bisect_left(fractions, v % unit) for v in low])
        for name, offset, count in [('seat', -constants['SEAT_' + axis.upper()], 256),
                                    ('push', 0, 128)]:
            bases, cuts = [], []
            for i in range(count):
                high = i - 128 if name == 'push' else (i if i < 128 else i - 256)
                v = (high * 256 + offset) * scale + unit // 2
                base, rem = divmod(v, unit)
                if base < -32768 or (v + 255 * scale) // unit > 32767:
                    return False
                bases.append(base)
                cuts.append(bisect_left(fractions, unit - rem) - 1)
            array('int16_t', name + '_base_' + axis, bases)
            array('uint8_t', name + '_cut_' + axis, cuts)

    def rounded(n, scale):
        return (n * scale + unit // 2) >> 24

    bucket = list(map(int, re.search(
        r'^#define RIDING_ELLIPSE_INSIDE_Y_VALUES ([0-9,]+)$', header, re.M)[1].split(',')))
    squares = [rounded(x, ellipse) ** 2 for x in range(right + 1)]
    heights, top_x, top_y = [], [], []
    limit = top * top
    last_length = math.isqrt(limit + squares[-1])
    if not top < last_length <= top + 255:
        return False
    # A Q16 scale with a constant rounding offset can give the exact integer
    # quotient for both coordinates. Intersect the allowable offsets for all
    # coordinates with each denominator, then verify one lies in that interval.
    scale = [(top << 16) // d for d in range(top + 1, last_length + 1)]
    lower = [0] * len(scale)
    upper = [65535] * len(scale)
    for x, square in enumerate(squares):
        h = max(bucket[x >> constants['RIDING_ELLIPSE_BUCKET_SHIFT']],
                math.isqrt(max(0, limit - square)))
        heights.append(h)
        d = math.isqrt(square + limit)
        top_x.append(x * top // d)
        top_y.append(top * top // d)
        for y in range(max(1, h + 1), top + 1):
            d = math.isqrt(square + y * y)
            if d == top:
                continue
            i = d - top - 1
            for n in (x, y):
                bias = ((n * top // d) << 16) - n * scale[i]
                lower[i] = max(lower[i], bias)
                upper[i] = min(upper[i], bias + 65535)
    if (any(a > b for a, b in zip(lower, upper)) or max(top_x) > 255
            or min(top_y) < 256):
        return False

    # The native upper-seat path accepts this bounded x interval for every
    # signed y above fast_y, including values above the top plane. Prove the
    # separately rounded distance cannot become negative or wrap there.
    fast_x, fast_y = constants['RIDING_SEAT_FAST_X'], constants['RIDING_SEAT_FAST_Y']
    if (not constants['RIDING_SEAT_FAST_ENABLED'] or not (0 < fast_x <= min(254, right))
            or not (256 <= fast_y <= top) or left != -512
            or min(heights[1:fast_x + 1]) < 256 or max(heights[1:fast_x + 1]) >= top
            or rounded(fast_y - constants['SEAT_Y'], ny) < rounded(fast_x - constants['SEAT_X'], nx)
            or rounded(32767 - constants['SEAT_Y'], ny) - rounded(left - constants['SEAT_X'], nx) > 32767
            or rounded(top - constants['SEAT_Y'], ny) - rounded(-32768 - constants['SEAT_X'], nx) > 32767
            or min(scale) < 32768):
        return False
    band = []
    for x in range(fast_x + 1):
        for off in range(1, 9):
            y = min(top, heights[x] + off)
            d = math.isqrt(squares[x] + y * y)
            dx, dy = x - x * top // d, y - y * top // d
            if not (0 <= dx < 16 and 0 <= dy < 16):
                return False
            band.append(16 * dx + dy)
    array('uint8_t', 'upper_height', [n - 256 for n in heights[:fast_x + 1]])
    array('uint8_t', 'upper_edge', band)
    array('uint16_t', 'ellipse_height', heights)
    array('uint8_t', 'ellipse_top_x', top_x)
    array('uint8_t', 'ellipse_top_y', [y - 256 for y in top_y])
    # Two bytes need loading for most squares. The third plane also fits the
    # largest scaled x for every positive coordinate allowed by the clamps.
    array('uint16_t', 'ellipse_square_low', [v & 65535 for v in squares])
    array('uint8_t', 'ellipse_square_high', [v >> 16 for v in squares])
    # Once outside the ellipse, adjacent integer squares are more than 256
    # apart. A 256-wide bin contains at most one change in floor(sqrt).
    if 2 * top + 1 < 256:
        return False
    base, cut = [], []
    for group in range(limit >> 8, ((limit + squares[-1]) >> 8) + 1):
        first = group << 8
        d = max(top, math.isqrt(first))
        base.append(d - top)
        cut.append(min(255, (d + 1) ** 2 - first - 1))
    lines.append(f'#define ELLIPSE_FIRST_BIN {limit >> 8}')
    array('uint8_t', 'ellipse_root', base)
    array('uint8_t', 'ellipse_cut', cut)
    array('uint16_t', 'ellipse_scale', scale)
    array('uint16_t', 'ellipse_bias', lower)
    write_if_changed(gen / 'physics_seat_tables.h', '\n'.join(lines) + '\n')
    return True
